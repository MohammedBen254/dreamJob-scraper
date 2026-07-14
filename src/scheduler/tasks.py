from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select, func
from structlog import get_logger

from src.config import settings
from src.embedding.engine import embed_text, embed_query, rank_jobs
from src.notifications.email import EmailNotifier
from src.scraper.crawler import Crawler
from src.storage.database import JobRecord, async_session_factory
from src.storage.repository import JobRepository

logger = get_logger()


async def scrape_and_store() -> None:
    logger.info("scrape_cycle_started")

    async with async_session_factory() as session:
        repo = JobRepository(session)
        run = await repo.create_run()

        queries = await repo.get_queries()
        if not queries:
            logger.warning("no_queries_loaded_seeding")
            import pathlib
            import yaml

            path = pathlib.Path(settings.queries_path)
            if path.exists():
                with open(path) as f:
                    seed_data = yaml.safe_load(f)
                if seed_data:
                    await repo.seed_queries(seed_data)
                    queries = await repo.get_queries()

        query_vecs = []
        for q in queries:
            try:
                vec = await embed_query(q.query_text)
                query_vecs.append((q, vec))
            except Exception as e:
                logger.error("query_embed_failed", query_name=q.name, error=str(e))

        if not query_vecs:
            logger.error("no_query_embeddings_aborting")
            await repo.finish_run(run.id, 0, 0, status="failed")
            return

        logger.info("queries_embedded", count=len(query_vecs))

        categories: dict[str, dict] = {}
        jobs_matched = 0
        jobs_skipped = 0
        total_seen = 0

        crawler = Crawler()
        async for job, category_path in crawler.scrape_stream():
            total_seen += 1

            try:
                job_vec = await embed_text(f"{job.title} {job.description or ''}")
            except Exception as e:
                logger.error("job_embed_failed", url=str(job.url), error=str(e))
                await repo.add_run_error(run.id, str(job.url), str(e))
                record = await repo.store_job(job, run.id)
                if record:
                    await repo.update_job_status([record.id], "parsed")
                jobs_skipped += 1
                cat_stats = categories.setdefault(category_path, {"found": 0, "matched": 0, "skipped": 0, "unmatched": 0})
                cat_stats["found"] = cat_stats.get("found", 0) + 1
                cat_stats["skipped"] = cat_stats.get("skipped", 0) + 1
                continue

            best_score = 0.0
            best_query = None
            match_scores: list[tuple] = []
            for q, qvec in query_vecs:
                scores = rank_jobs(qvec, [job_vec], top_k=1)
                if scores and scores[0]["score"] > best_score:
                    best_score = scores[0]["score"]
                    best_query = q
                if scores and scores[0]["score"] >= settings.notification_threshold:
                    match_scores.append((q, round(scores[0]["score"] * 100, 1)))

            record = await repo.store_job(job, run.id)

            if best_score < settings.notification_threshold:
                logger.debug("job_unmatched", url=str(job.url), score=round(best_score * 100, 1))
                jobs_skipped += 1
                if record:
                    await repo.store_embedding(record.id, job_vec)
                    await repo.update_job_status([record.id], "embedded")
                cat_stats = categories.setdefault(category_path, {"found": 0, "matched": 0, "skipped": 0, "unmatched": 0})
                cat_stats["found"] = cat_stats.get("found", 0) + 1
                cat_stats["unmatched"] = cat_stats.get("unmatched", 0) + 1
                continue

            if record:
                await repo.store_embedding(record.id, job_vec)
                await repo.update_job_status([record.id], "embedded")
                await repo.increment_run_counter(run.id, "jobs_embedded")
                for q, score in match_scores:
                    await repo.store_match(record.id, q.id, score)
                jobs_matched += 1
                logger.info(
                    "job_matched_and_stored",
                    url=str(job.url),
                    score=round(best_score * 100, 1),
                    query=best_query.name if best_query else "",
                )
            else:
                logger.debug("job_duplicate", url=str(job.url))

            cat_stats = categories.setdefault(category_path, {"found": 0, "matched": 0, "skipped": 0})
            cat_stats["found"] = cat_stats.get("found", 0) + 1
            cat_stats["matched"] = cat_stats.get("matched", 0) + 1

        logger.info("scrape_stream_complete", total_seen=total_seen, matched=jobs_matched, skipped=jobs_skipped)

        await repo.update_run_categories(run.id, categories)

        jobs_found_result = await session.execute(
            select(func.count()).select_from(JobRecord).where(JobRecord.scrape_run_id == run.id)
        )
        jobs_found = jobs_found_result.scalar() or 0

        await repo.finish_run(run.id, jobs_found, jobs_matched)
        logger.info("scrape_cycle_complete", run_id=run.id, jobs_found=jobs_found, matched=jobs_matched, skipped=jobs_skipped)

    await _notify_matches(run.id)


async def _notify_matches(run_id: int | None = None) -> None:
    async with async_session_factory() as session:
        repo = JobRepository(session)
        queries = await repo.get_queries()
        if not queries:
            logger.info("no_saved_queries_skip_notify")
            return

        embedded_jobs = await repo.get_jobs_by_status("embedded")
        if not embedded_jobs:
            logger.info("no_embedded_jobs_skip_notify")
            return

        job_embeddings = [j.embedding for j in embedded_jobs if j.embedding]
        if not job_embeddings:
            logger.info("no_embedding_vectors_skip_notify")
            return

        matching_jobs = []

        for query in queries:
            logger.info("matching_query", query_name=query.name, query_text=query.query_text[:80])
            query_vec = await embed_query(query.query_text)
            ranked = rank_jobs(query_vec, job_embeddings, top_k=len(embedded_jobs))
            for r in ranked:
                job = embedded_jobs[r["corpus_id"]]
                score = r["score"]
                if score >= settings.notification_threshold and job.id not in {
                    j.id for j in matching_jobs
                }:
                    job.match_score = round(score * 100, 1)
                    matching_jobs.append(job)

        if matching_jobs:
            logger.info("matching_jobs", count=len(matching_jobs))
            notifier = EmailNotifier()
            sent = await notifier.send(matching_jobs)
            if sent:
                job_ids = [j.id for j in matching_jobs]
                await repo.mark_notified(job_ids)
                await repo.update_job_status(job_ids, "notified")
                if run_id:
                    async with async_session_factory() as session2:
                        repo2 = JobRepository(session2)
                        await repo2.increment_run_counter(run_id, "jobs_notified", len(job_ids))
                logger.info("notification_sent", count=len(job_ids))
        else:
            logger.info("no_matching_jobs")


def create_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()
    hour, minute = settings.scraper_run_time.split(":")
    scheduler.add_job(
        scrape_and_store,
        trigger=CronTrigger(hour=int(hour), minute=int(minute)),
        id="scrape_and_store",
        replace_existing=True,
    )
    return scheduler
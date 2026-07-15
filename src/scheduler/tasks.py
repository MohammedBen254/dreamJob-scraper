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

        rerank_candidates: dict[int, list[dict]] = {q.id: [] for q, _ in query_vecs}
        job_records: dict[int, JobRecord] = {}
        matched_job_ids: set[int] = set()

        categories: dict[str, dict] = {}
        jobs_skipped = 0
        total_seen = 0

        crawler = Crawler()
        async for job, category_path in crawler.scrape_stream():
            if settings.scraper_max_jobs > 0 and total_seen >= settings.scraper_max_jobs:
                logger.info("max_jobs_reached", max_jobs=settings.scraper_max_jobs)
                break
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
                cat_stats = categories.setdefault(
                    category_path, {"found": 0, "matched": 0, "skipped": 0, "unmatched": 0}
                )
                cat_stats["found"] = cat_stats.get("found", 0) + 1
                cat_stats["skipped"] = cat_stats.get("skipped", 0) + 1
                continue

            best_score = 0.0
            best_query = None
            for q, qvec in query_vecs:
                scores = rank_jobs(qvec, [job_vec], top_k=1)
                if scores and scores[0]["score"] > best_score:
                    best_score = scores[0]["score"]
                    best_query = q

            if best_score < settings.stage1_threshold:
                logger.debug("job_unmatched", url=str(job.url), score=round(best_score * 100, 1))
                jobs_skipped += 1
                record = await repo.store_job(job, run.id)
                if record:
                    await repo.store_embedding(record.id, job_vec)
                    await repo.update_job_status([record.id], "embedded")
                cat_stats = categories.setdefault(
                    category_path, {"found": 0, "matched": 0, "skipped": 0, "unmatched": 0}
                )
                cat_stats["found"] = cat_stats.get("found", 0) + 1
                cat_stats["unmatched"] = cat_stats.get("unmatched", 0) + 1
                continue

            record = await repo.store_job(job, run.id)

            if record:
                await repo.store_embedding(record.id, job_vec)
                await repo.update_job_status([record.id], "embedded")
                await repo.increment_run_counter(run.id, "jobs_embedded")
                job_records[record.id] = record
                for q, qvec in query_vecs:
                    scores = rank_jobs(qvec, [job_vec], top_k=1)
                    if scores and scores[0]["score"] >= settings.stage1_threshold:
                        rerank_candidates[q.id].append(
                            {
                                "job_id": record.id,
                                "job": job,
                                "job_vec": job_vec,
                                "cosine_score": round(scores[0]["score"] * 100, 1),
                                "description": job.description or job.title,
                                "title": job.title,
                            }
                        )
                logger.info(
                    "job_candidate_collected",
                    url=str(job.url),
                    best_score=round(best_score * 100, 1),
                    query=best_query.name if best_query else "",
                )
            else:
                existing = await repo.get_job_by_url(str(job.url))
                if existing and existing.id:
                    job_records[existing.id] = existing
                    if existing.embedding:
                        for q, qvec in query_vecs:
                            scores = rank_jobs(qvec, [existing.embedding], top_k=1)
                            if scores and scores[0]["score"] >= settings.stage1_threshold:
                                rerank_candidates[q.id].append(
                                    {
                                        "job_id": existing.id,
                                        "cosine_score": round(scores[0]["score"] * 100, 1),
                                        "description": job.description or job.title,
                                        "title": job.title,
                                    }
                                )
                logger.debug("job_duplicate", url=str(job.url))

            cat_stats = categories.setdefault(
                category_path, {"found": 0, "matched": 0, "skipped": 0}
            )
            cat_stats["found"] = cat_stats.get("found", 0) + 1
            cat_stats["matched"] = cat_stats.get("matched", 0) + 1

        logger.info(
            "scrape_stream_complete",
            total_seen=total_seen,
            stage1_candidates=sum(len(v) for v in rerank_candidates.values()),
            skipped=jobs_skipped,
        )

        if settings.use_reranker:
            from src.reranker.engine import rerank_query_matches

            for q, qvec in query_vecs:
                candidates = rerank_candidates[q.id]
                if not candidates:
                    logger.info("rerank_skip_no_candidates", query=q.name)
                    continue
                logger.info("rerank_start", query=q.name, candidates=len(candidates))
                try:
                    reranked = await rerank_query_matches(
                        q.query_text, candidates, top_k=settings.reranker_top_k
                    )
                except Exception as e:
                    logger.warning(
                        "reranker_failed_fallback_cosine", query_name=q.name, error=str(e)
                    )
                    for c in candidates:
                        rec = job_records.get(c["job_id"])
                        if rec:
                            await repo.store_match(rec.id, q.id, c["cosine_score"])
                            if c["cosine_score"] >= settings.notification_threshold * 100:
                                matched_job_ids.add(rec.id)
                    continue
                matched_count = 0
                for c in reranked:
                    rec = job_records.get(c["job_id"])
                    if rec:
                        await repo.store_match(rec.id, q.id, c["rerank_score"])
                        if c["rerank_score"] >= settings.notification_threshold * 100:
                            matched_job_ids.add(rec.id)
                            matched_count += 1
                logger.info(
                    "rerank_complete",
                    query=q.name,
                    candidates=len(candidates),
                    reranked=len(reranked),
                    matched=matched_count,
                    top_score=reranked[0]["rerank_score"] if reranked else 0,
                )
        else:
            for q, qvec in query_vecs:
                candidates = rerank_candidates[q.id]
                for c in candidates:
                    rec = job_records.get(c["job_id"])
                    if rec:
                        await repo.store_match(rec.id, q.id, c["cosine_score"])
                        if c["cosine_score"] >= settings.notification_threshold * 100:
                            matched_job_ids.add(rec.id)

        await repo.update_run_categories(run.id, categories)

        jobs_found_result = await session.execute(
            select(func.count()).select_from(JobRecord).where(JobRecord.scrape_run_id == run.id)
        )
        jobs_found = jobs_found_result.scalar() or 0

        await repo.finish_run(run.id, jobs_found, len(matched_job_ids))
        logger.info(
            "scrape_cycle_complete",
            run_id=run.id,
            jobs_found=jobs_found,
            matched=len(matched_job_ids),
            skipped=jobs_skipped,
        )

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
        all_match_scores = []

        for query in queries:
            logger.info("matching_query", query_name=query.name, query_text=query.query_text[:80])
            query_vec = await embed_query(query.query_text)
            ranked = rank_jobs(query_vec, job_embeddings, top_k=len(embedded_jobs))

            if settings.use_reranker:
                from src.reranker.engine import rerank_query_matches

                top_candidates = []
                for r in ranked:
                    job = embedded_jobs[r["corpus_id"]]
                    if r["score"] >= settings.stage1_threshold:
                        top_candidates.append(
                            {
                                "job_id": job.id,
                                "description": job.description or job.title,
                                "title": job.title,
                                "cosine_score": round(r["score"] * 100, 1),
                            }
                        )
                try:
                    reranked = await rerank_query_matches(
                        query.query_text, top_candidates, top_k=settings.reranker_top_k
                    )
                    for c in reranked:
                        job = next((j for j in embedded_jobs if j.id == c["job_id"]), None)
                        if job:
                            all_match_scores.append((job.id, query.id, c["rerank_score"]))
                            if c[
                                "rerank_score"
                            ] >= settings.notification_threshold * 100 and job.id not in {
                                j.id for j in matching_jobs
                            }:
                                job.match_score = c["rerank_score"]
                                matching_jobs.append(job)
                except Exception as e:
                    logger.warning(
                        "reranker_failed_fallback_cosine", query_name=query.name, error=str(e)
                    )
                    for r in ranked:
                        job = embedded_jobs[r["corpus_id"]]
                        score = r["score"]
                        all_match_scores.append((job.id, query.id, round(score * 100, 1)))
                        if score >= settings.notification_threshold and job.id not in {
                            j.id for j in matching_jobs
                        }:
                            job.match_score = round(score * 100, 1)
                            matching_jobs.append(job)
            else:
                for r in ranked:
                    job = embedded_jobs[r["corpus_id"]]
                    score = r["score"]
                    all_match_scores.append((job.id, query.id, round(score * 100, 1)))
                    if score >= settings.notification_threshold and job.id not in {
                        j.id for j in matching_jobs
                    }:
                        job.match_score = round(score * 100, 1)
                        matching_jobs.append(job)

        for job_id, query_id, score in all_match_scores:
            await repo.store_match(job_id, query_id, score)

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

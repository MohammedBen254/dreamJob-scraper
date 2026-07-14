from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from structlog import get_logger

from src.config import settings
from src.embedding.engine import embed_jobs, embed_query, rank_jobs
from src.notifications.email import EmailNotifier
from src.scraper.crawler import Crawler
from src.storage.database import async_session_factory
from src.storage.repository import JobRepository

logger = get_logger()


async def scrape_and_store() -> None:
    logger.info("scrape_cycle_started")

    async with async_session_factory() as session:
        repo = JobRepository(session)

        crawler = Crawler()
        jobs = await crawler.scrape_all()
        logger.info("scrape_complete", total=len(jobs))

        run = await repo.create_run()
        new_count = await repo.store_jobs(jobs)
        logger.info("jobs_stored", new=new_count, total=len(jobs))
        await repo.finish_run(run.id, len(jobs), new_count)

        stored = await repo.get_all_jobs_with_embeddings()
        unembedded = [j for j in stored if j.embedding is None]
        if unembedded:
            logger.info("embedding_jobs", count=len(unembedded))
            try:
                embeddings = await embed_jobs(unembedded)
                for job, emb in zip(unembedded, embeddings):
                    await repo.store_embedding(job.id, emb)
                logger.info("embedding_complete", count=len(embeddings))
            except Exception as e:
                logger.error("embedding_failed", error=str(e), unembedded_count=len(unembedded))
        else:
            logger.info("no_unembedded_jobs")

    # Send email notifications for matching jobs
    await _notify_matches()


async def _notify_matches() -> None:
    async with async_session_factory() as session:
        repo = JobRepository(session)
        queries = await repo.get_queries()
        if not queries:
            logger.info("no_saved_queries_skip_notify")
            return

        jobs = await repo.get_all_jobs_with_embeddings()
        job_embeddings = [j.embedding for j in jobs if j.embedding]
        if not job_embeddings:
            logger.info("no_embedded_jobs_skip_notify")
            return

        matching_jobs = []

        for query in queries:
            logger.info("matching_query", query_name=query.name, query_text=query.query_text[:80])
            query_vec = await embed_query(query.query_text)
            ranked = rank_jobs(query_vec, job_embeddings, top_k=len(jobs))
            for r in ranked:
                job = jobs[r["corpus_id"]]
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

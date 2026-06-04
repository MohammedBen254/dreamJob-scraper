from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from structlog import get_logger

from src.config import settings
from src.matching.engine import score_jobs
from src.models.profile import UserProfile
from src.notifications.email import EmailNotifier
from src.scraper.crawler import Crawler
from src.storage.database import async_session_factory
from src.storage.repository import JobRepository

logger = get_logger()


async def scrape_and_notify() -> None:
    logger.info("scrape_cycle_started")
    profile = UserProfile.load(settings.profile_path)

    async with async_session_factory() as session:
        repo = JobRepository(session)

        crawler = Crawler()
        jobs = await crawler.scrape_all()
        logger.info("scrape_complete", total=len(jobs))

        run = await repo.create_run()
        scored = score_jobs(jobs, profile)
        new_count = await repo.store_jobs(scored)
        await repo.finish_run(run.id, len(jobs), new_count)

        matching = [j for j in scored if j.match_score >= profile.threshold]
        if matching:
            logger.info("matching_jobs", count=len(matching))

            notifier = EmailNotifier()
            sent = await notifier.send(matching)
            if sent:
                job_ids = [j.id for j in matching if hasattr(j, "id")]
                if job_ids:
                    await repo.mark_notified(job_ids)
        else:
            logger.info("no_matching_jobs")

    logger.info("scrape_cycle_completed")


def create_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()
    hour, minute = settings.scraper_run_time.split(":")
    scheduler.add_job(
        scrape_and_notify,
        trigger=CronTrigger(hour=int(hour), minute=int(minute)),
        id="scrape_and_notify",
        replace_existing=True,
    )
    return scheduler

from __future__ import annotations

import asyncio
import sys

import yaml
import uvicorn
from structlog import get_logger

from src.config import settings
from src.scheduler.tasks import create_scheduler, scrape_and_store

logger = get_logger()


async def cmd_scrape() -> None:
    logger.info("command: scrape")
    await scrape_and_store()


async def cmd_web() -> None:
    logger.info("command: web")
    from src.web.app import app

    config = uvicorn.Config(app, host="0.0.0.0", port=settings.web_port, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()


async def _run_migrations() -> None:
    from alembic.config import Config as AlembicConfig
    from alembic import command

    loop = asyncio.get_running_loop()
    cfg = AlembicConfig("alembic.ini")
    await loop.run_in_executor(None, command.upgrade, cfg, "head")


async def _send_ready_if_first_run() -> None:
    from src.notifications.email import EmailNotifier
    from src.storage.database import async_session_factory
    from src.storage.repository import JobRepository

    await _run_migrations()
    async with async_session_factory() as session:
        repo = JobRepository(session)
        await _seed_queries(repo)
        if not await repo.has_any_runs():
            hour, minute = settings.scraper_run_time.split(":")
            next_run = f"{hour}:{minute}"
            notifier = EmailNotifier()
            await notifier.send_ready(next_run)


async def _seed_queries(repo) -> None:
    import pathlib

    path = pathlib.Path(settings.queries_path)
    if path.exists():
        with open(path) as f:
            queries = yaml.safe_load(f)
        if queries:
            await repo.seed_queries(queries)
            logger.info("queries_seeded", count=len(queries))


async def cmd_schedule() -> None:
    logger.info("command: schedule")
    await _send_ready_if_first_run()
    scheduler = create_scheduler()
    scheduler.start()
    try:
        while True:
            await asyncio.sleep(3600)
    except (KeyboardInterrupt, asyncio.CancelledError):
        scheduler.shutdown(wait=False)


async def cmd_migrate() -> None:
    logger.info("command: migrate")
    await _run_migrations()


async def cmd_seed() -> None:
    from src.storage.database import async_session_factory
    from src.storage.repository import JobRepository

    await _run_migrations()
    with open(settings.queries_path) as f:
        queries = yaml.safe_load(f)
    async with async_session_factory() as session:
        repo = JobRepository(session)
        await repo.seed_queries(queries)
    logger.info("queries_seeded", count=len(queries))


def main() -> None:
    import logging

    logging.basicConfig(level=logging.INFO)

    cmd = sys.argv[1] if len(sys.argv) > 1 else "schedule"

    if cmd == "scrape":
        asyncio.run(cmd_scrape())
    elif cmd == "schedule":
        asyncio.run(cmd_schedule())
    elif cmd == "migrate":
        asyncio.run(cmd_migrate())
    elif cmd == "seed":
        asyncio.run(cmd_seed())
    elif cmd == "web":
        asyncio.run(cmd_web())
    elif cmd == "health":
        from scripts.healthcheck import run_health_server

        run_health_server()
    else:
        print("Usage: dreamjob {scrape|schedule|web|health|migrate|seed}")
        sys.exit(1)


if __name__ == "__main__":
    main()

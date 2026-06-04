from email.mime.text import MIMEText
from pathlib import Path

import aiosmtplib
from jinja2 import Environment, FileSystemLoader
from structlog import get_logger

from src.config import settings
from src.models.job import JobPosting
from src.notifications.base import Notifier

logger = get_logger()

TEMPLATE_DIR = Path(__file__).parent / "templates" / "email"
env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)))


class EmailNotifier(Notifier):
    def __init__(self) -> None:
        self._digest_template = env.get_template("digest.html")
        self._ready_template = env.get_template("ready.html")

    async def _send_message(self, subject: str, html: str) -> bool:
        msg = MIMEText(html, "html", "utf-8")
        msg["From"] = settings.email_from
        msg["To"] = settings.email_to
        msg["Subject"] = subject
        try:
            await aiosmtplib.send(
                msg,
                sender=settings.email_from,
                recipients=[settings.email_to],
                hostname=settings.email_smtp_host,
                port=settings.email_smtp_port,
                username=settings.email_username,
                password=settings.email_password,
                use_tls=settings.email_smtp_port == 465,
                start_tls=settings.email_smtp_port == 587,
            )
            return True
        except Exception as e:
            logger.error("email_failed", subject=subject, error=str(e))
            return False

    async def send_ready(self, next_run: str) -> bool:
        html = self._ready_template.render(
            next_run=next_run,
            threshold=settings.matching_threshold,
            page_limit=settings.scraper_page_limit,
            categories=["emploi", "stage", "emploi-public", "emploi-international"],
        )
        ok = await self._send_message("[DreamJob Scraper] System Ready", html)
        if ok:
            logger.info("ready_email_sent")
        return ok

    async def send(self, jobs: list[JobPosting]) -> bool:
        if not jobs:
            logger.info("no_jobs_to_notify")
            return True

        categories = {j.category for j in jobs if j.category}
        subject = (
            f"[DreamJob Scraper] {len(jobs)} new matches"
            f" — {', '.join(sorted(categories))}"
        )
        html = self._digest_template.render(
            jobs=sorted(jobs, key=lambda j: j.match_score, reverse=True),
        )
        ok = await self._send_message(subject, html)
        if ok:
            logger.info("email_sent", count=len(jobs), subject=subject)
        return ok

import asyncio

from structlog import get_logger

from src.config import settings
from src.models.job import JobPosting
from src.scraper.client import ScrapeClient
from src.scraper.parser import parse_detail_page, parse_listing_page

logger = get_logger()

CATEGORY_PATHS = [
    "/emploi/",
    "/stage/",
    "/emploi-public/",
    "/emploi-international/",
]


class Crawler:
    def __init__(self, client: ScrapeClient | None = None) -> None:
        self._client = client or ScrapeClient()

    async def scrape_all(self) -> list[JobPosting]:
        all_jobs: list[JobPosting] = []
        base = settings.scraper_target_url.rstrip("/")

        for path in CATEGORY_PATHS:
            jobs = await self._scrape_category(base, path)
            logger.info("category_done", category=path, count=len(jobs))
            all_jobs.extend(jobs)

        await self._client.close()
        return all_jobs

    async def _scrape_category(self, base: str, path: str, page: int = 1) -> list[JobPosting]:
        if page > settings.scraper_page_limit:
            return []

        url = f"{base}{path}"
        if page > 1:
            url = f"{base}{path}page/{page}/"

        logger.info("scraping_listing", url=url, page=page)
        try:
            html = await self._client.fetch(url)
        except Exception as e:
            logger.error("listing_failed", url=url, error=str(e))
            return []

        entries, next_url = parse_listing_page(html, base)
        logger.info("parsed_listing", url=url, entries=len(entries))

        jobs = await self._fetch_details(entries)
        if next_url and page < settings.scraper_page_limit:
            more = await self._scrape_category(base, path, page + 1)
            jobs.extend(more)

        return jobs

    async def _fetch_details(
        self, entries: list[tuple[str, str, str | None, str | None]]
    ) -> list[JobPosting]:
        async def fetch_one(
            title: str, url: str, date_text: str | None, excerpt: str | None
        ) -> JobPosting | None:
            try:
                html = await self._client.fetch(url)
                job = await parse_detail_page(html, url, self._client)
                return job
            except Exception as e:
                logger.error("detail_failed", url=url, error=str(e))
                return None

        tasks = [fetch_one(*e) for e in entries]
        results = await asyncio.gather(*tasks)
        return [j for j in results if j is not None]

import asyncio
import random

import httpx
from structlog import get_logger

from src.config import settings

logger = get_logger()

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:120.0) Gecko/20100101 Firefox/120.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/119.0.0.0 Safari/537.36",
]


class ScrapeClient:
    def __init__(self) -> None:
        self._semaphore = asyncio.Semaphore(2)
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(30.0),
            follow_redirects=True,
        )

    async def fetch(self, url: str) -> str:
        async with self._semaphore:
            delay = settings.scraper_request_delay + random.uniform(0.5, 1.5)
            await asyncio.sleep(delay)

            last_error: Exception | None = None
            for attempt in range(3):
                try:
                    headers = {
                        "User-Agent": random.choice(USER_AGENTS),
                        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                        "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
                    }
                    resp = await self._client.get(url, headers=headers)
                    resp.raise_for_status()
                    logger.info("fetched_page", url=url, status=resp.status_code)
                    return resp.text
                except httpx.HTTPError as e:
                    last_error = e
                    logger.warning(
                        "fetch_retry",
                        url=url,
                        attempt=attempt + 1,
                        error=str(e),
                    )
                    if attempt < 2:
                        wait = 2 ** attempt * random.uniform(1, 2)
                        await asyncio.sleep(wait)
            if last_error is not None:
                raise last_error
            raise RuntimeError(f"Failed to fetch {url}")

    async def close(self) -> None:
        await self._client.aclose()

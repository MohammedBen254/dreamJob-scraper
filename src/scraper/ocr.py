import base64
import hashlib

import httpx
from ollama import AsyncClient
from structlog import get_logger

from src.config import settings

logger = get_logger()

_OCR_MODEL = "minicpm-v"
_client: AsyncClient | None = None

_OCR_CACHE: dict[str, str] = {}


def _get_client() -> AsyncClient:
    global _client
    if _client is None:
        _client = AsyncClient(host=settings.ollama_host)
    return _client


def _image_hash(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest()


async def ocr_image(client: httpx.AsyncClient, url: str) -> str:
    img_hash = _image_hash(url)
    if img_hash in _OCR_CACHE:
        return _OCR_CACHE[img_hash]

    try:
        resp = await client.get(url, timeout=30)
        resp.raise_for_status()
        image_b64 = base64.b64encode(resp.content).decode("utf-8")
        ollama = _get_client()
        response = await ollama.chat(
            model=_OCR_MODEL,
            messages=[
                {
                    "role": "user",
                    "content": "Extract all text from this image. The text may be in Arabic, French, or English. Return only the extracted text, nothing else.",
                    "images": [image_b64],
                },
            ],
        )
        text = response["message"]["content"].strip()
        _OCR_CACHE[img_hash] = text
        return text
    except Exception as e:
        logger.warning("ocr_failed", url=url, error=str(e))
        return ""


def needs_ocr(soup) -> bool:
    content = soup.select_one(".entry-content, .content-inner")
    if not content:
        return False
    text_len = len(content.get_text(strip=True))
    img_count = len(content.find_all("img"))
    return img_count > 0 and text_len < 200

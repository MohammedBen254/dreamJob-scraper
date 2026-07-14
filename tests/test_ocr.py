import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from bs4 import BeautifulSoup

from src.scraper.ocr import needs_ocr


def test_needs_ocr_returns_true_for_image_dominant_page():
    html = '<div class="entry-content"><img src="a.jpg"><img src="b.jpg"><p>Hi</p></div>'
    soup = BeautifulSoup(html, "lxml")
    assert needs_ocr(soup) is True


def test_needs_ocr_returns_false_for_text_dominant_page():
    html = '<div class="entry-content"><p>' + ("A" * 500) + "</p></div>"
    soup = BeautifulSoup(html, "lxml")
    assert needs_ocr(soup) is False


def test_needs_ocr_returns_false_when_no_content():
    soup = BeautifulSoup("<html></html>", "lxml")
    assert needs_ocr(soup) is False


@pytest.mark.asyncio
async def test_ocr_image_calls_ollama():
    with patch("src.scraper.ocr._get_client") as mock_get_client:
        mock_client = AsyncMock()
        mock_get_client.return_value = mock_client
        mock_client.chat = AsyncMock(
            return_value={"message": {"content": "  Extracted text from image  "}}
        )
        mock_http_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.content = b"fake-image-bytes"
        mock_http_client.get = AsyncMock(return_value=mock_response)

        from src.scraper.ocr import ocr_image

        result = await ocr_image(mock_http_client, "https://example.com/image.jpg")
        assert result == "Extracted text from image"
        mock_client.chat.assert_called_once()


@pytest.mark.asyncio
async def test_ocr_image_returns_empty_on_error():
    with patch("src.scraper.ocr._get_client") as mock_get_client:
        mock_client = AsyncMock()
        mock_get_client.return_value = mock_client
        mock_client.chat = AsyncMock(side_effect=Exception("Ollama unavailable"))
        mock_http_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.content = b"fake-image-bytes"
        mock_http_client.get = AsyncMock(return_value=mock_response)

        from src.scraper.ocr import ocr_image

        result = await ocr_image(mock_http_client, "https://example.com/image.jpg")
        assert result == ""

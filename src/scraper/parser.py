import re
from datetime import date, datetime
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from pydantic import HttpUrl

from src.models.job import JobPosting
from src.scraper.selectors import (
    CONTENT_SELECTOR,
    DATE_SELECTOR,
    LISTING_CONTAINER,
    META_SELECTOR,
    NEXT_PAGE_SELECTOR,
    TITLE_SELECTOR,
)


def parse_listing_page(html: str, base_url: str) -> tuple[list[tuple[str, str, str | None, str | None]], str | None]:
    soup = BeautifulSoup(html, "lxml")
    cards = soup.select(LISTING_CONTAINER)
    results: list[tuple[str, str, str | None, str | None]] = []

    for card in cards:
        title_el = card.select_one(TITLE_SELECTOR)
        if not title_el:
            continue
        title = title_el.get_text(strip=True)
        href = title_el.get("href")
        if not href:
            continue
        href_str = str(href)
        url = urljoin(base_url, href_str)

        date_el = card.select_one(DATE_SELECTOR)
        date_text = date_el.get_text(strip=True) if date_el else None

        meta_el = card.select_one(META_SELECTOR)
        excerpt = meta_el.get_text(" ", strip=True) if meta_el else None

        results.append((title, url, date_text, excerpt))

    next_el = soup.select_one(NEXT_PAGE_SELECTOR)
    next_url: str | None = None
    if next_el:
        next_href = next_el.get("href")
        if next_href:
            next_url = urljoin(base_url, str(next_href))

    return results, next_url


_DATE_PATTERNS = [
    re.compile(r"(\d{2})/(\d{2})/(\d{4})"),
    re.compile(r"(\d{4})-(\d{2})-(\d{2})"),
]


def _parse_date(text: str | None) -> date | None:
    if not text:
        return None
    for pat in _DATE_PATTERNS:
        m = pat.search(text)
        if m:
            parts = m.groups()
            if len(parts[0]) == 4:
                return date(int(parts[0]), int(parts[1]), int(parts[2]))
            return date(int(parts[2]), int(parts[1]), int(parts[0]))
    return None


def _extract_meta_date(soup: BeautifulSoup) -> date | None:
    for meta in soup.find_all("meta", property="article:published_time"):
        raw = meta.get("content", "")
        content = str(raw) if raw else ""
        if content:
            try:
                dt = datetime.fromisoformat(content)
                return dt.date()
            except ValueError:
                pass
    return None


def _extract_company(soup: BeautifulSoup) -> str | None:
    patterns = [
        "span.jeg_meta_author a",
        ".jeg_meta_author a",
        "a[rel='author']",
        ".jeg_post_meta .jeg_meta_author",
    ]
    for sel in patterns:
        el = soup.select_one(sel)
        if el:
            return el.get_text(strip=True)
    return None


def _extract_location(soup: BeautifulSoup) -> str | None:
    for el in soup.select(".jeg_post_meta span, .location, .jeg_meta_location"):
        text = el.get_text(strip=True)
        if any(c in text.lower() for c in
               ["maroc", "casablanca", "rabat", "tanger", "marrakech", "fès",
                "fes", "meknès", "meknes", "oujda", "agadir"]):
            return text
    return None


def _extract_salary(soup: BeautifulSoup) -> str | None:
    for el in soup.select(".salary, .jeg_post_meta .salary"):
        text = el.get_text(strip=True)
        if "dh" in text.lower() or "mad" in text.lower() or "€" in text or "$" in text:
            return text
    content = soup.select_one(CONTENT_SELECTOR)
    if content:
        for p in content.find_all("p"):
            text = p.get_text(strip=True)
            if "salaire" in text.lower() and ("dh" in text.lower() or "mad" in text.lower()):
                return text
    return None


def parse_detail_page(html: str, job_url: str) -> JobPosting:
    soup = BeautifulSoup(html, "lxml")
    title_el = soup.select_one("h1.jeg_post_title")
    title = title_el.get_text(strip=True) if title_el else ""

    company = _extract_company(soup)
    location = _extract_location(soup)
    salary = _extract_salary(soup)

    meta_date = _extract_meta_date(soup)
    date_text = None
    if not meta_date:
        date_el = soup.select_one(DATE_SELECTOR)
        date_text = date_el.get_text(strip=True) if date_el else None

    content_el = soup.select_one(CONTENT_SELECTOR)
    description = content_el.get_text("\n", strip=True) if content_el else None

    category = _infer_category(job_url)

    posting = JobPosting(
        title=title,
        company=company,
        location=location or _guess_location_from_text(description),
        category=category,
        url=HttpUrl(job_url),
        date_posted=meta_date or _parse_date(date_text),
        description=description,
        salary=salary,
    )
    posting.compute_hash()
    return posting


_CATEGORY_PATTERNS: list[tuple[str, str]] = [
    ("emploi-public", "emploi-public"),
    ("emploi-international", "emploi-international"),
    ("stage", "stage"),
    ("emploi", "emploi"),
]


def _infer_category(url: str) -> str:
    for pattern, label in _CATEGORY_PATTERNS:
        if f"/{pattern}/" in url:
            return label
    return "emploi"


def _guess_location_from_text(text: str | None) -> str | None:
    if not text:
        return None
    cities = [
        "casablanca", "rabat", "tanger", "marrakech", "fès", "fes",
        "meknès", "meknes", "oujda", "agadir", "kenitra", "el jadida",
        "tétouan", "tetouan", "safi", "beni mellal", "nador", "laâyoune",
        "laayoune", "dakhla", "maroc",
    ]
    text_lower = text.lower()
    for city in cities:
        if city in text_lower:
            return city.capitalize()
    return None

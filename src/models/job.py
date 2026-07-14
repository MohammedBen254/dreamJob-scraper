import hashlib
from datetime import date

from pydantic import BaseModel, HttpUrl


class JobPosting(BaseModel):
    title: str
    company: str | None = None
    location: str | None = None
    category: str | None = None
    url: HttpUrl
    date_posted: date | None = None
    description: str | None = None
    salary: str | None = None
    match_score: float = 0.0
    content_hash: str = ""
    ocr_results: list[dict] | None = None

    def compute_hash(self) -> str:
        raw = (self.description or "") + self.title + (self.company or "")
        self.content_hash = hashlib.sha256(raw.encode()).hexdigest()
        return self.content_hash

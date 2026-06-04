from thefuzz import fuzz

from src.models.job import JobPosting
from src.models.profile import UserProfile


def _title_match(title: str, keywords: set[str]) -> float:
    title_lower = title.lower()
    score = 0.0
    for kw in keywords:
        if kw in title_lower:
            score += 40.0
            break
    if score == 0.0:
        for kw in keywords:
            ratio = fuzz.token_sort_ratio(title_lower, kw)
            if ratio >= 80:
                score += 20.0
                break
    return min(score, 60.0)


def _category_alignment(category: str | None, keywords: set[str], target_keywords: dict[str, list[str]]) -> float:
    if not category:
        return 0.0
    for field, kws in target_keywords.items():
        if any(kw in category.lower() for kw in kws):
            return 20.0
    return 0.0


def _description_relevance(description: str | None, keywords: set[str]) -> float:
    if not description:
        return 0.0
    desc_lower = description.lower()
    matches = sum(1 for kw in keywords if kw in desc_lower)
    if matches == 0:
        return 0.0
    score = min(matches * 5.0, 20.0)
    return score


def _excluded_terms_penalty(
    title: str, description: str | None, excluded: list[str]
) -> float:
    combined = (title + " " + (description or "")).lower()
    penalty = 0.0
    for term in excluded:
        if term.lower() in combined:
            penalty -= 30.0
    return penalty


def score_job(job: JobPosting, profile: UserProfile) -> float:
    keywords = profile.get_expanded_keywords()
    excluded = profile.excluded_terms

    title_score = _title_match(job.title, keywords)
    cat_score = _category_alignment(
        job.category, keywords, profile.target_keywords
    )
    desc_score = _description_relevance(job.description, keywords)
    ex_penalty = _excluded_terms_penalty(job.title, job.description, excluded)

    total = title_score + cat_score + desc_score + ex_penalty
    return min(100.0, max(0.0, total))


def score_jobs(jobs: list[JobPosting], profile: UserProfile) -> list[JobPosting]:
    for job in jobs:
        job.match_score = score_job(job, profile)
    return jobs

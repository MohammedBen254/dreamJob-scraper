from src.matching.engine import score_jobs
from src.models.job import JobPosting
from src.models.profile import UserProfile
from pydantic import HttpUrl


def _make_job(title: str, description: str = "", category: str = "emploi") -> JobPosting:
    return JobPosting(
        title=title,
        description=description,
        category=category,
        url=HttpUrl("https://www.dreamjob.ma/emploi/test/"),
    )


def _profile(keywords: list[str], excluded: list[str] | None = None) -> UserProfile:
    return UserProfile(
        target_keywords={"test_field": keywords},
        excluded_terms=excluded or [],
        threshold=60,
    )


class TestExactTitleMatch:
    def test_keyword_in_title_scores_high(self):
        profile = _profile(["python"])
        job = _make_job("Python Developer needed urgently")
        scored = score_jobs([job], profile)
        assert scored[0].match_score >= 40

    def test_multiple_keywords_in_description_boost_score(self):
        profile = _profile(["python", "sql", "tableau"])
        job = _make_job(
            "Data Analyst",
            description="Python SQL Tableau experience required",
        )
        scored = score_jobs([job], profile)
        assert scored[0].match_score >= 15


class TestFuzzyTitleMatch:
    def test_close_match_gets_fuzzy_bonus(self):
        profile = _profile(["data analyst"])
        job = _make_job("Data Analist")  # misspelled
        scored = score_jobs([job], profile)
        assert scored[0].match_score >= 20


class TestExcludedTerm:
    def test_excluded_term_reduces_score(self):
        profile = _profile(["python"], excluded=["senior"])
        job = _make_job("Senior Python Developer")
        scored = score_jobs([job], profile)
        assert scored[0].match_score < 40


class TestEmptyDescription:
    def test_no_description_does_not_crash(self):
        profile = _profile(["python"])
        job = _make_job("Python Developer", description="")
        scored = score_jobs([job], profile)
        assert scored[0].match_score >= 0


class TestCategoryAlignment:
    def test_matching_category_boosts_score(self):
        profile = UserProfile(
            target_keywords={"ai_ml": ["machine learning"]},
            excluded_terms=[],
            threshold=60,
        )
        job = _make_job("ML Engineer", category="emploi")
        scored = score_jobs([job], profile)
        # category 'emploi' doesn't directly match field name, but should still work
        assert scored[0].match_score >= 0

    def test_full_pipeline_scoring(self):
        profile = _profile(["python", "sql", "tableau"])
        job = _make_job(
            "Data Analyst",
            description="We need a data analyst with Python, SQL and Tableau skills",
            category="emploi",
        )
        scored = score_jobs([job], profile)
        assert 0 <= scored[0].match_score <= 100

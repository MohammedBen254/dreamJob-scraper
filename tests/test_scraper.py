import pytest
from pydantic import HttpUrl

from src.scraper.parser import parse_listing_page, parse_detail_page


class TestParseListingPage:
    def test_extracts_job_cards(self, sample_listing_html):
        entries, next_url = parse_listing_page(sample_listing_html, "https://www.dreamjob.ma")
        assert len(entries) == 2
        assert entries[0][0] == "Data Analyst"
        assert entries[1][0] == "Développeur Python"

    def test_detects_pagination(self, sample_listing_html):
        entries, next_url = parse_listing_page(sample_listing_html, "https://www.dreamjob.ma")
        assert next_url == "https://www.dreamjob.ma/emploi/page/2/"

    def test_no_next_page(self):
        html = "<html><body><article class='jeg_post'><h3 class='jeg_post_title'><a href='/job/'>Job</a></h3></article></body></html>"
        entries, next_url = parse_listing_page(html, "https://www.dreamjob.ma")
        assert next_url is None


class TestParseDetailPage:
    def test_extracts_all_fields(self, sample_detail_html):
        job = parse_detail_page(sample_detail_html, "https://www.dreamjob.ma/emploi/data-analyst/")
        assert job.title == "Data Analyst"
        assert job.company == "Tech Corp"
        assert job.date_posted is not None
        assert str(job.date_posted) == "2024-05-12"
        assert job.description is not None
        assert "Python" in job.description
        assert job.category == "emploi"

    def test_content_hash_is_computed(self, sample_detail_html):
        job = parse_detail_page(sample_detail_html, "https://www.dreamjob.ma/emploi/data-analyst/")
        assert len(job.content_hash) == 64

    def test_missing_title_handled(self):
        html = "<html><body><div class='content-inner'>Some content</div></body></html>"
        job = parse_detail_page(html, "https://www.dreamjob.ma/emploi/test/")
        assert job.title == ""

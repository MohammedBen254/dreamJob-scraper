import pytest


@pytest.fixture
def sample_listing_html() -> str:
    return """<!DOCTYPE html>
<html><body>
<article class="jeg_post">
  <h3 class="jeg_post_title"><a href="https://www.dreamjob.ma/emploi/data-analyst/">Data Analyst</a></h3>
  <div class="jeg_post_meta">
    <span class="jeg_meta_date"><a>12/05/2024</a></span>
  </div>
</article>
<article class="jeg_post">
  <h3 class="jeg_post_title"><a href="https://www.dreamjob.ma/emploi/developpeur-python/">Développeur Python</a></h3>
  <div class="jeg_post_meta">
    <span class="jeg_meta_date"><a>11/05/2024</a></span>
  </div>
</article>
<nav class="jeg_pagination">
  <a rel="next" href="https://www.dreamjob.ma/emploi/page/2/">Next</a>
</nav>
</body></html>"""


@pytest.fixture
def sample_detail_html() -> str:
    return """<!DOCTYPE html>
<html><body>
<article>
  <h1 class="jeg_post_title">Data Analyst</h1>
  <div class="jeg_post_meta">
    <span class="jeg_meta_author"><a rel="author">Tech Corp</a></span>
    <span class="jeg_meta_date"><a>12/05/2024</a></span>
  </div>
  <meta property="article:published_time" content="2024-05-12T10:00:00+00:00">
  <div class="content-inner">
    <p>Nous recherchons un Data Analyst compétent en Python, SQL et Tableau.</p>
    <p>Salaire: 15000 DH</p>
  </div>
</article>
</body></html>"""


@pytest.fixture
def sample_job_posting():
    from src.models.job import JobPosting
    from pydantic import HttpUrl

    return JobPosting(
        title="Data Analyst",
        company="Tech Corp",
        location="Casablanca",
        category="emploi",
        url=HttpUrl("https://www.dreamjob.ma/emploi/data-analyst/"),
        description="Python SQL Tableau data analysis",
    )

# DreamJob Scraper

Automated job scraper for [dreamjob.ma](https://www.dreamjob.ma) — scrapes job listings, matches them against your skill profile, and sends email digests of relevant opportunities.

## Architecture

```
Scraper (httpx + BeautifulSoup)
    ↓
Parser (lxml selectors for dreamjob.ma)
    ↓
Matching Engine (thefuzz keyword scoring)
    ↓
PostgreSQL (SQLAlchemy async + Alembic)
    ↓
Email Notifier (Jinja2 HTML + aiosmtplib)
```

| Component | Technology | Role |
|-----------|-----------|------|
| **Client** | `httpx.AsyncClient` | Fetches pages with retry, rate limiting, rotating UAs |
| **Parser** | `beautifulsoup4` + `lxml` | Extracts jobs from listing & detail pages |
| **Crawler** | asyncio | Orchestrates category/pagination crawling |
| **Matching** | `thefuzz` | Title fuzzy match (60%) + category (20%) + description (20%) − excluded terms (−30%) |
| **Storage** | `sqlalchemy[asyncio]` + asyncpg | Dedup via URL unique constraint; tracks scrape runs |
| **Notifications** | `aiosmtplib` + `jinja2` | HTML email digest of scored matches |
| **Scheduling** | `apscheduler` | Daily cron at configurable time (default 08:00) |

## Data Flow

```
dreamjob.ma ──→ Crawler ──→ Parser ──→ Matcher ──→ DB ──→ Email
                   │                                      │
                   └── page/N/ pagination (max 5)          └── unscored duplicates skipped
```

### Database Schema

**`jobs` table** — stores every scraped listing:
- `url` (unique) — dedup key
- `content_hash` (SHA-256 of title+company+description) — detects updated posts
- `match_score` (0–100) — computed by the matching engine
- `notified` (boolean) — tracks which jobs have been emailed

**`scrape_runs` table** — tracks each execution:
- `started_at`, `finished_at`, `status` (running/completed/failed)
- `jobs_found`, `jobs_new` — metrics for each run

### Profile YAML

Your skills profile drives the matching engine:

```yaml
target_keywords:
  data_analyst:   [python, sql, tableau, power bi, ...]
  ai_ml:          [machine learning, tensorflow, pytorch, ...]
  web_dev:        [react, angular, javascript, ...]
  it:             [réseau, cybersécurité, devops, cloud, ...]
excluded_terms:   [senior 10+ ans, CDD, chauffeur]
threshold: 60
```

Built-in synonym map handles French/Arabic → English normalization (e.g., "intelligence artificielle" → "ai").

## Quick Start

### Prerequisites

- Python 3.11+
- [Poetry](https://python-poetry.org/)
- PostgreSQL 16 (or Docker)
- Redis 7 (or Docker)

### Installation

```bash
git clone <repo> && cd dreamjob-scraper
poetry install
```

### Configuration

```bash
cp .env.example .env        # edit with your SMTP/DB credentials
cp profile.yaml.example profile.yaml   # customize your skill keywords
```

### Run

```bash
# One-shot scrape → match → notify
poetry run dreamjob scrape

# Scheduled daemon (default, runs daily at 08:00)
poetry run dreamjob schedule

# Run database migrations
poetry run dreamjob migrate

# Health check server on :8080
poetry run dreamjob health
```

### Docker (production)

```bash
docker compose up -d
```

This starts 4 containers: `postgres`, `redis`, `scraper` (scheduler daemon), `health` (HTTP health endpoint).

## Managing Data

### Querying Jobs

Connect to PostgreSQL directly:

```sql
-- Recent high-scoring jobs
SELECT title, company, match_score, notified
FROM jobs
WHERE match_score >= 60
ORDER BY date_posted DESC;

-- Scrape run history
SELECT * FROM scrape_runs ORDER BY started_at DESC;

-- Jobs that matched but weren't notified yet
SELECT * FROM jobs
WHERE match_score >= 60 AND notified = false;
```

### Reset Notifications

```sql
UPDATE jobs SET notified = false WHERE match_score >= 60;
```

### Rerun Matching

Delete scores to force re-scoring on next scrape:

```sql
UPDATE jobs SET match_score = 0;
```

### View Job Details via CLI

```bash
poetry run python -c "
import asyncio
from src.storage.database import async_session_factory
from src.storage.repository import JobRepository
from sqlalchemy import select
from src.storage.database import JobRecord

async def show():
    async with async_session_factory() as s:
        repo = JobRepository(s)
        jobs = await repo.get_unnotified_jobs(60)
        for j in jobs:
            print(f'{j.match_score:3.0f}% | {j.title} | {j.company}')
asyncio.run(show())
"
```

## Makefile Targets

| Target | Description |
|--------|-------------|
| `make build` | `docker compose build` |
| `make run` | `docker compose up -d` |
| `make stop` | `docker compose down` |
| `make test` | `pytest tests/ -v` |
| `make lint` | `ruff check src/` |
| `make typecheck` | `mypy src/` |
| `make migrate` | `alembic upgrade head` |
| `make clean` | Remove `__pycache__`, build artifacts |

## Project Map

```
├── src/
│   ├── config.py              # Pydantic env settings
│   ├── main.py                # CLI entry point
│   ├── scraper/               # client, selectors, parser, crawler
│   ├── models/                # JobPosting, UserProfile
│   ├── matching/              # rules, engine (scoring)
│   ├── storage/               # database, repository, migrations/
│   ├── notifications/         # base, email, templates/email/
│   └── scheduler/             # tasks (APScheduler cron)
├── tests/                     # conftest + scraper/matching/storage tests
├── scripts/healthcheck.py     # Lightweight HTTP health endpoint
├── Dockerfile / docker-compose.yml
├── .env.example / profile.yaml.example
└── Makefile
```

## Decisions

| Concern | Choice |
|---------|--------|
| Profile format | YAML — keyword groups per field |
| Notifications | Email only (abstract `Notifier` — Discord/Slack extendable) |
| Scrape depth | 5 pages/category (~50 posts) |
| Dedup | URL unique constraint + content hash |
| Parsing | BeautifulSoup4 — static HTML, no JS |
| Health check | Separate container, decoupled from lifecycle |

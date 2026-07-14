# DreamJob Scraper

Automated job scraper for [dreamjob.ma](https://www.dreamjob.ma) — scrapes job listings, extracts text from image-heavy pages via OCR, embeds them with a multilingual semantic model, and lets you search via a Web UI dashboard. Matching jobs are also sent as email digests.

## Architecture

```
Scraper (httpx + BeautifulSoup)
    ↓
Parser + OCR (Ollama minicpm-v — Arabic/French/English)
    ↓
Embedding Engine (Ollama nomic-embed-text)
    ↓
PostgreSQL + pgvector (SQLAlchemy async + Alembic)
    ↓
Web UI (FastAPI + Jinja2 + Bootstrap)  ──→  Email Notifier (aiosmtplib)
```

| Component         | Technology                      | Role                                                                                 |
| ----------------- | ------------------------------- | ------------------------------------------------------------------------------------ |
| **Client**        | `httpx.AsyncClient`             | Fetches pages with retry, rate limiting, rotating UAs                                |
| **Parser**        | `beautifulsoup4` + `lxml`       | Extracts jobs from listing & detail pages                                            |
| **OCR**           | Ollama (`minicpm-v`)            | Extracts Arabic/French/English text from image-heavy pages via vision model          |
| **Crawler**       | asyncio                         | Orchestrates category/pagination crawling                                            |
| **Embedding**     | Ollama (`nomic-embed-text`)    | Multilingual semantic embeddings (768-dim) via external Ollama service              |
| **Storage**       | `sqlalchemy[asyncio]` + asyncpg | Dedup via URL unique constraint; pgvector for embedding storage                      |
| **Web UI**        | `fastapi` + `jinja2`           | Read-only dashboard with saved queries, ranked results, job details                  |
| **Notifications** | `aiosmtplib` + `jinja2`         | HTML email digest of jobs matching saved queries (above configurable threshold)      |
| **Scheduling**    | `apscheduler`                   | Daily cron at configurable time (default 08:00)                                      |

## Data Flow

```
dreamjob.ma ──→ Crawler ──→ Parser ──→ OCR ──→ Embedder ──→ DB ──→ Web UI
                    │           │          │         │              │
                    └─ page/N   text    images →   job → vector    └── Email
                       (max 5)          text       (768-dim)          (matches above threshold)
```

### Database Schema

**`jobs` table** — stores every scraped listing:

- `url` (unique) — dedup key
- `content_hash` (SHA-256 of title+company+description) — detects updated posts
- `embedding` (VECTOR(768)) — semantic embedding for similarity search
- `match_score` (float) — computed by the matching engine (legacy)

**`scrape_runs` table** — tracks each execution:

- `started_at`, `finished_at`, `status` (running/completed/failed)
- `jobs_found`, `jobs_new` — metrics for each run

**`queries` table** — saved search queries:

- `name` — human-readable label
- `query_text` — free-text search query (e.g. "concours fonction publique casablanca 2026")

### Saved Queries

Instead of a keyword profile, you define free-text queries that are matched semantically against job embeddings:

```yaml
# queries.yaml
- name: "Web Development"
  query: "développeur react node.js full stack casablanca"
- name: "Data & AI"
  query: "data scientist machine learning python analyse de données"
- name: "Public Sector"
  query: "concours fonction publique recrutement ministère"
```

The multilingual embedding model (nomic-embed-text) handles French, Arabic, and English — no manual synonym mapping needed.

## Quick Start

### Prerequisites

- Python 3.11+
- [Poetry](https://python-poetry.org/)
- [Ollama](https://ollama.com/) running locally with the following models pulled:
  ```bash
  ollama pull nomic-embed-text
  ollama pull minicpm-v
  ```
- PostgreSQL 16 with pgvector extension (or Docker)

### Installation

```bash
git clone <repo> && cd dreamjob-scraper
poetry install
```

### Configuration

```bash
cp .env.example .env        # edit with your DB and email credentials
```

Key environment variables:

| Variable | Description | Default |
| -------- | ----------- | ------- |
| `DATABASE_URL` | PostgreSQL connection string | `postgresql+asyncpg://dreamjob:dreamjob@localhost:5432/dreamjob` |
| `OLLAMA_HOST` | Ollama API base URL | `http://localhost:11434` |
| `EMAIL_SMTP_HOST` | SMTP server for email notifications | `smtp.gmail.com` |
| `EMAIL_USERNAME` / `EMAIL_PASSWORD` | SMTP credentials | — |
| `EMAIL_FROM` / `EMAIL_TO` | Sender and recipient addresses | — |
| `NOTIFICATION_THRESHOLD` | Minimum similarity score (0-1) to trigger email | `0.6` |
| `SCRAPER_RUN_TIME` | Daily schedule time | `08:00` |
| `WEB_PORT` | Web UI port | `8080` |

### Saved Queries

Create a `queries.yaml` file to define what jobs you care about:

```yaml
- name: "Web Development"
  query: "développeur react node.js full stack casablanca"
- name: "Data & AI"
  query: "data scientist machine learning python analyse de données"
- name: "Public Sector"
  query: "concours fonction publique recrutement ministère"
```

The multilingual embedding model (nomic-embed-text) handles French, Arabic, and English — no manual synonym mapping needed.

### Run

```bash
# One-shot scrape → embed → store → notify
poetry run dreamjob scrape

# Scheduled daemon (default, runs daily at 08:00)
poetry run dreamjob schedule

# Run database migrations
poetry run dreamjob migrate

# Web UI dashboard on :8080
poetry run dreamjob web

# Health check endpoint on :8080
poetry run dreamjob health
```

> **Note (Windows users):** If `poetry run dreamjob ...` returns `'dreamjob' is not recognized as an internal or external command`, the Poetry entry-point shim wasn't generated in the venv. You can run the same commands by invoking the module directly:
>
> ```bash
> poetry run python -m src.main scrape      # one-shot scrape → embed → store → notify
> poetry run python -m src.main schedule    # scheduler daemon (default at 08:00)
> poetry run python -m src.main migrate     # alembic upgrade head
> poetry run python -m src.main web         # web UI on :8080
> poetry run python -m src.main health      # health check on :8080
> poetry run python -m src.main             # defaults to `schedule`
> ```
>
> To permanently restore the `dreamjob` command, recreate the virtualenv: `poetry env remove python && poetry install`.

### Docker (production)

```bash
# Build and start all services
docker compose up -d
```

This starts 3 containers: `postgres` (with pgvector), `scraper` (scheduler daemon), `web` (Web UI on :8080).

> **Important:** Both `scraper` and `web` services require an external [Ollama](https://ollama.com/) instance running with the `nomic-embed-text` and `minicpm-v` models. Set the `OLLAMA_HOST` environment variable to point to your Ollama service (default: `http://localhost:11434`). In Docker, use `http://host.docker.internal:11434` to reach Ollama on the host machine.
>
> **Install required Ollama models before running:**
> ```bash
> ollama pull nomic-embed-text    # embedding model (768-dim)
> ollama pull minicpm-v           # vision model for OCR
> ```

#### Manual scrape from Docker

You can trigger a one-shot scrape at any time without waiting for the scheduled run:

```bash
# If the scraper container is running (scheduler mode):
docker compose exec scraper python -m src.main scrape

# If the scraper container is not running (e.g., Ollama wasn't available at start):
docker compose run --rm scraper python -m src.main scrape

# Run database migrations:
docker compose run --rm web python -m src.main migrate
```

> **Tip:** `docker compose run --rm` starts a fresh container for a single command, even if the service isn't running. This is useful for one-off scrapes or migrations.

#### View logs

```bash
# Follow scraper logs
docker compose logs -f scraper

# Follow web logs
docker compose logs -f web
```

## Managing Data

### Querying Jobs

Connect to PostgreSQL directly:

```sql
-- Recent jobs
SELECT title, company, date_posted FROM jobs ORDER BY date_posted DESC;

-- Scrape run history
SELECT * FROM scrape_runs ORDER BY started_at DESC;

-- Jobs with embeddings (ready for semantic search)
SELECT COUNT(*) FROM jobs WHERE embedding IS NOT NULL;
```

### View Jobs via Web UI

Open `http://localhost:8080` in your browser. The dashboard shows saved queries and job stats. Click a query to see ranked results.

## Makefile Targets

| Target           | Description                           |
| ---------------- | ------------------------------------- |
| `make build`     | `docker compose build`                |
| `make run`       | `docker compose up -d`                |
| `make stop`      | `docker compose down`                 |
| `make test`      | `pytest tests/ -v`                    |
| `make lint`      | `ruff check src/`                     |
| `make typecheck` | `mypy src/`                           |
| `make migrate`   | `alembic upgrade head`                |
| `make clean`     | Remove `__pycache__`, build artifacts |

## Project Map

```
├── src/
│   ├── config.py              # Pydantic env settings
│   ├── main.py                # CLI entry point
│   ├── scraper/               # client, selectors, parser, crawler, ocr
│   ├── embedding/             # engine (Ollama nomic-embed-text)
│   ├── web/                   # FastAPI app + Jinja2 templates
│   ├── models/                # JobPosting
│   ├── storage/               # database, repository, migrations/
│   └── scheduler/             # tasks (APScheduler cron)
├── tests/                     # conftest + scraper/ocr/embedding/web/storage tests
├── scripts/healthcheck.py     # Lightweight HTTP health endpoint
├── Dockerfile / docker-compose.yml
├── .env.example
└── Makefile
```

## Decisions

| Concern        | Choice                                                      |
| -------------- | ----------------------------------------------------------- |
| Scoring        | Semantic search via Ollama (`nomic-embed-text`) — free-text queries, no keyword lists |
| OCR            | Ollama vision model (`minicpm-v`) — triggered on image-dominant pages, Arabic/French/English |
| Storage        | `pgvector` for embedding vectors — enables fast cosine similarity |
| Web UI         | FastAPI + Jinja2 + Bootstrap — read-only dashboard, no auth |
| Notifications  | Email via `aiosmtplib` — HTML digest of jobs matching saved queries, sent after each scrape |
| Scrape depth   | 5 pages/category (~50 posts)                                |
| Dedup          | URL unique constraint + content hash                        |
| Parsing        | BeautifulSoup4 — static HTML, no JS                         |

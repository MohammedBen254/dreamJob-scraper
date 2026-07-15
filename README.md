# DreamJob Scraper

Automated job scraper for [dreamjob.ma](https://www.dreamjob.ma) — scrapes listings, extracts text from images via OCR, embeds them semantically, and delivers matching jobs to your inbox and a web dashboard.

## How It Works

Jobs flow through a pipeline: **Scrape → Parse → OCR (if needed) → Embed → Store → Match → Notify**. Each job gets a 768-dim vector embedding via Ollama's `nomic-embed-text` model, stored in PostgreSQL with pgvector for fast similarity search. You define free-text queries (not keywords), and the system matches them semantically — handling French, Arabic, and English out of the box.

## Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) package manager
- [Ollama](https://ollama.com/) with two models installed:
  ```bash
  ollama pull nomic-embed-text   # embedding model
  ollama pull minicpm-v          # vision model for OCR
  ```
- PostgreSQL 16 with the pgvector extension (or just use Docker — see below)

## Setup

```bash
git clone <repo> && cd dreamjob-scraper
uv sync
cp .env.example .env            # edit with your DB and email settings
```

Then create a `queries.yaml` in the project root with the jobs you're looking for:

```yaml
- name: "Web Development"
  query: "développeur react node.js full stack casablanca"
- name: "Data & AI"
  query: "data scientist machine learning python analyse de données"
- name: "Public Sector"
  query: "concours fonction publique recrutement ministère"
```

## Running

```bash
uv run python -m src.main migrate     # create database tables
uv run python -m src.main seed        # load queries.yaml into the database
uv run python -m src.main scrape      # one-shot: scrape → embed → store → notify
uv run python -m src.main schedule    # daemon: runs daily at SCRAPER_RUN_TIME (default 08:00)
uv run python -m src.main web         # web dashboard on :8080
uv run python -m src.main             # defaults to schedule
```

> **Note:** You must run `migrate` then `seed` before scraping. The `schedule` command auto-seeds queries on first run, but for one-shot scraping you need to seed manually.

Open `http://localhost:8080` to browse your saved queries and matched jobs.

## Docker

```bash
docker compose up -d
```

This starts PostgreSQL (pgvector), the scraper daemon, and the web UI. Ollama must be running on the host — Docker connects to it at `http://host.docker.internal:11434` by default.

First-time setup after starting containers:

```bash
docker compose run --rm web migrate     # create database tables
docker compose run --rm web seed        # load queries into the database
```

Then trigger a scrape or let the scheduler handle it:

```bash
docker compose run --rm scraper scrape   # one-shot scrape (container starts fresh)
docker compose exec scraper scrape       # one-shot scrape (on running scheduler)
```

> **Tip:** Since the Docker image sets `ENTRYPOINT ["python", "-m", "src.main"]`, just pass the subcommand directly — don't prefix with `python -m src.main`.

Follow logs with `docker compose logs -f scraper` or `docker compose logs -f web`.

To start fresh ( wipes all data):

```bash
docker compose down -v
docker compose up -d
docker compose run --rm web migrate
docker compose run --rm web seed
```

## Configuration

All settings go in `.env`. The defaults work for local development:

| Variable | What it does | Default |
| -------- | ------------ | ------- |
| `DB_PORT` | PostgreSQL port | `5432` |
| `DATABASE_URL` | PostgreSQL connection string | `postgresql+asyncpg://dreamjob:dreamjob@postgres:5432/dreamjob` |
| `OLLAMA_HOST` | Where Ollama is running | `http://localhost:11434` |
| `SCRAPER_RUN_TIME` | Daily scrape time | `08:00` |
| `SCRAPER_PAGE_LIMIT` | Pages per category | `5` |
| `NOTIFICATION_THRESHOLD` | Min similarity (0–1) to email a job | `0.6` |
| `WEB_PORT` | Dashboard port | `8080` |
| `EMAIL_*` | SMTP credentials for notifications | — |
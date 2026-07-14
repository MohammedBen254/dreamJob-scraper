FROM python:3.11-slim AS builder

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

FROM python:3.11-slim

WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"

RUN addgroup --system --gid 1001 app && \
    adduser --system --uid 1001 --gid 1001 app

COPY alembic.ini ./
COPY src/ src/
COPY queries.yaml ./
COPY scripts/ scripts/
USER app

ENTRYPOINT ["python", "-m", "src.main"]
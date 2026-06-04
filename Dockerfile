FROM python:3.11-slim AS builder

WORKDIR /app
RUN pip install poetry

COPY pyproject.toml poetry.lock ./
RUN poetry config virtualenvs.in-project true && \
    poetry install --no-root --only main

FROM python:3.11-slim AS runtime

WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"

RUN addgroup --system --gid 1001 app && \
    adduser --system --uid 1001 --gid 1001 app

COPY alembic.ini ./
COPY src/ src/
COPY scripts/ scripts/
COPY profile.yaml ./

USER app

ENTRYPOINT ["python", "-m", "src.main"]

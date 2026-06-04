build:
	docker compose build

run:
	docker compose up -d

stop:
	docker compose down

test:
	pytest tests/ -v

lint:
	ruff check src/

typecheck:
	mypy src/

migrate:
	alembic upgrade head

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	rm -rf build dist .coverage htmlcov

.PHONY: build run stop test lint typecheck migrate clean

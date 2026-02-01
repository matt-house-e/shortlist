.PHONY: dev up down test check docs db-migrate

dev:
	PYTHONPATH=. uv run chainlit run app/chat/handlers.py --host 0.0.0.0 --port 8000 -w

up:
	docker compose up -d

rebuild:
	docker compose up --build -d

down:
	docker compose down

test:
	PYTHONPATH=. uv run pytest tests/ -v

check:
	uv run ruff check app/ tests/
	uv run ruff format app/ tests/ --check

docs:
	uv run mkdocs serve -a localhost:8080

db-migrate:
	PYTHONPATH=. uv run alembic upgrade head

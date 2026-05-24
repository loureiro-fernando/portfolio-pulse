.PHONY: up down logs seed dev test lint init-db smoke-slack

up:
	docker compose up -d
	@echo "Postgres: localhost:5432"
	@echo "Jaeger:   http://localhost:16686"

down:
	docker compose down

logs:
	docker compose logs -f

dev:
	uvicorn app.main:app --reload --port 8000

init-db:
	python -m app.scripts.init_db

smoke-slack:
	python tests/smoke_slack.py

seed:
	python -m app.scripts.seed

test:
	pytest -v

lint:
	ruff check . && ruff format --check .

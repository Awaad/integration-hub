.PHONY: install up down migrate api worker

install:
	poetry install

up:
	docker compose up -d

down:
	docker compose down -v

migrate:
	poetry run alembic upgrade head

api:
	poetry run uvicorn app.main:app --reload --port 8000

worker:
	poetry run celery -A worker.celery_app.celery worker -Q outbox,default --loglevel=INFO

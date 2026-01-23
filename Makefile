.PHONY: install up down migrate api worker

install:
	poetry install

up:
	docker compose up -d

down:
	docker compose down

reset:
	docker compose down -v
	
migrate:
	poetry run alembic upgrade head

api:
	poetry run uvicorn app.main:app --reload --port 8000

worker:
	poetry run celery -A worker.celery_app.celery worker -Q outbox,default --loglevel=INFO


HUB_BASE_URL ?= http://localhost:8000

catalog-preview-101evler:
	python -m ops.import_catalog --destination 101evler --file ops/catalogs/101evler/enums_currency.json --mode preview
	python -m ops.import_catalog --destination 101evler --file ops/catalogs/101evler/enums_property_type.json --mode preview
	python -m ops.import_catalog --destination 101evler --file ops/catalogs/101evler/enums_rooms.json --mode preview
	python -m ops.import_catalog --destination 101evler --file ops/catalogs/101evler/enums_title_type.json --mode preview
	python -m ops.import_catalog --destination 101evler --file ops/catalogs/101evler/areas_ncy.json --mode preview

catalog-apply-101evler:
	python -m ops.import_catalog --destination 101evler --file ops/catalogs/101evler/enums_currency.json --mode apply
	python -m ops.import_catalog --destination 101evler --file ops/catalogs/101evler/enums_property_type.json --mode apply
	python -m ops.import_catalog --destination 101evler --file ops/catalogs/101evler/enums_rooms.json --mode apply
	python -m ops.import_catalog --destination 101evler --file ops/catalogs/101evler/enums_title_type.json --mode apply
	python -m ops.import_catalog --destination 101evler --file ops/catalogs/101evler/areas_ncy.json --mode apply

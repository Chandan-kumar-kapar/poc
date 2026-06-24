.PHONY: help up down logs ps test keys seed migrate fmt clean

help:
	@echo "Targets:"
	@echo "  make up        - build & start API + Postgres + Redis (migrate + seed)"
	@echo "  make down      - stop and remove containers"
	@echo "  make logs      - tail API logs"
	@echo "  make ps        - show container status"
	@echo "  make test      - run the pytest suite locally (needs deps installed)"
	@echo "  make keys      - generate a local RS256 keypair into ./secrets"
	@echo "  make migrate   - run alembic migrations locally"
	@echo "  make seed      - run the seed script locally"
	@echo "  make clean     - remove volumes and local secrets"

up:
	docker compose up --build -d
	@echo "API:      http://localhost:8000"
	@echo "Swagger:  http://localhost:8000/docs"
	@echo "ReDoc:    http://localhost:8000/redoc"

down:
	docker compose down

logs:
	docker compose logs -f api

ps:
	docker compose ps

test:
	pytest -q

keys:
	python scripts/generate_keys.py --kid poc-key-a --out secrets

migrate:
	alembic upgrade head

seed:
	python -m app.db.seed

clean:
	docker compose down -v
	rm -rf secrets

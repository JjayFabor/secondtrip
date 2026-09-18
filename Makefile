.PHONY: dev dev-frontend dev-backend db-up db-down build lint typecheck test \
        migrate contracts seed-demo detect help

help:
	@echo "make dev            - postgres (docker), backend API, frontend dev server"
	@echo "make db-up          - start local Postgres (docker compose)"
	@echo "make db-down        - stop local Postgres"
	@echo "make migrate m=\"msg\" - create + apply an Alembic migration"
	@echo "make build          - production build (frontend)"
	@echo "make lint           - ruff + mypy --strict + import-linter (backend), eslint + tsc (frontend)"
	@echo "make typecheck      - mypy --strict (backend) + tsc --noEmit (frontend)"
	@echo "make test           - pytest (backend) + frontend tests (none yet)"

dev: db-up
	@echo "Postgres is up. Run 'make dev-backend' and 'make dev-frontend' in separate terminals."

dev-frontend:
	cd frontend && pnpm dev

dev-backend: db-up
	cd backend && uv run uvicorn app.main:app --reload

db-up:
	docker compose up -d
	@echo "Waiting for Postgres..."
	@until docker compose exec -T postgres pg_isready -U secondtrip_owner -d secondtrip_dev >/dev/null 2>&1; do sleep 1; done
	@echo "Postgres is ready on localhost:5439"

db-down:
	docker compose down

migrate:
	cd backend && uv run alembic revision --autogenerate -m "$(m)"
	cd backend && uv run alembic upgrade head

build:
	cd frontend && pnpm build

lint:
	cd backend && uv run ruff check .
	cd backend && uv run mypy .
	cd backend && uv run lint-imports
	cd frontend && pnpm lint

typecheck:
	cd backend && uv run mypy .
	cd frontend && pnpm typecheck

test:
	cd backend && uv run pytest
	@echo "No frontend tests yet — see docs/architecture/19-testing-strategy.md"

# Placeholders — real targets arrive as their modules are built.
contracts seed-demo detect:
	@echo "$@: not built yet — see PLAN.md"

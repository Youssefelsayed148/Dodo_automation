# Dodo Book Studio – common commands
PY ?= python3.12
VENV := backend/.venv
BIN := $(VENV)/bin

.PHONY: setup backend frontend dev test test-backend test-frontend lint fonts compare migrate

setup: ## install backend + frontend dependencies
	$(PY) -m venv $(VENV)
	$(BIN)/pip install -U pip
	$(BIN)/pip install -e "backend[dev]"
	cd frontend && npm install
	@test -f .env || cp .env.example .env

fonts: ## download bundled fonts (Fredoka, Nunito, Noto Naskh Arabic, Cairo)
	$(BIN)/python scripts/fetch_fonts.py

migrate:
	cd backend && ../$(BIN)/alembic upgrade head

backend:
	cd backend && ../$(BIN)/python -m app.main

frontend:
	cd frontend && npm run dev

dev: ## run backend and frontend together
	./scripts/dev.sh

test: test-backend test-frontend

test-backend:
	cd backend && ../$(BIN)/pytest

test-frontend:
	cd frontend && npm test && npm run typecheck

lint:
	cd backend && ../$(BIN)/ruff check .

compare: ## run the image model comparison harness (CLI)
	cd backend && ../$(BIN)/python -m app.services.compare $(ARGS)

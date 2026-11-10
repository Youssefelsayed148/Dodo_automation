# Dodo Book Studio. Everything runs in Docker; `make up` is the only command you need.
.PHONY: up down logs test compare reset

up: ## build the images and start the app at http://127.0.0.1:8080
	docker compose up --build -d --wait
	@echo "Dodo Book Studio: http://127.0.0.1:8080"

down: ## stop the app (data is kept)
	docker compose down

logs: ## follow the logs
	docker compose logs -f

test: ## backend pytest (mock providers, offline) + frontend tests/typecheck, all in containers
	docker compose run --rm --no-deps -e MANUAL_MODE=0 backend sh -c "ruff check . && pytest"
	docker build -f frontend/Dockerfile --target test -t dodo-frontend-test .

compare: ## image model comparison harness, e.g. make compare ARGS="--providers mock,openai"
	docker compose run --rm --no-deps backend python -m app.services.compare $(ARGS)

reset: ## stop the app AND delete all data (books, database, tokens)
	docker compose down -v

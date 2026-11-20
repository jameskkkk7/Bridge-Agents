# Bridge-Agents developer entry points.
# `make demo` runs the whole demo (mock model + API + built web UI) in one process group.

PYTHON ?= uv run python
NPM ?= npm

.PHONY: help install demo serve init-db web dev-api dev-web build-web web-release version-check test lint fmt check package release docker doctor

help:  ## Show the available targets
	@echo "Bridge-Agents targets:"
	@echo "  make install    Install Python dependencies (uv sync)"
	@echo "  make demo       One-command demo: mock model + API + built UI on :8000"
	@echo "  make serve      Serve the API + built UI on :8000"
	@echo "  make dev-api    API with auto-reload on :8000"
	@echo "  make dev-web    Vite dev server on :5173 (proxies the API)"
	@echo "  make build-web  Build the production web UI into web/dist"
	@echo "  make web-release Build the versioned web UI release artifact"
	@echo "  make test       Run the offline test suite"
	@echo "  make lint       Ruff check + format check"
	@echo "  make fmt        Format and auto-fix"
	@echo "  make check      lint + tests + web build"
	@echo "  make package    Build the server and core-library wheels (uv build)"
	@echo "  make version-check Check release version consistency"
	@echo "  make release    Version check + wheels + web UI release artifact"
	@echo "  make docker     docker compose up --build"
	@echo "  make doctor     Check local demo prerequisites"

install:  ## Install Python dependencies
	uv sync

demo:  ## One-command demo (mock model + API + UI)
	uv run bridge-agents demo

serve:  ## Serve API + built UI
	uv run bridge-agents serve

init-db:  ## Create the database schema
	uv run bridge-agents init-db

dev-api:  ## API with auto-reload
	uv run bridge-agents serve --reload

dev-web:  ## Vite dev server (proxies /api and /ws)
	$(NPM) --prefix web run dev

build-web:  ## Build the production web UI
	$(NPM) --prefix web install
	$(NPM) --prefix web run build

test:  ## Run tests
	uv run pytest -q

lint:  ## Lint and format check
	uv run ruff check .
	uv run ruff format --check .

fmt:  ## Auto-fix and format
	uv run ruff check . --fix
	uv run ruff format .

check: lint test build-web  ## Full local quality gate

package:  ## Build wheels
	uv build

web-release: build-web  ## Package the built UI for releases
	uv run python scripts/package_web.py

version-check:  ## Check release version consistency
	uv run python scripts/check_version.py

release: version-check package web-release  ## Build all release artifacts

docker:  ## Full stack in Docker
	docker compose up --build

doctor:  ## Check local demo prerequisites
	uv run bridge-agents doctor

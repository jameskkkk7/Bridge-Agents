# Contributing

Thanks for taking a look. This repository is a small, self-contained demo; the
fastest way to contribute is to run it, break it, and open an issue with the
exact steps.

## Development setup

Prerequisites: Python 3.11, [uv](https://github.com/astral-sh/uv), Node.js 20+
for the web UI, and Docker for the demo stack.

```bash
git clone <repository-url> bridge-agents
cd bridge-agents
uv sync
cp .env.example .env          # set ALLOW_DEV_LOGIN=true for the demo login
uv run python scripts/init_db.py
uv run uvicorn app.main:app --reload
```

The API is on `http://127.0.0.1:8000`. The browser demo lives in `web/`:

```bash
cd web
npm install
npm run dev                   # proxies /api and /ws to the local API
```

Or run everything, including a deterministic mock model and nginx, with:

```bash
docker compose up --build
```

## Before opening a pull request

```bash
uv run pytest -q
uv run pytest --cov=app/core --cov-report=term-missing --cov-fail-under=70
uv run ruff check .
uv run ruff format --check .
uv run python scripts/check_sanitized.py
docker compose config -q
cd web && npm run build
```

All of these run in CI (`.github/workflows/ci.yml`), together with a gitleaks
secret scan.

## Guidelines

- Keep commits focused; a feature and its tests belong together.
- Do not add credentials, customer data, private endpoints or absolute local
  paths. The sanitisation gate scans the tracked tree and commit messages.
- New runtime behaviour needs an offline test. Tests use a fake model and a
  fake compiled graph; the suite must not require network access.
- Do not edit `scripts/sanitize_allowlist.txt` as part of an unrelated change;
  exemptions are reviewed separately.
- Keep the demo web app within its documented budget (12 source files / 900
  lines) and keep the review gate's fail-closed behaviour intact.

## Reporting security issues

Please follow [SECURITY.md](SECURITY.md) instead of opening a public issue.

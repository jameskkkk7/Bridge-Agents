# Bridge-Agents API image
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /srv/bridge-agents

RUN groupadd --gid 1000 app \
    && useradd --uid 1000 --gid 1000 --create-home app \
    && mkdir -p /data \
    && chown -R app:app /data

COPY pyproject.toml README.md LICENSE ./
COPY packages ./packages
COPY app ./app
# bundled knowledge documents seed the knowledge base on first start
COPY docs/kb ./docs/kb
RUN pip install ./packages/bridge_agents .

RUN chown -R app:app /srv/bridge-agents
USER app

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

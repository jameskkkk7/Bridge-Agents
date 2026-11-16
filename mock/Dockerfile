# Bridge-Agents mock model image
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /srv/mock

RUN groupadd --gid 1000 app \
    && useradd --uid 1000 --gid 1000 --create-home app
RUN pip install "fastapi>=0.115" "uvicorn>=0.30"

COPY main.py ./
RUN chown -R app:app /srv/mock
USER app

EXPOSE 8001
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8001/health', timeout=3)"

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"]

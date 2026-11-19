# Deploying Bridge-Agents

The Python package and the web UI ship separately:

| Artifact | Contents |
|---|---|
| `bridge-agents` wheel | core Python runtime (no server dependencies) |
| `bridge-agents-server` wheel | FastAPI server, database models, CLI |
| `bridge-agents-web-<version>.tar.gz` | built static GUI (`web/dist`), deployed by nginx/CDN |

The package never contains the GUI. The standard topology is **nginx serving the
static GUI and reverse-proxying `/api` + `/ws` to the Python server on
`127.0.0.1:8000`** — same origin, so no CORS configuration is needed.

---

## 1. Single host: pipx + systemd + nginx

```bash
# 1. install the server (pulls the pinned core package)
python -m venv /opt/bridge-agents/.venv
/opt/bridge-agents/.venv/bin/pip install "bridge-agents-server[database-driver]"
# Postgres: "bridge-agents-server[postgres]"; MySQL: "bridge-agents-server[mysql]"

# 2. write non-secret config + secrets
cd /opt/bridge-agents
/opt/bridge-agents/.venv/bin/bridge-agents init --config /etc/bridge-agents/bridge-agents.toml \
    --env-file /etc/bridge-agents/bridge-agents.env
# edit both files: database URL, external identity provider, model keys, allowed hosts

# 3. create the schema and validate
bridge-agents init-db --config /etc/bridge-agents/bridge-agents.toml
bridge-agents config check --config /etc/bridge-agents/bridge-agents.toml

# 4. systemd + nginx
cp deploy/bridge-agents.service /etc/systemd/system/
cp deploy/nginx.conf /etc/nginx/conf.d/bridge-agents.conf
systemctl daemon-reload && systemctl enable --now bridge-agents
nginx -t && systemctl reload nginx

# 5. web UI (from the release assets)
mkdir -p /var/www/bridge-agents
tar -xzf bridge-agents-web-<version>.tar.gz -C /var/www/bridge-agents
# nginx root points at /var/www/bridge-agents/web
```

Production checklist:

- `app_env = "production"`, `allow_dev_login = false`, explicit `allowed_hosts`
- `JWT_SECRET` (HS256) or `AUTH_VERIFIER=jwks` / `rs256_pem` with an IdP
- TLS terminated at nginx; `/ws` has `proxy_read_timeout 3600s`
- database URL on Postgres for anything beyond a single-user demo
- `bridge-agents config check --config ...` exits non-zero on errors

---

## 2. Containers

`docker compose up --build` (repository root) runs the API, a web container and
a deterministic mock model for the offline demo. For production, replace the
mock model and mount the web release into the web container, or point nginx at
your own static hosting.

---

## 3. Embedded in an existing Python service

```bash
pip install bridge-agents            # core runtime only
pip install "bridge-agents[server]"  # add the FastAPI app + CLI
```

```python
from bridge_agents.agent.factory import create_pipeline
from bridge_agents.runtime import AgentRuntime

async with AgentRuntime(llm=my_chat_model) as runtime:
    answer = await runtime.reply("How do I activate Widget Pro?")

# or mount the ASGI app into an existing FastAPI service
from app.main import create_app

app.mount("/bridge-agents", create_app())
```

---

## Configuration precedence

`CLI arguments > environment variables > .env > bridge-agents.toml > defaults`.

Secrets (`JWT_SECRET`, provider keys) belong in `.env`/the environment;
non-secret settings can live in a version-controlled TOML file. Point at the
file with `--config` or `BRIDGE_CONFIG`.

## Front-end / API compatibility

`GET /api/v1/meta` returns the server version, `api_version` and
`min_web_version`. Release the GUI and server from the same tag; the GUI may
warn (or refuse to boot) when `min_web_version` is newer than its own build.

## Health checks

- `GET /health` — liveness (no database access)
- `GET /api/v1/meta` — version/information for the static front-end

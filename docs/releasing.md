# Releasing Bridge-Agents

A release publishes four things from one Git tag:

| Artifact | Built by | Published to |
|---|---|---|
| `bridge_agents-<version>-py3-none-any.whl` (+ sdist) | `uv build --package bridge-agents` | GitHub Release, optionally PyPI |
| `bridge_agents_server-<version>-py3-none-any.whl` (+ sdist) | `uv build --package bridge-agents-server` | GitHub Release, optionally PyPI |
| `bridge-agents-web-<version>.tar.gz` | `npm run build` + `scripts/package_web.py` | GitHub Release |
| server + web container images | `Dockerfile`, `web/Dockerfile` | GHCR (`server`, `web` tags) |

The Python packages never contain the GUI. See [deploy/README.md](../deploy/README.md)
for the deployment topology.

## One-time repository setup

1. **GitHub environment** `pypi` — Settings → Environments. Add required
   reviewers so publishing requires an explicit approval.
2. **PyPI trusted publishers** — create both projects (`bridge-agents` and
   `bridge-agents-server`) and add a trusted publisher for each:

   | Field | Value |
   |---|---|
   | Owner | repository owner |
   | Repository | this repository |
   | Workflow | `publish-pypi.yml` |
   | Environment | `pypi` |

   No API token is stored in the repository.
3. **GHCR visibility** — the release workflow pushes images with the default
   `GITHUB_TOKEN`. Public repositories produce public packages by default;
   private repositories need package visibility configured in GitHub settings.
4. **Actions permissions** — allow GitHub Actions to create releases (default
   `contents: write` is granted per workflow) and to write packages.

## Version bump checklist

The version must agree in every shipped place; the check script enforces it:

- `pyproject.toml` — `bridge-agents-server`
- `packages/bridge_agents/pyproject.toml` — `bridge-agents`
- `packages/bridge_agents/src/bridge_agents/__init__.py` — `__version__`
- `web/package.json` — display/version metadata
- `CHANGELOG.md` — `## [x.y.z]` entry

```bash
make version-check          # uv run python scripts/check_version.py
```

CI runs the same check on every pull request, so a version mismatch fails before
a release is tagged. Semantic versioning: `0.x` may break on minor versions; `/api/v1` stays stable
within a major API version. Bump the API version (not just the package version)
for breaking HTTP/WebSocket changes.

## Local rehearsal

```bash
make check                  # lint + tests + web build
make release                # version check + wheels + web archive
scripts/check_version.py     # ensure metadata is consistent
```

Without GNU `make` (for example on Windows), run the underlying commands:

```bash
uv run python scripts/check_version.py
uv run ruff check . && uv run ruff format --check . && uv run pytest -q
npm --prefix web run build
uv build --package bridge-agents
uv build --package bridge-agents-server
uv run python scripts/package_web.py
```

Verify the artifacts before tagging:

```bash
python -m venv /tmp/bridge-release && /tmp/bridge-release/bin/pip install dist/*.whl
/tmp/bridge-release/bin/bridge-agents version
tar -tzf dist/bridge-agents-web-0.1.0.tar.gz | head
```

The web archive contains `bridge-agents-web-<version>/web/` and
`bridge-agents-web-<version>/nginx.conf`.

## Tag and publish

```bash
git switch main && git pull
git tag -a v0.1.0 -m "Bridge-Agents 0.1.0"
git push origin v0.1.0
```

The tag starts `.github/workflows/release.yml`:

1. **quality** — version/tag check, lint, tests, sanitisation, compose config.
2. **artifacts** — builds the web GUI, both wheels, and the web archive.
3. **images** — builds and pushes `ghcr.io/<owner>/<repo>/server:<tag>` and
   `.../web:<tag>` plus `:latest`.
4. **github-release** — creates the release with generated notes and attaches
   every artifact.

Wait for all four jobs to pass, then verify the release page and `ghcr.io` tags.

## Publish to PyPI

PyPI publication is a separate, manual workflow so it can be approved and
rehearsed independently:

1. Run **Actions → Publish to PyPI → Run workflow** on the tagged commit.
2. Set `confirm` to true and approve the `pypi` environment.
3. The workflow requires an exact version tag and publishes both distributions
   with trusted publishing (no stored token).

If the workflow runs on an untagged commit it fails intentionally. Publish only
after the GitHub Release artifacts have been verified.

## Verify a published release

```bash
pip install --dry-run "bridge-agents-server[postgres]==0.1.0"
docker pull ghcr.io/<owner>/<repo>/server:0.1.0
docker pull ghcr.io/<owner>/<repo>/web:0.1.0
curl -fsSL https://pypi.org/pypi/bridge-agents-server/0.1.0/json | head
```

Check `GET /api/v1/meta` on a running server: `version` must match the release
tag and `min_web_version` must be satisfied by the shipped web archive.

## Rollback and yanking

- **Broken container/release assets** — delete or edit the GitHub Release and
  re-run the workflow on a fixed tag. GHCR tags can be overwritten by a new run.
- **Broken PyPI release** — use PyPI's *Yank* action; do not delete files that
  users may already depend on. Ship the fix as the next patch version.
- **Web/GUI regression** — redeploy the previous web archive; the server and GUI
  are independently versioned and `/api/v1/meta` reports mismatches.

## Release notes

GitHub generates release notes from merged pull requests. Add a short upgrade
section to the release body when a release needs manual steps (new environment
variables, database changes, breaking API changes). Keep `CHANGELOG.md` as the
canonical human-readable history.

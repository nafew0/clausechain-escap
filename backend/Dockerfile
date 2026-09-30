# ClauseChain backend image — serves both the `backend` (gunicorn API) and
# `engine-worker` (run_engine_worker) compose services from one image, the
# same way DEPLOY.md/bootstrap.sh lay both trees under one /srv/clausechain
# checkout with separate venvs. Build context is the repo root (needs
# engine/ and deploy/ alongside backend/), e.g.:
#   docker build -f backend/Dockerfile -t clausechain-backend .
#
# Reproducible by construction: the backend installs requirements.txt under
# constraints.txt (the exact tested versions) and the engine venv is built with
# `uv sync --frozen` from engine/uv.lock, so every build on every OS/CPU resolves
# to the same packages as the tested environment.
FROM python:3.12-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

# gcc/libpq-dev cover any package that must compile; curl is the healthcheck.
RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc libpq-dev curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# uv, pinned, from its official image.
COPY --from=ghcr.io/astral-sh/uv:0.11.14 /uv /usr/local/bin/uv

# Mirrors the production layout (App Dev Plan D0): backend, engine and
# deploy/ all live under /srv/clausechain so ENGINE_ROOT / ENGINE_ALLOWLIST
# defaults in clausechain/settings.py resolve without extra env vars.
WORKDIR /srv/clausechain

COPY backend/requirements.txt backend/constraints.txt backend/
RUN pip install --no-cache-dir -r backend/requirements.txt -c backend/constraints.txt gunicorn==23.0.0

# Engine venv from the lockfile (engine/.venv, the path ENGINE_PYTHON and the
# decision writer expect). Groups: crawl (Playwright for sites that need a real
# browser), graph (optional Neo4j mirror), dev (pytest, for the acceptance check).
# Not installed: embed (PyTorch/sentence-transformers — Model B embeds through its
# OpenAI-compatible endpoint) and pdf-advanced (docling, opt-in only).
COPY engine/pyproject.toml engine/uv.lock engine/
RUN cd engine \
    && UV_PROJECT_ENVIRONMENT=/srv/clausechain/engine/.venv \
       uv sync --frozen --no-install-project --python /usr/local/bin/python3.12 \
               --group crawl --group graph --group dev \
    && .venv/bin/playwright install --with-deps chromium \
    && rm -rf /var/lib/apt/lists/*

COPY engine/packages engine/packages
COPY engine/scripts engine/scripts
COPY engine/configs engine/configs
COPY engine/tests engine/tests
COPY engine/run.py engine/run.py
COPY deploy/engine_allowlist.json deploy/engine_allowlist.json
COPY backend backend

RUN install -d -m 0750 backend/var/locks backend/staticfiles backend/media

WORKDIR /srv/clausechain/backend
EXPOSE 8001

# Waits for Postgres to accept connections, then execs the real CMD (either
# gunicorn, or the engine-worker service's `manage.py run_engine_worker`
# override) — "--" becomes $0 so "$@" below is exactly that CMD.
ENTRYPOINT ["/bin/sh", "-c", "\
    echo \"Waiting for database ${DB_HOST:-localhost}:${DB_PORT:-5432}...\"; \
    tries=0; \
    until python -c \"import socket,os; s=socket.socket(); s.settimeout(2); s.connect((os.environ.get('DB_HOST','localhost'), int(os.environ.get('DB_PORT','5432'))))\" 2>/dev/null; do \
        tries=$((tries + 1)); \
        if [ \"$tries\" -ge 60 ]; then echo 'Database never became reachable - giving up.' >&2; exit 1; fi; \
        sleep 1; \
    done; \
    exec \"$@\"", "--"]

# Overridden by the engine-worker service to run:
#   python manage.py run_engine_worker
CMD ["gunicorn", "clausechain.wsgi:application", "--bind", "0.0.0.0:8001", \
     "--workers", "2", "--threads", "4", "--timeout", "300"]

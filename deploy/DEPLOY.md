# ClauseChain — Fresh-Server Deployment Runbook (no Docker)

Target: Ubuntu 22.04/24.04 · domain `clausechain.zai.bd` · layout `/srv/clausechain/{engine,backend,frontend}` · systemd + nginx. Executed per App Dev Plan D0.

## 0. Before touching the server
- Point `clausechain.zai.bd` DNS at the new IP (propagation runs while you work).
- Have ready: OpenAI key, OCR VM endpoint+key, strong `DJANGO_SECRET_KEY` + `JWT_SIGNING_KEY` (`openssl rand -hex 48` each).

## 1. Bootstrap
```bash
git clone <repo> /tmp/cc && bash /tmp/cc/deploy/bootstrap.sh
```
(installs nginx/python3.12/node24/certbot, ufw, clones to /srv/clausechain, creates both venvs)

## 2. Engine data (run ON the dev Mac)
```bash
cd "~/Documents/Web Projects/ClauseChain"
rsync -az engine/data engine/outputs engine/logs engine/submission engine/reports \
    <user>@<server>:/srv/clausechain/engine/
```

## 3. Env files (all chmod 600, never committed)
`/srv/clausechain/engine/.env`
```
OPENAI_API_KEY=...
OCR_PROVIDER=remote_paddle
OCR_ENDPOINT=http://<ocr-host>:<ocr-port>/ocr
OCR_API_KEY=...
GRAPH_BACKEND=sqlite
# keep the provider spend cap set (same value as local)
```
`/srv/clausechain/backend/.env`
```
DJANGO_SECRET_KEY=...        JWT_SIGNING_KEY=...
DEBUG=False                  ENVIRONMENT=production
DB_ENGINE=django.db.backends.sqlite3
USE_REDIS=0
APP_ORIGIN=https://clausechain.zai.bd
PUBLIC_APP_URL=https://clausechain.zai.bd
TRUST_X_FORWARDED_PROTO=1
ENGINE_ROOT=/srv/clausechain/engine
WORKSPACE_LOCK_DIR=/srv/clausechain/backend/var/locks
```
`/srv/clausechain/frontend/.env`
```
BACKEND_URL=http://127.0.0.1:8001
NEXT_PUBLIC_API_URL=/api
```

## 4. App setup
```bash
cd /srv/clausechain/backend
venv/bin/python manage.py migrate
venv/bin/python manage.py createsuperuser
venv/bin/python manage.py collectstatic --noinput

cd /srv/clausechain/frontend && npm ci && npm run build
# Code stays read-only; only writable paths get www-data ownership:
sudo chown -R www-data:www-data /srv/clausechain/backend/{db.sqlite3,media,staticfiles} 2>/dev/null || true
sudo install -d -o www-data -g www-data -m 0750 /srv/clausechain/backend/var/locks
sudo chown -R www-data:www-data /srv/clausechain/engine/{data,outputs,logs,submission,reports}
```

## 5. Services + nginx + TLS
```bash
sudo cp /srv/clausechain/deploy/clausechain-*.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now clausechain-api clausechain-web
sudo cp /srv/clausechain/deploy/nginx.conf /etc/nginx/sites-available/clausechain
sudo ln -sf /etc/nginx/sites-available/clausechain /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl reload nginx
sudo certbot --nginx -d clausechain.zai.bd
```

## 6. Acceptance (App Dev Plan D0)
```bash
cd /srv/clausechain/engine && .venv/bin/python -m pytest tests -q      # 112 passed
.venv/bin/python scripts/champion_validate.py                          # runs; FAIL list = pending approvals only
curl -s https://clausechain.zai.bd/api/auth/user/ -o /dev/null -w "%{http_code}\n"   # 401 (auth wall up)
```
Then: login over https works; one admin-terminal `run.py --economy Singapore --pillar 6` completes.

## Engine data transfer (3.1 GB — manifest, not blind copy)
Before rsync: `df -h /srv` must show ≥8 GB free. After rsync, verify with the hash
manifest: `cd engine && find data outputs submission reports -type f | wc -l` matches
the source count, and spot-check 5 SHA-256s against the source.

## Notes
- Engine actions run as the API's user — `www-data` must own `/srv/clausechain/engine/data` (the decisions file is written there).
- No Postgres/Redis/Celery/Channels in this deployment (D0 decision). Rollback = `git checkout <tag>` + `systemctl restart`, data dirs untouched.
- After the sprint: rotate any credentials that were shared during setup.

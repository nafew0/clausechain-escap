#!/usr/bin/env bash
# ClauseChain fresh-server bootstrap (Ubuntu 22.04/24.04) — App Dev Plan D0.
# Run as a sudo-capable user. Idempotent where possible. NO DOCKER.
set -euo pipefail

APP_DIR=/srv/clausechain
REPO_URL="${REPO_URL:-https://github.com/nafew0/ClauseChain.git}"

echo "== base packages =="
sudo apt-get update -y
sudo apt-get install -y nginx rsync git ufw curl \
    python3.12 python3.12-venv python3.12-dev build-essential \
    certbot python3-certbot-nginx

echo "== node 24 (Next 16 requirement) =="
if ! command -v node >/dev/null || [[ "$(node -v)" != v24* ]]; then
    curl -fsSL https://deb.nodesource.com/setup_24.x | sudo -E bash -
    sudo apt-get install -y nodejs
fi
node -v

echo "== firewall =="
sudo ufw allow OpenSSH && sudo ufw allow 'Nginx Full' && sudo ufw --force enable

echo "== clone =="
sudo mkdir -p "$APP_DIR" && sudo chown "$USER" "$APP_DIR"
[[ -d "$APP_DIR/.git" ]] || git clone "$REPO_URL" "$APP_DIR"

echo "== engine venv =="
cd "$APP_DIR/engine"
python3.12 -m venv .venv
.venv/bin/pip install -U pip
.venv/bin/pip install -e ".[dev]" || .venv/bin/pip install -e .
# (must FAIL loudly on install errors; if the project uses uv groups: uv sync --all-groups)

echo "== backend venv =="
cd "$APP_DIR/backend"
python3.12 -m venv venv
venv/bin/pip install -U pip
venv/bin/pip install -r requirements.txt gunicorn
sudo install -d -o www-data -g www-data -m 0750 "$APP_DIR/backend/var/locks"

echo "== frontend build (run after frontend/.env exists) =="
echo "   cd $APP_DIR/frontend && npm ci && npm run build"

cat <<'NEXT'
== REMAINING MANUAL STEPS (deploy/DEPLOY.md has full detail) ==
1. rsync engine data from the dev machine (run ON the dev machine):
   rsync -az engine/data engine/outputs engine/logs engine/submission engine/reports \
       <user>@<server>:/srv/clausechain/engine/
2. Write .env files (engine/.env, backend/.env, frontend/.env) — templates in DEPLOY.md. chmod 600.
3. Backend: venv/bin/python manage.py migrate && createsuperuser && collectstatic --noinput
4. Frontend: npm ci && npm run build
5. sudo cp deploy/clausechain-*.service /etc/systemd/system/ && sudo systemctl daemon-reload \
   && sudo systemctl enable --now clausechain-api clausechain-web
6. sudo cp deploy/nginx.conf /etc/nginx/sites-available/clausechain \
   && sudo ln -sf /etc/nginx/sites-available/clausechain /etc/nginx/sites-enabled/ \
   && sudo nginx -t && sudo systemctl reload nginx
7. sudo certbot --nginx -d clausechain.zai.bd   (after DNS points here)
8. Acceptance: engine/.venv/bin/python -m pytest engine/tests -q  -> 112 passed
NEXT

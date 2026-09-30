#!/usr/bin/env bash
# ClauseChain — one-command local deployment (macOS, Linux, Windows WSL2 / Git Bash).
# Windows PowerShell users: run .\deploy.ps1 instead (same steps).
#
# Needs only Docker (Docker Desktop, or Docker Engine + the compose plugin).
# Every other dependency — Python, Node, Postgres, all libraries — is pinned
# inside the images, so the result is the same on every machine.
#
#   ./deploy.sh                          download the data bundle, build, start
#   ./deploy.sh --data full              full data, 3.3 GB (asked interactively if omitted)
#   ./deploy.sh --data partial           partial data, 1.3 GB (no embedding caches or run logs)
#   ./deploy.sh --env-file keys.env      also install the provided engine keys
#   ./deploy.sh --data-file bundle.tgz   use a bundle you already downloaded
#   ./deploy.sh --port 9090              serve on another port (default 8080)
#   ./deploy.sh --help
#
# Safe to run again: finished steps are skipped (data, secrets, admin account).

set -euo pipefail

cd "$(dirname "$0")"
ROOT="$(pwd)"

# ---------------------------------------------------------------- options
PORT=""
ENV_FILE=""
DATA_FILE=""
DATA_URL=""
DATA_SHA256=""
DATA_CHOICE=""
SKIP_DATA=0
NO_BUILD=0

usage() { sed -n '2,17p' "$0" | sed 's/^# \{0,1\}//'; exit 0; }
while [ $# -gt 0 ]; do
  case "$1" in
    --port) PORT="$2"; shift 2 ;;
    --data) DATA_CHOICE="$2"; shift 2 ;;
    --env-file) ENV_FILE="$2"; shift 2 ;;
    --data-file) DATA_FILE="$2"; shift 2 ;;
    --data-url) DATA_URL="$2"; shift 2 ;;
    --data-sha256) DATA_SHA256="$2"; shift 2 ;;
    --skip-data) SKIP_DATA=1; shift ;;
    --no-build) NO_BUILD=1; shift ;;
    -h|--help) usage ;;
    *) echo "Unknown option: $1 (see --help)" >&2; exit 2 ;;
  esac
done

# Published bundle location (deploy/data_bundle.cfg); options override it.
if [ -f deploy/data_bundle.cfg ]; then
  # shellcheck disable=SC1091
  . deploy/data_bundle.cfg
fi

# ---------------------------------------------------------------- output
if [ -t 1 ]; then B=$'\033[1m'; G=$'\033[32m'; Y=$'\033[33m'; R=$'\033[31m'; N=$'\033[0m'; else B=; G=; Y=; R=; N=; fi
step() { printf '\n%s==> %s%s\n' "$B" "$1" "$N"; }
ok()   { printf '  %s✔%s %s\n' "$G" "$N" "$1"; }
warn() { printf '  %s!%s %s\n' "$Y" "$N" "$1"; }
die()  { printf '\n%s✘ %s%s\n' "$R" "$1" "$N" >&2; exit 1; }

# ---------------------------------------------------------------- 1. prerequisites
step "1/7  Checking prerequisites"
# A terminal opened before Docker Desktop was installed does not have it on PATH yet;
# look in Docker's standard install locations before giving up.
if ! command -v docker >/dev/null 2>&1; then
  for dir in "$HOME/.docker/bin" /usr/local/bin /opt/homebrew/bin \
             /Applications/Docker.app/Contents/Resources/bin \
             "/c/Program Files/Docker/Docker/resources/bin" \
             "/mnt/c/Program Files/Docker/Docker/resources/bin"; do
    if [ -x "$dir/docker" ] || [ -x "$dir/docker.exe" ]; then
      PATH="$dir:$PATH"; export PATH
      warn "docker was not on this terminal's PATH; using $dir (opening a new terminal also fixes this)"
      break
    fi
  done
fi
command -v docker >/dev/null 2>&1 || die "Docker is not installed.
   macOS / Windows: install Docker Desktop  https://docs.docker.com/desktop/
   Linux: install Docker Engine + compose    https://docs.docker.com/engine/install/"
if docker compose version >/dev/null 2>&1; then
  COMPOSE="docker compose"
elif command -v docker-compose >/dev/null 2>&1; then
  COMPOSE="docker-compose"
else
  die "Docker Compose v2 is missing (the 'docker compose' command). Update Docker Desktop, or install the compose plugin."
fi
docker info >/dev/null 2>&1 || die "Docker is installed but not running. Start Docker Desktop (or 'sudo systemctl start docker') and run this again."
ok "Docker $(docker version --format '{{.Server.Version}}' 2>/dev/null) with $($COMPOSE version --short 2>/dev/null || echo compose)"

if command -v curl >/dev/null 2>&1; then FETCH="curl"; elif command -v wget >/dev/null 2>&1; then FETCH="wget"; else FETCH=""; fi
command -v tar >/dev/null 2>&1 || die "'tar' is required to unpack the data bundle."

sha256_of() {
  if command -v sha256sum >/dev/null 2>&1; then sha256sum "$1" | awk '{print $1}'
  elif command -v shasum >/dev/null 2>&1; then shasum -a 256 "$1" | awk '{print $1}'
  else openssl dgst -sha256 "$1" | awk '{print $NF}'; fi
}
random_secret() {
  if command -v openssl >/dev/null 2>&1; then openssl rand -hex 32
  else LC_ALL=C tr -dc 'a-f0-9' < /dev/urandom | head -c 64; fi
}

# Docker's own disk (images ~5 GB), the download (~4 GB) and the data (~15 GB unpacked).
free_kb=$(df -Pk "$ROOT" | awk 'NR==2 {print $4}')
if [ "${free_kb:-0}" -lt 30000000 ]; then
  warn "Less than 30 GB free on this disk ($((free_kb / 1048576)) GB). The data and images need about 25 GB."
else
  ok "Disk: $((free_kb / 1048576)) GB free"
fi

# ---------------------------------------------------------------- 2. settings
step "2/7  Settings"
if [ ! -f .env ]; then
  cp .env.example .env
  for name in DJANGO_SECRET_KEY JWT_SIGNING_KEY POSTGRES_PASSWORD; do
    value="$(random_secret)"
    sed -i.bak "s|^${name}=.*|${name}=${value}|" .env
  done
  rm -f .env.bak
  ok "Created .env with new random secrets"
else
  ok ".env already present (kept)"
fi
if [ -n "$PORT" ]; then
  sed -i.bak -e "s|^CLAUSECHAIN_PORT=.*|CLAUSECHAIN_PORT=${PORT}|" \
             -e "s|^APP_ORIGIN=.*|APP_ORIGIN=http://localhost:${PORT}|" \
             -e "s|^CSRF_TRUSTED_ORIGINS=.*|CSRF_TRUSTED_ORIGINS=http://localhost:${PORT},http://127.0.0.1:${PORT}|" .env
  rm -f .env.bak
fi
PORT="$(grep -E '^CLAUSECHAIN_PORT=' .env | cut -d= -f2)"
PORT="${PORT:-8080}"
URL="http://localhost:${PORT}"

if [ -n "$ENV_FILE" ]; then
  [ -f "$ENV_FILE" ] || die "--env-file not found: $ENV_FILE"
  cp "$ENV_FILE" engine/.env
  ok "Installed engine keys from $ENV_FILE into engine/.env"
elif [ ! -f engine/.env ]; then
  cp engine/.env.example engine/.env
  warn "No engine keys yet: browsing and review work; runs need keys in engine/.env (then: $COMPOSE restart engine-worker)"
else
  ok "engine/.env already present (kept)"
fi

# ---------------------------------------------------------------- 3. data
step "3/7  Data bundle (corpus database, run outputs, source downloads)"
if [ "$SKIP_DATA" = 1 ]; then
  warn "Skipped (--skip-data)"
elif [ -f engine/data/graph_v2.db ] && [ -d engine/outputs ] && [ -z "$DATA_FILE" ]; then
  ok "Already in place (engine/data/graph_v2.db)"
else
  if [ -z "$DATA_FILE" ] && [ -z "$DATA_URL" ]; then
    if [ -z "$DATA_CHOICE" ] && [ -t 0 ]; then
      echo "  Which data bundle?"
      echo "    1) full     3.3 GB  corpus, source downloads, run outputs, embedding caches, run logs"
      echo "                        (re-runs need no re-embedding)"
      echo "    2) partial  1.3 GB  corpus, source downloads, run outputs"
      printf "  Choose 1 or 2 [1]: "
      read -r answer
      case "$answer" in 2|p|partial) DATA_CHOICE=partial ;; *) DATA_CHOICE=full ;; esac
    fi
    DATA_CHOICE="${DATA_CHOICE:-full}"
    case "$DATA_CHOICE" in
      full) DATA_URL="${CLAUSECHAIN_DATA_FULL_URL:-}"; DATA_SHA256="${DATA_SHA256:-${CLAUSECHAIN_DATA_FULL_SHA256:-}}" ;;
      partial) DATA_URL="${CLAUSECHAIN_DATA_PARTIAL_URL:-}"; DATA_SHA256="${DATA_SHA256:-${CLAUSECHAIN_DATA_PARTIAL_SHA256:-}}" ;;
      *) die "--data must be 'full' or 'partial'" ;;
    esac
    echo "  Data bundle: $DATA_CHOICE"
  fi
  if [ -z "$DATA_FILE" ]; then
    [ -n "$DATA_URL" ] || die "No data bundle location. Pass --data-url <link> or --data-file <bundle.tar.gz>."
    [ -n "$FETCH" ] || die "'curl' or 'wget' is required to download the data bundle."
    mkdir -p .deploy-cache
    DATA_FILE=".deploy-cache/clausechain-data-${DATA_CHOICE:-custom}.tar.gz"
    echo "  Downloading $DATA_URL"
    if [ "$FETCH" = curl ]; then
      curl -fL --retry 5 --retry-delay 5 -C - -o "$DATA_FILE" "$DATA_URL" || die "Download failed. Check the link, then run ./deploy.sh again (it resumes)."
    else
      wget -c -t 5 -O "$DATA_FILE" "$DATA_URL" || die "Download failed. Check the link, then run ./deploy.sh again (it resumes)."
    fi
  fi
  [ -f "$DATA_FILE" ] || die "Data bundle not found: $DATA_FILE"
  if [ -n "$DATA_SHA256" ]; then
    echo "  Verifying SHA-256 …"
    actual="$(sha256_of "$DATA_FILE")"
    [ "$actual" = "$DATA_SHA256" ] || die "Checksum mismatch (got $actual). Delete $DATA_FILE and run again."
    ok "Checksum verified"
  else
    warn "No checksum given; skipping verification"
  fi
  echo "  Unpacking about 15 GB (several minutes) …"
  tar -xzf "$DATA_FILE" -C "$ROOT" || die "Could not unpack $DATA_FILE"
  [ -f engine/data/graph_v2.db ] || die "The bundle did not contain engine/data/graph_v2.db"
  ok "Data in place ($(du -sh engine/data/graph_v2.db | awk '{print $1}') corpus database)"
fi
mkdir -p engine/outputs engine/logs engine/data/cache

# ---------------------------------------------------------------- 4. build + start
step "4/7  Building and starting the containers (first time: 10–20 minutes)"
if [ "$NO_BUILD" = 1 ]; then
  $COMPOSE up -d
else
  $COMPOSE up -d --build
fi
ok "Containers started"

# ---------------------------------------------------------------- 5. wait
step "5/7  Waiting for the app to answer on $URL"
http_code() {
  if [ "$FETCH" = curl ]; then curl -s -o /dev/null -w '%{http_code}' "$1" 2>/dev/null || echo 000
  else wget -q -S -O /dev/null "$1" 2>&1 | awk '/HTTP\//{c=$2} END{print c+0}'; fi
}
for i in $(seq 1 120); do
  api="$(http_code "$URL/api/auth/user/")"; web="$(http_code "$URL/")"
  if [ "$api" = 401 ] && [ "$web" = 200 ]; then break; fi
  if [ "$i" = 120 ]; then
    $COMPOSE ps
    die "The app did not come up within 10 minutes. See: $COMPOSE logs backend frontend"
  fi
  sleep 5
done
ok "API and web app are up"

# ---------------------------------------------------------------- 6. snapshots
step "6/7  Importing the reviewed evidence (Hybrid, then Local)"
for mode in hybrid local; do
  if $COMPOSE exec -T backend python manage.py engine_refresh --mode "$mode" > ".deploy-import-$mode.log" 2>&1; then
    ok "$mode snapshot imported"
  else
    warn "$mode snapshot import failed — details in .deploy-import-$mode.log (the app still runs; re-run ./deploy.sh to retry)"
  fi
done
# The signed decisions (engine/data/review/*.json) become the review state the queues show.
if $COMPOSE exec -T backend python manage.py import_decisions > .deploy-import-decisions.log 2>&1; then
  ok "signed review decisions loaded"
else
  warn "loading the signed decisions failed — details in .deploy-import-decisions.log (re-run ./deploy.sh to retry)"
fi

# ---------------------------------------------------------------- 7. admin
step "7/7  Admin account"
CRED=".deploy-credentials.txt"
if [ -f "$CRED" ]; then
  ok "Admin account already created (see $CRED)"
else
  ADMIN_PASSWORD="$(random_secret | cut -c1-20)"
  $COMPOSE exec -T -e CC_ADMIN_PASSWORD="$ADMIN_PASSWORD" backend python manage.py shell -c "
import os
from accounts.models import User
user, _ = User.objects.get_or_create(username='admin', defaults={'email': 'admin@clausechain.local'})
user.email = user.email or 'admin@clausechain.local'
user.first_name, user.last_name = 'Evaluator', 'Admin'
user.is_superuser = user.is_staff = True
user.email_verified = True
user.set_password(os.environ['CC_ADMIN_PASSWORD'])
user.save()
" >/dev/null
  printf 'ClauseChain admin login\nURL:      %s\nUsername: admin\nPassword: %s\n' "$URL" "$ADMIN_PASSWORD" > "$CRED"
  chmod 600 "$CRED" 2>/dev/null || true
  ok "Admin account created"
fi

# ---------------------------------------------------------------- done
cat <<EOF

${G}${B}ClauseChain is running:  $URL${N}

  Sign in:   $(sed -n 3,4p "$CRED" | tr '\n' ' ')  (saved in $CRED)
  Try it:    Runs → Sources → Build sources, then Queue run; switch Hybrid / Local at the top of any page.
  Stop:      $COMPOSE stop          Start again: $COMPOSE start
  Logs:      $COMPOSE logs -f backend engine-worker
  Remove:    $COMPOSE down           (keeps the data; add -v to also drop the database)
EOF

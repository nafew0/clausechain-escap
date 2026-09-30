#!/usr/bin/env bash
# ClauseChain — one-command local deployment (macOS, Linux, Windows WSL2 / Git Bash).
# Windows PowerShell users: run .\deploy.ps1 instead (same steps).
#
# Needs only Docker (Docker Desktop, or Docker Engine + the compose plugin).
# Every other dependency — Python, Node, Postgres, all libraries — is pinned
# inside the images, so the result is the same on every machine.
#
#   ./deploy.sh                          asks each setting (Enter keeps the default shown)
#   ./deploy.sh --yes                    no questions: defaults plus any options given
#
#   --data full | partial                data bundle: full 3.3 GB (default) or partial 1.3 GB
#   --data-file FILE                     use a bundle you already downloaded
#   --data-url URL [--data-sha256 SUM]   download the bundle from another link
#   --skip-data                          start with an empty workspace
#   --env-file FILE                      engine API keys file (default: keys.env in this folder)
#   --port N                             serve on port N (default 8080)
#   --no-build                           start the existing images without rebuilding
#   --help
#
# Safe to run again: finished steps are skipped (data, secrets, admin account).

set -euo pipefail

ORIG_PWD="$(pwd)"
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
ASSUME_YES=0

usage() { sed -n '2,22p' "$0" | sed 's/^# \{0,1\}//'; exit 0; }
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
    -y|--yes) ASSUME_YES=1; shift ;;
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
INTERACTIVE=0
if [ "$ASSUME_YES" = 0 ] && [ -t 0 ] && [ -t 1 ]; then INTERACTIVE=1; fi

# ask VAR "question" "default": prints the question with its default; Enter keeps it.
ask() {
  local answer=""
  if [ "$INTERACTIVE" = 1 ]; then
    if [ -n "$3" ]; then printf '  %s [%s]: ' "$2" "$3"; else printf '  %s: ' "$2"; fi
    read -r answer || answer=""
  fi
  printf -v "$1" '%s' "${answer:-$3}"
}
# A path typed or dragged into the terminal: drop quotes and backslash-escaped spaces, expand ~.
clean_path() {
  local path="$1"
  path="${path#"${path%%[![:space:]]*}"}"; path="${path%"${path##*[![:space:]]}"}"
  path="${path#\"}"; path="${path%\"}"; path="${path#\'}"; path="${path%\'}"
  path="${path//\\ / }"
  case "$path" in "~"*) path="$HOME${path#\~}" ;; esac
  # Relative to this folder first, then to the folder the command was run from.
  if [ -n "$path" ] && [ ! -e "$path" ] && [ "${path#/}" = "$path" ] && [ -e "$ORIG_PWD/$path" ]; then
    path="$ORIG_PWD/$path"
  fi
  printf '%s' "$path"
}

CURRENT_PORT="$(grep -E '^CLAUSECHAIN_PORT=' .env 2>/dev/null | cut -d= -f2 || true)"
[ -n "$PORT" ] || ask PORT "Port for the web app" "${CURRENT_PORT:-8080}"
case "$PORT" in ''|*[!0-9]*) die "The port must be a number (got '$PORT')." ;; esac

# Engine API keys: keys.env in this folder is the default (recommended), or any path.
if [ -z "$ENV_FILE" ]; then
  if [ -f keys.env ]; then keys_default=keys.env
  elif [ -f engine/.env ]; then keys_default=keep
  else keys_default=keys.env; fi
  if [ "$INTERACTIVE" = 1 ]; then
    echo "  Engine API keys (keys.env):"
    echo "    Recommended: download keys.env and copy it into this folder, then press Enter:"
    echo "      $ROOT"
    echo "    Or type the path to your keys file ('none' = add keys later in engine/.env)."
  fi
  while :; do
    ask ENV_FILE "Keys file" "$keys_default"
    case "$ENV_FILE" in keep|none|skip|no) ENV_FILE=""; break ;; esac
    ENV_FILE="$(clean_path "$ENV_FILE")"
    [ -f "$ENV_FILE" ] && break
    if [ "$INTERACTIVE" = 1 ]; then
      warn "Not found: $ENV_FILE. Copy keys.env into $ROOT and press Enter, type its path, or type 'none'."
    else
      warn "No keys file ($ENV_FILE); continuing without keys (add them later in engine/.env)"
      ENV_FILE=""; break
    fi
  done
fi
ENV_FILE="$(clean_path "$ENV_FILE")"
[ -z "$ENV_FILE" ] || [ -f "$ENV_FILE" ] || die "Keys file not found: $ENV_FILE"

DATA_PRESENT=0
if [ -f engine/data/graph_v2.db ] && [ -d engine/outputs ]; then DATA_PRESENT=1; fi
if [ "$SKIP_DATA" = 0 ] && [ -z "$DATA_FILE$DATA_URL$DATA_CHOICE" ] && [ "$DATA_PRESENT" = 0 ]; then
  if [ "$INTERACTIVE" = 1 ]; then
    echo "  Data bundle:"
    echo "    1) full     3.3 GB  corpus, source downloads, run outputs, embedding caches, run logs"
    echo "                        (re-runs need no re-embedding)"
    echo "    2) partial  1.3 GB  corpus, source downloads, run outputs"
    echo "    3) a bundle file you already downloaded"
    echo "    4) download from another link"
    echo "    5) none: start with an empty workspace"
  fi
  ask data_answer "Choose 1-5" "1"
  case "$data_answer" in
    1|full) DATA_CHOICE=full ;;
    2|partial) DATA_CHOICE=partial ;;
    3) ask DATA_FILE "Path to the bundle (.tar.gz)" ""
       DATA_FILE="$(clean_path "$DATA_FILE")"
       [ -f "$DATA_FILE" ] || die "Bundle not found: $DATA_FILE" ;;
    4) ask DATA_URL "Link to the bundle" ""
       [ -n "$DATA_URL" ] || die "No link given."
       ask DATA_SHA256 "Its SHA-256 (Enter to skip the check)" "" ;;
    5|none) SKIP_DATA=1 ;;
    *) die "Choose a number from 1 to 5 (got '$data_answer')." ;;
  esac
fi
if [ -n "$DATA_FILE" ]; then DATA_FILE="$(clean_path "$DATA_FILE")"; fi
case "${DATA_CHOICE:-}" in ''|full|partial) ;; *) die "--data must be 'full' or 'partial'." ;; esac

if [ "$NO_BUILD" = 0 ] && [ "$INTERACTIVE" = 1 ]; then
  ask build_answer "Build the images (needed the first time and after an update)" "yes"
  case "$build_answer" in n|N|no|No|NO) NO_BUILD=1 ;; esac
fi

if [ "$SKIP_DATA" = 1 ]; then data_summary="none (empty workspace)"
elif [ "$DATA_PRESENT" = 1 ] && [ -z "$DATA_FILE$DATA_URL" ]; then data_summary="already in place"
elif [ -n "$DATA_FILE" ]; then data_summary="$DATA_FILE"
elif [ -n "$DATA_URL" ]; then data_summary="$DATA_URL"
elif [ "${DATA_CHOICE:-full}" = partial ]; then data_summary="partial (1.3 GB download)"
else data_summary="full (3.3 GB download)"; fi
if [ -n "$ENV_FILE" ]; then keys_summary="$ENV_FILE"
elif [ -f engine/.env ]; then keys_summary="engine/.env (kept)"
else keys_summary="none yet (runs need them; add later in engine/.env)"; fi
if [ "$NO_BUILD" = 1 ]; then build_summary=no; else build_summary=yes; fi
echo "  Summary"
echo "    Port:   $PORT"
echo "    Keys:   $keys_summary"
echo "    Data:   $data_summary"
echo "    Build:  $build_summary"
if [ "$INTERACTIVE" = 1 ]; then
  ask go_answer "Continue" "yes"
  case "$go_answer" in n|N|no|No|NO) echo "  Nothing changed."; exit 0 ;; esac
fi

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
sed -i.bak -e "s|^CLAUSECHAIN_PORT=.*|CLAUSECHAIN_PORT=${PORT}|" \
           -e "s|^APP_ORIGIN=.*|APP_ORIGIN=http://localhost:${PORT}|" \
           -e "s|^CSRF_TRUSTED_ORIGINS=.*|CSRF_TRUSTED_ORIGINS=http://localhost:${PORT},http://127.0.0.1:${PORT}|" .env
rm -f .env.bak
URL="http://localhost:${PORT}"

if [ -n "$ENV_FILE" ]; then
  cp "$ENV_FILE" engine/.env
  ok "Installed engine keys from $ENV_FILE into engine/.env"
elif [ ! -f engine/.env ]; then
  cp engine/.env.example engine/.env
  warn "No engine keys yet: browsing and review work; runs need keys in engine/.env (then: $COMPOSE restart engine-worker backend)"
else
  ok "engine/.env already present (kept)"
fi

# ---------------------------------------------------------------- 3. data
step "3/7  Data bundle (corpus database, run outputs, source downloads)"
if [ "$SKIP_DATA" = 1 ]; then
  warn "Skipped: empty workspace"
elif [ "$DATA_PRESENT" = 1 ] && [ -z "$DATA_FILE$DATA_URL" ]; then
  ok "Already in place (engine/data/graph_v2.db)"
else
  if [ -z "$DATA_FILE" ] && [ -z "$DATA_URL" ]; then
    DATA_CHOICE="${DATA_CHOICE:-full}"
    if [ "$DATA_CHOICE" = partial ]; then
      DATA_URL="${CLAUSECHAIN_DATA_PARTIAL_URL:-}"; DATA_SHA256="${DATA_SHA256:-${CLAUSECHAIN_DATA_PARTIAL_SHA256:-}}"
    else
      DATA_URL="${CLAUSECHAIN_DATA_FULL_URL:-}"; DATA_SHA256="${DATA_SHA256:-${CLAUSECHAIN_DATA_FULL_SHA256:-}}"
    fi
  fi
  if [ -z "$DATA_FILE" ]; then
    [ -n "$DATA_URL" ] || die "No data bundle location. Pass --data-url <link> or --data-file <bundle.tar.gz>."
    [ -n "$FETCH" ] || die "'curl' or 'wget' is required to download the data bundle."
    mkdir -p .deploy-cache
    DATA_FILE=".deploy-cache/clausechain-data-${DATA_CHOICE:-custom}.tar.gz"
    if [ -f "$DATA_FILE" ] && [ -n "$DATA_SHA256" ] && [ "$(sha256_of "$DATA_FILE")" = "$DATA_SHA256" ]; then
      ok "Already downloaded ($DATA_FILE)"
    else
      echo "  Downloading $DATA_URL"
      if [ "$FETCH" = curl ]; then
        curl -fL --progress-bar --retry 5 --retry-delay 5 -C - -o "$DATA_FILE" "$DATA_URL" || die "Download failed. Check the link, then run ./deploy.sh again (it resumes)."
      else
        wget -c -t 5 --progress=bar:force -O "$DATA_FILE" "$DATA_URL" || die "Download failed. Check the link, then run ./deploy.sh again (it resumes)."
      fi
    fi
  fi
  [ -f "$DATA_FILE" ] || die "Data bundle not found: $DATA_FILE"
  echo "  Verifying SHA-256 …"
  actual="$(sha256_of "$DATA_FILE")"
  if [ -n "$DATA_SHA256" ]; then
    [ "$actual" = "$DATA_SHA256" ] || die "Checksum mismatch (got $actual). Delete $DATA_FILE and run again."
    ok "Checksum verified"
  elif [ "$actual" = "${CLAUSECHAIN_DATA_FULL_SHA256:-}" ] || [ "$actual" = "${CLAUSECHAIN_DATA_PARTIAL_SHA256:-}" ]; then
    ok "Checksum verified (a published bundle)"
  else
    warn "Not one of the published bundles (SHA-256 $actual); unpacking it anyway"
  fi
  echo "  Unpacking about 15 GB (several minutes; the large corpus file shows as a pause) …"
  tar -xzvf "$DATA_FILE" -C "$ROOT" 2>&1 | awk '{ printf "\r  unpacked %d files", NR; fflush() } END { print "" }' \
    || die "Could not unpack $DATA_FILE"
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
ADMIN_USER="$(sed -n 's/^Username: *//p' "$CRED")"
ADMIN_PASSWORD="$(sed -n 's/^Password: *//p' "$CRED")"
cat <<EOF

${G}${B}ClauseChain is running:  $URL${N}

  ${Y}${B}==============================================================${N}
  ${B}  ADMIN LOGIN — save these now${N}
      URL:       $URL
      Username:  ${B}$ADMIN_USER${N}
      Password:  ${B}$ADMIN_PASSWORD${N}
      (also kept in $CRED in this folder)
  ${Y}${B}==============================================================${N}
EOF
if [ "$INTERACTIVE" = 1 ]; then
  printf '  Press Enter once you have saved the password … '
  read -r _ || true
fi
cat <<EOF

  Try it:    Runs → Sources → Build sources, then Queue run; switch Hybrid / Local at the top of any page.
  Stop:      $COMPOSE stop          Start again: $COMPOSE start
  Logs:      $COMPOSE logs -f backend engine-worker
  Remove:    $COMPOSE down           (keeps the data; add -v to also drop the database)
EOF

#!/usr/bin/env bash
# Build the data bundle that deploy.sh / deploy.ps1 download: everything the app
# and the engine use that is not in git.
#
#   engine/data/graph_v2.db   the built corpus (a consistent snapshot, safe while the app runs)
#   engine/data/raw/          every downloaded source document
#   engine/data/cache/        embedding caches for both models (re-runs need no re-embedding)
#   engine/outputs/           every Hybrid and Local run
#   engine/logs/*.log         the run and corpus-build logs
#
# The proof images, review decisions, Zone-3 scores and review bundles are in git.
#
#   deploy/make_data_bundle.sh [output.tar.gz]
#
# Upload the .tar.gz, then put its link and the printed SHA-256 into
# deploy/data_bundle.cfg.
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="$(pwd)"
OUT="${1:-dist/clausechain-data-$(date +%Y%m%d).tar.gz}"
STAGE="dist/.bundle-stage"
mkdir -p "$(dirname "$OUT")" "$STAGE/engine/data"

# The API keys never go into the bundle: stop if one shows up in the text parts.
if grep -rlE "sk-or-v1-|sk-proj-|AIza[0-9A-Za-z_-]{30}" engine/logs/*.log engine/outputs >/dev/null 2>&1; then
  echo "An API key appears in engine/logs or engine/outputs; remove it before bundling." >&2
  exit 1
fi

# A consistent copy of the corpus database, even if a run is writing to it.
echo "Snapshotting the corpus database …"
rm -f "$STAGE/engine/data/graph_v2.db"
engine/.venv/bin/python - "$STAGE/engine/data/graph_v2.db" <<'PY'
import sqlite3, sys
source = sqlite3.connect("engine/data/graph_v2.db")
target = sqlite3.connect(sys.argv[1])
source.backup(target)
target.close()
source.close()
PY
if LC_ALL=C grep -aqE "sk-or-v1-|sk-proj-|AIza[0-9A-Za-z_-]{30}" "$STAGE/engine/data/graph_v2.db"; then
  echo "An API key appears in the corpus database; remove it before bundling." >&2
  exit 1
fi

GZIP_CMD="gzip -6"
command -v pigz >/dev/null 2>&1 && GZIP_CMD="pigz -6"
echo "Packing (this takes several minutes) -> $OUT"
# COPYFILE_DISABLE stops macOS tar from adding ._ metadata files.
COPYFILE_DISABLE=1 tar -cf - \
  --exclude='.DS_Store' --exclude='engine/outputs/final_r2__p*' \
  -C "$STAGE" engine/data/graph_v2.db \
  -C "$ROOT" engine/data/raw engine/data/cache engine/outputs engine/logs/*.log \
  | $GZIP_CMD > "$OUT"
rm -f "$STAGE/engine/data/graph_v2.db"

if command -v sha256sum >/dev/null 2>&1; then SUM=$(sha256sum "$OUT" | awk '{print $1}'); else SUM=$(shasum -a 256 "$OUT" | awk '{print $1}'); fi
echo "$SUM  $(basename "$OUT")" > "$OUT.sha256"
echo
echo "Bundle:  $OUT ($(du -h "$OUT" | awk '{print $1}'))"
echo "SHA-256: $SUM"
echo "Next: upload it, then set CLAUSECHAIN_DATA_URL and CLAUSECHAIN_DATA_SHA256 in deploy/data_bundle.cfg"

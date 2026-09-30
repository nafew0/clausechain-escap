#!/usr/bin/env bash
# Build the data bundles that deploy.sh / deploy.ps1 download: everything the app
# and the engine use that is not in git.
#
#   full     clausechain-fulldata-YYYYMMDD.tar.gz   corpus database, source downloads, run outputs,
#                                                   embedding caches for both models, run and cost logs
#   partial  clausechain-data-YYYYMMDD.tar.gz       corpus database, source downloads, run outputs
#
# The corpus database is a consistent snapshot, safe while the app runs. The proof
# images, review decisions, Zone-3 scores and review bundles are in git.
#
#   deploy/make_data_bundle.sh            both bundles, into dist/
#   deploy/make_data_bundle.sh full       only the full bundle
#   deploy/make_data_bundle.sh partial    only the partial bundle
#
# Upload the .tar.gz files, then put their links and the printed SHA-256 values into
# deploy/data_bundle.cfg (CLAUSECHAIN_DATA_FULL_* and CLAUSECHAIN_DATA_PARTIAL_*).
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="$(pwd)"
WHICH="${1:-both}"
case "$WHICH" in full|partial|both) ;; *) echo "usage: $0 [full|partial|both]" >&2; exit 2 ;; esac
DIST="${BUNDLE_DIR:-dist}"
STAMP="$(date +%Y%m%d)"
STAGE="$DIST/.bundle-stage"
mkdir -p "$STAGE/engine/data"

# The API keys never go into a bundle: stop if one shows up in the text parts.
if grep -rlE "sk-or-v1-|sk-proj-|AIza[0-9A-Za-z_-]{30}" engine/logs engine/outputs >/dev/null 2>&1; then
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
sha256_of() {
  if command -v sha256sum >/dev/null 2>&1; then sha256sum "$1" | awk '{print $1}'; else shasum -a 256 "$1" | awk '{print $1}'; fi
}

# pack OUT PATH… : the snapshot database plus the given paths, gzip, and its checksum.
pack() {
  local out="$1"; shift
  echo "Packing $out (several minutes) …"
  # COPYFILE_DISABLE stops macOS tar from adding ._ metadata files.
  COPYFILE_DISABLE=1 tar -cf - \
    --exclude='.DS_Store' --exclude='engine/outputs/final_r2__p*' \
    -C "$STAGE" engine/data/graph_v2.db \
    -C "$ROOT" "$@" \
    | $GZIP_CMD > "$out"
  local sum
  sum="$(sha256_of "$out")"
  echo "$sum  $(basename "$out")" > "$out.sha256"
  RESULTS="${RESULTS}  $(du -h "$out" | awk '{print $1}')  $out
      SHA-256 $sum
"
}

RESULTS=""
if [ "$WHICH" != partial ]; then
  LOGS="$(ls engine/logs/*.log 2>/dev/null | tr '\n' ' ')"
  [ -f engine/logs/review_cost_report.json ] && LOGS="$LOGS engine/logs/review_cost_report.json"
  # shellcheck disable=SC2086
  pack "$DIST/clausechain-fulldata-$STAMP.tar.gz" engine/data/raw engine/data/cache engine/outputs $LOGS
fi
if [ "$WHICH" != full ]; then
  pack "$DIST/clausechain-data-$STAMP.tar.gz" engine/data/raw engine/outputs
fi
rm -f "$STAGE/engine/data/graph_v2.db"

echo
echo "Bundles:"
printf '%s' "$RESULTS"
echo "Next: upload them, then set the links and SHA-256 values in deploy/data_bundle.cfg"

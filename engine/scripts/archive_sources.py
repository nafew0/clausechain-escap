"""Clear an economy's downloads and caches before a live run — by archiving them.

On the live-test day the cache and download folders are cleared on screen before
the clock starts, so the first engine pass has to fetch every document again.
Nothing is deleted: the economy's downloaded sources (data/raw/<cc>/, including
the download manifest) and its embedding caches (data/cache/embeddings_<cc>*.json)
move to data/archive/<cc>-<UTC time>/. Moving them back restores the previous
state exactly; ARCHIVED.json in that folder lists what moved.

The search index (data/graph_v2.db) is kept. A re-downloaded document with the
same bytes has the same SHA-256, so the builder reuses its verified extraction;
a changed document is extracted again.

Usage: .venv/bin/python scripts/archive_sources.py --economy "Lao PDR"
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from packages.connectors.seeds_fetch import ECON_CC  # noqa: E402
from packages.core import progress  # noqa: E402


def archive(economy: str, root: Path = Path(".")) -> dict:
    cc = ECON_CC[economy]
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dest = root / "data" / "archive" / f"{cc}-{stamp}"
    moved = []
    raw = root / "data" / "raw" / cc
    if raw.is_dir() and any(raw.iterdir()):
        files = sum(1 for path in raw.rglob("*") if path.is_file())
        dest.mkdir(parents=True, exist_ok=True)
        shutil.move(str(raw), str(dest / "raw"))
        moved.append({"what": "downloads", "from": f"data/raw/{cc}", "to": str(dest.relative_to(root) / "raw"),
                      "files": files})
        progress.emit("clear", f"{economy}: archived {files} downloaded file(s) from data/raw/{cc}")
    caches = sorted({*(root / "data" / "cache").glob(f"embeddings_{cc}.json"),
                     *(root / "data" / "cache").glob(f"embeddings_{cc}__*.json")})
    for cache in caches:
        (dest / "cache").mkdir(parents=True, exist_ok=True)
        shutil.move(str(cache), str(dest / "cache" / cache.name))
        moved.append({"what": "embedding cache", "from": f"data/cache/{cache.name}",
                      "to": str(dest.relative_to(root) / "cache" / cache.name)})
        progress.emit("clear", f"{economy}: archived embedding cache {cache.name}")
    record = {"economy": economy, "code": cc, "archived_at": stamp, "moved": moved,
              "restore": "move each 'to' path back to its 'from' path"}
    if moved:
        (dest / "ARCHIVED.json").write_text(json.dumps(record, indent=1))
        progress.emit("clear", f"{economy}: downloads and caches cleared; nothing deleted "
                               f"(archive: {dest.relative_to(root)})")
    else:
        progress.emit("clear", f"{economy}: nothing to clear (no downloads or caches)")
    return record


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--economy", required=True, choices=sorted(ECON_CC))
    args = parser.parse_args()
    print(json.dumps(archive(args.economy), indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Fail closed for PDF units whose canonical text/span alignment is unresolved."""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from packages.core.envfile import load_env_file  # noqa: E402
from packages.graph.sqlite_graph import SqliteGraphStore  # noqa: E402
from packages.graph.store import get_graph_store  # noqa: E402


def main() -> int:
    load_env_file()
    stores = [get_graph_store()]
    if (os.getenv("GRAPH_BACKEND") or "sqlite").casefold() != "sqlite":
        stores.append(SqliteGraphStore())
    total = 0
    for store in stores:
        quarantine = getattr(store, "quarantine_unaligned_provisions", None)
        if quarantine is None:
            print(f"{type(store).__name__}: quarantine contract unavailable")
            continue
        changed = quarantine()
        total += changed
        print(f"{type(store).__name__}: {changed} unaligned provisions quarantined")
    print(f"TOTAL quarantined: {total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

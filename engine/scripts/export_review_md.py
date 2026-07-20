"""Export output rows as reviewable Markdown — one file per run, one section per
row, with the FULL provision text (from the graph) under each row so a reviewer
(human or AI) never has to open the source PDF.

Usage: .venv/bin/python scripts/export_review_md.py outputs/p2_my_p6_v3 [more dirs...]
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from packages.core.envfile import load_env_file  # noqa: E402

load_env_file()

from packages.discovery.diff import laws_match, section_base  # noqa: E402
from packages.graph.sqlite_graph import SqliteGraphStore  # noqa: E402


def load_provisions(store) -> list[dict]:
    """Read the provision corpus once for the whole review export.

    The previous implementation re-scanned and decoded every graph provision
    for every output row.  Runtime therefore grew as rows x corpus size.
    """
    import json as _json
    rows = store._connect().execute("SELECT props FROM nodes WHERE label='Provision'").fetchall()
    return [_json.loads(props) for (props,) in rows]


def provision_text(provisions: list[dict], economy: str, law_name: str, article: str) -> str:
    base = section_base(article)
    hits = []
    for p in provisions:
        if (p.get("economy") == economy and laws_match(law_name, p.get("law_name", ""))
                and section_base(p.get("article_section", "")) == base):
            hits.append(p)
    return "\n\n".join(f"**{p['article_section']}** — {p.get('text','')}" for p in sorted(
        hits, key=lambda p: p.get("article_section", ""))) or "(provision not found in graph)"


def export(run_dir: Path, provisions: list[dict]) -> Path:
    rows = list(csv.DictReader((run_dir / "output.csv").open(encoding="utf-8")))
    lines = [f"# Review: {run_dir.name} — {len(rows)} rows\n"]
    for i, r in enumerate(rows, 1):
        tag = r.get("Discovery Tag", "")
        lines += [
            f"\n---\n\n## Row {i}: {r.get('Indicator ID')} · {r.get('Article / Section')} · **{tag}**",
            f"- **Law:** {r.get('Law Name')}  \n- **Confidence:** {r.get('Confidence')}  "
            f"\n- **Source:** {r.get('Source URL')}  \n- **Coverage:** {r.get('Coverage','')}",
            f"\n> **Verbatim snippet:** {r.get('Verbatim Snippet')}",
            f"\n**Rationale:** {r.get('Mapping Rationale')}",
            f"\n**Notes:** {r.get('Notes','')}",
            "\n<details><summary>Full section text (from graph)</summary>\n",
            provision_text(provisions, r.get("Economy", ""), r.get("Law Name", ""),
                           r.get("Article / Section", "")),
            "\n</details>",
        ]
    out = run_dir / "review.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    return out


if __name__ == "__main__":
    store = SqliteGraphStore()
    provisions = load_provisions(store)
    for arg in sys.argv[1:]:
        print("wrote", export(Path(arg), provisions))

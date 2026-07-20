"""Remove duplicated span payloads after immutable TextSpans are stored separately."""
from __future__ import annotations

import sqlite3
from pathlib import Path


def main() -> int:
    path = Path("data/graph_v2.db")
    connection = sqlite3.connect(path)
    try:
        before = connection.execute(
            "SELECT count(*) FROM nodes WHERE label='Provision' "
            "AND json_type(props,'$.metadata.aligned_span_evidence') IS NOT NULL"
        ).fetchone()[0]
        connection.execute(
            "UPDATE nodes SET props=json_remove(props,'$.metadata.aligned_span_evidence') "
            "WHERE label='Provision' "
            "AND json_type(props,'$.metadata.aligned_span_evidence') IS NOT NULL"
        )
        connection.execute(
            "UPDATE discovery_leads SET payload=json_object(" 
            "'provision_id',json_extract(payload,'$.id'),"
            "'economy',json_extract(payload,'$.economy'),"
            "'law_name',json_extract(payload,'$.law_name'),"
            "'article_section',json_extract(payload,'$.article_section')) "
            "WHERE reason_code='ALIGNMENT_UNRESOLVED' "
            "AND length(payload)>2000"
        )
        connection.commit()
        print(f"compacted duplicated span payloads from {before} provisions")
        return 0
    finally:
        connection.close()


if __name__ == "__main__":
    raise SystemExit(main())

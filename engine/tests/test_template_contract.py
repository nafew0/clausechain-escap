"""The CSV header must equal the organizer template's header row — byte for byte.

The template xlsx is vendored into tests/fixtures so this guard runs everywhere.
"""
from __future__ import annotations

from pathlib import Path

from packages.export.csv_writer import REQUIRED_HEADER
from packages.ingest.xlsx import read_rows

FIXTURE = Path(__file__).parent / "fixtures" / "OUTPUT_TEMPLATE_31MAY.xlsx"


def test_csv_header_matches_official_template() -> None:
    """The 13 REQUIRED columns must match the template exactly (extras append after)."""
    rows = read_rows(FIXTURE, "Output Data")
    header_row = next(row for row in rows if row and row[0].strip() == "Economy")
    assert tuple(cell.strip() for cell in header_row[: len(REQUIRED_HEADER)]) == REQUIRED_HEADER

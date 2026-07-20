from __future__ import annotations

import csv
from pathlib import Path
from typing import Iterable, Sequence

from packages.core.schemas import MappedFinding


# The 13 REQUIRED columns — order/spelling asserted byte-equal to OUTPUT_TEMPLATE_31MAY.xlsx.
REQUIRED_HEADER: tuple[str, ...] = (
    "Economy",
    "Law Name",
    "Law Number / Ref",
    "Last Amended",
    "Indicator ID",
    "Article / Section",
    "Discovery Tag",
    "Location Reference",
    "Verbatim Snippet",
    "Mapping Rationale",
    "Source URL",
    "Confidence",
    "Notes",
)
# Allowed extras, appended AFTER the 13 (15-Jun Q&A: additional columns permitted).
EXTRA_HEADER: tuple[str, ...] = (
    "Coverage",
    "Verbatim Snippet (English)",
    "Status",
)
CSV_HEADER: tuple[str, ...] = REQUIRED_HEADER + EXTRA_HEADER


def assert_header(header: Sequence[str]) -> None:
    """The header must START with the 13 required template columns; extras may follow."""
    actual = tuple(header)
    if actual[: len(REQUIRED_HEADER)] != REQUIRED_HEADER:
        raise ValueError(
            f"CSV header must start with the 13 template columns {REQUIRED_HEADER!r}; got {actual!r}"
        )


def finding_to_row(finding: MappedFinding) -> dict[str, object]:
    data = finding.model_dump(by_alias=True, mode="json")
    return {column: ("" if data.get(column) is None else data.get(column)) for column in CSV_HEADER}


def write_csv(
    findings: Iterable[MappedFinding],
    output_path: str | Path,
    header: Sequence[str] = CSV_HEADER,
) -> Path:
    assert_header(header)
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=list(header), extrasaction="ignore")
        writer.writeheader()
        for finding in findings:
            writer.writerow(finding_to_row(finding))

    return path


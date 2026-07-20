from __future__ import annotations

import csv

import pytest

from packages.core.orchestrator import run
from packages.export.csv_writer import CSV_HEADER, assert_header, write_csv


def test_csv_writer_rejects_wrong_header() -> None:
    with pytest.raises(ValueError):
        assert_header(["Economy", "Wrong"])


def test_csv_writer_writes_exact_header(tmp_path) -> None:
    envelope = run(country="SG", pillar=6)
    output_path = tmp_path / "output.csv"

    write_csv(envelope.findings, output_path)

    with output_path.open(newline="", encoding="utf-8") as file:
        reader = csv.reader(file)
        header = next(reader)

    assert tuple(header) == CSV_HEADER


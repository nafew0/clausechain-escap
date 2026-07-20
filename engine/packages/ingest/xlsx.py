"""Minimal read-only XLSX access using only the standard library.

Good enough for the ESCAP workbooks (shared strings, inline strings, plain
values). Avoids adding openpyxl as a dependency for read-only ingestion.
"""
from __future__ import annotations

import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

M = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
RID = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
RNS = "{http://schemas.openxmlformats.org/package/2006/relationships}"


def _cell_col(ref: str) -> int:
    col = 0
    for ch in ref:
        if ch.isalpha():
            col = col * 26 + (ord(ch.upper()) - 64)
        else:
            break
    return col - 1


def _shared_strings(z: zipfile.ZipFile) -> list[str]:
    try:
        root = ET.fromstring(z.read("xl/sharedStrings.xml"))
    except KeyError:
        return []
    return ["".join(t.text or "" for t in si.iter(f"{M}t")) for si in root.findall(f"{M}si")]


def sheet_names(path: str | Path) -> list[str]:
    with zipfile.ZipFile(path) as z:
        return list(_sheet_paths(z))


def _sheet_paths(z: zipfile.ZipFile) -> dict[str, str]:
    wb = ET.fromstring(z.read("xl/workbook.xml"))
    rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
    rel_map = {rel.get("Id"): rel.get("Target") for rel in rels.iter(f"{RNS}Relationship")}
    out: dict[str, str] = {}
    for sheet in wb.iter(f"{M}sheet"):
        target = rel_map.get(sheet.get(RID), "") or ""
        if target.startswith("/"):
            target = target[1:]
        elif not target.startswith("xl/"):
            target = f"xl/{target}"
        out[sheet.get("name") or ""] = target
    return out


def read_rows(path: str | Path, sheet_name: str | None = None) -> list[list[str]]:
    """Return all rows of one sheet as lists of strings ('' for empty cells)."""
    with zipfile.ZipFile(path) as z:
        strings = _shared_strings(z)
        sheets = _sheet_paths(z)
        if sheet_name is None:
            sheet_name = next(iter(sheets))
        if sheet_name not in sheets:
            raise KeyError(f"Sheet {sheet_name!r} not in {list(sheets)}")
        root = ET.fromstring(z.read(sheets[sheet_name]))

        rows: list[list[str]] = []
        for row in root.iter(f"{M}row"):
            cells: dict[int, str] = {}
            for c in row.iter(f"{M}c"):
                idx = _cell_col(c.get("r") or "A")
                kind = c.get("t")
                if kind == "s":
                    v = c.find(f"{M}v")
                    val = strings[int(v.text)] if v is not None and v.text else ""
                elif kind == "inlineStr":
                    val = "".join(t.text or "" for t in c.iter(f"{M}t"))
                else:
                    v = c.find(f"{M}v")
                    val = v.text if v is not None and v.text else ""
                cells[idx] = val or ""
            if cells:
                width = max(cells) + 1
                rows.append([cells.get(i, "") for i in range(width)])
            else:
                rows.append([])
        return rows

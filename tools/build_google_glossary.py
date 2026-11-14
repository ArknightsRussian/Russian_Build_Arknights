"""Import the community glossary spreadsheet into a small JSON map.

The spreadsheet is the canonical source for names, races, places, organisations
and terms. Only rows that have both a Latin source and a Cyrillic target are
kept. Values are later used for exact keys and for the ``<...>`` glossary.

Run: py tools/build_google_glossary.py <path-to.xlsx>
"""
from __future__ import annotations

import json
import re
import sys
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "tools" / "google_glossary.json"
REPORT = ROOT / "work" / "google_glossary_report.tsv"
NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
MAIN = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}t"

# sheet name -> (latin column, cyrillic column)
SHEETS = {
    "Игровые персонажи": (0, 1),
    "Имена (NPC) и прочее": (0, 1),
    "Расы и не только": (0, 1),
    "Термины и прочее": (0, 1),
    "Страны, города и локации": (0, 1),
    "Организации": (0, 1),
    "Потом": (0, 1),
    "Классы и подклассы": (0, 1),
    "Трекер сюжетов": (0, 1),
}


def shared_strings(z: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in z.namelist():
        return []
    root = ET.fromstring(z.read("xl/sharedStrings.xml"))
    return ["".join(t.text or "" for t in si.iter(MAIN))
            for si in root.findall("m:si", NS)]


def col_index(ref: str) -> int:
    letters = re.match(r"[A-Z]+", ref).group(0)
    n = 0
    for c in letters:
        n = n * 26 + ord(c) - 64
    return n - 1


def read_sheet(z: zipfile.ZipFile, path: str, shared: list[str]):
    root = ET.fromstring(z.read(path))
    for row in root.findall(".//m:sheetData/m:row", NS):
        cells: dict[int, str] = {}
        for c in row.findall("m:c", NS):
            value = c.find("m:v", NS)
            if value is None:
                isel = c.find("m:is", NS)
                text = "".join(t.text or "" for t in isel.iter(MAIN)) if isel is not None else ""
            elif c.get("t") == "s":
                text = shared[int(value.text)]
            else:
                text = value.text or ""
            cells[col_index(c.get("r"))] = text.strip()
        if cells:
            yield cells


def clean_latin(value: str) -> str:
    value = value.strip().strip("\"'“”‘’").strip()
    return value


def clean_cyr(value: str) -> str:
    value = value.strip().strip("\"'").strip()
    return value


def main() -> int:
    source = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(
        r"C:\Users\Артём\AppData\Local\Temp\opencode\glossary_new.xlsx")
    z = zipfile.ZipFile(source)
    shared = shared_strings(z)
    wb = ET.fromstring(z.read("xl/workbook.xml"))
    rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
    relmap = {r.get("Id"): r.get("Target") for r in rels}
    targets: dict[str, str] = {}
    for sh in wb.find("m:sheets", NS):
        rid = sh.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")
        target = relmap[rid]
        targets[sh.get("name")] = target if target.startswith("xl/") else "xl/" + target

    result: dict[str, str] = {}
    report: list[tuple[str, str, str]] = []
    for sheet, (latin_col, cyr_col) in SHEETS.items():
        if sheet not in targets:
            print("missing sheet:", sheet)
            continue
        kept = 0
        for cells in read_sheet(z, targets[sheet], shared):
            latin = clean_latin(cells.get(latin_col, ""))
            cyr = clean_cyr(cells.get(cyr_col, ""))
            if not latin or not cyr:
                continue
            if not re.search(r"[A-Za-z]", latin) or not re.search(r"[А-Яа-яЁё]", cyr):
                continue
            if len(latin) > 120 or len(cyr) > 160:
                continue
            key = latin.casefold()
            if key in result:
                if result[key] != cyr:
                    report.append((sheet, latin, f"{result[key]} -> {cyr} (kept first)"))
                continue
            result[latin] = cyr
            kept += 1
        print(f"{sheet}: {kept}")

    OUT.write_text(json.dumps(dict(sorted(result.items(), key=lambda kv: kv[0].casefold())),
                              ensure_ascii=False, indent=1) + "\n",
                   encoding="utf-8", newline="\n")
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    with open(REPORT, "w", encoding="utf-8", newline="\n") as handle:
        handle.write("sheet\tlatin\tconflict\n")
        for sheet, latin, conflict in report:
            handle.write(f"{sheet}\t{latin}\t{conflict}\n")
    print(f"wrote {OUT}: {len(result)} entries, {len(report)} conflicts -> {REPORT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Import the authoritative operator glossary from Google Sheets.

Source file: ``glossary/operators.csv`` (downloaded from the sheet below).
Columns: EN callsign, RU callsign, full EN name, full RU name, comment.

The sheet is the single source of truth for operator names. The importer
writes ``ru-overrides/05_glossary_names.json`` so the merge pipeline applies
it before the user's own ``00_fixes.json`` (the user always has the last say).

Known sheet errors are listed in ``SKIP`` and never applied automatically.

Run:  py tools/import_glossary.py
"""
from __future__ import annotations

import csv
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "glossary" / "operators.csv"
OUT = ROOT / "ru-overrides" / "05_glossary_names.json"

# The sheet lists Touch=Тачанка, duplicating the R6S operator Tachanka.
# "Touch" is a separate NPC/operator, so the value is a sheet bug. Keep the
# existing translation instead of silently renaming her to Tachanka.
SKIP = {"Touch"}

LATIN_RE = re.compile(r"[A-Za-z]")


def main() -> int:
    if not SRC.is_file():
        raise SystemExit(f"missing {SRC}; download the sheet into glossary/operators.csv")
    rows = list(csv.reader(SRC.read_text(encoding="utf-8-sig").splitlines()))
    if not rows:
        raise SystemExit("empty glossary")

    header = rows[0]
    if len(header) < 2 or "латиниц" not in header[0].lower():
        raise SystemExit(f"unexpected header: {header!r}")

    result: dict[str, str] = {}
    conflicts: list[tuple[str, str, str, str]] = []
    skipped: list[str] = []
    full_names = 0

    for row in rows[1:]:
        if len(row) < 2:
            continue
        en, ru = row[0].strip(), row[1].strip()
        if not en or not ru:
            continue
        if en in SKIP:
            skipped.append(en)
            continue
        if not LATIN_RE.search(en):
            continue
        if en in result and result[en] != ru:
            conflicts.append((en, result[en], ru, "duplicate EN"))
            continue
        result[en] = ru

        # Optional full name columns.
        if len(row) >= 4:
            full_en, full_ru = row[2].strip(), row[3].strip()
            if full_en and full_ru and LATIN_RE.search(full_en):
                if full_en in result and result[full_en] != full_ru:
                    conflicts.append((full_en, result[full_en], full_ru, "duplicate full EN"))
                else:
                    result[full_en] = full_ru
                    full_names += 1

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps(dict(sorted(result.items())), ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(f"glossary: {len(result)} names ({full_names} full) -> {OUT}")
    if skipped:
        print("skipped sheet rows:", ", ".join(skipped))
    for en, old, new, reason in conflicts[:20]:
        print(f"conflict ({reason}): {en}: {old!r} vs {new!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

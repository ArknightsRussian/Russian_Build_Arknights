"""Build ID-indexed RU context data (operator names etc.) like the CN project's.

Sources:
  - TSV tagged rows (table + structural path with char_*/skchr_* IDs)
  - Open gamedata EN (authoritative ID -> EN text)
Output:
  - work/ru-context.json {operators: {charId: {name_en, name_ru, fields}}, skills, stats}
  - work/13_names_from_ids.json (authoritative operator names for 13_names.txt)

Usage: py tools/build_ru_context.py
"""
from __future__ import annotations

import csv
import json
import pathlib
import re
from collections import Counter

ID_RE = re.compile(r"(?:char|skchr|token|trap)_[A-Za-z0-9_]+")
DATA = pathlib.Path("cache/ArknightsGamedataMulti/en/gamedata/excel")


def load_json(name: str):
    p = DATA / name
    if not p.is_file():
        return {}
    return json.loads(p.read_text(encoding="utf-8-sig"))


def main() -> int:
    chars = load_json("character_table.json")
    print("gamedata characters:", len(chars))
    name_by_id = {cid: v.get("name", "") for cid, v in chars.items() if isinstance(v, dict)}

    # TSV tagged rows -> (id, field, en, ru)
    with open("perevod.tsv", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.reader(f, delimiter="\t"))
    tagged = 0
    by_id: dict[str, list[dict]] = {}
    for r in rows[1:]:
        if len(r) < 4 or not r[2].strip() or not r[3].strip():
            continue
        s, t = (r[0] or "").strip(), (r[1] or "").strip()
        if not s or not t or s == t:
            continue
        for cid in set(ID_RE.findall(r[3])):
            by_id.setdefault(cid, []).append(
                {"table": r[2].strip()[:60], "field": r[3].strip()[:120], "en": s, "ru": t})
            tagged += 1
    print("tagged rows:", tagged, "ids:", len(by_id))

    # Full-TSV index: names live mostly in UNtagged rows.
    en_index: dict[str, Counter] = {}
    for r in rows[1:]:
        if len(r) < 2:
            continue
        s, t = (r[0] or "").strip(), (r[1] or "").strip()
        if s and t and s != t and " " not in s and "\n" not in s:
            en_index.setdefault(s, Counter())[t] += 1

    operators: dict[str, dict] = {}
    for cid, recs in by_id.items():
        if not cid.startswith("char_"):
            continue
        entry: dict = {"name_en": name_by_id.get(cid, ""), "name_ru": "", "fields": {}}
        for rec in recs:
            fl = rec["field"].lower()
            if any(k in fl for k in ("storytext", "talent", "trait", "skill", "descript")):
                entry["fields"].setdefault(rec["field"][:80], rec["ru"][:200])
        # Authoritative name: tagged evidence first, else full-TSV single-token rows.
        cands = [rec["ru"] for rec in recs if rec["en"] == entry["name_en"] and rec["ru"]]
        if not cands and entry["name_en"] in en_index:
            cands = list(en_index[entry["name_en"]].elements())
        if cands:
            # Prefer bare form (no trailing punctuation) and most common.
            bare = [c for c in cands if c and c[-1].isalnum()]
            pool = bare or cands
            entry["name_ru"] = Counter(pool).most_common(1)[0][0]
        operators[cid] = entry
    with_name = sum(1 for v in operators.values() if v["name_ru"])
    print(f"operators: {len(operators)}, with RU name: {with_name}")

    names = {cid: v["name_ru"] for cid, v in operators.items() if v["name_ru"]}
    out = pathlib.Path("work/ru-context.json")
    out.write_text(json.dumps({"operators": operators,
                               "stats": {"ids": len(by_id), "operators": len(operators),
                                         "with_name": with_name}},
                              ensure_ascii=False, indent=1), encoding="utf-8")
    pathlib.Path("work/13_names_from_ids.json").write_text(
        json.dumps(names, ensure_ascii=False, indent=1), encoding="utf-8")
    print("names:", len(names), "-> work/13_names_from_ids.json, full -> work/ru-context.json")

    # Same EN -> different RU across DIFFERENT ids: true context conflicts.
    en_to_ids: dict[str, dict[str, str]] = {}
    for cid, recs in by_id.items():
        for rec in recs:
            en_to_ids.setdefault(rec["en"], {})[cid] = rec["ru"]
    multi = {k: v for k, v in en_to_ids.items() if len(set(v.values())) > 1}
    print("cross-ID conflicts (need context, flat dict keeps one):", len(multi))
    samples = list(multi.items())[:10]
    for en, m in samples:
        print("  ", repr(en[:60]), {k: v[:30] for k, v in list(m.items())[:3]})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

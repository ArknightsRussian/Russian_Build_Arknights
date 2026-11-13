"""Pre-expand runtime skill/module/talent descriptions into direct translations.

The game substitutes ``{key}`` macros (skill numbers, talent values) into the
display text before XUnity sees it, so plain template entries never match and
the pack builder emits a huge regex per template. A 6 MB regex file makes the
first translation load freeze for ~a minute.

This script takes every concrete description variant that already exists in
the game data (skill levels, talent candidates, module candidates), substitutes
the real blackboard values into both the EN template and its RU translation,
and writes the resulting exact pairs as a normal manifest. Those become cheap
hash lookups instead of regexes. Templates whose every data variant was
expanded are listed in ``work/regex_exclude.json`` so the pack builder can skip
their regex.

Usage:
  py tools/build_skill_direct.py [--excel work/client-hot1105/decoded/dyn/gamedata/excel]
                                 [--map merged-manifests/99_merged.json]
                                 [--out merged-manifests/00_skill_direct.json]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from arklocalizer.custom_pack import (  # noqa: E402
    MACRO_RE, _canon_source, _strip_tags, strip_display_tags,
)
from arklocalizer.util import normalize_lookup_text  # noqa: E402

DEFAULT_EXCEL = ROOT / "work" / "client-hot1105" / "decoded" / "dyn" / "gamedata" / "excel"
DEFAULT_MAP = ROOT / "merged-manifests" / "99_merged.json"
DEFAULT_OUT = ROOT / "merged-manifests" / "00_skill_direct.json"
EXCLUDE = ROOT / "work" / "regex_exclude.json"
EXCLUDE_DIRECT = ROOT / "work" / "regex_exclude_direct.json"
REPORT = ROOT / "work" / "skill_direct_report.json"

HAN_RE = re.compile(r"[\u4e00-\u9fff]")


def variant_keys(text: str):
    seen = set()
    for base in (text, strip_display_tags(text), _strip_tags(text)):
        for v in (base, normalize_lookup_text(base),
                  _canon_source(normalize_lookup_text(base))):
            if v and v not in seen:
                seen.add(v)
                yield v


def load_index(mapping: dict[str, str]) -> dict[str, str]:
    index: dict[str, str] = {}
    for source, target in mapping.items():
        for key in variant_keys(source):
            index.setdefault(key, target)
    return index


def lookup(index: dict[str, str], text: str) -> str | None:
    for key in variant_keys(text):
        if key in index:
            return index[key]
    return None


def fmt(value: float, spec: str | None) -> str:
    if spec is None or spec == "":
        if isinstance(value, float) and value.is_integer():
            return str(int(value))
        return f"{value:g}"
    percent = spec.endswith("%")
    core = spec[:-1] if percent else spec
    decimals = len(core.split(".", 1)[1]) if "." in core else 0
    scaled = value * 100 if percent else value
    if decimals:
        text = f"{scaled:.{decimals}f}"
    else:
        text = f"{round(scaled):.0f}"
    return text + ("%" if percent else "")


def as_values(blackboard) -> dict[str, float]:
    if isinstance(blackboard, dict):
        return {str(k): float(v) for k, v in blackboard.items()
                if isinstance(v, (int, float))}
    values: dict[str, float] = {}
    if isinstance(blackboard, list):
        for item in blackboard:
            if isinstance(item, dict) and "key" in item and "value" in item:
                try:
                    values[str(item["key"])] = float(item["value"])
                except (TypeError, ValueError):
                    pass
    return values


def resolve(name: str, values: dict[str, float], extra: dict[str, float]) -> float | None:
    key = name.casefold()
    for candidate in (key, key.split("@", 1)[1] if "@" in key else None):
        if candidate is not None and candidate in values:
            return values[candidate]
        if candidate is not None and candidate in extra:
            return extra[candidate]
    if key.startswith("-"):
        inner = resolve(key[1:], values, extra)
        if inner is not None:
            return -inner
    return None


def expand(text: str, values: dict[str, float], extra: dict[str, float]):
    missing: list[str] = []

    def repl(m):
        body = m.group(0)[1:-1]
        name, _, spec = body.partition(":")
        value = resolve(name, values, extra)
        if value is None:
            missing.append(name)
            return m.group(0)
        return fmt(value, spec or None)

    return MACRO_RE.sub(repl, text), missing


class Expander:
    def __init__(self, index: dict[str, str]):
        self.index = index
        self.pairs: dict[str, str] = {}
        self.kind_stats: dict[str, Counter] = defaultdict(Counter)
        self.tpl_stats: dict[tuple[str, str], dict] = {}
        self.exclude: set[str] = set()

    def add(self, kind: str, template: str, values: dict[str, float],
            extra: dict[str, float] | None = None) -> None:
        if "{" not in template:
            return
        canon = _canon_source(normalize_lookup_text(template))
        if not canon:
            return
        key = (kind, canon)
        stat = self.tpl_stats.get(key)
        if stat is None:
            stat = self.tpl_stats[key] = {
                "kind": kind, "canon": canon, "template": template,
                "total": 0, "ok": 0,
            }
        stat["total"] += 1
        kstat = self.kind_stats[kind]
        kstat["variants"] += 1

        target = lookup(self.index, template)
        if not target:
            kstat["no_translation"] += 1
            return
        if "{0}" in template or "{1}" in template:
            kstat["positional"] += 1
            return
        en, missing = expand(template, values, extra or {})
        ru, missing_ru = expand(target, values, extra or {})
        if missing or missing_ru:
            kstat["unresolved"] += 1
            for name in missing + missing_ru:
                kstat["missing:" + name] += 1
            return
        if not en or not ru or HAN_RE.search(ru):
            kstat["invalid"] += 1
            return
        kstat["ok"] += 1
        stat["ok"] += 1
        self.pairs.setdefault(en, ru)

    def finalize(self) -> None:
        for stat in self.tpl_stats.values():
            if stat["total"] and stat["ok"] == stat["total"]:
                for key in variant_keys(stat["template"]):
                    self.exclude.add(key)


def collect(excel: Path, expander: Expander) -> dict[str, int]:
    counts = Counter()

    skill_path = excel / "skill_table.json"
    if skill_path.is_file():
        data = json.loads(skill_path.read_text(encoding="utf-8-sig"))
        data = data.get("skills", data)
        for skill in data.values():
            for level in skill.get("levels") or []:
                extra = {}
                if isinstance(level.get("duration"), (int, float)):
                    extra["duration"] = float(level["duration"])
                sp = level.get("spData") or {}
                for src, dst in (("spCost", "sp_cost"), ("initSp", "init_sp"),
                                 ("maxChargeTime", "max_charge_time"),
                                 ("increment", "increment")):
                    if isinstance(sp.get(src), (int, float)):
                        extra[dst] = float(sp[src])
                expander.add("skill", level.get("description") or "",
                             as_values(level.get("blackboard")), extra)
                counts["skill_levels"] += 1

    char_path = excel / "character_table.json"
    if char_path.is_file():
        data = json.loads(char_path.read_text(encoding="utf-8-sig"))
        data = data.get("characters", data)
        for char in data.values():
            for talent in char.get("talents") or []:
                for cand in talent.get("candidates") or []:
                    expander.add("talent", cand.get("description") or "",
                                 as_values(cand.get("blackboard")))
                    counts["talent_candidates"] += 1

    equip_path = excel / "battle_equip_table.json"
    if equip_path.is_file():
        data = json.loads(equip_path.read_text(encoding="utf-8-sig"))
        data = data.get("equips", data)
        for equip in data.values():
            for phase in equip.get("phases") or []:
                for part in phase.get("parts") or []:
                    for bundle_name in ("overrideTraitDataBundle",
                                        "addOrOverrideTalentDataBundle"):
                        bundle = part.get(bundle_name) or {}
                        for cand in bundle.get("candidates") or []:
                            for field in ("additionalDescription",
                                          "upgradeDescription"):
                                expander.add("module", cand.get(field) or "",
                                             as_values(cand.get("blackboard")))
                                counts["module_candidates"] += 1
    return counts


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--excel", default=str(DEFAULT_EXCEL))
    ap.add_argument("--map", default=str(DEFAULT_MAP))
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    args = ap.parse_args()

    excel = Path(args.excel)
    if not excel.is_dir():
        raise SystemExit(f"missing decoded excel dir: {excel}")
    mapping = json.loads(Path(args.map).read_text(encoding="utf-8-sig"))
    expander = Expander(load_index(mapping))

    counts = collect(excel, expander)
    expander.finalize()

    out = Path(args.out)
    out.write_text(json.dumps(dict(sorted(expander.pairs.items())), ensure_ascii=False),
                   encoding="utf-8")
    EXCLUDE.write_text(json.dumps(sorted(expander.exclude), ensure_ascii=False, indent=1) + "\n",
                       encoding="utf-8", newline="\n")
    EXCLUDE_DIRECT.write_text(json.dumps(sorted(expander.exclude), ensure_ascii=False, indent=1) + "\n",
                              encoding="utf-8", newline="\n")
    report = {
        "excel": str(excel),
        "pairs": len(expander.pairs),
        "templates_excluded": len(expander.exclude),
        "counts": counts,
        "stats": {k: dict(v) for k, v in sorted(expander.kind_stats.items())},
        "templates": {
            f"{v['kind']}: {v['template'][:120]}": {"total": v["total"], "ok": v["ok"]}
            for v in sorted(expander.tpl_stats.values(), key=lambda x: (x["kind"], x["canon"]))
        },
    }
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8", newline="\n")
    print("pairs:", len(expander.pairs))
    print("excluded template variants:", len(expander.exclude))
    for kind, stat in sorted(expander.kind_stats.items()):
        print(kind, dict(stat))
    print("wrote", out, out.stat().st_size)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

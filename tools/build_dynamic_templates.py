"""Convert runtime-macro templates into plugin-side dynamic rules.

XUnity AutoTranslator compiles every ``14_regex.txt`` pattern and then scans
ALL of them for every unmatched text (see TextTranslationCache.TryGetTranslation
-> ``for i in _defaultRegexes``). With ~2900 multi-KB patterns that sweep is the
minute-long freeze on first load.

The companion RichTextFix plugin runs *before* XUnity's cache/regex lookup
(``InvokeOnTranslatingCallback`` in AutoTranslationPlugin) and can override the
text. Its ``DynamicTranslations`` engine keeps templates as pre-compiled, anchor
filtered rules, so a template moved there costs almost nothing at runtime.

This script emits those rules for every macro template that the pack builder
would otherwise turn into a regex (same criteria: matching macro keys and >=12
literal characters), then adds their key variants to ``work/regex_exclude.json``
so the builder skips them.

Run AFTER tools/build_skill_direct.py (it rewrites regex_exclude.json).
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from arklocalizer.custom_pack import (  # noqa: E402
    HAN_RE, MACRO_RE, _canon_source, _macro_key, _macro_regex_pair,
    _strip_tags, strip_display_tags,
)
from arklocalizer.util import normalize_lookup_text  # noqa: E402

MAP_PATH = ROOT / "merged-manifests" / "99_merged.json"
OUT = ROOT / "work" / "dynamic_templates.json"
EXCLUDE = ROOT / "work" / "regex_exclude.json"
EXCLUDE_DIRECT = ROOT / "work" / "regex_exclude_direct.json"
REPORT = ROOT / "work" / "dynamic_templates_report.json"

MIN_LITERAL = 12   # matches _macro_regex_pair's threshold
MIN_ANCHOR = 6     # longest literal run; keeps placeholder-only rules out
SHORT_ANCHOR = 2   # allowed only when every slot is validated as a number
GREETING_ANCHOR = 3  # "Dr. {@nickname}!" — the literal before the slot is "Dr."

# Slots that hold a plain number at runtime. Used ONLY to unlock the short-anchor
# branch: the plugin then rejects any non-numeric capture, so a 2-3 character
# anchor ("ms", "sec", "ATK ") cannot misfire on ordinary prose.
NUMERIC_NAMES = {
    "atk", "def", "res", "attack_speed", "hp_ratio", "atk_scale",
    "atk_scale_2", "atk_scale_aoe", "atk_scale_e", "atk_scale_extra",
    "display_move_speed", "move_speed", "value", "duration", "duration_2",
    "stun", "constraint", "sluggish", "cost", "prob", "talent_scale",
    "fake_scale", "fake_interval", "block_cnt", "max_target_extra",
    "interval", "score", "next_score", "hp", "max_hp",
}

# The static game-UI label "Elite 2 Lv. 1" has no row in the translation map;
# it used to be a hardcoded regex in custom_pack.py.
MANUAL_RULES = [
    {
        "scope": "any",
        "source": "Elite {0} Lv. {1}",
        "target": "Элита {0}, ур. {1}",
        "roles": {"0": "number", "1": "number"},
    },
]


def _numeric_slot(token: str) -> bool:
    """A slot is numeric if it carries a format spec ({0:d2}, {atk:0%}) or is
    a known numeric macro name (also when nested, e.g.
    ``{tomb_buff[sniper_0].attack_speed}`` or ``{-attack_speed}``)."""
    key = _macro_key(token)
    if ":" in token or key.isdigit():
        return True
    leaf = key.rsplit(".", 1)[-1].lstrip("+-")
    return key in NUMERIC_NAMES or leaf in NUMERIC_NAMES


# Literal words that can accompany a purely numeric template. Positional slots
# ({0}) are only assumed to hold numbers inside this vocabulary: "(Currently
# {0}/{1})" also uses {0}/{1} but they are a number and an operator name.
UNIT_WORDS = {
    "ms", "sec", "secs", "second", "seconds", "min", "mins", "minute",
    "minutes", "hr", "hrs", "hour", "hours", "day", "days",
    "elite", "lv", "lv.", "atk", "aspd", "def", "res", "hp", "sp",
}


def _numeric_template(source: str) -> bool:
    tokens = MACRO_RE.findall(source)
    if not tokens or not all(_numeric_slot(t) for t in tokens):
        return False
    plain = strip_display_tags(MACRO_RE.sub(" ", source))
    words = re.findall(r"[A-Za-z.]+", plain)
    return bool(words) and all(w.lower() in UNIT_WORDS for w in words)


def variant_keys(text: str):
    seen = set()
    for base in (text, strip_display_tags(text), _strip_tags(text)):
        for v in (base, normalize_lookup_text(base),
                  _canon_source(normalize_lookup_text(base))):
            if v and v not in seen:
                seen.add(v)
                yield v


def macro_keys(text: str) -> list[str]:
    return [_macro_key(m) for m in MACRO_RE.findall(text)]


def build_rules(mapping: dict[str, str],
                already: set[str]) -> tuple[list[dict], list[str], Counter]:
    rules: list[dict] = []
    originals: list[str] = []
    stats: Counter = Counter()
    for source, target in mapping.items():
        if not MACRO_RE.search(source):
            continue
        src_keys = macro_keys(source)
        tgt_keys = macro_keys(target)
        # Plugin substitutes by slot key, so every target slot must exist in
        # the source. Repeated keys are fine (same captured value).
        if any(key not in src_keys for key in tgt_keys):
            stats["target_slot_missing"] += 1
            continue
        plain_source = strip_display_tags(source)
        literal_chunks = [c for c in MACRO_RE.split(plain_source)]
        anchor = max(literal_chunks, key=len, default="")
        short_anchor = len("".join(anchor.split())) < MIN_ANCHOR
        numeric = _numeric_template(source)
        # "Dr. {@nickname}!", "Dr. {@nickname}.", "'Dr. {@nickname}?'" — the
        # only literal is a greeting. Allow a 3-char anchor ONLY when the
        # literal before the slot is exactly the "Dr." vocative; a bare
        # "I am {@nickname}." stays out (it would match any "I am ..." prose).
        nickname_greeting = (set(src_keys) == {"nickname"} and set(tgt_keys) == {"nickname"}
                             and anchor.rstrip().casefold().endswith("dr."))
        if short_anchor and not (
            (numeric and len(anchor.strip()) >= SHORT_ANCHOR)
            or (nickname_greeting and len(anchor.strip()) >= GREETING_ANCHOR)
        ):
            # too short / short but not purely numeric: the builder cannot emit
            # a safe XUnity regex either, so this pair stays untranslated.
            stats["anchor_too_short" if _macro_regex_pair(source, target) else "no_regex"] += 1
            continue
        if HAN_RE.search(target):
            stats["han_target"] += 1
            continue
        # Keep restored <@...>/<$...> markup: the plugin resolves value colours
        # and rewrites keyword links from it after substituting numbers.
        clean_target = target.strip()
        if not clean_target:
            stats["empty_target"] += 1
            continue
        roles = {key: "number" if (short_anchor and numeric) else "identity"
                 for key in dict.fromkeys(src_keys + tgt_keys)}
        rules.append({
            "scope": "any",
            "source": plain_source.strip(),
            "target": clean_target,
            "roles": roles,
        })
        originals.append(source)
        stats["short_anchor_numeric" if short_anchor else "rules"] += 1
    # de-duplicate identical sources (first wins, translation map is unique anyway)
    unique: dict[str, dict] = {}
    for rule in rules:
        previous = unique.get(rule["source"])
        if previous is None:
            unique[rule["source"]] = rule
        elif ("<@" in rule["target"] or "<$" in rule["target"]) and not (
                "<@" in previous["target"] or "<$" in previous["target"]):
            # The merged map contains both tagged and untagged variants of the
            # same sentence; keep the one carrying the rich tags.
            unique[rule["source"]] = rule
    for rule in MANUAL_RULES:
        unique.setdefault(rule["source"], rule)
    stats["unique_rules"] = len(unique)
    return list(unique.values()), originals, stats


def main() -> int:
    mapping = json.loads(MAP_PATH.read_text(encoding="utf-8-sig"))
    exclude: set[str] = set()
    if EXCLUDE_DIRECT.is_file():
        exclude.update(json.loads(EXCLUDE_DIRECT.read_text(encoding="utf-8-sig")))
    rules, originals, stats = build_rules(mapping, exclude)
    OUT.write_text(json.dumps(rules, ensure_ascii=False, indent=1) + "\n",
                   encoding="utf-8", newline="\n")

    for source in originals:
        for key in variant_keys(source):
            exclude.add(key)
    EXCLUDE.write_text(json.dumps(sorted(exclude), ensure_ascii=False, indent=1) + "\n",
                       encoding="utf-8", newline="\n")

    REPORT.write_text(json.dumps({
        "rules": len(rules),
        "exclude_total": len(exclude),
        "stats": dict(stats),
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print("rules:", len(rules))
    print("exclude_total:", len(exclude))
    print("stats:", dict(stats))
    print("wrote", OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Derive grammar-safe global rename rules from the Google glossary.

The community spreadsheet is the canonical source for names.  When its
Cyrillic form differs from the wording already used in the pack, the old form
must be replaced everywhere, not only in the standalone key.

Every Russian occurrence is inflected, so a plain string replace would break
the case ("Лунгмэна" -> "Луньмэньа").  This script builds a small paradigm
table for each declension class, detects the grammatical form of the old
occurrence from its ending, and rewrites it with the ending of the new name for
the *same* form.  A rename is only emitted when the gender does not change,
because gender also governs the agreeing adjectives and verbs; names like
"Reunion" -> "Воссоединение" are reported for manual sentence work instead.
Their standalone keys are still overridden by the pack builder.

Outputs:
  tools/google_variants.json        rules consumed by build_ru_merged_pack
  work/google_variants_report.tsv   everything that was applied or skipped

Run: py tools/build_google_variants.py
"""
from __future__ import annotations

import io
import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MERGED = ROOT / "merged-manifests" / "99_merged.json"
GLOSSARY = ROOT / "tools" / "google_glossary.json"
OUT = ROOT / "tools" / "google_variants.json"
REPORT = ROOT / "work" / "google_variants_report.tsv"

CYRILLIC = re.compile(r"[А-Яа-яЁё]")
CASES = ("nom_sg", "gen_sg", "dat_sg", "acc_sg", "ins_sg", "prep_sg",
         "nom_pl", "gen_pl", "dat_pl", "acc_pl", "ins_pl", "prep_pl")

# lemma ending length to strip, gender, and endings per grammatical form
PARADIGMS = {
    "masc": (0, "m", ("", "а", "у", "а", "ом", "е",
                      "ы", "ов", "ам", "ы", "ами", "ах")),
    "masc-y": (1, "m", ("й", "я", "ю", "я", "ем", "и",
                        "и", "ев", "ям", "и", "ями", "ях")),
    "masc-soft": (1, "m", ("ь", "я", "ю", "я", "ем", "е",
                           "и", "ей", "ям", "и", "ями", "ях")),
    "fem": (1, "f", ("а", "ы", "е", "у", "ой", "е",
                     "ы", "", "ам", "ы", "ами", "ах")),
    "fem-ya": (1, "f", ("я", "и", "е", "ю", "ей", "е",
                        "и", "ь", "ям", "и", "ями", "ях")),
    "neut": (1, "n", ("о", "а", "у", "о", "ом", "е",
                      "а", "", "ам", "а", "ами", "ах")),
    "neut-e": (1, "n", ("е", "я", "ю", "е", "ем", "е",
                        "я", "ь", "ям", "я", "ями", "ях")),
    "adj": (2, "m", ("", "ого", "ому", "ого", "ым", "ом",
                     "ые", "ых", "ым", "ые", "ыми", "ых")),
}


def load(path: Path):
    return json.loads(io.open(path, encoding="utf-8-sig").read())


def dequote(value: str) -> str:
    return value.strip().strip("'\"“”‘’«»").strip()


def word_re(text: str) -> str:
    return r"(?<![А-Яа-яЁё])" + re.escape(text) + r"(?![А-Яа-яЁё])"


def classify(word: str) -> str | None:
    w = word.lower()
    if not w or not CYRILLIC.match(w[-1]):
        return None
    if w.endswith(("ый", "ой", "ний", "ский", "цкий", "ший", "щий", "кий",
                   "гий", "хий", "жий", "чий")):
        return "adj"
    if w[-1] == "а":
        return "fem"
    if w[-1] == "я":
        return "fem-ya"
    if w[-1] == "о":
        return "neut"
    if w[-1] == "е":
        return "neut-e"
    if w[-1] == "ь":
        return "masc-soft"
    if w[-1] == "й":
        return "masc-y"
    if w[-1] in "ыи":
        return None
    return "masc"


def paradigm(cls: str) -> tuple[str, str, dict[str, str]]:
    strip, gender, endings = PARADIGMS[cls]
    return gender, "", {case: ending for case, ending in zip(CASES, endings)}


def ending_map(cls: str) -> dict[str, set[str]]:
    """old ending -> possible grammatical forms."""
    _, _, endings = PARADIGMS[cls]
    result: dict[str, set[str]] = {}
    for case, ending in zip(CASES, endings):
        result.setdefault(ending, set()).add(case)
    return result


def form_map(old_cls: str, new_cls: str) -> dict[str, str]:
    """old case ending -> new case ending, for one declension pair."""
    new_endings = dict(zip(CASES, PARADIGMS[new_cls][2]))
    if new_cls == "adj":
        new_endings["nom_sg"] = "ADJ_NOM"
        # Animate masculine accusative is identical to the genitive
        # ("Морерождённого"), which is how the glossary names are used.
        new_endings["acc_sg"] = new_endings["gen_sg"]
    result: dict[str, str] = {}
    for old_ending, cases in ending_map(old_cls).items():
        targets = {new_endings[case] for case in cases if case in new_endings}
        if len(targets) == 1:
            result[old_ending] = targets.pop()
    # Velar stems take "-и" in the nominative plural ("Исповедники"),
    # although the dictionary ending is "-ы".
    if old_cls.startswith("masc") and new_cls.startswith("masc") \
            and "и" not in result:
        result["и"] = new_endings["nom_pl"]
    return result


def phrase_rules(old_head: str, old_tail: str, new_prefix: str,
                 new_head: str, new_suffix: str) -> list[tuple[str, str, str]]:
    """Decline the head of a multi-word name, keep the rest fixed."""
    old_cls, new_cls = classify(old_head), classify(new_head)
    if old_cls is None or new_cls is None:
        return []
    if PARADIGMS[old_cls][1] != PARADIGMS[new_cls][1]:
        return []
    old_strip = PARADIGMS[old_cls][0]
    new_strip = PARADIGMS[new_cls][0]
    old_stem = old_head[:-old_strip] if old_strip else old_head
    new_stem = new_head[:-new_strip] if new_strip else new_head
    result: list[tuple[str, str, str]] = []
    for old_ending, new_ending in form_map(old_cls, new_cls).items():
        if new_ending == "ADJ_NOM":
            new_ending = new_head[-2:]
        pattern = (r"(?<![А-Яа-яЁё])" + re.escape(old_stem + old_ending) +
                   r"\s+" + re.escape(old_tail) + r"(?![А-Яа-яЁё])")
        replacement = new_prefix + " " + new_stem + new_ending + new_suffix
        result.append((pattern, replacement, old_ending or "nom_sg"))
    return result


def rename_rules(old: str, new: str) -> list[tuple[str, str, str]] | None:
    old_cls, new_cls = classify(old), classify(new)
    if old_cls is None or new_cls is None:
        return None
    if PARADIGMS[old_cls][1] != PARADIGMS[new_cls][1]:
        return None  # gender change also rewrites agreeing words
    old_strip = PARADIGMS[old_cls][0]
    new_strip = PARADIGMS[new_cls][0]
    old_stem = old[:-old_strip] if old_strip else old
    new_stem = new[:-new_strip] if new_strip else new
    new_endings = dict(zip(CASES, PARADIGMS[new_cls][2]))
    if new_cls == "adj":
        # An adjective lemma keeps its own suffix in the nominative; the
        # animate accusative follows the genitive.
        new_endings["nom_sg"] = new[-2:]
        new_endings["acc_sg"] = new_endings["gen_sg"]
    result: list[tuple[str, str, str]] = []
    for old_ending, cases in ending_map(old_cls).items():
        targets = {new_endings[case] for case in cases if case in new_endings}
        if len(targets) != 1:
            continue  # one old form would map to two new forms
        new_ending = targets.pop()
        pattern = (r"(?<![А-Яа-яЁё])" + re.escape(old_stem) +
                   re.escape(old_ending) + r"(?![А-Яа-яЁё])")
        result.append((pattern, new_stem + new_ending, old_ending or "nom_sg"))
    # Velar stems take "-и" in the nominative plural ("Исповедники").
    if old_cls.startswith("masc") and new_cls.startswith("masc") \
            and not any(form == "и" for _, _, form in result):
        pattern = (r"(?<![А-Яа-яЁё])" + re.escape(old_stem) +
                   r"и(?![А-Яа-яЁё])")
        result.append((pattern, new_stem + new_endings["nom_pl"], "и"))
    return result


def main() -> int:
    merged = load(MERGED)
    glossary = load(GLOSSARY)
    values = [v for v in merged.values() if isinstance(v, str)]
    words: Counter = Counter()
    word_re_all = re.compile(r"[А-Яа-яЁё]+")
    for value in values:
        words.update(word_re_all.findall(value))

    changed: list[tuple[str, str, str]] = []
    seen: set[str] = set()

    def add(key: str, old: str, new: str) -> None:
        old, new = dequote(old), dequote(new)
        if key not in seen:
            seen.add(key)
            changed.append((key, old, new))

    if REPORT.is_file():
        with io.open(REPORT, encoding="utf-8") as handle:
            next(handle, None)
            for line in handle:
                parts = line.rstrip("\n").split("\t")
                if len(parts) == 5:
                    add(parts[0], parts[1], parts[2])
    if len(changed) < 10 and (ROOT / "work" / "google_exact_changes.tsv").is_file():
        # The report may have been overwritten by a partial run; the raw
        # glossary comparison still holds every original pair.
        pending: list[list[str]] = []
        with io.open(ROOT / "work" / "google_exact_changes.tsv", encoding="utf-8") as handle:
            next(handle, None)
            for line in handle:
                line = line.rstrip("\n")
                if "\t" not in line:
                    if pending:
                        pending[-1][2] += " / " + line.strip()
                    continue
                pending.append(line.split("\t"))
        changed = []
        seen = set()
        for key, old, new in pending:
            add(key, old, new)
    if not changed:
        for latin, target in glossary.items():
            for key in (latin, dequote(latin)):
                if key in merged and merged[key] != target:
                    add(key, dequote(merged[key]), dequote(target))
                    break

    rules: list[dict[str, str]] = []
    report: list[tuple[str, str, str, str, int]] = []
    for key, old, new in changed:
        if not old or not new or old == new:
            continue
        if not CYRILLIC.search(old) or not CYRILLIC.search(new):
            report.append((key, old, new, "skip: non-cyrillic", 0))
            continue
        if any(ch in old for ch in ",;:!?()"):
            report.append((key, old, new, "skip: punctuation", 0))
            continue

        lower_hits = words.get(old.lower(), 0)
        if lower_hits >= 25:
            report.append((key, old, new, f"skip: common word ({lower_hits})", 0))
            continue

        if old == "Остров Родоса":
            for pattern, replace, form in phrase_rules(
                    "Остров", "Родоса", "Родос", "Айленд", ""):
                rules.append({"pattern": pattern, "replace": replace,
                              "trigger": "Остров", "note": f"Rhodes Island ({form})"})
            report.append((key, old, new, "phrase-head", 0))
            continue

        if " " in old or " " in new:
            pattern = word_re(old)
            rules.append({"pattern": pattern, "replace": new,
                          "trigger": old.split()[0],
                          "note": f"{key} (phrase-exact)"})
            report.append((key, old, new, "phrase-exact", 0))
            continue

        built = rename_rules(old, new)
        if not built:
            report.append((key, old, new, "skip: grammar/gender", 0))
            continue
        stem = PARADIGMS[classify(old)][0]
        trigger = old[:-1] if len(old) > 1 else old
        for pattern, replace, form in built:
            rules.append({"pattern": pattern, "replace": replace,
                          "trigger": trigger, "note": f"{key} ({form})"})
        report.append((key, old, new, "paradigm", 0))

    OUT.write_text(
        json.dumps({"rules": rules}, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8", newline="\n")
    with io.open(REPORT, "w", encoding="utf-8", newline="\n") as handle:
        handle.write("key\told\tnew\tdecision\thits\n")
        for key, old, new, decision, hits in report:
            handle.write(f"{key}\t{old}\t{new}\t{decision}\t{hits}\n")
    applied = [r for r in report if not r[3].startswith("skip")]
    skipped = [r for r in report if r[3].startswith("skip")]
    print(f"changed keys: {len(changed)}, rename rules: {len(rules)} "
          f"({len(applied)} applied, {len(skipped)} skipped)")
    print("skipped (manual review):")
    for key, old, new, decision, _ in skipped:
        print(f"  {decision}\t{key}\t{old} -> {new}")
    print(f"wrote {OUT}")
    print(f"wrote {REPORT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

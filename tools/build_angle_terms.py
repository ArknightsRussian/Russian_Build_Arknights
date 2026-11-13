"""Build the canonical glossary for words inside <...> in translated values.

The game shows a bare ``<Dream Tiles>`` style reference as literal text. It is
not a Unity rich-text tag, so the words stay English unless we translate them.
This script collects every such term from the merged map + gap-fill manifests,
reuses the existing translation of the same word when there is one, and falls
back to ``tools/angle_terms_manual.json`` for names that have no standalone key.

Outputs:
  tools/angle_terms.json   term -> Russian (consumed by build_ru_merged_pack)
  docs/ANGLE_TERMS.md      human-readable glossary
  work/angle_terms_unresolved.tsv  terms still missing a translation

Run: py tools/build_angle_terms.py
"""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MERGED = ROOT / "merged-manifests" / "99_merged.json"
FILL_DIR = ROOT / "ru-manifests"
MANUAL = ROOT / "tools" / "angle_terms_manual.json"
OUT = ROOT / "tools" / "angle_terms.json"
DOCS = ROOT / "docs" / "ANGLE_TERMS.md"
REPORT = ROOT / "work" / "angle_terms_unresolved.tsv"

TAGS = {
    "alpha", "align", "b", "br", "color", "cspace", "font", "i", "indent",
    "line-height", "line-indent", "link", "lowercase", "mark", "material",
    "margin", "mspace", "nobr", "noparse", "page", "pos", "rotate", "s", "size",
    "smallcaps", "space", "sprite", "style", "sub", "sup", "u", "uppercase",
    "voffset", "width",
}
TERM_RE = re.compile(r"<([^<>\r\n]{1,120})>")
LATIN_RE = re.compile(r"[A-Za-z]")
CYRILLIC_RE = re.compile(r"[А-Яа-яЁё]")


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def iter_values():
    if MERGED.is_file():
        yield from load_json(MERGED).values()
    for path in sorted(FILL_DIR.glob("ru_fill_*.json")):
        yield from load_json(path).values()


def lookup_map() -> dict[str, str]:
    """English key -> Russian value, plus fill keys/values for cross-reuse."""
    result: dict[str, str] = {}
    if MERGED.is_file():
        for key, value in load_json(MERGED).items():
            if isinstance(key, str) and isinstance(value, str):
                result.setdefault(key, value)
    for path in sorted(FILL_DIR.glob("ru_fill_*.json")):
        for key, value in load_json(path).items():
            if isinstance(key, str) and isinstance(value, str):
                result.setdefault(key, value)
    folded: dict[str, str] = {}
    for key, value in result.items():
        folded.setdefault(key.casefold(), value)
    return folded


def candidates(term: str):
    """Spellings the runtime/glossary may use for the same term."""
    seen: set[str] = set()

    def add(value: str):
        value = value.strip()
        if value and value not in seen:
            seen.add(value)
            yield value

    plain = term.strip().strip("'\"’‘“”")
    for value in (term, plain):
        yield from add(value)
    yield from add(term.replace("&", "and"))
    yield from add(plain.replace("’", "'"))
    # Stage/chapter counters: "Braving Nature 3", "Braving Nature {0}".
    for pattern in (r"\s+\{\d+\}$", r"\s+\d+$"):
        stripped = re.sub(pattern, "", plain)
        if stripped != plain:
            yield from add(stripped)
    # Plurals.
    for singular in (
        re.sub(r"'s$", "", plain),
        re.sub(r"ies$", "y", plain),
        re.sub(r"men$", "man", plain),
        re.sub(r"es$", "", plain),
        re.sub(r"s$", "", plain),
    ):
        if singular != plain:
            yield from add(singular)


def collect_terms() -> Counter:
    terms: Counter = Counter()
    for value in iter_values():
        if not isinstance(value, str):
            continue
        for match in TERM_RE.finditer(value):
            term = match.group(1).strip()
            if not term or term[0] in "@$#/":
                continue
            if "=" in term or term.lower() in TAGS:
                continue
            if not LATIN_RE.search(term) or CYRILLIC_RE.search(term):
                continue
            if term.startswith(("http", "newsimg")):
                continue
            terms[term] += 1
    return terms


def main() -> int:
    lookups = lookup_map()
    manual = load_json(MANUAL) if MANUAL.is_file() else {}
    manual_folded = {k.casefold(): v for k, v in manual.items()}
    terms = collect_terms()

    resolved: dict[str, str] = {}
    unresolved: list[tuple[int, str]] = []
    for term, count in terms.most_common():
        hit = manual.get(term) or manual_folded.get(term.casefold())
        if not hit:
            for candidate in candidates(term):
                hit = manual.get(candidate) or manual_folded.get(candidate.casefold())
                if not hit:
                    hit = lookups.get(candidate.casefold())
                if hit:
                    break
        # "Condition: Alloy" style compounds reuse the plain word.
        if not hit and term.casefold().startswith("condition: "):
            rest = term.split(":", 1)[1].strip()
            if rest.casefold() in lookups and rest.casefold() not in TAGS:
                hit = "Состояние: " + lookups[rest.casefold()]
        if hit:
            resolved[term] = hit
        else:
            unresolved.append((count, term))

    OUT.write_text(
        json.dumps(dict(sorted(resolved.items(), key=lambda kv: kv[0].casefold())),
                   ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8", newline="\n")

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    with open(REPORT, "w", encoding="utf-8", newline="\n") as handle:
        handle.write("count\tterm\n")
        for count, term in unresolved:
            handle.write(f"{count}\t{term}\n")

    DOCS.parent.mkdir(parents=True, exist_ok=True)
    by_letter: dict[str, list[tuple[str, str]]] = {}
    for term, translation in resolved.items():
        letter = term[0].upper()
        if not letter.isalpha():
            letter = "#"
        by_letter.setdefault(letter, []).append((term, translation))
    lines = [
        "# Слова внутри `<...>` — канонический глоссарий",
        "",
        "Игра показывает ссылки вида `<Dream Tiles>` как обычный текст. "
        "Эти слова переводятся отдельным словарём `tools/angle_terms.json`, "
        "который применяется только внутри угловых скобок и не затрагивает "
        "обычные слова в сюжете.",
        "",
        f"Всего терминов: **{len(terms)}**, переведено: **{len(resolved)}**, "
        f"без перевода: **{len(unresolved)}**.",
        "",
    ]
    for letter in sorted(by_letter):
        lines.append(f"## {letter}")
        lines.append("")
        lines.append("| Оригинал | Перевод |")
        lines.append("| --- | --- |")
        for term, translation in sorted(by_letter[letter],
                                        key=lambda kv: kv[0].casefold()):
            lines.append(f"| `{term}` | {translation} |")
        lines.append("")
    DOCS.write_text("\n".join(lines), encoding="utf-8", newline="\n")

    print(f"terms: {len(terms)}, translated: {len(resolved)}, "
          f"unresolved: {len(unresolved)}")
    for count, term in unresolved[:120]:
        print(f"  {count}\t{term}")
    print(f"wrote {OUT}")
    print(f"wrote {DOCS}")
    print(f"wrote {REPORT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

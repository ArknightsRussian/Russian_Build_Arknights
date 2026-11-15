"""Restore Arknights inline rich-text tags lost during translation.

The EN client wraps important words in tags such as ``<@ba.vup>{atk:0%}</>``
(blue value highlight) or ``<$ba.stun>Stunning</>`` (clickable status tooltip).
Old RU sources kept only the plain text, so the RU client shows no colour and
no tooltip.  This module re-inserts the original tag around the corresponding
translated word.

Only term tags (``<@...>`` / ``<$...>``) are handled; a value is left untouched
when the matching RU word cannot be found with confidence.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

TERM_OPEN = re.compile(r"<([@$][^<>]*)>")
TAG_ANY = re.compile(r"<[^<>]*>")
PLACEHOLDER = re.compile(r"\{[^{}]+\}")
WORD_RE = re.compile(r"[A-Za-zА-Яа-яЁё][A-Za-zА-Яа-яЁё0-9'’\-]*")

# Mechanic tags link to a fixed game status, so the RU word can be found by a
# stem even when the translator used a verb or a different case.
STATUS_STEMS: dict[str, tuple[str, ...]] = {
    "$ba.stun": ("оглуш",),
    "$ba.sluggish": ("замедл",),
    "$ba.barrier": ("барьер",),
    "$ba.invisible": ("невидим",),
    "$ba.cold": ("холод",),
    "$ba.fragile": ("хрупк",),
    "$ba.root": ("связыва", "связыван", "обездвиж"),
    "$ba.protect": ("святилищ",),
    "$ba.dt.element": ("элементальн",),
    "$ba.sleep": ("сон", "спящ", "засыпа", "погружа"),
    "$ba.dt.apoptosis": ("некроз",),
    "$ba.dt.apoptosis2": ("некроз",),
    "$ba.buffres": ("сопротивлен",),
    "$ba.dt.burning": ("ожог", "горен"),
    "$ba.dt.burning2": ("ожог", "горен"),
    "$ba.dt.neural": ("нервн",),
    "$ba.dt.neural2": ("нервн",),
    "$ba.frozen": ("замороз", "заморож", "обморож"),
    "$ba.shield": ("щит",),
    "$ba.levitate": ("левит", "парени", "парит"),
    "$ba.charged": ("заряж",),
    "$ba.palsy": ("паралич",),
    "$ba.mujica": ("мухик", "муджик"),
    "$ba.tremble": ("ужас", "испуг", "страш"),
    "$ba.magicfragile": ("хрупк",),
    "$ba.camou": ("маскиров",),
    "$ba.liftoff": ("взлет", "взлёт"),
    "$ba.steal": ("крад",),
    "$ba.fear": ("страх",),
    "$ba.fever": ("жар",),
    "$ba.dt.erosion": ("коррози",),
    "$ba.dt.erosion2": ("коррози",),
    "$ba.magicpoint": ("ман",),
    "$ba.dying": ("смертельн", "ранен"),
    "$ba.strong": ("бодрост",),
    "$ba.debuff": ("негативн", "ослаблен"),
    "$ba.berserk": ("стойкост",),
    "$ba.float": ("парени", "парит"),
    "$ba.overdrive": ("перегрузк",),
    "$ba.inspire": ("вдохновен",),
    "$ba.elementfragile": ("хрупк",),
    "$ba.weaknessatk": ("слабост",),
    "$ba.dmgresistance": ("снижен",),
    "$ba.alter": ("изменен",),
    "$ba.weaken": ("ослаблен",),
    "$ba.chant": ("пени",),
    "$ba.attract": ("приман", "притяг"),
    "$ba.permanentatk": ("атак",),
}

# Short labels that are not standalone map keys.
EXTRA_TERMS = {
    "condition:": "Условие:",
    "condition": "Условие",
    "environmental conditions:": "Условия окружающей среды:",
    "environmental conditions": "Условия окружающей среды",
    "initial danger:": "Начальный уровень опасности:",
    "starting danger level:": "Начальный уровень опасности:",
    "integrated strategies": "Интегрированные стратегии",
    "arts damage": "урон Искусством",
    "arts": "Искусство",
    "true damage": "истинный урон",
    "physical damage": "физический урон",
    # Intensity adverbs used by pull/push/slow descriptions. They are not
    # standalone map keys, so without these the <@ba.vup> tag is lost on every
    # repeated "moderately"/"greatly"/"slightly".
    "moderately": "умеренно",
    "greatly": "сильно",
    "slightly": "слегка",
}

NOISE_WORDS = {"the", "a", "an", "of", "and", "or", "to", "in", "on", "for", "with", "is", "are"}


@dataclass
class Group:
    tags: list[str]
    inner: str
    raw: str
    start: int
    end: int


def _groups(src: str) -> list[Group]:
    groups: list[Group] = []
    i = 0
    while True:
        m = None
        for m2 in TERM_OPEN.finditer(src, i):
            m = m2
            break
        if m is None:
            break
        close = src.find("</>", m.end())
        if close == -1:
            break
        raw = src[m.end():close]
        nested = TAG_ANY.findall(raw)
        # nested term tags are handled by their own group; skip this outer one
        if any(TERM_OPEN.fullmatch(t) for t in nested) or "</>" in raw:
            i = m.end()
            continue
        inner = TAG_ANY.sub("", raw).strip()
        if not inner and not nested:
            i = close + 3
            continue
        tags = [m.group(0)]
        # consecutive open tags directly before the same text (nested tooltips)
        j = m.start() - 1
        while j >= 0 and src[j] == ">":
            prev = src.rfind("<", 0, j + 1)
            if prev == -1:
                break
            candidate = src[prev:j + 1]
            if not TERM_OPEN.fullmatch(candidate):
                break
            tags.insert(0, candidate)
            j = prev - 1
        # Only <@ba.*> value/mechanic colours are safe in every renderer.
        # <$...> tooltips need UICommentedText (absent in several panels), and
        # <@char.*>/<@lv.*>/<@ro*...> styles are rendered by dedicated widgets;
        # inserting them into plain Text shows raw <color=...> markup.
        tags = [tag for tag in tags if tag.startswith("<@ba.")]
        if not tags:
            i = close + 3
            continue
        groups.append(Group(tags, inner, raw, m.start(), close + 3))
        i = close + 3
    return groups


def _norm(text: str) -> str:
    text = text.replace("«", '"').replace("»", '"').replace("“", '"').replace("”", '"')
    text = text.replace("–", "-").replace("—", "-").replace("ё", "е").replace("Ё", "Е")
    return re.sub(r"\s+", " ", text).strip().lower()


def _words(text: str) -> list[str]:
    return [w for w in WORD_RE.findall(text) if w.lower() not in NOISE_WORDS]


def _mask_tags(text: str) -> str:
    """Blank out ``<...>`` markup while keeping every index stable."""
    return TAG_ANY.sub(lambda m: " " * len(m.group(0)), text)


def _stems(words: list[str]) -> tuple[str, str | None]:
    first = words[0].lower()
    last = words[-1].lower()
    return first[: max(4, min(6, len(first)))], (last[: max(4, min(6, len(last)))] if len(words) > 1 else None)


def _find_word(text: str, stem: str, start: int, stop: int | None = None) -> tuple[int, int] | None:
    pat = re.compile(r"(?<![A-Za-zА-Яа-яЁё0-9])" + re.escape(stem) + r"[A-Za-zА-Яа-яЁё0-9'’\-]*", re.IGNORECASE)
    end = len(text) if stop is None else min(len(text), stop)
    m = pat.search(text, start, end)
    if not m:
        return None
    return m.start(), m.end()


def _find_ru(text: str, candidate: str, start: int) -> tuple[int, int] | None:
    candidate = candidate.strip()
    if not candidate:
        return None
    idx = text.lower().find(candidate.lower(), start)
    if idx != -1:
        return idx, idx + len(candidate)
    # quote/dash-insensitive comparison
    norm_text = _norm(text)
    norm_cand = _norm(candidate)
    if norm_cand and norm_cand != candidate.lower() and len(norm_text) == len(text):
        idx = norm_text.find(norm_cand, start)
        if idx != -1:
            # only safe while normalisation keeps the exact string length
            return idx, idx + len(norm_cand)
    words = _words(candidate)
    if not words:
        return None
    first, last = _stems(words)
    hit = _find_word(text, first, start, None if last is None else start + 160)
    if not hit:
        return None
    if last is None:
        return hit
    second = _find_word(text, last, hit[1], hit[1] + 120)
    if second:
        return hit[0], second[1]
    return hit


class Restorer:
    def __init__(self, merged: dict[str, str]):
        self.merged = merged
        self.terms: dict[str, list[str]] = {}
        self._build_terms()
        self.stats = {"values": 0, "tags": 0, "skipped": 0}

    def _add(self, source: str, target: str) -> None:
        key = _norm(source)
        if not key or not target or TAG_ANY.search(key):
            return
        bucket = self.terms.setdefault(key, [])
        if target not in bucket and len(bucket) < 5:
            bucket.append(target)

    def _build_terms(self) -> None:
        glossary = ROOT / "work" / "GLOSSARY.tsv"
        if glossary.exists():
            for line in glossary.read_text(encoding="utf-8-sig").splitlines()[1:]:
                cells = line.split("\t")
                if len(cells) >= 4 and cells[0] and cells[3]:
                    self._add(cells[0], cells[3])
        for source, target in self.merged.items():
            if not isinstance(target, str):
                continue
            text = source.strip()
            if len(text) > 60 or len(text.split()) > 7:
                continue
            self._add(text, target)
        for source, target in EXTRA_TERMS.items():
            self._add(source, target)

    def lookup(self, inner: str, tag: str) -> list[str]:
        candidates: list[str] = []
        key = _norm(inner)
        if key in self.terms:
            candidates.extend(self.terms[key])
        # simple English inflection fallback
        for suffix, replaced in (("ing", ""), ("ing", "e"), ("ed", ""), ("ed", "e"),
                                 ("es", ""), ("s", ""), ("'s", "")):
            if key.endswith(suffix):
                alt = key[: -len(suffix)] + replaced
                if alt in self.terms:
                    candidates.extend(self.terms[alt])
                    break
        # tag-specific mechanic stems win over dictionary wording
        for stem in STATUS_STEMS.get(tag.lstrip("<").rstrip(">"), ()):
            candidates.append("\u0000" + stem)  # marker: bare stem search
        return candidates

    def _locate(self, dst: str, inner: str, tag: str, start: int,
                strict: bool = False) -> tuple[int, int] | None:
        inner = inner.strip()
        if not inner:
            return None
        mask = _mask_tags(dst)
        literal = inner
        if literal.startswith(("+", "-")) and literal[1:2] == "{":
            literal = literal[1:]
        idx = mask.find(literal, start)
        if idx != -1:
            return idx, idx + len(literal)
        if strict:
            # Long phrases (block/reminder spans) must never be re-anchored by a
            # stray number or a partial word match: that misplaces whole blocks.
            return None
        for token in PLACEHOLDER.findall(inner):
            idx = mask.find(token, start)
            if idx != -1:
                return idx, idx + len(token)
        for number in re.findall(r"\d+(?:[.,]\d+)?%?", inner):
            hit = re.search(r"(?<![\d.,])" + re.escape(number) + r"(?![\d.,])", mask[start:])
            if hit:
                return start + hit.start(), start + hit.end()
        for candidate in self.lookup(inner, tag):
            if candidate.startswith("\u0000"):
                hit = _find_word(mask, candidate[1:], start)
                if hit:
                    return hit
                continue
            hit = _find_ru(mask, candidate, start)
            if hit:
                return hit
        return None

    def _block_span(self, src: str, dst: str, group: Group) -> tuple[int, int] | None:
        plain_src = TAG_ANY.sub("", src).strip()
        if _norm(plain_src) == _norm(group.inner):
            lead = len(dst) - len(dst.lstrip())
            tail = len(dst.rstrip())
            return lead, tail
        src_lines = src.split("\n")
        if len(src_lines) > 1 and len(dst.split("\n")) == len(src_lines):
            needle = _norm(group.inner)
            for i, line in enumerate(src_lines):
                if _norm(TAG_ANY.sub("", line)) == needle:
                    dst_lines = dst.split("\n")
                    offset = sum(len(x) + 1 for x in dst_lines[:i])
                    body = dst_lines[i]
                    lead = len(body) - len(body.lstrip())
                    return offset + lead, offset + len(body.rstrip())
        return None

    def restore(self, src: str, dst: str) -> str:
        if not dst or "<@" in dst or "<$" in dst or "<" not in src:
            return dst
        groups = _groups(src)
        if not groups:
            return dst
        spans: list[tuple[int, int, list[str]]] = []
        cursor = 0
        for group in groups:
            inner = group.inner.strip()
            if not inner:
                continue
            span = None
            if not inner:
                # tag wrapping an already-present entity name, e.g.
                # <@lv.item><Intrusive Call> </>  ->  colour the entity tag
                for entity in TAG_ANY.findall(group.raw):
                    idx = dst.find(entity)
                    if idx != -1:
                        span = (idx, idx + len(entity))
                        break
                if span is None:
                    self.stats["skipped"] += 1
                    continue
            else:
                plain_inner = TAG_ANY.sub("", inner)
                strict = len(plain_inner) > 40 or len(_words(plain_inner)) > 5
                is_status = group.tags[-1].startswith("<$")
                if strict and not is_status:
                    span = self._block_span(src, dst, group)
                    if span is None:
                        span = self._locate(dst, inner, group.tags[-1], cursor, strict=True)
                else:
                    span = self._block_span(src, dst, group)
                    if span is None:
                        span = self._locate(dst, inner, group.tags[-1], cursor)
                    if span is None:
                        span = self._locate(dst, inner, group.tags[-1], 0)
            if span is None:
                self.stats["skipped"] += 1
                continue
            if span[0] < 0 or span[1] <= span[0]:
                continue
            spans.append((span[0], span[1], group.tags))
            cursor = span[1]
        if not spans:
            return dst
        # keep narrower spans, drop overlaps
        spans.sort(key=lambda s: (s[0], s[1] - s[0]))
        kept: list[tuple[int, int, list[str]]] = []
        for span in spans:
            if kept and span[0] < kept[-1][1]:
                continue
            kept.append(span)
        out = []
        pos = 0
        for start, end, tags in kept:
            out.append(dst[pos:start])
            out.append("".join(tags))
            out.append(dst[start:end])
            out.append("</>")
            pos = end
        out.append(dst[pos:])
        self.stats["tags"] += len(kept)
        return "".join(out)

    def run(self) -> int:
        changed = 0
        for src, dst in list(self.merged.items()):
            if not isinstance(dst, str) or "<" not in src:
                continue
            new = self.restore(src, dst)
            if new != dst:
                self.merged[src] = new
                changed += 1
        self.stats["values"] = changed
        return changed


def apply_rich_tags(merged: dict[str, str]) -> int:
    restorer = Restorer(merged)
    changed = restorer.run()
    print(f"rich tags restored: {changed} values, {restorer.stats['tags']} tags, "
          f"{restorer.stats['skipped']} unresolved")
    return changed

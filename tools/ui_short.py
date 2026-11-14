"""Shorten UI labels and unify a few names that the glossary does not cover.

Called from ``tools/build_ru_merged_pack.py`` and ``arklocalizer/custom_pack.py``
after the per-file overrides, so it also sees values added by the story TSV and
friends' tables.

The rewrites are deliberately narrow:

* ``Иммунитет к X`` -> ``НЕУЯЗ. к X`` only for short status labels (the enemy
  info resistance row). Prose keeps the full word.
* ``Элитный N`` -> ``Элита N`` for the promotion/level label.
* ``Монста`` declensions -> the indeclinable canon ``Мон3тр``.
* ``нейросеть`` -> ``нейромодуль`` (the ingame term for the network).
* ``L.G.D`` -> ``Д.О.Л``.
* ``СОМ``/``СОП`` + RES placeholder -> the established ``СОПР``.
"""
from __future__ import annotations

import re

_IMMUNITY = re.compile(r"^Иммунитет к (?=\S)")
_IMMUNITY_SKIP = ("большинств", "контролирующ", "негативн", "эффектам,")
_ELITE = re.compile(r"\bЭлитный (?=\d)")
_MON3TR = re.compile(r"\bМонст(?:а|у|е|ой|ою|ы)\b")
_LGD = re.compile(r"L\.\s?G\.\s?D\.?")

_NEURAL_PHRASES = (
    ("к нейросети", "к нейромодулю"),
    ("К нейросети", "К нейромодулю"),
)
_NEURAL_WORDS = {
    "нейросеть": "нейромодуль",
    "нейросети": "нейромодуля",
    "нейросетью": "нейромодулем",
    "нейросетевого": "нейромодульного",
    "нейросетевому": "нейромодульному",
    "нейросетевым": "нейромодульным",
    "нейросетевом": "нейромодульном",
    "нейросетевая": "нейромодульная",
    "нейросетевой": "нейромодульной",
    "нейросетевые": "нейромодульные",
    "нейросетевых": "нейромодульных",
    "нейросетевыми": "нейромодульными",
}
_NEURAL = re.compile(r"\b[Нн]ейросет\w*")


def _same_case(source: str, replacement: str) -> str:
    if source[:1].isupper():
        return replacement[:1].upper() + replacement[1:]
    return replacement


def _neural(match: re.Match[str]) -> str:
    word = match.group(0)
    replacement = _NEURAL_WORDS.get(word.lower())
    return _same_case(word, replacement) if replacement else word


def rewrite(value: str) -> str:
    """Return ``value`` with the short-UI substitutions applied."""
    if not value:
        return value

    stripped = value.strip()
    if (stripped.startswith("Иммунитет к ")
            and len(stripped) <= 52
            and "{" not in stripped
            and not any(skip in stripped.lower() for skip in _IMMUNITY_SKIP)):
        value = _IMMUNITY.sub("НЕУЯЗ. к ", value, count=1)

    value = _ELITE.sub("Элита ", value)
    value = _MON3TR.sub("Мон3тр", value)

    for source, target in _NEURAL_PHRASES:
        value = value.replace(source, target)
    value = _NEURAL.sub(_neural, value)

    value = _LGD.sub("Д.О.Л.", value)

    # The skill stat row uses three-letter abbreviations. Older sources left
    # "СОМ"/"СОП" (or the full phrase) next to the RES placeholder.
    if "{magic_resistance}" in value:
        value = value.replace("СОМ +<@ba.vup>{magic_resistance}",
                              "СОПР +<@ba.vup>{magic_resistance}")
        value = value.replace("СОП +<@ba.vup>{magic_resistance}",
                              "СОПР +<@ba.vup>{magic_resistance}")
        value = value.replace("Сопротивление искусству +{magic_resistance}",
                              "СОПР +{magic_resistance}")
        value = value.replace("Сопротивление +{magic_resistance}",
                              "СОПР +{magic_resistance}")

    return value

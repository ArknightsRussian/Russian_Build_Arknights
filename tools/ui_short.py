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
_IMMUNITY_WORDS = (
    ("Оглушению", "Оглуш."), ("Оглушение", "Оглуш."),
    ("Заморозке", "Замор."), ("Заморозка", "Замор."),
    ("Замедлению", "Замедл."), ("Замедление", "Замедл."),
    ("Левитации", "Левит."), ("Левитация", "Левит."),
    ("параличу", "Парал."), ("Паралич", "Парал."),
    ("приманке", "Приман."), ("Приманка", "Приман."),
    ("контролю", "Контр."), ("Контроль", "Контр."),
    ("эффектам Трясины", "Тряс."), ("Трясины", "Тряс."),
    ("Сну", "Сон"), ("Страху", "Страх"), ("Ужасу", "Ужас"),
)
_ELITE = re.compile(r"\bЭлитный (?=\d)")
# "Модули открываются на Элитном 2" -> "на Элите 2". Only adjective forms
# directly followed by a promotion number are rewritten; "элитный враг" and
# "Элитный оперативник" keep their normal Russian declension.
_ELITE_NUM = re.compile(r"\bЭлитн(?:ом|ому|ой|ым)\s+(?=\d|\{)")
_ELITE_GEN = re.compile(r"\bЭлитного\s+(?=\d|\{)")
_ELITE_EN = re.compile(r"\bElite\s+(?=\d)")
_MON3TR = re.compile(r"\bМонст(?:а|у|е|ой|ою|ы)\b")
# The game and the RU source use both Latin L.G.D. and Cyrillic Л. Г. Д.
# spellings. Both must become the accepted community abbreviation.
_LGD = re.compile(r"(?:L\.\s?G\.\s?D\.?|Л\.\s?Г\.\s?Д\.?)", re.I)
_LATIN_STATS = (
    (re.compile(r"\bHP\b"), "ХП"),
    (re.compile(r"\bATK\b"), "АТК"),
)
# ОЗ (очки здоровья) and ХП are the same stat. The community glossary uses ХП.
_HP_RU = re.compile(r"(?<![А-Яа-яЁё])ОЗ(?![А-Яа-яЁё])")
_RANK = re.compile(r"\bRANK\b")
# Skill points are "очки навыков" in the community glossary. The game and the
# RU source use both the Latin SP and the Cyrillic СП abbreviation.
_SKILL_POINTS = re.compile(r"(?<![A-Za-zА-Яа-яЁё])[SС][PР](?![A-Za-zА-Яа-яЁё])")
# "SP" is plural ("очки навыков"), so the adjectives that the old translations
# agreed with the singular acronym must become plural.
_SP_AGREEMENT = (
    ("стартовая ОН", "стартовые ОН"), ("стартовой ОН", "стартовых ОН"),
    ("стартового ОН", "стартовых ОН"), ("стартовый ОН", "стартовые ОН"),
    ("стартовое ОН", "стартовые ОН"),
    ("дополнительное ОН", "дополнительные ОН"),
    ("дополнительный ОН", "дополнительные ОН"),
    ("дополнительная ОН", "дополнительные ОН"),
    ("дополнительного ОН", "дополнительных ОН"),
    ("полном ОН", "полных ОН"),
    ("Увеличена стартовые ОН", "Повышены стартовые ОН"),
    ("увеличена стартовые ОН", "повышены стартовые ОН"),
)
# "ОВ" is plural as well ("очки высадки"), so the same agreement fixes apply.
_OV_AGREEMENT = (
    ("стартовая ОВ", "стартовые ОВ"), ("стартовой ОВ", "стартовых ОВ"),
    ("стартового ОВ", "стартовых ОВ"), ("стартовый ОВ", "стартовые ОВ"),
    ("стартовое ОВ", "стартовые ОВ"), ("стартовому ОВ", "стартовым ОВ"),
    ("начальная ОВ", "начальные ОВ"), ("начальной ОВ", "начальных ОВ"),
    ("начального ОВ", "начальных ОВ"), ("начальный ОВ", "начальные ОВ"),
    ("начальное ОВ", "начальные ОВ"),
)
# The promotion badge is assembled in code as "Elite 2Level60" (no space).
_ELITE_LEVEL = re.compile(r"\bElite\s*(\d)\s*Level\s*(\d+)", re.I)
# Some old drafts spell the skill points out instead of using the acronym.
_SP_LONG = re.compile(
    r"очк(?:о|а|ов|и|у|ом|ами)?\s+навык(?:а|ов|у|ом|ами)?", re.I)
_SP_DOUBLE = re.compile(r"ОН\s*\((?:ОН|[Оо]чки навыков)\)")
# The status-effect row already uses "НЕУЯЗ."; the new canon is a colon.
_UNAVAILABLE = re.compile(r"НЕУЯЗ\.\s*")
# Seconds are abbreviated with the short "с." everywhere in the UI.
_SECONDS = re.compile(r"(?<![А-Яа-яЁёA-Za-z])сек\.")
# Deployment points are "очки высадки" in the community glossary.
_DEPLOY_POINTS = re.compile(r"(?<![A-Za-zА-Яа-яЁё])(?:DP|ДП)(?![A-Za-zА-Яа-яЁё])")
# "дроп" is gamer slang; the UI calls these rewards.
_DROP_PHRASES = (
    ("Редкий дроп", "Редкая награда"), ("редкий дроп", "редкая награда"),
    ("Удачный дроп", "Удачная награда"), ("удачный дроп", "удачная награда"),
    ("Связанный дроп", "Связанная награда"),
    ("Дополнительные дропы", "Дополнительные награды"),
    ("Обычные дропы", "Обычные награды"),
    ("Особые дропы", "Особые награды"),
)
_DROP_WORDS = (
    ("дропами", "наградами"), ("дропы", "награды"), ("дропов", "наград"),
    ("дропа", "награды"), ("дропу", "награде"), ("дропом", "наградой"),
    ("Дропами", "Наградами"), ("Дропы", "Награды"), ("Дропов", "Наград"),
    ("Дропа", "Награды"), ("Дропу", "Награде"), ("Дропом", "Наградой"),
)
_DROP_LEFT = re.compile(r"(?<![А-Яа-яЁё])[Дд]роп(?![А-Яа-яЁё])")
# "Наем" is the noun "hiring"; the correct spelling is "наём".
_NAEM = re.compile(r"(?<![А-Яа-яЁё])[Нн]аем(?![А-Яа-яЁё])")
# Enemy/banner names that the glossary does not cover. Bracketed ones keep
# their brackets (the same convention as <Term>), so the text stays italic.
_BRACKET_PHRASES = (
    ("[Woe of Extinction]", "[Горе истребления]"),
    ("[Sword and Hammer of Olden Days]", "[Меч и молот минувших дней]"),
    ("[Standard Headhunting]", "[Стандартный наем]"),
    ("[Limited Headhunting]", "[Лимитный наем]"),
    ("[Special Headhunting]", "[Особый наем]"),
    ("[Kernel Headhunting]", "[Наем «Ядра»]"),
    ("[Newbie Pool]", "[Наем новичка]"),
)
# One spelling per mechanic/boss unit.
_NAME_FIXES = (
    ("OpFor:", "Противник:"),
    ("Armor Cleaver", "Расколыватель брони"),
    ("Armor Crusher", "Крушитель брони"),
    ("Раскол доспеха", "Расколыватель брони"),
    ("Крушитель доспеха", "Крушитель брони"),
    ("Пробиватель брони", "Пронзатель брони"),
    ("Восстановление ОВ при блокировке", "Восстановление ОН при блокировке"),
)
# Compression for narrow skill/talent cards. Only unambiguous patterns.
_ASPD_COMPRESS = re.compile(r"[Сс]корость атаки(?=\s*[+\-−])")
_DAMAGE_COMPRESS = re.compile(r"(урон[а]?) в размере ([^\s,.;]+) от АТК")

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
        value = _IMMUNITY.sub("НЕУЯЗ: ", value, count=1)
        for source, target in _IMMUNITY_WORDS:
            value = value.replace(source, target)

    value = _ELITE.sub("Элита ", value)
    value = _ELITE_NUM.sub("Элите ", value)
    value = _ELITE_GEN.sub("Элиты ", value)
    value = _ELITE_EN.sub("Элита ", value)
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
        value = value.replace("СОМ +{magic_resistance}",
                              "СОПР +{magic_resistance}")
        value = value.replace("СОП +{magic_resistance}",
                              "СОПР +{magic_resistance}")
        value = value.replace("Сопротивление искусству +{magic_resistance}",
                              "СОПР +{magic_resistance}")
        value = value.replace("Сопротивление +{magic_resistance}",
                              "СОПР +{magic_resistance}")

    for pattern, target in _LATIN_STATS:
        value = pattern.sub(target, value)
    value = _HP_RU.sub("ХП", value)
    value = _RANK.sub("РАНГ", value)
    value = _SKILL_POINTS.sub("ОН", value)
    value = _SP_LONG.sub("ОН", value)
    value = _SP_DOUBLE.sub("ОН", value)
    for source, target in _SP_AGREEMENT:
        value = value.replace(source, target)
    for source, target in _OV_AGREEMENT:
        value = value.replace(source, target)
    value = _ELITE_LEVEL.sub(lambda m: f"Элита {m.group(1)} Ур. {m.group(2)}", value)

    value = _UNAVAILABLE.sub("НЕУЯЗ: ", value)
    value = _SECONDS.sub("с.", value)
    value = _DEPLOY_POINTS.sub("ОВ", value)
    # DP may arrive inside a value ("+3 стартовой DP"), so fix the agreement
    # after it has been turned into ОВ.
    for source, target in _OV_AGREEMENT:
        value = value.replace(source, target)

    for source, target in _BRACKET_PHRASES:
        value = value.replace(source, target)
    value = _NAEM.sub(lambda m: "Наём" if m.group(0)[0].isupper() else "наём", value)
    for source, target in _NAME_FIXES:
        value = value.replace(source, target)

    value = _ASPD_COMPRESS.sub("СКОР", value)
    value = _DAMAGE_COMPRESS.sub(r"\1 \2 АТК", value)

    for source, target in _DROP_PHRASES:
        value = value.replace(source, target)
    for source, target in _DROP_WORDS:
        value = value.replace(source, target)
    value = _DROP_LEFT.sub("награда", value)

    return value

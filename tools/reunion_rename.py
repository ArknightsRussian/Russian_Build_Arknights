"""Rewrite the Reunion organisation as the neuter name "Воссоединение".

The community glossary renamed the faction, but the old wording is masculine
("Реюнион был", "Реюнион захватил"), while the canonical name is neuter
("Воссоединение было", "Воссоединение захватило").  A plain string replace
leaves the verb and adjective agreement masculine, so this module also fixes
the words that agree with the name.

The rewrite is deliberately conservative: only the modifiers directly before
the name and a short predicate chain after it are touched.  The chain stops at
a sentence boundary, a dash, a capitalised proper noun or a noun that may be a
new subject, which keeps the predicates of other characters intact.
"Движение/силы Реюнион" appositions become the genitive "… Воссоединения",
as Russian names movements.
"""
from __future__ import annotations

import re

NOUN_FORMS = [
    ("Реюнионами", "Воссоединениями"),
    ("Реюнионах", "Воссоединениях"),
    ("Реюнионам", "Воссоединениям"),
    ("Реюнионов", "Воссоединений"),
    ("Реюнионы", "Воссоединения"),
    ("Реюнионом", "Воссоединением"),
    ("Реюниону", "Воссоединению"),
    ("Реюниона", "Воссоединения"),
    ("Реюнионе", "Воссоединении"),
    ("Реюнион", "Воссоединение"),
]

NOUN_RE = re.compile(
    r"(?<![А-Яа-яЁё])(" + "|".join(re.escape(old) for old, _ in NOUN_FORMS) +
    r")(?![А-Яа-яЁё])")
MAP = dict(NOUN_FORMS)

# Governing nouns after which the name is used as a genitive modifier.
GOVERNING_GENITIVE = {
    "движение", "движения", "движению", "движением", "движении",
    "движенье", "движенья", "движенью", "движеньем",
    "сила", "силы", "силе", "силу", "силой", "силою",
    "сил", "силам", "силами", "силах",
    "имя", "имени", "именем", "именах",
    "название", "названия", "названию", "названием", "названии",
    "лидер", "лидера", "лидеру", "лидером", "лидере", "лидеры",
    "лидеров", "лидерам", "лидерами", "лидерах",
    "командир", "командира", "командиру", "командиром", "командиры",
    "командиров", "командирам", "командирами", "командирах",
    "боец", "бойца", "бойцу", "бойцом", "бойце", "бойцы",
    "бойцов", "бойцам", "бойцами", "бойцах",
    "член", "члена", "члену", "членом", "члене", "члены",
    "членов", "членам", "членами", "членах",
    "отряд", "отряда", "отряду", "отрядом", "отряде", "отряды",
    "отрядов", "отрядам", "отрядами", "отрядах",
    "подразделение", "подразделения", "подразделению",
    "подразделением", "подразделении", "подразделений",
    "подразделениям", "подразделениями", "подразделениях",
    "укрытие", "укрытия", "укрытию", "укрытием", "укрытии",
    "укрытий", "укрытиям", "укрытиями", "укрытиях",
    "ряды", "рядов", "рядам", "рядами", "рядах", "ряде",
    "части", "частей", "частям", "частями", "частях",
    "войска", "войск", "войскам", "войсками", "войсках",
    "сторонники", "сторонников", "сторонникам", "сторонниками",
    "представители", "представителей", "представителям",
    "представителями", "остатки", "остатков", "остаткам",
    "остатками", "остатках",
}

# Nouns in the instrumental or an oblique plural case take the name as a
# genitive modifier ("лидером Воссоединения", "силами Воссоединения").
OBLIQUE_ENDINGS = ("ами", "ями", "ов", "ев", "ом", "ем", "ой", "ей")

# Masculine short forms and irregular past-tense verbs (zero ending).
ZERO_FORMS = {
    "был": "было", "мог": "могло", "смог": "смогло", "погиб": "погибло",
    "умер": "умерло", "пришёл": "пришло", "пришел": "пришло",
    "ушёл": "ушло", "ушел": "ушло", "перешёл": "перешло",
    "перешел": "перешло", "прошёл": "прошло", "прошел": "прошло",
    "нашёл": "нашло", "нашел": "нашло", "зашёл": "зашло", "зашел": "зашло",
    "вышел": "вышло", "вошёл": "вошло", "вошел": "вошло",
    "дошёл": "дошло", "дошел": "дошло", "обошёл": "обошло",
    "обошел": "обошло", "подошёл": "подошло", "подошел": "подошло",
    "отошёл": "отошло", "отошел": "отошло", "сошёл": "сошло",
    "сошел": "сошло", "шёл": "шло", "шел": "шло",
    "рос": "росло", "нёс": "несло", "нес": "несло", "вёл": "вело",
    "лег": "легло", "лёг": "легло", "помог": "помогло", "мёр": "мерло",
    "мер": "мерло", "замер": "замерло", "возник": "возникло",
    "таков": "таково", "должен": "должно", "готов": "готово",
    "уверен": "уверено", "намерен": "намерено", "способен": "способно",
    "прав": "право", "виноват": "виновато", "мёртв": "мертво",
    "мертв": "мертво", "жив": "живо", "силён": "сильно",
    "силен": "сильно", "слаб": "слабо", "опасен": "опасно",
    "жесток": "жестоко", "страшен": "страшно", "нужен": "нужно",
    "следовал": "следовало", "пал": "пало", "дал": "дало",
    "стал": "стало", "взял": "взяло", "вторгся": "вторглось",
    "ворвался": "ворвалось", "пробрался": "пробралось",
    "вмешался": "вмешалось", "разобрался": "разобралось",
    "справился": "справилось", "основан": "основано",
    "создан": "создано", "образован": "образовано",
    "построен": "построено", "разрушен": "разрушено",
    "уничтожен": "уничтожено", "захвачен": "захвачено",
    "ослаблен": "ослаблено", "установлен": "установлено",
    "разгромлен": "разгромлено", "вынужден": "вынуждено",
    "зажёг": "зажгло", "зажег": "зажгло", "сжёг": "сожгло",
    "сжег": "сожгло", "поджёг": "подожгло", "поджег": "подожгло",
    "каков": "каково", "манипулирован": "манипулировано",
    "ведомый": "ведомое", "злонамерен": "злонамеренно",
    "самонадеян": "самонадеянно", "неуверен": "неуверенно",
    "обречён": "обречено", "обречен": "обречено",
}

# Masculine pronouns/adjectives that can precede the name and must agree.
MODIFIERS = {
    "он": "оно", "сам": "само", "весь": "всё", "наш": "наше", "ваш": "ваше",
    "этот": "это", "тот": "то", "каждый": "каждое", "такой": "такое",
    "который": "которое", "мой": "моё", "твой": "твоё", "свой": "своё",
    "новый": "новое", "старый": "старое", "целый": "целое",
    "Викторианский": "Викторианское", "Возродившийся": "Возродившееся",
    "неожиданный": "неожиданное", "прежний": "прежнее",
    "нынешний": "нынешнее", "здешний": "здешнее",
    "последний": "последнее", "легендарный": "легендарное",
    "настоящий": "настоящее", "долгожданный": "долгожданное",
    "семейный": "семейное", "Тёплый": "Тёплое", "Проклятый": "Проклятое",
}

# Adverbs and particles that may sit between the subject and its predicate.
ADVERBS = {
    "уже", "всё", "все", "снова", "действительно", "здесь", "просто",
    "лишь", "только", "всегда", "раньше", "теперь", "ещё", "еще", "тоже",
    "довольно", "якобы", "специально", "внезапно", "наконец", "сначала",
    "сейчас", "тогда", "потом", "вновь", "опять", "обычно", "вероятно",
    "возможно", "определённо", "наверное", "похоже", "видимо", "конечно",
    "буквально", "почти", "немного", "напротив", "очевидно", "даже",
    "именно", "не", "ни", "бы", "ли", "же", "ведь", "вот", "это", "как",
    "по-прежнему", "ныне", "нынче", "пока", "разве", "изначально",
    "постепенно", "полностью", "окончательно", "фактически", "впервые",
    "недавно", "давно", "основательно", "внезапно", "непременно",
    "потому", "поэтому", "затем", "после", "сразу", "вдруг",
}

CONJUNCTIONS = {"и", "а", "но", "да", "или", "либо", "чтобы", "что"}

PREPOSITIONS = {
    "в", "во", "на", "за", "под", "над", "из", "от", "до", "для", "к",
    "ко", "по", "с", "со", "о", "об", "обо", "при", "без", "у", "про",
    "через", "сквозь", "между", "перед", "ради", "вокруг", "около",
    "благодаря", "согласно", "вопреки", "навстречу",
}

POSSESSIVE = {"его", "её", "ее", "их", "наш", "наша", "наше", "наши",
              "ваш", "ваша", "ваше", "ваши", "свой", "своя", "своё", "свои",
              "мой", "моя", "моё", "мои", "твой", "твоя", "твоё", "твои",
              "моего", "моей", "моих", "моею", "твоего", "твоей", "твоих",
              "своего", "своей", "своих", "нашего", "нашей", "наших",
              "вашего", "вашей", "ваших"}

OBJECT_PRONOUNS = {"меня", "тебя", "нас", "вас", "себя", "его", "её", "ее",
                   "их", "ему", "ей", "им", "нам", "вам", "мне", "тебе"}

QUANTIFIERS = {"несколько", "много", "мало", "немало", "большинство",
               "часть", "ряд", "тысячи", "сотни", "десятки", "всех",
               "все", "многих", "некоторых", "столько", "сколько",
               "больше", "меньше", "множество", "куча"}

STOP_PRONOUNS = {"кто", "я", "ты", "вы", "они", "она"}

# Nouns ending in -л that must not be treated as past-tense verbs.
NOUN_L = {
    "символ", "стол", "узел", "предел", "канал", "финал", "идеал",
    "материал", "капитал", "персонал", "сигнал", "журнал", "зал", "вал",
    "бал", "тыл", "угол", "укол", "орел", "орёл", "козёл", "козел",
    "сокол", "футбол", "трибунал", "арсенал", "фестиваль", "телеканал",
    "интервал", "жезл", "мер", "отдел", "провал", "предел", "горизонт",
    "уровень",
}

TOKEN_RE = re.compile(r"[А-Яа-яЁё][А-Яа-яЁё-]*|[^\sА-Яа-яЁё]+")
BOUNDARY = set(".!?…;\n")


def _is_governing(word: str) -> bool:
    low = word.lower()
    if low in {"чем", "как"}:
        return False
    if low in GOVERNING_GENITIVE:
        return True
    if low in ZERO_FORMS or low.endswith(("л", "лся", "ть", "ться")):
        return False
    return low.endswith(OBLIQUE_ENDINGS)


def _neuter_verb(word: str, capitalization: bool = True) -> str | None:
    low = word.lower()
    if low in ZERO_FORMS:
        return ZERO_FORMS[low]
    # Inverted subject: only motion verbs can precede the name.
    if low in {"шёл", "шел", "следовал"}:
        return ZERO_FORMS.get(low)
    if low.endswith("лся") and len(low) > 5:
        return word[:-3] + "лось"
    if low.endswith("ёл") and len(low) > 4:
        return word[:-2] + "ло"
    if low.endswith("л") and len(low) >= 3 and not low.endswith("лл") \
            and low not in NOUN_L:
        return word + "о"
    return None


def _neuter_modifier(word: str) -> str | None:
    if word in MODIFIERS:
        return MODIFIERS[word]
    low = word.lower()
    if low in MODIFIERS:
        fixed = MODIFIERS[low]
        if word[:1].isupper():
            fixed = fixed[:1].upper() + fixed[1:]
        return fixed
    # Adjectives directly before a name: -ский/-цкий -> -ское, -ый/-ой -> -ое.
    if word.endswith(("ский", "цкий")):
        return word[:-2] + "ое"
    if word.endswith("щий"):
        return word[:-2] + "ее"
    if word.endswith("ый"):
        return word[:-2] + "ое"
    if word.endswith("ой") and len(word) > 4:
        return word[:-2] + "ое"
    return None


def _rewrite_segment(value: str) -> str:
    """Replace every occurrence of the faction name and fix its clause."""
    out: list[str] = []
    pos = 0
    for m in NOUN_RE.finditer(value):
        old = m.group(0)
        if m.start() < pos:
            continue
        before = value[:m.start()]
        words = list(re.finditer(r"[А-Яа-яЁё][А-Яа-яЁё-]*", before))
        # Agreement and case are decided inside the current sentence only.
        cut = 0
        for i in range(len(before) - 1, -1, -1):
            if before[i] in BOUNDARY:
                cut = i + 1
                break
        sentence_words = [w for w in words if w.start() >= cut]
        prev_word = sentence_words[-1].group(0) if sentence_words else ""
        prev2_word = sentence_words[-2].group(0) if len(sentence_words) > 1 else ""
        genitive = old == "Реюнион" and _is_governing(prev_word)
        # "деревня под названием «Воссоединение»": the apposition stays in the
        # nominative, unlike "имя Воссоединения".
        if prev_word.lower() in {"названием", "именем", "названии", "имени"} \
                and prev2_word.lower() in {"под", "по", "об"}:
            genitive = False
        new = "Воссоединения" if genitive else MAP[old]

        chunk = value[pos:m.start()]
        if not genitive:
            chunk = _fix_prefix(chunk, words, pos)
        out.append(chunk)
        out.append(new)

        # Only a bare nominative/accusative "Реюнион" can be the subject of the
        # following predicate.  Oblique forms ("члена Реюниона", "с Реюнионом")
        # never control the agreement of the clause, and an object after a verb
        # or an infinitive does not either.
        low_prev = prev_word.lower()
        motion = low_prev in {"шёл", "шел", "следовал"}
        object_verb = (not motion and
                       (low_prev in ZERO_FORMS or low_prev.endswith("лся") or
                        (low_prev.endswith("л") and low_prev not in NOUN_L)))
        subject = (old == "Реюнион" and
                   low_prev not in GOVERNING_GENITIVE and
                   low_prev not in PREPOSITIONS and
                   not low_prev.endswith(("ть", "ться")) and
                   not object_verb)

        tail_start = m.end()
        tail_end = len(value)
        for i in range(tail_start, len(value)):
            if value[i] in BOUNDARY:
                tail_end = i
                break
        # Never scan past the next occurrence of the name: it belongs to the
        # next match and must be renamed independently.
        later = NOUN_RE.search(value, tail_start)
        if later is not None and later.start() < tail_end:
            tail_end = later.start()
        tail = value[tail_start:tail_end]
        ends_at_name = later is not None and later.start() == tail_end
        out.append(_fix_tail(tail, ends_at_name=ends_at_name and not genitive)
                   if subject else tail)
        pos = tail_end

    out.append(value[pos:])
    return "".join(out)


def _fix_prefix(chunk: str, words, offset: int) -> str:
    """Make the modifiers that directly precede the name neuter."""
    # Walk back over contiguous words without punctuation between them.
    fixed_words: list[tuple[int, int, str]] = []
    end = len(chunk)
    for i in range(len(words) - 1, max(-1, len(words) - 4), -1):
        wm = words[i]
        start = wm.start() - offset
        stop = wm.end() - offset
        if not (0 <= start and stop <= len(chunk)):
            break
        gap = chunk[stop:end]
        if gap.strip(" \t"):
            break  # punctuation or quote between the words: separate clause
        word = wm.group(0)
        low = word.lower()
        if i == len(words) - 1 and (low in ZERO_FORMS or
                                    low in {"шёл", "шел", "следовал"}):
            fixed = _neuter_verb(word)
        else:
            fixed = _neuter_modifier(word)
        if fixed is None:
            # Adjective by ending, but only in the nominative singular.
            if not word.endswith(("ый", "ий", "ой")):
                break
        if fixed and fixed != word:
            fixed_words.append((start, stop, fixed))
        end = start
    for start, stop, fixed in reversed(fixed_words):
        chunk = chunk[:start] + fixed + chunk[stop:]
    return chunk


def _fix_tail(tail: str, ends_at_name: bool = False) -> str:
    if not tail:
        return tail
    tokens = list(TOKEN_RE.finditer(tail))
    replacements: list[tuple[int, int, str]] = []
    started = False
    prev = ""
    for t in tokens:
        w = t.group(0)
        if t.start() > 120:
            break
        if not re.match(r"[А-Яа-яЁё]", w):
            if w.strip() == "—":
                # "…, а потому он …" refers back to the same subject.
                rest = tail[t.end():]
                if re.match(r"\s*(?:и\s+)?потому\b", rest):
                    prev = "потому"
                    continue
                break
            continue
        low = w.lower()
        if low in STOP_PRONOUNS:
            break
        if low in ADVERBS:
            prev = low
            continue

        # A capitalised word inside the sentence is a proper name: an oblique
        # object may pass, but a new nominative subject ends the chain.
        if w[0].isupper():
            if not started and (prev in PREPOSITIONS or prev in POSSESSIVE):
                prev = low
                continue
            if started and low.endswith(("а", "я", "у", "ю", "и", "ы", "е")):
                prev = low
                continue
            break

        fixed = _neuter_verb(w)
        if fixed is None and low == "он":
            fixed = "оно"
        if fixed is not None and fixed != w:
            replacements.append((t.start(), t.end(), fixed))
            started = True
            prev = low
            continue

        if not started:
            prev = low
            continue

        if low in CONJUNCTIONS or low in POSSESSIVE or low in PREPOSITIONS \
                or low in OBJECT_PRONOUNS or low in QUANTIFIERS:
            prev = low
            continue

        # Adjectives, participles and their oblique forms describe an object
        # of the predicate, so the predicate chain may continue past them.
        if low.endswith(("ыми", "ими", "ого", "ому", "ым", "ых", "ая", "ое",
                         "ые", "ую", "ей", "его", "ему", "ом", "ой", "ий",
                         "ый", "ею", "ою", "ами", "ями", "ах", "ям",
                         "ам", "ов", "ев", "ием", "иях", "иям")):
            prev = low
            continue
        # Infinitives may sit between the auxiliary and the predicate.
        if low.endswith(("ть", "ться")):
            prev = low
            continue
        # Participles that agree with the subject keep their adjective ending.
        if low.endswith(("вший", "ший", "мый", "емый", "имый", "нный",
                         "тый", "жный")):
            fixed = _neuter_modifier(w)
            if fixed and fixed != w:
                replacements.append((t.start(), t.end(), fixed))
                prev = low
                continue
        # A plain noun after the predicate starts a new clause.
        if prev in PREPOSITIONS or prev in POSSESSIVE or prev in QUANTIFIERS:
            prev = low
            continue
        break

    if not replacements:
        result = tail
    else:
        result = tail
        for start, end, fixed in reversed(replacements):
            result = result[:start] + fixed + result[end:]
    if ends_at_name:
        # The next word is the faction name, so trailing modifiers must agree
        # with it as well.
        words = list(re.finditer(r"[А-Яа-яЁё][А-Яа-яЁё-]*", result))
        result = _fix_prefix(result, words, 0)
    return result


def rewrite(value: str) -> str:
    """Return the value with the faction renamed and agreement fixed."""
    if "Реюнион" not in value:
        return value
    return _rewrite_segment(value)

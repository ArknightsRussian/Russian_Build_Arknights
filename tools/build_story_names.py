"""Build Russian name plates for every story speaker.

Sources, highest priority first:
  1. ``tools/story_name_overrides.json``  -- hand-checked NPC spellings
  2. ``ru-overrides/05_glossary_names.json`` -- operator glossary (Google Sheets)
  3. automatic practical transliteration for the long tail

The result is written to ``ru-overrides/10_story_names.json``. Keys are the
exact ``[name="..."]`` values, so XUnity matches only the name plate itself and
never rewrites the same word inside a sentence.

Run AFTER tools/import_glossary.py and BEFORE tools/build_ru_merged_pack.py:
    py tools/build_story_names.py
"""
from __future__ import annotations

import glob
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STORY_DIR = ROOT / "work" / "client-hot1105" / "decoded" / "dyn" / "gamedata" / "story"
OVERRIDES = ROOT / "tools" / "story_name_overrides.json"
GLOSSARY = ROOT / "ru-overrides" / "05_glossary_names.json"
OUT = ROOT / "ru-overrides" / "10_story_names.json"
INVENTORY = ROOT / "work" / "story_speaker_names.json"

NAME_RE = re.compile(r'\[name="([^"]*)"\]')
LATIN_RE = re.compile(r"[A-Za-z]")
CYR_RE = re.compile(r"[А-Яа-яЁё]")
WORD_RE = re.compile(r"[A-Za-zÀ-ÿĀ-ž'’]+")

# Ordered digraphs: longest first.
DIGRAPHS: list[tuple[str, str]] = [
    ("shch", "щ"), ("sch", "ш"), ("tch", "ч"), ("sci", "си"), ("sce", "се"),
    ("ch", "ч"), ("sh", "ш"), ("zh", "ж"), ("kh", "х"), ("th", "т"),
    ("ph", "ф"), ("gh", "г"), ("ck", "к"), ("qu", "кв"), ("ts", "ц"),
    ("ya", "я"), ("yu", "ю"), ("yo", "ё"), ("ye", "е"), ("yi", "и"),
    ("ee", "и"), ("ea", "и"), ("oo", "у"), ("ou", "оу"), ("oa", "о"),
    ("oe", "о"), ("ai", "ай"), ("ay", "эй"), ("ey", "ей"), ("oy", "ой"),
    ("oi", "ой"), ("au", "ау"), ("aw", "о"), ("ew", "ью"), ("ow", "оу"),
]

SINGLE = {
    "a": "а", "b": "б", "d": "д", "e": "е", "f": "ф", "h": "х", "i": "и",
    "j": "дж", "k": "к", "l": "л", "m": "м", "n": "н", "o": "о", "p": "п",
    "q": "к", "r": "р", "s": "с", "t": "т", "u": "у", "v": "в", "w": "в",
    "x": "кс", "z": "з", "y": "и",
}
SPECIAL = {
    "à": "а", "á": "а", "â": "а", "ä": "е", "å": "о", "æ": "э", "ç": "с",
    "č": "ч", "ć": "ць", "đ": "дж", "é": "е", "è": "е", "ê": "е", "ë": "ё",
    "í": "и", "ì": "и", "î": "и", "ï": "и", "ł": "л", "ñ": "нь", "ń": "нь",
    "ó": "о", "ò": "о", "ô": "о", "ö": "ё", "ø": "ё", "œ": "ё", "ř": "рж",
    "ś": "сь", "š": "ш", "ß": "сс", "ú": "у", "ù": "у", "û": "у", "ü": "ю",
    "ý": "и", "ż": "ж", "ź": "зь", "ž": "ж", "ą": "а", "ę": "ен",
}
VOWELS = set("aeiouyàáâäåæéèêëíìîïóòôöøœúùûüý")

# ---------------------------------------------------------------------------
# Common speaker-label vocabulary. Without this, descriptive names such as
# "Excited Young Man" turn into gibberish ("Эксйтед Ёунг Мэн"). Proper nouns
# that are not listed here still go through transliteration.
# ---------------------------------------------------------------------------
DICT: dict[str, str] = {
    # articles / prepositions / conjunctions
    "a": "", "an": "", "the": "", "of": "", "and": "и", "in": "в", "on": "на",
    "to": "к", "by": "у", "from": "из", "outside": "снаружи", "behind": "позади",
    "with": "с", "at": "у", "for": "для", "not": "не", "no": "нет", "very": "очень",
    # people / roles
    "voice": "голос", "voices": "голоса", "man": "мужчина", "men": "мужчины",
    "woman": "женщина", "women": "женщины", "soldier": "солдат", "soldiers": "солдаты",
    "operator": "оперативник", "operators": "оперативники", "infected": "заражённый",
    "member": "член", "members": "члены", "guard": "страж", "guards": "стражи",
    "villager": "селянин", "villagers": "селяне", "officer": "офицер",
    "officers": "офицеры", "worker": "рабочий", "workers": "рабочие",
    "tourist": "турист", "tourists": "туристы", "passerby": "прохожий",
    "girl": "девушка", "girls": "девушки", "noble": "дворянин", "nobles": "дворяне",
    "child": "ребёнок", "children": "дети", "citizen": "гражданин",
    "citizens": "граждане", "knight": "рыцарь", "knights": "рыцари",
    "mercenary": "наёмник", "mercenaries": "наёмники", "resident": "житель",
    "residents": "жители", "staff": "персонал", "sailor": "моряк",
    "sailors": "моряки", "male": "мужчина", "female": "женщина",
    "student": "студент", "students": "студенты", "miner": "шахтёр",
    "miners": "шахтёры", "owner": "владелец", "warrior": "воин",
    "warriors": "воины", "youth": "юноша", "farmer": "фермер",
    "farmers": "фермеры", "employee": "сотрудник", "employees": "сотрудники",
    "merchant": "торговец", "merchants": "торговцы", "townsfolk": "горожане",
    "townsperson": "горожанин", "researcher": "исследователь",
    "mafioso": "мафиози", "boy": "мальчик", "boys": "мальчики",
    "squad": "отряд", "reporter": "репортёр", "bandit": "бандит",
    "bandits": "бандиты", "hunter": "охотник", "hunters": "охотники",
    "security": "охрана", "clan": "клан", "elder": "старейшина",
    "elders": "старейшины", "civilian": "гражданский", "inhabitant": "житель",
    "inhabitants": "жители", "patrol": "патруль", "creature": "создание",
    "patient": "пациент", "patients": "пациенты", "shop": "магазин",
    "crowd": "толпа", "captain": "капитан", "official": "чиновник",
    "refugee": "беженец", "refugees": "беженцы", "court": "двор",
    "priest": "жрец", "lady": "дама", "leader": "лидер", "servant": "слуга",
    "messenger": "посланник", "fan": "фанат", "fans": "фанаты",
    "clerk": "клерк", "customer": "покупатель", "customers": "покупатели",
    "prisoner": "заключённый", "prisoners": "заключённые",
    "spectator": "зритель", "spectators": "зрители", "section": "секция",
    "cleric": "клирик", "driver": "водитель", "gang": "банда",
    "representative": "представитель", "manager": "управляющий",
    "audience": "публика", "team": "команда", "apprentice": "ученик",
    "street": "улица", "visitor": "посетитель", "visitors": "посетители",
    "assassin": "убийца", "factory": "фабрика", "father": "отец",
    "mother": "мать", "caster": "заклинатель", "casters": "заклинатели",
    "logistics": "логистика", "broadcast": "трансляция", "boss": "босс",
    "medic": "медик", "traveler": "путешественник", "agent": "агент",
    "community": "община", "bounty": "награда", "doctor": "врач",
    "shopkeeper": "лавочник", "assistant": "помощник", "cultist": "культист",
    "cultists": "культисты", "stall": "лоток", "engineering": "инженерный",
    "subordinate": "подчинённый", "zone": "зона", "contestant": "участник",
    "trader": "торговец", "attendant": "слуга", "burdenbeast": "вьючный зверь",
    "entity": "сущность", "pioneer": "первопроходец", "artist": "художник",
    "vendor": "продавец", "guest": "гость", "guests": "гости", "chef": "повар",
    "ninja": "ниндзя", "wastelander": "житель пустошей",
    "bodyguard": "телохранитель", "union": "союз", "lab": "лаборатория",
    "hawker": "лоточник", "scholar": "учёный", "supervisor": "руководитель",
    "bank": "банк", "participant": "участник", "person": "человек",
    "people": "люди", "office": "офис", "shaman": "шаман", "scout": "разведчик",
    "monster": "монстр", "veteran": "ветеран", "juror": "присяжный",
    "battalion": "батальон", "thug": "бандит", "judge": "судья",
    "streamer": "стример", "unit": "подразделение", "intern": "стажёр",
    "defender": "защитник", "chief": "глава", "waiter": "официант",
    "sound": "звук", "casino": "казино", "alert": "тревога", "kid": "ребёнок",
    "kids": "дети", "shadow": "тень", "commoner": "простолюдин",
    "director": "директор", "peddler": "коробейник", "musician": "музыкант",
    "king": "король", "sea": "море", "teacher": "учитель", "tech": "техник",
    "armor": "броня", "machine": "машина", "technician": "техник",
    "nurse": "медсестра", "secretary": "секретарь", "councilor": "советник",
    # adjectives
    "young": "молодой", "old": "старый", "elderly": "пожилой",
    "excited": "взволнованный", "angry": "злой", "anxious": "обеспокоенный",
    "calm": "спокойный", "curious": "любопытный", "nervous": "нервный",
    "strange": "странный", "local": "местный", "tired": "усталый",
    "panicked": "паникующий", "frightened": "испуганный",
    "worried": "обеспокоенный", "injured": "раненый", "dressed": "одетый",
    "passing": "проходящий", "mysterious": "таинственный",
    "impatient": "нетерпеливый", "flustered": "растерянный",
    "silent": "молчаливый", "serious": "серьёзный", "gentle": "кроткий",
    "timid": "робкий", "happy": "счастливый", "royal": "королевский",
    "wounded": "раненый", "enthusiastic": "восторженный",
    "cheerful": "весёлый", "terrified": "в ужасе", "quiet": "тихий",
    "agitated": "взволнованный", "solemn": "торжественный",
    "panicking": "паникующий", "cautious": "осторожный", "little": "маленький",
    "surprised": "удивлённый", "exhausted": "измождённый", "stern": "суровый",
    "busy": "занятый", "eager": "нетерпеливый", "confused": "сбитый с толку",
    "feeble": "слабый", "kind": "добрый", "dying": "умирающий",
    "friendly": "дружелюбный", "skeptical": "скептический",
    "unhappy": "несчастный", "indifferent": "равнодушный",
    "passionate": "страстный", "spectating": "наблюдающий",
    "familiar": "знакомый", "frantic": "неистовый", "drunken": "пьяный",
    "lively": "живой", "patrolling": "патрулирующий", "armed": "вооружённый",
    "haggard": "измождённый", "senior": "старший", "fierce": "свирепый",
    "arrogant": "высокомерный", "big": "большой", "black": "чёрный",
    "all": "весь", "hesitant": "нерешительный", "broken": "сломленный",
    "suspicious": "подозрительный", "composed": "собранный",
    "cold": "холодный", "astute": "проницательный", "lead": "ведущий",
    "depressed": "подавленный", "alert": "бдительный", "distant": "далёкий",
    "ordinary": "обычный", "unfamiliar": "незнакомый", "weary": "усталый",
    "reserved": "сдержанный", "elegant": "элегантный", "pious": "благочестивый",
    "tipsy": "подвыпивший", "kindly": "добрый", "longer": "дольше",
    "looking": "смотрящий", "watching": "наблюдающий", "waiting": "ждущий",
    # races / nations / factions
    "sarkaz": "сарказский", "durin": "дюрин", "kjerag": "кьеранский",
    "lateran": "латеранский", "victorian": "викторианский", "ursus": "урсский",
    "columbian": "колумбийский", "taran": "таранский",
    "leithanian": "лейтанийский", "ægir": "эгирский", "sami": "сами",
    "lungmen": "лунмэнский", "londinium": "лондиниумский",
    "reunion": "Reunion", "blacksteel": "Blacksteel", "rhine": "Rhine",
    "rhodes": "Родос", "island": "остров", "shanhaizhong": "Шаньхайчжун",
    "tianshi": "Тяньши", "yeti": "Йети", "armorless": "бездоспешный",
    "browntail": "Браунтейл", "paleroche": "Пейлрош", "yumen": "Юмэнь",
    "silverash": "Сильверхэш", "rim": "Рим", "billiton": "Биллайтон",
    "emperors": "Императорские", "emperor": "Император",
    "corporate": "корпоративный", "blacksteel": "Blacksteel",
    # more adjectives seen in speaker labels
    "apathetic": "апатичный", "ardent": "пламенный", "apprehensive": "обеспокоенный",
    "apologetic": "извиняющийся", "aloof": "отстранённый", "bored": "скучающий",
    "sad": "грустный", "concerned": "обеспокоенный", "joyful": "радостный",
    "shrewd": "проницательный", "helpless": "беспомощный", "chatty": "болтливый",
    "mischievous": "озорной", "cheering": "ликующий", "amiable": "приветливый",
    "sickly": "болезненный", "greedy": "жадный", "bewildered": "растерянный",
    "diligent": "старательный", "scared": "испуганный", "perplexed": "озадаченный",
    "stubborn": "упрямый", "indistinct": "невнятный", "onlooking": "наблюдающий",
    "bold": "смелый", "seasoned": "опытный", "aged": "пожилой",
    "astonished": "изумлённый", "scathing": "язвительный", "masked": "скрытный",
    "jittery": "нервный", "relaxed": "расслабленный", "leisurely": "неторопливый",
    "courteous": "учтивый", "carefree": "беспечный", "spirited": "живой",
    "dazed": "ошеломлённый", "vicious": "злобный", "restless": "неугомонный",
    "lost": "потерянный", "tall": "высокий", "shy": "застенчивый",
    "furious": "разъярённый", "wary": "настороженный", "brave": "смелый",
    "determined": "решительный", "meticulous": "дотошный", "pained": "страдающий",
    "humble": "скромный", "loud": "громкий", "wealthy": "богатый",
    "startled": "испуганный", "hoarse": "хриплый", "noisy": "шумный",
    "annoyed": "раздражённый", "proud": "гордый", "vigilant": "бдительный",
    "cheery": "весёлый", "merry": "весёлый", "warm": "тёплый", "sedate": "степенный",
    "rowdy": "буйный", "faint": "слабый", "sickly": "болезненный",
    # more nouns
    "police": "полиция", "yakuza": "якудза", "field": "полевой", "door": "дверь",
    "radio": "радио", "hr": "HR", "sandbeast": "песчаный зверь",
    "dublinn": "Дублинн", "control": "контроль", "minister": "министр",
    "banshee": "банши", "diner": "закусочная", "feline": "фелин",
    "tester": "испытатель", "town": "город", "village": "деревня",
    "grand": "великий", "kazimierzian": "казимирский", "craftsman": "ремесленник",
    "noblewoman": "дворянка", "communicator": "переговорщик", "neighbor": "сосед",
    "sister": "сестра", "caravan": "караван", "ink": "чернила", "spirit": "дух",
    "announcement": "объявление", "hospital": "больница", "ambassador": "посол",
    "duke": "герцог", "head": "глава", "defense": "защита", "metal": "металл",
    "martial": "боевой", "imperial": "имперский", "truck": "грузовик",
    "government": "правительство", "babel": "Вавилон",
    "confessarius": "исповедник", "former": "бывший", "company": "компания",
    "mandarin": "мандарин", "dragon": "дракон", "uncle": "дядя",
    "ursine": "урсский", "fist": "кулак", "engineer": "инженер",
    "city": "город", "news": "новости", "rep": "представитель",
    "spokesman": "представитель", "left": "левый", "darkness": "тьма",
    "subject": "подданный", "vine": "лоза", "bead": "бусина",
    "ceremony": "церемония", "teahouse": "чайная", "window": "окно",
    "passenger": "пассажир", "legatus": "легат", "military": "военный",
    "slum": "трущобы", "sentry": "часовой", "power": "сила", "bar": "бар",
    "foreign": "иностранный", "warehouse": "склад", "station": "станция",
    "works": "завод", "museum": "музей", "party": "отряд",
    "famiglia": "семья", "ministry": "министерство", "mobster": "гангстер",
    "guerrilla": "партизан", "herd": "стадо", "house": "дом",
    "exhibition": "выставка", "suit": "костюм", "hooligan": "хулиган",
    "militiaman": "ополченец", "television": "телевидение",
    "jailer": "тюремщик", "bartender": "бармен", "dweller": "житель",
    "nobleman": "дворянин", "store": "магазин", "post": "пост",
    "stranger": "незнакомец", "hall": "зал", "singer": "певец",
    "rock": "камень", "mountain": "гора", "seaborn": "сиборн",
    "originium": "оригиниум", "sargonian": "саргонский", "minoan": "минойский",
    "senshi": "сэнси", "mobber": "погромщик", "dweller": "житель",
    "mr": "мистер", "mrs": "миссис", "ms": "мисс", "dr": "доктор",
    "lt": "лейтенант", "col": "полковник", "capt": "капитан",
    "spokeswoman": "представительница", "squadmember": "член отряда",
    "deathless": "бессмертный", "devouring": "пожирающий", "snake": "змея",
    "silent": "молчаливый", "sand": "песчаный", "handy": "умелый",
    "nameless": "безымянный", "ordinary": "обычный", "street": "улица",
    "corner": "угол", "institute": "институт", "facility": "объект",
    "management": "управление", "for": "для", "now": "сейчас",
}

# Single-word labels that are roles, not personal names. Anything else with
# one word is treated as a proper name and transliterated.
SINGLE_AS_ROLE = {
    "bishop", "priest", "drunkard", "child", "villager", "guard", "soldier",
    "doctor", "nurse", "judge", "teacher", "student", "worker", "merchant",
    "messenger", "assassin", "hunter", "sailor", "miner", "farmer", "clerk",
    "manager", "driver", "chef", "waiter", "artist", "musician", "scholar",
    "researcher", "supervisor", "director", "secretary", "councilor", "noble",
    "knight", "warrior", "youth", "boy", "girl", "woman", "man", "officer",
    "official", "prisoner", "refugee", "resident", "citizen", "elder",
    "leader", "servant", "patient", "visitor", "guest", "customer", "vendor",
    "trader", "shopkeeper", "infector", "infested", "passerby", "tourist",
}


def _translit_word(word: str) -> str:
    text = word.replace("’", "'").replace("‘", "'")
    # Apostrophes in names are elisions (Ch'en, Duq'arael): drop them.
    text = text.replace("'", "")
    lower = text.lower()
    out: list[str] = []
    i = 0
    while i < len(text):
        matched = False
        for src, dst in DIGRAPHS:
            if lower.startswith(src, i):
                piece = dst
                if text[i].isupper():
                    piece = piece[:1].upper() + piece[1:]
                out.append(piece)
                i += len(src)
                matched = True
                break
        if matched:
            continue
        ch = text[i]
        low = ch.lower()
        nxt = lower[i + 1] if i + 1 < len(lower) else ""
        piece: str | None = None
        if low in SINGLE:
            piece = SINGLE[low]
        elif low == "c":
            piece = "с" if nxt in "eiy" else "к"
        elif low == "g":
            piece = "дж" if nxt in "eiy" else "г"
        elif low in SPECIAL:
            piece = SPECIAL[low]
        if piece is None:
            out.append(ch)
        else:
            if ch.isupper():
                piece = piece[:1].upper() + piece[1:]
            out.append(piece)
        i += 1

    result = "".join(out)
    # Word-initial "e" is "э" in Russian transcription (Elliot, Enis, ...).
    if text[:1].lower() == "e" and not lower.startswith(("ee", "ea", "ey")):
        result = "Э" + result[1:] if result[:1].isupper() else "э" + result[1:]
    # Silent final -e after a consonant (Clare, Adele) — keep a readable stem.
    if lower.endswith("e") and len(text) > 3 and lower[-2] not in VOWELS and result[-1].lower() == "е":
        result = result[:-1]
    return result


def transliterate(name: str) -> str:
    def repl(match: re.Match[str]) -> str:
        return _translit_word(match.group(0))

    return WORD_RE.sub(repl, name)


PHRASE_FIXES = [
    ("Rhine лаборатория", "Rhine Lab"),
    ("Родос остров", "Остров Родоса"),
    ("Родос Остров", "Остров Родоса"),
    ("Остров Родоса страж", "Страж Острова Родоса"),
    ("Остров Родоса полевой оперативник", "Полевой оперативник Острова Родоса"),
    ("Остров Родоса оперативник", "Оперативник Острова Родоса"),
    ("Союз бездоспешный", "Союз бездоспешных"),
]


def _singular(word: str) -> str:
    if word.endswith("ies") and len(word) > 4:
        return word[:-3] + "y"
    if word.endswith("es") and word[:-2] in DICT:
        return word[:-2]
    if word.endswith("s") and word[:-1] in DICT:
        return word[:-1]
    return word


def _lookup_word(word: str) -> str | None:
    low = word.lower().strip("'’\"")
    if low.endswith("'s") or low.endswith("’s"):
        low = low[:-2]
    if low in DICT:
        return DICT[low]
    base = _singular(low)
    if base in DICT:
        return DICT[base]
    return None


def translate_phrase(name: str) -> str:
    """Translate descriptive labels, transliterate anything unknown.

    A one-word label is a personal name unless it is a known role, so
    "Bishop" becomes "Епископ" while "Picale" becomes "Пикал".
    """
    stripped = name.strip()
    if len(stripped) >= 2 and stripped[0] in "'\"" and stripped[-1] == stripped[0]:
        inner = translate_phrase(stripped[1:-1]).strip("«»")
        return "«" + inner + "»"

    words = list(WORD_RE.finditer(name))
    if not words:
        return name
    if len(words) == 1:
        word = words[0].group(0)
        if word.lower() in SINGLE_AS_ROLE:
            value = _lookup_word(word)
            if value:
                return value[:1].upper() + value[1:]
        return transliterate(word)

    out: list[str] = []
    last = 0
    for match in words:
        out.append(name[last:match.start()])
        word = match.group(0)
        if len(word) == 1 and word.isalpha():
            out.append(word.upper())
        else:
            value = _lookup_word(word)
            if value is not None:
                out.append(value)
            else:
                out.append(transliterate(word))
        last = match.end()
    out.append(name[last:])

    text = re.sub(r"[ \t]+", " ", "".join(out)).strip()
    for src, dst in PHRASE_FIXES:
        text = text.replace(src, dst)
    if text:
        text = text[:1].upper() + text[1:]
    return text


def _skip_candidate(name: str) -> bool:
    if not name.strip():
        return True
    if not LATIN_RE.search(name):
        return True  # already Cyrillic, numeric-only or punctuation
    # Keep all-caps abbreviations (W, PRTS, D.D.D., L.G.D.) as they are.
    letters = [c for c in name if c.isalpha()]
    if len(letters) >= 2 and all(c.isupper() for c in letters):
        return True
    return False


def collect_speakers() -> dict[str, int]:
    counts: dict[str, int] = {}
    for path in glob.glob(str(STORY_DIR / "**" / "*.txt"), recursive=True):
        try:
            text = Path(path).read_text(encoding="utf-8-sig")
        except (OSError, UnicodeDecodeError):
            continue
        for match in NAME_RE.finditer(text):
            name = match.group(1)
            counts[name] = counts.get(name, 0) + 1
    return counts


def main() -> int:
    counts = collect_speakers()
    if not counts:
        raise SystemExit(f"no story speakers found under {STORY_DIR}")
    INVENTORY.write_text(json.dumps(counts, ensure_ascii=False, indent=1) + "\n",
                         encoding="utf-8", newline="\n")

    manual = json.loads(OVERRIDES.read_text(encoding="utf-8-sig"))
    glossary = {}
    if GLOSSARY.is_file():
        glossary = json.loads(GLOSSARY.read_text(encoding="utf-8-sig"))
    manual = {k: v for k, v in manual.items() if not k.startswith("_")}

    result: dict[str, str] = {}
    stats = {"manual": 0, "glossary": 0, "translit": 0, "skipped": 0}
    for name in sorted(counts):
        if _skip_candidate(name):
            stats["skipped"] += 1
            continue
        if name in manual:
            value = manual[name]
            stats["manual"] += 1
        elif name in glossary:
            value = glossary[name]
            stats["glossary"] += 1
        else:
            value = translate_phrase(name)
            stats["translit"] += 1
        if not value or value == name or not CYR_RE.search(value):
            stats["skipped"] += 1
            continue
        result[name] = value

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=1) + "\n",
                   encoding="utf-8", newline="\n")
    print(f"story speakers: {len(counts)} unique, {sum(counts.values())} occurrences")
    print(f"names written: {len(result)} -> {OUT}")
    print("  manual {manual}, glossary {glossary}, translit {translit}, skipped {skipped}".format(**stats))

    unused = sorted(set(manual) - set(counts))
    if unused:
        print(f"manual overrides not used by this story set: {len(unused)}")
        print("  " + ", ".join(unused[:30]) + (" ..." if len(unused) > 30 else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Build the hybrid RU translation map for the launcher hook archive.

Priority (highest first):
  1. user's hand overrides    RUKAMI/*.txt + ru-overrides/*.json
  2. friend's new ru_txt      D:\ARKRUBUILD3\ru_txt (manual RU, 06.11.2026)
  3. user's existing pack     ru-manifests-all/99_all.json  (contains the user's later fixes)
  4. user's AI TSV            work/translated_1-521504.tsv  (fills keys absent from 99_all only)
  5. friend's extra strings   ARKRUBUILD2 runtime en-zh .txt (gaps only, RU values only)

The result is a single frozen manifest directory (merged-manifests/99_merged.json)
that is fed to arklocalizer's build-custom-pack. load_merged applies ru-overrides and
work/13_names_from_ids.json again, which keeps the result consistent with the user's
normal pipeline.

Run:  py tools/build_ru_merged_pack.py
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FRIEND = Path(r"D:\ARKRUBUILD2")
sys.path.insert(0, str(ROOT))

from arklocalizer.custom_pack import (  # noqa: E402
    HAN_RE, MACRO_RE, _canon_source, _extract_pairs, _macro_tokens,
    _strip_tags, _unwrap_quotes, strip_display_tags,
)
from arklocalizer.util import (  # noqa: E402
    RICH_TEXT_TAG_RE, normalize_lookup_text, placeholder_counter, write_json,
)
from arklocalizer.xunity import decode_translation_line  # noqa: E402
from rich_tags import apply_rich_tags  # noqa: E402

TSV = ROOT / "work" / "translated_1-521504.tsv"
BASE = ROOT / "ru-manifests-all" / "99_all.json"
OUT_DIR = ROOT / "merged-manifests"
OUT = OUT_DIR / "99_merged.json"
CACHE = OUT_DIR / ".build_cache.json"

FRIEND_TXT = FRIEND / "runtime" / "en-zh-offline-final" / "BepInEx" / "Translation" / "ru" / "Text"
FRIEND_FILES = ["20_tables.txt", "25_ru_extra.txt"]

# The friend's new toolkit (D:\ARKRUBUILD3) keeps a manually edited RU source
# ("EN=RU" text files, one per operator, updated 06.11.2026). It is applied
# after 99_all/TSV (so it replaces the older AI wording) but BEFORE RUKAMI and
# ru-overrides, which stay the user's final say.
FRIEND_RU_TXT = Path(r"D:\ARKRUBUILD3\ru_txt")
FRIEND_REPORT = ROOT / "work" / "friend_merge_report.tsv"

# Gap-fill manifests produced from the display audit (2026-11-09). They may
# only ADD keys that the merged map does not already cover, so hand-checked
# and friend translations always win.
FILL_DIR = ROOT / "ru-manifests"


def _detagged(counter: Counter) -> Counter:
    return Counter({k: v for k, v in counter.items()
                    if not (isinstance(k, str) and RICH_TEXT_TAG_RE.fullmatch(k))})


def clean(s_raw: str, t_raw: str):
    """Same normalization/validation load_merged applies, so output is final."""
    s = _canon_source(normalize_lookup_text(s_raw))
    t = t_raw.strip()
    if not s or not t or s == t:
        return None
    t = _unwrap_quotes(s, t)
    t = strip_display_tags(t)
    if not t or s == t or HAN_RE.search(t):
        return None
    if _detagged(placeholder_counter(s)) != _detagged(placeholder_counter(t)):
        if Counter(_macro_tokens(s)) != Counter(_macro_tokens(t)) or not MACRO_RE.search(s):
            return None
    return s, t


def read_tsv() -> dict[str, str]:
    counters: dict[str, Counter] = {}
    rows = 0
    with open(TSV, encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f, delimiter="\t")
        next(reader, None)
        for row in reader:
            rows += 1
            if len(row) < 2:
                continue
            hit = clean(row[0], row[1])
            if hit:
                s, t = hit
                counters.setdefault(s, Counter())[t] += 1
    result = {s: c.most_common(1)[0][0] for s, c in counters.items()}
    print(f"TSV: {rows} rows -> {len(result)} usable EN (multi-RU keys: "
          f"{sum(1 for c in counters.values() if len(c) > 1)})")
    return result


def read_friend_txt() -> dict[str, str]:
    result: dict[str, str] = {}
    for name in FRIEND_FILES:
        path = FRIEND_TXT / name
        if not path.is_file():
            print("friend txt missing:", path)
            continue
        kept = 0
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            if not line or line.startswith("//"):
                continue
            pair = decode_translation_line(line)
            if not pair or not pair[1].strip():
                continue
            hit = clean(*pair)
            if hit:
                s, t = hit
                if s not in result:
                    result[s] = t
                    kept += 1
        print(f"friend {name}: {kept} usable gap-fill entries")
    return result


def read_friend_ru_txt() -> dict[str, str]:
    """Parse D:\\ARKRUBUILD3\\ru_txt\\*.txt ("EN=RU", # comments, \\n escapes)."""
    result: dict[str, str] = {}
    if not FRIEND_RU_TXT.is_dir():
        print("friend ru_txt missing:", FRIEND_RU_TXT)
        return result
    rows = 0
    for path in sorted(FRIEND_RU_TXT.glob("*.txt")):
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            if "=" not in line:
                continue
            src, dst = line.split("=", 1)
            rows += 1
            hit = clean(src.replace("\\n", "\n"), dst.replace("\\n", "\n"))
            if hit:
                result.setdefault(hit[0], hit[1])
    print(f"friend ru_txt: {rows} rows -> {len(result)} usable entries ({FRIEND_RU_TXT})")
    return result


def apply_friend(friend: dict[str, str], merged: dict[str, str]) -> int:
    """Apply the friend's entries and keep display variants in sync.

    The map carries several spellings of one runtime string (raw tags, tags
    stripped, normalized). If only the raw key is updated, the pack builder
    later sees the stale stripped twin and drops one of the two as a conflict,
    which can resurrect the old wording. Update a variant only when it held
    exactly the old value, so unrelated keys are untouched.
    """
    replaced = 0
    for src, dst in friend.items():
        old = merged.get(src)
        if old == dst:
            continue
        if old is not None:
            replaced += 1
        merged[src] = dst
        if old is None:
            continue
        for variant in variant_keys(src):
            if variant == src or merged.get(variant) != old:
                continue
            merged[variant] = dst
    return replaced


def variant_keys(text: str):
    seen: set[str] = set()
    for base in (text, strip_display_tags(text), _strip_tags(text)):
        for value in (base, normalize_lookup_text(base),
                      _canon_source(normalize_lookup_text(base))):
            if value and value not in seen:
                seen.add(value)
                yield value


def write_friend_report(friend: dict[str, str], before: dict[str, str]) -> None:
    """Side-by-side list of every value the friend's source changes."""
    lines = ["kind\tEN\tours\tfriend"]
    changed = 0
    for src, dst in sorted(friend.items()):
        old = before.get(src)
        if old == dst:
            continue
        kind = "new" if old is None else "replace"
        changed += 1
        lines.append("\t".join((kind, src.replace("\n", "\\n"),
                                "" if old is None else old.replace("\n", "\\n"),
                                dst.replace("\n", "\\n"))))
    FRIEND_REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    print(f"friend merge report: {changed} changed -> {FRIEND_REPORT}")


def read_rukami() -> dict[str, str]:
    result: dict[str, str] = {}
    for path in sorted((ROOT / "RUKAMI").glob("*.txt")):
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            line = line.rstrip("\n")
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            idx = line.rfind("=")
            if idx <= 0:
                continue
            src, dst = line[:idx], line[idx + 1:]
            if not src.strip() or not dst.strip():
                idx = line.find("=")
                src, dst = line[:idx], line[idx + 1:]
            if not src.strip() or not dst.strip():
                continue
            src = src.replace("\\n", "\n").replace("\\r", "\n")
            dst = dst.replace("\\n", "\n").replace("\\r", "\n")
            hit = clean(src, dst)
            if hit:
                s, t = hit
                result.setdefault(s, t)
    print(f"RUKAMI: {len(result)} usable entries")
    return result


def read_overrides() -> dict[str, str]:
    """Read every ``ru-overrides/*.json``.

    Files are applied in name order, except that ``00_*.json`` (the user's own
    hand fixes) is always applied last so it remains the final say even when a
    generated glossary file sorts after it.
    """
    result: dict[str, str] = {}
    paths = sorted((ROOT / "ru-overrides").glob("*.json"))
    paths = [p for p in paths if not p.name.startswith("00_")] + \
            [p for p in paths if p.name.startswith("00_")]
    for path in paths:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        added = 0
        for src, dst in _extract_pairs(data, path.name):
            hit = clean(src, str(dst))
            if hit:
                s, t = hit
                result[s] = t
                added += 1
        print(f"  override {path.name}: {added} entries")
    print(f"ru-overrides: {len(result)} usable entries")
    return result


def read_name_variants() -> list[tuple[re.Pattern[str], str]]:
    path = ROOT / "tools" / "name_variants.json"
    if not path.is_file():
        return []
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    rules = []
    for item in data.get("rules", []):
        pattern = re.compile(item["pattern"])
        rules.append((pattern, item["replace"]))
    print(f"name variants: {len(rules)} rewrite rules")
    return rules


def apply_name_variants(merged: dict[str, str],
                        rules: list[tuple[re.Pattern[str], str]]) -> int:
    """Rewrite known bad name declensions inside every translation value."""
    if not rules:
        return 0
    changed = 0
    for key, value in merged.items():
        new_value = value
        for pattern, replacement in rules:
            new_value = pattern.sub(replacement, new_value)
        if new_value != value:
            merged[key] = new_value
            changed += 1
    return changed


SAMI_RE = re.compile(r"(?<![А-Яа-яЁё])Сами(?![А-Яа-яЁё])")
SANITY_NUM_RE = re.compile(r"(\d+)\s+Санити")
SANITY_RULES = [
    (re.compile(r"Лишний Санити"), "Лишний рассудок"),
    (re.compile(r"Санити (вернётся|возвратится|восстановится)"), r"рассудок \1"),
    (re.compile(r"Санити восстановится"), "Рассудок восстановится"),
    (re.compile(r"Санити будет возвращено"), "Рассудок будет возвращён"),
    (re.compile(r"(Восстанавливает|восстанавливает|восполняет|тратит|расходует|"
                r"вернёт|возвращает|даёт|дает|не расходует|не тратит|"
                r"тратящие|не тратящие)\s+Санити"), r"\1 рассудок"),
    (re.compile(r"подзаряжать Санити"), "подзаряжать рассудком"),
    (re.compile(r"(восстановлени[яе]|поддержани[яе]|уровня|стоимостью|ценой|"
                r"запас[ау]?|остаток|концентрат|зелье|зелий|ампул[ыа]?|"
                r"пробоотборник[аи]?|пробники|усилитель|расходники|"
                r"трат[аы]|нехватк[аи]|избыток)\s+Санити"), r"\1 рассудка"),
]


def _sanity_number(match: re.Match[str]) -> str:
    value = int(match.group(1))
    word = "рассудок" if value % 10 == 1 and value % 100 != 11 else "рассудка"
    return f"{match.group(1)} {word}"


AUTO_PHRASES = [
    (re.compile(r"Полное авторазвёртывание прокси"), "Полный прокси-автобой"),
    (re.compile(r"полное автопрокси-развёртывание"), "полный прокси-автобой"),
    (re.compile(r"Полного прокси-авторазвертывания"), "полного прокси-автобоя"),
    (re.compile(r"Полное прокси-авторазвертывание"), "полный прокси-автобой"),
    (re.compile(r"разовое автоматическое развёртывание полного прокси"),
     "разовый полный прокси-автобой"),
    (re.compile(r"автоматическое развёртывание полного прокси"),
     "полный прокси-автобой"),
    (re.compile(r"текущее (?:А|а)вто-?разв[её]рт[ыи]вание"), "текущий автобой"),
    (re.compile(r"текущее авторазвёртывание"), "текущий автобой"),
    (re.compile(r"сбой в автоматическом развёртывании"), "сбой автобоя"),
    (re.compile(r"Автоматическое развёртывание"), "Автобой"),
    (re.compile(r"автоматическое развёртывание"), "автобой"),
    (re.compile(r"Автоматическом развёртывании"), "автобое"),
    (re.compile(r"автоматическом развёртывании"), "автобое"),
    (re.compile(r"автовыход \(расширенный\)"), "расширенный автобой"),
]

AUTO_NOUN_RE = re.compile(
    r"(?i)(?:авто-?разв[её]рт[ыи]вани(?:ем|е|я|и|ю)?"
    r"|авто-?размещени(?:ем|е|я|и|ю)?"
    r"|авто-?депло(?:ем|й|я|е|ю)?"
    r"|автозапуск(?:ом|а|у|е)?)")

AUTO_AGREEMENT = [
    (re.compile(r"Автобой допустило ошибку"), "Автобой допустил ошибку"),
    (re.compile(r"автобой допустило ошибку"), "автобой допустил ошибку"),
    (re.compile(r"Автобой успешно выполнено"), "Автобой успешно выполнен"),
    (re.compile(r"автобой успешно выполнено"), "автобой успешно выполнен"),
    (re.compile(r"Автобой (4|6|\{0\}) раз(а)? выполняется"),
     r"Автобой выполняется \1 раз"),
    (re.compile(r"Автобой включено"), "Автобой включён"),
    (re.compile(r"автобой включено"), "автобой включён"),
    (re.compile(r"Автобой активно"), "Автобой активен"),
    (re.compile(r"автобой активно"), "автобой активен"),
    (re.compile(r"Автобой теперь доступно"), "Автобой теперь доступен"),
    (re.compile(r"автобой теперь доступно"), "автобой теперь доступен"),
    (re.compile(r"Автобой станет недоступным"), "Автобой станет недоступен"),
    (re.compile(r"автобой станет недоступным"), "автобой станет недоступен"),
    (re.compile(r"Автобой будет недоступно"), "Автобой будет недоступен"),
    (re.compile(r"автобой будет недоступно"), "автобой будет недоступен"),
    (re.compile(r"Автобой недоступно"), "Автобой недоступен"),
    (re.compile(r"автобой недоступно"), "автобой недоступен"),
    (re.compile(r"больше будет недоступно"), "больше будет недоступен"),
    (re.compile(r"однократное (?=(?:<color=#0099cc>)?[Пп]олный прокси-автобой)"),
     "однократный "),
]

AUTO_ENDINGS = {"ем": "ем", "ом": "ем", "а": "я", "я": "я", "и": "е",
                "ю": "ю"}


def _auto_deploy_repl(match: re.Match[str]) -> str:
    word = match.group(0)
    low = word.lower()
    if low.endswith("ем") or low.endswith("ом"):
        ending = "ем"
    elif low.endswith("я") or low.endswith("а"):
        ending = "я"
    elif low.endswith("и") or (low.endswith("е") and "депло" in low):
        ending = "е"
    else:
        ending = ""
    base = "Автобой" if word[:1].isupper() else "автобой"
    return base[:-1] + AUTO_ENDINGS[ending] if ending else base


def _fix_auto_deploy(text: str) -> str:
    for pattern, replacement in AUTO_PHRASES:
        text = pattern.sub(replacement, text)
    text = AUTO_NOUN_RE.sub(_auto_deploy_repl, text)
    for pattern, replacement in AUTO_AGREEMENT:
        text = pattern.sub(replacement, text)
    return text


def _fix_sanity(text: str) -> str:
    text = SANITY_NUM_RE.sub(_sanity_number, text)
    for pattern, replacement in SANITY_RULES:
        text = pattern.sub(replacement, text)
    return text.replace("Санити", "рассудка")


def apply_context_terms(merged: dict[str, str]) -> int:
    """Fix terms that need the English source to decline correctly.

    ``Сами`` is also the ordinary Russian pronoun ("сами посудите"), so a
    blanket replacement would break dialogue. When the source key contains
    ``Sami`` every ``Сами`` in its translation is the proper noun. The same
    trick keeps ``Санити`` -> ``Рассудок`` from touching unrelated text.
    """
    changed = 0
    for key, value in merged.items():
        new_value = value
        if re.search(r"(?<![A-Za-z])Sami(?![A-Za-z])", key):
            new_value = SAMI_RE.sub("Саами", new_value)
        if "Sanity" in key or "sanity" in key:
            new_value = _fix_sanity(new_value)
        if "Auto Deploy" in key:
            new_value = _fix_auto_deploy(new_value)
        if re.search(r"(?<![A-Za-z])Reunion(?![A-Za-z])", key):
            new_value = re.sub(r"(?<![A-Za-z])Reunion(?![A-Za-z])",
                               "Реюнион", new_value)
        if new_value != value:
            merged[key] = new_value
            changed += 1
    return changed


VOICE_KEYS_FILE = ROOT / "tools" / "voice_line_keys.json"
VOICE_TOKEN_RE = re.compile(
    r"(?:\{[^{}]*\}|<[^<>]*>)[,.;:!?…»)\]]*|\S+")
VOICE_PUNCT_RE = re.compile(r"^[,.;:!?…»)\]]+$")


def _voice_variants(text: str):
    """Same key variants the context builder uses, so matching is stable."""
    seen: set[str] = set()
    for value in (text, strip_display_tags(text)):
        for v in (value, normalize_lookup_text(value),
                  _canon_source(normalize_lookup_text(value))):
            if v and v not in seen:
                seen.add(v)
                yield v


def load_voice_keys() -> tuple[set[str], int]:
    """English source keys of the post-battle/profile voice lines."""
    if not VOICE_KEYS_FILE.is_file():
        print("voice keys missing:", VOICE_KEYS_FILE)
        return set(), 0
    data = json.loads(VOICE_KEYS_FILE.read_text(encoding="utf-8"))
    keys: set[str] = set()
    for key in data.get("keys", []):
        keys.update(_voice_variants(key))
    return keys, int(data.get("max_line", 60))


def _wrap_voice_line(text: str, max_line: int) -> str:
    """Break a long voice line into lines of <= max_line, each next no longer.

    The post-battle VOICE banner renders the string on one line and does not
    wrap it, so explicit newlines are the only way to keep it on screen.
    Macros ``{...}`` and rich-text tags ``<...>`` are never split. A stray
    closing punctuation mark is kept on the previous line instead of starting
    a new one.
    """
    tokens = VOICE_TOKEN_RE.findall(text)
    lines: list[str] = []
    current: list[str] = []
    length = 0
    width = max_line
    for token in tokens:
        extra = len(token) + (1 if current else 0)
        if current and length + extra > width and not VOICE_PUNCT_RE.fullmatch(token):
            lines.append(" ".join(current))
            width = min(max_line, len(lines[-1]))
            current = [token]
            length = len(token)
        else:
            current.append(token)
            length += extra
    if current:
        lines.append(" ".join(current))
    return "\n".join(lines)


def apply_voice_wrap(merged: dict[str, str]) -> tuple[int, int]:
    """Add line breaks to long voice lines so they do not run off screen."""
    keys, max_line = load_voice_keys()
    if not keys or max_line <= 0:
        return 0, 0
    changed = 0
    over = 0
    for key, value in merged.items():
        if key not in keys:
            continue
        if "\n" in value:
            # Keep the existing paragraphs but break any line that is still too
            # long (the banner does not wrap at all).
            parts = value.split("\n")
            if all(len(part) <= max_line for part in parts):
                continue
            wrapped = "\n".join(_wrap_voice_line(part, max_line) for part in parts)
        else:
            if len(value) <= max_line:
                continue
            wrapped = _wrap_voice_line(value, max_line)
        if wrapped == value:
            continue
        merged[key] = wrapped
        changed += 1
        if any(len(line) > max_line for line in wrapped.split("\n")):
            over += 1
    print(f"voice wrap: {changed} lines broken (max {max_line}), "
          f"{over} with an unbreakable token longer than the limit")
    return changed, over


def read_fill() -> dict[str, str]:
    """Load every ru-manifests/ru_fill_*.json gap-fill batch."""
    result: dict[str, str] = {}
    for path in sorted(FILL_DIR.glob("ru_fill_*.json")):
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        for src, dst in data.items():
            hit = clean(str(src), str(dst))
            if hit:
                result[hit[0]] = hit[1]
    return result


def apply_fill(fill: dict[str, str], merged: dict[str, str]) -> int:
    """Add fill entries only when no equivalent key exists yet."""
    added = 0
    for src, dst in fill.items():
        if any(variant in merged for variant in variant_keys(src)):
            continue
        merged[src] = dst
        added += 1
    return added


def _feed_file(digest: "hashlib._Hash", path: Path) -> None:
    digest.update(path.name.encode("utf-8"))
    digest.update(b"\0")
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    digest.update(b"\0")


def source_fingerprint() -> str:
    """Hash everything that can change the merged map.

    The cache lets a rebuild of the pack skip the 30-60 s merge when only the
    launcher/plugin changed. ``--force`` overrides it.
    """
    digest = hashlib.sha256()
    _feed_file(digest, BASE)
    _feed_file(digest, TSV)
    _feed_file(digest, Path(__file__))
    _feed_file(digest, ROOT / "tools" / "name_variants.json")
    _feed_file(digest, VOICE_KEYS_FILE)
    for path in sorted(FILL_DIR.glob("ru_fill_*.json")):
        _feed_file(digest, path)
    for path in sorted((ROOT / "ru-overrides").glob("*.json")):
        _feed_file(digest, path)
    if FRIEND_RU_TXT.is_dir():
        for path in sorted(FRIEND_RU_TXT.glob("*.txt")):
            _feed_file(digest, path)
    for name in FRIEND_FILES:
        path = FRIEND_TXT / name
        if path.is_file():
            _feed_file(digest, path)
    return digest.hexdigest()


def load_cache() -> dict:
    if not CACHE.is_file():
        return {}
    try:
        return json.loads(CACHE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true",
                        help="rebuild even when the cache matches")
    args = parser.parse_args()

    fingerprint = source_fingerprint()
    cached = load_cache()
    if (not args.force and OUT.is_file() and cached.get("fingerprint") == fingerprint):
        print(f"cache hit: {OUT} is up to date ({cached.get('entries', '?')} entries)")
        return 0

    base = json.loads(BASE.read_text(encoding="utf-8-sig"))
    merged: dict[str, str] = {}
    dropped_base = 0
    for src, dst in base.items():
        hit = clean(src, str(dst))
        if hit:
            merged[hit[0]] = hit[1]
        else:
            dropped_base += 1
    print(f"base 99_all: {len(base)} -> {len(merged)} usable (dropped {dropped_base})")

    tsv = read_tsv()
    tsv_added = 0
    for s, t in tsv.items():
        if s not in merged:
            merged[s] = t
            tsv_added += 1
    print(f"TSV gaps added: {tsv_added} (ignored {len(tsv) - tsv_added} already in 99_all), total {len(merged)}")

    friend_ru = read_friend_ru_txt()
    write_friend_report(friend_ru, merged)
    friend_replaced = apply_friend(friend_ru, merged)
    print(f"friend ru_txt applied: replaced {friend_replaced} (final say: RUKAMI + ru-overrides), total {len(merged)}")

    rukami = read_rukami()
    rukami_replaced = sum(1 for s, t in rukami.items() if s in merged and merged[s] != t)
    merged.update(rukami)
    print(f"RUKAMI applied: replaced {rukami_replaced}, total {len(merged)}")

    overrides = read_overrides()
    ov_replaced = sum(1 for s, t in overrides.items() if s in merged and merged[s] != t)
    merged.update(overrides)
    print(f"overrides applied: replaced {ov_replaced}, total {len(merged)}")

    friend = read_friend_txt()
    friend_added = 0
    for s, t in friend.items():
        if s not in merged:
            merged[s] = t
            friend_added += 1
    print(f"friend gaps added: {friend_added}, total {len(merged)}")

    fill = read_fill()
    fill_added = apply_fill(fill, merged)
    print(f"display fill added: {fill_added} of {len(fill)}, total {len(merged)}")

    variants = read_name_variants()
    variant_changed = apply_name_variants(merged, variants)
    print(f"name variants applied: {variant_changed} values rewritten, total {len(merged)}")

    context_changed = apply_context_terms(merged)
    print(f"context terms applied: {context_changed} values rewritten, total {len(merged)}")

    apply_voice_wrap(merged)

    # Re-attach the game's inline rich-text tags (value highlights, status
    # tooltips like <$ba.stun>Stunning</>). Old RU sources dropped them all.
    apply_rich_tags(merged)

    # Drop junk "translations" that were never display strings: they are raw
    # story directive fragments whose value was a cosmetic rewrite. Keeping
    # them only risks corrupting a directive if the game ever passes one.
    junk_prefixes = ("protectTime=", "animStyle=", "startCardIndex=", "startX=",
                     "dialogHead=", "focusStyle=")
    junk = [k for k in merged if k == "_readme" or k.startswith(junk_prefixes)]
    for k in junk:
        del merged[k]
    print(f"junk directive entries removed: {len(junk)}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    write_json(OUT, merged)
    CACHE.write_text(json.dumps({
        "fingerprint": fingerprint,
        "entries": len(merged),
    }, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {OUT}: {len(merged)} entries")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

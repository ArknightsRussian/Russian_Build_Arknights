"""Fill the RichTextFix context dictionaries with the hybrid RU translation.

Keys come from the friend's CN context dictionaries (the last real build embeds
them in runtime/en-zh-offline-final/.../ArknightsLocalization.RichTextFix.dll)
plus the current editable context_translations/ folder. Values are replaced by
our hybrid RU map; friend's Chinese targets are never kept. Keys without a RU
translation are left out so the plugin falls back to XUnity .txt.

Output:
  work/context_translations_ru/*.json
  D:/ARKRUBUILD2/plugins/ArknightsLocalization.RichTextFix/Resources/context_translations.json.gz

Run: py tools/build_ru_context_merged.py
"""
from __future__ import annotations

import gzip
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FRIEND = Path(r"D:\ARKRUBUILD2")
sys.path.insert(0, str(ROOT))

from arklocalizer.custom_pack import HAN_RE, _canon_source, strip_display_tags  # noqa: E402
from arklocalizer.util import normalize_lookup_text  # noqa: E402

import importlib.util  # noqa: E402

_spec = importlib.util.spec_from_file_location("friend_context_json", FRIEND / "tools" / "context_json.py")
assert _spec and _spec.loader
_ctx = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_ctx)
pack = _ctx.pack

MAP = ROOT / "merged-manifests" / "99_merged.json"
EXTRACTED = ROOT / "work" / "friend_context_translations.json.gz"
SOURCE_FOLDER = FRIEND / "context_translations"
# Newer toolkit generations regenerated the context key sets; union all folders
# so keys we already ship are not lost. ARKRUBUILD4 (08.11) adds the whole
# voice-line domain (~1320 keys) on top of BUILD3.
SOURCE_FOLDERS = (
    SOURCE_FOLDER,
    Path(r"D:\ARKRUBUILD3\ArknightsLocalizationToolkit\context_translations"),
    Path(r"D:\ARKRUBUILD4\context_translations"),
)
OUT_FOLDER = ROOT / "work" / "context_translations_ru"
OUT_GZ = FRIEND / "plugins" / "ArknightsLocalization.RichTextFix" / "Resources" / "context_translations.json.gz"


def variant_keys(text: str):
    seen = set()
    base = text
    for value in (base, strip_display_tags(base)):
        for v in (value, normalize_lookup_text(value), _canon_source(normalize_lookup_text(value))):
            if v and v not in seen:
                seen.add(v)
                yield v


def make_lookup(mapping: dict[str, str]):
    index: dict[str, str] = {}
    for source, target in mapping.items():
        for key in variant_keys(source):
            previous = index.get(key)
            # Prefer the variant that still carries <@...>/<$...> markup; the
            # map has both tagged and plain copies of the same sentence.
            if previous is None or (("<@" in target or "<$" in target)
                                    and not ("<@" in previous or "<$" in previous)):
                index[key] = target
    return index


def main() -> int:
    mapping = json.loads(MAP.read_text(encoding="utf-8-sig"))
    lookup = make_lookup(mapping)
    print(f"map: {len(mapping)}, lookup variants: {len(lookup)}")

    # domain -> ordered list of sources (union of both key sources)
    domains: dict[str, list[str]] = {}
    seen: dict[str, set[str]] = {}

    def add(domain: str, source: str) -> None:
        bucket = seen.setdefault(domain, set())
        if source in bucket:
            return
        bucket.add(source)
        domains.setdefault(domain, []).append(source)

    if EXTRACTED.is_file():
        packed = json.loads(gzip.decompress(EXTRACTED.read_bytes()))
        for domain, entries in packed.items():
            # "ambiguous" domains carry an EMPTY target and make the plugin
            # suppress otherwise valid translations. They are not shipped.
            if domain.startswith("ambiguous:"):
                continue
            if domain == "dynamic":
                for record in entries.values():
                    add(domain, json.loads(record)["source"])
            else:
                for source in entries:
                    add(domain, source)
        print(f"extracted keys: {sum(len(v) for v in domains.values())}")

    def add_folder(folder: Path) -> None:
        for path in sorted(folder.glob("*.json")):
            try:
                content = path.read_text(encoding="utf-8-sig").strip()
                if not content:
                    continue
                data = json.loads(content)
            except Exception as e:
                print(f"  skip {path.name}: {e}")
                continue
            if path.name == "id.json":
                for text_id, entries in data.items():
                    for source in entries:
                        add("id:" + text_id, source)
            elif path.name == "ambiguous.json":
                # Explicitly skipped: ambiguous sources used to be emitted with
                # an empty target, which blocked the normal translation path.
                continue
            elif path.name == "dynamic.json":
                for record in data:
                    add("dynamic", record["source"])
            else:
                domain = "number:" + path.stem[len("number_"):] if path.stem.startswith("number_") else path.stem
                for source in data:
                    add(domain, source)

    if SOURCE_FOLDER.is_dir():
        add_folder(SOURCE_FOLDER)
    for extra_folder in SOURCE_FOLDERS[1:]:
        if extra_folder.is_dir():
            add_folder(extra_folder)

    OUT_FOLDER.mkdir(parents=True, exist_ok=True)
    for old in OUT_FOLDER.glob("*.json"):
        old.unlink()

    dynamic_sources: list[str] = []
    filled = 0
    total = 0
    for domain, sources in sorted(domains.items()):
        if domain.startswith("ambiguous:"):
            continue
        if domain == "dynamic":
            dynamic_sources = sources
            continue
        result: dict[str, str] = {}
        for source in sources:
            total += 1
            if domain.startswith("ambiguous:"):
                result[source] = ""
                continue
            target = lookup.get(source)
            if not target:
                for key in variant_keys(source):
                    target = lookup.get(key)
                    if target:
                        break
            if target and not HAN_RE.search(target):
                # Keep restored <@...>/<$...> markup: the plugin hands tagged
                # skill/talent strings to UICommentedText so keyword tooltips
                # and value highlights survive translation.
                result[source] = target
                filled += 1
        if not result:
            continue
        # mirror context_json.unpack naming
        if domain.startswith("id:"):
            ids_path = OUT_FOLDER / "id.json"
            data = json.loads(ids_path.read_text(encoding="utf-8")) if ids_path.is_file() else {}
            data[domain[3:]] = result
            ids_path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                                encoding="utf-8", newline="\n")
        elif domain.startswith("ambiguous:"):
            amb_path = OUT_FOLDER / "ambiguous.json"
            data = json.loads(amb_path.read_text(encoding="utf-8")) if amb_path.is_file() else {}
            data[domain[len("ambiguous:"):]] = sorted(result)
            amb_path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                                encoding="utf-8", newline="\n")
        else:
            name = "number_" + domain[len("number:"):] if domain.startswith("number:") else domain
            (OUT_FOLDER / (name + ".json")).write_text(
                json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8", newline="\n")

    # dynamic templates: keep only those whose exact source has a translation
    templates = []
    for source in dynamic_sources:
        target = lookup.get(source) or next((lookup[k] for k in variant_keys(source) if k in lookup), None)
        if not target or HAN_RE.search(target):
            continue
        templates.append({"scope": "", "source": source, "target": target, "roles": {}})
    # roles/scope are needed for matching, so take them from the real sources instead
    templates = []
    for folder in (SOURCE_FOLDER,):
        path = folder / "dynamic.json"
        if not path.is_file():
            continue
        for record in json.loads(path.read_text(encoding="utf-8-sig")):
            source = record["source"]
            target = lookup.get(source) or next((lookup[k] for k in variant_keys(source) if k in lookup), None)
            if target and not HAN_RE.search(target):
                templates.append({**record, "target": target})
    if templates:
        (OUT_FOLDER / "dynamic.json").write_text(
            json.dumps(templates, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")

    # Global macro templates (skill/module numbers, {0} slots, nicknames, ...).
    # The pack builder no longer emits XUnity regexes for these: 14_regex.txt
    # was ~6 MB / 4500 patterns and every text scanned all of them, freezing the
    # first load for a minute. The plugin matches them with anchored rules.
    generated = ROOT / "work" / "dynamic_templates.json"
    if generated.is_file():
        extra = json.loads(generated.read_text(encoding="utf-8-sig"))
        dynamic_path = OUT_FOLDER / "dynamic.json"
        current = json.loads(dynamic_path.read_text(encoding="utf-8")) if dynamic_path.is_file() else []
        known = {item["source"] for item in current}
        current.extend(item for item in extra if item["source"] not in known)
        (dynamic_path).write_text(
            json.dumps(current, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
        templates = current

    # Attack/redeploy speed tiers are quoted labels, not status effects. The old
    # translations reused "Замедление" (the Slow debuff) next to a numeric stat;
    # the panel expects the tier adjective.
    # "Скорость атаки" is feminine, "развёртывание" is neuter, so the same tier
    # needs different adjective endings in the two panels.
    attack_speed_labels = {
        "Normal": "Нормальная", "Average": "Средняя", "Slightly Fast": "Повышена",
        "Fast": "Высокая", "Slightly Slow": "Снижена", "Slow": "Низкая",
        "Very Fast": "Очень высокая", "Very Slow": "Очень низкая",
    }
    redeploy_speed_labels = {
        "Normal": "Нормальное", "Average": "Среднее", "Slightly Fast": "Повышено",
        "Fast": "Высокое", "Slightly Slow": "Снижено", "Slow": "Низкое",
        "Very Fast": "Очень высокое", "Very Slow": "Очень низкое",
    }
    for name, labels in (("attack-speed", attack_speed_labels),
                         ("redeploy-speed", redeploy_speed_labels)):
        path = OUT_FOLDER / (name + ".json")
        if not path.is_file():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        for source, target in labels.items():
            if source in data:
                data[source] = target
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                        encoding="utf-8", newline="\n")
    id_path = OUT_FOLDER / "id.json"
    if id_path.is_file():
        ids = json.loads(id_path.read_text(encoding="utf-8"))
        for domain, entries in ids.items():
            if "ATK_SPEED" in domain:
                labels = attack_speed_labels
            elif "RESPAWN" in domain:
                labels = redeploy_speed_labels
            else:
                continue
            for source, target in labels.items():
                if source in entries:
                    entries[source] = target
        id_path.write_text(json.dumps(ids, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                           encoding="utf-8", newline="\n")

    print(f"context sources: {total}, filled: {filled}, dynamic templates: {len(templates)}")
    pack(OUT_FOLDER, OUT_GZ)
    print("wrote", OUT_GZ, OUT_GZ.stat().st_size)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


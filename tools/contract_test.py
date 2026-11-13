"""Contract checks for the built RU pack and the latest release archive."""
from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PACK_TEXT = ROOT / "work" / "en-ru-pack-merged" / "Translation" / "ru" / "Text"
DIST = ROOT / "dist"

BANNED_NAMES = [
    "Клозур", "Клоужер", "Клоузер", "Клоужур", "Клоуж", "Клозер",
    "Кложер", "Клоужи", "Клоузи", "Шиоппа",
]

# Запрещаем только НЕПРАВИЛЬНЫЕ русские переводы. 
# Английские слова (Sami, Sanity) оставляем, так как они могут быть в тегах или непереведенных кусках.
BANNED_VALUES = [
    "Санити", "Стойкая Сидж", "Авто-деплой", "Автодеплой",
    "Авто-разв", "Автозапуск",
]

EXPECTED_NAMES = {
    "Closure": "Кложур",
    "Viy": "Вий",
    "Oleg": "Олег",
}

EXPECTED_UI = {
    "Auto Deploy": "Автобой",
    "Tough Siege": "Упорная осада",
    "Building Materials": "Стройматериалы",
    "Upgrade Materials": "Материалы",
    "Mon/Thu/Sat/Sun": "Пн/Чт/Сб/Вс",
    "Open on {0}": "Открыто в {0}",
    "Reunion Member": "Член Реюниона",
    "Reunion Troops": "Войска Реюниона",
    "Tap to select Buildilng materials.": "Нажмите, чтобы выбрать стройматериалы.",
}

def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()

def read_names(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        if not line or line.startswith("//") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        result[key] = value
    return result

def main() -> int:
    errors: list[str] = []
    required_files = ["11_ui.txt", "12_story.txt", "13_names.txt"]

    for name in required_files:
        if not (PACK_TEXT / name).is_file():
            errors.append(f"Missing pack file: {name}")
    
    if (PACK_TEXT / "14_regex.txt").exists():
        errors.append("14_regex.txt must not be shipped")

    if errors:
        print("CONTRACT FAILED")
        for e in errors: print(" -", e)
        return 1

    names = read_names(PACK_TEXT / "13_names.txt")
    for key, expected in EXPECTED_NAMES.items():
        actual = names.get(key)
        if actual != expected:
            errors.append(f"13_names: {key!r} = {actual!r}, expected {expected!r}")

    for name in required_files:
        text = (PACK_TEXT / name).read_text(encoding="utf-8-sig")
        for word in BANNED_NAMES:
            if word in text:
                errors.append(f"{name}: banned name variant {word!r}")

    ui_text = (PACK_TEXT / "11_ui.txt").read_text(encoding="utf-8-sig")
    ui_values = read_names(PACK_TEXT / "11_ui.txt")
    
    for key, expected in EXPECTED_UI.items():
        actual = ui_values.get(key)
        if actual != expected:
            errors.append(f"11_ui: {key!r} = {actual!r}, expected {expected!r}")

    for name in ["11_ui.txt", "12_story.txt"]:
        text = (PACK_TEXT / name).read_text(encoding="utf-8-sig")
        for word in BANNED_VALUES:
            if word in text:
                errors.append(f"{name}: banned term {word!r}")

    for key in ("Are you sure you want to open {0} {1}?", "(Currently held: {0})"):
        if f"{key}=" not in ui_text:
            errors.append(f"11_ui: missing popup template {key!r}")

    zips = sorted(DIST.glob("hook-ru-ai-*-hybrid.zip"), key=lambda p: p.stat().st_mtime)
    if not zips:
        errors.append("no release zip found in dist/")
    else:
        newest = zips[-1]
        manifest_path = newest.with_name(newest.name.replace(".zip", ".manifest.json"))
        if not manifest_path.is_file():
            errors.append(f"missing manifest: {manifest_path.name}")
        else:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            for item in manifest.get("files", []):
                path = item["path"]
                if path.endswith("14_regex.txt"):
                    errors.append("release manifest contains 14_regex.txt")
                    continue
                with zipfile.ZipFile(newest) as archive:
                    try:
                        data = archive.read(path)
                    except KeyError:
                        errors.append(f"release missing {path}")
                        continue
                if hashlib.sha256(data).hexdigest() != item["sha256"]:
                    errors.append(f"release hash mismatch: {path}")
                    
        with zipfile.ZipFile(newest) as archive:
            if any(name.endswith("14_regex.txt") for name in archive.namelist()):
                errors.append("release archive contains 14_regex.txt")

    if errors:
        print("CONTRACT FAILED")
        for error in errors:
            print(" -", error)
        return 1

    print("contract OK")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
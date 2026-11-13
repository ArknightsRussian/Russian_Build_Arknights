"""Package the hybrid RU hook archive for ArknightsRU_Launcher.

Layout (only BepInEx/ matters to the launcher):
  BepInEx/Translation/ru/Text/11_ui.txt
  BepInEx/Translation/ru/Text/12_story.txt
  BepInEx/Translation/ru/Text/13_names.txt
  BepInEx/config/AutoTranslatorConfig.ini
  BepInEx/plugins/ArknightsLocalization/ArknightsLocalization.RichTextFix.dll
  BepInEx/plugins/ArknightsLocalization/arknights_cn_notosanshans
  hook-ru-manifest.json  (root, informational)

Run: py tools/package_merged_hook.py --version 1.0.23
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PACK_TEXT = ROOT / "work" / "en-ru-pack-merged" / "Translation" / "ru" / "Text"
CONFIG = ROOT / "runtime" / "en-ru-test" / "BepInEx" / "config" / "AutoTranslatorConfig.ini"
PLUGIN_DLL = Path(r"D:\ARKRUBUILD2\tools\runtime\ArknightsLocalization.RichTextFix.dll")
FONT = ROOT / "runtime" / "en-zh-offline-final" / "arknights_cn_notosanshans"
STAGE = ROOT / "work" / "hook-ru-merged-stage"
FILES = ["11_ui.txt", "12_story.txt", "13_names.txt"]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", default="1.0.23")
    ap.add_argument("--out", default=str(ROOT / "dist"))
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    if STAGE.exists():
        shutil.rmtree(STAGE)
    text_dir = STAGE / "BepInEx" / "Translation" / "ru" / "Text"
    plugin_dir = STAGE / "BepInEx" / "plugins" / "ArknightsLocalization"
    config_dir = STAGE / "BepInEx" / "config"
    for d in (text_dir, plugin_dir, config_dir):
        d.mkdir(parents=True, exist_ok=True)

    for name in FILES:
        shutil.copy2(PACK_TEXT / name, text_dir / name)
    shutil.copy2(CONFIG, config_dir / CONFIG.name)
    shutil.copy2(PLUGIN_DLL, plugin_dir / PLUGIN_DLL.name)
    shutil.copy2(FONT, plugin_dir / FONT.name)

    manifest = {
        "tool": "arknights-ru-hook-hybrid",
        "source_locale": "en",
        "target_locale": "ru",
        "version": f"v{args.version}",
        "translation_source": "ru-manifests-all/99_all.json (user fixes) + work/translated_1-521504.tsv gap fill",
        "plugin": "ArknightsLocalization.RichTextFix 2.0.0 (rebuilt with merged context)",
        "files": [],
    }
    for path in sorted(STAGE.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(STAGE).as_posix()
        manifest["files"].append({"path": rel, "bytes": path.stat().st_size, "sha256": sha256(path)})
    manifest["files"] = [item for item in manifest["files"] if item["path"] != "hook-ru-manifest.json"]
    manifest_path = STAGE / "hook-ru-manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                             encoding="utf-8", newline="\n")
    outer = dict(manifest)
    outer["files"] = list(manifest["files"]) + [{
        "path": "hook-ru-manifest.json", "bytes": manifest_path.stat().st_size,
        "sha256": sha256(manifest_path)}]

    zip_path = out / f"hook-ru-ai-{args.version}-hybrid.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for path in sorted(STAGE.rglob("*")):
            if path.is_file():
                z.write(path, path.relative_to(STAGE).as_posix())
    (out / f"hook-ru-ai-{args.version}-hybrid.manifest.json").write_text(
        json.dumps(outer, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")

    print("zip:", zip_path)
    print("bytes:", zip_path.stat().st_size)
    print("sha256:", sha256(zip_path))
    for item in outer["files"]:
        print(f"  {item['path']} {item.get('bytes', '')} {item.get('sha256', '')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

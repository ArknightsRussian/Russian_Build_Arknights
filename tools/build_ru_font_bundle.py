"""Swap the dynamic font payload of a Unity Font asset bundle.

The RU build ships its own replacement faces.  A Unity *dynamic* Font asset
stores the raw TTF/OTF bytes in m_FontData, so the existing game-native bundle
can be reused as a shell and only the payload replaced.  That keeps the
AssetBundle/Material/Texture2D wiring intact and avoids building a Unity
project just to change the font.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import UnityPy

ROOT = Path(__file__).resolve().parents[1]


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bundle", required=True, type=Path)
    ap.add_argument("--font", required=True, type=Path)
    ap.add_argument("--report", type=Path)
    args = ap.parse_args()

    payload = args.font.read_bytes()
    env = UnityPy.load(str(args.bundle))
    patched = 0
    old_sha = None
    for obj in env.objects:
        if obj.type.name != "Font":
            continue
        tree = obj.read_typetree()
        old_sha = sha256(bytes(tree["m_FontData"]))
        tree["m_FontData"] = payload
        obj.save_typetree(tree)
        patched += 1
    if patched != 1:
        raise SystemExit(f"expected exactly one Font in {args.bundle}, found {patched}")

    data = env.file.save(packer="lz4")
    args.bundle.write_bytes(data)
    report = {
        "bundle": args.bundle.name,
        "font": args.font.name,
        "font_sha256": sha256(payload),
        "font_bytes": len(payload),
        "previous_font_sha256": old_sha,
        "bundle_bytes": len(data),
        "bundle_sha256": sha256(data),
    }
    target = args.report or args.bundle.with_suffix(".json")
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

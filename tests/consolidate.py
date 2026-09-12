#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""最终整合：E 盘开发位的 manifest 条目 + 素材文件 → D:\Tools 生产位 manifest"""
import hashlib
import json
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

SRC = Path(r"E:\项目搭建\剪贴板")
DST = Path(r"D:\Tools\EasyClipboard")
IMG_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"}

APPLY = "--apply" in sys.argv


def fhash(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    src_manifest = SRC / "_TempShelf" / ".manifest.json"
    try:
        src_entries = json.loads(src_manifest.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        src_entries = []
    print(f"E 盘 manifest 条目: {len(src_entries)}")

    dst_manifest_p = DST / ".manifest.json"
    try:
        dst_entries = json.loads(dst_manifest_p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        dst_entries = []
    print(f"D 盘 manifest 条目: {len(dst_entries)}")

    # 1) E 盘素材文件 → D 盘 _TempShelf（重名改序号）
    for f in sorted(SRC.joinpath("_TempShelf").glob("*")):
        if f.name.startswith("."):
            continue
        dst_f = DST / "_TempShelf" / f.name
        if dst_f.exists():
            if fhash(f) == fhash(dst_f):
                continue
            i = 1
            while (DST / "_TempShelf" / f"{f.stem}_{i}{f.suffix}").exists():
                i += 1
            dst_f = DST / "_TempShelf" / f"{f.stem}_{i}{f.suffix}"
        shutil.copy2(f, dst_f)
        print(f"素材复制 {f.name} → {dst_f.name}")

    # 2) 合并两侧 manifest：以 D 侧为基准，追加 E 侧独有条目（按内容指纹去重）
    def fingerprint(e):
        if e["kind"] == "text":
            return ("text", hashlib.sha256(e["text"].encode("utf-8", "ignore")).hexdigest())
        if e["kind"] == "image":
            return ("image", e.get("hash", ""))
        return ("file", e.get("src", ""))

    seen = {fingerprint(e) for e in dst_entries}
    added = 0
    for e in src_entries:
        fp = fingerprint(e)
        if fp in seen:
            continue
        seen.add(fp)
        # image 条目的实体文件从 E 盘补拷到 D 盘
        if e["kind"] == "image":
            e_src = SRC / "_TempShelf" / e["name"]
            if e_src.exists():
                dst_img = DST / "_TempShelf" / e["name"]
                i = 1
                while dst_img.exists():
                    st, ex = dst_img.stem, dst_img.suffix
                    dst_img = DST / "_TempShelf" / f"{st}_{i}{ex}"
                    i += 1
                shutil.copy2(e_src, dst_img)
                e["name"] = dst_img.name
        dst_entries.append(e)
        added += 1
    print(f"E 侧新增并入: {added} 条")

    dst_manifest_p.parent.mkdir(parents=True, exist_ok=True)
    dst_manifest_p.write_text(json.dumps(dst_entries, ensure_ascii=False, indent=1),
                              encoding="utf-8")
    print(f"合并完成，D 盘 manifest 共 {len(dst_entries)} 条")


if __name__ == "__main__":
    main()

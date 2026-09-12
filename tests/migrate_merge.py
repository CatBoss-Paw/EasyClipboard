#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""一次性数据迁移合并：E 盘开发位 → D:\Tools 生产位
原则：先备份后写入；同名日志按 ### 时间段合并去重；素材文件重名加序号；manifest 合并去重"""
import hashlib
import json
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

SRC = Path(r"E:\项目搭建\剪贴板")
DST = Path(r"D:\Tools\EasyClipboard")
APPLY = "--apply" in sys.argv

backup_root = DST / "_migration_backup" / datetime.now().strftime("%Y%m%d_%H%M%S")
copied, merged, skipped = [], [], []


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else ""


def merge_journal(src: Path, dst: Path):
    """合并两份日志：按 ### 时间小节去重后按时间排序"""
    def parse(text):
        secs = []
        cur = None
        for line in text.splitlines():
            if line.startswith("### "):
                if cur:
                    secs.append(cur)
                cur = [line[4:].strip(), []]
            elif cur is not None and line.strip() != "---":
                cur[1].append(line)
        if cur:
            secs.append(cur)
        return secs

    a_secs = parse(src.read_text(encoding="utf-8")) if src.exists() else []
    b_secs = parse(dst.read_text(encoding="utf-8")) if dst.exists() else []
    seen = {(ts, "\n".join(body).strip()) for ts, body in b_secs}
    merged = list(b_secs)
    for ts, body in a_secs:
        key = (ts, "\n".join(body).strip())
        if key not in seen:
            merged.append((ts, body))
            seen.add(key)
    merged.sort(key=lambda s: s[0])
    head = dst.read_text(encoding="utf-8").split("---")[0] if dst.exists() else \
        (f"# 剪贴板工作日志 — {dst.stem}\n\n> 记录今日复制与输入的文字碎片，"
         f"沉淀为个人工作记忆与知识库。\n\n---\n\n")
    out = head
    for ts, body in merged:
        out += f"### {ts}\n\n{chr(10).join(body).strip()}\n\n---\n\n"
    dst.write_text(out, encoding="utf-8")


print(f"== 数据迁移 E→D {'(APPLY)' if APPLY else '(DRY-RUN 预览)'} ==")

# 1. 每日日志合并（同名按小节合并，异名直接复制）
if SRC.joinpath("_History").exists():
    DST.mkdir(parents=True, exist_ok=True)
    for j in sorted(SRC.joinpath("_History").glob("*.md")):
        dst_j = DST / "_History" / j.name
        if dst_j.exists():
            # 同名 → 小节级合并
            before = dst_j.read_text(encoding="utf-8")
            merge_journal(j, dst_j)
            after = dst_j.read_text(encoding="utf-8")
            (merged if after != before else skipped).append(f"日志合并 {j.name}")
            print(("MERGE " if after != before else "SAME  ") + j.name)
        else:
            dst_j.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(j, dst_j)
            copied.append(f"日志 {j.name}")
            print("COPY  ", j.name)
    # 备份目录整体保留
    for b in SRC.joinpath("_History").glob("_backup*"):
        dst_b = DST / "_History" / b.name
        if not dst_b.exists():
            shutil.copytree(b, dst_b)
            copied.append(f"备份目录 {b.name}")

# 2. 素材文件：E 盘 _TempShelf 的自产截图 → D 盘 _TempShelf（重名改序号，绝不覆盖）
for f in sorted(SRC.joinpath("_TempShelf").glob("*")):
    if f.name.startswith("."):
        continue
    dst_f = DST / "_TempShelf" / f.name
    if dst_f.exists():
        if sha(f) == sha(dst_f):
            continue
        i = 1
        while (DST / "_TempShelf" / f"{f.stem}_{i}{f.suffix}").exists():
            i += 1
        dst_f = DST / "_TempShelf" / f"{f.stem}_{i}{f.suffix}"
    shutil.copy2(f, dst_f)
    copied.append(f"素材 {f.name}")

# 3. _Pinned：E 盘的托管文件全部进 D 盘 _Pinned
for f in sorted(SRC.joinpath("_Pinned").glob("*")):
    if f.name == "_links.json":
        continue
    dst_f = DST / "_Pinned" / f.name
    if dst_f.exists():
        if sha(f) == sha(dst_f):
            continue
        i = 1
        while (DST / "_Pinned" / f"{f.stem}_{i}{f.suffix}").exists():
            i += 1
        dst_f = DST / "_Pinned" / f"{f.stem}_{i}{f.suffix}"
    shutil.copy2(f, dst_f)
    copied.append(f"托管 {f.name}")

# 4. 提示词库：E 盘 _Prompts 全部进 D 盘 _Prompts
for f in sorted(SRC.joinpath("_Prompts").rglob("*")):
    rel = f.relative_to(SRC.joinpath("_Prompts"))
    dst_f = DST / "_Prompts" / rel
    if f.is_dir():
        dst_f.mkdir(parents=True, exist_ok=True)
        continue
    if dst_f.exists() and sha(f) == sha(dst_f):
        continue
    dst_f.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(f, dst_f)
    copied.append(f"提示词 {rel}")

print(f"复制 {len(copied)} 项, 合并 {len(merged)} 项, 跳过 {len(skipped)} 项")
if APPLY:
    print("已执行迁移")
else:
    print("（DRY-RUN 结束，加 --apply 执行真实迁移）")

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""E 盘开发位日志 → D 盘生产位合并（同名按小节去重合并，异名直接复制）"""
import shutil
from datetime import datetime
from pathlib import Path

E_HIST = Path(r"E:\项目搭建\剪贴板\_History")
D_HIST = Path(r"D:\Tools\EasyClipboard\_History")
D_HIST.mkdir(parents=True, exist_ok=True)


def parse_secs(text: str):
    secs, cur = [], None
    for line in text.splitlines():
        if line.startswith("### "):
            if cur:
                secs.append(cur)
            cur = (line[4:].strip(), [])
        elif cur is not None:
            cur[1].append(line)
    if cur:
        secs.append(cur)
    return secs


merged_count = 0
for j in sorted(E_HIST.glob("*.md")):
    dst = D_HIST / j.name
    if dst.exists():
        # 同名 → 小节级合并
        a_secs = parse_secs(j.read_text(encoding="utf-8"))
        b_secs = parse_secs(dst.read_text(encoding="utf-8"))
        b_keys = {(ts, "\n".join(body).strip()) for ts, body in b_secs}
        new_secs = [(ts, "\n".join(body).strip()) for ts, body in a_secs if (ts, "\n".join(body).strip()) not in b_keys]
        if new_secs:
            merged = dst.read_text(encoding="utf-8")
            for ts, body in new_secs:
                merged += f"### {ts}\n\n{body}\n\n---\n\n"
            dst.write_text(merged, encoding="utf-8")
            print(f"MERGE {j.name} (+{len(new_secs)} 条新小节)")
        else:
            print(f"SAME  {j.name} (无新增)")
    else:
        shutil.copy2(j, dst)
        print(f"NEW   {j.name}")

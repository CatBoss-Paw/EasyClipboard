#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
一次性清理：移除本轮调试期间误写入真实数据目录的【测试产物】。

事故经过（必须如实记录）：
    本轮新增的 Shelf.ensure_watchdog() 原本写在 Shelf.__init__ 里。
    沙箱测试构造 Shelf() 时会拉起一个【真实的常驻看守进程】，而看守子进程用
    它自己的 __file__ 解析路径 → 指向真实数据目录，测试对 shelf_app 模块常量的
    沙箱覆写对它完全无效。该看守从 02:26 一直跑到 03:15。

    根因已修复：ensure_watchdog() 移到 main()，只有真实启动产品才拉看守。

清理原则（严格遵守）：
    - 只删【测试产物】：本次调试用的标记文本与 64x48 纯色测试图
    - 绝不动【用户真实素材】：02:28~03:11 期间看守意外捕获的 13 条是用户
      自己复制的真实工作内容（FDE 笔记、Palantir、语音转写等），必须保留
    - 每条删除都打印出来，可人工核对

判据用【精确字符串匹配】，不用时间范围，避免误删用户素材。

职责边界：本脚本只改写文本内容（manifest / 每日日志），【不删除任何文件】。
    测试图片文件本体的删除交由人工执行 Bash rm（绝对路径），脚本末尾打印清单。
"""
import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(r"E:\项目搭建\剪贴板")
SHELF = ROOT / "_TempShelf"
HIST = ROOT / "_History"
MANIFEST = SHELF / ".manifest.json"
JOURNAL = HIST / "2026-09-07.md"

# ---- 本次调试产生的测试标记（精确匹配，不含任何用户可能复制的内容）----
TEST_TEXT_MARKS = [
    "签名修复端到端验证-CTYPES-64BIT",
    "架构验证：看守写入的条目",   # ts="00:35" 格式异常且缺 on/at/hash，手工写入的产物
    "探针文本-ctypes截断验证",
    "E2E端到端实测标记-9f3kq2mz",
    "审计用文本条目ABCDEFG",
    "双击复制测试文本ABCDEFG",
    "运行时双击验证ABCDEF",
    "检查默认值ABC",
]
# 测试图：64x48 纯色，由 tests/*.py 用 QImage(64,48) 生成
TEST_IMAGE_FILES = [
    "cap_20260907_022630.bmp",
    "cap_20260907_031411.bmp",
]
# 测试文件引用：指向 Python 解释器本体（用户不可能复制它当素材）
TEST_FILE_REFS = ["python.exe"]

BACKUP = ROOT / "_History" / "_backup_before_cleanup"


def is_test_entry(e: dict) -> bool:
    kind = e.get("kind")
    if kind == "text":
        t = (e.get("text") or "").strip()
        return any(t == m or t.startswith(m) for m in TEST_TEXT_MARKS)
    if kind == "image":
        return e.get("name") in TEST_IMAGE_FILES
    if kind == "file":
        return e.get("name") in TEST_FILE_REFS
    return False


def main():
    if not MANIFEST.exists():
        print("manifest 不存在，无需清理")
        return 0

    # ---- 备份（不可逆操作前的保险）----
    BACKUP.mkdir(parents=True, exist_ok=True)
    shutil.copy2(MANIFEST, BACKUP / "manifest.json.bak")
    if JOURNAL.exists():
        shutil.copy2(JOURNAL, BACKUP / (JOURNAL.name + ".bak"))
    print("已备份到:", BACKUP)
    print()

    entries = json.loads(MANIFEST.read_text(encoding="utf-8"))
    print("清理前 manifest 条目数:", len(entries))
    print()

    removed, kept = [], []
    for e in entries:
        (removed if is_test_entry(e) else kept).append(e)

    if removed:
        print("=== 将移除的【测试产物】（逐条核对）===")
        for e in removed:
            k = e.get("kind")
            desc = e.get("text", "")[:50] if k == "text" else e.get("name")
            print("  - [%s] ts=%s  %r" % (k, e.get("ts"), desc))
    else:
        print("未发现测试产物条目")
    print()

    print("=== 保留的条目数:", len(kept), "===")
    # 打印保留项的时间范围，供人工确认用户素材完好
    if kept:
        print("  首条 ts=%s  末条 ts=%s" % (kept[0].get("ts"), kept[-1].get("ts")))
        print("  其中 02:28~03:11 的用户真实素材（必须保留）：")
        n = 0
        for e in kept:
            ts = str(e.get("ts", ""))
            if ts >= "02:28" and ts <= "03:12":
                n += 1
                d = e.get("text", "")[:40] if e.get("kind") == "text" else e.get("name")
                print("     [%s] %s %r" % (e.get("kind"), ts, d))
        print("  小计:", n, "条")
    print()

    # ---- 写回 manifest ----
    MANIFEST.write_text(json.dumps(kept, ensure_ascii=False), encoding="utf-8")
    print("已写回 manifest:", len(kept), "条")

    # ---- 测试图片文件本体：本脚本不删，打印清单交人工 rm ----
    pending = [SHELF / n for n in TEST_IMAGE_FILES if (SHELF / n).exists()]
    if pending:
        print()
        print("!!! 待人工删除的测试图片（请用 Bash rm 绝对路径执行）!!!")
        for p in pending:
            print("    rm \"%s\"" % p.as_posix())

    # ---- 清理每日日志中的测试段 ----
    if JOURNAL.exists():
        txt = JOURNAL.read_text(encoding="utf-8")
        segs = re.split(r"(?m)^(?=### )", txt)
        out, dropped = [], []
        for s in segs:
            if any(m in s for m in TEST_TEXT_MARKS):
                dropped.append(s.strip().splitlines()[0][:50])
            else:
                out.append(s)
        if dropped:
            JOURNAL.write_text("".join(out), encoding="utf-8")
            print("已从每日日志移除 %d 个测试段:" % len(dropped))
            for d in dropped:
                print("  -", d)
        else:
            print("每日日志无需清理")

    print()
    final = json.loads(MANIFEST.read_text(encoding="utf-8"))
    print("清理后 manifest 条目数:", len(final))
    leftover = [e for e in final if is_test_entry(e)]
    print("残留测试产物:", len(leftover))
    return 0 if not leftover else 1


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BUG 验证：保留策略（auto_clear_hours）清理后不落盘 + _save_manifest 方法不存在。

事实依据（源码静态分析）：
  1) Shelf._load_manifest 末尾 `if self.entries and not p.exists(): self._save_manifest()`
     调用了一个【从未定义】的方法（Shelf 里只有 _commit，看守里才有 save_manifest）。
  2) 该分支在 _load_manifest 内部恒不可达：
        p 不存在 → entries=[] → self.entries 为假 → 不进入
        p 存在   → not p.exists() 为假 → 不进入
     所以它现在是"死代码"，不会当场崩；但它是一枚地雷：任何人调整
     _load_manifest 的语句顺序或新增调用点，就会 AttributeError。
  3) 真正生效的缺陷：_apply_retention 会【物理删除】过期截图文件，
     但清理结果从不写回 manifest（无 _commit 调用）。
     看守进程每次捕获都是 load_manifest() → 追加 → save_manifest()，
     于是被清理的条目连同指向【已删除文件】的死引用会被看守原样写回，
     保留策略静默失效，manifest 长期积累失效条目。

本测试用沙箱 + 直接构造过期 manifest 验证 (2)(3)。
"""
import json
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROJECT_PY = r"C:\Users\37162\AppData\Local\Programs\Python\Python313\python.exe"
if not Path(PROJECT_PY).exists():
    PROJECT_PY = sys.executable

PROBE = r'''
import os, sys, json, tempfile
from datetime import datetime, timedelta
from pathlib import Path
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, r"__ROOT__")

import shelf_app
_sb = Path(tempfile.mkdtemp(prefix="shelf_ret_"))
shelf_app.DEFAULT_SETTINGS["shelf_dir"]   = str(_sb / "_TempShelf")
shelf_app.DEFAULT_SETTINGS["history_dir"] = str(_sb / "_History")
shelf_app.DEFAULT_SETTINGS["pinned_dir"]  = str(_sb / "_Pinned")
shelf_app.SETTINGS_PATH = _sb / "settings.json"

from PyQt6.QtWidgets import QApplication
app = QApplication(sys.argv)

w = shelf_app.Shelf()
w._sync_ui = lambda: None          # 观测期间不刷新 UI，聚焦数据层

# ---- 静态事实：落盘方法是否存在 ----
# 修复方案：旧的 self._save_manifest() 是一个从未定义的死方法（地雷），
# 已改为调用新拆出的 _persist_manifest()（纯数据落盘、不碰 UI）。
# 所以 _save_manifest 消失是【正确结果】，_persist_manifest 存在才对。
print("HAS_save_manifest=%s" % hasattr(w, "_save_manifest"), flush=True)
print("HAS_persist_manifest=%s" % hasattr(w, "_persist_manifest"), flush=True)
print("HAS_commit=%s" % hasattr(w, "_commit"), flush=True)

# ---- 构造 3 条过期(48h前) + 1 条新鲜 的 manifest ----
old = (datetime.now() - timedelta(hours=48)).strftime("%Y-%m-%d %H:%M:%S")
new = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
entries = [
    {"kind": "image", "name": "shot_old.png",  "ts": old, "at": old, "on": False},
    {"kind": "image", "name": "shot_old2.png", "ts": old, "at": old, "on": False},
    {"kind": "text",  "text": "过期文字条目",    "ts": old, "at": old, "on": False},
    {"kind": "text",  "text": "新鲜文字条目",    "ts": new, "at": new, "on": False},
]
mp = shelf_app.SHELF_DIR / shelf_app.MANIFEST_NAME
mp.parent.mkdir(parents=True, exist_ok=True)
mp.write_text(json.dumps(entries, ensure_ascii=False), encoding="utf-8")
before_mtime = mp.stat().st_mtime_ns

# ---- 开启保留策略 24h 并重新加载 ----
w.settings["auto_clear_hours"] = 24
try:
    w._load_manifest()
    print("LOAD_NO_CRASH=True", flush=True)
except AttributeError as e:
    print("LOAD_NO_CRASH=False", flush=True)
    print("LOAD_ERR=%r" % e, flush=True)

print("MEM_ENTRIES_AFTER=%d" % len(w.entries), flush=True)
disk = json.loads(mp.read_text(encoding="utf-8"))
print("DISK_ENTRIES_AFTER=%d" % len(disk), flush=True)
print("DISK_CHANGED=%s" % (mp.stat().st_mtime_ns != before_mtime), flush=True)
print("DISK_MATCHES_MEMORY=%s" % (disk == w.entries), flush=True)

# ---- 模拟看守的下一次写入：load_manifest() 追加 -> save_manifest() ----
wd_path = r"__ROOT__" + "\\" + "watchdog.pyw"
import importlib.util
spec = importlib.util.spec_from_file_location("wd_probe", wd_path)
# 看守模块顶层会读配置/建目录，这里只复用它的纯函数逻辑，手工模拟其行为：
wd_disk = json.loads(mp.read_text(encoding="utf-8"))
wd_disk.append({"kind": "text", "text": "看守新捕获", "ts": new, "at": new, "on": False})
mp.write_text(json.dumps(wd_disk, ensure_ascii=False), encoding="utf-8")
wd_after = json.loads(mp.read_text(encoding="utf-8"))
print("AFTER_WATCHDOG_WRITE_ENTRIES=%d" % len(wd_after), flush=True)
stale = [e for e in wd_after
         if e["kind"] == "image" and not (shelf_app.SHELF_DIR / e["name"]).exists()]
print("RESURRECTED_STALE_ENTRIES=%d" % len(stale), flush=True)

print("PROBE_DONE", flush=True)
'''
PROBE = PROBE.replace("__ROOT__", str(ROOT))


def main():
    r = subprocess.run([PROJECT_PY, "-E", "-X", "faulthandler", "-c", PROBE],
                       capture_output=True, timeout=120, cwd=str(ROOT))
    out = r.stdout.decode("utf-8", "replace")
    err = r.stderr.decode("utf-8", "replace")
    # 子进程在 GBK 控制台写中文，解码会得 U+FFFD；宿主 stdout 同为 GBK，
    # 直接 print 会 UnicodeEncodeError 把测试脚本自身撞死（已踩过），转 ASCII 安全。
    out = out.encode("ascii", "replace").decode("ascii")
    err = err.encode("ascii", "replace").decode("ascii")
    print("=" * 70)
    print("returncode =", r.returncode)
    print(out)
    if err.strip():
        print("-" * 30, "STDERR", "-" * 30)
        print(err[-2000:])
    print("=" * 70)

    if "PROBE_DONE" not in out:
        print("判定：无效验证 —— 探针未跑完")
        return 2

    kv = {}
    for line in out.splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            kv[k.strip()] = v.strip()

    crashed = kv.get("LOAD_NO_CRASH") == "False"
    persisted = kv.get("DISK_CHANGED") == "True" and kv.get("DISK_MATCHES_MEMORY") == "True"
    resurrected = int(kv.get("RESURRECTED_STALE_ENTRIES", "0") or 0)
    # 修复后应有的方法：_persist_manifest 存在；旧死方法 _save_manifest 不再被调用
    method_ok = (kv.get("HAS_persist_manifest") == "True"
                 and kv.get("HAS_commit") == "True")

    print("落盘方法齐备(_persist_manifest/_commit): %s（应为 True）" % method_ok)
    print("旧死方法 _save_manifest 已移除: %s（应为 True）"
          % (kv.get("HAS_save_manifest") == "False"))
    print("保留策略清理后落盘: %s（应为 True）" % persisted)
    print("看守写回后复活的失效条目数: %d（应为 0）" % resurrected)

    if crashed:
        print("\n判定：P0 —— _load_manifest 当场 AttributeError 崩溃")
        return 1
    if persisted and resurrected == 0 and method_ok \
            and kv.get("HAS_save_manifest") == "False":
        print("\n判定：功能正常 —— 保留策略清理已落盘，死方法已清除")
        return 0
    print("\n判定：缺陷成立 —— 保留策略清理不落盘或落盘方法缺失")
    return 1


if __name__ == "__main__":
    sys.exit(main())

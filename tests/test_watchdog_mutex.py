#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BUG 验证：看守单实例锁 GetLastError 读取方式错误 → 行为不确定。

根因（已实测证明）：
    ctypes 在两次 FFI 调用之间会自己调用其他 Win32 API（参数类型转换、内存管理），
    那些调用会【覆盖】当前线程的 last error。因此：
        kernel32.CreateMutexW(...)
        kernel32.GetLastError()          <- 读到的往往不是 CreateMutexW 的错误码
    实测：mutex 已存在时
        kernel32.GetLastError()   = 0    （错）
        ctypes.get_last_error()   = 183  （对，需 use_last_error=True）

后果（两个方向都会出事）：
    - 误判 183 → 看守刚启动就"看守已在运行，退出"→ 产品完全不工作
      （无剪贴板捕获、F9 无反应）。这正是本次端到端实测中真实发生的现象。
    - 漏判 183 → 多个看守同时跑 → 重复捕获、互相覆盖 manifest。

正确做法：用 WINFUNCTYPE(..., use_last_error=True) 构造 CreateMutexW，
再用 ctypes.get_last_error() 读取。

沙箱铁律：覆写 watchdog 模块的路径常量到 tempdir，绝不触碰真实数据目录。
"""
import ctypes
import importlib.util
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WD = ROOT / "watchdog.pyw"
PROJECT_PY = r"C:\Users\37162\AppData\Local\Programs\Python\Python313\python.exe"
if not Path(PROJECT_PY).exists():
    PROJECT_PY = sys.executable

PROBE = r'''
import ctypes, importlib.util, json, sys, tempfile
from pathlib import Path

_sb = Path(tempfile.mkdtemp(prefix="wd_mutex_"))
(_sb / "_TempShelf").mkdir()
(_sb / "_History").mkdir()
(_sb / "shelf_settings.json").write_text(
    json.dumps({"min_text_len": 2, "hotkey": "f9", "pause_hotkey": "f10"}),
    encoding="utf-8")

spec = importlib.util.spec_from_file_location("wd", r"__WD__")
wd = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wd)
wd.APP_DIR = _sb
wd.SETTINGS_PATH = _sb / "shelf_settings.json"
wd.SHELF_DIR = _sb / "_TempShelf"
wd.HISTORY_DIR = _sb / "_History"
wd.SHOW_SIG = wd.SHELF_DIR / ".show_sig"
wd.PAUSE_SIG = wd.SHELF_DIR / ".paused"

print("SANDBOX=%s" % _sb, flush=True)

# ---------- 1) 源码必须已改用 use_last_error 版本 ----------
src = Path(r"__WD__").read_text(encoding="utf-8")
print("SRC_HAS_use_last_error=%s" % ("use_last_error=True" in src), flush=True)
print("SRC_HAS_get_last_error=%s" % ("ctypes.get_last_error()" in src), flush=True)
print("HAS_CreateMutexW_wrapper=%s" % hasattr(wd, "CreateMutexW"), flush=True)
# 绝不能再用裸 GetLastError 做单实例判定
print("SRC_NO_BARE_GetLastError_check=%s"
      % ("kernel32.GetLastError() == ERROR_ALREADY_EXISTS" not in src
         and "kernel32.GetLastError() == 183" not in src), flush=True)

# ---------- 2) 对照实验：裸 GetLastError vs get_last_error ----------
NAME = "ShelfProbeMutexContrast"
k = ctypes.windll.kernel32

# 2a) 裸调用（旧实现方式）
k.CreateMutexW.restype = ctypes.c_void_p
k.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
k.GetLastError.restype = ctypes.c_uint32
k.GetLastError.argtypes = []
first = k.CreateMutexW(None, False, NAME)          # 首次创建，持有不放
second = k.CreateMutexW(None, False, NAME)         # 已存在 → 应报 183
bare = k.GetLastError()
print("CONTRAST_HANDLE_1=0x%X" % (first or 0), flush=True)
print("CONTRAST_HANDLE_2=0x%X" % (second or 0), flush=True)
print("BARE_GetLastError=%d" % bare, flush=True)

# 2b) 正确方式
proto = ctypes.WINFUNCTYPE(ctypes.c_void_p, ctypes.c_void_p, ctypes.c_bool,
                           ctypes.c_wchar_p, use_last_error=True)
fn = proto(("CreateMutexW", k))
third = fn(None, False, NAME)
proper = ctypes.get_last_error()
print("PROPER_get_last_error=%d" % proper, flush=True)
print("CONTRAST_PROPER_IS_183=%s" % (proper == 183), flush=True)
# 裸读是否可靠（不可靠即证明旧实现有缺陷）
print("CONTRAST_BARE_UNRELIABLE=%s" % (bare != 183), flush=True)

for h in (third, second, first):
    if h:
        k.CloseHandle(h)

# ---------- 3) 被测包装器的真实行为：同进程内第二次调用应报 183 ----------
h1 = wd.CreateMutexW(None, False, "ShelfProbeWrapperTest")
e1 = ctypes.get_last_error()
h2 = wd.CreateMutexW(None, False, "ShelfProbeWrapperTest")
e2 = ctypes.get_last_error()
print("WRAPPER_FIRST_ERR=%d" % e1, flush=True)
print("WRAPPER_SECOND_ERR=%d" % e2, flush=True)
print("WRAPPER_HANDLE_NONZERO=%s" % bool(h1 and h2), flush=True)
print("WRAPPER_DETECTS_DUPLICATE=%s"
      % (e1 == 0 and e2 == wd.ERROR_ALREADY_EXISTS), flush=True)
for h in (h2, h1):
    if h:
        k.CloseHandle(h)

print("PROBE_DONE", flush=True)
'''
PROBE = PROBE.replace("__WD__", str(WD))


def main():
    r = subprocess.run([PROJECT_PY, "-E", "-X", "utf8", "-c", PROBE],
                       capture_output=True, timeout=180, cwd=str(ROOT))
    out = r.stdout.decode("utf-8", "replace")
    err = r.stderr.decode("utf-8", "replace")
    print("=" * 78)
    print("returncode =", r.returncode)
    print("-" * 78)
    print(out)
    if err.strip():
        print("-" * 30, "STDERR", "-" * 30)
        print(err[-2000:])
    print("=" * 78)

    if "PROBE_DONE" not in out:
        print("判定：无效验证 —— 探针未跑完")
        return 2

    kv = {}
    for line in out.splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            kv[k.strip()] = v.strip()

    checks = [
        ("源码使用 use_last_error=True", kv.get("SRC_HAS_use_last_error") == "True"),
        ("源码使用 ctypes.get_last_error()", kv.get("SRC_HAS_get_last_error") == "True"),
        ("存在 CreateMutexW 包装器", kv.get("HAS_CreateMutexW_wrapper") == "True"),
        ("不再用裸 GetLastError 判定单实例", kv.get("SRC_NO_BARE_GetLastError_check") == "True"),
        ("对照：正确方式能拿到 183", kv.get("CONTRAST_PROPER_IS_183") == "True"),
        ("包装器句柄非零", kv.get("WRAPPER_HANDLE_NONZERO") == "True"),
        ("包装器能识别重复实例(0→183)", kv.get("WRAPPER_DETECTS_DUPLICATE") == "True"),
    ]

    allok = True
    for name, ok in checks:
        print("  %-40s %s" % (name, "✅" if ok else "❌"))
        allok = allok and ok

    print()
    print("  对照实验（同一 mutex 名，第二次调用应报 ERROR_ALREADY_EXISTS=183）：")
    print("    裸 kernel32.GetLastError()   = %-6s %s"
          % (kv.get("BARE_GetLastError"),
             "← 不可靠，证明旧实现有缺陷" if kv.get("CONTRAST_BARE_UNRELIABLE") == "True"
             else "← 本次恰好正确（但行为不确定）"))
    print("    ctypes.get_last_error()      = %-6s ← 可靠"
          % kv.get("PROPER_get_last_error"))
    print()
    if allok:
        print("判定：修复生效 —— 单实例锁能可靠识别重复实例")
        return 0
    print("判定：仍有问题，见上表 ❌ 项")
    return 1


if __name__ == "__main__":
    sys.exit(main())

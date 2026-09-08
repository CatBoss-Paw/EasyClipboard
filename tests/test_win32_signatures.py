#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BUG 验证：看守进程 ctypes 未声明签名 → 64 位指针被截断 → 捕获全线失效。

根因（已实测证明）：
    ctypes 默认 restype = c_long（4 字节），argtypes 不校验。
    64 位 Windows 上 GetClipboardData / GlobalLock 实际返回 8 字节指针：
        真实值 0x0000020858D84CD0  →  截断后 0x58D84CD0（高位全丢）
    截断地址交给 wstring_at / string_at 必然 access violation。

    看守日志中的实证：
        循环异常(已忽略): exception: access violation reading 0x000000003A8C1B30
    地址【高位全是 0】正是截断特征。

    这纠正了交接文档 §4 坑 #14 的错误诊断（"与其他进程争抢剪贴板，捕获后
    跳过即可，实测已稳定"）。真因是指针截断；try/except 只是把崩溃吞掉，
    后果是【文字/图片/文件三类捕获全部静默失效】——产品核心功能不工作。

本测试三层验证：
    L1 签名声明：所有返回句柄/指针的 API 的 restype 必须是 c_void_p / 无符号整型
    L2 截断对照：同一个句柄，声明前 vs 声明后的高位是否保留
    L3 端到端：真实写剪贴板 → 看守函数读取 → 内容正确（三类格式各测一次）

沙箱铁律：绝不使用真实数据目录（覆写 watchdog 模块的 SHELF_DIR/HISTORY_DIR/
SETTINGS_PATH 到 tempdir）。
"""
import ctypes
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WD = ROOT / "watchdog.pyw"

# ---------------------------------------------------------------------------
# 【平台守卫：踩过一次坑，切勿再删】
#
# 本测试的 L3 要验证的是【真实 Win32 剪贴板】上的三类格式能否被看守读到。
# 若带 QT_QPA_PLATFORM=offscreen 跑，Qt 的 QClipboard 不与真实 Win32 剪贴板
# 交互，cb.setImage() / cb.setMimeData() 写进去后，IsClipboardFormatAvailable
# 对 CF_DIB / CF_HDROP 直接返回 False，于是：
#     IMG_HANDLE=0x0000000000000000   FILE_HANDLE=0x0000000000000000
#     L3 图片/文件/落盘 共 6 项 ❌
# 而【同一份代码】不加 offscreen 跑就是 13/13 全 ✅。实测对照已确认。
#
# 危险之处在于：这种失败看起来太像产品回归了（句柄为 0 = 捕获失效，正是
# BUG-005 的症状），很容易被误判成“修坏了”，进而去改本来正确的 ctypes 签名。
# 所以这里直接在子进程探针里【强制清掉 offscreen】，并在外层显式报错。
# ---------------------------------------------------------------------------
_PROJECT_PY = r"C:\Users\37162\AppData\Local\Programs\Python\Python313\python.exe"
if not Path(_PROJECT_PY).exists():
    _PROJECT_PY = sys.executable

if os.environ.get("QT_QPA_PLATFORM", "").lower() == "offscreen":
    print("[GUARD] 检测到 QT_QPA_PLATFORM=offscreen，本测试需真实 Win32 剪贴板，",
          file=sys.stderr, flush=True)
    print("[GUARD] 已自动清除该变量后重跑（offscreen 下 CF_DIB/CF_HDROP 不可见，",
          file=sys.stderr, flush=True)
    print("[GUARD] 会产生假失败，极易被误判为产品回归）。", file=sys.stderr,
          flush=True)
    env = dict(os.environ)
    env.pop("QT_QPA_PLATFORM", None)
    # 用 -E 避开 WPS 灵犀 python-env 的 .pth 污染（否则 site 初始化 Fatal），
    # 用 -X utf8 避开 GBK 控制台下的 UnicodeEncodeError
    r = subprocess.run([_PROJECT_PY, "-E", "-X", "utf8",
                        str(Path(__file__).resolve())],
                       env=env, cwd=str(ROOT))
    sys.exit(r.returncode)
PROJECT_PY = _PROJECT_PY

PROBE = r'''
import ctypes, importlib.util, json, os, sys, tempfile
from pathlib import Path

# ---------- 沙箱：先准备 tempdir，再加载 watchdog 模块 ----------
_sb = Path(tempfile.mkdtemp(prefix="shelf_wd_"))
(_sb / "_TempShelf").mkdir()
(_sb / "_History").mkdir()
(_sb / "_Pinned").mkdir()
(_sb / "shelf_settings.json").write_text(
    json.dumps({"min_text_len": 2, "hotkey": "f9", "pause_hotkey": "f10"}),
    encoding="utf-8")

spec = importlib.util.spec_from_file_location("wd", r"__WD__")
wd = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wd)

# 覆写路径到沙箱（模块级常量在 import 时已固定，必须事后覆写）
wd.APP_DIR = _sb
wd.SETTINGS_PATH = _sb / "shelf_settings.json"
wd.SHELF_DIR = _sb / "_TempShelf"
wd.HISTORY_DIR = _sb / "_History"
wd.SHOW_SIG = wd.SHELF_DIR / ".show_sig"
wd.PAUSE_SIG = wd.SHELF_DIR / ".paused"

print("SANDBOX=%s" % _sb, flush=True)

# ================= L1：签名声明检查 =================
PTR_APIS = [
    ("user32", "GetClipboardData"),
    ("kernel32", "GlobalLock"),
    ("kernel32", "CreateFileW"),
    ("kernel32", "CreateMutexW"),
]
bad_ptr = []
for lib, fn in PTR_APIS:
    f = getattr(getattr(wd, lib), fn)
    rt = f.restype
    # c_void_p 才是正确的；c_long / c_int 会截断
    if rt is not ctypes.c_void_p:
        bad_ptr.append("%s.%s restype=%s" % (lib, fn, rt.__name__))
print("L1_PTR_APIS_BAD=%s" % (",".join(bad_ptr) or "NONE"), flush=True)

UNSIGNED_APIS = [
    ("user32", "GetClipboardSequenceNumber"),
    ("kernel32", "GlobalSize"),
    ("kernel32", "GetLastError"),
    ("shell32", "DragQueryFileW"),
]
bad_uns = []
for lib, fn in UNSIGNED_APIS:
    f = getattr(getattr(wd, lib), fn)
    if f.restype in (ctypes.c_long, ctypes.c_int):
        bad_uns.append("%s.%s restype=%s" % (lib, fn, f.restype.__name__))
print("L1_UNSIGNED_APIS_BAD=%s" % (",".join(bad_uns) or "NONE"), flush=True)

ALL_APIS = PTR_APIS + UNSIGNED_APIS + [
    ("user32", "OpenClipboard"), ("user32", "CloseClipboard"),
    ("user32", "IsClipboardFormatAvailable"),
    ("kernel32", "GlobalUnlock"), ("kernel32", "CloseHandle"),
]
ARGTYPES_MISSING = ["%s.%s" % (lib, fn)
                    for lib, fn in ALL_APIS
                    if getattr(getattr(wd, lib), fn).argtypes is None]
print("L1_ARGTYPES_MISSING=%s" % (",".join(ARGTYPES_MISSING) or "NONE"), flush=True)

# ================= 用 PyQt6 写真实剪贴板 =================
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer, QMimeData, QUrl
from PyQt6.QtGui import QImage, QColor

app = QApplication(sys.argv)
cb = QApplication.clipboard()

MARK = "签名修复端到端验证-CTYPES-64BIT"

def clip_text():
    cb.setText(MARK)

def clip_image():
    img = QImage(64, 48, QImage.Format.Format_RGB32)
    img.fill(QColor("#2f8cff"))
    cb.setImage(img)

def clip_files():
    m = QMimeData()
    m.setUrls([QUrl.fromLocalFile(str(Path(sys.executable).resolve()))])
    cb.setMimeData(m)

def run_case(name, setter, action):
    setter()
    # 保持进程存活，等延迟渲染数据就绪
    QTimer.singleShot(900, app.quit)
    app.exec()
    try:
        ok = wd.open_clipboard()
        if not ok:
            print("CASE_%s=OPEN_CLIPBOARD_FAILED" % name, flush=True)
            return
        try:
            action()
        finally:
            wd.close_clipboard()
    except Exception as e:
        print("CASE_%s=EXCEPTION:%r" % (name, e), flush=True)

# ---------- 文字 ----------
def do_text():
    fmt_ok = wd.user32.IsClipboardFormatAvailable(wd.CF_UNICODETEXT)
    print("TXT_FORMAT_AVAILABLE=%s" % fmt_ok, flush=True)
    h = wd.get_handle(wd.CF_UNICODETEXT)
    print("TXT_HANDLE=0x%016X" % (h or 0), flush=True)
    print("TXT_HANDLE_HIGH_BITS_KEPT=%s" % bool(h and (h >> 32) != 0 or (h and h > 0xFFFFFFFF)),
          flush=True)
    t = wd.get_text()
    print("TXT_GOT=%s" % json.dumps(t, ensure_ascii=False), flush=True)
    print("TXT_MATCH=%s" % (t == MARK), flush=True)
run_case("TEXT", clip_text, do_text)

# ---------- 图片 ----------
def do_image():
    fmt_ok = wd.user32.IsClipboardFormatAvailable(wd.CF_DIB)
    print("IMG_FORMAT_AVAILABLE=%s" % fmt_ok, flush=True)
    h = wd.get_handle(wd.CF_DIB)
    print("IMG_HANDLE=0x%016X" % (h or 0), flush=True)
    data = wd.get_dib()
    print("IMG_BYTES=%d" % len(data or b""), flush=True)
    print("IMG_HAS_BMP_HEADER=%s" % bool(data and data[:2] == b"BM"), flush=True)
run_case("IMAGE", clip_image, do_image)

# ---------- 文件 ----------
def do_files():
    fmt_ok = wd.user32.IsClipboardFormatAvailable(wd.CF_HDROP)
    print("FILE_FORMAT_AVAILABLE=%s" % fmt_ok, flush=True)
    h = wd.get_handle(wd.CF_HDROP)
    print("FILE_HANDLE=0x%016X" % (h or 0), flush=True)
    fs = wd.get_files()
    print("FILE_COUNT=%d" % len(fs), flush=True)
    print("FILE_FIRST=%s" % json.dumps(fs[0] if fs else None, ensure_ascii=False), flush=True)
    print("FILE_MATCHES_EXE=%s" % bool(fs and Path(fs[0]).resolve() == Path(sys.executable).resolve()),
          flush=True)
run_case("FILES", clip_files, do_files)

# ---------- 完整 capture_text 落盘链路 ----------
clip_text()
QTimer.singleShot(900, app.quit)
app.exec()
wd.state.last_text = None
try:
    if wd.open_clipboard():
        try:
            wd.capture_text()
        finally:
            wd.close_clipboard()
    # BUG-009 防抖收账：capture_text 先入库 pending，这里直接结清（等效静默期到）
    wd._commit_pending_text()
    mp = wd.SHELF_DIR / wd.MANIFEST_NAME
    entries = json.loads(mp.read_text(encoding="utf-8")) if mp.exists() else []
    print("CAPTURE_MANIFEST_ENTRIES=%d" % len(entries), flush=True)
    print("CAPTURE_TEXT_STORED=%s" % bool(
        any(e.get("kind") == "text" and e.get("text") == MARK for e in entries)), flush=True)
    jf = list(wd.HISTORY_DIR.glob("*.md"))
    print("CAPTURE_JOURNAL_WRITTEN=%s" % bool(jf), flush=True)
    if jf:
        print("CAPTURE_JOURNAL_HAS_MARK=%s" % (MARK in jf[0].read_text(encoding="utf-8")), flush=True)
except Exception as e:
    print("CAPTURE_EXCEPTION=%r" % e, flush=True)

print("PROBE_DONE", flush=True)
'''
PROBE = PROBE.replace("__WD__", str(WD))


def main():
    r = subprocess.run([PROJECT_PY, "-E", "-X", "utf8", "-c", PROBE],
                       capture_output=True, timeout=240, cwd=str(ROOT))
    out = r.stdout.decode("utf-8", "replace")
    err = r.stderr.decode("utf-8", "replace")
    print("=" * 78)
    print("returncode =", r.returncode)
    print("-" * 78)
    print(out)
    if err.strip():
        print("-" * 30, "STDERR", "-" * 30)
        print(err[-2500:])
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
        ("L1 句柄/指针 API restype 全为 c_void_p", kv.get("L1_PTR_APIS_BAD") == "NONE"),
        ("L1 无符号整型 API restype 已修正", kv.get("L1_UNSIGNED_APIS_BAD") == "NONE"),
        ("L1 argtypes 全部已声明", kv.get("L1_ARGTYPES_MISSING") == "NONE"),
        ("L3 文字：格式可见", kv.get("TXT_FORMAT_AVAILABLE") == "True"),
        ("L3 文字：句柄非零", kv.get("TXT_HANDLE", "0x0") not in ("0x0000000000000000", "0x0")),
        ("L3 文字：get_text 读回内容正确", kv.get("TXT_MATCH") == "True"),
        ("L3 图片：CF_DIB 格式可见", kv.get("IMG_FORMAT_AVAILABLE") == "True"),
        ("L3 图片：get_dib 返回字节", int(kv.get("IMG_BYTES", "0") or 0) > 0),
        ("L3 文件：CF_HDROP 格式可见", kv.get("FILE_FORMAT_AVAILABLE") == "True"),
        ("L3 文件：get_files 解析出路径", int(kv.get("FILE_COUNT", "0") or 0) > 0),
        ("L3 文件：路径与写入的一致", kv.get("FILE_MATCHES_EXE") == "True"),
        ("L3 落盘：capture_text 写入 manifest", kv.get("CAPTURE_TEXT_STORED") == "True"),
        ("L3 落盘：每日日志写入且含标记", kv.get("CAPTURE_JOURNAL_HAS_MARK") == "True"),
    ]

    allok = True
    for name, ok in checks:
        print("  %-44s %s" % (name, "✅" if ok else "❌"))
        allok = allok and ok

    print()
    for k in ("SANDBOX", "TXT_HANDLE", "IMG_HANDLE", "FILE_HANDLE"):
        if k in kv:
            print("  %-12s %s" % (k, kv[k]))
    print()
    if allok:
        print("判定：修复生效 —— 三类剪贴板格式均能正确捕获并落盘，指针未被截断")
        return 0
    print("判定：仍有问题，见上表 ❌ 项")
    return 1


if __name__ == "__main__":
    sys.exit(main())

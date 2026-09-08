#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
E2E 实测：验证【打包版看守 exe】的剪贴板捕获是否真正工作。

背景（为什么必须做这个实测）：
    BUG-005 之前，watchdog.pyw 全文没有任何 restype/argtypes 声明，
    GetClipboardData 返回的 8 字节句柄被 ctypes 默认 c_long 截断成 4 字节，
    三类格式（文本/图片/文件）的捕获【全部静默失效】——进程活着、热键注册了、
    日志写着"循环异常(已忽略)"，但 manifest 永远不增长。这种失效没有任何
    报错，只有真的写一次剪贴板、再去看数据目录有没有落盘，才能证明。

    所以本脚本走完整链路：真实 Win32 写剪贴板 -> 等看守轮询 -> 读隔离目录的
    manifest 与每日日志，逐项断言。

隔离保证：
    看守 exe 在 frozen 模式下把 APP_DIR 解析为 sys.executable 的父目录，
    因此数据落在 ROOT（/tmp/e2e_dist）下，绝不触碰真实数据目录。
    脚本只读 ROOT 下的文件，不读也不写项目目录的 _TempShelf / _History。
"""
import ctypes
import ctypes.wintypes as wt
import json
import struct
import sys
import time
from pathlib import Path

ROOT = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/e2e_dist")
SHELF = ROOT / "_TempShelf"
HIST = ROOT / "_History"
MANIFEST = SHELF / ".manifest.json"

TEXT_MARK = "E2E打包版实测-文本捕获-9F3KQ2MZ"

# ---- Win32 签名：本脚本自己也不能犯 BUG-005 的错，全部显式声明 ----
u = ctypes.windll.user32
k = ctypes.windll.kernel32

u.OpenClipboard.argtypes = [wt.HWND]
u.OpenClipboard.restype = wt.BOOL
u.CloseClipboard.restype = wt.BOOL
u.EmptyClipboard.restype = wt.BOOL
u.GetClipboardData.restype = ctypes.c_void_p
u.GetClipboardData.argtypes = [wt.UINT]
u.SetClipboardData.restype = ctypes.c_void_p
u.SetClipboardData.argtypes = [wt.UINT, ctypes.c_void_p]

k.GlobalAlloc.restype = ctypes.c_void_p
k.GlobalAlloc.argtypes = [wt.UINT, ctypes.c_size_t]
k.GlobalLock.restype = ctypes.c_void_p
k.GlobalLock.argtypes = [ctypes.c_void_p]
k.GlobalUnlock.argtypes = [ctypes.c_void_p]
k.GlobalUnlock.restype = wt.BOOL

GMEM_MOVEABLE = 0x0002
CF_UNICODETEXT = 13
CF_DIB = 8
CF_HDROP = 15


def set_text(s: str) -> bool:
    """写入 CF_UNICODETEXT。"""
    if not u.OpenClipboard(None):
        return False
    try:
        u.EmptyClipboard()
        raw = (s + "\x00").encode("utf-16-le")
        h = k.GlobalAlloc(GMEM_MOVEABLE, len(raw))
        if not h:
            return False
        p = k.GlobalLock(h)
        if not p:
            return False
        ctypes.memmove(p, raw, len(raw))
        k.GlobalUnlock(h)
        return bool(u.SetClipboardData(CF_UNICODETEXT, h))
    finally:
        u.CloseClipboard()


def set_dib(w: int, h: int) -> bool:
    """构造真 BMP DIB（BITMAPINFOHEADER + BGRA 像素）写入 CF_DIB。

    biHeight 用 2h 表示 top-down 32bpp（看守按 BITMAPINFOHEADER 解析）。
    """
    if not u.OpenClipboard(None):
        return False
    try:
        u.EmptyClipboard()
        header = struct.pack("<IiiHHIIiiII", 40, w, h * 2, 1, 32, 0, w * h * 4, 0, 0, 0, 0)
        pixel = struct.pack("BBBB", 200, 120, 40, 255) * (w * h)
        blob = header + pixel
        hb = k.GlobalAlloc(GMEM_MOVEABLE, len(blob))
        if not hb:
            return False
        p = k.GlobalLock(hb)
        if not p:
            return False
        ctypes.memmove(p, blob, len(blob))
        k.GlobalUnlock(hb)
        return bool(u.SetClipboardData(CF_DIB, hb))
    finally:
        u.CloseClipboard()


def set_hdrop(path: str) -> bool:
    """构造 DROPFILES 结构写入 CF_HDROP，验证文件引用捕获（零拷贝）。"""
    if not u.OpenClipboard(None):
        return False
    try:
        u.EmptyClipboard()
        wide = path.encode("utf-16-le") + b"\x00\x00" + b"\x00\x00"
        header = struct.pack("<IIiii", 20, 0, 0, 0, 1)  # pFiles=20, fWide=1
        blob = header + wide
        hb = k.GlobalAlloc(GMEM_MOVEABLE, len(blob))
        if not hb:
            return False
        p = k.GlobalLock(hb)
        if not p:
            return False
        ctypes.memmove(p, blob, len(blob))
        k.GlobalUnlock(hb)
        return bool(u.SetClipboardData(CF_HDROP, hb))
    finally:
        u.CloseClipboard()


def wait_capture(predicate, timeout=6.0, interval=0.3):
    """轮询等待看守落盘，返回是否命中。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if predicate():
                return True
        except (OSError, ValueError):
            pass
        time.sleep(interval)
    return False


def load_manifest():
    if not MANIFEST.exists():
        return []
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def main():
    results = []

    def check(name, ok, detail=""):
        results.append((name, bool(ok), detail))
        flag = "PASS" if ok else "FAIL"
        print("[%s] %s %s" % (flag, name, detail))

    print("=== E2E 打包版看守实测 ===")
    print("隔离根目录:", ROOT)
    print("数据目录:", SHELF)
    print("每日日志:", HIST)
    print()

    # 隔离性前置断言：绝不能指向真实项目目录
    real = Path(r"E:\项目搭建\剪贴板\_TempShelf")
    check("数据目录与真实目录隔离", SHELF.resolve() != real.resolve(),
          str(SHELF.resolve()))

    baseline = len(load_manifest())
    print("起始 manifest 条目:", baseline)
    print()

    # ---- 1) 文本捕获 ----
    check("写入文本剪贴板", set_text(TEXT_MARK))
    got_text = wait_capture(
        lambda: any(e.get("kind") == "text" and TEXT_MARK in (e.get("text") or "")
                    for e in load_manifest())
    )
    check("看守捕获文本并落盘 manifest", got_text)

    # ---- 2) 图片捕获 ----
    check("写入 DIB 图片剪贴板", set_dib(32, 24))
    got_img = wait_capture(
        lambda: any(e.get("kind") == "image" for e in load_manifest()[baseline:])
    )
    check("看守捕获图片并落盘 manifest", got_img)
    img_files = sorted(p.name for p in SHELF.iterdir()
                       if p.suffix.lower() in (".bmp", ".png", ".jpg")) if SHELF.exists() else []
    check("图片文件实体已写入隔离目录", bool(img_files), str(img_files))
    if img_files:
        blob = (SHELF / img_files[0]).read_bytes()
        check("图片非空且有位图头", len(blob) > 40 and blob[:2] in (b"BM", b"\x28\x00"),
              "%d bytes head=%s" % (len(blob), blob[:4].hex()))

    # ---- 3) 文件引用捕获（零拷贝）----
    target = ROOT / "轻松剪贴板.exe"
    check("写入 HDROP 文件剪贴板", set_hdrop(str(target.resolve())))
    got_file = wait_capture(
        lambda: any(e.get("kind") == "file" for e in load_manifest()[baseline:])
    )
    check("看守捕获文件引用并落盘 manifest", got_file)
    file_entries = [e for e in load_manifest() if e.get("kind") == "file"]
    if file_entries:
        e = file_entries[-1]
        check("文件条目是引用而非拷贝(带 src 且目录内无副本)",
              bool(e.get("src")) and not (SHELF / Path(str(e.get("src"))).name).exists(),
              "src=%r" % (e.get("src") or "")[:80])

    # ---- 4) 每日日志 ----
    journals = sorted(HIST.glob("*.md")) if HIST.exists() else []
    check("每日日志已生成", bool(journals), str([j.name for j in journals]))
    if journals:
        jtxt = journals[-1].read_text(encoding="utf-8")
        check("每日日志含本次测试文本", TEXT_MARK in jtxt)
        check("每日日志永不自动清除(未被覆盖为0)", len(jtxt) > 0, "%d chars" % len(jtxt))

    # ---- 5) 隔离目录最终状态 ----
    final = load_manifest()
    print()
    print("=== 最终 manifest（%d 条，新增 %d）===" % (len(final), len(final) - baseline))
    for e in final[baseline:]:
        kk = e.get("kind")
        desc = (e.get("text") or "")[:44] if kk == "text" else (e.get("name") or "")
        print("  [%s] ts=%s %r" % (kk, e.get("ts"), desc))
    print()
    print("=== 隔离目录文件清单 ===")
    for p in sorted(SHELF.iterdir()):
        print("  %-42s %d" % (p.name, p.stat().st_size if p.is_file() else -1))

    passed = sum(1 for _, ok, _ in results if ok)
    total = len(results)
    print()
    print("=" * 60)
    print("E2E 结果: %d/%d 通过" % (passed, total))
    for name, ok, _ in results:
        if not ok:
            print("  FAILED:", name)
    print("=" * 60)
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())

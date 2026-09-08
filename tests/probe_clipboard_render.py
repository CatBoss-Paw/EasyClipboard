#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
判定 test_win32_signatures.py 的 L3 图片/文件断言为何稳定失败。

矛盾事实（必须先解释掉，否则无法判断是产品回归还是测试缺陷）：
    - e2e_packaged_capture.py 用【真实 Win32】写剪贴板：13/13 全通过，
      DIB 图片真的被看守捕获成 3126 bytes 带 BM 头
    - test_win32_signatures.py 的 L3 用【Qt QClipboard.setImage】写：
      IMG_HANDLE=0x0000000000000000 稳定复现（连跑 3 次都一样）
    - 同一个测试里 TXT_HANDLE 却是正常的非零值

唯一差异 = 写入方式。假设：
    Qt 在 Windows 上用 OLE 剪贴板 + 【延迟渲染】：setImage 只是登记了格式
    （SetClipboardData(fmt, NULL)），真实字节要等有人请求时，由 Windows 发
    WM_RENDERFORMAT / OLE 调 IDataObject::GetData，而【这必须由 Qt 的事件
    循环来处理】。
    该测试的结构是：
        cb.setImage(img)
        QTimer.singleShot(900, app.quit); app.exec()   # 循环跑完就退出
        wd.open_clipboard(); wd.get_handle(CF_DIB)     # 循环已停！
    循环停了就没人渲染 -> GetClipboardData 返回 NULL。
    文本能过，是因为 Qt 对 CF_UNICODETEXT 通常是【立即渲染】的（小数据）。

本探针把「循环内读」和「循环外读」做对照，直接证伪或证实。
"""
import ctypes
import ctypes.wintypes as wt
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PyQt6.QtWidgets import QApplication          # noqa: E402
from PyQt6.QtGui import QImage, QColor            # noqa: E402
from PyQt6.QtCore import QUrl, QTimer, Qt, QMimeData  # noqa: E402
# 注：QMimeData 在 PyQt6 里属于 QtCore，不是 QtGui（踩过一次 ImportError）

u = ctypes.windll.user32
k = ctypes.windll.kernel32
u.OpenClipboard.argtypes = [wt.HWND]
u.OpenClipboard.restype = wt.BOOL
u.CloseClipboard.restype = wt.BOOL
u.GetClipboardData.restype = ctypes.c_void_p
u.GetClipboardData.argtypes = [wt.UINT]
u.IsClipboardFormatAvailable.argtypes = [wt.UINT]
u.IsClipboardFormatAvailable.restype = wt.BOOL
u.EmptyClipboard.restype = wt.BOOL
u.SetClipboardData.restype = ctypes.c_void_p
u.SetClipboardData.argtypes = [wt.UINT, ctypes.c_void_p]
k.GlobalAlloc.restype = ctypes.c_void_p
k.GlobalAlloc.argtypes = [wt.UINT, ctypes.c_size_t]
k.GlobalLock.restype = ctypes.c_void_p
k.GlobalLock.argtypes = [ctypes.c_void_p]
k.GlobalUnlock.argtypes = [ctypes.c_void_p]

CF_DIB, CF_HDROP, CF_UNICODETEXT = 8, 15, 13
GMEM_MOVEABLE = 0x0002


def probe(tag):
    ok = u.OpenClipboard(None)
    if not ok:
        print("  [%s] OpenClipboard FAILED" % tag)
        return
    try:
        for name, fmt in (("CF_UNICODETEXT", CF_UNICODETEXT),
                          ("CF_DIB", CF_DIB),
                          ("CF_HDROP", CF_HDROP)):
            avail = bool(u.IsClipboardFormatAvailable(fmt))
            h = u.GetClipboardData(fmt)
            print("  [%s] %-14s avail=%-5s handle=0x%016X"
                  % (tag, name, avail, h or 0))
    finally:
        u.CloseClipboard()


def set_dib_win32(w, h):
    """真实 Win32 写入 DIB（立即有字节，不依赖任何事件循环）。"""
    u.OpenClipboard(None)
    u.EmptyClipboard()
    header = struct.pack("<IiiHHIIiiII", 40, w, h * 2, 1, 32, 0, w * h * 4,
                         0, 0, 0, 0)
    pixels = struct.pack("BBBB", 200, 120, 40, 255) * (w * h)
    blob = header + pixels
    hb = k.GlobalAlloc(GMEM_MOVEABLE, len(blob))
    p = k.GlobalLock(hb)
    ctypes.memmove(p, blob, len(blob))
    k.GlobalUnlock(hb)
    r = u.SetClipboardData(CF_DIB, hb)
    u.CloseClipboard()
    return bool(r)


def main():
    app = QApplication.instance() or QApplication(sys.argv[:1])
    cb = app.clipboard()

    print("=" * 74)
    print("【对照 A】Qt cb.setImage 写入，在【事件循环内】读（singleShot 回调里）")
    print("=" * 74)
    img = QImage(64, 48, QImage.Format.Format_RGB32)
    img.fill(QColor("#2f8cff"))
    cb.setImage(img)

    def read_inside():
        probe("循环内")
        app.quit()

    QTimer.singleShot(500, read_inside)
    app.exec()
    print()

    print("=" * 74)
    print("【对照 B】同一份 Qt 写入，在【事件循环退出后】读（= 该测试的写法）")
    print("=" * 74)
    probe("循环外")
    print()

    print("=" * 74)
    print("【对照 C】真实 Win32 写 DIB，循环外读（= e2e_packaged_capture 的写法）")
    print("=" * 74)
    ok = set_dib_win32(64, 48)
    print("  SetClipboardData(CF_DIB) 返回:", ok)
    probe("win32写")
    print()

    print("=" * 74)
    print("结论判读")
    print("=" * 74)
    print("  若 A 有 CF_DIB 句柄、B 没有 -> 证实【延迟渲染需要事件循环】，")
    print("     test_win32_signatures 的 L3 是【测试写法缺陷】，不是产品回归。")
    print("  若 C 有 CF_DIB 句柄 -> 证实真实 Win32 写入路径完全正常，")
    print("     与 e2e_packaged_capture 13/13 通过一致，看守捕获能力没问题。")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
探查：Qt 的 FramelessWindowHint 窗口在 Win32 层到底是什么样式？
      WM_NCHITTEST 方案能否让四角四边原生缩放？

为什么必须先探查（不靠猜）：
    要让无边框窗口拥有系统级的边缘缩放（含光标箭头、Aero 贴边、
    最大化还原），业界标准做法是覆写 nativeEvent 处理 WM_NCHITTEST，
    在边缘返回 HTLEFT/HTRIGHT/HTTOP/HTBOTTOM/HTTOPLEFT 等命中码。
    但这条路的【前提】是窗口带有 WS_THICKFRAME（可缩放边框）样式 ——
    没有它，Windows 收到 HTLEFT 也不会真的去缩放。

    Qt 6 的 FramelessWindowHint 在 Windows 上究竟给不给 WS_THICKFRAME，
    不同版本行为不一致，必须实测。这决定了我要走哪条实现路线：
      路线1: 已有 WS_THICKFRAME -> 只需 WM_NCHITTEST（最像系统窗口）
      路线2: 没有 -> 需先用 SetWindowLongPtr 补上 WS_THICKFRAME，
                     并调 SetWindowPos(SWP_FRAMECHANGED) 让样式生效
      路线3: 都不行 -> 退回 QWindow.startSystemResize（Qt 自带，
                     光标由 Qt 给，行为接近但不完全是系统原生）

    同时验证 startSystemResize 是否真能改变窗口尺寸（它是路线3的兜底，
    也可能直接就是最优解）。
"""
import ctypes
import ctypes.wintypes as wt
import json
import sys
import tempfile
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="shelf_style_probe_"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import shelf_app                                     # noqa: E402
from PyQt6.QtWidgets import QApplication             # noqa: E402
from PyQt6.QtCore import Qt                          # noqa: E402

u = ctypes.windll.user32
k = ctypes.windll.kernel32
u.GetWindowLongPtrW.restype = ctypes.c_ssize_t
u.GetWindowLongPtrW.argtypes = [wt.HWND, ctypes.c_int]
u.SetWindowLongPtrW.restype = ctypes.c_ssize_t
u.SetWindowLongPtrW.argtypes = [wt.HWND, ctypes.c_int, ctypes.c_ssize_t]
u.SetWindowPos.restype = wt.BOOL
u.SetWindowPos.argtypes = [wt.HWND, wt.HWND, ctypes.c_int, ctypes.c_int,
                           ctypes.c_int, ctypes.c_int, wt.UINT]
dwm = ctypes.windll.dwmapi
# 注：ctypes.wintypes 里没有 HRESULT，它就是个 LONG（踩了一次 AttributeError）
dwm.DwmIsCompositionEnabled.restype = wt.LONG
dwm.DwmIsCompositionEnabled.argtypes = [ctypes.POINTER(wt.BOOL)]

GWL_STYLE, GWL_EXSTYLE = -16, -20
WS_THICKFRAME = 0x00040000
WS_CAPTION = 0x00C00000
WS_POPUP = 0x80000000
WS_BORDER = 0x00800000
WS_MINIMIZEBOX = 0x00020000
WS_MAXIMIZEBOX = 0x00010000
WS_SYSMENU = 0x00080000
SWP_FRAMECHANGED = 0x0020
SWP_NOMOVE = 0x0002
SWP_NOSIZE = 0x0001
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010

STYLE_FLAGS = [
    ("WS_POPUP", WS_POPUP), ("WS_THICKFRAME", WS_THICKFRAME),
    ("WS_CAPTION", WS_CAPTION), ("WS_BORDER", WS_BORDER),
    ("WS_SYSMENU", WS_SYSMENU), ("WS_MINIMIZEBOX", WS_MINIMIZEBOX),
    ("WS_MAXIMIZEBOX", WS_MAXIMIZEBOX),
]


def dump_style(hwnd, tag):
    st = u.GetWindowLongPtrW(hwnd, GWL_STYLE)
    ex = u.GetWindowLongPtrW(hwnd, GWL_EXSTYLE)
    print("  [%s] hwnd=0x%X" % (tag, hwnd))
    print("      style   = 0x%016X" % (st & 0xFFFFFFFFFFFFFFFF))
    print("      exstyle = 0x%016X" % (ex & 0xFFFFFFFFFFFFFFFF))
    on = [n for n, v in STYLE_FLAGS if st & v]
    print("      已置位: %s" % (on or "(无)"))
    print("      WS_THICKFRAME(可缩放边框): %s"
          % ("有 ✅" if st & WS_THICKFRAME else "无 ❌"))
    return st, ex


def isolate():
    s = {
        "shelf_dir": str(TMP / "_TempShelf"),
        "history_dir": str(TMP / "_History"),
        "pinned_dir": str(TMP / "_Pinned"),
        "min_text_len": 2, "auto_clear_hours": 0,
        "hotkey": "f9", "autostart": False,
    }
    (TMP / "shelf_settings.json").write_text(
        json.dumps(s, ensure_ascii=False), encoding="utf-8")
    shelf_app.SETTINGS_PATH = TMP / "shelf_settings.json"
    shelf_app.SHELF_DIR = TMP / "_TempShelf"
    shelf_app.HISTORY_DIR = TMP / "_History"
    shelf_app.PINNED_DIR = TMP / "_Pinned"
    for kk in ("shelf_dir", "history_dir", "pinned_dir"):
        Path(s[kk]).mkdir(parents=True, exist_ok=True)
    real = Path(r"E:\项目搭建\剪贴板\_TempShelf")
    assert Path(s["shelf_dir"]).resolve() != real.resolve()


def main():
    isolate()
    app = QApplication.instance() or QApplication(sys.argv[:1])
    sh = shelf_app.Shelf()
    sh.resize(900, 620)
    sh.show()
    app.processEvents()
    assert Path(shelf_app.SHELF_DIR).resolve() == (TMP / "_TempShelf").resolve()

    hwnd = int(sh.winId())
    print("=" * 76)
    print("【1】Qt FramelessWindowHint 窗口的真实 Win32 样式")
    print("=" * 76)
    st0, ex0 = dump_style(hwnd, "原始")
    print()

    comp = wt.BOOL()
    dwm.DwmIsCompositionEnabled(ctypes.byref(comp))
    print("      DWM 合成开启: %s（影响能否走 Aero 贴边）" % bool(comp.value))
    print()

    # 系统边框厚度：决定原生缩放边框该留多宽
    print("=" * 76)
    print("【2】系统度量（决定命中区宽度）")
    print("=" * 76)
    SM_CXSIZEFRAME, SM_CYSIZEFRAME = 32, 33
    SM_CXPADDEDBORDER = 92
    cx = u.GetSystemMetrics(SM_CXSIZEFRAME)
    cy = u.GetSystemMetrics(SM_CYSIZEFRAME)
    pad = u.GetSystemMetrics(SM_CXPADDEDBORDER)
    print("  SM_CXSIZEFRAME = %d   SM_CYSIZEFRAME = %d" % (cx, cy))
    print("  SM_CXPADDEDBORDER = %d" % pad)
    print("  -> 标准可缩放边框厚度约 %d px（含 padded）" % (cx + pad))
    print("  设备像素比 DPR = %s（4K 屏 200%% 缩放时逻辑像素要乘 DPR）"
          % sh.devicePixelRatioF())
    print()

    # 路线2：补 WS_THICKFRAME 后能否原生缩放
    print("=" * 76)
    print("【3】补 WS_THICKFRAME 后验证（路线2可行性）")
    print("=" * 76)
    new_style = st0 | WS_THICKFRAME
    u.SetWindowLongPtrW(hwnd, GWL_STYLE, new_style)
    u.SetWindowPos(hwnd, None, 0, 0, 0, 0,
                   SWP_FRAMECHANGED | SWP_NOMOVE | SWP_NOSIZE |
                   SWP_NOZORDER | SWP_NOACTIVATE)
    app.processEvents()
    st1, _ = dump_style(hwnd, "补样式后")
    print("  样式是否成功写入: %s" % (bool(st1 & WS_THICKFRAME)))
    # 补样式会不会带出系统标题栏/边框（破坏 frameless 外观）？
    r = wt.RECT()
    u.GetWindowRect(hwnd, ctypes.byref(r))
    cr = wt.RECT()
    u.GetClientRect(hwnd, ctypes.byref(cr))
    print("  窗口矩形 w=%d h=%d ; 客户区 w=%d h=%d"
          % (r.right - r.left, r.bottom - r.top,
             cr.right - cr.left, cr.bottom - cr.top))
    grew = (r.right - r.left) > sh.width() * sh.devicePixelRatioF() + 2
    print("  补样式后是否凭空长出可见边框: %s"
          % ("是 ⚠（会破坏无边框外观，需再补 WS_CAPTION 清除或用 DWM）"
             if grew else "否 ✅（外观不受影响）"))
    print()

    # 路线3：startSystemResize 实测
    print("=" * 76)
    print("【4】QWindow.startSystemResize 实测（路线3兜底）")
    print("=" * 76)
    win = sh.windowHandle()
    print("  windowHandle(): %s" % win)
    print("  有 startSystemResize: %s" % hasattr(win, "startSystemResize"))
    before = (sh.width(), sh.height())
    try:
        ok = win.startSystemResize(Qt.Edge.RightEdge | Qt.Edge.BottomEdge)
        print("  调用返回: %s" % ok)
        app.processEvents()
        after = (sh.width(), sh.height())
        print("  尺寸 %s -> %s（startSystemResize 进入系统模态缩放，"
              "需真实鼠标拖动才改变，返回 True 即表示系统已接管）"
              % (before, after))
    except Exception as e:                              # noqa: BLE001
        print("  调用抛异常: %r" % e)
    print()

    print("=" * 76)
    print("【结论判读】")
    print("=" * 76)
    if st0 & WS_THICKFRAME:
        print("  路线1 可行：窗口已有 WS_THICKFRAME，只需 WM_NCHITTEST")
    elif st1 & WS_THICKFRAME and not grew:
        print("  路线2 可行：补 WS_THICKFRAME 不破坏外观，")
        print("           配合 WM_NCHITTEST 即可获得完全原生的八向缩放")
    else:
        print("  路线3：用 startSystemResize，由 Qt 转发给系统")
    print("=" * 76)

    sh.close()
    app.processEvents()


if __name__ == "__main__":
    main()

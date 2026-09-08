"""纯复现：Shelf 真实窗口 + SendInput，无任何 monkeypatch/插桩。

验证 59620 那种"真实产品形态"下鼠标移入边缘是否稳定、
以及窗口边缘热区收到的光标/事件行为（崩溃则由 native 层 repro）。
"""
import ctypes
import ctypes.wintypes as wt
import json
import sys
import tempfile
import time
from pathlib import Path

import faulthandler
faulthandler.enable()

TMP = Path(tempfile.mkdtemp(prefix="shelf_pure_"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# DPI 感知：GetWindowRect/SendInput 都用物理像素坐标，
# 否则非 aware 进程里坐标被虚拟化减半，鼠标根本没移到窗口边缘。
ctypes.windll.shcore.SetProcessDpiAwareness(2)

import shelf_app as S                          # noqa: E402
from PyQt6.QtWidgets import QApplication       # noqa: E402
from PyQt6.QtCore import Qt                    # noqa: E402


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
    S.SETTINGS_PATH = TMP / "shelf_settings.json"
    S.SHELF_DIR = TMP / "_TempShelf"
    S.HISTORY_DIR = TMP / "_History"
    S.PINNED_DIR = TMP / "_Pinned"
    for k in ("shelf_dir", "history_dir", "pinned_dir"):
        Path(s[k]).mkdir(parents=True, exist_ok=True)
    real = Path(r"E:\项目搭建\剪贴板\_TempShelf")
    assert Path(s["shelf_dir"]).resolve() != real.resolve(), "隔离失败"


def move_mouse_abs(x, y):
    user32 = ctypes.windll.user32

    class MOUSEINPUT(ctypes.Structure):
        _fields_ = [("dx", ctypes.c_long), ("dy", ctypes.c_long),
                    ("mouseData", wt.DWORD), ("dwFlags", wt.DWORD),
                    ("time", wt.DWORD), ("dwExtraInfo", ctypes.c_void_p)]

    class INPUT(ctypes.Structure):
        _fields_ = [("type", wt.DWORD), ("mi", MOUSEINPUT)]

    sw = user32.GetSystemMetrics(0)
    sh = user32.GetSystemMetrics(1)
    i = INPUT(type=0, mi=MOUSEINPUT(
        dx=int(x * 65535 / (sw - 1)), dy=int(y * 65535 / (sh - 1)),
        mouseData=0, dwFlags=0x8001, time=0, dwExtraInfo=None))
    user32.SendInput(1, ctypes.byref(i), ctypes.sizeof(i))


def main():
    isolate()
    app = QApplication.instance() or QApplication(sys.argv[:1])
    sh = S.Shelf()
    sh.resize(560, 480)
    sh.move(80, 80)
    sh.show()
    # 模拟 main：show 后立即 apply_look + 等 60ms singleShot 的 apply_look
    sh.apply_look()
    for _ in range(10):
        time.sleep(0.02)
        app.processEvents()

    dpr = sh.devicePixelRatioF()
    print("dpr:", dpr, flush=True)

    user32 = ctypes.windll.user32
    orig = wt.POINT()
    user32.GetCursorPos(ctypes.byref(orig))
    try:
        user32.LoadCursorW.restype = ctypes.c_void_p
        user32.LoadCursorW.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        pres = {
            "arrow": user32.LoadCursorW(None, 32512),      # IDC_ARROW
            "sizewe(左右)": user32.LoadCursorW(None, 32644),  # IDC_SIZEWE
            "sizens(上下)": user32.LoadCursorW(None, 32645),  # IDC_SIZENS
            "sizenwse(左上右下)": user32.LoadCursorW(None, 32642),  # IDC_SIZENWSE
            "sizenesw(右上左下)": user32.LoadCursorW(None, 32643),  # IDC_SIZENESW
            "hand": user32.LoadCursorW(None, 32649),       # IDC_HAND
        }

        class CURSORINFO(ctypes.Structure):
            _fields_ = [("cbSize", wt.DWORD), ("flags", wt.DWORD),
                        ("hCursor", wt.HANDLE), ("pt", wt.POINT)]

        def current_cursor():
            ci = CURSORINFO()
            ci.cbSize = ctypes.sizeof(ci)
            user32.GetCursorInfo.argtypes = [ctypes.c_void_p]
            user32.GetCursorInfo(ctypes.byref(ci))
            for name, hc in pres.items():
                if ci.hCursor == hc:
                    return name
            return f"other:{ci.hCursor}"

        # 窗口逻辑 (80,80,560,480) → 物理坐标
        spots = {
            "左边缘": (84, 320),
            "右边缘": (636, 320),
            "下边缘": (360, 556),
            "右下角": (634, 554),
            "左下角": (84, 554),
            "右上角": (634, 84),
            "上边缘": (360, 84),
            "窗口中央": (360, 320),
        }
        user32.WindowFromPoint.restype = ctypes.c_void_p
        user32.WindowFromPoint.argtypes = [wt.POINT]
        my_hwnd = user32.WindowFromPoint(wt.POINT(int(84 * dpr), int(320 * dpr)))
        print(f"winId={int(sh.winId())} hwnd@popupTest={my_hwnd}", flush=True)
        for name, (lx, ly) in spots.items():
            move_mouse_abs(int(lx * dpr), int(ly * dpr))
            time.sleep(0.25)
            app.processEvents()
            cp = wt.POINT()
            user32.GetCursorPos(ctypes.byref(cp))
            under = user32.WindowFromPoint(cp)
            mine = "我方窗口" if (under and (under == int(sh.winId()) or user32.IsChild(int(sh.winId()), under))) else f"别家窗口 {under}"
            sw = getattr(sh, "_scaled_cursor_widget", None)
            bc = sh.body.cursor().shape() if sh.body.testAttribute(Qt.WidgetAttribute.WA_SetCursor) else None
            print(f"  {name}: pos=({cp.x},{cp.y}) under={mine} 光标={current_cursor()} body_cursor={bc} scaled={type(sw).__name__ if sw is not None else None}", flush=True)
    finally:
        move_mouse_abs(orig.x, orig.y)

    sh.close()
    print("PUREREPO-OK", flush=True)


if __name__ == "__main__":
    main()

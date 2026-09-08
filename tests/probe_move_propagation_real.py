"""真实链路探针：无按钮 MouseMove 事件能否传播到 Shelf.mouseMoveEvent？

隔离临时数据目录，构造真实显示的 Shelf 窗口，用 SendInput 把鼠标
移到窗口边缘，统计 Shelf.mouseMoveEvent / body 的 MouseMove 是否被调用。

判据：
- 计数=0  → 事件根本没到 Shelf（Qt 不传播无按钮 move），修 eventFilter 层
- 计数>0 但光标没变 → setCursor 层面问题
"""
import ctypes
import ctypes.wintypes as wt
import json
import sys
import tempfile
import time
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="shelf_moveprobe_"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import faulthandler                                 # noqa: E402
faulthandler.enable()                              # 抓原生崩溃的 Python 栈

import shelf_app as S                              # noqa: E402
from PyQt6.QtWidgets import QApplication           # noqa: E402
from PyQt6.QtCore import Qt                        # noqa: E402


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
    app.processEvents()

    # 二分开关：NO_TRACK=1 时关闭 Shelf/body 的 mouseTracking
    import os
    if os.environ.get("NO_TRACK") == "1":
        sh.setMouseTracking(False)
        sh.body.setMouseTracking(False)
        print("[probe] mouseTracking disabled", flush=True)
    if os.environ.get("NO_QSS") == "1":
        sh.setStyleSheet("")
        for w in sh.findChildren(type(sh.body)):
            w.setStyleSheet("")
        print("[probe] stylesheet cleared", flush=True)
    if os.environ.get("NO_GLASS") == "1":
        sh.settings["glass"] = False
        sh.apply_look()
        print("[probe] glass disabled", flush=True)

    # 插桩：统计 Shelf / body 收到的 MouseMove
    counts = {"shelf": 0, "body": 0}
    orig_shelf_move = S.Shelf.mouseMoveEvent

    def wrapped(ev):
        counts["shelf"] += 1
        print("  [move] shelf enter", counts["shelf"], flush=True)
        orig_shelf_move(sh, ev)
        print("  [move] shelf exit", counts["shelf"], flush=True)

    S.Shelf.mouseMoveEvent = wrapped

    from PyQt6.QtWidgets import QFrame
    body = sh.body
    orig_body_move = QFrame.mouseMoveEvent

    def wrapped_body(ev):
        counts["body"] += 1
        orig_body_move(body, ev)

    body.__class__ = body.__class__  # noop；body 是 QFrame，无法按实例 override
    # 改用事件过滤器给 body 计数
    from PyQt6.QtCore import QObject, QEvent

    class BodyCounter(QObject):
        def eventFilter(self, obj, ev):
            if obj is body and ev.type() == QEvent.Type.MouseMove:
                counts["body"] += 1
            return False

    filt = BodyCounter(sh)
    body.installEventFilter(filt)

    # DPI：探针进程非 DPI aware 时 GetWindowRect 返回虚拟化坐标。
    # shelf_app 进程是 DPI aware（DPR=2），我们移鼠标用物理坐标，
    # 直接用 geometry 物理：窗口 (80,80) 是逻辑，物理=逻辑*2（DPR=2.0）
    dpr = sh.devicePixelRatioF()
    print("dpr:", dpr)
    geo = sh.geometry()
    print("logic geo:", geo)

    # 物理坐标下的窗口边缘测试点（左边中点）
    px = int((geo.x() + 4) * dpr)
    py = int((geo.y() + geo.height() // 2) * dpr)
    print("moving mouse to phys:", px, py)

    user32 = ctypes.windll.user32
    orig_pt = wt.POINT()
    user32.GetCursorPos(ctypes.byref(orig_pt))

    try:
        for dx in (4, 6, 8, 200, 300):
            move_mouse_abs(int((geo.x() + dx) * dpr), py)
            time.sleep(0.15)
            app.processEvents()
        time.sleep(0.3)
        app.processEvents()
    finally:
        move_mouse_abs(orig_pt.x, orig_pt.y)

    print("mouseMoveEvent counts:", counts)
    sh.close()
    print("VERDICT:",
          "事件到达了 Shelf.mouseMoveEvent" if counts["shelf"] else
          ("事件只到了 body，未传播到 Shelf" if counts["body"]
           else "连 body 都没收到（mouseTracking 问题）"))


if __name__ == "__main__":
    main()

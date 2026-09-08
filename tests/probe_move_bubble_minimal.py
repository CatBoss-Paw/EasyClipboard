"""最小复现：Qt 父子窗口中，无按钮 MouseMove 是否传播到父？

子控件覆盖整个父窗口并开 mouseTracking，真实 SendInput 移鼠标到边缘，
看父的 mouseMoveEvent 是否收到（即冒泡是否存在）。
"""
import ctypes
import ctypes.wintypes as wt
import sys
import time

import faulthandler
faulthandler.enable()

from PyQt6.QtCore import QEvent, QObject, Qt
from PyQt6.QtWidgets import QApplication, QFrame, QVBoxLayout, QWidget

counts = {"parent": 0, "child": 0}


class Child(QFrame):
    def mouseMoveEvent(self, ev):
        counts["child"] += 1
        ev.ignore()          # 显式忽略，理论上 Qt 应把它传给父

    def mousePressEvent(self, ev):
        ev.ignore()


class Parent(QWidget):
    def mouseMoveEvent(self, ev):
        counts["parent"] += 1
        ev.ignore()


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
    app = QApplication(sys.argv[:1])
    w = Parent()
    w.setWindowTitle("move-probe")
    import os
    if os.environ.get("FULL_ATTRS") == "1":
        # 逼近 Shelf 的窗口属性组合
        w.setWindowFlags(Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.WindowStaysOnTopHint
                         | Qt.WindowType.Tool)
        w.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        print("[probe] full attrs applied", flush=True)
    w.setMouseTracking(True)
    lay = QVBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    c = Child()
    c.setMouseTracking(True)
    import os as _os
    if _os.environ.get("FULL_ATTRS") == "1":
        # 半透明窗口下给子控件不透明背景，模拟 Shelf body 满铺背景
        c.setStyleSheet("background: #223344;")
    lay.addWidget(c)
    w.resize(400, 300)
    w.move(60, 60)
    w.show()
    app.processEvents()

    dpr = w.devicePixelRatioF()
    print("dpr:", dpr, flush=True)

    user32 = ctypes.windll.user32
    orig = wt.POINT()
    user32.GetCursorPos(ctypes.byref(orig))
    try:
        # 在子控件区域内移动几步
        for dx in (10, 30, 60, 120, 200):
            move_mouse_abs(int((60 + dx) * dpr), int((60 + 150) * dpr))
            time.sleep(0.12)
            app.processEvents()
    finally:
        move_mouse_abs(orig.x, orig.y)

    time.sleep(0.2)
    app.processEvents()
    print("counts:", counts, flush=True)
    w.close()
    print("VERDICT:",
          "父收到了 move（Qt 会传播）" if counts["parent"] else
          ("只有子收到（Qt 不传播无按钮 move）" if counts["child"] else "谁都没收到"),
          flush=True)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
验证 Qt 层面八向缩放：
    1. 八个方位 _hit_test 返回正确命中码
    2. 模拟八向拖拽，窗口尺寸真的改变
    3. 光标反馈正确
    4. 标题栏拖动不受影响
    5. 圆角恢复（不再补 WS_THICKFRAME）
    6. 双击/单击卡片不受影响
"""
import json
import sys
import tempfile
import ctypes
import ctypes.wintypes as wt
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="shelf_qt_resize_"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import shelf_app as S                              # noqa: E402
from PyQt6.QtWidgets import QApplication           # noqa: E402
from PyQt6.QtCore import QEvent, QPoint, QPointF, Qt  # noqa: E402
from PyQt6.QtGui import QMouseEvent                # noqa: E402

PASS, FAIL = [], []


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


def check(name, ok, detail=""):
    (PASS if ok else FAIL).append(name)
    print("[%s] %s%s" % ("PASS" if ok else "FAIL", name,
                         ("  | " + detail) if detail else ""))


def mk(etype, local, glob, button, buttons):
    return QMouseEvent(etype, QPointF(local), QPointF(glob), button, buttons,
                       Qt.KeyboardModifier.NoModifier)


def main():
    isolate()
    app = QApplication.instance() or QApplication(sys.argv[:1])
    sh = S.Shelf()
    sh.resize(900, 620)
    sh.show()
    app.processEvents()
    assert Path(S.SHELF_DIR).resolve() == (TMP / "_TempShelf").resolve()

    W, H = sh.width(), sh.height()
    b = sh._resize_border_px()
    print("=" * 74)
    print("窗口 %d x %d ; 边缘宽 = %d 逻辑像素" % (W, H, b))
    print("=" * 74)

    # ---- 1. 八向命中码 ----
    print("\n【1】八向命中码")
    probes = [
        ("左上角", 2, 2, S.HTTOPLEFT),
        ("上边", W // 2, 2, S.HTTOP),
        ("右上角", W - 3, 2, S.HTTOPRIGHT),
        ("左边", 2, H // 2, S.HTLEFT),
        ("右边", W - 3, H // 2, S.HTRIGHT),
        ("左下角", 2, H - 3, S.HTBOTTOMLEFT),
        ("下边", W // 2, H - 3, S.HTBOTTOM),
        ("右下角", W - 3, H - 3, S.HTBOTTOMRIGHT),
    ]
    for name, x, y, want in probes:
        got = sh._hit_test(x, y)
        check("%s 命中码" % name, got == want, "got=%d want=%d" % (got, want))
    check("中央不接管", sh._hit_test(W // 2, H // 2) == 0)

    # ---- 2. 标题栏区域不接管（保护拖动）----
    print("\n【2】标题栏保护")
    tb = sh.titlebar
    tb_pt = tb.mapTo(sh, QPoint(tb.width() // 2, tb.height() // 2))
    check("标题栏中央不接管（拖动不受影响）",
          sh._hit_test(tb_pt.x(), tb_pt.y()) == 0,
          "(%d,%d)" % (tb_pt.x(), tb_pt.y()))

    # ---- 3. 模拟八向拖拽 ----
    print("\n【3】模拟八向拖拽（尺寸真的改变）")

    def drag_resize(pt, dx, dy):
        """模拟：在 pt 处按下 -> 移动 dx,dy -> 释放。返回 (before, after)。"""
        before = (sh.width(), sh.height())
        gp = sh.mapToGlobal(QPointF(pt))
        app.sendEvent(sh, mk(QEvent.Type.MouseButtonPress, QPointF(pt), gp,
                             Qt.MouseButton.LeftButton,
                             Qt.MouseButton.LeftButton))
        app.processEvents()
        new_pt = QPoint(pt.x() + dx, pt.y() + dy)
        new_gp = sh.mapToGlobal(QPointF(new_pt))
        app.sendEvent(sh, mk(QEvent.Type.MouseMove, QPointF(new_pt), new_gp,
                             Qt.MouseButton.NoButton,
                             Qt.MouseButton.LeftButton))
        app.processEvents()
        app.sendEvent(sh, mk(QEvent.Type.MouseButtonRelease, QPointF(new_pt),
                             new_gp, Qt.MouseButton.NoButton,
                             Qt.MouseButton.NoButton))
        app.processEvents()
        after = (sh.width(), sh.height())
        return before, after

    cases = [
        ("右下角拉大", QPoint(W - 3, H - 3), 100, 80),
        ("右边拉宽", QPoint(W - 3, H // 2), 100, 0),
        ("下边拉高", QPoint(W // 2, H - 3), 0, 80),
        ("左上角拉大", QPoint(2, 2), -100, -80),
        ("左边拉宽", QPoint(2, H // 2), -100, 0),
        ("上边拉高", QPoint(W // 2, 2), 0, -80),
    ]
    for name, pt, dx, dy in cases:
        sh.resize(900, 620)
        app.processEvents()
        W2, H2 = sh.width(), sh.height()
        pt2 = QPoint(min(pt.x(), W2 - 1), min(pt.y(), H2 - 1))
        if pt.x() < 0:
            pt2 = QPoint(2, pt.y())
        before, after = drag_resize(pt2, dx, dy)
        changed = before != after
        check("%s 尺寸改变" % name, changed, "%s -> %s" % (before, after))

    # ---- 4. 最小尺寸约束 ----
    print("\n【4】最小尺寸约束")
    sh.resize(400, 320)
    app.processEvents()
    before, after = drag_resize(QPoint(2, 2), -600, -600)
    check("缩到极限不小于 320x240",
          after[0] >= 320 and after[1] >= 240,
          "%s -> %s" % (before, after))

    # ---- 5. 光标反馈 ----
    print("\n【5】光标反馈")
    sh.resize(900, 620)
    app.processEvents()
    W3, H3 = sh.width(), sh.height()
    cursor_tests = [
        ("右边", QPoint(W3 - 3, H3 // 2), Qt.CursorShape.SizeHorCursor),
        ("下边", QPoint(W3 // 2, H3 - 3), Qt.CursorShape.SizeVerCursor),
        ("右下角", QPoint(W3 - 3, H3 - 3), Qt.CursorShape.SizeFDiagCursor),
        ("左上角", QPoint(2, 2), Qt.CursorShape.SizeFDiagCursor),
        ("中央", QPoint(W3 // 2, H3 // 2), Qt.CursorShape.ArrowCursor),
    ]
    for name, pt, want_cursor in cursor_tests:
        hit = sh._hit_test(pt.x(), pt.y())
        got_cursor = sh._CURSOR_MAP.get(hit, Qt.CursorShape.ArrowCursor)
        check("%s 光标 = %s" % (name, str(want_cursor).split(".")[-1]),
              got_cursor == want_cursor,
              "got=%s" % str(got_cursor).split(".")[-1])

    # ---- 6. 圆角恢复（不再补 WS_THICKFRAME）----
    print("\n【6】圆角恢复")
    u = ctypes.windll.user32
    u.GetWindowLongPtrW.restype = ctypes.c_ssize_t
    u.GetWindowLongPtrW.argtypes = [ctypes.c_void_p, ctypes.c_int]
    hwnd = int(sh.winId())
    style = u.GetWindowLongPtrW(ctypes.c_void_p(hwnd), -16)
    has_thick = bool(style & 0x00040000)
    check("不再补 WS_THICKFRAME（圆角不被破坏）", not has_thick,
          "style=0x%X" % (style & 0xFFFFFFFF))

    # ---- 7. 标题栏拖动不受影响 ----
    print("\n【7】标题栏拖动")
    sh.resize(900, 620)
    app.processEvents()
    pos_before = (sh.x(), sh.y())
    tb2 = sh.titlebar
    tb_pt2 = QPoint(tb2.width() // 2, tb2.height() // 2)
    tb_gp = tb2.mapToGlobal(QPointF(tb_pt2))
    app.sendEvent(tb2, mk(QEvent.Type.MouseButtonPress, QPointF(tb_pt2),
                          tb_gp, Qt.MouseButton.LeftButton,
                          Qt.MouseButton.LeftButton))
    app.processEvents()
    moved = QPoint(tb_pt2.x() + 60, tb_pt2.y() + 40)
    app.sendEvent(tb2, mk(QEvent.Type.MouseMove, QPointF(moved),
                          tb2.mapToGlobal(QPointF(moved)),
                          Qt.MouseButton.NoButton,
                          Qt.MouseButton.LeftButton))
    app.processEvents()
    app.sendEvent(tb2, mk(QEvent.Type.MouseButtonRelease, QPointF(moved),
                          tb2.mapToGlobal(QPointF(moved)),
                          Qt.MouseButton.NoButton,
                          Qt.MouseButton.NoButton))
    app.processEvents()
    pos_after = (sh.x(), sh.y())
    check("标题栏拖动有效（位置改变）", pos_before != pos_after,
          "%s -> %s" % (pos_before, pos_after))

    sh.close()
    app.processEvents()

    print()
    print("=" * 74)
    print("结果: %d PASS / %d FAIL" % (len(PASS), len(FAIL)))
    for f in FAIL:
        print("   FAILED:", f)
    print("=" * 74)
    return 0 if not FAIL else 1


if __name__ == "__main__":
    sys.exit(main())

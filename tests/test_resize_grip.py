#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
右下角缩放把手的真实路径验证（修复前后都跑这个）。

【判据为什么必须这样设计】
    第一版我用 app.sendEvent(sh, press) 直接发给 Shelf，测出"缩放有效"
    (760x560 -> 880x650)，于是以为把手是好的。但那是错的：
      - 真实鼠标路径是「先发给 childAt() 命中的子控件，子控件不消费才冒泡到父」
      - 直接发给 Shelf 绕过了这一步，等于自己给自己喂事件
      - 而且 sendEvent 无法区分事件是否被吃掉（对照组 QPushButton 也报
        "父收到 press"），判据本身无效
    所以本版改用两个硬指标：
      1) 事件发给 childAt() 命中的真实控件（复刻系统分发）
      2) 看 Shelf._resizing 是否被置位 + 窗口尺寸是否真的变了
    _resizing 只有 mousePressEvent 里命中热区才会置 True，是无可辩驳的证据。

【实测出的根因】
    ◢ 视觉把手 QRect(867,593,18,14)  vs  功能热区 QRect(882,602,18,18)
    交集只有 3x5=15 像素 -> 按住 ◢ 只有 6.0% 的概率真能缩放。
    原因：v.setContentsMargins(14,10,14,12) 把 ◢ 推进窗口内侧，
          而 _near_resize_corner 从窗口边缘算 18px，两者错开 15px/9px。

用法：python tests/test_resize_grip.py
安全：数据根隔离到临时目录，绝不触碰真实 _TempShelf / _History。

【过时标注】◢ 缩放把手（grab_handle + _begin_grip_resize）在 Qt 八向
缩放重写时已被整体移除：现在四条边 + 四个角全可缩放（热区由 _hit_test
判定），不再需要右下角单独把手。本测试针对已删除的功能，改为 SKIP
直接退出，避免误报为产品回归。现行覆盖见 tests/test_qt_resize.py
（八向热区）与 tests/test_cursor_edge_filter.py（悬停光标反馈）。
"""
import json
import sys
import tempfile
from pathlib import Path

import sys as _sys2
print("SKIP: ◢缩放把手已被 Qt 八向缩放替代（grab_handle/_begin_grip_resize 已删除），")
print("      现行覆盖：tests/test_qt_resize.py + tests/test_cursor_edge_filter.py")
_sys2.exit(0)

TMP = Path(tempfile.mkdtemp(prefix="shelf_grip_test_"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import shelf_app                                          # noqa: E402
from PyQt6.QtWidgets import QApplication                  # noqa: E402
from PyQt6.QtCore import QEvent, QPoint, QPointF, QRect, Qt  # noqa: E402
from PyQt6.QtGui import QMouseEvent                       # noqa: E402

PASS, FAIL = [], []


def isolate():
    s = {
        "shelf_dir": str(TMP / "_TempShelf"),
        "history_dir": str(TMP / "_History"),
        "pinned_dir": str(TMP / "_Pinned"),
        "min_text_len": 2, "auto_clear_hours": 0,
        "hotkey": "f9", "autostart": False,
    }
    f = TMP / "shelf_settings.json"
    f.write_text(json.dumps(s, ensure_ascii=False), encoding="utf-8")
    shelf_app.SETTINGS_PATH = f
    for k in ("shelf_dir", "history_dir", "pinned_dir"):
        Path(s[k]).mkdir(parents=True, exist_ok=True)
    real = Path(r"E:\项目搭建\剪贴板\_TempShelf")
    assert Path(s["shelf_dir"]).resolve() != real.resolve(), "隔离失败"
    return s


def mk(etype, local, glob, button, buttons):
    return QMouseEvent(etype, QPointF(local), QPointF(glob), button, buttons,
                       Qt.KeyboardModifier.NoModifier)


def reset_size(sh, app, w=900, h=620):
    """把窗口恢复到已知尺寸并重算布局（每次拖拽用例前必须调用，否则
    上一次拖拽改变的尺寸会让后续硬编码坐标失效）。"""
    sh.resize(w, h)
    app.processEvents()
    sh._resizing = False


def visual_grip_rect(sh):
    """◢ 在当前布局下的实际矩形（Shelf 坐标系）。"""
    lab = sh.size_hint_lab
    tl = lab.mapTo(sh, QPoint(0, 0))
    return QRect(tl.x(), tl.y(), lab.width(), lab.height())


def drag_resize(sh, app, target_pt, dx=140, dy=110):
    """复刻真实鼠标路径：事件发给 childAt() 命中的控件，靠冒泡到 Shelf。

    返回 (started, size_before, size_after, receiver_cls)。
    started = _resizing 是否被置位（命中热区的铁证）。
    【调用前必须先 reset_size + 重新取坐标】，否则上一次拖拽改变的窗口尺寸
    会让 target_pt 指向错误位置。
    """
    sh._resizing = False
    receiver = sh.childAt(target_pt) or sh
    local = receiver.mapFrom(sh, target_pt)
    gp = receiver.mapToGlobal(QPointF(local))

    app.sendEvent(receiver, mk(QEvent.Type.MouseButtonPress, QPointF(local),
                               QPointF(gp), Qt.MouseButton.LeftButton,
                               Qt.MouseButton.LeftButton))
    app.processEvents()
    started = bool(getattr(sh, "_resizing", False))

    before = (sh.width(), sh.height())
    # 缩放期间 Shelf 调了 grabMouse()，后续 MouseMove 会直接发给 Shelf 本身；
    # 未命中热区时（started=False）事件仍归 receiver，两者都要试到。
    if started:
        receiver2 = sh
        lp = QPointF(sh.mapFromGlobal(QPoint(int(gp.x()) + dx,
                                             int(gp.y()) + dy)))
    else:
        receiver2 = receiver
        lp = QPointF(local.x() + dx, local.y() + dy)
    gl = receiver2.mapToGlobal(lp)
    app.sendEvent(receiver2, mk(QEvent.Type.MouseMove, lp, gl,
                               Qt.MouseButton.NoButton,
                               Qt.MouseButton.LeftButton))
    app.processEvents()
    after = (sh.width(), sh.height())

    app.sendEvent(receiver2, mk(QEvent.Type.MouseButtonRelease, lp, gl,
                                Qt.MouseButton.NoButton,
                                Qt.MouseButton.NoButton))
    app.processEvents()
    after = (sh.width(), sh.height())
    sh._resizing = False
    return started, before, after, type(receiver).__name__


def check(name, ok, detail=""):
    (PASS if ok else FAIL).append(name)
    print("[%s] %s%s" % ("PASS" if ok else "FAIL", name,
                         ("  | " + detail) if detail else ""))


def main():
    isolate()
    app = QApplication.instance() or QApplication(sys.argv[:1])
    sh = shelf_app.Shelf()
    sh.resize(900, 620)
    sh.show()
    app.processEvents()
    assert Path(shelf_app.SHELF_DIR).resolve() == Path(
        TMP / "_TempShelf").resolve(), "隔离失败"

    W, H = sh.width(), sh.height()
    visual = visual_grip_rect(sh)
    print("=" * 78)
    print("窗口 %d x %d ; ◢ 视觉把手 %s ; tooltip=%r"
          % (W, H, str(visual), sh.size_hint_lab.toolTip()))
    print("=" * 78)
    print()

    # ---- 1. 按住 ◢ 的【中心】必须能缩放（用户的真实操作）----
    reset_size(sh, app)
    center = visual_grip_rect(sh).center()
    started, before, after, recv = drag_resize(sh, app, center)
    print("按住 ◢ 中心 (%d,%d)  事件接收者=%s" % (center.x(), center.y(), recv))
    print("   _resizing 置位 = %s" % started)
    print("   尺寸 %s -> %s" % (before, after))
    check("按住 ◢ 中心能触发缩放（_resizing 置位）", started)
    check("按住 ◢ 中心真的改变了窗口尺寸", after != before,
          "%s -> %s" % (before, after))
    print()

    # ---- 2. 按住 ◢ 的【左上角】也必须能缩放（把手最远端）----
    reset_size(sh, app)
    tl2 = visual_grip_rect(sh).topLeft()
    started2, b2, a2, recv2 = drag_resize(sh, app, tl2)
    print("按住 ◢ 左上 (%d,%d)  事件接收者=%s"
          % (tl2.x(), tl2.y(), recv2))
    print("   _resizing 置位 = %s ; 尺寸 %s -> %s" % (started2, b2, a2))
    check("按住 ◢ 左上角也能触发缩放", started2)
    print()

    # ---- 3. 窗口最右下角仍然可缩放（不得回归）----
    reset_size(sh, app)
    W3, H3 = sh.width(), sh.height()
    started3, b3, a3, recv3 = drag_resize(sh, app, QPoint(W3 - 2, H3 - 2))
    check("窗口最右下角可缩放（原功能不回归）", started3 and a3 != b3,
          "%s -> %s" % (b3, a3))
    print()

    # ---- 4. 窗口其它区域不得被误判为缩放热区 ----
    reset_size(sh, app)
    W4, H4 = sh.width(), sh.height()
    false_hits = []
    for name, pt in (("标题栏", QPoint(W4 // 2, 15)),
                     ("左下把手对称位置", QPoint(9, H4 - 9)),
                     ("底部中央", QPoint(W4 // 2, H4 - 9)),
                     ("左侧边中部", QPoint(9, H4 // 2)),
                     ("上边中部", QPoint(W4 // 2, 40))):
        if sh._near_resize_corner(pt):
            false_hits.append((name, pt))
    check("窗口其它区域未被误判为缩放热区", not false_hits,
          str(false_hits) if false_hits else "标题栏/左下/底部中央/左边/上边 均不命中")
    print()

    # ---- 5. 量化对齐度：视觉把手落在热区内的比例 ----
    reset_size(sh, app)
    visual = visual_grip_rect(sh)
    inside = sum(
        1 for y in range(visual.top(), visual.bottom() + 1)
        for x in range(visual.left(), visual.right() + 1)
        if sh._near_resize_corner(QPoint(x, y)))
    total = visual.width() * visual.height()
    ratio = 100.0 * inside / total if total else 0
    print("视觉把手落在缩放热区内的比例: %.1f%% (%d/%d)" % (ratio, inside, total))
    check("视觉把手 100% 落在缩放热区内（看得见=摸得着）", ratio >= 99.0,
          "%.1f%%" % ratio)
    print()

    # ---- 6. 缩放不得突破最小尺寸约束 ----
    reset_size(sh, app, 400, 320)
    c = visual_grip_rect(sh).center()
    _, bb, aa, _ = drag_resize(sh, app, c, dx=-600, dy=-600)
    check("向内缩到极限时不小于最小尺寸 (320x240)",
          aa[0] >= 320 and aa[1] >= 240, "%s -> %s" % (bb, aa))
    print()

    sh.close()
    app.processEvents()

    print("=" * 78)
    print("结果: %d PASS / %d FAIL" % (len(PASS), len(FAIL)))
    for f in FAIL:
        print("   FAILED:", f)
    print("=" * 78)
    return 0 if not FAIL else 1


if __name__ == "__main__":
    sys.exit(main())

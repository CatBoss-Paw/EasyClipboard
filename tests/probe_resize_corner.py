#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
诊断：右下角 18x18 缩放把手到底能不能被鼠标点到？

产品事实：
    Shelf 是 FramelessWindowHint（无系统标题栏、无系统缩放边框），
    setMinimumSize(320,240) 只设下限 —— 所以缩放【必须】靠自绘把手：
        Shelf._near_resize_corner(pos) = pos.x() >= W-18 and pos.y() >= H-18
        Shelf.mousePressEvent -> 命中就 grabMouse() 开始缩放

高度可疑之处：
    _build_ui 里 root.setContentsMargins(0, 0, 0, 0)，且 v.addWidget(
    self.view_stack, stretch=1) —— 内容【填满整个窗口】，包括右下角。
    Qt 的事件分发是「先给最上层的子控件」，只有子控件 ignore 了才会
    冒泡到父 widget。所以如果右下角被某个子控件覆盖，
    Shelf.mousePressEvent 永远收不到，缩放把手就是【死的】。

本探针用 childAt() 直接问 Qt：这个坐标上到底是哪个控件。
    - 返回 None          -> 事件能到 Shelf，把手可用
    - 返回某个子控件      -> 事件被截走，把手死的（这就是根因）

安全：全程使用临时目录做数据根，绝不触碰真实 _TempShelf / _History。
"""
import os
import sys
import tempfile
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="shelf_resize_probe_"))
# 必须在 import shelf_app 之前把数据根指到临时目录
os.environ["SHELF_PROBE_TMP"] = str(TMP)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import shelf_app                                        # noqa: E402
from PyQt6.QtWidgets import QApplication               # noqa: E402
from PyQt6.QtCore import QPoint, QPointF               # noqa: E402


def main():
    # 把数据目录改到临时位置，绝不碰真实数据
    import json

    # [ISOLATION] must happen BEFORE constructing Shelf:
    # DEFAULT_SETTINGS["shelf_dir"] is frozen to the REAL project dir at import
    # time, and Shelf.__init__ does load_settings() -> overwrites global
    # SHELF_DIR with settings["shelf_dir"]. So merely assigning
    # shelf_app.SHELF_DIR gets clobbered. Correct way: write a settings file
    # pointing at TMP, then redirect SETTINGS_PATH to it (load_settings reads
    # the module global at call time, so this takes effect).
    tmp_settings = {
        "shelf_dir": str(TMP / "_TempShelf"),
        "history_dir": str(TMP / "_History"),
        "pinned_dir": str(TMP / "_Pinned"),
        "min_text_len": 2,
        "auto_clear_hours": 0,
        "hotkey": "f9",
        "autostart": False,          # never let it write the registry
    }
    settings_file = TMP / "shelf_settings.json"
    settings_file.write_text(json.dumps(tmp_settings, ensure_ascii=False),
                             encoding="utf-8")
    shelf_app.SETTINGS_PATH = settings_file
    shelf_app.SHELF_DIR = TMP / "_TempShelf"
    shelf_app.HISTORY_DIR = TMP / "_History"
    shelf_app.PINNED_DIR = TMP / "_Pinned"
    for d in (shelf_app.SHELF_DIR, shelf_app.HISTORY_DIR, shelf_app.PINNED_DIR):
        d.mkdir(parents=True, exist_ok=True)

    real = Path(r"E:\项目搭建\剪贴板\_TempShelf")
    assert Path(tmp_settings["shelf_dir"]).resolve() != real.resolve(), \
        "isolation FAILED: data dir still points at the real project"
    print("数据根已隔离到:", TMP)
    print("settings:", settings_file)
    print()

    app = QApplication.instance() or QApplication(sys.argv[:1])

    sh = shelf_app.Shelf()
    # 隔离双重校验：构造之后 SHELF_DIR 必须已被 __init__ 改成临时目录
    assert Path(shelf_app.SHELF_DIR).resolve() == Path(
        tmp_settings["shelf_dir"]).resolve(), \
        "隔离失败：Shelf.__init__ 把 SHELF_DIR 改回了真实目录"
    print("构造后 SHELF_DIR =", shelf_app.SHELF_DIR)
    print("构造后 settings[autostart] =", sh.settings.get("autostart"))
    print()
    sh.resize(760, 560)
    sh.show()
    app.processEvents()

    W, H = sh.width(), sh.height()
    print("窗口尺寸: %d x %d（逻辑像素）" % (W, H))
    print("把手判定: _near_resize_corner -> x >= %d and y >= %d" % (W - 18, H - 18))
    print()

    def consumes_mouse(w):
        """判定一个控件是否【真的会吃掉】鼠标事件。

        childAt() 返回子控件并不等于事件被截走：QFrame / QLabel 默认不处理
        鼠标事件，会冒泡给父 widget。真正会吃掉的是：
          - 控件自己重写了 mousePressEvent（看类里有无该方法）
          - 或者是能接受鼠标输入的控件（按钮/输入框/滚动区/列表）
        """
        if w is None:
            return None
        cls = type(w).__name__
        own = "mousePressEvent" in type(w).__dict__
        grabber = any(isinstance(w, t) for t in (
            __import__("PyQt6.QtWidgets", fromlist=["x"]).QPushButton,
            __import__("PyQt6.QtWidgets", fromlist=["x"]).QScrollArea,
            __import__("PyQt6.QtWidgets", fromlist=["x"]).QListWidget,
            __import__("PyQt6.QtWidgets", fromlist=["x"]).QLineEdit,
        ))
        return {"class": cls, "obj": w.objectName(),
                "overrides_press": own, "is_grabber": grabber,
                "consumes": own or grabber,
                "size": (w.width(), w.height()),
                "geom": (w.x(), w.y(), w.width(), w.height())}

    probes = [
        ("正中把手点", QPoint(W - 9, H - 9)),
        ("把手外角(最右下)", QPoint(W - 1, H - 1)),
        ("把手内角", QPoint(W - 18, H - 18)),
        ("把手外一点(对照)", QPoint(W - 30, H - 30)),
        ("左下角(对照)", QPoint(5, H - 5)),
        ("标题栏(对照)", QPoint(W // 2, 8)),
    ]

    print("=" * 96)
    print("%-16s %-8s %-46s %-8s" % (
        "探测点", "把手区?", "childAt() 返回", "吃掉?"))
    print("=" * 96)
    blocked = 0
    for name, pos in probes:
        near = sh._near_resize_corner(pos)
        info = consumes_mouse(sh.childAt(pos))
        if info is None:
            desc, cons = "None -> 事件直接到 Shelf", False
        else:
            desc = "%s(obj=%r) size=%s" % (
                info["class"], info["obj"], info["size"])
            cons = info["consumes"]
            if cons:
                desc += " overrides_press=%s grabber=%s" % (
                    info["overrides_press"], info["is_grabber"])
        if near and cons:
            blocked += 1
        print("%-14s %-6s %-52s %-6s" % (
            name, near, desc[:52], "是" if cons else "否(冒泡)"))
    print("=" * 96)
    print()
    print("【重要】childAt 返回子控件并不等于事件被截走：QFrame/QLabel 默认")
    print("      不处理鼠标事件，会冒泡给父 Shelf。只有 overrides_press 或")
    print("      本身是按钮/滚动区/列表/输入框的控件才会真吃掉。")
    print()

    # 真刀真枪地模拟一次缩放：按下把手 -> 移动 -> 看尺寸有没有变
    from PyQt6.QtCore import QEvent, Qt
    from PyQt6.QtGui import QMouseEvent

    def mk(etype, local, glob, buttons, button=Qt.MouseButton.LeftButton):
        # PyQt6 要求 QPointF，传 QPoint 会报 arguments did not match
        return QMouseEvent(etype, QPointF(local), QPointF(glob), button,
                           buttons, Qt.KeyboardModifier.NoModifier)

    before = (sh.width(), sh.height())
    corner_local = QPoint(W - 9, H - 9)
    corner_glob = sh.mapToGlobal(corner_local)

    press = mk(QEvent.Type.MouseButtonPress, corner_local, corner_glob,
               Qt.MouseButton.LeftButton)
    app.sendEvent(sh, press)
    app.processEvents()

    move_glob = QPoint(corner_glob.x() + 120, corner_glob.y() + 90)
    move = mk(QEvent.Type.MouseMove,
              QPoint(corner_local.x() + 120, corner_local.y() + 90),
              move_glob, Qt.MouseButton.LeftButton)
    app.sendEvent(sh, move)
    app.processEvents()

    release = mk(QEvent.Type.MouseButtonRelease, corner_local, corner_glob,
                 Qt.MouseButton.NoButton)
    app.sendEvent(sh, release)
    app.processEvents()

    after = (sh.width(), sh.height())
    print("直接向 Shelf 派发事件模拟缩放:")
    print("  before=%s  after=%s" % (before, after))
    print("  尺寸改变: %s" % (before != after))
    print()

    # 更接近真实的验证：把事件发给【该坐标上真正的控件】，看能否冒泡到 Shelf
    real_child = sh.childAt(corner_local)
    if real_child is not None:
        print("真实情况复现：事件发给该坐标上的实际控件 %s" % type(real_child).__name__)
        b2 = (sh.width(), sh.height())
        local_in_child = real_child.mapFrom(sh, corner_local)
        gp = real_child.mapToGlobal(local_in_child)
        app.sendEvent(real_child, mk(QEvent.Type.MouseButtonPress,
                                     local_in_child, gp,
                                     Qt.MouseButton.LeftButton))
        app.processEvents()
        app.sendEvent(real_child, mk(QEvent.Type.MouseMove,
                                     QPoint(local_in_child.x() + 120,
                                            local_in_child.y() + 90),
                                     QPoint(gp.x() + 120, gp.y() + 90),
                                     Qt.MouseButton.LeftButton))
        app.processEvents()
        app.sendEvent(real_child, mk(QEvent.Type.MouseButtonRelease,
                                     local_in_child, gp,
                                     Qt.MouseButton.NoButton))
        app.processEvents()
        a2 = (sh.width(), sh.height())
        print("  before=%s  after=%s  尺寸改变=%s" % (b2, a2, b2 != a2))
        print()

    print("=" * 78)
    if blocked:
        print("结论: 右下角把手区域被 %d 个子控件覆盖 -> Shelf.mousePressEvent" % blocked)
        print("      收不到鼠标事件 -> 用户拖右下角【缩放无效】。这是真实缺陷。")
    else:
        print("结论: 把手区域未被覆盖，事件能到 Shelf。若用户仍反馈拖不动，")
        print("      需另找原因（如 grabMouse 在 frameless 下的行为）。")
    print("=" * 78)

    sh.close()
    app.processEvents()


if __name__ == "__main__":
    main()

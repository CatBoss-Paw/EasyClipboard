#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
实测「按住按钮拖出附件」这条链路的每一环，定位断点在哪。

链路（源码事实）：
    DragOutButton.mouseMoveEvent        shelf_app.py:727
      -> drag_requested.emit()          :739
      -> Shelf.start_batch_drag         :1287 connect / :2506 def
         -> _collect_drag_files         :2639
            -> _get_selected_files      :2631   只收 on=True 的条目
         -> 若 files 为空: self._toast("没有勾选的附件"); return
         -> _execute_drag(files)        :2591
            -> QDrag.exec()

两个高度可疑的断点：
    A) _toast 是【空实现】（零打扰原则）。所以只要没勾选附件，拖拽就是
       【完全静默地什么都不发生】——用户看到的现象正是「拖不动、没反应、
       也没提示」，而且永远不知道为什么。
    B) drag.exec() 在 mouseMoveEvent 内被【同步】调用。Qt 里在鼠标移动
       事件处理器中进入 QDrag 的嵌套事件循环是危险做法。

本脚本把每一环都插桩，打印真实走到了哪一步。
安全：数据根隔离到临时目录，绝不触碰真实 _TempShelf / _History。
"""
import json
import os
import sys
import tempfile
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="shelf_dragout_"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import shelf_app                                     # noqa: E402
from PyQt6.QtWidgets import QApplication             # noqa: E402
from PyQt6.QtCore import QEvent, QPoint, QPointF, Qt  # noqa: E402
from PyQt6.QtGui import QMouseEvent                  # noqa: E402


def isolate():
    """必须在构造 Shelf 之前：__init__ 会用 settings['shelf_dir'] 覆写全局。"""
    s = {
        "shelf_dir": str(TMP / "_TempShelf"),
        "history_dir": str(TMP / "_History"),
        "pinned_dir": str(TMP / "_Pinned"),
        "min_text_len": 2,
        "auto_clear_hours": 0,
        "hotkey": "f9",
        "autostart": False,
    }
    f = TMP / "shelf_settings.json"
    f.write_text(json.dumps(s, ensure_ascii=False), encoding="utf-8")
    shelf_app.SETTINGS_PATH = f
    for k in ("shelf_dir", "history_dir", "pinned_dir"):
        Path(s[k]).mkdir(parents=True, exist_ok=True)
    real = Path(r"E:\项目搭建\剪贴板\_TempShelf")
    assert Path(s["shelf_dir"]).resolve() != real.resolve()
    return s


def mk(etype, local, glob, button, buttons):
    return QMouseEvent(etype, QPointF(local), QPointF(glob), button, buttons,
                       Qt.KeyboardModifier.NoModifier)


def main():
    isolate()
    app = QApplication.instance() or QApplication(sys.argv[:1])

    trace = []

    # ---- 插桩：记录链路每一环是否被走到 ----
    orig_collect = shelf_app.Shelf._collect_drag_files
    orig_selected = shelf_app.Shelf._get_selected_files
    orig_execute = shelf_app.Shelf._execute_drag
    orig_toast = shelf_app.Shelf._toast
    orig_batch = shelf_app.Shelf.start_batch_drag

    def spy_collect(self):
        files, missing = orig_collect(self)
        trace.append(("_collect_drag_files", "files=%d missing=%d"
                      % (len(files), len(missing))))
        return files, missing

    def spy_selected(self):
        r = orig_selected(self)
        trace.append(("_get_selected_files", "returned=%d" % len(r)))
        return r

    def spy_execute(self, files):
        trace.append(("_execute_drag ENTERED", "n=%d isVisible=%s"
                      % (len(files), self.isVisible())))
        # 不真的进 QDrag.exec()（offscreen 下会卡住），只验证到这里
        return None

    def spy_toast(self, msg):
        trace.append(("_toast CALLED", repr(msg)))
        return orig_toast(self, msg)

    def spy_batch(self):
        trace.append(("start_batch_drag ENTERED", ""))
        return orig_batch(self)

    shelf_app.Shelf._collect_drag_files = spy_collect
    shelf_app.Shelf._get_selected_files = spy_selected
    shelf_app.Shelf._execute_drag = spy_execute
    shelf_app.Shelf._toast = spy_toast
    shelf_app.Shelf.start_batch_drag = spy_batch

    sh = shelf_app.Shelf()
    sh.resize(900, 620)
    sh.show()
    app.processEvents()

    assert Path(shelf_app.SHELF_DIR).resolve() == Path(
        TMP / "_TempShelf").resolve(), "隔离失败"

    print("=" * 78)
    print("【0】布局实测：右下角 / 底部到底是哪个控件")
    print("=" * 78)
    W, H = sh.width(), sh.height()
    print("窗口 %d x %d" % (W, H))
    for label, pt in (("右下角(缩放把手区)", QPoint(W - 9, H - 9)),
                      ("左下角", QPoint(9, H - 9)),
                      ("底部中央", QPoint(W // 2, H - 9))):
        c = sh.childAt(pt)
        if c is None:
            print("  %-20s -> None（事件直接到 Shelf）" % label)
        else:
            txt = c.text()[:24] if hasattr(c, "text") else ""
            print("  %-20s -> %s(obj=%r) text=%r geom=(%d,%d,%d,%d)"
                  % (label, type(c).__name__, c.objectName(), txt,
                     c.x(), c.y(), c.width(), c.height()))
    print()
    btn = sh.btn_drag_files
    gp = btn.mapTo(sh, QPoint(0, 0))
    print("  btn_drag_files 在 Shelf 坐标系: (%d,%d) size=(%d,%d)"
          % (gp.x(), gp.y(), btn.width(), btn.height()))
    print("  btn_drag_files 文字: %r" % btn.text())
    print("  => 它位于【左下】还是【右下】: x=%d / 窗宽=%d -> %s"
          % (gp.x(), W, "左半" if gp.x() < W // 2 else "右半"))
    print()

    # ---- 造数据：一个图片条目 + 一个文件条目 ----
    print("=" * 78)
    print("【1】场景 A：没有任何勾选（产品默认状态 = 全不选）")
    print("=" * 78)
    shelf_dir = Path(shelf_app.SHELF_DIR)
    img = shelf_dir / "img_probe.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 200)
    sh.entries = [
        {"kind": "image", "name": "img_probe.png", "on": False,
         "ts": "00:00", "at": 0, "hash": "x"},
        {"kind": "text", "text": "一段文字", "on": False,
         "ts": "00:00", "at": 0, "hash": "y"},
    ]
    trace.clear()
    btn_pos_local = QPoint(btn.width() // 2, btn.height() // 2)
    btn_glob = btn.mapToGlobal(btn_pos_local)
    app.sendEvent(btn, mk(QEvent.Type.MouseButtonPress, btn_pos_local,
                          btn_glob, Qt.MouseButton.LeftButton,
                          Qt.MouseButton.LeftButton))
    app.processEvents()
    far = QPoint(btn_pos_local.x() + 40, btn_pos_local.y() + 40)
    app.sendEvent(btn, mk(QEvent.Type.MouseMove, far,
                          btn.mapToGlobal(far), Qt.MouseButton.NoButton,
                          Qt.MouseButton.LeftButton))
    app.processEvents()
    app.sendEvent(btn, mk(QEvent.Type.MouseButtonRelease, far,
                          btn.mapToGlobal(far), Qt.MouseButton.NoButton,
                          Qt.MouseButton.NoButton))
    app.processEvents()
    for step, detail in trace:
        print("   -> %-26s %s" % (step, detail))
    entered = any(s == "_execute_drag ENTERED" for s, _ in trace)
    toasted = any(s == "_toast CALLED" for s, _ in trace)
    print()
    print("   结论 A: 走到 _execute_drag = %s ; 调了 _toast = %s"
          % (entered, toasted))
    if not entered and toasted:
        print("   !! 这就是【静默失败】：没勾选附件 -> 调 _toast -> 而 _toast")
        print("      是空实现 -> 用户看到的是【拖了完全没反应，也没任何提示】")
    print()

    # ---- 场景 B：勾选了附件 ----
    print("=" * 78)
    print("【2】场景 B：勾选了图片附件（on=True）")
    print("=" * 78)
    sh.entries[0]["on"] = True
    trace.clear()
    app.sendEvent(btn, mk(QEvent.Type.MouseButtonPress, btn_pos_local,
                          btn_glob, Qt.MouseButton.LeftButton,
                          Qt.MouseButton.LeftButton))
    app.processEvents()
    app.sendEvent(btn, mk(QEvent.Type.MouseMove, far,
                          btn.mapToGlobal(far), Qt.MouseButton.NoButton,
                          Qt.MouseButton.LeftButton))
    app.processEvents()
    app.sendEvent(btn, mk(QEvent.Type.MouseButtonRelease, far,
                          btn.mapToGlobal(far), Qt.MouseButton.NoButton,
                          Qt.MouseButton.NoButton))
    app.processEvents()
    for step, detail in trace:
        print("   -> %-26s %s" % (step, detail))
    entered_b = any(s == "_execute_drag ENTERED" for s, _ in trace)
    print()
    print("   结论 B: 勾选后走到 _execute_drag = %s" % entered_b)
    print()

    print("=" * 78)
    print("【3】_toast 实现体（决定用户能否感知失败）")
    print("=" * 78)
    import inspect
    print(inspect.getsource(shelf_app.Shelf._toast).rstrip())
    print()
    print("【4】按钮文字在两种状态下的实际显示")
    sh._update_drag_button() if hasattr(sh, "_update_drag_button") else None
    print("   当前 btn 文字: %r" % btn.text())

    sh.close()
    app.processEvents()


if __name__ == "__main__":
    main()

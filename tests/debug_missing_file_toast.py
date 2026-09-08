#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
插桩定位：源文件失效时拖卡片，为什么没走到新增的 else 分支？

test_card_dragout.py 第 7 项断言 FAIL：_toast 调用 = []。
新增的 else 分支理论上必须命中。可能原因（逐一排查，不猜）：
    a) 拖拽根本没触发（卡片尺寸/几何问题，move 未跨过阈值）
    b) 卡片引用是 _sync_ui 重建后的陈旧对象（C++ 已删除）
    c) start_card_drag 因 isVisible()=False 提前 return
    d) _get_entry_files 抛异常被吞
    e) entry 的 name 改了但卡片持有的是旧 dict
"""
import json
import sys
import tempfile
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="shelf_dbg_"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import shelf_app                                     # noqa: E402
from PyQt6.QtWidgets import QApplication             # noqa: E402
from PyQt6.QtCore import QEvent, QPoint, QPointF, Qt  # noqa: E402
from PyQt6.QtGui import QMouseEvent, QDrag           # noqa: E402

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
for k in ("shelf_dir", "history_dir", "pinned_dir"):
    Path(s[k]).mkdir(parents=True, exist_ok=True)

app = QApplication.instance() or QApplication(sys.argv[:1])


def mk(t, l, g, b, bs):
    return QMouseEvent(t, QPointF(l), QPointF(g), b, bs,
                       Qt.KeyboardModifier.NoModifier)


drag_log = []
QDrag.exec = lambda self, *a, **k: (drag_log.append("EXEC"),
                                    Qt.DropAction.CopyAction)[1]

orig_start = shelf_app.Shelf.start_card_drag
orig_files = shelf_app.Shelf.start_files_drag
orig_getef = shelf_app.Shelf._get_entry_files
orig_exec = shelf_app.Shelf._execute_drag
orig_toast = shelf_app.Shelf._toast
orig_move = shelf_app.ShelfCard.mouseMoveEvent


def sp_start(self, entry):
    print("   [start_card_drag] kind=%r visible=%s name=%r"
          % (entry.get("kind"), self.isVisible(), entry.get("name")))
    return orig_start(self, entry)


def sp_files(self, entry):
    print("   [start_files_drag] name=%r on=%r"
          % (entry.get("name"), entry.get("on")))
    return orig_files(self, entry)


def sp_getef(self, e):
    try:
        r = orig_getef(self, e)
    except Exception as ex:                     # noqa: BLE001
        print("   [_get_entry_files] RAISED %r" % ex)
        raise
    print("   [_get_entry_files] -> %r" % (r,))
    return r


def sp_exec(self, files):
    print("   [_execute_drag] n=%d visible=%s" % (len(files), self.isVisible()))
    return orig_exec(self, files)


def sp_toast(self, msg):
    print("   [_toast] %r" % msg)
    return orig_toast(self, msg)


def sp_move(self, ev):
    dsp = getattr(self, "_drag_start_pos", "MISSING")
    print("   [ShelfCard.mouseMoveEvent] kind=%r drag_start_pos=%s pos=%s"
          % (self.entry.get("kind"), dsp, ev.position().toPoint()))
    return orig_move(self, ev)


shelf_app.Shelf.start_card_drag = sp_start
shelf_app.Shelf.start_files_drag = sp_files
shelf_app.Shelf._get_entry_files = sp_getef
shelf_app.Shelf._execute_drag = sp_exec
shelf_app.Shelf._toast = sp_toast
shelf_app.ShelfCard.mouseMoveEvent = sp_move

sh = shelf_app.Shelf()
print("SHELF_DIR =", shelf_app.SHELF_DIR)
sh.resize(900, 620)
sh.entries = [
    {"kind": "image", "name": "img_dbg.png", "on": False,
     "ts": "00:01", "at": 0, "hash": "z"},
]
(TMP / "_TempShelf" / "img_dbg.png").write_bytes(
    b"\x89PNG\r\n\x1a\n" + b"0" * 100)
sh._sync_ui()
sh.show()
app.processEvents()
print()

print("=== 步骤1: 先把【存在的】图片改掉 name 指向不存在的文件 ===")
for e in sh.entries:
    if e["kind"] == "image":
        e["name"] = "不存在的图片.png"
print("   sh.entries 现在:", [(e["kind"], e["name"]) for e in sh.entries])
sh._sync_ui()
app.processEvents()
app.processEvents()      # 让 deleteLater 生效

cards = [w for w in sh.findChildren(shelf_app.ShelfCard)]
print("   重建后卡片数:", len(cards))
for i, c in enumerate(cards):
    try:
        print("     card[%d] kind=%r name=%r size=(%d,%d) entry_id=%s"
              % (i, c.entry.get("kind"), c.entry.get("name"),
                 c.width(), c.height(), id(c.entry)))
    except RuntimeError as ex:
        print("     card[%d] STALE(C++ deleted): %s" % (i, ex))
print("   sh.entries[0] dict id =", id(sh.entries[0]))
print()

valid = [c for c in cards if c.entry.get("name") == "不存在的图片.png"]
print("=== 步骤2: 拖动 name 已失效的图片卡片 ===")
if not valid:
    print("   !! 找不到目标卡片 -> 测试脚本的卡片定位有问题")
else:
    card = valid[0]
    w_, h_ = card.width(), card.height()
    print("   卡片尺寸 (%d,%d) -> 若为 0 说明布局未完成，press 点会退化" % (w_, h_))
    pt = QPoint(max(w_ // 2, 5), max(h_ // 2, 5))
    gp = card.mapToGlobal(QPointF(pt))
    app.sendEvent(card, mk(QEvent.Type.MouseButtonPress, QPointF(pt), gp,
                           Qt.MouseButton.LeftButton,
                           Qt.MouseButton.LeftButton))
    app.processEvents()
    for step in (20, 40):
        lp = QPointF(pt.x() + step, pt.y() + step)
        app.sendEvent(card, mk(QEvent.Type.MouseMove, lp,
                               card.mapToGlobal(lp),
                               Qt.MouseButton.NoButton,
                               Qt.MouseButton.LeftButton))
        app.processEvents()
    app.sendEvent(card, mk(QEvent.Type.MouseButtonRelease,
                           QPointF(pt.x() + 40, pt.y() + 40),
                           card.mapToGlobal(QPointF(pt.x() + 40, pt.y() + 40)),
                           Qt.MouseButton.NoButton,
                           Qt.MouseButton.NoButton))
    app.processEvents()

print()
print("drag_log =", drag_log)
print()
print("=== 步骤3: 直接调用 start_card_drag（绕过鼠标事件）验证 else 分支 ===")
drag_log.clear()
sh.start_card_drag(sh.entries[0])
print("drag_log =", drag_log)
sh.close()
app.processEvents()

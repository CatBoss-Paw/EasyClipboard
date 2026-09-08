#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Phase 5B 运行时部署验证（Rule 6）。

与 test_dragoutbutton_bug.py 的区别：
  那个测试直接调用 btn.mouseMoveEvent(ev) —— 异常在【我们的】调用帧里抛出，
  Python 能捕获到 traceback，属于"离线"复现。
  本脚本走【真实 Qt 事件循环】：QApplication.sendEvent / postEvent + app.processEvents，
  让事件经由 Qt 派发回 PyQt6 的虚方法包装层。这才是用户真实手势下的执行路径，
  也是"事件处理器内异常 → qFatal 静默杀进程"真正会发生的场景。

沙箱铁律：绝不使用真实 shelf_settings.json / 真实数据目录。
使用真实 windows 平台（非 offscreen），以贴近生产运行时。
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROJECT_PY = r"C:\Users\37162\AppData\Local\Programs\Python\Python313\python.exe"
if not Path(PROJECT_PY).exists():
    PROJECT_PY = sys.executable

PROBE = r'''
import os, sys, tempfile, json
from pathlib import Path

# 关键：不设置 QT_QPA_PLATFORM=offscreen，使用真实 Windows GUI 平台
sys.path.insert(0, r"__ROOT__")

import shelf_app
_sb = Path(tempfile.mkdtemp(prefix="shelf_rt_"))
shelf_app.DEFAULT_SETTINGS["shelf_dir"]   = str(_sb / "_TempShelf")
shelf_app.DEFAULT_SETTINGS["history_dir"] = str(_sb / "_History")
shelf_app.DEFAULT_SETTINGS["pinned_dir"]  = str(_sb / "_Pinned")
shelf_app.SETTINGS_PATH = _sb / "settings.json"
# 关闭开机自启/热键，避免污染用户真实注册表与全局热键占用
shelf_app.DEFAULT_SETTINGS["autostart"] = False

from PyQt6.QtCore import Qt, QPointF, QEvent, QTimer
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtWidgets import QApplication

app = QApplication(sys.argv)

print("QT_PLATFORM=%s" % app.platformName(), flush=True)

w = shelf_app.Shelf()
w.show()
w.apply_look()
app.processEvents()
print("SHELF_CONSTRUCTED_VISIBLE=%s" % w.isVisible(), flush=True)
print("HAS_DRAGOUT_BUTTON=%s" % hasattr(w, "btn_drag_files"), flush=True)

btn = w.btn_drag_files

def mev(t, lx, ly, buttons):
    return QMouseEvent(t, QPointF(lx, ly), btn.mapToGlobal(QPointF(lx, ly)),
                       Qt.MouseButton.LeftButton, buttons,
                       Qt.KeyboardModifier.NoModifier)

# ============ P0 路径：底栏拖出按钮，经真实事件循环派发 ============
# 用 sendEvent 让事件走 Qt 的派发机制，而不是直接调用覆写方法
app.sendEvent(btn, mev(QEvent.Type.MouseButtonPress, 10, 10, Qt.MouseButton.LeftButton))
app.processEvents()
print("RT_PRESS_OK", flush=True)

# 注意：__init__ 里是 `btn.drag_requested.connect(self.start_batch_drag)`，
# 连接持有的是【已绑定的方法对象】，事后给实例赋 w.start_batch_drag = ... 无法拦截。
# 因此直接监听信号本身，这才是可靠的证据获取方式。
drag_calls = []
btn.drag_requested.connect(lambda: drag_calls.append(1))

# 下游处理器的接线关系用【静态源码核对】确认（因为信号已绑定方法对象，
# 运行时 monkeypatch 实例属性无法拦截，不能当作证据）。
import inspect
_ui_src = inspect.getsource(shelf_app.Shelf)
WIRED_TO_BATCH = "btn_drag_files.drag_requested.connect(self.start_batch_drag)" in _ui_src
print("WIRED_TO_start_batch_drag=%s" % WIRED_TO_BATCH, flush=True)

for i, (lx, ly) in enumerate([(20, 20), (40, 45), (70, 80)]):
    app.sendEvent(btn, mev(QEvent.Type.MouseMove, lx, ly, Qt.MouseButton.LeftButton))
    app.processEvents()
    print("RT_MOVE_%d_OK" % i, flush=True)

print("DRAG_REQUESTED_EMITTED=%s" % bool(drag_calls), flush=True)

# ============ 双击复制路径：经真实事件循环派发 ============
entry = {"kind": "text", "text": "运行时双击验证ABCDEF", "ts": "00:00:00",
         "at": "2026-09-07 00:00:00", "on": False}
w.entries = [entry]
w._sync_ui()
app.processEvents()

card = None
for i in range(w.cards_box_text.count()):
    it = w.cards_box_text.itemAt(i)
    if it and isinstance(it.widget(), shelf_app.ShelfCard):
        card = it.widget()
        break
print("CARD_FOUND=%s" % (card is not None), flush=True)

if card is not None:
    copies = []
    w.copy_single_entry = lambda e: copies.append(e)
    cpos = QPointF(card.width() / 2, card.height() / 2)

    def cmev(t, buttons):
        return QMouseEvent(t, cpos, card.mapToGlobal(cpos),
                           Qt.MouseButton.LeftButton, buttons,
                           Qt.KeyboardModifier.NoModifier)

    # 模拟真实双击序列：Press → Release → DblClick → Release
    app.sendEvent(card, cmev(QEvent.Type.MouseButtonPress, Qt.MouseButton.LeftButton))
    app.sendEvent(card, cmev(QEvent.Type.MouseButtonRelease, Qt.MouseButton.NoButton))
    app.sendEvent(card, cmev(QEvent.Type.MouseButtonDblClick, Qt.MouseButton.LeftButton))
    app.sendEvent(card, cmev(QEvent.Type.MouseButtonRelease, Qt.MouseButton.NoButton))
    app.processEvents()
    print("RT_DBLCLICK_COPY=%s" % bool(copies), flush=True)

# ============ 事件循环存活确认 ============
QTimer.singleShot(300, app.quit)
rc = app.exec()
print("EVENT_LOOP_EXITED_RC=%s" % rc, flush=True)
print("STILL_ALIVE", flush=True)
'''
PROBE = PROBE.replace("__ROOT__", str(ROOT))


def main():
    r = subprocess.run([PROJECT_PY, "-E", "-X", "utf8", "-X", "faulthandler", "-c", PROBE],
                       capture_output=True, timeout=180, cwd=str(ROOT))
    out = r.stdout.decode("utf-8", "replace")
    err = r.stderr.decode("utf-8", "replace")
    print("=" * 72)
    print("returncode =", r.returncode)
    print("-" * 72)
    print(out)
    if err.strip():
        print("-" * 30, "STDERR", "-" * 30)
        print(err[-3000:])
    print("=" * 72)

    if "STILL_ALIVE" not in out:
        print("判定：失败 —— 进程在真实事件循环中死亡（未打印 STILL_ALIVE）")
        print("      这是 P0 原生崩溃的特征：事件处理器内异常 → qFatal → 静默退出")
        return 1

    kv = {}
    for line in out.splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            kv[k.strip()] = v.strip()

    checks = {
        "真实 GUI 平台（非 offscreen）": kv.get("QT_PLATFORM", "") != "offscreen",
        "Shelf 构造并可见": kv.get("SHELF_CONSTRUCTED_VISIBLE") == "True",
        "底栏拖出按钮存在": kv.get("HAS_DRAGOUT_BUTTON") == "True",
        "按钮 mouseMove 不再崩溃": all(("RT_MOVE_%d_OK" % i) in out for i in range(3)),
        "drag_requested 已发射": kv.get("DRAG_REQUESTED_EMITTED") == "True",
        "信号已接线 start_batch_drag": kv.get("WIRED_TO_start_batch_drag") == "True",
        "卡片经事件循环找到": kv.get("CARD_FOUND") == "True",
        "双击复制生效": kv.get("RT_DBLCLICK_COPY") == "True",
        "事件循环正常退出": kv.get("EVENT_LOOP_EXITED_RC") == "0",
    }

    allok = True
    for name, ok in checks.items():
        print("  %-28s %s" % (name, "✅" if ok else "❌"))
        allok = allok and ok

    print()
    if allok:
        print("判定：运行时部署验证通过 —— 修复已在真实 Qt 事件循环下生效，进程存活")
        return 0
    print("判定：运行时部署验证未通过")
    return 1


if __name__ == "__main__":
    sys.exit(main())

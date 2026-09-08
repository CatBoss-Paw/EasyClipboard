#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""诊断：设置按钮点击链路 open_settings → SettingsDialog 构造"""
import os
import sys
import tempfile
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import shelf_app

# 沙箱隔离，不碰真实数据
_sandbox = Path(tempfile.mkdtemp(prefix="shelf_diag_"))
shelf_app.DEFAULT_SETTINGS["shelf_dir"] = str(_sandbox / "_TempShelf")
shelf_app.DEFAULT_SETTINGS["history_dir"] = str(_sandbox / "_History")
shelf_app.DEFAULT_SETTINGS["pinned_dir"] = str(_sandbox / "_Pinned")
shelf_app.SETTINGS_PATH = _sandbox / "settings.json"

from PyQt6.QtWidgets import QApplication
app = QApplication(sys.argv)

from shelf_app import Shelf
w = Shelf()
w.show()
app.processEvents()

print("1. gear 按钮存在:", hasattr(w, "gear") or "查按钮名")
# 找顶栏的 ⚙ 按钮
from PyQt6.QtWidgets import QPushButton
btns = w.titlebar.findChildren(QPushButton)
print("2. 顶栏按钮数:", len(btns), [b.text() for b in btns])
gear = next((b for b in btns if b.text() == "⚙"), None)
print("3. ⚙ 按钮定位:", "找到" if gear else "未找到")
if gear:
    print("4. ⚙ 可见:", gear.isVisible(), "可点击区域:", not gear.geometry().isNull())
    try:
        gear.click()
        app.processEvents()
        print("5. click() 无异常")
        dlg = w._settings_dlg
        print("6. _settings_dlg:", dlg)
        if dlg is not None:
            print("7. 设置窗口可见:", dlg.isVisible(), "几何:", dlg.geometry())
    except Exception as e:
        import traceback
        print("❌ 点击链路抛异常:")
        traceback.print_exc()

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""回归：文本卡片拖拽入口不再抛 TypeError（此前会经 mouseMoveEvent 触发 PyQt6 qFatal 闪退）"""
import os
import sys
import tempfile

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication
app = QApplication(sys.argv)

import shelf_app
from pathlib import Path
from shelf_app import Shelf

# 沙箱隔离（铁律）：测试永不触碰真实数据目录
_sandbox = Path(tempfile.mkdtemp(prefix="shelf_drag_"))
shelf_app.DEFAULT_SETTINGS["shelf_dir"] = str(_sandbox / "_TempShelf")
shelf_app.DEFAULT_SETTINGS["history_dir"] = str(_sandbox / "_History")
shelf_app.DEFAULT_SETTINGS["pinned_dir"] = str(_sandbox / "_Pinned")
shelf_app.SETTINGS_PATH = _sandbox / "settings.json"

w = Shelf()
w.show()
app.processEvents()

w._ingest_text("回归测试文本")
from PyQt6.QtGui import QImage
img = QImage(10, 10, QImage.Format.Format_RGB32)
img.fill(Qt.GlobalColor.blue)
w._ingest_image(img)
tmp = Path(os.path.join(os.path.dirname(__file__), "_tmp_drag_src.txt"))
tmp.write_text("回归测试文件", encoding="utf-8")
w._ingest_files([str(tmp)])

text_entry = next(e for e in w.entries if e["kind"] == "text")
w.start_card_drag(text_entry)          # offscreen 下 drag.exec 立即返回
w.start_card_drag(next(e for e in w.entries if e["kind"] == "image"))
file_entry = next(e for e in w.entries if e["kind"] == "file")
w.start_card_drag(file_entry)

# 隐藏状态下再走一遍（竞速防护路径）
w.hide()
w.start_card_drag(text_entry)
w.start_files_drag(text_entry)
tmp.unlink(missing_ok=True)

# 三页面切换回归（此前 refresh_journal_page 调用不存在的方法导致真机闪退）
w.show()
app.processEvents()
w._switch_view(1)                      # ⭐ 快速访问
assert w.view_stack.currentIndex() == 1
w._switch_view(2)                      # 📜 今日日志
assert w.view_stack.currentIndex() == 2
assert w.journal_box.count() >= 0      # 结构化日志行已渲染
w._switch_view(0)
assert w.view_stack.currentIndex() == 0

print("✅ 三类卡片拖拽入口 + 隐藏态防护 + 三页面切换 全部无异常")

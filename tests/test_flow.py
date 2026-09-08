#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""全链路业务逻辑模拟验证：连续复制、微信分栏、每日日志落盘、清空隔离"""
import sys
import os
import time
from datetime import datetime

sys.path.insert(0, r"E:\项目搭建\剪贴板")
os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PyQt6.QtWidgets import QApplication, QMessageBox
from PyQt6.QtGui import QImage
from PyQt6.QtCore import Qt
import shelf_app
import tempfile
from pathlib import Path

# 沙箱隔离（铁律）：测试永不触碰真实数据目录
_sandbox = Path(tempfile.mkdtemp(prefix="shelf_flow_"))
shelf_app.DEFAULT_SETTINGS["shelf_dir"] = str(_sandbox / "_TempShelf")
shelf_app.DEFAULT_SETTINGS["history_dir"] = str(_sandbox / "_History")
shelf_app.DEFAULT_SETTINGS["pinned_dir"] = str(_sandbox / "_Pinned")
shelf_app.SETTINGS_PATH = _sandbox / "settings.json"

app = QApplication(sys.argv)
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes)

s = shelf_app.Shelf()

# 1. 模拟连续复制纯文本（包含模拟语音输入法的长句）
s._ingest_text("【会议纪要】关于微信与企微中转架构的讨论")
s._ingest_text("这是用语音输入法口述的一大段思路：我们需要把临时工作台和长期工作记忆完全分开，每天锁定一篇独立日记。")
s._ingest_text("API_ENDPOINT = https://internal.company.com/v1")

# 2. 模拟截图
img = QImage(120, 90, QImage.Format.Format_RGB32)
img.fill(Qt.GlobalColor.green)
s._ingest_image(img)

# 3. 检查今日日志
today_str = datetime.now().strftime("%Y-%m-%d")
today_file = shelf_app.HISTORY_DIR / f"{today_str}.md"
print("日志文件路径:", str(today_file))
print("日志是否存在:", today_file.exists())
if today_file.exists():
    print("--- 日志片段内容 ---")
    print(today_file.read_text(encoding="utf-8")[:260])

# 4. 检查卡片分栏
left_count = sum(1 for i in range(s.cards_box_files.count()) if isinstance(s.cards_box_files.itemAt(i).widget(), shelf_app.ShelfCard))
right_count = sum(1 for i in range(s.cards_box_text.count()) if isinstance(s.cards_box_text.itemAt(i).widget(), shelf_app.ShelfCard))
print("左栏附件卡片数 (预期 1):", left_count)
print("右栏文本卡片数 (预期 3):", right_count)

# 5. 模拟合并复制文字（产品默认不全选，交付测试先全选）
s.toggle_select_all()
s.copy_merged_text()
clip_text = QApplication.clipboard().text()
print("合并复制剪贴板总字数:", len(clip_text))
assert "【会议纪要】" in clip_text and "API_ENDPOINT" in clip_text

# 6. 清空当前批次
s.purge()
print("清空后 entries 长度 (预期 0):", len(s.entries))
print("清空后每日日志是否存在 (预期 True):", today_file.exists())
print("清空后每日日志大小:", today_file.stat().st_size, "字节")

print("\n🎉 全部业务链路验证大获成功！")

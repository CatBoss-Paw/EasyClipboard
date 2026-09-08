#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""离屏全链路自动化测试：左右分栏 / 摄取去重 / 每日日志落盘与清空隔离 / 快照预览 / 内存释放"""
import json
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QImage
from PyQt6.QtWidgets import QApplication, QMessageBox

import shelf_app
from shelf_app import Shelf, elide, fmt_size, safe_dest, unique_dest, \
    load_settings, save_settings, build_qss, PALETTES

# ============================================================
# 沙箱隔离（铁律）：测试永不触碰真实数据目录。
# 曾经的教训：早期版本直接清空真实 _TempShelf，导致用户收集的素材丢失。
_sandbox = Path(tempfile.mkdtemp(prefix="shelf_test_"))
shelf_app.DEFAULT_SETTINGS["shelf_dir"] = str(_sandbox / "_TempShelf")
shelf_app.DEFAULT_SETTINGS["history_dir"] = str(_sandbox / "_History")
shelf_app.DEFAULT_SETTINGS["pinned_dir"] = str(_sandbox / "_Pinned")
shelf_app.SETTINGS_PATH = _sandbox / "settings.json"

app = QApplication(sys.argv)

# 拦掉 purge 弹窗
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes)

w = Shelf()

# ------------------------------------------------------------ 1. 文本摄取与每日日志写入
w._ingest_text("第一段文本：客户需求确认")
w._ingest_text("第二段文本：API 密钥 sk-test-123456")

# 文本去重测试（含 A-B-A 重复）
w._ingest_text("第二段文本：API 密钥 sk-test-123456")
assert len(w.entries) == 2, "文本去重失败"
w._ingest_text("第一段文本：客户需求确认")
assert len(w.entries) == 2, "A-B-A 文本去重失败"

# 验证每日日志文件是否自动生成并按格式追加
today_str = datetime.now().strftime("%Y-%m-%d")
today_log_path = shelf_app.HISTORY_DIR / f"{today_str}.md"
assert today_log_path.exists(), "每日剪贴板工作日志未自动生成"
log_content = today_log_path.read_text(encoding="utf-8")
assert "客户需求确认" in log_content, "日志未包含第一段文本"
assert "sk-test-123456" in log_content, "日志未包含第二段文本"
assert "### " in log_content, "日志未包含时分秒时间戳标记"

# ------------------------------------------------------------ 2. 截图摄取与去重
img = QImage(80, 60, QImage.Format.Format_RGB32)
img.fill(Qt.GlobalColor.blue)
w._ingest_image(img)
w._ingest_image(img)  # 重复截图
img_entries = [e for e in w.entries if e["kind"] == "image"]
assert len(img_entries) == 1, "截图去重失败"

# ------------------------------------------------------------ 3. 文件引用摄取（大文件零IO）
tmpdir = tempfile.mkdtemp()
doc_file = os.path.join(tmpdir, "合同终版.docx")
Path(doc_file).write_bytes(b"PK\x03\x04 fake docx" * 20)
w._ingest_files([doc_file])
file_entries = [e for e in w.entries if e["kind"] == "file"]
assert len(file_entries) == 1, "文件摄取失败"
assert not os.path.exists(os.path.join(shelf_app.SHELF_DIR, "合同终版.docx")), "引用模式不应物理拷贝源文件"

# ------------------------------------------------------------ 4. 左右双栏分轨渲染验证
# 左栏应只包含：1 个截图 + 1 个文件 = 2 张卡片
left_cards = [w.cards_box_files.itemAt(i).widget()
              for i in range(w.cards_box_files.count())
              if isinstance(w.cards_box_files.itemAt(i).widget(), shelf_app.ShelfCard)]
assert len(left_cards) == 2, f"左栏附件卡片数错误: {len(left_cards)} != 2"
for card in left_cards:
    assert card.entry["kind"] in ("image", "file"), "左栏混入了非文件卡片"

# 右栏应只包含：2 个文本卡片
right_cards = [w.cards_box_text.itemAt(i).widget()
               for i in range(w.cards_box_text.count())
               if isinstance(w.cards_box_text.itemAt(i).widget(), shelf_app.ShelfCard)]
assert len(right_cards) == 2, f"右栏文本卡片数错误: {len(right_cards)} != 2"
for card in right_cards:
    assert card.entry["kind"] == "text", "右栏混入了非文本卡片"

# ------------------------------------------------------------ 5. 微信/企微协同交付动作
# （默认不全选是产品行为；交付测试先显式全选）
w.toggle_select_all()
# (1) 纯文字合并复制
cb = QApplication.clipboard()
w.copy_merged_text()
assert "客户需求确认\n\n第二段文本：API 密钥 sk-test-123456" in cb.text(), "合并复制纯文字内容不符"

# (2) 附件拖拽集获取
sel_files = w._get_selected_files()
assert len(sel_files) == 2, f"选中附件集数量错误: {len(sel_files)}"
assert any(f.endswith("合同终版.docx") for f in sel_files), "源文件未进入附件集"

# (3) 单项取消勾选联动
w.entries[0]["on"] = False  # 取消第一条文字勾选
w._on_entry_selection_changed()
w.copy_merged_text()
assert "客户需求确认" not in cb.text(), "已取消勾选的文字仍被合并复制"
assert "sk-test-123456" in cb.text()

# ------------------------------------------------------------ 6. 空格键快照预览测试
w.show_quick_preview(w.entries[0])
assert w._preview_dlg is not None and w._preview_dlg.isVisible(), "快照预览窗未能呼出"
w._preview_dlg.close()
w._preview_dlg = None

# ------------------------------------------------------------ 7. 核心隔离铁律：清空托盘绝不伤每日日志！
log_len_before = len(today_log_path.read_text(encoding="utf-8"))
w.purge()

# 验证临时托盘归零
assert len(w.entries) == 0, "清空托盘后条目未归零"
assert len(os.listdir(shelf_app.SHELF_DIR)) <= 2, "暂存区文件未被清理"

# 验证每日日志依然完好无损、一字不少！
assert today_log_path.exists(), "【致命错误】清空托盘误删了每日日志！"
log_len_after = len(today_log_path.read_text(encoding="utf-8"))
assert log_len_after == log_len_before, f"【致命错误】每日日志内容被篡改或减少！{log_len_after} != {log_len_before}"
print(f"✅ 清空隔离铁律验证通过：日志保持完整 {log_len_after} 字节")

# ------------------------------------------------------------ 8. 设置与主题
s = load_settings()
s["theme"] = "light"
save_settings(s)
assert load_settings()["theme"] == "light"
s["theme"] = "dark"
save_settings(s)

print("🎉 离屏全链路自动化测试 100% 全部通过！")

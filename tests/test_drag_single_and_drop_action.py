#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import json
import sys
import tempfile
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="shelf_drag_anti_multi_"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import shelf_app
from PyQt6.QtWidgets import QApplication, QListWidget
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QDrag, QImage

def main():
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
    shelf_app.SHELF_DIR = TMP / "_TempShelf"
    shelf_app.HISTORY_DIR = TMP / "_History"
    shelf_app.PINNED_DIR = TMP / "_Pinned"
    for k in ("shelf_dir", "history_dir", "pinned_dir"):
        Path(s[k]).mkdir(parents=True, exist_ok=True)

    app = QApplication.instance() or QApplication(sys.argv[:1])

    # 拦截 QDrag
    dragged_records = []
    def spy_exec(self, actions=None, *a, **kw):
        mime = self.mimeData()
        dragged_records.append({
            "urls": [u.toLocalFile() for u in mime.urls()] if mime.hasUrls() else [],
            "has_image": mime.hasImage(),
            "actions": actions,
        })
        return Qt.DropAction.CopyAction

    orig_exec = QDrag.exec
    QDrag.exec = spy_exec

    try:
        sh = shelf_app.Shelf()
        sh.resize(900, 620)
        sh.show()

        # 生成一张真实测试图片
        img_p1 = TMP / "_TempShelf" / "test1.png"
        img_p2 = TMP / "_TempShelf" / "test2.png"
        qimg = QImage(64, 64, QImage.Format.Format_RGB32)
        qimg.fill(Qt.GlobalColor.red)
        qimg.save(str(img_p1))
        qimg.save(str(img_p2))

        # 模拟 3 个条目，其中 2 个处于已勾选状态 (on=True)
        sh.entries = [
            {"kind": "image", "name": "test1.png", "on": True, "ts": "10:00", "at": 1},
            {"kind": "image", "name": "test2.png", "on": True, "ts": "10:01", "at": 2},
            {"kind": "text", "text": "普通文本", "on": False, "ts": "10:02", "at": 3},
        ]
        sh._sync_ui()

        # 1. 测试单卡拖拽独立性：即使 entries 里面有两个勾选，直接拖 test1.png 卡片，也只能拖出 test1.png！
        dragged_records.clear()
        sh.start_card_drag(sh.entries[0])
        assert len(dragged_records) == 1, "必须触发了一次拖拽"
        assert len(dragged_records[0]["urls"]) == 1, f"单卡拖拽必须只有 1 个文件，实测有: {len(dragged_records[0]['urls'])}"
        assert "test1.png" in dragged_records[0]["urls"][0]
        assert dragged_records[0]["has_image"] is True, "图片拖拽必须注入位图数据"
        print("[PASS] 单卡拖拽隔离验证通过：多选状态下拖单张卡片绝不打包其余文件！")

        # 2. 测试批量整包拖出：点击底栏批量拖出时，应该打包所有勾选项
        dragged_records.clear()
        sh.start_batch_drag()
        assert len(dragged_records) == 1
        assert len(dragged_records[0]["urls"]) == 2, f"批量整包拖出必须包含 2 个勾选文件，实测有: {len(dragged_records[0]['urls'])}"
        print("[PASS] 底栏批量拖出整包功能正常！")

        # 3. 测试 QuickList 选择模式必须是 SingleSelection
        assert sh.quick_list.selectionMode() == QListWidget.SelectionMode.SingleSelection, "QuickList 必须为 SingleSelection"
        print("[PASS] 快速访问区 SingleSelection 模式验证通过，禁止划拉强行多选！")

        print("\n=== 全部拖拽防多选与微信位图专项验证 100% 通过！===")
    finally:
        QDrag.exec = orig_exec

if __name__ == "__main__":
    main()

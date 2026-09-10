#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import json
import sys
import tempfile
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="shelf_geo_test_"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import shelf_app
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QPoint

def main():
    s = {
        "shelf_dir": str(TMP / "_TempShelf"),
        "history_dir": str(TMP / "_History"),
        "pinned_dir": str(TMP / "_Pinned"),
        "prompts_dir": str(TMP / "_Prompts"),
        "min_text_len": 2, "auto_clear_hours": 0,
        "hotkey": "f9", "autostart": False,
        "win_x": 420, "win_y": 260, "win_w": 500, "win_h": 400,
        "pinned": True,
    }
    f = TMP / "shelf_settings.json"
    f.write_text(json.dumps(s, ensure_ascii=False), encoding="utf-8")
    shelf_app.SETTINGS_PATH = f
    shelf_app.SHELF_DIR = TMP / "_TempShelf"
    shelf_app.HISTORY_DIR = TMP / "_History"
    shelf_app.PINNED_DIR = TMP / "_Pinned"
    for k in ("shelf_dir", "history_dir", "pinned_dir", "prompts_dir"):
        Path(s[k]).mkdir(parents=True, exist_ok=True)

    app = QApplication.instance() or QApplication(sys.argv[:1])

    sh = shelf_app.Shelf()
    sh.show()

    # 1. 验证原地位置恢复：必须是 420, 260
    pos = sh.pos()
    print(f"窗口当前坐标: ({pos.x()}, {pos.y()})，尺寸: {sh.width()}x{sh.height()}")
    assert pos.x() == 420, f"X坐标期望 420，实测 {pos.x()}"
    assert pos.y() == 260, f"Y坐标期望 260，实测 {pos.y()}"
    print("[PASS] 窗口原地坐标恢复验证通过！")

    # 2. 模拟拖动后保存
    sh.move(550, 330)
    sh._save_current_geometry()
    reloaded = json.loads(f.read_text(encoding="utf-8"))
    assert reloaded["win_x"] == 550 and reloaded["win_y"] == 330, "拖拽后必须持久化写入设置"
    print("[PASS] 窗口拖拽后位置持久化验证通过！")

    # 3. 验证 show_and_activate 绝不移回右上角
    sh.show_and_activate()
    assert sh.pos().x() == 550 and sh.pos().y() == 330, "唤出时必须稳稳停在原地！"
    print("[PASS] show_and_activate 原地保持验证通过！")

    # 4. 验证 toggle_pin 持久化
    orig_pin = sh._pinned
    sh.toggle_pin()
    assert sh._pinned != orig_pin, "图钉切换成功"
    reloaded2 = json.loads(f.read_text(encoding="utf-8"))
    assert reloaded2["pinned"] == sh._pinned, "图钉置顶状态成功持久化"
    print("[PASS] 窗口图钉置顶持久化验证通过！")

    print("\n=== 全部原地记忆与持久化测试 100% 通过！===")

if __name__ == "__main__":
    main()

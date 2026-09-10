#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="shelf_wakeup_test_"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import shelf_app
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer

def main():
    s = {
        "shelf_dir": str(TMP / "_TempShelf"),
        "history_dir": str(TMP / "_History"),
        "pinned_dir": str(TMP / "_Pinned"),
        "prompts_dir": str(TMP / "_Prompts"),
        "min_text_len": 2, "auto_clear_hours": 0,
        "hotkey": "f9", "autostart": False,
        "win_x": 400, "win_y": 300, "win_w": 500, "win_h": 400,
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

    test_key = "SmartStagingShelf.TestWakeupSocket"

    # 1. 验证首个实例获取单实例成功
    activated_count = [0]
    def on_act():
        activated_count[0] += 1

    ok1 = shelf_app.acquire_single_instance(on_act, key=test_key)
    assert ok1 is True, "首个实例必须成功获取单实例监听"
    print("[PASS] 首实例成功监听 SingleInstance Socket！")

    # 2. 模拟真实场景：启动子进程（模拟桌面双击启动新实例）尝试获取单实例
    child_code = f"""
import sys
from pathlib import Path
sys.path.insert(0, r"{Path(__file__).resolve().parent.parent}")
import shelf_app
shelf_app.SHELF_DIR = Path(r"{TMP / '_TempShelf'}")
ret = shelf_app.acquire_single_instance(key="{test_key}")
sys.exit(0 if ret is False else 1)
"""
    p = subprocess.Popen([sys.executable, "-c", child_code])
    
    # 驱动主进程事件循环接收子进程的 Socket 唤醒
    t0 = time.time()
    while p.poll() is None or activated_count[0] == 0:
        app.processEvents()
        time.sleep(0.02)
        if time.time() - t0 > 4.0:
            break

    exit_code = p.wait()
    assert exit_code == 0, f"新实例必须识别出已有实例并退出(0)，实测 {exit_code}"
    assert activated_count[0] >= 1, f"首实例应收到唤醒信号，实测 {activated_count[0]}"
    print("[PASS] 跨进程桌面快捷方式双击唤醒 Socket 通道验证通过！")

    # 3. 验证主窗口的 _poll_backend 对 .wake_sig 文件信号的消费与响应
    sh = shelf_app.Shelf()
    sh.show()
    wake_file = shelf_app.SHELF_DIR / ".wake_sig"
    wake_file.write_text(str(time.time()), encoding="utf-8")
    assert wake_file.exists(), "测试信号文件必须创建成功"

    # 执行 _poll_backend 轮询
    sh._poll_backend()
    assert not wake_file.exists(), ".wake_sig 必须被 _poll_backend 瞬间消费并删除！"
    print("[PASS] 文件信号双保险 .wake_sig 轮询消费验证通过！")

    print("\n=== 单实例 Socket 与文件信号双保险唤醒测试 100% 通过！===")
    sh.close()

if __name__ == "__main__":
    main()

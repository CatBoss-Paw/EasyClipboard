"""构造期冒烟：逐步定位新全局 eventFilter 的崩溃点。"""
import json
import sys
import tempfile
import time
from pathlib import Path

import faulthandler
faulthandler.enable()

TMP = Path(tempfile.mkdtemp(prefix="shelf_smoke_"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
ctypes_ok = True
import ctypes
ctypes.windll.shcore.SetProcessDpiAwareness(2)

import shelf_app as S
from PyQt6.QtWidgets import QApplication

s = {
    "shelf_dir": str(TMP / "_TempShelf"),
    "history_dir": str(TMP / "_History"),
    "pinned_dir": str(TMP / "_Pinned"),
    "min_text_len": 2, "auto_clear_hours": 0,
    "hotkey": "f9", "autostart": False,
}
(TMP / "shelf_settings.json").write_text(json.dumps(s, ensure_ascii=False), encoding="utf-8")
S.SETTINGS_PATH = TMP / "shelf_settings.json"
S.SHELF_DIR = TMP / "_TempShelf"
S.HISTORY_DIR = TMP / "_History"
S.PINNED_DIR = TMP / "_Pinned"
for k in ("shelf_dir", "history_dir", "pinned_dir"):
    Path(s[k]).mkdir(parents=True, exist_ok=True)

print("step1: imports+settings done", flush=True)
app = QApplication(sys.argv[:1])
print("step2: QApplication ok", flush=True)
sh = S.Shelf()
print("step3: Shelf() ok", flush=True)
sh.resize(560, 480)
sh.move(80, 80)
print("step4: resize/move ok", flush=True)
sh.show()
print("step5: show ok", flush=True)
for i in range(20):
    time.sleep(0.05)
    app.processEvents()
print("step6: event loop 1s ok", flush=True)
sh.close()
print("SMOKE-OK", flush=True)

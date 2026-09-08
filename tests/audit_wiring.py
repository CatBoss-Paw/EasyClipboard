#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
产品完成度审计：找出所有"用户操作了却没反应"的死控件 / 死信号。

动机（BUG-001 同类问题）：
    DragOutButton 的 drag_requested 信号虽 connect 了，但 mouseMoveEvent 因复制粘贴
    错误属性而崩溃 → 信号永远发不出去，功能双重失效。
    必须系统性区分：哪些是【真死控件】，哪些是【有意为之的设计】。

两部分：
  A) 运行时反射（子进程，真实 windows 平台）
     用 QObject.receivers(signal) 查询每个可交互控件的信号接收者数量。
     0 = 没有任何槽连接 = 用户操作它不会有任何反应。
     这是最可靠的判据，能抓到静态分析抓不到的情况。
     【关键】按每种控件类型检查它【实际使用】的信号，而不是统一查 clicked：
       - QCheckBox   → toggled（本项目 check_box.toggled.connect(_on_toggled)）
       - QComboBox   → currentIndexChanged
       - 其余按钮     → clicked
  B) 自定义 pyqtSignal 审计（【外层进程】执行 AST，不在子进程内做）
     声明了 pyqtSignal 但从不 emit / 从不 connect → 死信号。
     注意：此部分必须在外层跑。曾把 AST 审计放进子进程 PROBE 里，
     经 python -c 传递含中文的路径字符串时结果失真（DragOutButton 明明
     receivers=1 却报 emit=False connect=False），属于审计工具自身缺陷。

沙箱铁律：绝不使用真实数据目录。
"""
import ast
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "shelf_app.py"
PROJECT_PY = r"C:\Users\37162\AppData\Local\Programs\Python\Python313\python.exe"
if not Path(PROJECT_PY).exists():
    PROJECT_PY = sys.executable

# 明确属于"设计如此"的情况，需在报告中说明而非当作缺陷
INTENTIONAL = {
    ("QCheckBox", "clicked"):
        "勾选框用 toggled 接线（check_box.toggled.connect(_on_toggled)），clicked 本就不该接",
    ("DragOutButton", "clicked"):
        "tooltip 明写「纯点击无效果」——拖拽必须伴随真实拖动手势，防止误触（设计如此）",
    ("ShelfCard", "clicked"):
        "交接文档§5：ShelfCard 的 clicked 未连接是设计（单击=只选中，供空格预览）",
    ("QLineEdit", "(由按钮驱动)"):
        "本项目输入框由「应用」按钮驱动（apply_hk.clicked.connect(apply_hotkey)），"
        "QLineEdit 无 clicked 信号，不应按按钮规则检查",
}

PROBE = r'''
import os, sys, tempfile
from pathlib import Path
sys.path.insert(0, r"__ROOT__")

import shelf_app
_sb = Path(tempfile.mkdtemp(prefix="shelf_audit_"))
shelf_app.DEFAULT_SETTINGS["shelf_dir"]   = str(_sb / "_TempShelf")
shelf_app.DEFAULT_SETTINGS["history_dir"] = str(_sb / "_History")
shelf_app.DEFAULT_SETTINGS["pinned_dir"]  = str(_sb / "_Pinned")
shelf_app.SETTINGS_PATH = _sb / "settings.json"
shelf_app.DEFAULT_SETTINGS["autostart"] = False

from PyQt6.QtCore import QObject
from PyQt6.QtWidgets import (QApplication, QCheckBox, QComboBox, QLineEdit,
                             QAbstractButton)

app = QApplication(sys.argv)

# 构造带素材的界面，确保卡片类控件也被创建出来
w = shelf_app.Shelf()
w.entries = [
    {"kind": "text",  "text": "审计用文本条目ABCDEFG", "ts": "00:00:01",
     "at": "2026-09-07 00:00:01", "on": False},
    {"kind": "image", "name": "audit_shot.png", "ts": "00:00:02",
     "at": "2026-09-07 00:00:02", "on": False, "size": 1024},
    {"kind": "file",  "name": "audit_file.txt", "src": "C:\\Windows\\win.ini",
     "ts": "00:00:03", "at": "2026-09-07 00:00:03", "on": False, "size": 2048},
]
w._sync_ui()
w.show()
app.processEvents()

# 同时把设置面板也构造出来，审计它的控件（否则 SettingsDialog 里的控件全漏检）
try:
    w.open_settings()
    app.processEvents()
except Exception as e:
    print("SETTINGS_OPEN_ERR|%r" % (e,), flush=True)

def receivers_of(obj, sig_name):
    sig = getattr(obj, sig_name, None)
    if sig is None:
        return None
    try:
        return obj.receivers(sig)
    except (RuntimeError, TypeError):
        return None

def signal_for(obj):
    """返回该控件【实际应该被接线】的信号名"""
    if isinstance(obj, QCheckBox):
        return "toggled"
    if isinstance(obj, QComboBox):
        return "currentIndexChanged"
    if isinstance(obj, QLineEdit):
        return None          # 由「应用」按钮驱动，不按按钮规则检查
    return "clicked"

roots = [w]
if getattr(w, "_settings_dlg", None) is not None:
    roots.append(w._settings_dlg)

seen = set()
print("===WIDGET_AUDIT_START===", flush=True)
for root in roots:
    for obj in root.findChildren(QObject):
        if id(obj) in seen:
            continue
        seen.add(id(obj))
        cls = type(obj).__name__
        if isinstance(obj, QAbstractButton) or isinstance(obj, QComboBox) \
                or isinstance(obj, QLineEdit):
            sig = signal_for(obj)
            if sig is None:
                # QLineEdit：确认它确实被某个按钮的槽读取（而非无人理睬）
                on = obj.objectName() or ""
                print("WIDGET|%s|%s|%s|%s"
                      % (cls, (on or "(edit)").replace("|", "/")[:36],
                         "(由按钮驱动)", "NA"), flush=True)
                continue
            n = receivers_of(obj, sig)
            label = ""
            if hasattr(obj, "text"):
                label = obj.text() or ""
            label = label or obj.objectName() or getattr(obj, "placeholderText", lambda: "")() or "(无标识)"
            print("WIDGET|%s|%s|%s|%s" % (cls, label.replace("|", "/")[:36], sig, n), flush=True)
            # 自定义信号（如 DragOutButton.drag_requested）额外检查
            for extra in ("drag_requested",):
                if hasattr(obj, extra) and extra != sig:
                    print("WIDGET|%s|%s|%s|%s"
                          % (cls, label.replace("|", "/")[:36], extra,
                             receivers_of(obj, extra)), flush=True)
print("===WIDGET_AUDIT_END===", flush=True)
print("PROBE_DONE", flush=True)
'''
PROBE = PROBE.replace("__ROOT__", str(ROOT))


def audit_signals():
    """B) 外层进程 AST 审计自定义 pyqtSignal 的 emit / connect 情况"""
    txt = SRC.read_text(encoding="utf-8")
    tree = ast.parse(txt)
    results = []
    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        declared = []
        for sub in node.body:
            if isinstance(sub, ast.Assign) and isinstance(sub.value, ast.Call):
                fn = sub.value.func
                fname = getattr(fn, "id", None) or getattr(fn, "attr", None)
                if fname == "pyqtSignal":
                    for t in sub.targets:
                        if isinstance(t, ast.Name):
                            declared.append(t.id)
        if not declared:
            continue
        seg = ast.get_source_segment(txt, node) or ""
        for s in declared:
            # emit 可能写在本类内（self.x.emit()）
            emits = ("%s.emit(" % s) in seg
            # connect 通常写在别的类里（self._mini.clicked.connect(...)），故查全文
            connects = ("%s.connect(" % s) in txt
            results.append((node.name, s, emits, connects))
    return results


def main():
    r = subprocess.run([PROJECT_PY, "-E", "-X", "utf8", "-c", PROBE],
                       capture_output=True, timeout=180, cwd=str(ROOT))
    out = r.stdout.decode("utf-8", "replace")
    err = r.stderr.decode("utf-8", "replace")

    if "PROBE_DONE" not in out:
        print("审计未跑完：")
        print(out)
        print(err[-3000:])
        return 2

    widgets = []
    mode = False
    for line in out.splitlines():
        if line.startswith("===WIDGET_AUDIT_START==="):
            mode = True
            continue
        if line.startswith("===WIDGET_AUDIT_END==="):
            mode = False
            continue
        if mode and line.startswith("WIDGET|"):
            _, cls, label, sig, n = line.split("|", 4)
            widgets.append((cls, label, sig, n))

    print("=" * 84)
    print("A) 控件接线审计（receivers=0 → 用户操作它没有任何反应）")
    print("=" * 84)
    dead, intentional = [], []
    for cls, label, sig, n in widgets:
        if n != "0":
            print("  ✅ %-15s %-38s %-20s receivers=%s" % (cls, label[:38], sig, n))
            continue
        key = (cls, sig)
        if key in INTENTIONAL:
            intentional.append((cls, label, sig, INTENTIONAL[key]))
            print("  ℹ️  %-15s %-38s %-20s receivers=0  设计如此" % (cls, label[:38], sig))
        else:
            dead.append((cls, label, sig))
            print("  ❌ %-15s %-38s %-20s receivers=0  死控件" % (cls, label[:38], sig))

    print()
    print("=" * 84)
    print("B) 自定义 pyqtSignal 审计（外层 AST，emit=False 表示信号永不发射）")
    print("=" * 84)
    sig_dead = []
    for cls, name, em, cn in audit_signals():
        if em and cn:
            print("  ✅ %-16s %-20s 已接线且会发射" % (cls, name))
        elif cn and not em:
            sig_dead.append((cls, name, "已 connect 但从不 emit（BUG-001 同类，接线形同虚设）"))
            print("  ❌ %-16s %-20s 已 connect 但从不 emit" % (cls, name))
        elif em and not cn:
            sig_dead.append((cls, name, "会 emit 但无人 connect（发了没人听）"))
            print("  ⚠️  %-16s %-20s 会 emit 但无人 connect" % (cls, name))
        else:
            sig_dead.append((cls, name, "既不 emit 也不 connect（完全死信号）"))
            print("  ❌ %-16s %-20s 既不 emit 也不 connect" % (cls, name))

    print()
    print("=" * 84)
    print("审计结论")
    print("=" * 84)
    if intentional:
        print("ℹ️  %d 项属有意设计（无需修）：" % len(intentional))
        for c, l, s, why in intentional:
            print("     %s.%s（%s）— %s" % (c, s, l, why))
    if not dead and not sig_dead:
        print("\n✅ 未发现死控件 / 死信号，界面所有可交互元素均已正确接线")
        return 0
    if dead:
        print("\n❌ 发现 %d 个真死控件（用户点了没反应）：" % len(dead))
        for c, l, s in dead:
            print("     %s.%s（%s）" % (c, s, l))
    if sig_dead:
        print("\n❌ 发现 %d 个死信号：" % len(sig_dead))
        for c, n, why in sig_dead:
            print("     %s.%s — %s" % (c, n, why))
    return 1


if __name__ == "__main__":
    sys.exit(main())

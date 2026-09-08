#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BUG 复现测试：文本卡片"双击复制"未实装。

交接文档 §6 待办 #2 与交接提示词第三步 #2 均声称"已实装程序内双击自判定
（450ms + 12px）"，但实际代码中：
  - ShelfCard._last_press 只在 __init__ 里赋值为 None，全文件从未被读取（死变量）
  - ShelfCard 从未覆写 mouseDoubleClickEvent
  → 双击文本卡片不会复制。而 meta_lab 文案却写着"双击复制"，属于对用户的功能承诺落空。

关键框架事实（Rule 7，已按 Qt 行为设计两条互补路径验证）：
  Qt 双击事件序列并非"两次 MouseButtonPress"。当两次按压的位移小于系统双击阈值
  （Windows SM_CXDOUBLECLK，通常 4px）时，第二次按下派发的是 MouseButtonDblClick，
  而【不是】 MouseButtonPress —— 此时覆写的 mousePressEvent 根本收不到第二次按压。
  只有手抖超过该阈值时，第二次按下才是普通 Press。
  这正是交接文档踩坑 #3 所述"双击复制时好时坏"的真实机理：只改 mousePressEvent
  无法覆盖 Qt 已判定为双击的那一半情况。
  因此本测试分别验证两条路径，二者必须都能触发复制。

沙箱铁律：绝不触碰真实数据目录。
"""
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

PROJECT_PY = r"C:\Users\37162\AppData\Local\Programs\Python\Python313\python.exe"
if not Path(PROJECT_PY).exists():
    PROJECT_PY = sys.executable

PROBE = r'''
import os, sys, tempfile
from pathlib import Path
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, r"__ROOT__")

import shelf_app
_sandbox = Path(tempfile.mkdtemp(prefix="shelf_dbl_"))
shelf_app.DEFAULT_SETTINGS["shelf_dir"]   = str(_sandbox / "_TempShelf")
shelf_app.DEFAULT_SETTINGS["history_dir"] = str(_sandbox / "_History")
shelf_app.DEFAULT_SETTINGS["pinned_dir"]  = str(_sandbox / "_Pinned")
shelf_app.SETTINGS_PATH = _sandbox / "settings.json"

from PyQt6.QtCore import Qt, QPointF, QEvent
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtWidgets import QApplication

app = QApplication(sys.argv)
w = shelf_app.Shelf()

# 记录 copy_single_entry 的真实调用（不改动被测逻辑，只做观测）
calls = []
w.copy_single_entry = lambda e: calls.append(("copy", e))
w.open_entry        = lambda e: calls.append(("open", e))

ENTRY = {"kind": "text", "text": "双击复制测试文本ABCDEFG", "ts": "00:00:00", "on": False}

def mev(t, lx, ly):
    return QMouseEvent(t, QPointF(lx, ly), QPointF(lx + 300, ly + 300),
                       Qt.MouseButton.LeftButton,
                       Qt.MouseButton.LeftButton if t == QEvent.Type.MouseMove
                       else (Qt.MouseButton.LeftButton if "Press" in str(t) or "DblClick" in str(t)
                             else Qt.MouseButton.NoButton),
                       Qt.KeyboardModifier.NoModifier)

def release(lx, ly):
    return QMouseEvent(QEvent.Type.MouseButtonRelease, QPointF(lx, ly), QPointF(lx + 300, ly + 300),
                       Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton,
                       Qt.KeyboardModifier.NoModifier)

# ---- 静态证据 ----
import inspect
# 静态证据：路径 A 的自判定逻辑是否真的存在。
# 实现上 mousePressEvent 委托给 _maybe_double_click()，_last_press 的读写在后者里，
# 所以两个方法的源码合并检查。
src_press = inspect.getsource(shelf_app.ShelfCard.mousePressEvent)
if "_maybe_double_click" in shelf_app.ShelfCard.__dict__:
    src_press += inspect.getsource(shelf_app.ShelfCard._maybe_double_click)
print("PRESS_READS_LAST_PRESS=%s" % ("_last_press" in src_press), flush=True)
print("OVERRIDES_DBLCLICK=%s"
      % ("mouseDoubleClickEvent" in shelf_app.ShelfCard.__dict__), flush=True)

# ============ 路径 A：手抖超出 Qt 原生双击阈值，但仍在双击容差内 ============
# 边界计算（度量均为 manhattanLength，与实现一致）：
#   Qt 原生双击阈值 SM_CX/CYDOUBLECLK = 每轴 4px；单轴位移 >4px 时 Qt 判不出双击，
#   第二次按下派发普通 MouseButtonPress（而非 DblClick）→ 必须靠 _maybe_double_click。
#   取 dx=dy=5：单轴 5 > 4（Qt 判不出），manhattan=10 <= CARD_DBLCLICK_MAX_DIST=12
#   （仍属双击容差），且 10 < CARD_DRAG_THRESHOLD=14（不会被误判为拖拽）。
# 注意：旧用例用 dx=dy=8 → manhattan=16，既超双击上限又超拖拽阈值，
#       不判为双击是【正确行为】，那是用例本身的缺陷而非产品缺陷。
calls.clear()
c1 = shelf_app.ShelfCard(dict(ENTRY), w, False)
c1.mousePressEvent(mev(QEvent.Type.MouseButtonPress, 10, 10))
c1.mouseReleaseEvent(release(10, 10))
c1.mousePressEvent(mev(QEvent.Type.MouseButtonPress, 15, 15))   # 单轴5px、间隔极短
c1.mouseReleaseEvent(release(15, 15))
print("PATH_A_JITTER_COPY=%s" % bool([c for c in calls if c[0] == "copy"]), flush=True)

# ============ 路径 A 反向：手抖超过拖拽阈值时必须判为拖拽，不得复制 ============
calls.clear()
c5 = shelf_app.ShelfCard(dict(ENTRY), w, False)
w.start_card_drag = lambda e: calls.append(("drag", e))
c5.mousePressEvent(mev(QEvent.Type.MouseButtonPress, 10, 10))
c5.mouseReleaseEvent(release(10, 10))
c5.mousePressEvent(mev(QEvent.Type.MouseButtonPress, 18, 18))
c5.mouseMoveEvent(mev(QEvent.Type.MouseMove, 40, 40))   # manhattan 60 > 14 → 拖拽
c5.mouseReleaseEvent(release(40, 40))
print("PATH_A_DRAG_NOT_COPY=%s"
      % (bool([c for c in calls if c[0] == "drag"])
         and not [c for c in calls if c[0] == "copy"]), flush=True)

# ============ 路径 B：零手抖（Qt 判定为双击，第二次是 DblClick 事件）============
calls.clear()
c2 = shelf_app.ShelfCard(dict(ENTRY), w, False)
c2.mousePressEvent(mev(QEvent.Type.MouseButtonPress, 10, 10))
c2.mouseReleaseEvent(release(10, 10))
c2.mouseDoubleClickEvent(mev(QEvent.Type.MouseButtonDblClick, 10, 10))
c2.mouseReleaseEvent(release(10, 10))
print("PATH_B_NATIVE_DBLCLICK_COPY=%s" % bool([c for c in calls if c[0] == "copy"]), flush=True)

# ============ 反向保护：图片/文件卡片双击不得复制，而是打开 ============
calls.clear()
c6 = shelf_app.ShelfCard({"kind": "file", "name": "x.txt", "src": "x.txt",
                          "size": 1, "ts": "00:00:00", "on": False}, w, True)
c6.mousePressEvent(mev(QEvent.Type.MouseButtonPress, 10, 10))
c6.mouseReleaseEvent(release(10, 10))
c6.mouseDoubleClickEvent(mev(QEvent.Type.MouseButtonDblClick, 10, 10))
c6.mouseReleaseEvent(release(10, 10))
print("FILE_DBLCLICK_OPENS=%s"
      % bool([c for c in calls if c[0] == "open"] and not [c for c in calls if c[0] == "copy"]),
      flush=True)

# ============ 反向保护：单击不得触发复制（防误触）============
calls.clear()
c3 = shelf_app.ShelfCard(dict(ENTRY), w, False)
c3.mousePressEvent(mev(QEvent.Type.MouseButtonPress, 10, 10))
c3.mouseReleaseEvent(release(10, 10))
print("SINGLE_CLICK_NO_COPY=%s" % (not calls), flush=True)

# ============ 反向保护：慢速两次点击（间隔 > 阈值）不得触发复制 ============
calls.clear()
import time
c4 = shelf_app.ShelfCard(dict(ENTRY), w, False)
c4.mousePressEvent(mev(QEvent.Type.MouseButtonPress, 10, 10))
c4.mouseReleaseEvent(release(10, 10))
time.sleep(0.9)
c4.mousePressEvent(mev(QEvent.Type.MouseButtonPress, 11, 11))
c4.mouseReleaseEvent(release(11, 11))
print("SLOW_TWICE_NO_COPY=%s" % (not [c for c in calls if c[0] == "copy"]), flush=True)

print("PROBE_DONE", flush=True)
'''
PROBE = PROBE.replace("__ROOT__", str(ROOT))


def main():
    r = subprocess.run([PROJECT_PY, "-E", "-X", "faulthandler", "-c", PROBE],
                       capture_output=True, timeout=120, cwd=str(ROOT))
    out = r.stdout.decode("utf-8", "replace")
    err = r.stderr.decode("utf-8", "replace")
    # 子进程在 GBK 控制台输出中文时，解码会产生 U+FFFD，而本宿主 stdout 也是 GBK，
    # 直接 print 会 UnicodeEncodeError 把测试脚本自身撞死（已踩过），一律转 ASCII 安全。
    out = out.encode("ascii", "replace").decode("ascii")
    err = err.encode("ascii", "replace").decode("ascii")
    print("=" * 70)
    print("returncode =", r.returncode)
    print("-" * 70)
    print(out)
    if err.strip():
        print("-" * 30, "STDERR", "-" * 30)
        print(err[-2500:])
    print("=" * 70)

    if "PROBE_DONE" not in out:
        print("判定：无效复现 —— 探针未跑完（环境/依赖问题）")
        return 2

    kv = {}
    for line in out.splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            kv[k.strip()] = v.strip()

    path_a = kv.get("PATH_A_JITTER_COPY") == "True"
    path_b = kv.get("PATH_B_NATIVE_DBLCLICK_COPY") == "True"
    file_open = kv.get("FILE_DBLCLICK_OPENS") == "True"
    guards_ok = (kv.get("SINGLE_CLICK_NO_COPY") == "True"
                 and kv.get("SLOW_TWICE_NO_COPY") == "True"
                 and kv.get("PATH_A_DRAG_NOT_COPY") == "True")

    print("静态证据: mousePressEvent 读取 _last_press = %s ; 覆写 mouseDoubleClickEvent = %s"
          % (kv.get("PRESS_READS_LAST_PRESS"), kv.get("OVERRIDES_DBLCLICK")))
    print("路径A(手抖超Qt阈值但在容差内) 触发复制: %s" % path_a)
    print("路径B(Qt 原生双击)           触发复制: %s" % path_b)
    print("图片/文件双击 = 打开(非复制): %s" % file_open)
    print("防误触保护(单击/慢速/拖拽不复制) 通过: %s" % guards_ok)

    if path_a and path_b and guards_ok and file_open:
        print("\n判定：功能正常 —— 双击复制在两条路径下都生效，且无误触")
        return 0
    print("\n判定：缺陷成立 —— 双击复制未在下列路径生效: %s"
          % ", ".join([n for n, ok in (("A", path_a), ("B", path_b)) if not ok] or ["(仅防误触失败)"]))
    return 1


if __name__ == "__main__":
    sys.exit(main())

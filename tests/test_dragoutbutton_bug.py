#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BUG 复现测试：DragOutButton.mouseMoveEvent 引用了本类不存在的属性。

背景（交接文档 §4 踩坑 #1）：
    PyQt6 里事件处理器（覆写的虚方法）内抛出的 Python 异常不会被上层 try 捕获，
    而是走 qFatal → 进程静默死亡（无 traceback）。因此本测试把"触发一次 mouseMove"
    放进【独立子进程】执行：子进程非零退出/被 abort，即为缺陷成立的直接证据。

沙箱铁律：绝不触碰真实数据目录（DEFAULT_SETTINGS / SETTINGS_PATH 全部覆写到 tempdir）。
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# 项目实际使用的解释器（系统 Python 3.13.2 + PyQt6 6.11.0）。
# 注意：WPS 灵犀自带的 python-env 没有 PyQt6，且它的 .pth 会污染系统 Python 的
# site 初始化，因此用 -E 忽略继承的 PYTHONPATH。
PROJECT_PY = r"C:\Users\37162\AppData\Local\Programs\Python\Python313\python.exe"
if not Path(PROJECT_PY).exists():
    PROJECT_PY = sys.executable

# 子进程内执行的探测代码：
#   1) 静态断言 DragOutButton 没有 _drag_start_pos / shelf / entry 这三个属性
#   2) 构造真实按钮并派发一次"按住左键移动"事件，看进程是否存活
PROBE = r'''
import os, sys, tempfile
from pathlib import Path
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, r"__ROOT__")

import shelf_app
_sandbox = Path(tempfile.mkdtemp(prefix="shelf_probe_"))
shelf_app.DEFAULT_SETTINGS["shelf_dir"]   = str(_sandbox / "_TempShelf")
shelf_app.DEFAULT_SETTINGS["history_dir"] = str(_sandbox / "_History")
shelf_app.DEFAULT_SETTINGS["pinned_dir"]  = str(_sandbox / "_Pinned")
shelf_app.SETTINGS_PATH = _sandbox / "settings.json"

from PyQt6.QtCore import Qt, QPointF, QEvent
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtWidgets import QApplication, QPushButton

app = QApplication(sys.argv)

btn = shelf_app.DragOutButton("probe", "probe")

# ---- 静态证据：DragOutButton 及其基类链上都不存在这三个名字 ----
missing = [n for n in ("_drag_start_pos", "shelf", "entry") if not hasattr(btn, n)]
print("MISSING_ATTRS=" + ",".join(missing), flush=True)

# ---- 确认 mouseMoveEvent 源码确实引用了这些名字 ----
import inspect
src = inspect.getsource(shelf_app.DragOutButton.mouseMoveEvent)
refs = [n for n in ("_drag_start_pos", "self.shelf", "self.entry") if n in src]
print("SRC_REFS=" + ",".join(refs), flush=True)

# ---- 动态证据：派发一次真实 mouseMove（按住左键拖动）----
# 期望：mousePressEvent 先记下 _press_pos，mouseMoveEvent 里读 self._drag_start_pos
#       → AttributeError → PyQt6 qFatal → 进程 abort
press = QMouseEvent(QEvent.Type.MouseButtonPress, QPointF(10, 10), QPointF(100, 100),
                    Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
btn.mousePressEvent(press)
print("PRESS_OK", flush=True)

move = QMouseEvent(QEvent.Type.MouseMove, QPointF(60, 60), QPointF(150, 150),
                   Qt.MouseButton.NoButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
btn.mouseMoveEvent(move)
print("MOVE_SURVIVED", flush=True)
'''
PROBE = PROBE.replace("__ROOT__", str(ROOT))

def run_probe():
    r = subprocess.run([PROJECT_PY, "-E", "-c", PROBE],
                       capture_output=True, text=True, timeout=90, cwd=str(ROOT))
    return r

if __name__ == "__main__":
    r = run_probe()
    print("=" * 70)
    print("returncode =", r.returncode)
    print("-" * 70)
    print("STDOUT:\n" + r.stdout)
    print("-" * 70)
    print("STDERR:\n" + (r.stderr[-3000:] if r.stderr else "(empty)"))
    print("=" * 70)

    # 必须先排除"环境/import 失败"这类假阳性：探针跑完 press 阶段才会打印 PRESS_OK，
    # 连 PRESS_OK 都没有说明根本没进到待测代码，属于环境问题而非缺陷成立。
    if "PRESS_OK" not in r.stdout:
        print("判定：无效复现 —— 探针未跑到待测代码路径（环境/依赖问题），请检查上面的 STDERR")
        sys.exit(2)

    if "MOVE_SURVIVED" in r.stdout:
        print("判定：缺陷不存在 —— 派发 mouseMove 后进程存活")
        sys.exit(0)

    print("判定：缺陷成立 —— mousePressEvent 成功(PRESS_OK)，"
          "但派发 mouseMove 后进程异常终止（returncode=%s）" % r.returncode)
    sys.exit(1)

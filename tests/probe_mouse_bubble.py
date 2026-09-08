#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
校验 probe_resize_corner.py 的判据是否可信，并用最小复现确定事件到底会不会冒泡。

为什么需要这一步：
    探针报告「QFrame(obj='root') overrides_press=True -> 事件被截走」。
    但这个判据可疑：PyQt 的 sip 包装类会把父类方法平铺进自己的 __dict__，
    于是 `"mousePressEvent" in type(w).__dict__` 对【任何】 QWidget 都可能为
    True —— 若如此，探针的"被覆盖"结论就是误报，而我会据此改错代码。

    判据不可信就不能下结论，必须：
      1) 直接检验该判据对 QWidget/QFrame/QLabel/QPushButton 的返回值
      2) 用最小可复现工程实测「事件发给 QLabel/QFrame 后能否冒泡到父 widget」
    只有实测的冒泡行为才是真相（Iron Rule 7：框架行为不靠猜）。
"""
import sys

from PyQt6.QtCore import QEvent, QPointF, Qt
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtWidgets import (QApplication, QFrame, QLabel, QPushButton,
                             QWidget)

app = QApplication.instance() or QApplication(sys.argv[:1])

print("=" * 74)
print("【1】判据可信度检验: 'mousePressEvent' in cls.__dict__")
print("=" * 74)
for cls in (QWidget, QFrame, QLabel, QPushButton):
    own = "mousePressEvent" in cls.__dict__
    print("  %-13s -> %s" % (cls.__name__, own))
print()
verdict = all("mousePressEvent" in c.__dict__
              for c in (QWidget, QFrame, QLabel))
if verdict:
    print("  !! 判据对所有 QWidget 恒为 True -> 探针的 overrides_press 结论是")
    print("     误报，不能用它判定事件是否被截走。")
else:
    print("  判据有区分度，可信。")
print()

print("=" * 74)
print("【2】最小复现: 事件发给子控件后能否冒泡到父 widget")
print("=" * 74)


class Spy(QWidget):
    """记录自己有没有真的收到鼠标按下事件的父容器。"""

    def __init__(self):
        super().__init__()
        self.hits = []

    def mousePressEvent(self, ev):
        self.hits.append("PRESS")
        super().mousePressEvent(ev)


def mk(etype, local, glob, button, buttons):
    return QMouseEvent(etype, QPointF(local), QPointF(glob), button, buttons,
                       Qt.KeyboardModifier.NoModifier)


def trial(label, build_child):
    spy = Spy()
    spy.resize(200, 200)
    child = build_child(spy)
    spy.show()
    app.processEvents()

    target_pt = QPointF(190, 190)
    gp = child.mapToGlobal(target_pt)
    ev = mk(QEvent.Type.MouseButtonPress, target_pt, gp,
            Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton)
    app.sendEvent(child, ev)
    app.processEvents()
    bubbled = "PRESS" in spy.hits
    print("  %-34s 父 widget 收到 press: %s" % (label, bubbled))
    spy.close()
    return bubbled


def bare_frame(parent):
    f = QFrame(parent)
    f.setObjectName("root")
    f.setGeometry(0, 0, 200, 200)
    return f


def bare_label(parent):
    lb = QLabel("↘", parent)
    lb.setObjectName("sizeHint")
    lb.setGeometry(180, 186, 20, 14)
    return lb


def bare_button(parent):
    b = QPushButton("x", parent)
    b.setGeometry(170, 170, 30, 30)
    return b


def frame_with_label(parent):
    f = QFrame(parent)
    f.setObjectName("root")
    f.setGeometry(0, 0, 200, 200)
    lb = QLabel("↘", f)
    lb.setObjectName("sizeHint")
    lb.setGeometry(180, 186, 20, 14)
    return lb


r_frame = trial("QFrame(obj='root') 覆盖全窗", bare_frame)
r_label = trial("QLabel(obj='sizeHint') 在把手角", bare_label)
r_button = trial("QPushButton（对照：按钮必吃掉）", bare_button)
r_nested = trial("QFrame 内再套 QLabel（复刻真实层级）", frame_with_label)
print()

print("=" * 74)
print("【3】结论")
print("=" * 74)
if r_frame and r_label and r_nested:
    print("  QFrame / QLabel 都【不】吃掉鼠标事件，会冒泡到父 widget。")
    print("  -> 探针的『把手被覆盖』结论是【误报】，缩放把手在事件层面是可达的。")
    print("  -> 用户反馈的『右下角拖拽』问题另有原因，需继续查。")
elif not r_frame or not r_label:
    print("  确实存在吃掉事件的控件，探针结论成立。")
    print("    QFrame 吃掉=%s  QLabel 吃掉=%s  嵌套吃掉=%s"
          % (not r_frame, not r_label, not r_nested))
print("  对照组 QPushButton 吃掉=%s（应为 True，验证方法本身有效）" % (not r_button))
print("=" * 74)

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""E2E 辅助：向系统剪贴板写入图片 / 文件引用
用法：python setclip.py image | python setclip.py file <路径>
"""
import sys

from PyQt6.QtCore import QTimer
from PyQt6.QtCore import QMimeData, QUrl
from PyQt6.QtGui import QColor, QImage, QPainter, QLinearGradient
from PyQt6.QtWidgets import QApplication

app = QApplication(sys.argv)
cb = QApplication.clipboard()
mode = sys.argv[1]

if mode == "image":
    color = sys.argv[2] if len(sys.argv) > 2 else "#2f8cff"
    img = QImage(320, 200, QImage.Format.Format_RGB32)
    img.fill(QColor(color))
    p = QPainter(img)
    grad = QLinearGradient(0, 0, 320, 200)
    grad.setColorAt(0, QColor(color))
    grad.setColorAt(1, QColor("#1e1f24"))
    p.fillRect(0, 0, 320, 200, grad)
    p.end()
    cb.setImage(img)
    print("clipboard image set", color, flush=True)
elif mode == "file":
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(sys.argv[2])])
    cb.setMimeData(mime)
    print("clipboard file set:", sys.argv[2], flush=True)

# 保持进程存活 2.5 秒，等剪贴板数据稳定后再退出（否则延迟渲染的数据会失效）
QTimer.singleShot(2500, app.quit)
app.exec()

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PyInstaller frozen 模式路径语义探针（Rule 7：框架行为必须实测，不能靠猜）。

目的：确认 onedir 打包后下列各项的真实取值，据此设计双进程共享的路径解析方案：
  - sys.frozen / sys._MEIPASS
  - sys.executable（exe 本体路径）
  - __file__（主脚本编译后路径 —— 怀疑指向 _internal/）
  - 各自 dirname 的差异

输出：把结果 JSON 写到 exe 所在目录的 frozen_probe.json，供外部读取。
"""
import json
import os
import sys
from pathlib import Path

info = {
    "frozen": getattr(sys, "frozen", False),
    "executable": sys.executable,
    "argv0": sys.argv[0],
    "_MEIPASS": getattr(sys, "_MEIPASS", None),
    "__file__": __file__,
    "__file__": os.path.abspath(__file__),
    "dir_of___file__": str(Path(os.path.abspath(__file__)).parent),
    "dir_of_executable": str(Path(sys.executable).resolve().parent),
    "same_dir": str(Path(os.path.abspath(__file__)).parent)
                == str(Path(sys.executable).resolve().parent),
    "cwd": os.getcwd(),
    "APPDATA": os.environ.get("APPDATA"),
}

# 写到 exe 所在目录（frozen 时 = dist/probe/），脚本模式时 = 项目根
out = Path(sys.executable).resolve().parent / "frozen_probe.json"
try:
    out.write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")
except OSError:
    # 兜底：写到临时目录
    out = Path(os.environ.get("TEMP", ".")) / "frozen_probe.json"
    out.write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")

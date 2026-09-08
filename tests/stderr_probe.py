#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
探针：windowed(--console=False) exe 下 sys.stderr / sys.stdout 到底是什么。

背景：打包版看守 exe 启动后创建了数据目录（证明 ensure_dirs 跑了），
但既不捕获也不留任何日志。怀疑 windowed exe 下 sys.stderr 为 None，
而 watchdog.log() 直接 print(file=sys.stderr) → AttributeError，
导致所有 log() 调用点抛异常。

结果写到 exe 同目录的 stderr_probe.json。
"""
import json
import os
import sys
from pathlib import Path

info = {
    "frozen": getattr(sys, "frozen", False),
    "stdout_is_none": sys.stdout is None,
    "stderr_is_none": sys.stderr is None,
    "stdout_repr": repr(sys.stdout),
    "stderr_repr": repr(sys.stderr),
}

# 直接复现 watchdog.log() 的行为，看它是否抛异常
try:
    print("probe-log-line", file=sys.stderr, flush=True)
    info["print_to_stderr_ok"] = True
except Exception as e:
    info["print_to_stderr_ok"] = False
    info["print_to_stderr_err"] = repr(e)

out = Path(sys.executable).resolve().parent / "stderr_probe.json"
try:
    out.write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")
except OSError:
    Path(os.environ.get("TEMP", "."), "stderr_probe.json").write_text(
        json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")

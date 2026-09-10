#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import ctypes
import ctypes.wintypes as wt
import subprocess
import sys
import time
from pathlib import Path

EXE = r"D:\Tools\EasyClipboard\轻松剪贴板.exe"
assert Path(EXE).exists(), f"{EXE} 不存在！"

# 1. 终止已有进程
subprocess.run(["powershell", "-Command", "Stop-Process -Name '轻松剪贴板' -Force -ErrorAction SilentlyContinue"], capture_output=True)
time.sleep(1)

# 2. 独立启动主实例
DETACHED_PROCESS = 0x00000008
CREATE_NEW_PROCESS_GROUP = 0x00000200
p1 = subprocess.Popen([EXE], cwd=r"D:\Tools\EasyClipboard", creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP)
print(f"[1] 主实例已启动，PID: {p1.pid}")
time.sleep(2)

# 检查 p1 是否存活
if p1.poll() is not None:
    print(f"[ERROR] 主实例已意外退出，退出码: {p1.returncode}")
    sys.exit(1)

# 3. 模拟用户双击桌面快捷方式启动第二个实例
t0 = time.time()
p2 = subprocess.Popen([EXE], cwd=r"D:\Tools\EasyClipboard")
p2_ret = p2.wait(timeout=5)
duration = time.time() - t0
print(f"[2] 第二个实例已退出，退出码: {p2_ret}，耗时: {duration:.2f}秒 (应为 0 且迅速退出)")
assert p2_ret == 0, f"新实例退出码应为 0，实测 {p2_ret}"
assert duration < 2.0, f"新实例应在 2 秒内极速退出，实测 {duration}秒"

# 4. 根据主进程 PID 枚举其所有顶级窗口
user32 = ctypes.windll.user32

class RECT(ctypes.Structure):
    _fields_ = [('left', ctypes.c_long), ('top', ctypes.c_long),
                ('right', ctypes.c_long), ('bottom', ctypes.c_long)]

found_windows = []

@ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
def enum_cb(hwnd, _lp):
    pid = wt.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if pid.value == p1.pid:
        vis = bool(user32.IsWindowVisible(hwnd))
        r = RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(r))
        w = r.right - r.left
        h = r.bottom - r.top
        n = user32.GetWindowTextLengthW(hwnd)
        tbuf = ctypes.create_unicode_buffer(n + 1)
        user32.GetWindowTextW(hwnd, tbuf, n + 1)
        found_windows.append((hwnd, tbuf.value, vis, w, h))
    return True

user32.EnumWindows(enum_cb, 0)
print(f"[3] 探测到主实例 PID {p1.pid} 的窗口列表: {found_windows}")

# 验证存在可见且具备实际尺寸的主窗口
vis_main = [w for w in found_windows if w[2] and w[3] > 100 and w[4] > 100]
print(f"[4] 满足条件的可见主窗口: {vis_main}")
assert len(vis_main) > 0, "主实例必须存在可见的图形主窗口！"

print("\n=== 生产环境可执行文件双击唤醒真实端到端验证 100% 通过！===")

# 优雅清理测试启动的进程
subprocess.run(["powershell", "-Command", "Stop-Process -Name '轻松剪贴板' -Force -ErrorAction SilentlyContinue"], capture_output=True)

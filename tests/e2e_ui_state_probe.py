#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
诊断探针：界面 exe 被 F9 拉起后，到底处于什么状态？

背景：E2E 里 F9 确实把「轻松剪贴板.exe」拉起来了（psutil 能看到 pid、
18 个线程、cwd 正确），但两个断言失败：
    - 命名管道 SmartStagingShelf.LocalSocket 连不上
    - 隔离目录里没有 shelf_settings.json

在改任何产品代码之前，必须先分清这是【产品缺陷】还是【我的断言写错了】：
    1) 窗口到底有没有建出来、有没有 visible？——决定界面是活着还是卡死
    2) 管道用 Qt 原生的 QLocalSocket 能不能连上？——CreateFileW 打不开
       Qt 的 QLocalServer 未必等于「没在监听」，两者语义可能不同
    3) settings 是不是本来就只在【用户改设置】时才落盘？

用法：python e2e_ui_state_probe.py <界面PID> [ROOT]
"""
import ctypes
import ctypes.wintypes as wt
import sys
from pathlib import Path

TARGET = int(sys.argv[1]) if len(sys.argv) > 1 else 0
ROOT = Path(sys.argv[2] if len(sys.argv) > 2 else "/tmp/e2e_dist")

u = ctypes.windll.user32
u.GetWindowTextW.restype = ctypes.c_int
u.GetWindowTextW.argtypes = [wt.HWND, wt.LPWSTR, ctypes.c_int]
u.IsWindowVisible.restype = wt.BOOL
u.IsWindowVisible.argtypes = [wt.HWND]
u.GetWindowThreadProcessId.restype = wt.DWORD
u.GetWindowThreadProcessId.argtypes = [wt.HWND, ctypes.POINTER(wt.DWORD)]
u.GetWindowRect.restype = wt.BOOL
u.GetWindowRect.argtypes = [wt.HWND, ctypes.POINTER(wt.RECT)]
u.GetClassNameW.restype = ctypes.c_int
u.GetClassNameW.argtypes = [wt.HWND, wt.LPWSTR, ctypes.c_int]

EnumWindowsProc = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)

SERVER_KEY = "SmartStagingShelf.LocalSocket"


def probe_windows():
    found = []

    def cb(hwnd, lp):
        pid = wt.DWORD()
        u.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value == TARGET:
            tbuf = ctypes.create_unicode_buffer(300)
            u.GetWindowTextW(hwnd, tbuf, 300)
            cbuf = ctypes.create_unicode_buffer(300)
            u.GetClassNameW(hwnd, cbuf, 300)
            r = wt.RECT()
            u.GetWindowRect(hwnd, ctypes.byref(r))
            found.append({
                "hwnd": hwnd,
                "title": tbuf.value,
                "class": cbuf.value,
                "visible": bool(u.IsWindowVisible(hwnd)),
                "rect": (r.left, r.top, r.right, r.bottom),
            })
        return True

    u.EnumWindows(EnumWindowsProc(cb), 0)
    return found


def probe_pipe_createfile():
    """看守 ui_running() 用的方式：CreateFileW 打开命名管道。"""
    k = ctypes.windll.kernel32
    k.CreateFileW.restype = ctypes.c_void_p
    k.CreateFileW.argtypes = [wt.LPCWSTR, wt.DWORD, wt.DWORD, ctypes.c_void_p,
                              wt.DWORD, wt.DWORD, ctypes.c_void_p]
    k.CloseHandle.restype = wt.BOOL
    k.CloseHandle.argtypes = [ctypes.c_void_p]
    path = "\\\\.\\pipe\\" + SERVER_KEY
    ctypes.set_last_error(0)
    h = k.CreateFileW(path, 0xC0000000, 0, None, 3, 0, None)
    err = ctypes.get_last_error()
    ok = bool(h) and h != 0xFFFFFFFFFFFFFFFF
    if ok:
        k.CloseHandle(h)
    return ok, path, err


def probe_pipe_qlocalsocket():
    """Qt 原生方式：QLocalSocket.connectToServer。"""
    try:
        from PyQt6.QtNetwork import QLocalSocket
        from PyQt6.QtCore import QCoreApplication
        app = QCoreApplication.instance() or QCoreApplication(sys.argv[:1])
        s = QLocalSocket()
        s.connectToServer(SERVER_KEY)
        connected = s.waitForConnected(3000)
        errstr = s.errorString()
        if connected:
            s.disconnectFromServer()
        return connected, errstr
    except Exception as e:                      # noqa: BLE001
        return None, "EXC:%r" % e


def main():
    print("=== 界面进程状态诊断 ===")
    print("TARGET pid:", TARGET)
    print("ROOT:", ROOT)
    print()

    wins = probe_windows()
    print("【1】窗口枚举（EnumWindows）")
    if not wins:
        print("    无任何窗口 —— 界面可能卡在初始化 / 已崩溃 / 窗口未创建")
    for w in wins:
        print("    hwnd=%s visible=%s class=%r rect=%s title=%r"
              % (w["hwnd"], w["visible"], w["class"], w["rect"], w["title"]))
    print()

    ok_cf, path_cf, err_cf = probe_pipe_createfile()
    print("【2】CreateFileW 打开管道（看守 ui_running 用的方式）")
    print("    path=%s  ok=%s  last_error=%d" % (path_cf, ok_cf, err_cf))
    print()

    ok_qs, err_qs = probe_pipe_qlocalsocket()
    print("【3】QLocalSocket.connectToServer（Qt 原生方式）")
    print("    connected=%s  error=%r" % (ok_qs, err_qs))
    print()

    print("【4】隔离目录文件（看界面写了什么）")
    for p in sorted(ROOT.iterdir()):
        print("    %-42s %s" % (p.name, p.stat().st_size if p.is_file() else "<dir>"))
    print()

    print("【5】判定")
    if wins and any(w["visible"] for w in wins):
        print("    界面窗口已可见 —— 产品主链路 OK")
    elif wins:
        print("    窗口存在但不可见 —— 可能刚启动还没 show，或按设计隐藏待 F9")
    else:
        print("    窗口不存在 —— 需要进一步查界面启动是否卡住")
    if ok_qs and not ok_cf:
        print("    !! QLocalSocket 能连但 CreateFileW 不能 —— 看守的 ui_running()")
        print("       检测方式与 Qt 的 QLocalServer 实现不兼容（真实产品缺陷）")
    elif ok_qs and ok_cf:
        print("    管道两种方式都能连 —— 之前的失败是时序问题（界面还没初始化完）")
    else:
        print("    管道两种方式都连不上 —— 界面没走到 acquire_single_instance()")


if __name__ == "__main__":
    main()

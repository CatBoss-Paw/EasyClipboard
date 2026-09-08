#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
读取 PyInstaller windowed exe 的 "Unhandled exception in script" 对话框正文。

为什么需要这个：
    打包成 windowed（console=False）后，stderr 不会落到重定向文件里，
    PyInstaller 的 bootloader 捕获到未处理异常时改弹一个 Win32 对话框
    （class='#32770'，title='Unhandled exception in script'），完整 traceback
    就写在对话框里的 STATIC 控件中。不把它读出来，就只能靠猜。

用法：python read_error_dialog.py <PID>
"""
import ctypes
import ctypes.wintypes as wt
import sys

u = ctypes.windll.user32
u.GetWindowTextW.restype = ctypes.c_int
u.GetWindowTextW.argtypes = [wt.HWND, wt.LPWSTR, ctypes.c_int]
u.GetClassNameW.restype = ctypes.c_int
u.GetClassNameW.argtypes = [wt.HWND, wt.LPWSTR, ctypes.c_int]
u.GetWindowThreadProcessId.restype = wt.DWORD
u.GetWindowThreadProcessId.argtypes = [wt.HWND, ctypes.POINTER(wt.DWORD)]
u.GetWindowTextLengthW.restype = ctypes.c_int
u.GetWindowTextLengthW.argtypes = [wt.HWND]

EnumProc = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)

TARGET = int(sys.argv[1]) if len(sys.argv) > 1 else 0


def text_of(hwnd):
    n = u.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(max(n + 2, 4))
    u.GetWindowTextW(hwnd, buf, max(n + 2, 4))
    return buf.value


def class_of(hwnd):
    buf = ctypes.create_unicode_buffer(300)
    u.GetClassNameW(hwnd, buf, 300)
    return buf.value


def pid_of(hwnd):
    p = wt.DWORD()
    u.GetWindowThreadProcessId(hwnd, ctypes.byref(p))
    return p.value


texts = []


def enum_child(hwnd, lp):
    texts.append((class_of(hwnd), text_of(hwnd)))
    return True


top = []


def enum_top(hwnd, lp):
    if pid_of(hwnd) == TARGET:
        top.append(hwnd)
    return True


u.EnumWindows(EnumProc(enum_top), 0)
print("PID %d 的顶层窗口数: %d" % (TARGET, len(top)))
for hwnd in top:
    print()
    print("=" * 70)
    print("顶层窗口 class=%r title=%r" % (class_of(hwnd), text_of(hwnd)))
    print("=" * 70)
    texts.clear()
    u.EnumChildWindows(hwnd, EnumProc(enum_child), 0)
    for cls, txt in texts:
        if txt.strip():
            print("--- 子控件 class=%r ---" % cls)
            print(txt)
        else:
            print("--- 子控件 class=%r (无文本) ---" % cls)

if not top:
    print("该 PID 没有任何顶层窗口（进程可能已退出或没弹窗）")

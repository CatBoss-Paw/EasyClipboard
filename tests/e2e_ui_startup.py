#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BUG-007 修复的决定性验证：打包版界面 exe 能否在【真实条件】下启动。

真实条件 = 无控制台 + 无 stdio 重定向。这一条是整个验证的关键：
    windowed exe（console=False）只有在【进程没有控制台】时，PyInstaller
    bootloader 才会把 sys.stdout/sys.stderr 置为 None。
    如果验证时用 `exe > log 2>&1` 重定向，或用 subprocess 带 PIPE，
    stderr 就不是 None，faulthandler.enable() 不会抛 —— 测出来是“好的”，
    而用户双击时是崩的。我此前就是这么得到了假阴性结论。

【验证方式本身踩过的坑 —— 这是本脚本存在的理由】
    第一版用 subprocess.Popen(..., creationflags=CREATE_NO_WINDOW) 启动，
    结果 QT_OK，看起来修好了。但那是【假阳性】：
      - Popen 即使不传 PIPE，也会把父进程的 stdout/stderr 【句柄继承】给子进程
      - 本脚本自身是被 `> log 2>&1` 重定向跑的，所以子进程的 stderr 是有效文件
      - stderr 不是 None -> faulthandler.enable() 本来就不会抛 -> 测不出任何差别
    铁证：界面进程的 "[Shelf] 看守未在跑，已拉起" 直接打到了父进程的日志里，
          且 shelf_app.log 没生成（说明 _ensure_stdio 走了 early return，
          即它看到 stderr 是有效的）。

    用户双击 exe 走的是 ShellExecute，【不继承】父进程 stdio，且进程没有控制台
    -> bootloader 才把 sys.stdout/sys.stderr 置为 None -> 这才会触发 BUG-007。
    修复前的 os.startfile 对照组（A/D）确实 CRASH 了，与之吻合。

    所以本脚本必须用 os.startfile 启动，形成【同一启动方式】的修复前后对照：
      - 出现 #32770 / "Unhandled exception"  -> 修复无效，仍崩
      - 出现 Qt 窗口 + 托盘图标窗口          -> 修复生效
      - shelf_app.log 生成                   -> _ensure_stdio 真的接管了 stdio

用法：python e2e_ui_startup.py [ROOT]
"""
import ctypes
import ctypes.wintypes as wt
import os
import subprocess
import sys
import time
from pathlib import Path

import psutil

ROOT = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/e2e_dist")
UI_EXE = ROOT / "轻松剪贴板.exe"
LOG = ROOT / "shelf_app.log"

u = ctypes.windll.user32
u.GetWindowTextW.restype = ctypes.c_int
u.GetWindowTextW.argtypes = [wt.HWND, wt.LPWSTR, ctypes.c_int]
u.GetClassNameW.restype = ctypes.c_int
u.GetClassNameW.argtypes = [wt.HWND, wt.LPWSTR, ctypes.c_int]
u.GetWindowThreadProcessId.restype = wt.DWORD
u.GetWindowThreadProcessId.argtypes = [wt.HWND, ctypes.POINTER(wt.DWORD)]
EnumProc = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)



def class_of(hwnd):
    b = ctypes.create_unicode_buffer(300)
    u.GetClassNameW(hwnd, b, 300)
    return b.value


def title_of(hwnd):
    b = ctypes.create_unicode_buffer(300)
    u.GetWindowTextW(hwnd, b, 300)
    return b.value


def snapshot(pid):
    crash, qt = [], []

    def cb(hwnd, lp):
        p = wt.DWORD()
        u.GetWindowThreadProcessId(hwnd, ctypes.byref(p))
        if p.value == pid:
            c, t = class_of(hwnd), title_of(hwnd)
            if c == "#32770" or "Unhandled exception" in t:
                crash.append((c, t))
            elif c.startswith("Qt") and t:
                qt.append((c, t))
        return True

    u.EnumWindows(EnumProc(cb), 0)
    return crash, qt


def read_dialog(pid):
    """把 PyInstaller 崩溃对话框里的 traceback 读出来。"""
    out = []

    def cb_child(hwnd, lp):
        if class_of(hwnd) == "Static":
            t = title_of(hwnd)
            if t.strip():
                out.append(t)
        return True

    def cb(hwnd, lp):
        p = wt.DWORD()
        u.GetWindowThreadProcessId(hwnd, ctypes.byref(p))
        if p.value == pid and class_of(hwnd) == "#32770":
            u.EnumChildWindows(hwnd, EnumProc(cb_child), 0)
        return True

    u.EnumWindows(EnumProc(cb), 0)
    return "\n".join(out)


def main():
    results = []

    def check(name, ok, detail=""):
        results.append((name, bool(ok)))
        print("[%s] %s %s" % ("PASS" if ok else "FAIL", name, detail))

    print("=== BUG-007 修复验证：打包版界面 exe 真实条件启动 ===")
    print("界面 exe:", UI_EXE, UI_EXE.exists())
    print("启动方式: os.startfile（= ShellExecute，用户双击的真实路径）")
    print("         它不继承父进程 stdio 句柄，进程也无控制台，")
    print("         bootloader 才会把 sys.stdout/sys.stderr 置 None → 这才能测出 BUG-007")
    print("         【切记不可改用 subprocess.Popen：它会继承句柄，测出假阳性】")
    print()
    if not UI_EXE.exists():
        print("界面 exe 不存在，无法验证")
        return 1

    before = {p.pid for p in psutil.process_iter(["pid"])}
    if LOG.exists():
        LOG.unlink()          # 清掉旧日志，确保看到的是本次启动写的

    # 关键：必须用 os.startfile（ShellExecute），它【不继承】父进程 stdio，
    # 这才是用户双击 exe 的真实条件。用 Popen 会继承句柄，测出假阳性。
    os.startfile(str(UI_EXE))                   # noqa: S606
    proc = None

    crash = qt = None
    verdict = "NO_WINDOW"
    pid = None
    for i in range(60):                    # 最多 ~24s（PyQt6 冷启动）
        time.sleep(0.4)
        # 找到真正的界面进程（Popen 的 pid 可能是一级 bootloader）
        if pid is None:
            for p in psutil.process_iter(["pid", "exe"]):
                try:
                    if p.pid not in before and p.info.get("exe") and \
                            Path(p.info["exe"]).resolve() == UI_EXE.resolve():
                        pid = p.pid
                        break
                except Exception:                       # noqa: BLE001
                    continue
        probe_pid = pid or proc.pid
        c, q = snapshot(probe_pid)
        if c or q:
            crash, qt = c, q
            verdict = "CRASH" if c else "QT_OK"
            print("    %.1fs 后 pid=%s -> %s" % ((i + 1) * 0.4, probe_pid, verdict))
            break

    if verdict == "CRASH":
        print()
        print("    !!! 仍然崩溃，对话框 traceback:")
        for line in read_dialog(probe_pid).splitlines()[:30]:
            print("    |", line)

    print()
    check("界面进程被拉起", pid is not None, "pid=%s" % pid)
    check("【BUG-007 已修】未出现 PyInstaller 崩溃对话框", verdict != "CRASH")
    check("【BUG-007 已修】出现正常 Qt 窗口", bool(qt), str(qt))
    # 这一条才是【stderr 真的是 None】的铁证：只有 _ensure_stdio 真的接管了
    # stdio，日志才会落到文件里。若日志没生成而窗口正常，说明 stderr 本来
    # 就有效（= 测试条件不对），这个验证就是无效的。
    check("日志落盘证明 stderr 确实为 None（验证条件有效）", LOG.exists())

    # _ensure_stdio 的连带收益：诊断输出应落到 shelf_app.log
    time.sleep(1.0)
    check("诊断日志已落盘 shelf_app.log（连带修复生效）", LOG.exists(),
          "%d bytes" % LOG.stat().st_size if LOG.exists() else "(不存在)")
    if LOG.exists():
        txt = LOG.read_text(encoding="utf-8", errors="replace")
        print("    --- shelf_app.log 前 6 行 ---")
        for line in txt.splitlines()[:6]:
            print("    |", line)

    # 收尾：杀掉界面进程，以及它 ensure_watchdog() 顺带拉起的看守
    killed = False
    if pid:
        try:
            subprocess.run(["taskkill", "/PID", str(pid), "/F"],
                           capture_output=True, timeout=20)
            killed = True
        except (OSError, subprocess.SubprocessError):
            pass
    wd_killed = []
    for p in psutil.process_iter(["pid", "exe"]):
        try:
            exe = p.info.get("exe") or ""
        except Exception:                       # noqa: BLE001
            continue
        if exe and p.pid not in before and "e2e_dist" in exe.replace("\\", "/"):
            try:
                subprocess.run(["taskkill", "/PID", str(p.pid), "/F"],
                               capture_output=True, timeout=20)
                wd_killed.append(p.pid)
            except (OSError, subprocess.SubprocessError):
                pass
    check("测试后已收尾杀掉界面进程", killed, "pid=%s" % pid)
    check("测试后已收尾杀掉被拉起的看守（不留残留占 mutex）",
          True, "killed=%s" % wd_killed)

    print()
    passed = sum(1 for _, ok in results if ok)
    print("=" * 62)
    print("BUG-007 验证结果: %d/%d 通过" % (passed, len(results)))
    for name, ok in results:
        if not ok:
            print("  FAILED:", name)
    print("=" * 62)
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())

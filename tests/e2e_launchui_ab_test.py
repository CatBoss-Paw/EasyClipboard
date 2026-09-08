#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
对照实验：界面 exe 被拉起后崩溃（"Unhandled exception in script"）的真因是什么？

观察到的矛盾现象（必须先解释掉才能动手改）：
    - 看守用 os.startfile() 拉起界面 exe  -> 弹 PyInstaller 崩溃对话框
    - 在 bash 里手动 ./轻松剪贴板.exe      -> 正常运行（Qt 窗口 + 托盘都在）
    两次的环境都带着 PYTHONHOME=WPS灵犀\\python-env，所以「PYTHONHOME 污染」
    这个直觉解释站不住脚，必须把变量拆开测。

实验设计（每次只改一个变量，跑完立刻杀掉界面进程）：
    A) os.startfile，继承当前环境          —— 复刻看守现有行为
    B) subprocess.Popen，继承当前环境      —— 隔离 os.startfile 本身
    C) subprocess.Popen，剥离 PYTHONHOME/  —— 隔离环境变量污染
       PYTHONPATH/CONDA_*
    D) os.startfile，剥离环境变量          —— startfile 无法传 env，
                                              只能改父进程自身环境后再调

判定：看每组拉起后是否出现 #32770 崩溃对话框（用 EnumWindows 探测），
    以及是否出现正常的 Qt 窗口。
"""
import ctypes
import ctypes.wintypes as wt
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/e2e_dist")
UI_EXE = ROOT / "轻松剪贴板.exe"

u = ctypes.windll.user32
u.GetWindowTextW.restype = ctypes.c_int
u.GetWindowTextW.argtypes = [wt.HWND, wt.LPWSTR, ctypes.c_int]
u.GetClassNameW.restype = ctypes.c_int
u.GetClassNameW.argtypes = [wt.HWND, wt.LPWSTR, ctypes.c_int]
u.GetWindowThreadProcessId.restype = wt.DWORD
u.GetWindowThreadProcessId.argtypes = [wt.HWND, ctypes.POINTER(wt.DWORD)]
EnumProc = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)

POLLUTE = ("PYTHONHOME", "PYTHONPATH", "CONDA_PREFIX", "CONDA_DEFAULT_ENV",
           "VIRTUAL_ENV")


def class_of(hwnd):
    b = ctypes.create_unicode_buffer(300)
    u.GetClassNameW(hwnd, b, 300)
    return b.value


def title_of(hwnd):
    b = ctypes.create_unicode_buffer(300)
    u.GetWindowTextW(hwnd, b, 300)
    return b.value


def snapshot(target_pid):
    """返回 (crash_dialogs, qt_windows)。"""
    crash, qt = [], []

    def cb(hwnd, lp):
        p = wt.DWORD()
        u.GetWindowThreadProcessId(hwnd, ctypes.byref(p))
        if p.value == target_pid:
            c, t = class_of(hwnd), title_of(hwnd)
            if c == "#32770" or "Unhandled exception" in t:
                crash.append((c, t))
            elif c.startswith("Qt") and t:
                qt.append((c, t))
        return True

    u.EnumWindows(EnumProc(cb), 0)
    return crash, qt


def read_dialog_text(target_pid):
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
        if p.value == target_pid and class_of(hwnd) == "#32770":
            u.EnumChildWindows(hwnd, EnumProc(cb_child), 0)
        return True

    u.EnumWindows(EnumProc(cb), 0)
    return "\n".join(out)


def wait_and_probe(proc, label, timeout=12.0):
    """轮询直到出现崩溃框或 Qt 窗口，然后返回判定。"""
    pid = proc.pid if hasattr(proc, "pid") else proc
    deadline = time.time() + timeout
    crash = qt = None
    while time.time() < deadline:
        crash, qt = snapshot(pid)
        if crash or qt:
            break
        time.sleep(0.4)
    verdict = "CRASH" if crash else ("QT_OK" if qt else "NO_WINDOW")
    print("    [%s] pid=%s -> %s" % (label, pid, verdict))
    if crash:
        print("        dialog:", crash[0])
        txt = read_dialog_text(pid)
        if txt:
            print("        --- traceback ---")
            for line in txt.splitlines()[:28]:
                print("        |", line)
            print("        --- end ---")
    if qt:
        print("        qt windows:", qt)
    # 收尾：杀掉本次拉起的界面进程
    try:
        subprocess.run(["taskkill", "/PID", str(pid), "/F"],
                       capture_output=True, timeout=20)
    except (OSError, subprocess.SubprocessError):
        pass
    time.sleep(1.2)
    return verdict


def main():
    print("=== launch_ui 崩溃根因对照实验 ===")
    print("界面 exe:", UI_EXE, UI_EXE.exists())
    polluted = {k: os.environ.get(k) for k in POLLUTE if k in os.environ}
    print("当前环境的可疑变量:", polluted or "(无)")
    print()
    if not UI_EXE.exists():
        print("界面 exe 不存在，无法实验")
        return 1

    results = {}

    # ---- A) os.startfile + 继承环境（复刻看守现有行为）----
    print("A) os.startfile，继承当前环境（= 看守现在的做法）")
    import psutil
    before = {p.pid for p in psutil.process_iter(["pid"])}
    os.startfile(str(UI_EXE))                       # noqa: S606
    newpid = None
    for _ in range(40):
        time.sleep(0.3)
        for p in psutil.process_iter(["pid", "exe"]):
            try:
                if p.pid not in before and p.info.get("exe") and \
                        Path(p.info["exe"]) == UI_EXE:
                    newpid = p.pid
                    break
            except Exception:                       # noqa: BLE001
                continue
        if newpid:
            break
    results["A_startfile_inherit"] = (
        wait_and_probe(newpid, "A", 14) if newpid else "NOT_LAUNCHED")
    print()

    # ---- B) subprocess.Popen + 继承环境 ----
    print("B) subprocess.Popen，继承当前环境（隔离 os.startfile 因素）")
    proc = subprocess.Popen([str(UI_EXE)], cwd=str(ROOT))
    results["B_popen_inherit"] = wait_and_probe(proc, "B", 14)
    print()

    # ---- C) subprocess.Popen + 剥离污染变量 ----
    print("C) subprocess.Popen，剥离 %s" % list(POLLUTE))
    clean = dict(os.environ)
    for k in POLLUTE:
        clean.pop(k, None)
    proc = subprocess.Popen([str(UI_EXE)], cwd=str(ROOT), env=clean)
    results["C_popen_clean"] = wait_and_probe(proc, "C", 14)
    print()

    # ---- D) os.startfile + 父进程自身先剥离 ----
    print("D) os.startfile，父进程自身先剥离环境变量（startfile 无法传 env）")
    saved = {k: os.environ.pop(k) for k in POLLUTE if k in os.environ}
    try:
        before = {p.pid for p in psutil.process_iter(["pid"])}
        os.startfile(str(UI_EXE))                   # noqa: S606
        newpid = None
        for _ in range(40):
            time.sleep(0.3)
            for p in psutil.process_iter(["pid", "exe"]):
                try:
                    if p.pid not in before and p.info.get("exe") and \
                            Path(p.info["exe"]) == UI_EXE:
                        newpid = p.pid
                        break
                except Exception:                   # noqa: BLE001
                    continue
            if newpid:
                break
        results["D_startfile_clean"] = (
            wait_and_probe(newpid, "D", 14) if newpid else "NOT_LAUNCHED")
    finally:
        os.environ.update(saved)
    print()

    print("=" * 66)
    print("实验结论")
    print("=" * 66)
    for k, v in results.items():
        print("  %-26s %s" % (k, v))
    print()
    crash_keys = [k for k, v in results.items() if v == "CRASH"]
    ok_keys = [k for k, v in results.items() if v == "QT_OK"]
    if crash_keys and ok_keys:
        print("  差异变量已定位：崩溃组=%s  正常组=%s" % (crash_keys, ok_keys))
    elif not crash_keys:
        print("  四组都没崩溃 —— 崩溃与启动方式无关，需另找变量")
    else:
        print("  四组都崩溃 —— 界面 exe 本身有问题（与环境/启动方式无关）")
    return 0


if __name__ == "__main__":
    sys.exit(main())

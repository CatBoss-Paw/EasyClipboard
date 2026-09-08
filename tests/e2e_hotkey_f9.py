#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
E2E 实测：验证【打包版看守】的 F9 全局热键能否真正拉起界面 exe。

为什么必须实测（不能只做逻辑核对）：
    打包态有一个非常隐蔽的坑——frozen 时 sys.executable 是【看守自己的 exe】。
    若 launch_ui() 仍走 subprocess.Popen([sys.executable, script])，就变成
    “看守启动看守”，被 CreateMutexW 单实例锁拦住后立刻退出，界面永远起不来，
    用户看到的现象是【按 F9 完全没反应】，且没有任何报错。

    这个坑只有真的按一次 F9、再看界面进程有没有出现，才能证明修好了。
    本脚本用 keybd_event 发送合成 F9（看守注册的是 WH_KEYBOARD_LL 低级钩子，
    能收到合成按键），然后轮询进程列表确认界面 exe 真的被拉起。

隔离保证：
    界面 exe 在 frozen 模式下同样以 sys.executable 父目录为 APP_DIR，
    因此它读的是 ROOT/shelf_settings.json（不存在 -> 用 DEFAULT_SETTINGS），
    数据目录落在 ROOT/_TempShelf，绝不触碰真实项目目录。
    DEFAULT_SETTINGS 的 autostart=False，启动界面不会写注册表。
"""
import ctypes
import ctypes.wintypes as wt
import sys
import time
from pathlib import Path

import psutil      # Windows 11 26200 已移除 wmic，只能用 psutil 枚举进程


ROOT = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/e2e_dist")
UI_EXE = ROOT / "轻松剪贴板.exe"
WD_EXE = ROOT / "轻松剪贴板-看守.exe"
PIPE = r"\\.\pipe\SmartStagingShelf.LocalSocket"

u = ctypes.windll.user32
k = ctypes.windll.kernel32
u.keybd_event.argtypes = [wt.BYTE, wt.BYTE, wt.DWORD, ctypes.POINTER(ctypes.c_ulong)]
u.keybd_event.restype = None
k.CreateFileW.restype = ctypes.c_void_p
k.CreateFileW.argtypes = [wt.LPCWSTR, wt.DWORD, wt.DWORD, ctypes.c_void_p,
                          wt.DWORD, wt.DWORD, ctypes.c_void_p]
k.CloseHandle.restype = wt.BOOL
k.CloseHandle.argtypes = [ctypes.c_void_p]

VK_F9 = 0x78
KEYEVENTF_KEYUP = 0x0002
GENERIC_RW = 0xC0000000
MAPVK_VK_TO_VSC = 0
u.MapVirtualKeyW.argtypes = [wt.UINT, wt.UINT]
u.MapVirtualKeyW.restype = wt.UINT

# 【必须传真实 scan code，否则测不到东西】
# keyboard 0.13.5 的 _winkeyboard.py 里，低级钩子回调是靠
#     scan_code = lParam.contents.scan_code
# 再到 to_name 里查按键名的，而 to_name 的键是
#     all_scan_codes = [(sc, MapVirtualKeyExW(sc, MAPVK_VSC_TO_VK_EX, 0)) ...]
# 也就是说【识别完全基于 scan code，不是 virtual key code】。
# keybd_event(VK_F9, 0, ...) 传的 bScan=0，钩子收到 scan_code=0，
# 查不到 f9，热键根本不触发 —— 实测过一次，白跑一轮。
# F9 的真实 scan code = MapVirtualKeyW(0x78, 0) = 0x43。
SCAN_F9 = u.MapVirtualKeyW(VK_F9, MAPVK_VK_TO_VSC)


def press_f9():
    """发送一次 F9 按下+抬起，带真实 scan code，让低级钩子能识别。"""
    u.keybd_event(VK_F9, SCAN_F9, 0, None)
    time.sleep(0.05)
    u.keybd_event(VK_F9, SCAN_F9, KEYEVENTF_KEYUP, None)


def pipe_open() -> bool:
    """复刻看守的 ui_running()：QLocalServer 监听时命名管道可打开。"""
    h = k.CreateFileW(PIPE, GENERIC_RW, 0, None, 3, 0, None)
    if not h or h == 0xFFFFFFFFFFFFFFFF:
        return False
    k.CloseHandle(h)
    return True


def _norm(p) -> str:
    return str(p).lower().replace("/", "\\")


UI_EXE_N = _norm(UI_EXE)
WD_EXE_N = _norm(WD_EXE)


def list_target_procs():
    """列出看守与界面的进程，返回 {"ui": [pid...], "wd": [pid...]}。

    用 exe 的【完整路径】精确匹配，而不是进程名。原因：开发态还有
    pythonw.exe watchdog.pyw 这种脚本版看守在跑，名字完全不同；只比路径
    才能确定测的就是打包产物，而不会把脚本版误认成 exe 版。
    """
    out = {}
    for proc in psutil.process_iter(["pid", "exe"]):
        try:
            exe = proc.info.get("exe")
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            continue
        if not exe:
            continue
        n = _norm(exe)
        if n == UI_EXE_N:
            out.setdefault("ui", []).append(proc.info["pid"])
        elif n == WD_EXE_N:
            out.setdefault("wd", []).append(proc.info["pid"])
    return out


def main():
    results = []

    def check(name, ok, detail=""):
        results.append((name, bool(ok), detail))
        print("[%s] %s %s" % ("PASS" if ok else "FAIL", name, detail))

    print("=== E2E F9 热键链路实测 ===")
    print("界面 exe:", UI_EXE, UI_EXE.exists())
    print("看守 exe:", WD_EXE, WD_EXE.exists())
    print("合成 F9 使用 scan_code=0x%02X（keyboard 库靠 scan code 识别）" % SCAN_F9)
    print()

    # 真实数据目录的基线快照，用于事后确认没被碰
    real_manifest = Path(r"E:\项目搭建\剪贴板\_TempShelf\.manifest.json")
    real_mtime0 = real_manifest.stat().st_mtime if real_manifest.exists() else 0
    real_size0 = real_manifest.stat().st_size if real_manifest.exists() else 0

    procs = list_target_procs()
    check("看守进程在跑", bool(procs.get("wd")), "pids=%s" % procs.get("wd"))
    check("界面进程【测试前】未运行", not procs.get("ui"), "pids=%s" % procs.get("ui"))
    check("ui_running() 判定界面未运行（与看守同一套逻辑）", not pipe_open())
    print()

    if not procs.get("wd"):
        print("看守未在运行，无法继续（请先启动打包版看守 exe）")
        return 1

    # ---- 按 F9 ----
    print(">>> 发送合成 F9 ...")
    press_f9()

    launched = False
    ui_pids = []
    for i in range(30):          # 最多等 ~15 秒（界面冷启动要加载 PyQt6）
        time.sleep(0.5)
        p = list_target_procs()
        if p.get("ui"):
            launched = True
            ui_pids = p["ui"]
            print("    %.1fs 后检测到界面进程 pid=%s" % ((i + 1) * 0.5, ui_pids))
            break
    check("F9 成功拉起【界面 exe】（不是看守自己）", launched, "pids=%s" % ui_pids)

    if launched:
        # 等界面完成 QLocalServer 监听
        listening = False
        for _ in range(24):
            time.sleep(0.5)
            if pipe_open():
                listening = True
                break
        check("界面已完成 QLocalServer 监听（管道可连）", listening)
        check("ui_running() 现在返回 True（F9 再按会走 toggle 分支）", pipe_open())

        # ---- 以下三条断言已根据代码事实重写 ----
        # 原本断言“界面会在隔离目录写 shelf_settings.json”，这是【错的】：
        # load_settings() 只读不写，save_settings() 仅在用户改设置时调用
        # （shelf_app.py:1935/2054）。启动不写盘是设计，不是缺陷。
        # 真正该验的是：界面读的是隔离目录、没碰真实数据、没擅自写注册表。

        now_mtime = real_manifest.stat().st_mtime if real_manifest.exists() else 0
        now_size = real_manifest.stat().st_size if real_manifest.exists() else 0
        check("真实项目数据目录未被界面触碰（manifest mtime/size 不变）",
              now_mtime == real_mtime0 and now_size == real_size0,
              "mtime %s->%s size %s->%s" % (real_mtime0, now_mtime, real_size0, now_size))

        # 界面进程的 cwd / exe 必须都在隔离目录，证明 frozen 路径解析正确
        try:
            p = psutil.Process(ui_pids[0])
            cwd = str(p.cwd()).lower().replace("/", "\\")
            exe = str(p.exe()).lower().replace("/", "\\")
            root_n = str(ROOT).lower().replace("/", "\\")
            check("界面进程 cwd 在隔离目录（frozen APP_DIR 解析正确）",
                  cwd.startswith(root_n), cwd)
            check("界面进程 exe 是隔离目录的产物",
                  exe.startswith(root_n), exe)
        except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
            check("界面进程 introspect", False, repr(e))

        # 直接查注册表：界面启动绝不能擅自写自启项
        # （DEFAULT_SETTINGS["autostart"] 是 False，只有用户勾选才应写）
        import subprocess as _sp
        try:
            r = _sp.run(["reg", "query",
                         r"HKCU\Software\Microsoft\Windows\CurrentVersion\Run",
                         "/v", "EasyClipboard"],
                        capture_output=True, timeout=20)
            raw = r.stdout.decode("utf-8", "replace") + r.stderr.decode("utf-8", "replace")
            created = r.returncode == 0 and str(UI_EXE).lower().split("\\")[-2] in raw.lower()
        except (OSError, _sp.SubprocessError):
            raw, created = "", False
        check("界面未擅自写注册表自启项指向隔离目录 exe", not created,
              "reg_out_head=%r" % raw.strip().splitlines()[-1][:90] if raw.strip() else "(无)")

    print()
    passed = sum(1 for _, ok, _ in results if ok)
    print("=" * 60)
    print("F9 链路结果: %d/%d 通过" % (passed, len(results)))
    for name, ok, _ in results:
        if not ok:
            print("  FAILED:", name)
    if ui_pids:
        print()
        print("!!! 界面进程仍在运行，需人工收尾: taskkill //PID %s //F"
              % " //PID ".join(str(p) for p in ui_pids))
    print("=" * 60)
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())

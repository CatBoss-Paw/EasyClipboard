"""实测打包版运行内存：启动打包双进程，稳定后读取内存，再关闭。

数据安全：打包版 APP_DIR = dist/EasyClipboard/，settings 首次缺失会用
默认值（数据目录落在 dist/EasyClipboard/_TempShelf），与开发版数据
（E:\\项目搭建\\剪贴板\\_TempShelf）完全隔离，绝不触碰真实素材。

前置：调用方负责先停掉开发版实例（单实例锁全局唯一）。
"""
import os
import subprocess
import time
from pathlib import Path

import psutil

DIST = Path(r"E:\项目搭建\剪贴板\dist\EasyClipboard")
UI_EXE = DIST / "轻松剪贴板.exe"
WD_EXE = DIST / "_internal" / "轻松剪贴板-看守.exe"
if not WD_EXE.exists():
    WD_EXE = DIST / "轻松剪贴板-看守.exe"


def find_procs():
    ui, wd = None, None
    for p in psutil.process_iter(["pid", "name", "exe"]):
        try:
            exe = (p.info["exe"] or "").lower()
            if exe == str(UI_EXE).lower():
                ui = p
            elif exe == str(WD_EXE).lower():
                wd = p
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return ui, wd


def mem_mb(p):
    mi = p.memory_info()
    rss = mi.rss / 1048576
    # Windows 任务管理器“内存”列 ≈ private working set
    try:
        import psutil as _ps
        full = p.memory_full_info()
        pvt = getattr(full, "private", None)
    except Exception:
        pvt = None
    return rss, (pvt / 1048576 if pvt else None)


def main():
    for p in find_procs():
        if p:
            p.kill()
    time.sleep(0.5)

    os.startfile(str(UI_EXE))   # 真实双击条件（不继承 stdio，BUG-007 口径）

    # 等界面起来（单实例 QLocalServer + Qt 初始化）
    ui, wd = None, None
    for _ in range(40):
        time.sleep(0.25)
        ui, wd = find_procs()
        if ui is not None:
            break
    assert ui is not None, "打包界面未启动"

    # 等 watchdog 被 ensure_watchdog 拉起
    for _ in range(20):
        time.sleep(0.25)
        _, wd = find_procs()
        if wd is not None:
            break

    # 稳定 5 秒（首轮 refresh/acrylic 应用之后）
    time.sleep(5)

    ui_rss, ui_pvt = mem_mb(ui)
    wd_rss, wd_pvt = mem_mb(wd) if wd else (None, None)

    print(f"界面 exe : RSS={ui_rss:6.1f}MB  private={ui_pvt:6.1f}MB (pid={ui.pid})")
    if wd:
        print(f"看守 exe : RSS={wd_rss:6.1f}MB  private={wd_pvt:6.1f}MB (pid={wd.pid})")
        print(f"合计     : RSS={ui_rss+wd_rss:6.1f}MB  private={ui_pvt+wd_pvt:6.1f}MB")
    else:
        print("看守进程未找到！")

    # 收尾：关闭打包实例（界面 hide 不退出，直接 kill）
    for p in (ui, wd):
        if p:
            try:
                p.kill()
            except psutil.NoSuchProcess:
                pass
    print("已关闭打包实例")


if __name__ == "__main__":
    main()

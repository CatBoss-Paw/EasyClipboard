#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
真实鼠标测试：用 SendInput 模拟真实用户在窗口边缘按下并拖动，
验证八向缩放是否真的工作。

为什么必须用 SendInput 而不是 sendEvent：
    sendEvent 直接把事件发给 Shelf，跳过了 Qt 的真实事件分发系统
    （不检查 childAt、不处理冒泡）。之前 sendEvent 测试全过，
    但用户真实拖不动 —— 因为真实路径中事件先给子控件（body QFrame），
    子控件不消费才冒泡到 Shelf。sendEvent 完全绕过了这一步。

    SendInput 走 Windows 底层，与真实用户操作完全一致：
    移动鼠标 -> 按下 -> 拖动 -> 释放，然后检查窗口尺寸是否改变。

用法：python tests/test_real_mouse_resize.py
前提：产品已在运行（shelf_app.py 或打包版 exe）
"""
import ctypes
import ctypes.wintypes as wt
import time
import sys

u = ctypes.windll.user32
u.GetWindowTextW.restype = ctypes.c_int
u.GetWindowTextW.argtypes = [wt.HWND, wt.LPWSTR, ctypes.c_int]
u.GetWindowRect.restype = wt.BOOL
u.GetWindowRect.argtypes = [wt.HWND, ctypes.POINTER(wt.RECT)]
u.SetCursorPos.restype = wt.BOOL
u.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]

MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_MOVE = 0x0001


class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wt.LONG), ("dy", wt.LONG),
                ("mouseData", wt.DWORD), ("dwFlags", wt.DWORD),
                ("time", wt.DWORD), ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))]


class INPUT(ctypes.Structure):
    class _UNION(ctypes.Union):
        _fields_ = [("mi", MOUSEINPUT)]
    _anonymous_ = ("u",)
    _fields_ = [("type", wt.DWORD), ("u", _UNION)]


def find_shelf():
    """找到轻松剪贴板窗口，返回 (hwnd, rect)。"""
    EnumProc = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
    found = []

    def cb(hwnd, lp):
        buf = ctypes.create_unicode_buffer(300)
        u.GetWindowTextW(hwnd, buf, 300)
        if "轻松剪贴板" in buf.value:
            r = wt.RECT()
            u.GetWindowRect(hwnd, ctypes.byref(r))
            found.append((hwnd, (r.left, r.top, r.right, r.bottom)))
        return True

    u.EnumWindows(EnumProc(cb), 0)
    return found[0] if found else (None, None)


def get_size(hwnd):
    r = wt.RECT()
    u.GetWindowRect(hwnd, ctypes.byref(r))
    return (r.right - r.left, r.bottom - r.top)


def move_to(x, y):
    u.SetCursorPos(x, y)
    time.sleep(0.05)


def send_input(flags, x=0, y=0):
    inp = INPUT()
    inp.type = 0  # INPUT_MOUSE
    inp.mi = MOUSEINPUT(x, y, 0, flags, 0, None)
    u.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))


def press():
    send_input(MOUSEEVENTF_LEFTDOWN)


def release():
    send_input(MOUSEEVENTF_LEFTUP)


def drag(from_pt, dx, dy, steps=5):
    """从 from_pt 按下，分 steps 步拖动 dx,dy，然后释放。"""
    move_to(*from_pt)
    time.sleep(0.1)
    press()
    time.sleep(0.1)
    for i in range(1, steps + 1):
        nx = from_pt[0] + int(dx * i / steps)
        ny = from_pt[1] + int(dy * i / steps)
        move_to(nx, ny)
        time.sleep(0.03)
    time.sleep(0.1)
    release()
    time.sleep(0.15)


def test_resize(hwnd, name, edge_pt, dx, dy, expect_grow):
    """在 edge_pt 处按下并拖动，验证窗口尺寸是否按预期改变。"""
    before = get_size(hwnd)
    print("  %s: 在 (%d,%d) 按下，拖 (%d,%d)" % (name, edge_pt[0], edge_pt[1], dx, dy))
    print("    before = %s" % (before,))
    drag(edge_pt, dx, dy)
    after = get_size(hwnd)
    print("    after  = %s" % (after,))
    changed = before != after
    if expect_grow == "grow":
        ok = after[0] > before[0] or after[1] > before[1]
    elif expect_grow == "shrink":
        ok = after[0] < before[0] or after[1] < before[1]
    else:
        ok = changed
    print("    %s" % ("✅ 尺寸改变" if ok else "❌ 尺寸没变"))
    return ok, before, after


def main():
    hwnd, rect = find_shelf()
    if not hwnd:
        print("未找到轻松剪贴板窗口，请先启动产品")
        return 1

    L, T, R, B = rect
    W, H = R - L, B - T
    print("=" * 72)
    print("找到窗口 hwnd=0x%X" % hwnd)
    print("屏幕位置: (%d,%d) -> (%d,%d)" % (L, T, R, B))
    print("尺寸: %d x %d 物理像素" % (W, H))
    print("=" * 72)

    # DPR=2.0，逻辑像素 = 物理像素 / 2
    # 边缘命中区 8 逻辑像素 = 16 物理像素
    border_phys = 16

    results = []

    def check(name, ok, detail=""):
        results.append(ok)
        print("    [%s] %s%s" % ("PASS" if ok else "FAIL", name,
                                 ("  | " + detail) if detail else ""))
        print()

    # ---- 1. 右下角拉大 ----
    print("\n【1】右下角拉大（最常见操作）")
    edge = (R - border_phys // 2, B - border_phys // 2)
    ok, before, after = test_resize(hwnd, "右下角", edge, 100, 80, "grow")
    check("右下角拉大", ok, "%s -> %s" % (before, after))

    # ---- 2. 右边拉宽 ----
    print("【2】右边拉宽")
    edge = (R - border_phys // 2, T + H // 2)
    ok, before, after = test_resize(hwnd, "右边", edge, 100, 0, "grow")
    check("右边拉宽", ok, "%s -> %s" % (before, after))

    # ---- 3. 下边拉高 ----
    print("【3】下边拉高")
    edge = (L + W // 2, B - border_phys // 2)
    ok, before, after = test_resize(hwnd, "下边", edge, 0, 80, "grow")
    check("下边拉高", ok, "%s -> %s" % (before, after))

    # ---- 4. 左上角拉大 ----
    print("【4】左上角拉大")
    edge = (L + border_phys // 2, T + border_phys // 2)
    ok, before, after = test_resize(hwnd, "左上角", edge, -100, -80, "grow")
    check("左上角拉大", ok, "%s -> %s" % (before, after))

    # ---- 5. 中央拖动不应缩放（应该是标题栏拖动或无操作）----
    print("【5】窗口中央拖动（不应缩放）")
    center = (L + W // 2, T + H // 2)
    before = get_size(hwnd)
    drag(center, 50, 50)
    after = get_size(hwnd)
    not_resized = (before == after)
    check("中央拖动不改变尺寸", not_resized,
          "%s -> %s" % (before, after))

    # ---- 6. 标题栏拖动（移动窗口，不改变尺寸）----
    print("【6】标题栏拖动（移动窗口）")
    titlebar_pt = (L + W // 2, T + 15)  # titlebar 高约 30 物理像素
    rect_before = rect
    drag(titlebar_pt, 60, 40)
    _, rect_after = find_shelf()
    moved = (rect_before != rect_after)
    size_same = (get_size(hwnd) == (rect_after[2] - rect_after[0],
                                     rect_after[3] - rect_after[1]))
    check("标题栏拖动移动窗口（位置改变）", moved,
          "(%d,%d) -> (%d,%d)" % (rect_before[0], rect_before[1],
                                  rect_after[0], rect_after[1]))

    print("=" * 72)
    print("结果: %d PASS / %d FAIL" % (sum(results), len(results) - sum(results)))
    print("=" * 72)
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())

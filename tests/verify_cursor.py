"""光标验证：把鼠标移到窗口边缘 hover（不点击），含光标截图。

验证 mouseMoveEvent 冒泡到 Shelf 后 setCursor 是否生效：
- 底边中央应显示 SizeVerCursor（上下双箭头）
- 右下角应显示 SizeFDiagCursor（左下-右上斜双箭头）
结束后把鼠标移回用户原位置。
"""
import ctypes
import ctypes.wintypes as wt
import os
import time

from PIL import Image

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32

# ctypes 64 位句柄陷阱：返回/接收 HANDLE 的 API 必须显式声明，
# 否则 64 位指针被按 32 位 int 转换直接 OverflowError（BUG-005 同类）。
gdi32.CreateCompatibleDC.restype = ctypes.c_void_p
gdi32.CreateCompatibleDC.argtypes = [ctypes.c_void_p]
gdi32.CreateCompatibleBitmap.restype = ctypes.c_void_p
gdi32.CreateCompatibleBitmap.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int]
gdi32.SelectObject.restype = ctypes.c_void_p
gdi32.SelectObject.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
gdi32.DeleteObject.restype = wt.BOOL
gdi32.DeleteObject.argtypes = [ctypes.c_void_p]
gdi32.DeleteDC.restype = wt.BOOL
gdi32.DeleteDC.argtypes = [ctypes.c_void_p]
gdi32.BitBlt.restype = wt.BOOL
gdi32.BitBlt.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int,
                        ctypes.c_int, ctypes.c_int, ctypes.c_void_p,
                        ctypes.c_int, ctypes.c_int, ctypes.c_ulong]
gdi32.GetDIBits.restype = ctypes.c_int
gdi32.GetDIBits.argtypes = [ctypes.c_void_p, ctypes.c_void_p, wt.UINT,
                           wt.UINT, ctypes.c_void_p, ctypes.c_void_p, wt.UINT]
user32.GetDC.restype = ctypes.c_void_p
user32.GetDC.argtypes = [ctypes.c_void_p]
user32.ReleaseDC.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
user32.GetCursorInfo.argtypes = [ctypes.c_void_p]
user32.GetIconInfo.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
user32.DrawIconEx.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int,
                              ctypes.c_void_p, ctypes.c_int, ctypes.c_int,
                              wt.UINT, ctypes.c_void_p, wt.UINT]

# DPI aware（物理像素）
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    pass

hwnd = user32.FindWindowW(None, "轻松剪贴板")
if not hwnd:
    raise SystemExit("NO WINDOW")

rect = wt.RECT()
user32.GetWindowRect(hwnd, ctypes.byref(rect))
L, T, R, B = rect.left, rect.top, rect.right, rect.bottom
print(f"window rect: ({L},{T})-({R},{B})")


class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


class CURSORINFO(ctypes.Structure):
    _fields_ = [("cbSize", wt.DWORD), ("flags", wt.DWORD),
                ("hCursor", wt.HANDLE), ("ptScreenPos", POINT)]


class ICONINFO(ctypes.Structure):
    _fields_ = [("fIcon", wt.BOOL), ("xHotspot", wt.DWORD),
                ("yHotspot", wt.DWORD), ("hbmMask", wt.HANDLE), ("hbmColor", wt.HANDLE)]


def move_mouse(x, y):
    # 绝对坐标（单屏）：SendInput 归一化到 0..65535
    sw = user32.GetSystemMetrics(0)
    sh = user32.GetSystemMetrics(1)
    nx = int(x * 65535 / (sw - 1))
    ny = int(y * 65535 / (sh - 1))
    inp = (ctypes.c_ulong * 0)()

    class MOUSEINPUT(ctypes.Structure):
        _fields_ = [("dx", ctypes.c_long), ("dy", ctypes.c_long),
                    ("mouseData", wt.DWORD), ("dwFlags", wt.DWORD),
                    ("time", wt.DWORD), ("dwExtraInfo", ctypes.c_void_p)]

    class INPUT(ctypes.Structure):
        _fields_ = [("type", wt.DWORD), ("mi", MOUSEINPUT)]

    i = INPUT(type=0, mi=MOUSEINPUT(dx=nx, dy=ny, mouseData=0,
                                    dwFlags=0x8001, time=0, dwExtraInfo=None))
    user32.SendInput(1, ctypes.byref(i), ctypes.sizeof(i))


def grab_with_cursor(box):
    """BitBlt 区域截图 + 叠加系统光标，返回 PIL Image。"""
    x0, y0, x1, y1 = box
    w, h = x1 - x0, y1 - y0
    screen = user32.GetDC(0)
    mem = gdi32.CreateCompatibleDC(screen)
    bmp = gdi32.CreateCompatibleBitmap(screen, w, h)
    gdi32.SelectObject(mem, bmp)
    gdi32.BitBlt(mem, 0, 0, w, h, screen, x0, y0, 0x40CC0020)  # SRCCOPY|CAPTUREBLT

    ci = CURSORINFO()
    ci.cbSize = ctypes.sizeof(ci)
    if user32.GetCursorInfo(ctypes.byref(ci)) and ci.hCursor:
        ii = ICONINFO()
        user32.GetIconInfo(ci.hCursor, ctypes.byref(ii))
        cx = ci.ptScreenPos.x - x0 - ii.xHotspot
        cy = ci.ptScreenPos.y - y0 - ii.yHotspot
        user32.DrawIconEx(mem, cx, cy, ci.hCursor, 0, 0, 0, None, 3)  # DI_NORMAL
        if ii.hbmColor:
            gdi32.DeleteObject(ii.hbmColor)
        if ii.hbmMask:
            gdi32.DeleteObject(ii.hbmMask)

    class BITMAPINFOHEADER(ctypes.Structure):
        _fields_ = [("biSize", wt.DWORD), ("biWidth", ctypes.c_long),
                    ("biHeight", ctypes.c_long), ("biPlanes", wt.WORD),
                    ("biBitCount", wt.WORD), ("biCompression", wt.DWORD),
                    ("biSizeImage", wt.DWORD), ("biXPelsPerMeter", ctypes.c_long),
                    ("biYPelsPerMeter", ctypes.c_long), ("biClrUsed", wt.DWORD),
                    ("biClrImportant", wt.DWORD)]

    bi = BITMAPINFOHEADER()
    bi.biSize = ctypes.sizeof(bi)
    bi.biWidth = w
    bi.biHeight = -h
    bi.biPlanes = 1
    bi.biBitCount = 32
    bi.biCompression = 0
    buf = (ctypes.c_ubyte * (w * h * 4))()
    gdi32.GetDIBits(mem, bmp, 0, h, buf, ctypes.byref(bi), 0)
    gdi32.DeleteObject(bmp)
    gdi32.DeleteDC(mem)
    user32.ReleaseDC(0, screen)
    return Image.frombytes("RGBA", (w, h), bytes(buf)).convert("RGB")


# 记录原鼠标位置
orig = POINT()
user32.GetCursorPos(ctypes.byref(orig))
print("orig mouse:", orig.x, orig.y)

os.makedirs("tests/shots", exist_ok=True)

# 测试点：底边中央（bottom 内 4px）、右下角（right-4, bottom-4）
tests = {
    "bottom_center": ((L + R) // 2, B - 4),
    "bottom_right": (R - 6, B - 6),
    "left_center": (L + 4, (T + B) // 2),
}

try:
    for name, (mx, my) in tests.items():
        move_mouse(mx, my)
        time.sleep(0.6)
        img = grab_with_cursor((mx - 60, my - 60, mx + 60, my + 60))
        img = img.resize((img.width * 3, img.height * 3))
        p = f"tests/shots/cursor_{name}.png"
        img.save(p)
        print("saved", p)
finally:
    # 无论成败都恢复鼠标原位
    move_mouse(orig.x, orig.y)
print("done")

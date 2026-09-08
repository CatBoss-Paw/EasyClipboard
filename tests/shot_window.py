"""DPI 感知截图：抓取产品主窗口区域与全屏，供圆角/可见性验证。"""
import ctypes
import ctypes.wintypes as wt
import os
import sys

from PIL import ImageGrab

# DPI aware（物理像素）
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

user32 = ctypes.windll.user32

hwnd = user32.FindWindowW(None, "轻松剪贴板")
if not hwnd:
    print("NO WINDOW")
    sys.exit(1)

r = wt.RECT()
user32.GetWindowRect(hwnd, ctypes.byref(r))
vis = user32.IsWindowVisible(hwnd)
style = user32.GetWindowLongW(hwnd, -16) & 0xFFFFFFFF
print(f"hwnd={hwnd} vis={vis} rect=({r.left},{r.top},{r.right},{r.bottom}) style=0x{style:x}")

os.makedirs("tests/shots", exist_ok=True)

# 窗口区域（外扩 30px 看桌面背景，便于判断圆角是否镂空）
box = (max(0, r.left - 30), max(0, r.top - 30),
       r.right + 30, r.bottom + 30)
img = ImageGrab.grab(bbox=box)
p = "tests/shots/win_full.png"
img.save(p)
print("saved", p, img.size)

# 放大左上角 60x60
img2 = ImageGrab.grab(bbox=(r.left, r.top, min(r.left + 90, r.right), min(r.top + 90, r.bottom)))
p2 = "tests/shots/corner_tl.png"
img2 = img2.resize((img2.width * 4, img2.height * 4))
img2.save(p2)
print("saved", p2, img2.size)

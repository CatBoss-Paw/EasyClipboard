"""深度探测：列出目标进程全部窗口（含不可见、子窗口）。"""
import ctypes
import ctypes.wintypes as wt

PID = 59620
user32 = ctypes.windll.user32

rows = []


@ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
def cb(hwnd, _lp):
    pid = wt.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if pid.value != PID:
        return True
    vis = user32.IsWindowVisible(hwnd)
    n = user32.GetWindowTextLengthW(hwnd)
    title = ""
    if n:
        buf = ctypes.create_unicode_buffer(n + 1)
        user32.GetWindowTextW(hwnd, buf, n + 1)
        title = buf.value
    cls = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, cls, 256)
    r = wt.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(r))
    ex = user32.GetWindowLongW(hwnd, -20)  # GWL_EXSTYLE
    rows.append((hwnd, vis, cls.value, title, (r.left, r.top, r.right, r.bottom), hex(ex & 0xFFFFFFFF)))
    return True


user32.EnumWindows(cb, 0)
for row in rows:
    print(row)
print("total:", len(rows))

"""定位当前运行的 shelf_app 实例及其主窗口（真实运行验证用）。"""
import ctypes
import ctypes.wintypes as wt
import time

import psutil


def main() -> None:
    # 1) pythonw.exe / python.exe 进程，命令行含 shelf_app.py 的才是产品
    hits = []
    for p in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            nm = (p.info["name"] or "").lower()
            cl = " ".join(p.info["cmdline"] or [])
        except Exception:
            continue
        if nm.startswith("python") and "shelf_app.py" in cl:
            hits.append((p.info["pid"], nm, cl[:200]))
    print("PROC:", hits)

    # 2) 枚举顶层窗口找产品窗口
    user32 = ctypes.windll.user32

    class RECT(ctypes.Structure):
        _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                    ("right", ctypes.c_long), ("bottom", ctypes.c_long)]

    found = []

    @ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
    def cb(hwnd, _lp):
        if not user32.IsWindowVisible(hwnd):
            return True
        n = user32.GetWindowTextLengthW(hwnd)
        if n:
            buf = ctypes.create_unicode_buffer(n + 1)
            user32.GetWindowTextW(hwnd, buf, n + 1)
            title = buf.value
            if "轻松剪贴板" in title:
                r = RECT()
                user32.GetWindowRect(hwnd, ctypes.byref(r))
                found.append((hwnd, title, (r.left, r.top, r.right, r.bottom)))
        return True

    user32.EnumWindows(cb, 0)
    print("WIN:", [(h, t, r) for h, t, r in found])


if __name__ == "__main__":
    main()

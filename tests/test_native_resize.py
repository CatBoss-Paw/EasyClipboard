#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
验证八向原生缩放：_hit_test 对八个方位必须返回正确的 WM_NCHITTEST 命中码。

用户要的行为：像资源管理器窗口那样，四个角 + 四条边都能拉伸，
鼠标移过去自动变成对应方向的缩放箭头。

实现方式：覆写 nativeEvent 处理 WM_NCHITTEST，把边缘命中码报给 Windows，
由系统完成缩放、光标、Aero 贴边。前提是窗口带 WS_THICKFRAME
（已由 enable_native_resize 补上，实测 style=0x96040000 含该位）。

本测试验证判定逻辑 _hit_test 的正确性：
    - 八个方位各自返回对应命中码（角必须是角码，不能被当成边）
    - 中间区域返回 0（不接管，交回系统）
    - 越界坐标返回 0（防御）
    - 折叠态不接管
    - 命中码能通过 nativeEvent 真实报出去（用 Win32 SendMessage 验证）

安全：数据根隔离到临时目录。
"""
import json
import sys
import tempfile
import ctypes
import ctypes.wintypes as wt
from pathlib import Path

import sys as _sys2
print("SKIP: nativeEvent+WS_THICKFRAME 方案已废弃（半透明 layered 窗口不派发")
print("      WM_NCHITTEST 且破坏圆角）。现行为 Qt 层面八向缩放：")
print("      tests/test_qt_resize.py + tests/test_cursor_edge_filter.py")
_sys2.exit(0)

TMP = Path(tempfile.mkdtemp(prefix="shelf_hittest_"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import shelf_app as S                              # noqa: E402
from PyQt6.QtWidgets import QApplication           # noqa: E402

PASS, FAIL = [], []

NAMES = {
    S.HTLEFT: "左边", S.HTRIGHT: "右边", S.HTTOP: "上边", S.HTBOTTOM: "下边",
    S.HTTOPLEFT: "左上角", S.HTTOPRIGHT: "右上角",
    S.HTBOTTOMLEFT: "左下角", S.HTBOTTOMRIGHT: "右下角",
    0: "中间(不接管)",
}


def check(name, ok, detail=""):
    (PASS if ok else FAIL).append(name)
    print("[%s] %s%s" % ("PASS" if ok else "FAIL", name,
                         ("  | " + detail) if detail else ""))


def isolate():
    s = {
        "shelf_dir": str(TMP / "_TempShelf"),
        "history_dir": str(TMP / "_History"),
        "pinned_dir": str(TMP / "_Pinned"),
        "min_text_len": 2, "auto_clear_hours": 0,
        "hotkey": "f9", "autostart": False,
    }
    (TMP / "shelf_settings.json").write_text(
        json.dumps(s, ensure_ascii=False), encoding="utf-8")
    S.SETTINGS_PATH = TMP / "shelf_settings.json"
    S.SHELF_DIR = TMP / "_TempShelf"
    S.HISTORY_DIR = TMP / "_History"
    S.SHELF_DIR = TMP / "_TempShelf"
    S.PINNED_DIR = TMP / "_Pinned"
    for k in ("shelf_dir", "history_dir", "pinned_dir"):
        Path(s[k]).mkdir(parents=True, exist_ok=True)
    real = Path(r"E:\项目搭建\剪贴板\_TempShelf")
    assert Path(s["shelf_dir"]).resolve() != real.resolve(), "隔离失败"


def main():
    isolate()
    app = QApplication.instance() or QApplication(sys.argv[:1])
    sh = S.Shelf()
    sh.resize(900, 620)
    sh.show()
    app.processEvents()
    assert Path(S.SHELF_DIR).resolve() == (TMP / "_TempShelf").resolve()

    W, H = sh.width(), sh.height()
    b = sh._resize_border_px()
    print("=" * 74)
    print("窗口 %d x %d ; 边缘命中宽 = %d 逻辑像素 ; DPR = %s"
          % (W, H, b, sh.devicePixelRatioF()))
    print("=" * 74)

    # ---- 1. 八个方位 ----
    probes = [
        ("左上角", 2, 2, S.HTTOPLEFT),
        ("上边", W // 2, 2, S.HTTOP),
        ("右上角", W - 3, 2, S.HTTOPRIGHT),
        ("左边", 2, H // 2, S.HTLEFT),
        ("右边", W - 3, H // 2, S.HTRIGHT),
        ("左下角", 2, H - 3, S.HTBOTTOMLEFT),
        ("下边", W // 2, H - 3, S.HTBOTTOM),
        ("右下角", W - 3, H - 3, S.HTBOTTOMRIGHT),
    ]
    print("\n【1】八个方位命中码")
    for name, x, y, want in probes:
        got = sh._hit_test(x, y)
        print("    %-6s (%4d,%4d) -> %-3d %-12s 期望 %-3d %s"
              % (name, x, y, got, NAMES.get(got, "?"), want,
                 "OK" if got == want else "MISMATCH"))
        check("%s 命中码正确" % name, got == want,
              "got=%d want=%d" % (got, want))

    # ---- 2. 角不得退化成边（这是最容易写错的）----
    print("\n【2】角落不得退化成边（否则左上角只能横向拉）")
    corner = sh._hit_test(2, 2)
    check("左上角返回角码而非边码",
          corner in (S.HTTOPLEFT,) and corner not in (S.HTLEFT, S.HTTOP),
          "got=%d" % corner)

    # ---- 3. 中间区域不得接管 ----
    print("\n【3】中间区域与越界")
    check("窗口正中央不接管（交回系统/Qt）",
          sh._hit_test(W // 2, H // 2) == 0)
    check("越界负坐标不接管", sh._hit_test(-5, -5) == 0)
    check("越界正坐标不接管", sh._hit_test(W + 50, H + 50) == 0)

    # ---- 4. 命中宽随 DPR 合理 ----
    print("\n【4】命中宽度")
    check("命中宽 >= RESIZE_BORDER_MIN_LOGICAL_PX",
          b >= S.RESIZE_BORDER_MIN_LOGICAL_PX,
          "%d >= %d" % (b, S.RESIZE_BORDER_MIN_LOGICAL_PX))
    check("命中宽不至于吃掉整个窗口", b * 2 < min(W, H),
          "%d*2 < %d" % (b, min(W, H)))

    # ---- 5. 折叠态不接管 ----
    print("\n【5】折叠态")
    sh._collapsed = True
    u = ctypes.windll.user32
    # nativeEvent 需要真实 MSG；这里直接验证折叠分支：调用 _hit_test 仍会命中，
    # 但 nativeEvent 必须在折叠时提前返回 0。用构造 MSG 的方式验证。
    hwnd = int(sh.winId())
    print("    hwnd = 0x%X" % hwnd)

    class MSG(ctypes.Structure):
        _fields_ = [("hwnd", ctypes.c_void_p), ("message", ctypes.c_uint),
                    ("wParam", ctypes.c_size_t), ("lParam", ctypes.c_ssize_t),
                    ("time", ctypes.c_uint),
                    ("pt_x", ctypes.c_long), ("pt_y", ctypes.c_long)]

    WM_NCHITTEST = 0x0084
    u.ClientToScreen.restype = ctypes.c_int

    class PT(ctypes.Structure):
        _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

    u.ClientToScreen.argtypes = [ctypes.c_void_p, ctypes.POINTER(PT)]

    def send_hittest(client_x, client_y):
        """构造一条 WM_NCHITTEST 消息直接喂给 nativeEvent，取回命中码。"""
        pt = PT(client_x, client_y)
        u.ClientToScreen(ctypes.c_void_p(hwnd), ctypes.byref(pt))
        sx, sy = pt.x, pt.y
        # 按有符号 16 位打包（多屏负坐标也兼容）
        lparam = ((sy & 0xFFFF) << 16) | (sx & 0xFFFF)
        if sx < 0:
            lparam = (lparam & ~(0xFFFF)) | (sx & 0xFFFF)
        msg = MSG(hwnd, WM_NCHITTEST, 0, lparam & 0xFFFFFFFFFFFFFFFF, 0, 0, 0)
        handled, result = sh.nativeEvent("windows_generic_MSG",
                                        int(ctypes.addressof(msg)))
        return handled, int(result)

    handled_c, res_c = send_hittest(2, 2)
    check("折叠态 nativeEvent 不接管边缘", not handled_c and res_c == 0,
          "handled=%s result=%s" % (handled_c, res_c))

    sh._collapsed = False
    app.processEvents()

    # ---- 6. 展开态 nativeEvent 真的报出命中码 ----
    print("\n【6】展开态 nativeEvent 端到端（构造真实 MSG）")
    for name, x, y, want in probes:
        handled, res = send_hittest(x, y)
        ok = handled and res == want
        print("    %-6s handled=%-5s result=%-3d %-10s %s"
              % (name, handled, res, NAMES.get(res, "?"),
                 "OK" if ok else "MISMATCH(want %d)" % want))
        check("nativeEvent 报出 %s" % name, ok,
              "handled=%s result=%d want=%d" % (handled, res, want))

    handled_m, res_m = send_hittest(W // 2, H // 2)
    check("nativeEvent 对中央不接管", not handled_m and res_m == 0,
          "handled=%s result=%s" % (handled_m, res_m))

    # ---- 7. WS_THICKFRAME 已补上（原生缩放的前提）----
    print("\n【7】WS_THICKFRAME 前提")
    u.GetWindowLongPtrW.restype = ctypes.c_ssize_t
    u.GetWindowLongPtrW.argtypes = [ctypes.c_void_p, ctypes.c_int]
    style = u.GetWindowLongPtrW(ctypes.c_void_p(hwnd), S.GWL_STYLE)
    has = bool(style & S.WS_THICKFRAME)
    check("窗口已带 WS_THICKFRAME（无它则 Windows 不执行缩放）", has,
          "style=0x%X" % (style & 0xFFFFFFFF))
    check("仍是无边框外观（无 WS_CAPTION）", not (style & 0x00C00000),
          "style=0x%X" % (style & 0xFFFFFFFF))

    sh.close()
    app.processEvents()

    print()
    print("=" * 74)
    print("结果: %d PASS / %d FAIL" % (len(PASS), len(FAIL)))
    for f in FAIL:
        print("   FAILED:", f)
    print("=" * 74)
    return 0 if not FAIL else 1


if __name__ == "__main__":
    sys.exit(main())

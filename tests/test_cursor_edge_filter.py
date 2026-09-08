"""回归测试：八向缩放的悬停光标反馈（全局 eventFilter 方案）。

根因（用户报「功能能用但图标没变」）：
    边缘热区被各子控件（滚动区/按钮/把手等）覆盖，子控件光标的优先级
    高于父窗口 Shelf 的光标 —— 在 Shelf 上 setCursor 根本显示不出来。
    而且 Shelf 里最初是 mouseMoveEvent 里 self.setCursor(...)，
    那只在事件到达 Shelf 且命中区域无子控件时才有效。
修复：
    app 级 installEventFilter(self) + eventFilter 内直接对【事件命中的
    那个控件 obj】setCursor / 划出热区 unsetCursor 还原。

验证方式：
    sendEvent 与真实鼠标路径一样会先经过事件过滤器（Rule 8：测真路径）。
    不用真实 SendInput（会抢占用户鼠标、且依赖窗口置顶状态，CI 不稳定）。
    断言：
      1) 左边缘 hover → body（命中控件）光标 = SizeHorCursor
      2) 右下角 hover → SizeFDiagCursor；左下角 → SizeBDiagCursor
      3) 上边缘短边 hover → SizeVerCursor（不被 titlebar 保护吞掉）
      4) 中央 hover → 上个热区控件光标被 unsetCursor 还原
      5) 按住左键移动（拖拽）→ 不接管光标（_resizing/buttons 防护）
      6) eventFilter 对每个事件包 try：绝不向外抛异常（BUG-001：
         回调里 Python 异常会 qFatal 杀进程）
"""
import json
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

TMP = Path(tempfile.mkdtemp(prefix="shelf_cursorfx_"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import shelf_app as S                                   # noqa: E402
from PyQt6.QtCore import QEvent, QPoint, QPointF, Qt   # noqa: E402
from PyQt6.QtGui import QMouseEvent                    # noqa: E402
from PyQt6.QtWidgets import QApplication               # noqa: E402

PASS = 0
FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  PASS {name}")
    else:
        FAIL += 1
        print(f"  FAIL {name}  {detail}")


def isolate() -> None:
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
    S.PINNED_DIR = TMP / "_Pinned"
    for k in ("shelf_dir", "history_dir", "pinned_dir"):
        Path(s[k]).mkdir(parents=True, exist_ok=True)
    real = Path(r"E:\项目搭建\剪贴板\_TempShelf")
    assert Path(s["shelf_dir"]).resolve() != real.resolve(), "隔离失败：会污染真实数据"


def send_move(sh: S.Shelf, x: int, y: int, target=None,
              buttons=Qt.MouseButton.NoButton) -> None:
    """以真实派发表单把 MouseMove 送到命中控件（走真实 eventFilter 链）。"""
    target = target or sh.body
    ev = QMouseEvent(QEvent.Type.MouseMove,
                     QPointF(x, y),                       # local
                     QPointF(sh.mapToGlobal(QPoint(x, y))),  # global
                     Qt.MouseButton.NoButton, buttons,
                     Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(target, ev)


def main() -> int:
    isolate()
    app = QApplication.instance() or QApplication(sys.argv[:1])
    sh = S.Shelf()
    sh.resize(560, 480)
    app.processEvents()

    cs = Qt.CursorShape

    # 1) 左边缘 → SizeHorCursor 挂到命中控件上
    #    （sendEvent 后 Qt 还会合成 hover/move 给窗口本身，obj 可能是
    #     body 也可能是 Shelf —— 哪个最后调用挂在谁上面，两者都有效）
    send_move(sh, 2, 240)
    check("左边缘光标挂到命中控件", sh._scaled_cursor_widget is not None,
          f"scaled={sh._scaled_cursor_widget}")
    check("左边缘光标=左右缩放", sh.body.cursor().shape() == cs.SizeHorCursor,
          f"actual={sh.body.cursor().shape()}")

    # 2) 右下角 → SizeFDiagCursor
    send_move(sh, 558, 478)
    check("右下角光标=斜向缩放(\\)", sh.body.cursor().shape() == cs.SizeFDiagCursor,
          f"actual={sh.body.cursor().shape()}")

    # 3) 左下角 → SizeBDiagCursor
    send_move(sh, 2, 478)
    check("左下角光标=斜向缩放(/)", sh.body.cursor().shape() == cs.SizeBDiagCursor,
          f"actual={sh.body.cursor().shape()}")

    # 4) 上边缘（在 titlebar 保护带之外的最上沿）→ SizeVerCursor
    send_move(sh, 280, 2)
    check("上边缘光标=上下缩放", sh.body.cursor().shape() == cs.SizeVerCursor,
          f"actual={sh.body.cursor().shape()}")

    # 5) 移到中央 → 命中控件光标被还原（unsetCursor 后 WA_SetCursor=False）
    send_move(sh, 280, 240)
    check("划出热区后光标还原", sh._scaled_cursor_widget is None,
          f"scaled={sh._scaled_cursor_widget}")
    check("还原后控件无自定义光标",
          not sh.body.testAttribute(Qt.WidgetAttribute.WA_SetCursor))

    # 6) 按住左键移动 → 过滤器不接管（不改光标）
    send_move(sh, 2, 240, buttons=Qt.MouseButton.LeftButton)
    check("拖拽中不接管光标", sh._scaled_cursor_widget is None)

    # 7) 各类事件走过滤器不抛异常（回调异常 = qFatal 杀进程）
    ok = True
    for t in (QEvent.Type.MouseButtonPress, QEvent.Type.HoverEnter,
              QEvent.Type.HoverLeave, QEvent.Type.Resize, QEvent.Type.Show):
        try:
            ev2 = QEvent(t)
            sh.eventFilter(sh.body, ev2)
        except Exception:
            ok = False
    check("eventFilter 对杂项事件不抛异常", ok)

    print(f"\n=== 结果: {PASS} PASS, {FAIL} FAIL ===")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

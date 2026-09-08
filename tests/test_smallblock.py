"""回归测试：折叠态小方块（SmallBlock）拖动 + 尺寸 + 标题栏按钮精简。

用户三条反馈：
  1) 「最小化(—)按钮没意义，和缩成小方块合并」→ 删除 — 按钮，
     ▾=缩成小方块（最小化语义），✕ 保持后台运行（hide，非退出）。
  2) 「小方块可以拖动」→ 按住拖动改变位置；原地点击才展开
     （6px 阈值防误触，点击不展开、拖动不展开的判定必须准确）。
  3) 「小方块太小，放大一倍」→ 48x48 → 96x96。

另：用户拖动后再次折叠应回到拖到的位置（本次运行期内记忆）。
"""
import json
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

TMP = Path(tempfile.mkdtemp(prefix="shelf_smallblock_"))
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
    assert Path(s["shelf_dir"]).resolve() != real.resolve(), "隔离失败"


def mouse_ev(t, local, gpos, btn=Qt.MouseButton.LeftButton,
             buttons=Qt.MouseButton.LeftButton):
    return QMouseEvent(t, QPointF(local), QPointF(gpos),
                       btn, buttons, Qt.KeyboardModifier.NoModifier)


def main() -> int:
    isolate()
    app = QApplication.instance() or QApplication(sys.argv[:1])
    sh = S.Shelf()
    sh.resize(560, 480)
    app.processEvents()

    # ---- 1. 标题栏按钮：「▾」已删除（太小难按），「—」= 缩成小方块 ----
    from PyQt6.QtWidgets import QPushButton as _QPB
    btns = [b.text() for b in sh.titlebar.findChildren(_QPB)]
    check("「▾」折叠按钮已删除", "▾" not in btns, f"btns={btns}")
    check("「—」最小化按钮保留", "—" in btns)
    check("「✕」关闭按钮保留", "✕" in btns)
    # 点「—」= 缩成小方块（toggle_collapse）
    mini = next(b for b in sh.titlebar.findChildren(_QPB) if b.text() == "—")
    check("折叠前主窗未折叠", not sh._collapsed)
    mini.click()
    app.processEvents()
    check("点「—」后缩成小方块", sh._collapsed and sh._mini is not None)
    sh._mini.close()
    sh._mini = None
    sh._collapsed = False

    # ---- 2. SmallBlock 尺寸翻倍 ----
    sh.toggle_collapse()
    app.processEvents()
    mb = sh._mini
    check("小方块已创建", mb is not None)
    check("小方块 96x96（放大一倍）",
          mb.width() == 96 and mb.height() == 96,
          f"actual={mb.width()}x{mb.height()}")
    check("折叠后主窗隐藏", not sh.isVisible() or sh._collapsed)

    # ---- 3. 小方块拖动：移动窗口、松手不展开 ----
    origin = mb.pos()
    start_g = origin + QPoint(48, 48)
    mb.mousePressEvent(mouse_ev(QEvent.Type.MouseButtonPress,
                                QPoint(48, 48), start_g))
    drag_to = start_g + QPoint(120, 80)
    mb.mouseMoveEvent(mouse_ev(QEvent.Type.MouseMove,
                               QPoint(168, 128), drag_to))
    mb.mouseReleaseEvent(mouse_ev(QEvent.Type.MouseButtonRelease,
                                  QPoint(168, 128), drag_to,
                                  buttons=Qt.MouseButton.NoButton))
    app.processEvents()
    check("拖动后小方块移动到新位置",
          (mb.pos() - origin).manhattanLength() > 100,
          f"origin={origin} now={mb.pos()}")
    check("拖动松手不展开主窗", sh._mini is mb and sh._collapsed)

    # ---- 4. 原地点击：展开主窗并记住拖动位置 ----
    dragged_pos = mb.pos()
    click_g = dragged_pos + QPoint(48, 48)
    mb.mousePressEvent(mouse_ev(QEvent.Type.MouseButtonPress,
                                QPoint(48, 48), click_g))
    mb.mouseMoveEvent(mouse_ev(QEvent.Type.MouseMove,
                               QPoint(50, 50), click_g + QPoint(2, 2)))
    mb.mouseReleaseEvent(mouse_ev(QEvent.Type.MouseButtonRelease,
                                  QPoint(50, 50), click_g + QPoint(2, 2),
                                  buttons=Qt.MouseButton.NoButton))
    app.processEvents()
    check("原地点击展开主窗", sh._mini is None and not sh._collapsed)
    check("记住了用户拖到的位置",
          getattr(sh, "_mini_last_pos", None) == dragged_pos,
          f"last={getattr(sh, '_mini_last_pos', None)}")

    # ---- 5. 再次折叠 → 小方块回到用户拖到的位置 ----
    sh.toggle_collapse()
    app.processEvents()
    check("再折叠回到拖到的位置",
          sh._mini is not None and sh._mini.pos() == dragged_pos,
          f"actual={sh._mini.pos() if sh._mini else None}")
    sh._mini.close()
    sh._mini = None
    sh._collapsed = False

    print(f"\n=== 结果: {PASS} PASS, {FAIL} FAIL ===")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

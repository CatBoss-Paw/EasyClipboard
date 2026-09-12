"""素材页多选删除回归测试（沙盒隔离，绝不触碰真实数据）。

覆盖：
  1) 勾选 3 项后右键任一勾选卡：菜单出现「🗑 删除勾选的 3 项」
  2) 选择该项：3 张勾选卡一并移除，未勾选卡保留，manifest 同步
  3) 右键未勾选卡：菜单仍是单卡「删除」，只删那一张
  4) delete_entries 直接调用：列表与落盘一致，无残留
"""
import json
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

TMP = Path(tempfile.mkdtemp(prefix="shelf_multidel_"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import shelf_app as S                                   # noqa: E402
from PyQt6.QtCore import QPoint as _QP                  # noqa: E402
from PyQt6.QtWidgets import QApplication, QMenu         # noqa: E402

PASS = 0
FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  PASS {name}")
    else:
        FAIL += 1
        print(f"  FAIL {name}  {detail}")


def isolate():
    s = {
        "shelf_dir": str(TMP / "_TempShelf"),
        "history_dir": str(TMP / "_History"),
        "pinned_dir": str(TMP / "_Pinned"),
        "prompts_dir": str(TMP / "_Prompts"),
        "min_text_len": 2, "auto_clear_hours": 0,
        "hotkey": "f9", "autostart": False,
    }
    (TMP / "shelf_settings.json").write_text(
        json.dumps(s, ensure_ascii=False), encoding="utf-8")
    S.SETTINGS_PATH = TMP / "shelf_settings.json"
    S.SHELF_DIR = TMP / "_TempShelf"
    S.HISTORY_DIR = TMP / "_History"
    S.PINNED_DIR = TMP / "_Pinned"
    for k in ("shelf_dir", "history_dir", "pinned_dir", "prompts_dir"):
        Path(s[k]).mkdir(parents=True, exist_ok=True)
    real = Path(r"E:\项目搭建\剪贴板\_TempShelf")
    assert Path(s["shelf_dir"]).resolve() != real.resolve(), "隔离失败"


def manifest_texts():
    mp = S.SHELF_DIR / S.MANIFEST_NAME
    if not mp.exists():
        return []
    return [e.get("text", e.get("name", "?")) for e in
            json.loads(mp.read_text(encoding="utf-8"))]


def seed(sh):
    sh.entries = [
        {"kind": "text", "text": "多选甲", "ts": "01:00:01", "on": True},
        {"kind": "text", "text": "多选乙", "ts": "01:00:02", "on": True},
        {"kind": "text", "text": "多选丙", "ts": "01:00:03", "on": True},
        {"kind": "text", "text": "单选丁", "ts": "01:00:04", "on": False},
    ]
    sh._commit()


def card_of(sh, entry):
    for w in sh.findChildren(S.ShelfCard):
        if w.entry is entry:
            return w
    return None


class _Ctx:
    """拦截 QMenu.exec：记录菜单项并返回指定动作。"""
    last_actions = []
    pick_text = None

    def fake_exec(self, *a, **k):
        _Ctx.last_actions = [x.text() for x in self.actions()]
        for x in self.actions():
            if _Ctx.pick_text and _Ctx.pick_text in x.text():
                return x
        return None


def main():
    isolate()
    app = QApplication.instance() or QApplication(sys.argv[:1])
    sh = S.Shelf()
    sh.resize(560, 480)
    app.processEvents()

    seed(sh)
    old_exec = QMenu.exec
    QMenu.exec = _Ctx.fake_exec
    try:
        # 1) 右键勾选卡 → 批量删除菜单项出现并被选中
        _Ctx.pick_text = "删除勾选的"
        card = card_of(sh, sh.entries[0])
        check("勾选卡找到", card is not None)
        card.customContextMenuRequested.emit(_QP(5, 5))
        app.processEvents()
        check("菜单含「删除勾选的 3 项」",
              any("删除勾选的 3 项" in a for a in _Ctx.last_actions),
              repr(_Ctx.last_actions))
        check("批量删除生效：剩 1 条", len(sh.entries) == 1 and
              sh.entries[0]["text"] == "单选丁", repr(manifest_texts()))
        check("manifest 同步", manifest_texts() == ["单选丁"])

        # 2) 右键未勾选卡 → 单卡删除，菜单不含批量项
        _Ctx.last_actions = []
        _Ctx.pick_text = "删除"          # 命中唯一含「删除」的项（此时无批量项）
        card_d = card_of(sh, sh.entries[0])
        card_d.customContextMenuRequested.emit(_QP(5, 5))
        app.processEvents()
        check("未勾选卡菜单为单卡「删除」",
              _Ctx.last_actions and "删除" in _Ctx.last_actions
              and not any("删除勾选的" in a for a in _Ctx.last_actions),
              repr(_Ctx.last_actions))
        check("单卡删除生效：清空", len(sh.entries) == 0, repr(manifest_texts()))

        # 3) delete_entries 直调：混合勾选批量移除
        seed(sh)
        sh.entries[3]["on"] = True       # 4 项全勾
        sh._commit()
        targets = list(sh.entries)
        sh.delete_entries(targets)
        check("delete_entries 全清", len(sh.entries) == 0 and manifest_texts() == [])
    finally:
        QMenu.exec = old_exec

    print(f"\n=== 结果: {PASS} PASS, {FAIL} FAIL ===")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

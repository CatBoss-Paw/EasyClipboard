#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
实测右下角缩放把手：【用户看到的 ◢】和【真正能触发缩放的热区】是否重合。

源码事实：
    视觉把手  shelf_app.py:1461
        self.size_hint_lab = QLabel("◢", objectName="sizeHint")
        self.size_hint_lab.setFixedSize(18, 14)
        grip_row = QHBoxLayout(); grip_row.addStretch(1); addWidget(size_hint_lab)
        -> 贴 body 右下角，而 body 的 layout margins 是 (14,10,14,12)
           (shelf_app.py:1174  v.setContentsMargins(14, 10, 14, 12))

    功能热区  shelf_app.py:2525
        def _near_resize_corner(self, pos):
            return pos.x() >= self.width() - 18 and pos.y() >= self.height() - 18
        -> 热区 = 窗口右下角 18x18，【从窗口边缘算起】

高度可疑之处：
    ◢ 因为 layout 的右/下边距 (14,12) 而被推到窗口边缘【内侧】，
    于是「看得见的把手」和「摸得着的热区」很可能大面积错开 ——
    用户照着 ◢ 去拖，按到的却是热区之外的空白，表现就是
    「右下角拖不动 / 一直实现不了」。

判据（必须量化，不能靠感觉）：
    交集面积 / ◢ 面积  -> 用户按住 ◢ 时有多大比例真的能触发缩放
    交集面积 / 热区面积 -> 热区里有多大比例是「看得见」的

安全：数据根隔离到临时目录。
"""
import json
import sys
import tempfile
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="shelf_grip_geo_"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import shelf_app                                     # noqa: E402
from PyQt6.QtWidgets import QApplication             # noqa: E402
from PyQt6.QtCore import QPoint, QRect               # noqa: E402


def isolate():
    s = {
        "shelf_dir": str(TMP / "_TempShelf"),
        "history_dir": str(TMP / "_History"),
        "pinned_dir": str(TMP / "_Pinned"),
        "min_text_len": 2, "auto_clear_hours": 0,
        "hotkey": "f9", "autostart": False,
    }
    f = TMP / "shelf_settings.json"
    f.write_text(json.dumps(s, ensure_ascii=False), encoding="utf-8")
    shelf_app.SETTINGS_PATH = f
    for k in ("shelf_dir", "history_dir", "pinned_dir"):
        Path(s[k]).mkdir(parents=True, exist_ok=True)
    real = Path(r"E:\项目搭建\剪贴板\_TempShelf")
    assert Path(s["shelf_dir"]).resolve() != real.resolve()


def main():
    isolate()
    app = QApplication.instance() or QApplication(sys.argv[:1])
    sh = shelf_app.Shelf()
    for w, h in ((900, 620), (760, 560), (320, 240)):
        sh.resize(w, h)
        sh.show()
        app.processEvents()

        W, H = sh.width(), sh.height()
        lab = sh.size_hint_lab
        # ◢ 的真实几何（换算到 Shelf 坐标系）
        tl = lab.mapTo(sh, QPoint(0, 0))
        grip_visual = QRect(tl.x(), tl.y(), lab.width(), lab.height())
        # 功能热区（_near_resize_corner 的定义域）
        hot = QRect(W - 18, H - 18, 18, 18)
        inter = grip_visual.intersected(hot)

        a_v = grip_visual.width() * grip_visual.height()
        a_h = hot.width() * hot.height()
        a_i = max(0, inter.width()) * max(0, inter.height())

        print("=" * 76)
        print("窗口 %d x %d" % (W, H))
        print("  ◢ 视觉把手  : %s  (面积 %d)" % (str(grip_visual), a_v))
        print("  功能热区    : %s  (面积 %d)" % (str(hot), a_h))
        print("  两者交集    : %s  (面积 %d)" % (str(inter), a_i))
        print("  按住 ◢ 能触发缩放的比例 : %.1f%%" % (100.0 * a_i / a_v if a_v else 0))
        print("  热区中「看得见」的比例  : %.1f%%" % (100.0 * a_i / a_h if a_h else 0))

        # 逐点实测：从 ◢ 的中心到窗口最右下角，哪些点真能触发缩放
        print("  逐点实测（x,y -> _near_resize_corner）:")
        samples = [
            ("◢ 中心", grip_visual.center()),
            ("◢ 左上", grip_visual.topLeft()),
            ("◢ 右下", grip_visual.bottomRight()),
            ("窗口最右下角", QPoint(W - 1, H - 1)),
            ("热区中心", hot.center()),
        ]
        hit = 0
        for name, p in samples:
            ok = sh._near_resize_corner(p)
            hit += 1 if ok else 0
            print("      %-14s (%3d,%3d) -> %s"
                  % (name, p.x(), p.y(), "可缩放" if ok else "★ 不可缩放"))
        print("  按住 ◢ 中心能否缩放: %s"
              % ("能" if sh._near_resize_corner(grip_visual.center()) else "★ 不能"))
        print()

    sh.close()
    app.processEvents()
    print("=" * 76)
    print("结论：若『按住 ◢ 能触发缩放的比例』远小于 100%，则用户看到的把手")
    print("      与功能热区错位 —— 这就是「右下角拖不动」的真因。")
    print("=" * 76)


if __name__ == "__main__":
    main()

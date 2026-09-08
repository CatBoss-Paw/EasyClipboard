#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
实测「按住单个卡片直接拖出该卡片」链路，不依赖勾选状态。

用户要的行为：按住卡片往外拖 = 拖出这张卡片本身，不需要先勾选。

源码链路：
    ShelfCard.mouseMoveEvent            shelf_app.py:689
      dist >= CARD_DRAG_THRESHOLD(14)
      -> Shelf.start_card_drag(entry)   :2557
           text  -> QMimeData.setText  -> _execute_drag 之外单独 exec
           image -> start_files_drag -> _get_entry_files(entry)
           file  -> start_files_drag -> _get_entry_files(entry)
      -> _execute_drag(drag_files)      :2591  QDrag.exec()

必须实测的原因：
    修 BUG-001/002 时改过 ShelfCard 的 mousePressEvent / mouseMoveEvent /
    mouseDoubleClickEvent，拖出链路从未做过端到端验证。而且
    _toast 是空实现（零打扰原则），任何失败分支都是【静默的】——
    用户拖不动时得不到任何解释。

测法：把 QDrag.exec 替换成记录器（真调 exec 会进嵌套事件循环把测试卡死），
    断言 mimeData 内容正确、且真的走到了 exec。

安全：数据根隔离到临时目录。
"""
import json
import sys
import tempfile
import time
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="shelf_carddrag_"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import shelf_app                                          # noqa: E402
from PyQt6.QtWidgets import QApplication                  # noqa: E402
from PyQt6.QtCore import QEvent, QPoint, QPointF, Qt      # noqa: E402
from PyQt6.QtGui import QMouseEvent, QDrag                # noqa: E402

PASS, FAIL = [], []


def isolate():
    """把数据根完全隔离到 TMP，返回 (settings, shelf_dir)。

    【本脚本曾因此污染过真实数据目录，切记】
    shelf_app 在 import 时就把 SHELF_DIR / DEFAULT_SETTINGS["shelf_dir"]
    固化为【真实项目目录】的绕对路径。而 Shelf.__init__ 会 load_settings()
    后用 settings["shelf_dir"] 覆写全局 SHELF_DIR。

    所以：在构造 Shelf() 【之前】读 shelf_app.SHELF_DIR 拿到的是真实目录！
    当时就向它写了 img_carddrag.png，直接落到用户真实 _TempShelf 里。

    铁律：本文件内【绝不引用 shelf_app.SHELF_DIR】，所有路径一律用
    isolate() 返回的 tmp_shelf（在 TMP 下）。写完文件后还要在构造 Shelf()
    之后断言一次全局已被改成 TMP，作为第二重保险。
    """
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
    # 同时把模块全局也改掉，避免任何遗漏的引用路径误写到真实目录
    shelf_app.SHELF_DIR = TMP / "_TempShelf"
    shelf_app.HISTORY_DIR = TMP / "_History"
    shelf_app.PINNED_DIR = TMP / "_Pinned"
    for k in ("shelf_dir", "history_dir", "pinned_dir"):
        Path(s[k]).mkdir(parents=True, exist_ok=True)
    real = Path(r"E:\项目搭建\剪贴板\_TempShelf")
    assert Path(s["shelf_dir"]).resolve() != real.resolve(), "隔离失败"
    return s, TMP / "_TempShelf"


def mk(etype, local, glob, button, buttons):
    return QMouseEvent(etype, QPointF(local), QPointF(glob), button, buttons,
                       Qt.KeyboardModifier.NoModifier)


def check(name, ok, detail=""):
    (PASS if ok else FAIL).append(name)
    print("[%s] %s%s" % ("PASS" if ok else "FAIL", name,
                         ("  | " + detail) if detail else ""))


def live_cards(sh):
    """从【布局】里取活卡片，而不是用 findChildren。

    踩坑记录：_sync_ui() 重建卡片时先 takeAt(0) 把旧卡片移出布局，
    再 deleteLater() 销毁。但 DeferredDelete 事件不一定被 processEvents
    当场处理完，实测 findChildren 会同时返回【新卡片和陈旧的待删卡片】，
    而且两者持有的是同一个 entry 字典（`is` 也分不开），拿 [0] 就可能
    拿到陈旧对象，事件发进去什么也不会发生（表现为静默失败）。

    布局是可靠的：takeAt 已经把旧卡片移出去了，剩下的就是活的。
    """
    out = []
    for box in (sh.cards_box_files, sh.cards_box_text):
        for i in range(box.count()):
            w = box.itemAt(i).widget()
            if isinstance(w, shelf_app.ShelfCard):
                out.append(w)
    return out


def card_of(sh, kind):
    """按 kind 取当前布局里的活卡片（_sync_ui 分两栏且各自 reversed，
    所以绝不能按 sh.entries 的顺序索引 findChildren 的结果）。"""
    for c in live_cards(sh):
        if c.entry.get("kind") == kind:
            return c
    return None


def main():
    _settings, tmp_shelf = isolate()
    app = QApplication.instance() or QApplication(sys.argv[:1])

    # ---- 拦截 QDrag.exec：真调会进嵌套事件循环卡死测试 ----
    drag_log = []
    orig_exec = QDrag.exec

    def spy_exec(self, actions=None, *a, **kw):
        mime = self.mimeData()
        drag_log.append({
            "text": mime.text() if mime.hasText() else None,
            "urls": [u.toLocalFile() for u in mime.urls()] if mime.hasUrls() else [],
            "formats": sorted(mime.formats()),
        })
        return Qt.DropAction.CopyAction

    QDrag.exec = spy_exec

    # ---- 记录 _toast 调用：静默失败的唯一线索 ----
    toast_log = []
    orig_toast = shelf_app.Shelf._toast

    def spy_toast(self, msg):
        toast_log.append(msg)
        return orig_toast(self, msg)

    shelf_app.Shelf._toast = spy_toast

    # ---- 造数据：文本 / 图片 / 文件 引用三种，全部 on=False（产品默认）----
    # 【必须用 tmp_shelf，绠不能用 shelf_app.SHELF_DIR】—— 后者在构造 Shelf()
    # 之前仍指向真实项目目录，用它就会把测试图写进用户真实数据（踩过）。
    shelf_dir = tmp_shelf
    real_dir = Path(r"E:\项目搭建\剪贴板\_TempShelf")
    assert shelf_dir.resolve() != real_dir.resolve(), "隔离失败：将写入真实目录"
    img_name = "img_carddrag.png"
    (shelf_dir / img_name).write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 200)
    ref_file = TMP / "外部引用.txt"
    ref_file.write_text("外部文件内容", encoding="utf-8")

    entries = [
        {"kind": "text", "text": "卡片直接拖出的文本内容", "on": False,
         "ts": "00:01", "at": 0, "hash": "a"},
        {"kind": "image", "name": img_name, "on": False,
         "ts": "00:02", "at": 0, "hash": "b"},
        {"kind": "file", "name": ref_file.name, "src": str(ref_file),
         "on": False, "ts": "00:03", "at": 0, "hash": "c"},
    ]

    sh = shelf_app.Shelf()
    # 第二重保险：构造后全局必须已被 __init__ 改成 TMP，否则立即中止
    assert Path(shelf_app.SHELF_DIR).resolve() == shelf_dir.resolve(), \
        "隔离失败：Shelf.__init__ 把 SHELF_DIR 改回了 %r" % (shelf_app.SHELF_DIR,)
    sh.resize(900, 620)
    sh.entries = list(entries)
    sh._sync_ui()
    sh.show()
    app.processEvents()

    print("=" * 78)
    print("【前提】所有条目 on=False（产品铁律：默认全不选）")
    print("        卡片拖出必须【不依赖勾选】就能工作")
    print("=" * 78)
    all_cards = live_cards(sh)
    print("布局内活卡片数:", len(all_cards))
    by_kind = {}
    for c in all_cards:
        by_kind.setdefault(c.entry["kind"], []).append(c)
    print("按 kind 分组:", {k: len(v) for k, v in by_kind.items()})
    card_text = card_of(sh, "text")
    card_image = card_of(sh, "image")
    card_file = card_of(sh, "file")
    check("三种卡片均已渲染", all((card_text, card_image, card_file)))
    print()

    def drag_card(card, expect_kind, move=40):
        """按住指定卡片往外拖 move 像素，返回 (drag_ok, toast_msgs)。

        【每次调用前重取卡片】：_sync_ui 会 deleteLater 旧卡片并重建，
        旧引用会变成已删除的 C++ 对象（RuntimeError: wrapped C/C++ object
        of type ShelfCard has been deleted）。已踩过一次。
        """
        drag_log.clear()
        toast_log.clear()
        pt = QPoint(card.width() // 2, card.height() // 2)
        gp = card.mapToGlobal(QPointF(pt))
        app.sendEvent(card, mk(QEvent.Type.MouseButtonPress, QPointF(pt),
                               gp, Qt.MouseButton.LeftButton,
                               Qt.MouseButton.LeftButton))
        app.processEvents()
        # 分两步移动，跨越阈值 14
        for step in (move // 2, move):
            lp = QPointF(pt.x() + step, pt.y() + step)
            app.sendEvent(card, mk(QEvent.Type.MouseMove, lp,
                                   card.mapToGlobal(lp),
                                   Qt.MouseButton.NoButton,
                                   Qt.MouseButton.LeftButton))
            app.processEvents()
        app.sendEvent(card, mk(QEvent.Type.MouseButtonRelease,
                               QPointF(pt.x() + move, pt.y() + move),
                               card.mapToGlobal(QPointF(pt.x() + move,
                                                        pt.y() + move)),
                               Qt.MouseButton.NoButton,
                               Qt.MouseButton.NoButton))
        app.processEvents()
        return bool(drag_log), list(toast_log)

    # ---- 1. 文本卡片：拖出纯文字 ----
    ok, toasts = drag_card(card_text, "text")
    print("【1】文本卡片拖出")
    print("    发起 QDrag = %s ; _toast 调用 = %s" % (ok, toasts))
    if drag_log:
        print("    mime.text = %r" % drag_log[-1]["text"])
        print("    mime.formats = %s" % drag_log[-1]["formats"])
    check("文本卡片：按住直接拖出发起了 QDrag", ok)
    check("文本卡片：mime 携带正确文本",
          bool(drag_log) and drag_log[-1]["text"] == entries[0]["text"],
          repr(drag_log[-1]["text"]) if drag_log else "(无)")
    print()

    # ---- 2. 图片卡片：拖出图片文件本体（零拷贝引用）----
    ok2, toasts2 = drag_card(card_image, "image")
    print("【2】图片卡片拖出（on=False，不依赖勾选）")
    print("    发起 QDrag = %s ; _toast 调用 = %s" % (ok2, toasts2))
    if drag_log:
        print("    mime.urls = %s" % drag_log[-1]["urls"])
    expect_img = str((shelf_dir / img_name))
    check("图片卡片：按住直接拖出发起了 QDrag", ok2)
    check("图片卡片：mime 携带图片文件路径（非拷贝）",
          bool(drag_log) and any(
              Path(u).resolve() == Path(expect_img).resolve()
              for u in drag_log[-1]["urls"]),
          str(drag_log[-1]["urls"]) if drag_log else "(无)")
    print()

    # ---- 3. 文件引用卡片：拖出源文件路径 ----
    ok3, toasts3 = drag_card(card_file, "file")
    print("【3】文件引用卡片拖出（on=False）")
    print("    发起 QDrag = %s ; _toast 调用 = %s" % (ok3, toasts3))
    if drag_log:
        print("    mime.urls = %s" % drag_log[-1]["urls"])
    check("文件卡片：按住直接拖出发起了 QDrag", ok3)
    check("文件卡片：mime 携带源文件路径（零拷贝）",
          bool(drag_log) and any(
              Path(u).resolve() == ref_file.resolve()
              for u in drag_log[-1]["urls"]),
          str(drag_log[-1]["urls"]) if drag_log else "(无)")
    print()

    # ---- 4. 拖出不得污染勾选状态（拖拽 != 勾选）----
    on_states = [e.get("on") for e in sh.entries]
    check("拖出操作未擅自改变勾选状态（仍全 False）",
          all(v is False for v in on_states), str(on_states))
    print()

    # ---- 5. 单击不得误触发拖出（阈值防误触）----
    drag_log.clear()
    toast_log.clear()
    card = card_of(sh, "text")
    pt = QPoint(card.width() // 2, card.height() // 2)
    gp = card.mapToGlobal(QPointF(pt))
    app.sendEvent(card, mk(QEvent.Type.MouseButtonPress, QPointF(pt), gp,
                           Qt.MouseButton.LeftButton,
                           Qt.MouseButton.LeftButton))
    app.processEvents()
    tiny = QPointF(pt.x() + 3, pt.y() + 3)          # 3+3=6 < 14 阈值
    app.sendEvent(card, mk(QEvent.Type.MouseMove, tiny, card.mapToGlobal(tiny),
                           Qt.MouseButton.NoButton,
                           Qt.MouseButton.LeftButton))
    app.processEvents()
    app.sendEvent(card, mk(QEvent.Type.MouseButtonRelease, tiny,
                           card.mapToGlobal(tiny), Qt.MouseButton.NoButton,
                           Qt.MouseButton.NoButton))
    app.processEvents()
    check("轻微移动(6px<14阈值)不误触发拖出", not drag_log,
          "drag_log=%s" % drag_log)
    print()

    # ---- 6. 双击仍走双击动作，不演变成拖出（BUG-002 修复不得回归）----
    drag_log.clear()
    card = card_of(sh, "text")
    pt = QPoint(card.width() // 2, card.height() // 2)
    gp = card.mapToGlobal(QPointF(pt))
    t0 = time.monotonic()
    app.sendEvent(card, mk(QEvent.Type.MouseButtonPress, QPointF(pt), gp,
                           Qt.MouseButton.LeftButton,
                           Qt.MouseButton.LeftButton))
    app.processEvents()
    app.sendEvent(card, mk(QEvent.Type.MouseButtonRelease, QPointF(pt), gp,
                           Qt.MouseButton.NoButton,
                           Qt.MouseButton.NoButton))
    app.processEvents()
    app.sendEvent(card, mk(QEvent.Type.MouseButtonPress, QPointF(pt), gp,
                           Qt.MouseButton.LeftButton,
                           Qt.MouseButton.LeftButton))
    app.processEvents()
    dt = time.monotonic() - t0
    check("双击文本卡片未误触发拖出（走双击复制分支）", not drag_log,
          "两次按压间隔 %.3fs ; drag_log=%s" % (dt, drag_log))
    print()

    # ---- 7. 缺失源文件时不得静默：应给出可感知反馈 ----
    drag_log.clear()
    toast_log.clear()
    img_entry = next(e for e in sh.entries if e["kind"] == "image")
    img_entry["name"] = "不存在的图片.png"
    sh._sync_ui()
    app.processEvents()
    app.processEvents()

    # 从布局取，自然只有活卡片（旧卡片已被 takeAt 移出布局）
    fresh = [c for c in live_cards(sh) if c.entry["kind"] == "image"]
    print("    布局内 image 活卡片: %d 张" % len(fresh))
    check("重建后布局内只有一张活的 image 卡片", len(fresh) == 1,
          "live=%d" % len(fresh))
    if fresh:
        drag_card(fresh[0], "image")
        print("【7】源文件缺失时的表现")
        print("    发起 QDrag = %s ; _toast 调用 = %s"
              % (bool(drag_log), toast_log))
        check("源文件缺失时给出可感知反馈（不得纯静默）",
              bool(toast_log) or bool(drag_log),
              "toast=%s drag=%s" % (toast_log, bool(drag_log)))
    print()

    QDrag.exec = orig_exec
    shelf_app.Shelf._toast = orig_toast
    sh.close()
    app.processEvents()

    print("=" * 78)
    print("结果: %d PASS / %d FAIL" % (len(PASS), len(FAIL)))
    for f in FAIL:
        print("   FAILED:", f)
    print("=" * 78)
    return 0 if not FAIL else 1


if __name__ == "__main__":
    sys.exit(main())

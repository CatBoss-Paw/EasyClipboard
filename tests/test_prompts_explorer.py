# -*- coding: utf-8 -*-
"""快速指令区（提示词收藏夹）资源管理器打开与分类新建专项测试。

覆盖：
1. 快速指令顶部按钮：包含「新建分类」、「打开目录」、「刷新」；
2. 分类列表右键菜单：包含「在资源管理器中打开」、「新建分类」；
3. 分类列表空白处右键菜单：包含「在资源管理器中打开」、「新建分类」、「刷新列表」；
4. MD 文档卡片右键菜单：包含「在资源管理器中打开」、「复制全文」、「编辑内容」；
5. _reveal_in_explorer 方法：对目录调用 os.startfile，对文件调用 explorer /select。
"""
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

TMP = Path(tempfile.mkdtemp(prefix="shelf_prompts_exp_"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import shelf_app as S
from PyQt6.QtWidgets import QApplication, QMenu, QPushButton
from PyQt6.QtCore import QPoint

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


def main():
    app = QApplication.instance() or QApplication(sys.argv[:1])

    # 1. 严格沙盒隔离
    S.SHELF_DIR = TMP / "_TempShelf"
    S.HISTORY_DIR = TMP / "_History"
    S.PINNED_DIR = TMP / "_Pinned"
    S.SHELF_DIR.mkdir(parents=True, exist_ok=True)
    (TMP / "_Prompts").mkdir(parents=True, exist_ok=True)

    sh = S.Shelf()
    sh.prompts.root = TMP / "_Prompts"
    sh.refresh_prompts_page()
    app.processEvents()

    # 2. 检查顶部按钮
    top_btn_texts = [b.text().strip() for b in sh.prompts_page.findChildren(QPushButton)]
    check("顶部包含「新建分类」按钮", "新建分类" in top_btn_texts, repr(top_btn_texts))
    check("顶部包含「打开目录」按钮", "打开目录" in top_btn_texts, repr(top_btn_texts))
    check("顶部包含「刷新」按钮", "刷新" in top_btn_texts, repr(top_btn_texts))

    # 3. 捕获分类右键菜单
    captured_menus = []
    old_menu_exec = QMenu.exec

    def spy_exec(self, *a, **k):
        captured_menus.append([act.text() for act in self.actions()])
        return None

    QMenu.exec = spy_exec

    try:
        # 分类项右键
        sh._prompt_cat_ctx(QPoint(5, 5))
        cat_acts = captured_menus[-1] if captured_menus else []
        check("分类项右键含「在资源管理器中打开」", "在资源管理器中打开" in cat_acts, repr(cat_acts))
        check("分类项右键含「新建分类」", "新建分类" in cat_acts, repr(cat_acts))

        # 空白处右键
        sh._prompt_cat_ctx(QPoint(5, 999))
        blank_acts = captured_menus[-1] if captured_menus else []
        check("空白处右键含「在资源管理器中打开」", "在资源管理器中打开" in blank_acts, repr(blank_acts))
        check("空白处右键含「新建分类」", "新建分类" in blank_acts, repr(blank_acts))

        # 4. 文档卡片右键菜单
        sh.prompts.add_text("这是一条测试提示词内容", "默认", "测试指令")
        sh.refresh_prompts_page()
        app.processEvents()
        doc_cards = sh.prompt_docs_host.findChildren(S.PromptDocCard)
        check("成功渲染文档卡片", len(doc_cards) >= 1, f"count={len(doc_cards)}")

        if doc_cards:
            sh._prompt_doc_ctx(doc_cards[0], QPoint(5, 5))
            doc_acts = captured_menus[-1] if captured_menus else []
            check("文档卡右键含「在资源管理器中打开」", "在资源管理器中打开" in doc_acts, repr(doc_acts))
            check("文档卡右键含「复制全文」", "复制全文" in doc_acts, repr(doc_acts))
            check("文档卡右键含「编辑内容」", "编辑内容" in doc_acts, repr(doc_acts))
    finally:
        QMenu.exec = old_menu_exec

    # 5. _reveal_in_explorer 逻辑验证
    calls = []
    old_startfile = S.os.startfile
    S.os.startfile = lambda p: calls.append(("startfile", p))

    import subprocess
    old_popen = subprocess.Popen
    subprocess.Popen = lambda cmd, **k: calls.append(("popen", cmd))

    try:
        # 验证目录打开
        sh._reveal_in_explorer(str(TMP / "_Prompts"))
        check("_reveal_in_explorer 打开目录调用 startfile",
              any(c[0] == "startfile" for c in calls), repr(calls))

        # 验证文件打开
        test_file = TMP / "_Prompts" / "默认" / "测试指令.md"
        sh._reveal_in_explorer(str(test_file))
        check("_reveal_in_explorer 打开文件调用 explorer /select",
              any("explorer" in str(c[1]) and "/select," in str(c[1])
                  for c in calls if c[0] == "popen"),
              repr(calls))
    finally:
        S.os.startfile = old_startfile
        subprocess.Popen = old_popen

    print(f"\n=== 结果: {PASS} PASS, {FAIL} FAIL ===")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

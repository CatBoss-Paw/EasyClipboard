"""快速指令区 UI 插入（第2部分）：QtWidgets 补全 / Shelf 方法 / 卡片右键接线 / 日志按钮 / 三个新类。"""
from pathlib import Path

p = Path(r"E:\项目搭建\剪贴板\shelf_app.py")
src = p.read_text(encoding="utf-8")

def rep(old, new, tag):
    global src
    assert src.count(old) == 1, f"{tag} 锚点 {src.count(old)} 处"
    src = src.replace(old, new)

# 1) QtWidgets 补 QInputDialog / QComboBox
rep('''                              QStackedWidget, QLineEdit, QSizeGrip)''',
    '''                              QStackedWidget, QLineEdit, QSizeGrip,
                              QInputDialog, QComboBox)''',
    "qtimports")

# 2) ShelfCard 右键接线（有 shelf 引用）
rep('''        self._drag_start_pos = None
        self._last_press = None          # (monotonic秒, 逻辑坐标) 用于自判定双击
        self._build_ui()''',
    '''        self._drag_start_pos = None
        self._last_press = None          # (monotonic秒, 逻辑坐标) 用于自判定双击
        # 右键菜单：文字卡=「加入快速/删除」；附件卡=「加入快速访问区/删除」
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(
            lambda pos: shelf._card_context_menu(self, pos))
        self._build_ui()''',
    "cardctx")

# 3) 日志条目右侧加 ⚡ 加入快速按钮
rep('''        cp = QPushButton("📋", objectName="hoverActionBtn")
        cp.setFixedSize(24, 24)
        cp.setToolTip("复制这一条")
        cp.clicked.connect(lambda *a, b=body, t=ts: self._copy_journal_entry(b))
        h.addWidget(cp)
        return row''',
    '''        qp = QPushButton("⚡", objectName="hoverActionBtn")
        qp.setFixedSize(24, 24)
        qp.setToolTip("收进快速指令（提示词收藏夹）")
        qp.clicked.connect(lambda *a, b=body: self.add_prompt_text(b))
        h.addWidget(qp)
        cp = QPushButton("📋", objectName="hoverActionBtn")
        cp.setFixedSize(24, 24)
        cp.setToolTip("复制这一条")
        cp.clicked.connect(lambda *a, b=body, t=ts: self._copy_journal_entry(b))
        h.addWidget(cp)
        return row''',
    "journalbtn")

# 4) Shelf 方法组：插在 toggle_collapse 定义之前
rep('''    def toggle_collapse(self):''',
    '''    # ------------------------------------------------------ ⚡ 快速指令区（提示词收藏夹）
    def refresh_prompts_page(self):
        """刷新分类列表（保留选中）+ 文档卡片。"""
        cur_item = self.prompt_cat_list.currentItem()
        cur = cur_item.text() if cur_item is not None else None
        folders = self.prompts.folders()
        if not folders:
            self.prompts.ensure_folder("默认")
            folders = self.prompts.folders()
        blocker = self.prompt_cat_list.blockSignals(True)
        self.prompt_cat_list.clear()
        self.prompt_cat_list.addItems(
            [("📌 " if self.prompts._index["folders"].get(f, {}).get("pinned") else "") + f
             for f in folders])
        idx = folders.index(cur) if cur in folders else 0
        self.prompt_cat_list.setCurrentRow(idx)
        self.prompt_cat_list.blockSignals(blocker)
        self.refresh_prompt_docs(folders[idx])

    def refresh_prompt_docs(self, folder=""):
        """刷文档卡片；folder 列表项可能带 📌 前缀，需剥离。"""
        if isinstance(folder, str):
            folder = folder.lstrip("📌 ")
        if not folder:
            item = self.prompt_cat_list.currentItem()
            folder = item.text().lstrip("📌 ") if item is not None else ""
        while (item := self.prompt_docs_box.takeAt(0)) is not None:
            w = item.widget()
            if w is not None:
                w.deleteLater()
        if not folder:
            self.prompt_docs_box.addWidget(
                QLabel("先新建一个分类", objectName="empty"))
        else:
            docs = self.prompts.docs(folder)
            if not docs:
                empty = QLabel("这个分类还没有提示词\n\n"
                               "在首页的文字碎片卡片上，右键「加入快速」即可收进来",
                               objectName="empty")
                empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
                self.prompt_docs_box.addWidget(empty)
            for d in docs:
                self.prompt_docs_box.addWidget(PromptDocCard(self, folder, d))
        self.prompt_docs_box.addStretch(1)

    def _prompt_current_folder(self):
        item = self.prompt_cat_list.currentItem()
        return item.text().lstrip("📌 ") if item is not None else ""

    def _prompt_new_category(self):
        name, ok = QInputDialog.getText(self, "新建分类", "分类名称（对应文件夹）：")
        if ok and str(name).strip():
            self.prompts.ensure_folder(str(name).strip())
            self.refresh_prompts_page()
            self._toast(f"已建分类「{name.strip()}」")

    def _prompt_cat_ctx(self, pos):
        item = self.prompt_cat_list.itemAt(pos)
        if item is None:
            return
        name = item.text().lstrip("📌 ")
        menu = QMenu(self)
        a_rename = menu.addAction("改名")
        pinned = self.prompts._index["folders"].get(name, {}).get("pinned", False)
        a_pin = menu.addAction("取消置顶" if pinned else "置顶")
        a_del = menu.addAction("删除分类")
        chosen = menu.exec(self.prompt_cat_list.mapToGlobal(pos))
        if chosen == a_rename:
            new_name, ok = QInputDialog.getText(
                self, "分类改名", f"「{name}」改为：", text=name)
            if ok and str(new_name).strip() and new_name.strip() != name:
                try:
                    self.prompts.rename_folder(name, str(new_name).strip())
                    self.refresh_prompts_page()
                except (FileNotFoundError, FileExistsError) as e:
                    self._toast(f"分类改名失败：{e}")
        elif chosen == a_pin:
            self.prompts.toggle_folder_pin(name)
            self.refresh_prompts_page()
        elif chosen == a_del:
            if self.prompts.delete_folder(name):
                self.refresh_prompts_page()
                self._toast("已删除分类")
            else:
                self._toast("分类里还有内容，先移走或删除其中的提示词")

    def _prompt_doc_ctx(self, card, pos):
        fold, name = card.folder, card.info["name"]
        menu = QMenu(self)
        a_copy = menu.addAction("复制全文")
        a_edit = menu.addAction("编辑内容")
        menu.addSeparator()
        a_ren = menu.addAction("改名")
        a_pin = menu.addAction("取消置顶" if card.info["pinned"] else "置顶")
        menu.addSeparator()
        a_del = menu.addAction("删除")
        chosen = menu.exec(card.mapToGlobal(pos))
        if chosen == a_copy:
            self._prompt_copy(fold, name)
        elif chosen == a_edit:
            dlg = PromptEditDialog(self, fold, name)
            dlg.saved.connect(self.refresh_prompt_docs_cur)
            dlg.show()
        elif chosen == a_ren:
            new_name, ok = QInputDialog.getText(
                self, "文档改名", f"「{name}」改为：", text=name)
            if ok and str(new_name).strip() and new_name.strip() != name:
                try:
                    self.prompts.rename_doc(fold, name, str(new_name).strip())
                    self.refresh_prompt_docs_cur()
                except (FileNotFoundError, FileExistsError) as e:
                    self._toast(f"改名失败：{e}")
        elif chosen == a_pin:
            self.prompts.toggle_doc_pin(fold, name)
            self.refresh_prompt_docs_cur()
        elif chosen == a_del:
            self.prompts.delete_doc(fold, name)
            self.refresh_prompt_docs_cur()
            self._toast("已删除这篇提示词")

    def refresh_prompt_docs_cur(self):
        self.refresh_prompt_docs(self._prompt_current_folder())

    def _prompt_copy(self, folder, name):
        text = self.prompts.read_doc(folder, name)
        if not text.strip():
            self._toast("内容为空")
            return
        mime = QMimeData()
        mime.setText(text)
        self._write_own_clipboard(mime, self._suppress_signature([], text))
        self._toast("已复制这条提示词")

    # ---- 文本入收藏：从文字卡片/日志条目进入 ----
    def add_prompt_text(self, text: str):
        if not str(text or "").strip():
            self._toast("内容为空，未收藏")
            return
        dlg = PromptCategoryDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            folder = dlg.selected_folder()
            try:
                path = self.prompts.add_text(text, folder)
                self._toast(f"已收进「{folder}」：{path.stem}")
                if self.view_stack.currentIndex() == 4:
                    self.refresh_prompts_page()
            except ValueError:
                self._toast("内容为空，未收藏")

    # ---- 素材卡片右键：文字=加入快速/删除；附件=加入快速访问区/删除 ----
    def _card_context_menu(self, card, pos):
        e = card.entry
        menu = QMenu(self)
        if e["kind"] == "text":
            a_add = menu.addAction("⚡ 加入快速…")
        else:
            a_add = menu.addAction("⭐ 加入快速访问区")
        menu.addSeparator()
        a_del = menu.addAction("删除")
        chosen = menu.exec(card.mapToGlobal(pos))
        if chosen == a_add:
            if e["kind"] == "text":
                self.add_prompt_text(e.get("text", ""))
            else:
                src = e.get("src") or ""
                if not src and e["kind"] == "image":
                    src = self._entry_path(e.get("name", ""))
                if src and os.path.exists(src):
                    self.quick_ingest_files([src])
                else:
                    self._toast("源文件已失效")
        elif chosen == a_del:
            self.delete_entry(e)
            self._toast("已移除这条")

    def toggle_collapse(self):''',
    "methods")

# 5) 三个新类：插在 def acquire_single_instance 之前
rep('''def acquire_single_instance() -> bool:''',
    '''# ------------------------------------------------------------------ 快速指令区 UI 组件
class PromptDocCard(QFrame):
    """快速指令页文档卡：双击=复制全文；右键=改名/编辑内容/置顶/删除。"""

    def __init__(self, shelf, folder: str, info: dict):
        super().__init__(objectName="card")
        self.shelf, self.folder, self.info = shelf, folder, info
        self.setFixedHeight(50)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(
            lambda pos: shelf._prompt_doc_ctx(self, pos))

        h = QHBoxLayout(self)
        h.setContentsMargins(10, 5, 8, 5)
        h.setSpacing(8)
        if info["pinned"]:
            pin = QLabel("📌", objectName="cardMeta")
            pin.setFixedWidth(16)
            h.addWidget(pin)
        col = QVBoxLayout()
        col.setSpacing(1)
        col.setContentsMargins(0, 0, 0, 0)
        col.addWidget(QLabel("📄 " + info["name"], objectName="cardName"))
        meta = f"{info["preview"]} · {info["chars"]}字" if info["preview"] \\
            else f"{info["chars"]}字"
        col.addWidget(elided_label(meta, 380, "cardMeta"))
        h.addLayout(col, stretch=1)

    def mouseDoubleClickEvent(self, ev):
        self.shelf._prompt_copy(self.folder, self.info["name"])
        super().mouseDoubleClickEvent(ev)


class PromptCategoryDialog(QDialog):
    """「加入快速」分类选择对话框：下拉已有分类，也可输入新分类名。"""

    def __init__(self, shelf):
        super().__init__(shelf)
        self.shelf = shelf
        self.setWindowTitle("加入快速")
        self.setModal(True)
        self.setFixedSize(300, 150)
        self.setStyleSheet(shelf.app_qss)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowFlags(Qt.WindowType.Dialog
                            | Qt.WindowType.FramelessWindowHint
                            | Qt.WindowType.WindowStaysOnTopHint)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        box = QFrame(objectName="previewBox")
        root.addWidget(box)
        v = QVBoxLayout(box)
        v.setContentsMargins(14, 12, 14, 12)
        v.setSpacing(10)

        v.addWidget(QLabel("⚡ 收进快速指令", objectName="previewTitle"))
        v.addWidget(QLabel("放到哪个分类（可输入新分类名）：", objectName="cardMeta"))
        self.combo = QComboBox()
        self.combo.setEditable(True)
        folders = shelf.prompts.folders()
        if folders:
            self.combo.addItems(folders)
        v.addWidget(self.combo)

        bts = QHBoxLayout()
        bts.addStretch(1)
        ok_btn = QPushButton("收进去", objectName=None)
        ok_btn.setProperty("class", "footerBtn")
        ok_btn.setProperty("primary", True)
        ok_btn.clicked.connect(self.accept)
        bts.addWidget(ok_btn)
        cancel = QPushButton("取消")
        cancel.setProperty("class", "footerBtn")
        cancel.clicked.connect(self.reject)
        bts.addWidget(cancel)
        v.addLayout(bts)

    def selected_folder(self) -> str:
        return str(self.combo.currentText()).strip() or "默认"


class PromptEditDialog(QDialog):
    """提示词内容编辑：就地修改 MD 文档全文，保存回写磁盘。"""
    saved = pyqtSignal()

    def __init__(self, shelf, folder: str, name: str):
        super().__init__(shelf)
        self.shelf, self.folder, self.name = shelf, folder, name
        self.setWindowTitle(f"编辑：{name}")
        self.setModal(False)
        self.setFixedSize(420, 360)
        self.setStyleSheet(shelf.app_qss)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowFlags(Qt.WindowType.Dialog
                            | Qt.WindowType.FramelessWindowHint
                            | Qt.WindowType.WindowStaysOnTopHint
                            | Qt.WindowType.Tool)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        box = QFrame(objectName="previewBox")
        root.addWidget(box)
        v = QVBoxLayout(box)
        v.setContentsMargins(14, 12, 14, 12)
        v.setSpacing(8)
        v.addWidget(QLabel("📄 " + name, objectName="previewTitle"))

        self.edit = QPlainTextEdit()
        self.edit.setPlainText(shelf.prompts.read_doc(folder, name))
        v.addWidget(self.edit, stretch=1)

        bts = QHBoxLayout()
        hint = QLabel("改动保存到 _Prompts 目录的 MD 文件", objectName="cardMeta")
        bts.addWidget(hint)
        bts.addStretch(1)
        save = QPushButton("保存")
        save.setProperty("class", "footerBtn")
        save.clicked.connect(self._save)
        bts.addWidget(save)
        cancel = QPushButton("取消")
        cancel.setProperty("class", "footerBtn")
        cancel.clicked.connect(self.close)
        bts.addWidget(cancel)
        v.addLayout(bts)

    def _save(self):
        self.shelf.prompts.write_doc(self.folder, self.name, self.edit.toPlainText())
        self.shelf._toast("已保存修改")
        self.saved.emit()
        self.close()


def acquire_single_instance() -> bool:''',
    "classes")

p.write_text(src, encoding="utf-8")
print("UI-PART2 OK")

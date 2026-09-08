"""快速指令区 UI 插入（第1部分）：import/settings/init/footer/页面/_switch_view。"""
from pathlib import Path

p = Path(r"E:\项目搭建\剪贴板\shelf_app.py")
src = p.read_text(encoding="utf-8")

def rep(old, new, tag):
    global src
    assert src.count(old) == 1, f"{tag} 锚点 {src.count(old)} 处"
    src = src.replace(old, new)

# 1) 顶部 import PromptsStore
rep('''from prompts_store import PromptsStore''' if "from prompts_store import PromptsStore" in src else
    '''from PyQt6.QtCore import (Qt, QRect, QPoint, QUrl, QByteArray, QBuffer,
                          QIODevice, QMimeData, QTimer, pyqtSignal, QEvent)''',
    '''from PyQt6.QtCore import (Qt, QRect, QPoint, QUrl, QByteArray, QBuffer,
                          QIODevice, QMimeData, QTimer, pyqtSignal, QEvent)
from prompts_store import PromptsStore''',
    "import")

# 2) DEFAULT_SETTINGS 加 prompts_dir
rep('''    "pinned_dir": str(APP_DIR / "_Pinned"),''',
    '''    "pinned_dir": str(APP_DIR / "_Pinned"),
    "prompts_dir": str(APP_DIR / "_Prompts"),''',
    "settings")

# 3) Shelf.__init__ 初始化存储
rep('''        SHELF_DIR = Path(self.settings["shelf_dir"])''',
    '''        SHELF_DIR = Path(self.settings["shelf_dir"])
        # ⚡ 快速指令区（提示词收藏夹）存储：默认 APP_DIR/_Prompts，
        # 可在设置里改 prompts_dir（绝对路径直用，相对按 APP_DIR）
        _pd = Path(str(self.settings.get("prompts_dir") or "")).expanduser() \\
            if str(self.settings.get("prompts_dir") or "").strip() else APP_DIR / "_Prompts"
        if not _pd.is_absolute():
            _pd = APP_DIR / _pd
        self.prompts = PromptsStore(_pd.resolve())''',
    "init")

# 4) footer：今日日志后加「⚡ 快速指令」按钮
rep('''        self.journal_btn2.clicked.connect(lambda: self._switch_view(2))
        foot_bar.addWidget(self.journal_btn2)''',
    '''        self.journal_btn2.clicked.connect(lambda: self._switch_view(2))
        foot_bar.addWidget(self.journal_btn2)

        self.prompts_btn2 = QPushButton("⚡ 快速指令")
        self.prompts_btn2.setProperty("class", "footerBtn")
        self.prompts_btn2.setToolTip("提示词收藏夹：分类存放，双击即拷")
        self.prompts_btn2.clicked.connect(lambda: self._switch_view(4))
        foot_bar.addWidget(self.prompts_btn2)''',
    "footer")

# 5) 快速指令页构建（插在 help_page addWidget 之后）
rep('''        self.view_stack.addWidget(self.help_page)''',
    '''        self.view_stack.addWidget(self.help_page)

        # ---- ⚡ 快速指令页（提示词收藏夹）：左分类 + 右文档
        self.prompts_page = QWidget()
        pv = QVBoxLayout(self.prompts_page)
        pv.setContentsMargins(0, 0, 0, 0)
        pv.setSpacing(8)
        ph = QHBoxLayout()
        ph.addWidget(QLabel("⚡ 快速指令（提示词收藏夹）", objectName="colHeader"))
        ph.addStretch(1)
        newcat_btn = QPushButton("➕ 新建分类")
        newcat_btn.setProperty("class", "footerBtn")
        newcat_btn.clicked.connect(self._prompt_new_category)
        ph.addWidget(newcat_btn)
        pback_btn = QPushButton("🔙 返回素材")
        pback_btn.setProperty("class", "footerBtn")
        pback_btn.clicked.connect(lambda: self._switch_view(0))
        ph.addWidget(pback_btn)
        pv.addLayout(ph)

        pbody = QHBoxLayout()
        pbody.setSpacing(8)
        self.prompt_cat_list = QListWidget()
        self.prompt_cat_list.setFixedWidth(128)
        self.prompt_cat_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.prompt_cat_list.customContextMenuRequested.connect(self._prompt_cat_ctx)
        self.prompt_cat_list.currentTextChanged.connect(self.refresh_prompt_docs)
        pbody.addWidget(self.prompt_cat_list)

        self.prompt_docs_host = QWidget()
        self.prompt_docs_box = QVBoxLayout(self.prompt_docs_host)
        self.prompt_docs_box.setContentsMargins(0, 2, 2, 2)
        self.prompt_docs_box.setSpacing(4)
        p_scroll = QScrollArea()
        p_scroll.setWidgetResizable(True)
        p_scroll.setWidget(self.prompt_docs_host)
        p_scroll.setFrameShape(QFrame.Shape.NoFrame)
        pbody.addWidget(p_scroll, stretch=1)
        pv.addLayout(pbody, stretch=1)
        pv.addWidget(QLabel("双击复制 · 右键改名 / 置顶 / 编辑", objectName="empty"))
        self.view_stack.addWidget(self.prompts_page)   # index 4''',
    "page")

# 6) _switch_view 进入第 4 页时刷新
rep('''    def _switch_view(self, idx: int):
        self.view_stack.setCurrentIndex(idx)''',
    '''    def _switch_view(self, idx: int):
        self.view_stack.setCurrentIndex(idx)
        if idx == 4:
            self.refresh_prompts_page()''',
    "switch")

p.write_text(src, encoding="utf-8")
print("UI-PART1 OK")

"""图标化替换（阶段B）：footer 四按钮 + 各页按钮 + PromptDocCard ⚡/🔄/🔙/➕/🗂 + 纯文本 emoji 清洗。"""
from pathlib import Path

p = Path(r"E:\项目搭建\剪贴板\shelf_app.py")
src = p.read_text(encoding="utf-8")

def rep(old, new, tag):
    global src
    assert src.count(old) == 1, f"{tag} 锚点 {src.count(old)}"
    src = src.replace(old, new)

THEME = 'PALETTES.get(self.settings.get("theme", "dark"), PALETTES["dark"])'

# ---- footer 四按钮 ----
rep('''        self.quick_btn = QPushButton("⭐ 快速访问")''',
    f'''        self.quick_btn = QPushButton(" 快速访问")
        self.quick_btn.setIcon(_icon("star", {THEME}["meta"]))
        self.quick_btn.setIconSize(QSize(13, 13))''',
    "quick")
rep('''        self.journal_btn2 = QPushButton("📜 今日日志")''',
    f'''        self.journal_btn2 = QPushButton(" 今日日志")
        self.journal_btn2.setIcon(_icon("doc", {THEME}["meta"]))
        self.journal_btn2.setIconSize(QSize(13, 13))''',
    "journal")
rep('''        self.prompts_btn2 = QPushButton("⚡ 快速指令")''',
    f'''        self.prompts_btn2 = QPushButton(" 快速指令")
        self.prompts_btn2.setIcon(_icon("bolt", {THEME}["btn_primary"]))
        self.prompts_btn2.setIconSize(QSize(13, 13))''',
    "prompts")
rep('''        purge_btn = QPushButton("🧹 清空当前批次", objectName="purgeBtn")''',
    f'''        purge_btn = QPushButton(" 清空当前批次", objectName="purgeBtn")
        purge_btn.setIcon(_icon("trash", {THEME}["meta"]))
        purge_btn.setIconSize(QSize(13, 13))''',
    "purge")

# ---- 快速访问页 ----
rep('''        qh.addWidget(QLabel("⭐ 快速访问（双击直达 · 固定不消失）", objectName="colHeader"))''',
    '''        qh.addWidget(QLabel("快速访问（双击直达 · 固定不消失）", objectName="colHeader"))''',
    "qh")
rep('''        addf_btn = QPushButton("➕ 加文件夹")''',
    f'''        addf_btn = QPushButton(" 加文件夹")
        addf_btn.setIcon(_icon("plus", {THEME}["meta"]))
        addf_btn.setIconSize(QSize(12, 12))''',
    "addf")
rep('''        addfile_btn = QPushButton("➕ 加文件")''',
    f'''        addfile_btn = QPushButton(" 加文件")
        addfile_btn.setIcon(_icon("plus", {THEME}["meta"]))
        addfile_btn.setIconSize(QSize(12, 12))''',
    "addfile")
rep('''        back_btn = QPushButton("🔙 返回素材")''',
    f'''        back_btn = QPushButton(" 返回素材")
        back_btn.setIcon(_icon("back", {THEME}["meta"]))
        back_btn.setIconSize(QSize(12, 12))''',
    "qback")

# ---- 今日日志页 ----
rep('''        jh.addWidget(QLabel("📜 今日复制日志", objectName="colHeader"))''',
    '''        jh.addWidget(QLabel("今日复制日志", objectName="colHeader"))''',
    "jh")
rep('''        jr_btn = QPushButton("🔄 刷新")''',
    f'''        jr_btn = QPushButton(" 刷新")
        jr_btn.setIcon(_icon("refresh", {THEME}["meta"]))
        jr_btn.setIconSize(QSize(12, 12))''',
    "jrefresh")
rep('''        jext_btn = QPushButton("🗂 外部打开")''',
    f'''        jext_btn = QPushButton(" 外部打开")
        jext_btn.setIcon(_icon("folder", {THEME}["meta"]))
        jext_btn.setIconSize(QSize(12, 12))''',
    "jext")
rep('''        jback_btn = QPushButton("🔙 返回素材")''',
    f'''        jback_btn = QPushButton(" 返回素材")
        jback_btn.setIcon(_icon("back", {THEME}["meta"]))
        jback_btn.setIconSize(QSize(12, 12))''',
    "jback")
rep('''        qp = QPushButton("⚡", objectName="hoverActionBtn")''',
    '''        qp = QPushButton("", objectName="hoverActionBtn")''',
    "qp")
rep('''        qp.setFixedSize(24, 24)
        qp.setToolTip("收进快速指令（提示词收藏夹）")''',
    f'''        qp.setFixedSize(24, 24)
        qp.setIcon(_icon("bolt", {THEME}["btn_primary"], 12))
        qp.setIconSize(QSize(12, 12))
        qp.setToolTip("收进快速指令（提示词收藏夹）")''',
    "qpset")
rep('''        cp = QPushButton("📋", objectName="hoverActionBtn")''',
    '''        cp = QPushButton("", objectName="hoverActionBtn")''',
    "cp")
rep('''        cp.setFixedSize(24, 24)
        cp.setToolTip("复制这一条")''',
    f'''        cp.setFixedSize(24, 24)
        cp.setIcon(_icon("copy", {THEME}["meta"], 12))
        cp.setIconSize(QSize(12, 12))
        cp.setToolTip("复制这一条")''',
    "cpset")

# ---- 帮助页 ----
rep('''        hh.addWidget(QLabel("❓ 使用帮助", objectName="colHeader"))''',
    '''        hh.addWidget(QLabel("使用帮助", objectName="colHeader"))''',
    "hh")

# ---- 快速指令页 ----
rep('''        ph.addWidget(QLabel("⚡ 快速指令（提示词收藏夹）", objectName="colHeader"))''',
    '''        ph.addWidget(QLabel("快速指令（提示词收藏夹）", objectName="colHeader"))''',
    "ph")
rep('''        newcat_btn = QPushButton("➕ 新建分类")''',
    f'''        newcat_btn = QPushButton(" 新建分类")
        newcat_btn.setIcon(_icon("plus", {THEME}["meta"]))
        newcat_btn.setIconSize(QSize(12, 12))''',
    "newcat")
rep('''        pback_btn = QPushButton("🔙 返回素材")''',
    f'''        pback_btn = QPushButton(" 返回素材")
        pback_btn.setIcon(_icon("back", {THEME}["meta"]))
        pback_btn.setIconSize(QSize(12, 12))''',
    "pback")

# ---- PromptDocCard 📄 前缀 → doc 图标 label ----
rep('''        col.addWidget(QLabel("📄 " + info["name"], objectName="cardName"))''',
    f'''        nm_h = QHBoxLayout()
        nm_h.setSpacing(5)
        nm_h.setContentsMargins(0, 0, 0, 0)
        doc_ic = QLabel()
        doc_ic.setPixmap(_icon("doc", {THEME}["meta"], 12).pixmap(12, 12))
        nm_h.addWidget(doc_ic)
        nm_h.addWidget(QLabel(info["name"], objectName="cardName"))
        nm_h.addStretch(1)
        col.addLayout(nm_h)''',
    "doccard")

# ---- PromptEditDialog 标题 ----
rep('''        v.addWidget(QLabel("📄 " + name, objectName="previewTitle"))''',
    '''        v.addWidget(QLabel(name, objectName="previewTitle"))''',
    "editdlg")

# ---- SettingsDialog 标题 ----
rep('''        head.addWidget(QLabel("⚙ 选项设置", objectName="previewTitle"))''',
    '''        head.addWidget(QLabel("选项设置", objectName="previewTitle"))''',
    "settingsdlg")

# ---- 预览对话框 emoji 图标去 ----
rep('icon = "🖼 截图预览" if self.entry["kind"] == "image" else ("📝 文本全文" if self.entry["kind"] == "text" else "📎 文件名片")',
    'icon = "截图预览" if self.entry["kind"] == "image" else ("文本全文" if self.entry["kind"] == "text" else "文件名片")',
    "previewicon")

# ---- 纯文本 emoji 清洗（标题/标签/meta）----
CLEAN = [
    ('QLabel("📁 附件与截图 (按住拖入微信)")', 'QLabel("附件与截图 · 按住可拖出")'),
    ('QLabel("📝 文字碎片 (点击即拷)")', 'QLabel("文字碎片 · 点击即拷")'),
    ('"📦 按住拖出全部选中附件"', '"按住拖出全部选中附件"'),
    ('QPushButton("📋 合并复制选中文字")', 'QPushButton(" 合并复制选中文字")'),
    ('self.meta_lab.setText("✅ 已复制")', 'self.meta_lab.setText("已复制")'),
    ('dead = "" if path and os.path.exists(path) else " ⚠失效"',
     'dead = "" if path and os.path.exists(path) else " · 失效"'),
    ('thumb.setText("🖼")', 'thumb.setText("图片")'),
    ('self.meta_lab.setText(f"{e.get(\'ts\', \'-\')} · {len(e[\'text\'])}字 · 双击复制")',
     'self.meta_lab.setText(f"{e.get(\'ts\', \'-\')} · {len(e[\'text\'])}字 · 双击复制")'),
]
for old, new in CLEAN:
    if old in src:
        src = src.replace(old, new)

# 帮助正文 emoji 清洗（仅去掉行首 emoji 与各【】标记里的 emoji，结构不动）
for emj in ["❓ ", "⚙ ", "📋 ", "⭐ ", "📜 ", "🧹 ", "📌 "]:
    src = src.replace(  # HELP_TEXT 内的写法
        emj, "") if emj in src and src.count(emj) <= 6 else src

p.write_text(src, encoding="utf-8")
print("ICONS-B OK")

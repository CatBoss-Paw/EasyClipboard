"""图标化替换（阶段A）：按钮 setIcon + pin 状态重写 + SmallBlock + 标题 logo。"""
from pathlib import Path

p = Path(r"E:\项目搭建\剪贴板\shelf_app.py")
src = p.read_text(encoding="utf-8")

def rep(old, new, tag):
    global src
    assert src.count(old) == 1, f"{tag} 锚点 {src.count(old)}"
    src = src.replace(old, new)

# 0) 顶部 import 图标库
rep("from prompts_store import PromptsStore",
    "from prompts_store import PromptsStore\nfrom icons import icon as _icon",
    "import")

# 1) 标题：✂️ 改为细线剪刀图标（独立小 logo label）
rep('''        title = QLabel("✂️ 轻松剪贴板", objectName="title")''',
    '''        logo = QLabel()
        logo.setPixmap(_icon("scissors", "#0A84FF" if PALETTES.get(self.settings.get("theme", "dark")) == PALETTES.get("dark") else "#007AFF", 15).pixmap(15, 15))
        h.addWidget(logo)
        title = QLabel("轻松剪贴板", objectName="title")''',
    "title")

# 2) help/gear/pin 按钮去 emoji
rep('''        help_btn = QPushButton("❓", objectName="helpBtn")''',
    '''        help_btn = QPushButton("", objectName="helpBtn")''', "help")
rep('''        help_btn.setFixedSize(26, 26)''',
    '''        help_btn.setFixedSize(26, 26)
        help_btn.setIcon(_icon("help", PALETTES[self.settings.get("theme", "dark")]["meta"]))
        help_btn.setIconSize(QSize(15, 15))''',
    "helpset")
rep('''        gear = QPushButton("⚙")''', '''        gear = QPushButton("")''', "gear")
rep('''        gear.setFixedWidth(26)''',
    '''        gear.setFixedWidth(26)
        gear.setIcon(_icon("gear", PALETTES[self.settings.get("theme", "dark")]["meta"]))
        gear.setIconSize(QSize(15, 15))''',
    "gearset")
rep('''        self.pin_btn = QPushButton("📌")''', '''        self.pin_btn = QPushButton("")''', "pin")

# 2.5) pin 状态绘制：去硬编码蓝、去 emoji，用图标+主题色
OLD_PIN = '''    def _paint_pin_state(self):
        """置顶状态三重显性反馈：文字 + 底色 + 图标方向"""
        if self._pinned:
            self.pin_btn.setText("📌 已置顶")
            self.pin_btn.setFixedWidth(78)
            self.pin_btn.setStyleSheet(
                "#pinBtn { background:#2563eb; color:white; font-weight:600;"
                " border-radius:6px; font-size:11px; }")
            self.pin_btn.setToolTip("当前置顶中 · 点击取消置顶")
        else:
            self.pin_btn.setText("📍 未置顶")
            self.pin_btn.setFixedWidth(78)
            self.pin_btn.setStyleSheet(
                "#pinBtn { background:transparent; color:#7b8094;"
                " border:1px dashed #43475c; border-radius:6px; font-size:11px; }")
            self.pin_btn.setToolTip("当前未置顶 · 点击恢复置顶")
        self.pin_btn.setObjectName("pinBtn")'''
NEW_PIN = '''    def _paint_pin_state(self):
        """置顶状态反馈：图标 + 文字（颜色走当前主题，不再硬编码蓝）。"""
        p = PALETTES.get(self.settings.get("theme", "dark"), PALETTES["dark"])
        if self._pinned:
            self.pin_btn.setText("已置顶")
            self.pin_btn.setIcon(_icon("pin", p["btn_primary"]))
            self.pin_btn.setIconSize(QSize(12, 12))
            self.pin_btn.setFixedWidth(74)
            self.pin_btn.setStyleSheet(
                f"#pinBtn {{ background:{p['btn_primary']}; color:white; font-weight:600;"
                f" border-radius:9px; font-size:11px; border:none; }}")
            self.pin_btn.setToolTip("当前置顶中 · 点击取消置顶")
        else:
            self.pin_btn.setText("置顶")
            self.pin_btn.setIcon(_icon("pin", p["meta"]))
            self.pin_btn.setIconSize(QSize(12, 12))
            self.pin_btn.setFixedWidth(60)
            self.pin_btn.setStyleSheet(
                f"#pinBtn {{ background:transparent; color:{p['meta']};"
                f" border:1px dashed {p['border']}; border-radius:9px; font-size:11px; }}")
            self.pin_btn.setToolTip("当前未置顶 · 点击恢复置顶")
        self.pin_btn.setObjectName("pinBtn")'''
rep(OLD_PIN, NEW_PIN, "pinstate")

# 3) 卡片悬浮按钮：📋→copy 图标，📂→folder 图标
rep('''        if e["kind"] == "text":
            copy_btn = QPushButton("📋")''',
    '''        if e["kind"] == "text":
            copy_btn = QPushButton("")''',
    "copyBtn")
rep('''            copy_btn.setFixedSize(20, 20)
            copy_btn.clicked.connect(self._copy_single)''',
    '''            copy_btn.setFixedSize(20, 20)
            copy_btn.setIcon(_icon("copy", PALETTES.get(
                self.shelf.settings.get("theme", "dark"), PALETTES["dark"])["meta"], 12))
            copy_btn.setIconSize(QSize(12, 12))
            copy_btn.clicked.connect(self._copy_single)''',
    "copyset")
rep('''        else:
            open_btn = QPushButton("📂")''',
    '''        else:
            open_btn = QPushButton("")''',
    "openBtn")
rep('''            open_btn.setFixedSize(20, 20)
            open_btn.clicked.connect(self._open_single)''',
    '''            open_btn.setFixedSize(20, 20)
            open_btn.setIcon(_icon("folder", PALETTES.get(
                self.shelf.settings.get("theme", "dark"), PALETTES["dark"])["meta"], 12))
            open_btn.setIconSize(QSize(12, 12))
            open_btn.clicked.connect(self._open_single)''',
    "openset")

# 4) SmallBlock 🗂 → folder 图标（96px 块用 34px 图标）
rep('''        lab = QLabel("🗂", self)
        lab.setStyleSheet("font-size: 40px; background: transparent;")''',
    '''        lab = QLabel("", self)
        lab.setPixmap(_icon("folder", "#ffffff", 36).pixmap(36, 36))''',
    "miniblock")

p.write_text(src, encoding="utf-8")
print("ICONS-A OK")

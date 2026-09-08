"""UI tokens 重构：PALETTES 收敛 Apple 灰阶 + build_qss 整体重写（全站 QSS 基座）。
锚点：PALETTES dict 起点 136 行 到 build_qss 结束（QScrollArea 段落）。"""
from pathlib import Path

p = Path(r"E:\项目搭建\剪贴板\shelf_app.py")
src = p.read_text(encoding="utf-8")

START = src.index("PALETTES = {")
END_MARK = "QScrollArea, QScrollArea > QWidget > QWidget {{ background: transparent; }}\n\"\"\""
END = src.index(END_MARK) + len(END_MARK)

NEW_BLOCK = '''PALETTES = {
    # ------------------------------------------------------------ macOS 分层色板
    # 设计基调：单支系统蓝 + 分层灰；hover 只动背景明暗，不动边框颜色；
    # 圆角 12/10px 栅格；字号 13/12/10 三级。深色=macOS Dark，亮色=macOS Light。
    "dark": {
        "bg": "#1c1c1e", "bg_alpha": 222, "bg_solid": "#1c1c1e",
        "border": "#3a3a3c",
        "title": "#f5f5f7", "meta": "#98989d", "subtext": "#aeaeb2",
        "card": "#2c2c2e", "card_border": "#3a3a3c",
        "card_hover": "#363638", "card_hover_border": "#48484a",
        "btn": "#3a3a3c", "btn_hover": "#48484a", "btn_text": "#e5e5ea",
        "btn_primary": "#0A84FF", "btn_primary_hover": "#409CFF",
        "count_bg": "#3a3a3c", "count_text": "#aeaeb2",
        "empty_icon": "#48484a", "empty_title": "#98989d", "empty_hint": "#6e6e73",
        "scroll": "#48484a", "scroll_hover": "#6e6e73",
        "action_btn": "#3a3a3c", "action_btn_hover": "#48484a",
        "divider": "#38383a",
        "preview_bg": "#262628",
        "danger": "#FF453A", "danger_bg": "#4a2426",
        "input_bg": "#1c1c1e",
        "dwmdark": 1,
    },
    "light": {
        "bg": "#f5f5f7", "bg_alpha": 226, "bg_solid": "#f5f5f7",
        "border": "#d2d2d7",
        "title": "#1d1d1f", "meta": "#86868b", "subtext": "#6e6e73",
        "card": "#ffffff", "card_border": "#e8e8ed",
        "card_hover": "#f5f5f7", "card_hover_border": "#d2d2d7",
        "btn": "#e8e8ed", "btn_hover": "#dcdce0", "btn_text": "#1d1d1f",
        "btn_primary": "#007AFF", "btn_primary_hover": "#0059C8",
        "count_bg": "#e8e8ed", "count_text": "#86868b",
        "empty_icon": "#d2d2d7", "empty_title": "#86868b", "empty_hint": "#aeaeb2",
        "scroll": "#d2d2d7", "scroll_hover": "#aeaeb2",
        "action_btn": "#e8e8ed", "action_btn_hover": "#dcdce0",
        "divider": "#e8e8ed",
        "preview_bg": "#ffffff",
        "danger": "#FF3B30", "danger_bg": "#fdeceb",
        "input_bg": "#ffffff",
        "dwmdark": 0,
    },
}

def build_qss(p: dict, glass: bool) -> str:
    bg = f"rgba(28,28,30,{p['bg_alpha']})" if glass else p["bg_solid"]
    if glass and p is PALETTES["light"]:
        bg = f"rgba(245,245,247,{p['bg_alpha']})"
    accent = p["btn_primary"]
    accent_hover = p["btn_primary_hover"]

    return f"""
* {{ font-family: "PingFang SC", "Microsoft YaHei UI", -apple-system, sans-serif; outline: none; }}
#root {{ background: {bg}; border-radius: 16px; border: 1px solid {p['border']}; }}
#title {{ color: {p['title']}; font-size: 13px; font-weight: 600; background: transparent; letter-spacing: 0.2px; }}
#countPill {{ color: {p['count_text']}; background: {p['count_bg']};
             border-radius: 10px; padding: 1px 8px; font-size: 10px; font-weight: 500; }}
#toastPill {{ color: white; background: {accent};
             border-radius: 10px; padding: 1px 9px; font-size: 10px; font-weight: 600; }}

.colHeader {{ color: {p['meta']}; font-size: 11px; font-weight: 500; background: transparent; padding: 2px 4px; }}
#colDivider {{ background: {p['divider']}; width: 1px; max-width: 1px; }}

#helpBtn {{ background: transparent; color: {p['meta']}; font-weight: 500; border: none; }}
#helpBtn:hover {{ background: {p['btn_hover']}; color: {p['title']}; }}
#miniBlock {{ background: {p['card']}; border: 1px solid {p['border']}; border-radius: 24px; }}

.iconBtn {{ background: transparent; color: {p['meta']}; border: none;
           border-radius: 8px; font-size: 12px; padding: 4px 7px; }}
.iconBtn:hover {{ background: {p['btn_hover']}; color: {p['title']}; }}
.iconBtn:pressed {{ background: {p['btn']}; }}
#closeBtn:hover {{ background: {p['danger_bg']}; color: {p['danger']}; }}
#pinOn {{ color: {accent}; font-weight: 600; }}

#card {{ background: {p['card']}; border: 1px solid {p['card_border']}; border-radius: 12px; }}
#card:hover {{ background: {p['card_hover']}; }}
#cardName {{ color: {p['title']}; font-size: 12px; font-weight: 600; background: transparent; }}
#cardMeta {{ color: {p['meta']}; font-size: 10px; background: transparent; }}
#badge {{ color: #ffffff; border-radius: 8px; font-size: 9px; font-weight: 700; }}
#thumb {{ border-radius: 8px; background: {p['card_border']}; border: 1px solid {p['card_border']}; }}

QCheckBox#selBox {{ background: transparent; }}
QCheckBox#selBox::indicator {{ width: 15px; height: 15px; border-radius: 5px;
    border: 1.5px solid {p['scroll']}; background: {p['card']}; }}
QCheckBox#selBox::indicator:hover {{ border-color: {accent}; }}
QCheckBox#selBox::indicator:checked {{ background: {accent}; border-color: {accent}; }}

.hoverActionBtn {{ background: transparent; color: {p['meta']}; border: none;
                  border-radius: 6px; font-size: 11px; padding: 1px 4px; }}
.hoverActionBtn:hover {{ background: {p['action_btn_hover']}; color: {p['title']}; }}
.hoverDelBtn:hover {{ background: {p['danger_bg']}; color: {p['danger']}; }}

.colActionBtn {{ background: {p['btn']}; color: {p['btn_text']}; border: none;
                border-radius: 10px; font-size: 12px; font-weight: 500; height: 30px; }}
.colActionBtn:hover {{ background: {p['btn_hover']}; }}
#primaryColBtn {{ background: {accent}; color: white; border: none; font-weight: 600; border-radius: 10px; }}
#primaryColBtn:hover {{ background: {accent_hover}; }}

.footerBtn {{ background: {p['btn']}; color: {p['btn_text']}; border: none;
             border-radius: 10px; font-size: 12px; font-weight: 500; height: 30px; padding: 2px 12px; }}
.footerBtn:hover {{ background: {p['btn_hover']}; }}
.footerBtn[primary="true"] {{ background: {accent}; color: white; font-weight: 600; }}
.footerBtn[primary="true"]:hover {{ background: {accent_hover}; }}
#purgeBtn:hover {{ background: {p['danger_bg']}; color: {p['danger']}; }}

#emptyText {{ color: {p['empty_hint']}; font-size: 11px; background: transparent; }}
#sizeHint {{ color: {p['empty_icon']}; font-size: 10px; background: transparent; }}
#empty {{ color: {p['empty_hint']}; font-size: 11px; background: transparent; }}

#previewBox {{ background: {p['preview_bg']}; border-radius: 14px; border: 1px solid {p['border']}; }}
#previewTitle {{ color: {p['title']}; font-size: 13px; font-weight: 600; background: transparent; }}
#previewBody {{ background: transparent; color: {p['title']}; font-size: 12px; border: none; }}

/* ---- 输入控件（快速指令区/设置/对话框） ---- */
QLineEdit, QComboBox, QPlainTextEdit {{
    background: {p['input_bg']}; color: {p['title']};
    border: 1px solid {p['border']}; border-radius: 10px;
    padding: 5px 9px; font-size: 12px; selection-background-color: {accent};
}}
QLineEdit:focus, QComboBox:focus, QPlainTextEdit:focus {{ border-color: {accent}; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox QAbstractItemView {{
    background: {p['card']}; color: {p['title']};
    border: 1px solid {p['border']}; border-radius: 10px;
    selection-background-color: {p['btn_hover']}; outline: none;
}}

/* ---- 分类列表（快速指令页左侧栏） ---- */
QListWidget {{
    background: transparent; border: none; outline: none; font-size: 12px; color: {p['title']};
}}
QListWidget::item {{ padding: 7px 10px; border-radius: 8px; }}
QListWidget::item:hover {{ background: {p['btn_hover']}; }}
QListWidget::item:selected {{ background: {p['card_border']}; color: {p['title']}; font-weight: 600; }}

/* ---- 右键菜单（全站统一） ---- */
QMenu {{
    background: {p['card']}; color: {p['title']};
    border: 1px solid {p['border']}; border-radius: 10px; padding: 5px;
    font-size: 12px;
}}
QMenu::item {{ padding: 6px 22px 6px 12px; border-radius: 6px; }}
QMenu::item:selected {{ background: {p['btn_hover']}; }}
QMenu::separator {{ height: 1px; background: {p['divider']}; margin: 5px 8px; }}

QToolTip {{
    background: {p['card']}; color: {p['title']};
    border: 1px solid {p['border']}; border-radius: 8px;
    padding: 4px 8px; font-size: 11px;
}}

QScrollBar:vertical {{ background: transparent; width: 4px; margin: 0; }}
QScrollBar::handle:vertical {{ background: {p['scroll']}; border-radius: 2px; min-height: 24px; }}
QScrollBar::handle:vertical:hover {{ background: {p['scroll_hover']}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
QScrollBar:horizontal {{ background: transparent; height: 4px; margin: 0; }}
QScrollBar::handle:horizontal {{ background: {p['scroll']}; border-radius: 2px; min-width: 24px; }}
QScrollBar::handle:horizontal:hover {{ background: {p['scroll_hover']}; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0px; }}
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{ background: transparent; }}

QScrollArea, QScrollArea > QWidget > QWidget {{ background: transparent; }}
"""'''

src = src[:START] + NEW_BLOCK + src[END:]
p.write_text(src, encoding="utf-8")
print("TOKENS OK")

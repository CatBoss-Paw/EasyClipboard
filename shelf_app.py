#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Smart Staging Shelf — 微信/企微协同桌面临时中转架（PyQt6）

架构设计：
- 双轨制：
  1. 临时工作台（Staging Shelf）：左右分轨（左文件/截图，右文字），连击交付（一贴一拖），用完即清。
  2. 永久工作记忆（Daily Clipboard Journal）：每日自动锁定一篇 YYYY-MM-DD.md，纯文字自动追加，不受清空影响。
- 极致轻量：
  - 内存死守 15MB~20MB，零 WebEngine，原图不常驻内存，清空与收起时主动触发 gc.collect()。
- 快照预览：
  - 空格键（Space）轻量极速预览（图片大图/文字全文/文件信息），零额外常驻内存。
"""

import ctypes
import gc
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import (Qt, QRect, QPoint, QUrl, QByteArray, QBuffer,
                          QIODevice, QMimeData, QTimer, pyqtSignal, QEvent, QSize,
                          QFileInfo)
from prompts_store import PromptsStore
from icons import icon as _icon
from PyQt6.QtGui import (QGuiApplication, QPixmap, QPainter, QColor, QFont,
                          QDrag, QIcon, QAction, QKeySequence,
                          QShortcut, QLinearGradient, QPainterPath,
                          QImageReader, QPixmapCache, QDesktopServices, QCursor)
from PyQt6.QtWidgets import (QApplication, QWidget, QLabel, QPushButton,
                              QVBoxLayout, QHBoxLayout, QScrollArea,
                              QFrame, QSystemTrayIcon, QMenu, QMessageBox,
                              QDialog, QFileDialog, QSlider, QCheckBox,
                              QPlainTextEdit, QListWidget, QListWidgetItem,
                              QStackedWidget, QLineEdit, QSizeGrip,
                              QInputDialog, QComboBox, QFileIconProvider,
                              QTextBrowser, QSizePolicy)

_FILE_ICON_PROVIDER = None

def _get_icon_provider() -> QFileIconProvider:
    global _FILE_ICON_PROVIDER
    if _FILE_ICON_PROVIDER is None:
        _FILE_ICON_PROVIDER = QFileIconProvider()
    return _FILE_ICON_PROVIDER

# ------------------------------------------------------------------ 配置与常量
def _resolve_app_dir() -> Path:
    r"""解析程序根目录，兼容【脚本运行】与【PyInstaller 打包】两种模式。

    实测结论（PyInstaller 6.12 onedir，tests/frozen_probe.py 验证）：
        sys.executable          -> ...\EasyClipboard\轻松剪贴板.exe
        __file__                -> ...\EasyClipboard\_internal\shelf_app.py
        两者 dirname 【不相同】
    因此打包后若仍用 __file__，数据目录会被建到 _internal/ 里面：
      - 用户覆盖安装/升级时，_TempShelf 素材与 _History 日志会随之丢失
      - 看守与界面两个进程各自解析，可能指向不同目录→文件通信断裂
    frozen 时必须以 exe 本体所在目录为根。
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(os.path.dirname(os.path.abspath(__file__)))


APP_DIR = _resolve_app_dir()
SETTINGS_PATH = APP_DIR / "shelf_settings.json"
DRAFT_NAME = "draft.md"
MANIFEST_NAME = ".manifest.json"
HOTKEY = "f9"

# ------------------------------------------------------------------ 内置看护架构
# 【一体化单进程架构】软件与看护后台完全融为一体（All-in-One）。
# 剪贴板监听、图片与文件捕获、每日工作日志写入作为内部守护线程常驻。
# 彻底废除外部独立看守进程与黑框终端，开机自启直接常驻托盘，零黑框、零多开。
from clipboard_watcher import ClipboardWatcher

HELP_TEXT = """轻松剪贴板 (EasyClipboard) · 完整功能与技巧指南

一、核心架构：双轨制高效中转
  • 左右分轨：左侧为附件/截图卡片，右侧为纯文字碎片。
  • 零拷贝理念：复制大文件时仅记录路径引用，绝不重复拷贝浪费磁盘空间。
  • 内存极致轻量：无任何 WebEngine 负担；当主窗口收起或折叠为小方块时，操作系统自动回收休眠内存页，常驻物理内存仅十几 MB。

二、素材交互与交付清单（心智：一贴一拖，用完即清）
  • 单击勾选：单击卡片或图标任意位置，即可切换勾选进底栏交付清单（无需微操瞄准复选框）。
  • 双击操作：双击文字卡 = 立即复制全文；双击文件/图片卡 = 默认程序直接打开。
  • 连击交付：在微信/企微/钉钉聊天窗口中，长按底栏「拖出交付」把手，把所有勾选素材一次性整包拖拽发送。
  • 空格预览（Space）：按键盘空格键，极速快照预览原图大图、文字全文或文件详情，用完即收。
  • 清空托盘：清空当前工作台临时素材；每日工作日志与快速指令库绝对安全，不受影响。

三、⚡ 快速指令（提示词收藏夹与 Markdown 知识库）
  • 独立 MD 文档：每段提示词都是本地独立的 .md 文件，保存在 _Prompts/ 文件夹下。
  • 资源管理器直通（核心特性）：
    - 右键分类文件夹 → 选择「在资源管理器中打开」，直接打开并管理分类文件夹；
    - 右键提示词卡片 → 选择「在资源管理器中打开」，直接在文件夹中定位并高亮选中该 .md 文件；
    - 顶部「📁 打开目录」一键直达当前分类文件夹。
  • 双向实时同步：您在外部资源管理器中直接添加、重命名或编辑 .md 文件，点击顶部「🔄 刷新」按钮即可瞬间完成磁盘对账。
  • 命名约束铁律：收录与改名时严格限制文件名最多 30 个字，自动清洗特殊字符并去除标题排版符，彻底杜绝超长文件名问题。
  • 便捷收纳：
    - 在文字卡片上右键 →「加入快速…」：弹窗上方下拉直接选已有分类，下方可输入新建分类；
    - 在「今日日志」条目右侧点击「⚡」按钮，一键将历史记录收进快速指令库。
  • 就地管理：右键提示词卡片支持「编辑内容」、「改名」、「置顶」、「删除」与「在资源管理器中打开」。

四、永久工作记忆（Daily Clipboard Journal）
  • 每日自动留痕：每天所有复制的纯文字片段，自动归档为独立的 YYYY-MM-DD.md 日志文件。
  • 严格去重与单字过滤：相同内容连续复制自动过滤；2 字以下单字误触自动拦截，绝不刷屏。
  • 永久保存：日志独立存放在 _History/ 目录下，清空临时托盘绝不影响每日日志。

五、窗口形态与自由摆放
  • 最小化小方块：点击标题栏「—」按钮，主窗口折叠为 96×96 像素的彩色立体文件夹图标「🗂」。
  • 自由拖拽停放：按住小方块可拖动到屏幕任意角落；松手停放，原地点击展开，并自动记忆您摆放的位置。
  • 边缘自由缩放：主窗口四边四角均可拖拽缩放大小，右下角配有显式拖拽把手。
  • 置顶图钉：点击标题栏「置顶」按钮，窗口永远保持在最上层，避免被其他全屏软件遮挡。

六、全局快捷键
  • F9  ：全局随时呼出 / 隐藏面板（主窗口隐藏或变成小方块时，自动释放物理内存）。
  • F10 ：全局暂停 / 恢复剪贴板自动捕获（复制账号密码或私密信息前按 F10 临时静默）。
  • Esc ：快速隐藏主窗口。
  • 空格：选中卡片后空格极速预览。

七、更多设置与自启动
  • 点击右上角「⚙ 设置」图标，可自由配置深色/浅色主题、毛玻璃磨砂效果、窗口不透明度、全局热键、数据存储目录以及开机自动启动。
"""
IMG_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"}
WIN_W, WIN_H = 560, 480
HASH_LIMIT = 512 * 1024 * 1024

# 拖拽启动阈值（逻辑像素）：卡片与底栏拖出按钮必须共用同一常量。
# Qt 默认的 startDragDistance()=4px 过于敏感，快速双击时的手抖会被误判为拖拽，
# 导致「双击复制时好时坏」。历史教训：两处阈值各写一份时曾发生只改一处、
# 另一处连带复制粘贴错属性名的缺陷（见 DragOutButton.mouseMoveEvent）。
CARD_DRAG_THRESHOLD = 14
# 程序内双击自判定窗口：两次按压间隔 ≤ 此值且位移 ≤ CARD_DBLCLICK_MAX_DIST
# 才算双击。Qt 原生判定要求几乎零位移，手抖 1-2px 就失效，故改为程序内自判定。
CARD_DBLCLICK_INTERVAL = 0.45     # 秒；用户双击偏慢可上调到 0.6
CARD_DBLCLICK_MAX_DIST = 12       # 逻辑像素
# 顶栏行内提示的自动消失时长（毫秒）。零打扰原则：只占顶栏一小条，
# 不弹系统通知、不抢焦点、不阻断操作，到时自己消失。
TOAST_DURATION_MS = 2200


def trim_working_set() -> None:
    """跨代垃圾回收、清理 Qt 位图缓存，并调用 Windows 原生 EmptyWorkingSet 收缩物理内存。"""
    try:
        gc.collect()
        try:
            QPixmapCache.clear()
        except Exception:
            pass
        if sys.platform == "win32":
            from ctypes import wintypes
            k32 = ctypes.windll.kernel32
            psapi = ctypes.windll.psapi
            k32.GetCurrentProcess.restype = wintypes.HANDLE
            h_proc = k32.GetCurrentProcess()
            try:
                psapi.EmptyWorkingSet.argtypes = [wintypes.HANDLE]
                psapi.EmptyWorkingSet.restype = wintypes.BOOL
                psapi.EmptyWorkingSet(h_proc)
            except Exception:
                pass
            try:
                k32.SetProcessWorkingSetSize.argtypes = [wintypes.HANDLE, ctypes.c_size_t, ctypes.c_size_t]
                k32.SetProcessWorkingSetSize.restype = wintypes.BOOL
                c_neg = ctypes.c_size_t(-1).value
                k32.SetProcessWorkingSetSize(h_proc, c_neg, c_neg)
            except Exception:
                pass
    except Exception:
        pass


SHELF_DIR = APP_DIR / "_TempShelf"
SHELF_REAL = ""
HISTORY_DIR = APP_DIR / "_History"
PINNED_DIR = APP_DIR / "_Pinned"

DEFAULT_SETTINGS = {
    "theme": "dark",
    "opacity": 96,
    "glass": True,
    "shelf_dir": str(APP_DIR / "_TempShelf"),
    "history_dir": str(APP_DIR / "_History"),
    "pinned_dir": str(APP_DIR / "_Pinned"),
    "prompts_dir": str(APP_DIR / "_Prompts"),
    "min_text_len": 2,        # 文字最短收录长度：低于此值的碎片不入架不写日志
    "auto_clear_hours": 168,  # 素材保留策略：默认保留 7 天（168 小时）
    "hotkey": "f9",           # 全局呼出热键，设置面板可改
    "autostart": False,       # 开机自启
}

EXT_COLORS = {
    "doc": "#3b82f6", "docx": "#3b82f6", "txt": "#64748b", "md": "#64748b",
    "xls": "#22c55e", "xlsx": "#22c55e", "csv": "#22c55e",
    "ppt": "#f97316", "pptx": "#f97316",
    "pdf": "#ef4444",
    "zip": "#a855f7", "rar": "#a855f7", "7z": "#a855f7",
    "py": "#eab308", "js": "#eab308", "ts": "#eab308", "json": "#eab308",
    "mp4": "#06b6d4", "mp3": "#06b6d4", "exe": "#ec4899",
}

# ------------------------------------------------------------------ 主题调色板
PALETTES = {
    # ------------------------------------------------------------ macOS 分层色板
    # 设计基调：单支系统蓝 + 分层灰；hover 只动背景明暗，不动边框颜色；
    # 圆角 12/10px 栅格；字号 13/12/10 三级。深色=macOS Dark，亮色=macOS Light。
    "dark": {
        "bg": "#1c1c1e", "bg_alpha": 222, "bg_solid": "#1c1c1e",
        "border": "#3a3a3c",
        "title": "#f5f5f7", "meta": "#a1a1aa", "subtext": "#d4d4d8",
        "col_header": "#e2e8f0",    # 栏目标题高亮亮白
        "icon": "#e2e8f0",          # 高明度亮白灰图标（黑底下晶莹清晰）
        "card": "#2c2c2e", "card_border": "#3a3a3c",
        "card_hover": "#363638", "card_hover_border": "#48484a",
        "btn": "#3a3a3c", "btn_hover": "#48484a", "btn_text": "#e5e5ea",
        "btn_primary": "#0A84FF", "btn_primary_hover": "#409CFF",
        "count_bg": "#3a3a3c", "count_text": "#f4f4f5",
        "empty_icon": "#48484a", "empty_title": "#a1a1aa", "empty_hint": "#71717a",
        "scroll": "#48484a", "scroll_hover": "#71717a",
        "action_btn": "#3a3a3c", "action_btn_hover": "#48484a",
        "divider": "#38383a",
        "preview_bg": "#262628",
        "danger": "#FF453A", "danger_bg": "#4a2426",
        "input_bg": "#1c1c1e",
        "dwmdark": 1,
    },
    "light": {
        "bg": "#f5f5f7", "bg_alpha": 226, "bg_solid": "#f5f5f7",
        "border": "#cbd5e1",
        "title": "#0f172a", "meta": "#475569", "subtext": "#1e293b",
        "col_header": "#1e293b",    # 栏目标题深色高对比度，彻底告别发虚
        "icon": "#1e293b",          # 高对比度深石墨灰图标（浅底上极度清晰醒目）
        "card": "#ffffff", "card_border": "#cbd5e1",
        "card_hover": "#f8fafc", "card_hover_border": "#94a3b8",
        "btn": "#e2e8f0", "btn_hover": "#cbd5e1", "btn_text": "#0f172a",
        "btn_primary": "#007AFF", "btn_primary_hover": "#0059C8",
        "count_bg": "#e2e8f0", "count_text": "#0f172a", # 计数胶囊深沉清晰
        "empty_icon": "#cbd5e1", "empty_title": "#475569", "empty_hint": "#64748b",
        "scroll": "#cbd5e1", "scroll_hover": "#94a3b8",
        "action_btn": "#e2e8f0", "action_btn_hover": "#cbd5e1",
        "divider": "#cbd5e1",
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
             border-radius: 10px; padding: 1px 8px; font-size: 11px; font-weight: 600; }}
#toastPill {{ color: white; background: {accent};
             border-radius: 10px; padding: 1px 9px; font-size: 10px; font-weight: 600; }}

.colHeader {{ color: {p.get('col_header', p['meta'])}; font-size: 12px; font-weight: 600; background: transparent; padding: 2px 4px; }}
#colDivider {{ background: {p['divider']}; width: 1px; max-width: 1px; }}

#helpBtn {{
    background: rgba(239, 68, 68, 0.12);
    color: #ef4444;
    font-size: 14px;
    font-weight: 800;
    font-family: "Segoe UI", "Arial", sans-serif;
    border: 1.5px solid rgba(239, 68, 68, 0.4);
    border-radius: 12px;
    padding: 0;
    margin: 0;
}}
#helpBtn:hover {{
    background: #ef4444;
    color: #ffffff;
    border-color: #ef4444;
}}
#miniBlock {{ background: {p['card']}; border: 1px solid {p['border']}; border-radius: 12px; }}

.iconBtn {{ background: transparent; color: {p['icon']}; border: none;
           border-radius: 8px; font-size: 12px; padding: 4px 7px; }}
.iconBtn:hover {{ background: {p['btn_hover']}; color: {p['title']}; }}
.iconBtn:pressed {{ background: {p['btn']}; }}
#closeBtn:hover {{ background: {p['danger_bg']}; color: {p['danger']}; }}
#pinOn {{ color: {accent}; font-weight: 600; }}

#card {{ background: {p['card']}; border: 1px solid {p['card_border']}; border-radius: 12px; }}
#card:hover {{ background: {p['card_hover']}; }}
#cardName {{ color: {p['title']}; font-size: 12px; font-weight: 600; background: transparent; }}
#cardMeta {{ color: {p['meta']}; font-size: 11px; font-weight: 500; background: transparent; }}
#badge {{ color: #ffffff; border-radius: 8px; font-size: 9px; font-weight: 700; }}
#thumb {{ border-radius: 8px; background: {p['card_border']}; border: 1px solid {p['card_border']}; }}

QCheckBox#selBox {{ background: transparent; padding: 2px; }}
QCheckBox#selBox::indicator {{ width: 18px; height: 18px; border-radius: 6px;
    border: 1.5px solid {p['scroll']}; background: {p['card']}; }}
QCheckBox#selBox::indicator:hover {{ border-color: {accent}; }}
QCheckBox#selBox::indicator:checked {{ background: {accent}; border-color: {accent}; }}
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

.settingCard {{
    background: {p['card']};
    border: 1px solid {p['card_border']};
    border-radius: 10px;
    padding: 10px 14px;
}}
.groupTitle {{
    font-size: 13px;
    font-weight: 700;
    color: {p['title']};
}}

/* ---- 输入控件（快速指令区/设置/对话框） ---- */
QLineEdit, QPlainTextEdit {{
    background: {p['input_bg']}; color: {p['title']};
    border: 1px solid {p['border']}; border-radius: 10px;
    padding: 6px 10px; font-size: 12px; selection-background-color: {accent};
}}
QLineEdit:focus, QPlainTextEdit:focus {{ border-color: {accent}; }}

QComboBox {{
    background: {p['input_bg']}; color: {p['title']};
    border: 1px solid {p['border']}; border-radius: 10px;
    padding: 6px 30px 6px 10px; font-size: 12px;
    selection-background-color: {accent};
}}
QComboBox:focus {{ border-color: {accent}; }}
QComboBox::drop-down {{
    subcontrol-origin: padding;
    subcontrol-position: center right;
    width: 26px;
    border: none;
    background: transparent;
}}
QComboBox::down-arrow {{
    width: 0;
    height: 0;
    border-left: 5px solid transparent;
    border-right: 5px solid transparent;
    border-top: 5px solid {p['meta']};
    margin-right: 8px;
}}
QComboBox::down-arrow:hover {{
    border-top: 5px solid {accent};
}}
QComboBox QAbstractItemView {{
    background: {p['card']}; color: {p['title']};
    border: 1px solid {p['border']}; border-radius: 10px;
    selection-background-color: {p['btn_hover']};
    selection-color: {p['title']};
    padding: 4px;
    outline: none;
}}
QComboBox QAbstractItemView::item {{
    min-height: 28px;
    padding: 4px 8px;
    border-radius: 6px;
}}
QComboBox QAbstractItemView::item:hover {{
    background: {p['btn_hover']};
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
"""


# ------------------------------------------------------------------ 设置与工具函数
def load_settings() -> dict:
    s = dict(DEFAULT_SETTINGS)
    if SETTINGS_PATH.exists():
        try:
            s.update(json.loads(SETTINGS_PATH.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            pass
    s["opacity"] = max(50, min(100, int(s.get("opacity", 96))))
    if s["theme"] not in PALETTES:
        s["theme"] = "dark"
    return s


def save_settings(s: dict):
    SETTINGS_PATH.write_text(json.dumps(s, ensure_ascii=False, indent=1), encoding="utf-8")


def fmt_size(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    for unit in ("KB", "MB", "GB"):
        n /= 1024.0
        if n < 1024 or unit == "GB":
            return f"{n:.1f} {unit}"
    return f"{n:.1f} GB"


def elide(s: str, n: int = 22) -> str:
    s = s.strip().replace("\n", " ")
    return s if len(s) <= n else s[: n - 1] + "…"


class ElidedLabel(QLabel):
    """自适应宽度的动态省略标签：
    - 记录未截断的原始完整文本 _raw_text；
    - 尺寸策略设为 Expanding，最小宽度设为 30px，允许随容器自由拉伸；
    - 监听 resizeEvent，当窗口被用户横向拉大时，按实际即时宽度动态展开显示更多字符；
    - 缩窄时平滑截断并在末尾添加优雅省略号 '…'；
    - 完美兼容 setText() 动态更新（如“已复制”及恢复原文）。
    """
    def __init__(self, text: str = "", parent=None, objectName: str = ""):
        super().__init__(parent)
        if objectName:
            self.setObjectName(objectName)
        self._raw_text = str(text).replace("\r", " ").replace("\n", " ").strip()
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.setMinimumWidth(30)
        self._update_elided()

    def setText(self, text: str):
        self._raw_text = str(text).replace("\r", " ").replace("\n", " ").strip()
        self._update_elided()

    def text(self) -> str:
        return self._raw_text

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_elided()

    def _update_elided(self):
        w = self.width()
        if w > 10:
            fm = self.fontMetrics()
            elided = fm.elidedText(self._raw_text, Qt.TextElideMode.ElideRight, w)
            super().setText(elided)
        else:
            super().setText(self._raw_text)


def elided_label(text: str, width: int = 0, name: str = "") -> ElidedLabel:
    """向下兼容的便捷工厂函数，返回自适应伸缩的 ElidedLabel。"""
    return ElidedLabel(text, objectName=name)


def safe_dest(name: str) -> str:
    name = os.path.basename(name).strip()
    if not name or name in {".", ".."} or ".." in name:
        name = "unnamed"
    dest = os.path.realpath(os.path.join(SHELF_DIR, name))
    try:
        inside = os.path.commonpath([dest, SHELF_REAL]) == SHELF_REAL
    except ValueError:
        inside = False
    if not inside:
        raise ValueError(f"非法目标路径: {name}")
    return dest


def unique_dest(name: str) -> str:
    """同名冲突自动改名 name_1.ext / name_2.ext（暂存区）"""
    base, ext = os.path.splitext(os.path.basename(name))
    if not base:
        base = "unnamed"
    cand, i = f"{base}{ext}", 0
    while os.path.exists(safe_dest(cand)):
        i += 1
        cand = f"{base}_{i}{ext}"
    return safe_dest(cand)


def safe_pinned_dest(name: str) -> str:
    """快速访问区（_Pinned）的路径围栏，语义同 safe_dest"""
    name = os.path.basename(name).strip()
    if not name or name in {".", ".."} or ".." in name:
        name = "unnamed"
    pinned_real = os.path.realpath(PINNED_DIR)
    dest = os.path.realpath(os.path.join(pinned_real, name))
    try:
        inside = os.path.commonpath([dest, pinned_real]) == pinned_real
    except ValueError:
        inside = False
    if not inside:
        raise ValueError(f"非法目标路径: {name}")
    return dest


def unique_pinned_dest(name: str) -> str:
    """_Pinned 内同名冲突自动改名"""
    base, ext = os.path.splitext(os.path.basename(name))
    if not base:
        base = "unnamed"
    cand, i = f"{base}{ext}", 0
    while os.path.exists(safe_pinned_dest(cand)):
        i += 1
        cand = f"{base}_{i}{ext}"
    return safe_pinned_dest(cand)


def make_tray_icon() -> QIcon:
    ico_path = APP_DIR / "assets" / "app.ico"
    if ico_path.exists():
        return QIcon(str(ico_path))
    png_path = APP_DIR / "assets" / "app_logo_96.png"
    if png_path.exists():
        return QIcon(str(png_path))
    pm = QPixmap(64, 64)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    grad = QLinearGradient(0, 0, 64, 64)
    grad.setColorAt(0, QColor("#1e293b"))
    grad.setColorAt(1, QColor("#0f172a"))
    p.setBrush(grad)
    p.setPen(Qt.PenStyle.NoPen)
    p.drawRoundedRect(4, 4, 56, 56, 14, 14)
    p.setPen(QColor("#f59e0b"))
    p.setFont(QFont("Segoe UI Emoji", 24))
    p.drawText(pm.rect(), Qt.AlignmentFlag.AlignCenter, "📋")
    p.end()
    return QIcon(pm)


def rounded_pixmap(pm: QPixmap, radius: int = 6) -> QPixmap:
    out = QPixmap(pm.size())
    out.fill(Qt.GlobalColor.transparent)
    p = QPainter(out)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    path = QPainterPath()
    path.addRoundedRect(0, 0, pm.width(), pm.height(), radius, radius)
    p.setClipPath(path)
    p.drawPixmap(0, 0, pm)
    p.end()
    return out


def enable_acrylic(hwnd: int, dark: bool) -> bool:
    try:
        if sys.platform != "win32" or sys.getwindowsversion().build < 22621:
            return False
        dwm = ctypes.windll.dwmapi

        class MARGINS(ctypes.Structure):
            _fields_ = [("l", ctypes.c_int), ("r", ctypes.c_int),
                        ("t", ctypes.c_int), ("b", ctypes.c_int)]

        dwm.DwmExtendFrameIntoClientArea(ctypes.c_void_p(hwnd),
                                         ctypes.byref(MARGINS(-1, -1, -1, -1)))
        dark_v = ctypes.c_int(1 if dark else 0)
        dwm.DwmSetWindowAttribute(ctypes.c_void_p(hwnd), 20, ctypes.byref(dark_v), 4)
        backdrop = ctypes.c_int(3)
        hr = dwm.DwmSetWindowAttribute(ctypes.c_void_p(hwnd), 38, ctypes.byref(backdrop), 4)
        return hr == 0
    except Exception:
        return False


# ------------------------------------------------------------------ 极轻快照预览窗（零常驻内存）
# ------------------------------------------------------------------ 原生八向缩放
# 【为什么要动 Win32】用户要的是【系统原生窗口行为】：四个角 + 四条边都能拉，
# 鼠标移过去自动变成对应的缩放箭头，就像资源管理器窗口一样。
# 自己手写八个方向的 geometry 计算 + 自己管光标，既累又不像系统窗口。
# 正解是覆写 nativeEvent 处理 WM_NCHITTEST，把边缘报给 Windows，
# 由系统自己完成缩放、光标和 Aero 贴边。
#
# 【前提已实测】tests/probe_native_resize.py 证实：Qt 的 FramelessWindowHint
# 窗口默认只有 WS_POPUP（style=0x96000000），【没有 WS_THICKFRAME】，
# 而 Windows 收到 HTLEFT 也不会缩放除非窗口带可缩放边框样式。
# 实测补上 WS_THICKFRAME 后：客户区 == 窗口矩形（没凭空长出可见边框），
# 无边框外观不受影响，DWM 合成已开启 —— 所以走“补样式 + WM_NCHITTEST”。
WM_NCHITTEST = 0x0084
HTCLIENT = 1
HTLEFT, HTRIGHT, HTTOP, HTBOTTOM = 10, 11, 12, 15
HTTOPLEFT, HTTOPRIGHT = 13, 14
HTBOTTOMLEFT, HTBOTTOMRIGHT = 16, 17

GWL_STYLE = -16
WS_THICKFRAME = 0x00040000     # 可缩放边框：原生八向缩放的必要条件
WS_MAXIMIZEBOX = 0x00010000
SWP_NOSIZE, SWP_NOMOVE = 0x0001, 0x0002
SWP_NOZORDER, SWP_NOACTIVATE = 0x0004, 0x0010
SWP_FRAMECHANGED = 0x0020      # 改完样式必须带上，否则新样式不生效
SM_CXSIZEFRAME, SM_CXPADDEDBORDER = 32, 92

# 缩放边框至少多宽（逻辑像素）。4K 屏 200% 缩放时 DPR=2.0，系统度量只有
# 5+8=13 物理像素 = 6.5 逻辑像素，太窄难以命中；按 DPR 放大到至少 8 逻辑像素。
RESIZE_BORDER_MIN_LOGICAL_PX = 8


class _POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


class _MSG(ctypes.Structure):
    """Win32 MSG。字段宽度必须按 64 位定，否则 lParam 会被截断。"""
    _fields_ = [("hwnd", ctypes.c_void_p), ("message", ctypes.c_uint),
                ("wParam", ctypes.c_size_t), ("lParam", ctypes.c_ssize_t),
                ("time", ctypes.c_uint),
                ("pt_x", ctypes.c_long), ("pt_y", ctypes.c_long)]


class _RECT(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                ("right", ctypes.c_long), ("bottom", ctypes.c_long)]


if sys.platform == "win32":
    _u32 = ctypes.windll.user32
    # 【BUG-005 教训：凡是返回值可能超出 32 位的 API 必须显式声明 restype】
    # 不声明则 ctypes 默认 c_long（4 字节），而 style 位、指针、lParam 都可能
    # 是 8 字节 —— 静默截断后行为诡异且无任何报错。
    _u32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
    _u32.GetWindowLongPtrW.argtypes = [ctypes.c_void_p, ctypes.c_int]
    _u32.SetWindowLongPtrW.restype = ctypes.c_ssize_t
    _u32.SetWindowLongPtrW.argtypes = [ctypes.c_void_p, ctypes.c_int,
                                      ctypes.c_ssize_t]
    _u32.SetWindowPos.restype = ctypes.c_int
    _u32.SetWindowPos.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int,
                                  ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                  ctypes.c_uint]
    _u32.ScreenToClient.restype = ctypes.c_int
    _u32.ScreenToClient.argtypes = [ctypes.c_void_p, ctypes.POINTER(_POINT)]
    _u32.GetClientRect.restype = ctypes.c_int
    _u32.GetClientRect.argtypes = [ctypes.c_void_p, ctypes.POINTER(_RECT)]
    _u32.GetSystemMetrics.restype = ctypes.c_int
    _u32.GetSystemMetrics.argtypes = [ctypes.c_int]
else:
    _u32 = None


def _lparam_to_screen_point(lparam: int):
    """WM_NCHITTEST 的 lParam 里打包了屏幕坐标。

    必须按【有符号 16 位】解：多显示器下副屏坐标可能是负数，
    直接取低 16 位会得到 65000+ 的错误值。
    """
    v = lparam & 0xFFFFFFFFFFFFFFFF
    x = v & 0xFFFF
    y = (v >> 16) & 0xFFFF
    if x >= 0x8000:
        x -= 0x10000
    if y >= 0x8000:
        y -= 0x10000
    return x, y


def enable_native_resize(hwnd: int) -> bool:
    """给无边框窗口补上 WS_THICKFRAME，让 Windows 肯执行边缘缩放。

    已实测：补完后客户区 == 窗口矩形，不会凭空长出可见边框，
    所以无边框外观与圆角/亚克力效果都不受影响。
    """
    if sys.platform != "win32" or not hwnd:
        return False
    try:
        h = ctypes.c_void_p(hwnd)
        style = _u32.GetWindowLongPtrW(h, GWL_STYLE)
        if style & WS_THICKFRAME:
            return True                      # 已有，幂等返回
        _u32.SetWindowLongPtrW(h, GWL_STYLE, style | WS_THICKFRAME)
        # SWP_FRAMECHANGED 必须带：否则新样式写进去了但不生效
        _u32.SetWindowPos(h, None, 0, 0, 0, 0,
                          SWP_FRAMECHANGED | SWP_NOMOVE | SWP_NOSIZE |
                          SWP_NOZORDER | SWP_NOACTIVATE)
        return bool(_u32.GetWindowLongPtrW(h, GWL_STYLE) & WS_THICKFRAME)
    except Exception:                        # noqa: BLE001
        return False


def extract_preview_text(path: str, ext: str) -> tuple[str, str]:
    """尝试以零外部依赖提取常见办公文档/文本文件的正文预览。
    返回 (预览文本, 摘要说明)。
    """
    if not path or not os.path.exists(path):
        return ("原文件不存在或已移动", "失效文件")
    ext = ext.lower()

    # 1. 常见纯文本、脚本与代码
    TEXT_EXTS = {".txt", ".md", ".py", ".json", ".js", ".ts", ".html", ".htm", ".css",
                 ".xml", ".yaml", ".yml", ".ini", ".cfg", ".log", ".csv", ".bat", ".cmd",
                 ".ps1", ".sh", ".sql", ".java", ".c", ".cpp", ".h", ".go", ".rs"}
    if ext in TEXT_EXTS:
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read(10000)
            return (content, f"文本内容预览 · 读取前 {len(content)} 字符")
        except Exception as e:
            return (f"读取失败: {e}", "文本文件")

    # 2. Word 文档 (.docx)
    if ext == ".docx":
        try:
            import zipfile
            import xml.etree.ElementTree as ET
            with zipfile.ZipFile(path) as z:
                tree = ET.fromstring(z.read("word/document.xml"))
                paragraphs = []
                for p in tree.iter("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}p"):
                    text = "".join(node.text for node in p.iter() if node.text)
                    if text.strip():
                        paragraphs.append(text.strip())
                    if len(paragraphs) >= 80:
                        break
                if paragraphs:
                    return ("\n\n".join(paragraphs), f"Word 文档正文预览 · 共 {len(paragraphs)} 个段落")
        except Exception:
            pass

    # 3. PowerPoint 演示文稿 (.pptx)
    if ext == ".pptx":
        try:
            import zipfile
            import xml.etree.ElementTree as ET
            with zipfile.ZipFile(path) as z:
                slide_files = sorted([n for n in z.namelist() if n.startswith("ppt/slides/slide") and n.endswith(".xml")])
                slides = []
                for idx, sf in enumerate(slide_files[:30], 1):
                    tree = ET.fromstring(z.read(sf))
                    slide_txt = " ".join(node.text for node in tree.iter() if node.text and node.tag.endswith("}t")).strip()
                    if slide_txt:
                        slides.append(f"【第 {idx} 页幻灯片】\n{slide_txt}")
                if slides:
                    return ("\n\n".join(slides), f"PPT 幻灯片大纲预览 · 共 {len(slides)} 页")
        except Exception:
            pass

    # 4. Excel 表格 (.xlsx)
    if ext == ".xlsx":
        try:
            import zipfile
            import xml.etree.ElementTree as ET
            with zipfile.ZipFile(path) as z:
                if "xl/sharedStrings.xml" in z.namelist():
                    tree = ET.fromstring(z.read("xl/sharedStrings.xml"))
                    strings = [node.text.strip() for node in tree.iter() if node.text and node.text.strip()][:120]
                    if strings:
                        # 格式化成小表格展示
                        chunks = [strings[i:i+4] for i in range(0, len(strings), 4)]
                        table_view = "\n".join("  |  ".join(f"{col:<15}" for col in row) for row in chunks)
                        return (table_view, f"Excel 核心数据项预览 · 共 {len(strings)} 个文本单元格")
        except Exception:
            pass

    # 5. markitdown 提取兜底（如 PDF、老格式等）
    try:
        from markitdown import MarkItDown
        md = MarkItDown()
        res = md.convert(path)
        if res and res.text_content:
            trimmed = res.text_content[:6000].strip()
            if trimmed:
                return (trimmed, f"智能解析预览 · 提取前 {min(6000, len(trimmed))} 字符")
    except Exception:
        pass

    return ("", "")


class QuickPreviewPopup(QWidget):
    """
    按空格键触发的瞬时轻量快照预览（翻倍大视野）：
    - 截图大图：800x560 超大高清视界，纤毫毕现
    - 文本全文：800x540 宽敞排版，滚动通览，一键复制
    - Office 文档：Word/Excel/PPT/PDF/代码 直接提取内容大窗阅读
    - 文件夹名片：包含子项统计与直通打开
    - 随时按 Space 或 Esc 瞬关并释放内存
    """
    def __init__(self, entry: dict, parent_shelf):
        super().__init__(None, Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.WindowStaysOnTopHint
                         | Qt.WindowType.Tool)
        self.entry = entry
        self.shelf = parent_shelf
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self.setStyleSheet(parent_shelf.app_qss)
        self._build_ui()

    def _build_ui(self):
        theme = self.shelf.settings.get("theme", "dark")
        p = PALETTES.get(theme, PALETTES["dark"])
        src = self.entry.get("src", "")
        is_folder = self.entry.get("is_dir") or (src and os.path.isdir(src))

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        box = QFrame(objectName="previewBox")
        root.addWidget(box)

        v = QVBoxLayout(box)
        v.setContentsMargins(18, 14, 18, 14)
        v.setSpacing(10)

        # 头部
        head = QHBoxLayout()
        head.setSpacing(10)

        if self.entry["kind"] == "image":
            title_text = "📷 高清截图预览"
        elif self.entry["kind"] == "text":
            title_text = "📝 纯文本全文预览"
        elif is_folder:
            title_text = "📁 文件夹名片"
        else:
            ext = os.path.splitext(self.entry["name"])[1].lstrip(".").upper() or "文件"
            title_text = f"📄 {ext} 文档与极速预览"

        t_lab = QLabel(title_text, objectName="previewTitle")
        t_lab.setStyleSheet(f"font-size: 15px; font-weight: 700; color: {p['title']};")
        head.addWidget(t_lab)
        head.addStretch(1)

        # 右上角系统打开/快捷复制
        if self.entry["kind"] == "text":
            cp_btn = QPushButton("复制全文")
            cp_btn.setProperty("class", "footerBtn")
            cp_btn.setFixedHeight(24)
            cp_btn.clicked.connect(lambda: self.shelf.copy_single_entry(self.entry))
            head.addWidget(cp_btn)
        elif src and os.path.exists(src):
            open_ext = QPushButton("外部打开")
            open_ext.setProperty("class", "footerBtn")
            open_ext.setFixedHeight(24)
            open_ext.clicked.connect(lambda: self.shelf.open_entry(self.entry))
            head.addWidget(open_ext)

        close_btn = QPushButton("✕", objectName="closeBtn")
        close_btn.setProperty("class", "iconBtn")
        close_btn.setFixedSize(24, 24)
        close_btn.clicked.connect(self.close)
        head.addWidget(close_btn)
        v.addLayout(head)

        # 主体内容区域
        if self.entry["kind"] == "image":
            img_path = self.shelf._entry_path(self.entry["name"])
            lab = QLabel()
            lab.setAlignment(Qt.AlignmentFlag.AlignCenter)
            pm = QPixmap(img_path)
            meta_str = ""
            if not pm.isNull():
                # 翻倍大视野：最大缩放到 800x560
                scaled_pm = pm.scaled(800, 560, Qt.AspectRatioMode.KeepAspectRatio,
                                      Qt.TransformationMode.SmoothTransformation)
                lab.setPixmap(scaled_pm)
                target_w = max(520, min(860, scaled_pm.width() + 48))
                target_h = max(380, min(660, scaled_pm.height() + 85))
                self.resize(target_w, target_h)
                meta_str = f"原图尺寸: {pm.width()} × {pm.height()} 像素 · 文件大小: {fmt_size(self.entry.get('size', 0))}"
            else:
                lab.setText("（无法读取图片内容）")
                self.resize(520, 360)
            v.addWidget(lab, stretch=1)
            if meta_str:
                foot_meta = QLabel(f"💡 {meta_str} · 按空格键或 Esc 随时退出", objectName="cardMeta")
                foot_meta.setStyleSheet(f"color: {p['meta']}; font-size: 11px;")
                v.addWidget(foot_meta)

        elif self.entry["kind"] == "text":
            raw_text = self.entry["text"]
            te = QPlainTextEdit(raw_text)
            te.setReadOnly(True)
            te.setObjectName("previewBody")
            te.setStyleSheet(f"""
                QPlainTextEdit {{
                    background: {p['card']};
                    border: 1px solid {p['card_border']};
                    border-radius: 10px;
                    padding: 16px 18px;
                    font-size: 15px;
                    line-height: 1.8;
                    color: {p['title']};
                }}
            """)
            v.addWidget(te, stretch=1)
            char_cnt = len(raw_text)
            lines = [line for line in raw_text.splitlines() if line.strip()]
            line_cnt = len(lines) if lines else 1
            foot_meta = QLabel(f"💡 统计：{char_cnt} 字符 · {len(raw_text.splitlines())} 行 · 按空格键或 Esc 随时退出", objectName="cardMeta")
            foot_meta.setStyleSheet(f"color: {p['meta']}; font-size: 11px;")
            v.addWidget(foot_meta)

            # 智能自适应高度：短文本小巧紧凑不留大白板，长文本宽畅通透
            if line_cnt <= 2 and char_cnt < 80:
                self.resize(680, 240)
            elif line_cnt <= 4 and char_cnt < 160:
                self.resize(720, 320)
            elif line_cnt <= 8 and char_cnt < 350:
                self.resize(780, 420)
            else:
                self.resize(820, 580)

        elif is_folder:
            f_frame = QFrame()
            f_frame.setStyleSheet(f"background: {p['card']}; border: 1px solid {p['card_border']}; border-radius: 8px; padding: 14px;")
            fv = QVBoxLayout(f_frame)
            fv.setSpacing(8)

            top_h = QHBoxLayout()
            folder_ic = QLabel()
            try:
                ic = _get_icon_provider().icon(QFileIconProvider.IconType.Folder)
                folder_ic.setPixmap(ic.pixmap(48, 48))
            except Exception:
                folder_ic.setText("📁")
                folder_ic.setStyleSheet("font-size: 36px;")
            top_h.addWidget(folder_ic)

            nm_col = QVBoxLayout()
            nm_lab = QLabel(self.entry["name"])
            nm_lab.setStyleSheet(f"font-size: 16px; font-weight: 700; color: {p['title']};")
            nm_col.addWidget(nm_lab)
            nm_col.addWidget(QLabel("文件夹目录", objectName="cardMeta"))
            top_h.addLayout(nm_col, stretch=1)
            fv.addLayout(top_h)

            # 统计子项
            sub_info = "无法统计内容"
            if src and os.path.exists(src):
                try:
                    entries = os.listdir(src)
                    sub_info = f"共包含 {len(entries)} 个项目（{', '.join(entries[:6])}{'...' if len(entries) > 6 else ''}）"
                except Exception:
                    sub_info = "系统受保护目录"

            info_text = (
                f"📁 包含项目：{sub_info}\n"
                f"⏰ 捕获时间：{self.entry.get('ts', '-')}\n"
                f"📍 真实路径：{src}"
            )
            detail = QLabel(info_text)
            detail.setStyleSheet(f"color: {p['title']}; font-size: 12px; line-height: 1.6;")
            detail.setWordWrap(True)
            fv.addWidget(detail)
            v.addWidget(f_frame, stretch=1)

            btn_box = QHBoxLayout()
            open_folder_btn = QPushButton(" 在资源管理器中打开此文件夹")
            open_folder_btn.setProperty("class", "colActionBtn")
            open_folder_btn.setObjectName("primaryColBtn")
            open_folder_btn.setFixedHeight(30)
            open_folder_btn.clicked.connect(lambda: self.shelf.open_entry(self.entry))
            btn_box.addWidget(open_folder_btn)
            v.addLayout(btn_box)
            self.resize(640, 360)

        else:
            # 具体文件：尝试智能提取内容（Word / Excel / PPT / PDF / 文本代码）
            ext = os.path.splitext(self.entry["name"])[1].lower()
            preview_content, summary = extract_preview_text(src, ext)

            if preview_content:
                # 能够提取到文本内容：展示大号预览阅读器
                head_sub = QLabel(f"🔍 {summary}", objectName="cardMeta")
                head_sub.setStyleSheet(f"color: {p['meta']}; font-size: 11px;")
                v.addWidget(head_sub)

                te = QPlainTextEdit(preview_content)
                te.setReadOnly(True)
                te.setStyleSheet(f"""
                    QPlainTextEdit {{
                        background: {p['card']};
                        border: 1px solid {p['card_border']};
                        border-radius: 10px;
                        padding: 14px 16px;
                        font-size: 14px;
                        line-height: 1.7;
                        color: {p['title']};
                    }}
                """)
                v.addWidget(te, stretch=1)

                foot_h = QHBoxLayout()
                path_info = QLabel(f"源路径: {src} · 体积: {fmt_size(self.entry.get('size', 0))}")
                path_info.setStyleSheet(f"color: {p['meta']}; font-size: 11px;")
                foot_h.addWidget(path_info, stretch=1)

                op_btn = QPushButton("用默认软件打开")
                op_btn.setProperty("class", "colActionBtn")
                op_btn.setFixedHeight(28)
                op_btn.clicked.connect(lambda: self.shelf.open_entry(self.entry))
                foot_h.addWidget(op_btn)
                v.addLayout(foot_h)
                self.resize(820, 580)   # 翻倍大视野

            else:
                # 二进制文件或不可提取文件：大号名片卡
                f_frame = QFrame()
                f_frame.setStyleSheet(f"background: {p['card']}; border: 1px solid {p['card_border']}; border-radius: 8px; padding: 14px;")
                fv = QVBoxLayout(f_frame)
                fv.setSpacing(8)

                top_h = QHBoxLayout()
                file_ic = QLabel()
                if src and os.path.exists(src):
                    try:
                        fi = QFileInfo(src)
                        ic = _get_icon_provider().icon(fi)
                        file_ic.setPixmap(ic.pixmap(48, 48))
                    except Exception:
                        pass
                if not file_ic.pixmap() or file_ic.pixmap().isNull():
                    file_ic.setText("📄")
                    file_ic.setStyleSheet("font-size: 36px;")
                top_h.addWidget(file_ic)

                nm_col = QVBoxLayout()
                nm_lab = QLabel(self.entry["name"])
                nm_lab.setStyleSheet(f"font-size: 16px; font-weight: 700; color: {p['title']};")
                nm_col.addWidget(nm_lab)
                nm_col.addWidget(QLabel(f"{ext.upper().lstrip('.')} 文件 · 大小: {fmt_size(self.entry.get('size', 0))}", objectName="cardMeta"))
                top_h.addLayout(nm_col, stretch=1)
                fv.addLayout(top_h)

                info_text = (
                    f"📄 文件名：{self.entry['name']}\n"
                    f"📦 文件大小：{fmt_size(self.entry.get('size', 0))} ({self.entry.get('size', 0)} 字节)\n"
                    f"⏰ 捕获时间：{self.entry.get('ts', '-')}\n"
                    f"📍 存储路径：{src}"
                )
                detail = QLabel(info_text)
                detail.setStyleSheet(f"color: {p['title']}; font-size: 12px; line-height: 1.6;")
                detail.setWordWrap(True)
                fv.addWidget(detail)
                v.addWidget(f_frame, stretch=1)

                btn_box = QHBoxLayout()
                open_file_btn = QPushButton(" 用系统软件打开")
                open_file_btn.setProperty("class", "colActionBtn")
                open_file_btn.setObjectName("primaryColBtn")
                open_file_btn.setFixedHeight(30)
                open_file_btn.clicked.connect(lambda: self.shelf.open_entry(self.entry))
                btn_box.addWidget(open_file_btn)

                reveal_btn = QPushButton(" 在文件夹中定位")
                reveal_btn.setProperty("class", "colActionBtn")
                reveal_btn.setFixedHeight(30)
                reveal_btn.clicked.connect(lambda: self.shelf._reveal_in_explorer(src))
                btn_box.addWidget(reveal_btn)
                v.addLayout(btn_box)
                self.resize(640, 360)

        # 快捷键与自适应屏幕安全居中
        QShortcut(QKeySequence("Space"), self).activated.connect(self.close)
        QShortcut(QKeySequence("Esc"), self).activated.connect(self.close)

        screen = QGuiApplication.primaryScreen().availableGeometry()
        geo = self.shelf.geometry()
        w, h = self.width(), self.height()
        # 居中对齐，严格防止超出屏幕
        x = max(30, min(screen.right() - w - 30, geo.left() + (geo.width() - w) // 2))
        y = max(30, min(screen.bottom() - h - 30, geo.top() + (geo.height() - h) // 2))
        self.move(x, y)

    def closeEvent(self, ev):
        try:
            for child in self.findChildren(QLabel):
                child.clear()
            for child in self.findChildren(QPlainTextEdit):
                child.clear()
        except Exception:
            pass
        super().closeEvent(ev)
        trim_working_set()


# ------------------------------------------------------------------ 双栏分轨智能卡片
class ShelfCard(QFrame):
    """
    轻量卡片（用于左栏或右栏）：
    - 左栏卡片（文件/截图）：按住直接拖出，悬浮微操作（打开、删除、复制）
    - 右栏卡片（纯文本）：双击直接复制本条，悬浮微操作（复制、删除）
    - 单击获得焦点，按 Space 键调出极速预览
    """
    def __init__(self, entry: dict, shelf, is_file_col: bool):
        super().__init__(objectName="card")
        self.entry = entry
        self.shelf = shelf
        self.is_file_col = is_file_col
        self.setFixedHeight(50)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self._drag_start_pos = None
        self._last_press = None          # (monotonic秒, 逻辑坐标) 用于自判定双击
        # 右键菜单：文字卡=「加入快速/删除」；附件卡=「加入快速访问区/删除」
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(
            lambda pos: shelf._card_context_menu(self, pos))
        self._build_ui()

    def _build_ui(self):
        e = self.entry
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 5, 8, 5)
        layout.setSpacing(8)

        # 1. 勾选框
        self.check_box = QCheckBox(objectName="selBox")
        self.check_box.setChecked(bool(e.get("on", False)))
        self.check_box.toggled.connect(self._on_toggled)
        layout.addWidget(self.check_box)

        # 2. 徽标 / 缩略图（仅保留 32x32，杜绝内存常驻）
        badge_box = self._create_badge()
        layout.addWidget(badge_box)

        # 3. 核心文本
        info_col = QVBoxLayout()
        info_col.setSpacing(1)
        info_col.setContentsMargins(0, 0, 0, 0)

        w_limit = 125 if self.is_file_col else 135
        if e["kind"] == "text":
            first_line = e["text"].strip().splitlines()[0] if e["text"].strip() else "（空白文本）"
            self.title_lab = elided_label(first_line, w_limit, "cardName")
            self.meta_lab = elided_label(f"{e.get('ts', '-')} · {len(e['text'])}字 · 双击复制",
                                         w_limit, "cardMeta")
        elif e["kind"] == "image":
            self.title_lab = elided_label(e["name"], w_limit, "cardName")
            self.meta_lab = elided_label(f"{e.get('ts', '-')} · 截图 · 可直接拖出",
                                         w_limit, "cardMeta")
        else:
            self.title_lab = elided_label(e["name"], w_limit, "cardName")
            path = e.get("src", "")
            dead = "" if path and os.path.exists(path) else " · 失效"
            self.meta_lab = elided_label(f"{e.get('ts', '-')} · {fmt_size(e.get('size', 0))}{dead}",
                                         w_limit, "cardMeta")

        info_col.addWidget(self.title_lab)
        info_col.addWidget(self.meta_lab)
        layout.addLayout(info_col, stretch=1)

        # 4. 悬浮快捷工具栏
        self.hover_bar = QWidget()
        self.hover_bar.setFixedHeight(24)
        self.hover_bar.setStyleSheet("background:transparent;")
        hbar = QHBoxLayout(self.hover_bar)
        hbar.setContentsMargins(0, 0, 0, 0)
        hbar.setSpacing(2)

        if e["kind"] == "text":
            copy_btn = QPushButton("")
            copy_btn.setToolTip("复制单条文本")
            copy_btn.setProperty("class", "hoverActionBtn")
            copy_btn.setFixedSize(20, 20)
            copy_btn.setIcon(_icon("copy", PALETTES.get(
                self.shelf.settings.get("theme", "dark"), PALETTES["dark"])["meta"], 12))
            copy_btn.setIconSize(QSize(12, 12))
            copy_btn.clicked.connect(self._copy_single)
            hbar.addWidget(copy_btn)
        else:
            open_btn = QPushButton("📂")
            open_btn.setToolTip("查看/定位原文件")
            open_btn.setProperty("class", "hoverActionBtn")
            open_btn.setFixedSize(22, 22)
            open_btn.setStyleSheet("font-size: 13px; padding: 0; background: transparent; border: none;")
            open_btn.clicked.connect(self._open_single)
            hbar.addWidget(open_btn)

        del_btn = QPushButton("✕")
        del_btn.setToolTip("移除此条")
        del_btn.setProperty("class", "hoverActionBtn hoverDelBtn")
        del_btn.setFixedSize(20, 20)
        del_btn.clicked.connect(self._delete_single)
        hbar.addWidget(del_btn)

        self.hover_bar.hide()
        layout.addWidget(self.hover_bar)

    def _create_badge(self) -> QWidget:
        e = self.entry
        if e["kind"] == "text":
            raw = str(e.get("text", "")).strip()
            theme = self.shelf.settings.get("theme", "dark")
            is_dark = (theme == "dark")
            is_url = raw.startswith(("http://", "https://", "ftp://", "www."))

            badge = QLabel()
            badge.setFixedSize(32, 32)
            badge.setAlignment(Qt.AlignmentFlag.AlignCenter)

            if is_url:
                bg = "rgba(59, 130, 246, 0.18)" if is_dark else "rgba(37, 99, 235, 0.10)"
                bd = "rgba(59, 130, 246, 0.35)" if is_dark else "rgba(37, 99, 235, 0.25)"
                ic_col = "#60a5fa" if is_dark else "#2563eb"
                badge.setStyleSheet(f"background: {bg}; border: 1px solid {bd}; border-radius: 8px;")
                badge.setPixmap(_icon("link", ic_col, 16).pixmap(16, 16))
            else:
                bg = "rgba(255, 255, 255, 0.08)" if is_dark else "#eef2f6"
                bd = "rgba(255, 255, 255, 0.12)" if is_dark else "#cbd5e1"
                ic_col = "#94a3b8" if is_dark else "#475569"
                badge.setStyleSheet(f"background: {bg}; border: 1px solid {bd}; border-radius: 8px;")
                badge.setPixmap(_icon("text", ic_col, 16).pixmap(16, 16))
            return badge
        elif e["kind"] == "image":
            thumb = QLabel(objectName="thumb")
            thumb.setFixedSize(32, 32)
            thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
            try:
                img_path = self.shelf._entry_path(e["name"])
                # 内存极致防爆：采用 QImageReader 流式流式解码（64x64）
                # 原图不进内存，单图解码内存降低 99%，彻底根除 4K/2K 截图导致的显存和物理内存尖峰
                reader = QImageReader(img_path)
                reader.setAutoTransform(True)
                orig_sz = reader.size()
                if orig_sz.isValid() and not orig_sz.isEmpty():
                    scale_sz = orig_sz.scaled(64, 64, Qt.AspectRatioMode.KeepAspectRatio)
                    reader.setScaledSize(scale_sz)
                img = reader.read()
                if not img.isNull():
                    pm = QPixmap.fromImage(img)
                    thumb.setPixmap(rounded_pixmap(pm.scaled(
                        32, 32, Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation), 5))
                else:
                    thumb.setText("图片")
            except Exception:
                thumb.setText("图片")
            return thumb
        else:
            src = e.get("src", "")
            is_folder = e.get("is_dir") or (src and os.path.isdir(src))

            # 1. 文件夹：直接展示系统原生金色文件夹大图标
            if is_folder:
                thumb = QLabel(objectName="thumb")
                thumb.setFixedSize(32, 32)
                thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
                try:
                    ic = _get_icon_provider().icon(QFileIconProvider.IconType.Folder)
                    pm = ic.pixmap(32, 32)
                    if not pm.isNull():
                        thumb.setPixmap(pm)
                        return thumb
                except Exception:
                    pass
                thumb.setText("📁")
                thumb.setStyleSheet("font-size: 20px; background: transparent;")
                return thumb

            # 2. 具体文件：直接提取该文件在系统关联的真实软件图标（Word/Excel/PDF/PPT/代码等）
            if src and os.path.exists(src):
                try:
                    fi = QFileInfo(src)
                    ic = _get_icon_provider().icon(fi)
                    pm = ic.pixmap(32, 32)
                    if not pm.isNull():
                        thumb = QLabel(objectName="thumb")
                        thumb.setFixedSize(32, 32)
                        thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
                        thumb.setPixmap(pm)
                        return thumb
                except Exception:
                    pass

            # 3. 兜底降级：根据扩展名显示精致彩色徽章
            ext = os.path.splitext(e["name"])[1].lstrip(".").upper()[:4] or "FILE"
            b = QLabel(ext, objectName="badge")
            b.setFixedSize(32, 32)
            b.setAlignment(Qt.AlignmentFlag.AlignCenter)
            bg_col = EXT_COLORS.get(ext.lower(), "#64748b")
            b.setStyleSheet(f"#badge {{ background:{bg_col}; border-radius:6px; font-weight:600; font-size:10px; color:white; }}")
            return b

    def _on_toggled(self, on: bool):
        self.entry["on"] = bool(on)
        self.shelf._on_entry_selection_changed()

    def _copy_single(self):
        self.shelf.copy_single_entry(self.entry)
        self.meta_lab.setText("已复制")
        QTimer.singleShot(1200, self._restore_meta)

    def _open_single(self):
        self.shelf.open_entry(self.entry)

    def _delete_single(self):
        self.shelf.delete_entry(self.entry)

    def _restore_meta(self):
        e = self.entry
        if e["kind"] == "text":
            self.meta_lab.setText(f"{e.get('ts', '-')} · {len(e['text'])}字 · 双击复制")
        elif e["kind"] == "image":
            self.meta_lab.setText(f"{e.get('ts', '-')} · 截图 · 可直接拖出")
        else:
            path = e.get("src", "")
            dead = "" if path and os.path.exists(path) else " · 失效"
            self.meta_lab.setText(f"{e.get('ts', '-')} · {fmt_size(e.get('size', 0))}{dead}")

    # ----- 鼠标与拖拽
    def enterEvent(self, ev):
        self.hover_bar.show()
        self.shelf._hovered_entry = self.entry      # 记录当前悬停项，供 Space 预览
        super().enterEvent(ev)

    def leaveEvent(self, ev):
        self.hover_bar.hide()
        if getattr(self.shelf, "_hovered_entry", None) == self.entry:
            self.shelf._hovered_entry = None
        super().leaveEvent(ev)

    def mousePressEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton:
            self.setFocus()                             # 显式获取键盘焦点
            self._drag_start_pos = ev.position().toPoint()
            self.shelf._selected_entry = self.entry      # 供 Space 预览定位
            # 程序内双击自判定（路径 A）：Qt 原生判定要求两次按压几乎零位移，
            # 手抖超过系统双击阈值（SM_CXDOUBLECLK，约 4px）时 Qt 判不出双击，
            # 第二次按下会派发普通 MouseButtonPress 而不是 MouseButtonDblClick。
            # 这一半情况只能靠本方法自己比对上一次按压的时间与位移。
            # 另一半（零手抖、Qt 已判定为双击）由 mouseDoubleClickEvent 覆盖。
            self._maybe_double_click(ev.position().toPoint())
        super().mousePressEvent(ev)

    def mouseDoubleClickEvent(self, ev):
        # 程序内双击自判定（路径 B）：Qt 已判定为双击时走这里，
        # 此时 mousePressEvent 收不到第二次按压，必须由本方法兵底。
        if ev.button() == Qt.MouseButton.LeftButton:
            self._drag_start_pos = None    # 双击不得演变成拖拽
            self._last_press = None
            self._dbl_triggered = True
            self._activate_by_double_click()
        super().mouseDoubleClickEvent(ev)

    def _maybe_double_click(self, pos):
        """路径 A 判定：与上一次按压比时间/位移，命中则触发双击动作。"""
        now = time.monotonic()
        last = self._last_press
        if last is not None:
            dt = now - last[0]
            dist = (pos - last[1]).manhattanLength()
            if dt <= CARD_DBLCLICK_INTERVAL and dist <= CARD_DBLCLICK_MAX_DIST:
                self._last_press = None     # 消费本次双击，避免三连击重复触发
                self._drag_start_pos = None
                self._dbl_triggered = True
                self._activate_by_double_click()
                return
        self._last_press = (now, pos)

    def _activate_by_double_click(self):
        """双击动作：文本=复制本条；图片/文件=打开（产品约定）。"""
        if self.entry["kind"] == "text":
            self._copy_single()
        else:
            self._open_single()

    def mouseMoveEvent(self, ev):
        if self._drag_start_pos is not None and (ev.buttons() & Qt.MouseButton.LeftButton):
            dist = (ev.position().toPoint() - self._drag_start_pos).manhattanLength()
            if dist >= CARD_DRAG_THRESHOLD:  # 高于双击抖动幅度，确保单击不被误判为拖拽
                self._drag_start_pos = None
                self.shelf.start_card_drag(self.entry)   # 文本/图片/文件统一入口
                return
        super().mouseMoveEvent(ev)

    def mouseReleaseEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton:
            if self._drag_start_pos is not None and not getattr(self, "_dbl_triggered", False):
                # 落实产品铁律第 7 条「单击=只选中」：单击卡片/图标直接切换勾选进清单
                self.check_box.setChecked(not self.check_box.isChecked())
            self._drag_start_pos = None
            self._dbl_triggered = False
        super().mouseReleaseEvent(ev)

    def keyPressEvent(self, ev):
        if ev.key() == Qt.Key.Key_Space:
            self.shelf.show_quick_preview(self.entry)
        else:
            super().keyPressEvent(ev)


# ------------------------------------------------------------------ 按住即拖按钮
class DragOutButton(QPushButton):
    """按住并向外拖动 = 发起整包拖出；纯点击不误触（拖拽必须伴随真实拖动手势）"""
    drag_requested = pyqtSignal()

    def __init__(self, text: str, tooltip: str = ""):
        super().__init__(text)
        self.setProperty("class", "colActionBtn")
        self.setObjectName("primaryColBtn")
        self.setToolTip(tooltip)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self._press_pos = None

    def mousePressEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton:
            self._press_pos = ev.position().toPoint()
        super().mousePressEvent(ev)

    def mouseMoveEvent(self, ev):
        # 本方法早期是从 ShelfCard.mouseMoveEvent 复制粘贴而来，误引用了本类不存在的
        # self._drag_start_pos / self.shelf / self.entry → AttributeError。
        # PyQt6 中事件处理器内的 Python 异常不会被上层 try 捕获，而是走 qFatal
        # 静默杀死整个进程（无 traceback），表现为「按住底栏按钮往外拖就闪退」。
        # 本类只有 _press_pos；且按钮自身不认识 entry，只负责发出 drag_requested，
        # 由 Shelf.start_batch_drag 统一收集勾选附件后整包拖出。
        if self._press_pos is not None and (ev.buttons() & Qt.MouseButton.LeftButton):
            dist = (ev.position().toPoint() - self._press_pos).manhattanLength()
            # 阈值与卡片一致（14 逻辑像素），远高于 Qt 默认 4px，避免手抖误触发
            if dist >= CARD_DRAG_THRESHOLD:
                self._press_pos = None      # 先清标志，避免拖拽模态期间重入再次触发
                self.drag_requested.emit()
                return
        super().mouseMoveEvent(ev)

    def mouseReleaseEvent(self, ev):
        self._press_pos = None
        super().mouseReleaseEvent(ev)


# ------------------------------------------------------------------ 快速访问列表（可拖入拖出 + 完整文件操作）
class QuickList(QListWidget):
    """快速访问区的文件夹语义：
    - 拖出：按住条目拖到微信/桌面，实体文件直接外发（不删 _Pinned 原件）
    - 拖入：把任意文件/文件夹拖进列表，实体拷入 _Pinned 托管区（像拷进一个文件夹）
    - 文件操作：Ctrl+C 复制 / Ctrl+X 剪切 / Ctrl+V 粘贴 / Delete 删除（右键菜单同）"""
    def __init__(self, shelf):
        super().__init__()
        self.shelf = shelf
        self.setAcceptDrops(True)
        self.setDragEnabled(True)          # 允许触发拖出（startDrag 自定义实体外发）
        self.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self.shelf._quick_context_menu)

    def startDrag(self, actions):
        paths = [i.data(Qt.ItemDataRole.UserRole)
                 for i in self.selectedItems()
                 if i.data(Qt.ItemDataRole.UserRole)]
        paths = [p for p in paths if os.path.exists(p)]
        if not paths:
            return
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(p) for p in paths])
        drag = QDrag(self)
        drag.setMimeData(mime)
        drag.exec(Qt.DropAction.CopyAction)

    def dragEnterEvent(self, ev):
        if ev.mimeData().hasUrls():
            ev.acceptProposedAction()

    def dragMoveEvent(self, ev):
        if ev.mimeData().hasUrls():
            ev.acceptProposedAction()

    def dropEvent(self, ev):
        locals_ = [u.toLocalFile() for u in ev.mimeData().urls() if u.isLocalFile()]
        if locals_:
            self.shelf.quick_ingest_files(locals_)
        ev.acceptProposedAction()

    def keyPressEvent(self, ev):
        key = ev.key()
        mods = ev.modifiers()
        if key == Qt.Key.Key_Delete:
            self.shelf.quick_delete_selected()
        elif mods & Qt.KeyboardModifier.ControlModifier and key == Qt.Key.Key_C:
            self.shelf.quick_copy_selected(cut=False)
        elif mods & Qt.KeyboardModifier.ControlModifier and key == Qt.Key.Key_X:
            self.shelf.quick_copy_selected(cut=True)
        elif mods & Qt.KeyboardModifier.ControlModifier and key == Qt.Key.Key_V:
            self.shelf.quick_paste()
        else:
            super().keyPressEvent(ev)


# ------------------------------------------------------------------ 折叠态小方块
class SmallBlock(QFrame):
    """折叠态的圆润小方块：点一下展开完整窗口，按住拖动可改变贴放位置"""
    clicked = pyqtSignal()

    def __init__(self):
        super().__init__(objectName="miniBlock")
        # [REMOVE SYSTEM TITLEBAR] SmallBlock is a standalone top-level window;
        # by default Windows adds a system title bar (the ugly blue bar with X
        # that the user complained about). FramelessWindowHint removes it;
        # Tool keeps it off the taskbar.
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint
                            | Qt.WindowType.WindowStaysOnTopHint
                            | Qt.WindowType.Tool)
        # Translucent background so border-radius corners are truly transparent
        # (without this, the corners show the system default color)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self.setFixedSize(48, 48)   # 变为原先 1/4 面积的精致小方块（48x48）
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        lab = QLabel(self)
        lab.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lab.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        logo_path = APP_DIR / "assets" / "app_logo_96.png"
        if logo_path.exists():
            pm = QPixmap(str(logo_path))
            if not pm.isNull():
                scaled = pm.scaled(40, 40, Qt.AspectRatioMode.KeepAspectRatio,
                                   Qt.TransformationMode.SmoothTransformation)
                lab.setPixmap(rounded_pixmap(scaled, 9))
            else:
                lab.setText("🗂")
                lab.setStyleSheet("font-size: 22px; background: transparent;")
        else:
            lab.setText("🗂")
            lab.setStyleSheet("font-size: 22px; background: transparent;")

        lay = QVBoxLayout(self)
        lay.setContentsMargins(3, 3, 3, 3)
        lay.addWidget(lab)
        # 拖动状态（按下记偏移，移动超阈值才视为拖动，未拖动松开才展开）
        self._press_global = None   # 按下时的全局坐标
        self._drag_offset = None    # 按下点相对窗口左上角
        self._dragging = False

    def mousePressEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton:
            self._press_global = ev.globalPosition().toPoint()
            self._drag_offset = self._press_global - self.frameGeometry().topLeft()
            self._dragging = False
        super().mousePressEvent(ev)

    def mouseMoveEvent(self, ev):
        if (self._drag_offset is not None
                and ev.buttons() & Qt.MouseButton.LeftButton):
            gp = ev.globalPosition().toPoint()
            # 超过 6px 才算拖动，避免正常点击时微小抖动被误判
            if not self._dragging and \
                    (gp - self._press_global).manhattanLength() > 6:
                self._dragging = True
            if self._dragging:
                self.move(gp - self._drag_offset)
        super().mouseMoveEvent(ev)

    def mouseReleaseEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton:
            was_dragging = self._dragging
            self._press_global = None
            self._drag_offset = None
            self._dragging = False
            if not was_dragging:
                self.clicked.emit()   # 原地点击才展开；拖动松手只停在原地
        super().mouseReleaseEvent(ev)


# ------------------------------------------------------------------ 设置对话框（现代化分块卡片排版）
class SettingsDialog(QDialog):
    def __init__(self, shelf):
        super().__init__(shelf)
        self.shelf = shelf
        self.setWindowTitle("选项设置")
        self.setModal(False)
        self.setFixedSize(460, 640)
        self.setStyleSheet(shelf.app_qss)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint
                            | Qt.WindowType.WindowStaysOnTopHint)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        box = QFrame(objectName="previewBox")
        root.addWidget(box)

        v = QVBoxLayout(box)
        v.setContentsMargins(18, 14, 18, 14)
        v.setSpacing(10)

        # 顶栏
        head = QHBoxLayout()
        head.addWidget(QLabel("⚙ 选项设置", objectName="previewTitle"))
        head.addStretch(1)
        close_top = QPushButton("✕", objectName="closeBtn")
        close_top.setProperty("class", "iconBtn")
        close_top.setFixedSize(22, 22)
        close_top.clicked.connect(self.close)
        head.addWidget(close_top)
        v.addLayout(head)

        # 滚动区域包装（确保小屏幕不被挤压）
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")

        content_w = QWidget()
        cv = QVBoxLayout(content_w)
        cv.setContentsMargins(0, 0, 4, 0)
        cv.setSpacing(10)

        # --- 模块 1：🎨 界面外观与视觉动效 ---
        card_app = QFrame()
        card_app.setProperty("class", "settingCard")
        av = QVBoxLayout(card_app)
        av.setSpacing(8)
        av.addWidget(QLabel("🎨 界面与外观", objectName="cardName"))

        # 主题
        r1 = QHBoxLayout()
        r1.addWidget(QLabel("界面主题", objectName="cardMeta"))
        r1.addStretch(1)
        self.t_dark = QPushButton("深色", checkable=True)
        self.t_light = QPushButton("浅色", checkable=True)
        for b in (self.t_dark, self.t_light):
            b.setProperty("class", "colActionBtn")
            b.setFixedSize(56, 26)
        cur = self.shelf.settings.get("theme", "dark")
        self.t_dark.setChecked(cur == "dark")
        self.t_light.setChecked(cur == "light")
        self.t_dark.clicked.connect(lambda: self.set_theme("dark"))
        self.t_light.clicked.connect(lambda: self.set_theme("light"))
        r1.addWidget(self.t_dark)
        r1.addWidget(self.t_light)
        av.addLayout(r1)

        # 亚克力
        self.glass_cb = QCheckBox("Win11 亚克力磨砂模糊效果")
        self.glass_cb.setObjectName("cardMeta")
        self.glass_cb.setChecked(bool(self.shelf.settings.get("glass", True)))
        self.glass_cb.toggled.connect(self.set_glass)
        av.addWidget(self.glass_cb)

        # 透明度
        r3 = QVBoxLayout()
        lab = QHBoxLayout()
        lab.addWidget(QLabel("窗口不透明度", objectName="cardMeta"))
        lab.addStretch(1)
        self.op_val = QLabel(f"{self.shelf.settings.get('opacity', 96)}%", objectName="cardMeta")
        lab.addWidget(self.op_val)
        r3.addLayout(lab)
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(50, 100)
        self.slider.setValue(int(self.shelf.settings.get("opacity", 96)))
        self.slider.valueChanged.connect(self.set_opacity)
        r3.addWidget(self.slider)
        av.addLayout(r3)
        cv.addWidget(card_app)

        # --- 模块 2：📁 本地数据存储（四大存储中心） ---
        card_dir = QFrame()
        card_dir.setProperty("class", "settingCard")
        dv = QVBoxLayout(card_dir)
        dv.setSpacing(8)
        dv.addWidget(QLabel("📁 本地存储中心（四大目录，支持指定任意路径）", objectName="cardName"))

        # 1. 暂存目录
        self._make_dir_row(dv, "暂存区（临时素材中转，清空仅清理这里）",
                           self.shelf.settings.get("shelf_dir", str(SHELF_DIR)),
                           self.change_shelf_dir, "dir_lab")

        # 2. 每日日志
        self._make_dir_row(dv, "每日剪贴板日志保存目录（可指定 Obsidian 库）",
                           self.shelf.settings.get("history_dir", str(HISTORY_DIR)),
                           self.change_hist_dir, "hist_lab")

        # 3. 快速访问
        self._make_dir_row(dv, "常用托管文件区（快速访问，清空绝不涉及）",
                           self.shelf.settings.get("pinned_dir", str(PINNED_DIR)),
                           self.change_pinned_dir, "pinned_lab")

        # 4. 快速指令（提示词库）—— 补齐配置
        self._make_dir_row(dv, "⚡ 快速指令（提示词库，支持指定 Obsidian 知识库）",
                           self.shelf.settings.get("prompts_dir", str(APP_DIR / "_Prompts")),
                           self.change_prompts_dir, "prompts_lab")

        cv.addWidget(card_dir)

        # --- 模块 3：⏱️ 素材保留策略（默认保留 7 天，支持自定义天数） ---
        card_ret = QFrame()
        card_ret.setProperty("class", "settingCard")
        rv = QVBoxLayout(card_ret)
        rv.setSpacing(8)
        rv.addWidget(QLabel("⏱️ 素材保留期限（默认 7 天）", objectName="cardName"))

        r_btns = QHBoxLayout()
        self.keep_168 = QPushButton("7天(默认)", checkable=True)
        self.keep_72 = QPushButton("3天", checkable=True)
        self.keep_24 = QPushButton("24小时", checkable=True)
        self.keep_never = QPushButton("永不清除", checkable=True)
        self.keep_custom = QPushButton("自定义", checkable=True)

        for b in (self.keep_168, self.keep_72, self.keep_24, self.keep_never, self.keep_custom):
            b.setProperty("class", "colActionBtn")
            b.setFixedHeight(26)

        cur_h = int(self.shelf.settings.get("auto_clear_hours", 168) or 0)
        self.keep_168.setChecked(cur_h == 168)
        self.keep_72.setChecked(cur_h == 72)
        self.keep_24.setChecked(cur_h == 24)
        self.keep_never.setChecked(cur_h == 0)
        self.keep_custom.setChecked(cur_h not in (0, 24, 72, 168))

        self.keep_168.clicked.connect(lambda: self.set_retention(168))
        self.keep_72.clicked.connect(lambda: self.set_retention(72))
        self.keep_24.clicked.connect(lambda: self.set_retention(24))
        self.keep_never.clicked.connect(lambda: self.set_retention(0))
        self.keep_custom.clicked.connect(self._toggle_custom_retention)

        r_btns.addWidget(self.keep_168)
        r_btns.addWidget(self.keep_72)
        r_btns.addWidget(self.keep_24)
        r_btns.addWidget(self.keep_never)
        r_btns.addWidget(self.keep_custom)
        rv.addLayout(r_btns)

        # 自定义天数输入行
        self.custom_row = QWidget()
        cr_h = QHBoxLayout(self.custom_row)
        cr_h.setContentsMargins(0, 0, 0, 0)
        cr_h.setSpacing(6)
        cr_h.addWidget(QLabel("自定义保留天数：", objectName="cardMeta"))
        cur_days = max(1, cur_h // 24) if cur_h > 0 else 7
        self.custom_days_edit = QLineEdit(str(cur_days))
        self.custom_days_edit.setFixedWidth(56)
        self.custom_days_edit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cr_h.addWidget(self.custom_days_edit)
        cr_h.addWidget(QLabel("天", objectName="cardMeta"))
        apply_days = QPushButton("保存")
        apply_days.setProperty("class", "footerBtn")
        apply_days.setFixedSize(50, 24)
        apply_days.clicked.connect(self._apply_custom_days)
        cr_h.addWidget(apply_days)
        cr_h.addStretch(1)
        rv.addWidget(self.custom_row)
        self.custom_row.setVisible(cur_h not in (0, 24, 72, 168))

        hint_lab = QLabel("到期仅在下次启动时清理暂存区；每日日志与快速指令库绝对安全", objectName="cardMeta")
        hint_lab.setStyleSheet("font-size: 10px;")
        rv.addWidget(hint_lab)
        cv.addWidget(card_ret)

        # --- 模块 4：⌨️ 系统集成与全局热键 ---
        card_sys = QFrame()
        card_sys.setProperty("class", "settingCard")
        sv = QVBoxLayout(card_sys)
        sv.setSpacing(8)
        sv.addWidget(QLabel("⚙️ 系统集成与快捷键", objectName="cardName"))

        self.build_hotkey_row(sv)
        self.build_autostart_row(sv)
        cv.addWidget(card_sys)

        scroll.setWidget(content_w)
        v.addWidget(scroll, stretch=1)

        # 底部完成按钮
        foot = QHBoxLayout()
        foot.addStretch(1)
        done_btn = QPushButton("完成并生效", objectName="primaryColBtn")
        done_btn.setProperty("class", "footerBtn")
        done_btn.setFixedSize(110, 30)
        done_btn.clicked.connect(self.close)
        foot.addWidget(done_btn)
        v.addLayout(foot)

        QShortcut(QKeySequence("Esc"), self).activated.connect(self.close)

    def _make_dir_row(self, layout, title: str, path: str, on_change, attr_name: str):
        col = QVBoxLayout()
        col.setSpacing(2)
        col.addWidget(QLabel(title, objectName="cardMeta"))
        row = QHBoxLayout()
        row.setSpacing(6)
        lab = QLabel(path, objectName="cardMeta")
        lab.setStyleSheet("color: #64748b; font-size: 11px;")
        lab.setToolTip(path)
        setattr(self, attr_name, lab)
        change_btn = QPushButton("更改…")
        change_btn.setProperty("class", "footerBtn")
        change_btn.setFixedSize(54, 24)
        change_btn.clicked.connect(on_change)
        row.addWidget(lab, stretch=1)
        row.addWidget(change_btn)
        col.addLayout(row)
        layout.addLayout(col)

    def change_prompts_dir(self):
        d = QFileDialog.getExistingDirectory(
            self, "选择快速指令（提示词库）保存目录 (可指定 Obsidian 库)",
            self.shelf.settings.get("prompts_dir", str(APP_DIR / "_Prompts")))
        if d:
            new_path = os.path.realpath(d)
            self.shelf.set_setting("prompts_dir", new_path)
            self.prompts_lab.setText(new_path)
            self.prompts_lab.setToolTip(new_path)
            self.shelf.prompts = PromptsStore(Path(new_path))
            self.shelf.refresh_prompts_page()
            self.shelf._toast("快速指令库目录已更新")

    def _toggle_custom_retention(self):
        self.set_retention(-1)
        self.custom_row.setVisible(True)

    def _apply_custom_days(self):
        try:
            days = max(1, int(self.custom_days_edit.text().strip()))
        except ValueError:
            days = 7
            self.custom_days_edit.setText("7")
        hours = days * 24
        self.shelf.set_setting("auto_clear_hours", hours)
        self.shelf._toast(f"素材保留策略已设置为 {days} 天")

    def set_retention(self, hours: int):
        self.keep_168.setChecked(hours == 168)
        self.keep_72.setChecked(hours == 72)
        self.keep_24.setChecked(hours == 24)
        self.keep_never.setChecked(hours == 0)
        self.keep_custom.setChecked(hours not in (0, 24, 72, 168))
        self.custom_row.setVisible(hours not in (0, 24, 72, 168))
        if hours >= 0:
            self.shelf.set_setting("auto_clear_hours", hours)
            if hours == 0:
                self.shelf._toast("素材保留策略已设为：永不自动清除")
            else:
                self.shelf._toast(f"素材保留策略已设为：{hours // 24} 天")

    # 呼出热键（可配置）
    def build_hotkey_row(self, v):
        r8 = QHBoxLayout()
        r8.addWidget(QLabel("呼出热键", objectName="cardName"))
        r8.addStretch(1)
        self.hotkey_edit = QLineEdit(self.shelf.settings.get("hotkey", "f9"))
        self.hotkey_edit.setFixedSize(110, 24)
        self.hotkey_edit.setToolTip("如 f9 / ctrl+alt+s / ctrl+shift+space")
        r8.addWidget(self.hotkey_edit)
        apply_hk = QPushButton("应用")
        apply_hk.setProperty("class", "footerBtn")
        apply_hk.setFixedSize(54, 24)
        apply_hk.clicked.connect(self.apply_hotkey)
        r8.addWidget(apply_hk)
        v.addLayout(r8)
        v.addWidget(QLabel("改完点应用立即生效；建议避开 Ctrl+C 等常用组合",
                           objectName="cardMeta"))

    def apply_hotkey(self):
        hk = self.hotkey_edit.text().strip().lower()
        if not hk:
            return
        self.shelf.set_setting("hotkey", hk)
        self.shelf._register_hotkey()          # 重新注册即时生效
        self.shelf._toast(f"呼出热键已切换为 {hk.upper()}")

    # 开机自启
    def build_autostart_row(self, v):
        r9 = QHBoxLayout()
        self.auto_cb = QCheckBox("开机自动启动（装成 exe 后指向程序本体）")
        self.auto_cb.setObjectName("cardName")
        self.auto_cb.setChecked(self.shelf.autostart_enabled())
        self.auto_cb.toggled.connect(self.set_autostart)
        r9.addWidget(self.auto_cb)
        v.addLayout(r9)

        r_gh = QHBoxLayout()
        gh_lab = QLabel("官方主页与更新", objectName="cardName")
        r_gh.addWidget(gh_lab)
        r_gh.addStretch(1)
        gh_link = QPushButton("访问 GitHub Releases")
        gh_link.setProperty("class", "footerBtn")
        gh_link.setFixedHeight(24)
        gh_link.setCursor(Qt.CursorShape.PointingHandCursor)
        gh_link.clicked.connect(lambda: QDesktopServices.openUrl(QUrl("https://github.com/CatBoss-Paw/EasyClipboard/releases")))
        r_gh.addWidget(gh_link)
        v.addLayout(r_gh)

    def set_autostart(self, on: bool):
        self.shelf.set_autostart(bool(on))

    def set_theme(self, theme: str):
        self.t_dark.setChecked(theme == "dark")
        self.t_light.setChecked(theme == "light")
        self.shelf.set_setting("theme", theme)

    def set_glass(self, on: bool):
        self.shelf.set_setting("glass", bool(on))

    def set_opacity(self, val: int):
        self.op_val.setText(f"{val}%")
        self.shelf.set_setting("opacity", int(val))

    def change_shelf_dir(self):
        d = QFileDialog.getExistingDirectory(self, "选择暂存目录",
                                             self.shelf.settings["shelf_dir"])
        if d:
            self.shelf.set_setting("shelf_dir", os.path.realpath(d))
            self.dir_lab.setText(self.shelf.settings["shelf_dir"])
            self.dir_lab.setToolTip(self.shelf.settings["shelf_dir"])

    def change_hist_dir(self):
        d = QFileDialog.getExistingDirectory(self, "选择每日日志存放目录 (如 Obsidian 库)",
                                             self.shelf.settings.get("history_dir", str(HISTORY_DIR)))
        if d:
            self.shelf.set_setting("history_dir", os.path.realpath(d))
            self.hist_lab.setText(self.shelf.settings["history_dir"])
            self.hist_lab.setToolTip(self.shelf.settings["history_dir"])

    def change_pinned_dir(self):
        d = QFileDialog.getExistingDirectory(self, "选择常用托管文件区",
                                             self.shelf.settings.get("pinned_dir", str(PINNED_DIR)))
        if d:
            self.shelf.set_setting("pinned_dir", os.path.realpath(d))
            self.pinned_lab.setText(self.shelf.settings["pinned_dir"])
            self.pinned_lab.setToolTip(self.shelf.settings["pinned_dir"])

    def refresh_values(self):
        """重新打开设置面板时，将所有控件与当前最新配置同步"""
        cur_theme = self.shelf.settings.get("theme", "dark")
        self.t_dark.setChecked(cur_theme == "dark")
        self.t_light.setChecked(cur_theme == "light")

        self.glass_cb.setChecked(bool(self.shelf.settings.get("glass", True)))

        cur_op = int(self.shelf.settings.get("opacity", 96))
        self.slider.setValue(cur_op)
        self.op_val.setText(f"{cur_op}%")

        if hasattr(self, "dir_lab"):
            d = self.shelf.settings.get("shelf_dir", str(SHELF_DIR))
            self.dir_lab.setText(d)
            self.dir_lab.setToolTip(d)
        if hasattr(self, "hist_lab"):
            d = self.shelf.settings.get("history_dir", str(HISTORY_DIR))
            self.hist_lab.setText(d)
            self.hist_lab.setToolTip(d)
        if hasattr(self, "pinned_lab"):
            d = self.shelf.settings.get("pinned_dir", str(PINNED_DIR))
            self.pinned_lab.setText(d)
            self.pinned_lab.setToolTip(d)
        if hasattr(self, "prompts_lab"):
            d = self.shelf.settings.get("prompts_dir", str(APP_DIR / "_Prompts"))
            self.prompts_lab.setText(d)
            self.prompts_lab.setToolTip(d)

        cur_h = int(self.shelf.settings.get("auto_clear_hours", 168) or 0)
        self.keep_168.setChecked(cur_h == 168)
        self.keep_72.setChecked(cur_h == 72)
        self.keep_24.setChecked(cur_h == 24)
        self.keep_never.setChecked(cur_h == 0)
        self.keep_custom.setChecked(cur_h not in (0, 24, 72, 168))
        self.custom_row.setVisible(cur_h not in (0, 24, 72, 168))
        if cur_h not in (0, 24, 72, 168):
            cur_days = max(1, cur_h // 24) if cur_h > 0 else 7
            self.custom_days_edit.setText(str(cur_days))

        if hasattr(self, "hotkey_edit"):
            self.hotkey_edit.setText(self.shelf.settings.get("hotkey", "f9"))
        if hasattr(self, "auto_cb"):
            self.auto_cb.setChecked(self.shelf.autostart_enabled())



# ------------------------------------------------------------------ 完整功能使用帮助大弹窗
class HelpDialog(QDialog):
    """独立宽屏使用指南大窗口（740x580，支持自由缩放、现代化卡片富文本排版）"""
    def __init__(self, shelf):
        super().__init__(shelf)
        self.shelf = shelf
        self.setWindowTitle("轻松剪贴板 (EasyClipboard) · 完整功能与使用技巧指南")
        self.resize(740, 580)
        self.setMinimumSize(600, 440)
        self.setWindowIcon(make_tray_icon())
        self.setModal(False)
        self._build_ui()

    def _build_ui(self):
        theme = self.shelf.settings.get("theme", "dark")
        is_dark = (theme == "dark")
        p = PALETTES.get(theme, PALETTES["dark"])

        self.setStyleSheet(f"""
            QDialog {{ background: {p['bg_solid']}; color: {p['title']}; }}
            QTextBrowser {{
                background: transparent;
                border: none;
                color: {p['title']};
                selection-background-color: {p['btn_primary']};
            }}
            #helpHeader {{
                background: {p['card']};
                border-bottom: 1px solid {p['border']};
                padding: 10px 18px;
            }}
            #helpFooter {{
                background: {p['card']};
                border-top: 1px solid {p['border']};
                padding: 10px 18px;
            }}
            #primaryColBtn {{
                background: {p['btn_primary']};
                color: #ffffff;
                font-weight: 600;
                border-radius: 8px;
                padding: 6px 16px;
                border: none;
            }}
            #primaryColBtn:hover {{ background: {p['btn_primary_hover']}; }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 顶部 Header
        header = QFrame(objectName="helpHeader")
        hh = QHBoxLayout(header)
        hh.setContentsMargins(14, 10, 14, 10)
        hh.setSpacing(12)

        # Logo
        logo_lab = QLabel()
        logo_lab.setFixedSize(36, 36)
        logo_path = APP_DIR / "assets" / "app_logo_96.png"
        if logo_path.exists():
            pm = QPixmap(str(logo_path))
            if not pm.isNull():
                scaled = pm.scaled(36, 36, Qt.AspectRatioMode.KeepAspectRatio,
                                   Qt.TransformationMode.SmoothTransformation)
                logo_lab.setPixmap(rounded_pixmap(scaled, 8))
        hh.addWidget(logo_lab)

        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        h_title = QLabel("轻松剪贴板 (EasyClipboard) · 核心技巧与使用说明")
        h_title.setStyleSheet(f"font-size: 15px; font-weight: 700; color: {p['title']};")
        h_sub = QLabel("双轨极速中转 · 永久剪贴记忆 · 快速指令库 · 极度轻量")
        h_sub.setStyleSheet(f"font-size: 11px; color: {p['meta']};")
        title_box.addWidget(h_title)
        title_box.addWidget(h_sub)
        hh.addLayout(title_box, stretch=1)

        gh_btn = QPushButton("⭐ GitHub 仓库 & 检查更新")
        gh_btn.setToolTip("点击在浏览器中打开官方 GitHub Releases 下载最新版本")
        gh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        gh_btn.setFixedHeight(28)
        gh_btn.setStyleSheet(f"""
            QPushButton {{
                background: {p['btn_primary']};
                color: #ffffff;
                font-size: 11px;
                font-weight: 600;
                border-radius: 6px;
                padding: 0 12px;
                border: none;
            }}
            QPushButton:hover {{
                background: {p['btn_primary_hover']};
            }}
        """)
        gh_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl("https://github.com/CatBoss-Paw/EasyClipboard/releases")))
        hh.addWidget(gh_btn)

        close_top = QPushButton("✕")
        close_top.setFixedSize(26, 26)
        close_top.setStyleSheet(f"""
            QPushButton {{ background: transparent; color: {p['meta']}; font-size: 13px; border: none; border-radius: 6px; }}
            QPushButton:hover {{ background: {p['danger_bg']}; color: {p['danger']}; }}
        """)
        close_top.clicked.connect(self.close)
        hh.addWidget(close_top)
        layout.addWidget(header)

        # 主体富文本展示区
        self.browser = QTextBrowser()
        self.browser.setOpenExternalLinks(True)
        self.browser.setHtml(self._render_html(is_dark, p))
        layout.addWidget(self.browser, stretch=1)

        # 底部操作栏
        footer = QFrame(objectName="helpFooter")
        fh = QHBoxLayout(footer)
        fh.setContentsMargins(18, 10, 18, 10)
        hint = QLabel("💡 提示：窗口支持鼠标边缘自由缩放，随时按 Esc 键即可快速关闭")
        hint.setStyleSheet(f"color: {p['meta']}; font-size: 11px;")
        fh.addWidget(hint)
        fh.addStretch(1)

        ok_btn = QPushButton("我知道了，开始使用", objectName="primaryColBtn")
        ok_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        ok_btn.clicked.connect(self.close)
        fh.addWidget(ok_btn)
        layout.addWidget(footer)

        QShortcut(QKeySequence("Esc"), self).activated.connect(self.close)

    def _render_html(self, is_dark: bool, p: dict) -> str:
        bg_card = "#27272a" if is_dark else "#ffffff"
        bd_card = "#3f3f46" if is_dark else "#e2e8f0"
        title_color = "#f4f4f5" if is_dark else "#0f172a"
        text_color = "#d4d4d8" if is_dark else "#334155"
        sec_title = "#60a5fa" if is_dark else "#0284c7"
        kbd_bg = "#333338" if is_dark else "#f1f5f9"
        kbd_bd = "#52525b" if is_dark else "#cbd5e1"
        kbd_txt = "#f5f5f7" if is_dark else "#0f172a"

        return f'''
        <html>
        <head>
        <style>
            body {{
                font-family: "PingFang SC", "Microsoft YaHei UI", -apple-system, sans-serif;
                margin: 18px 22px;
                color: {text_color};
                font-size: 13px;
                line-height: 1.65;
            }}
            .card {{
                background: {bg_card};
                border: 1px solid {bd_card};
                border-radius: 10px;
                padding: 14px 18px;
                margin-bottom: 14px;
            }}
            h2 {{
                color: {sec_title};
                font-size: 14px;
                font-weight: 700;
                margin-top: 0;
                margin-bottom: 8px;
                padding-bottom: 4px;
                border-bottom: 1px dashed {bd_card};
            }}
            ul {{ margin: 4px 0 6px 0; padding-left: 20px; }}
            li {{ margin-bottom: 6px; }}
            b {{ color: {title_color}; }}
            kbd {{
                background: {kbd_bg};
                border: 1px solid {kbd_bd};
                border-bottom: 2px solid {kbd_bd};
                border-radius: 4px;
                color: {kbd_txt};
                display: inline-block;
                font-family: Consolas, monospace;
                font-size: 11px;
                font-weight: 600;
                padding: 1px 6px;
                margin: 0 2px;
            }}
            .table-box {{
                width: 100%;
                border-collapse: collapse;
                margin-top: 6px;
            }}
            .table-box th, .table-box td {{
                border: 1px solid {bd_card};
                padding: 6px 12px;
                text-align: left;
                font-size: 12px;
            }}
            .table-box th {{
                background: rgba(0,0,0,0.05);
                color: {title_color};
                font-weight: 600;
            }}
        </style>
        </head>
        <body>

        <div style="background: rgba(59, 130, 246, 0.12); border: 1px solid rgba(59, 130, 246, 0.35); border-radius: 10px; padding: 12px 16px; margin-bottom: 14px;">
            <b style="color: {sec_title}; font-size: 14px;">🌐 官方开源主页与最新版本下载</b><br/>
            <div style="margin-top: 5px; font-size: 12px; color: {text_color}; line-height: 1.65;">
                本软件 100% 离线隐私运行。获取最新功能更新、查看 Release 发行版或提交 Issue 反馈，请访问官方 GitHub：<br/>
                <a href="https://github.com/CatBoss-Paw/EasyClipboard/releases" style="color: {sec_title}; font-weight: 700; text-decoration: underline;">👉 前往 GitHub Releases 检查并下载最新版本</a>
                <span style="color: {text_color}; margin-left: 8px;">(https://github.com/CatBoss-Paw/EasyClipboard)</span>
            </div>
        </div>

        <div class="card">
            <h2>🚀 一、核心架构：双轨分轨与极致轻量</h2>
            <ul>
                <li><b>左栏（附件与截图）</b>：自动收录复制的本地文件、微信/企微接收文件与系统截图，大文件采用<b>零拷贝</b>引用，绝不重复占用磁盘。</li>
                <li><b>右栏（文字碎片）</b>：纯文字片段自动归入，智能识别 URL 链接 🔗，双击直接复制全文。</li>
                <li><b>物理内存极致克制</b>：主面板隐藏或折叠为小方块时，自动触发 Windows 工作集深度修剪，物理内存狂降至 <b>4.16MB</b>，看守进程仅 <b>28MB</b>！</li>
            </ul>
        </div>

        <div class="card">
            <h2>🖱️ 二、键鼠高效交互（一贴一拖，用完即清）</h2>
            <ul>
                <li><b>单击卡片任意位置</b>：直接勾选进底栏待交付清单，免去微操瞄准复选框。</li>
                <li><b>双击卡片</b>：文字卡 = <b>立即复制全文</b>；附件卡 = <b>调用系统关联程序极速打开</b>。</li>
                <li><b>空格键极速预览 (<kbd>Space</kbd>)</b>：鼠标悬停或单击选中任意卡片，按键盘空格键瞬时调出<b>高清大图/全文长文/文件详情</b>浮窗，再按空格即收！</li>
                <li><b>整包外发交付</b>：在微信、企微、钉钉等聊天窗口中，长按底栏<b>「按住拖出全部选中附件」</b>，所有选中文件一次性批量拖入松手发送。</li>
                <li><b>清空批次</b>：点击底部红色垃圾桶，瞬间重置工作台临时素材（每日工作日志与快速指令库受永久保护，绝不受影响）。</li>
            </ul>
        </div>

        <div class="card">
            <h2>⚡ 三、快速指令（提示词收藏夹与 Markdown 知识库）</h2>
            <ul>
                <li><b>独立本地 Markdown 存储</b>：每段提示词都是本地独立的 <code>.md</code> 文件，永不绑定私有格式。</li>
                <li><b>资源管理器双向秒级直通</b>：
                    <ul>
                        <li>点击顶部<b>「📁 打开目录」</b>，直接在资源管理器中管理提示词分类文件夹；</li>
                        <li>在分类或提示词卡片上<b>右键 →「在资源管理器中打开」</b>，自动定位高亮该 <code>.md</code>；</li>
                        <li>外部直接增删改文件，回到软件点击<b>「🔄 刷新」</b>即可瞬间完成磁盘对账同步！</li>
                    </ul>
                </li>
                <li><b>快速收纳</b>：在文字卡片上右键 → 选择<b>「加入快速…」</b>，或在「今日日志」右侧点击 <b>⚡</b> 按钮，一键归类收藏。</li>
            </ul>
        </div>

        <div class="card">
            <h2>📅 四、永久工作记忆（Daily Clipboard Journal）</h2>
            <ul>
                <li><b>每日自动留痕</b>：每天复制的所有纯文字片段，自动按天归档至 <code>_History/YYYY-MM-DD.md</code>，永久保存。</li>
                <li><b>智能去重过滤</b>：相同内容连续复制自动过滤；2 字以下误触拦截，绝不刷屏。</li>
                <li><b>应用内查看与外部编辑</b>：点击底部<b>「今日日志」</b>在面板内直接翻阅，也可点击<b>「外部打开」</b>用 Obsidian 或外部编辑器编辑。</li>
            </ul>
        </div>

        <div class="card">
            <h2>⌨️ 五、全局快捷键速查表</h2>
            <table class="table-box">
                <tr><th>快捷键</th><th>触发动作</th><th>适用场景与说明</th></tr>
                <tr><td><kbd>Alt + V</kbd> 或 <kbd>F9</kbd></td><td><b>呼出 / 隐藏主面板</b></td><td>全局随时唤起；隐藏或收起时操作系统自动释放内存</td></tr>
                <tr><td><kbd>F10</kbd></td><td><b>暂停 / 恢复剪贴板捕获</b></td><td>复制账号密码或私密数据前按 F10 临时静默</td></tr>
                <tr><td><kbd>Space (空格)</kbd></td><td><b>极速快照预览</b></td><td>选中或悬停卡片后按空格瞬开大图或长文，用完即关</td></tr>
                <tr><td><kbd>Esc</kbd></td><td><b>快速关闭当前窗口</b></td><td>帮助窗口、预览弹窗、主窗口随时秒退</td></tr>
            </table>
        </div>

        <div class="card">
            <h2>🎨 六、窗口形态与个性化定制</h2>
            <ul>
                <li><b>折叠小方块挂件（标题栏「—」）</b>：主窗口收缩为 <b>48×48</b> 像素的高清微型挂件，可按住自由拖拽停靠在屏幕边缘，原地点击秒级展开。</li>
                <li><b>自由边缘拉伸</b>：主窗口四边四角与右下角把手均可自由缩放，文字自适应展开，告别留白浪费。</li>
                <li><b>个性化设置（标题栏「⚙」）</b>：支持深色/浅色主题、毛玻璃亚克力效果、透明度滑块与开机自启动。</li>
            </ul>
        </div>

        </body>
        </html>
        '''


# ------------------------------------------------------------------ 主窗口（左右分轨）
class Shelf(QWidget):
    # 注：此处原有 hotkey_pressed = pyqtSignal()，已删除。
    # 它既不 emit 也不 connect（tests/audit_wiring.py 查出的唯一死信号）。
    # 根因：双进程架构定稿后 F9/F10 全局热键由看守进程（watchdog.pyw）持有，
    # 界面进程改为轮询 .show_sig 信号文件（见 _poll_backend），该信号成为残留。
    # 保留死信号会误导后续开发者以为“界面侧还有热键通路”。

    def __init__(self):
        super().__init__()
        global SHELF_DIR, SHELF_REAL, HISTORY_DIR, PINNED_DIR
        self.settings = load_settings()
        SHELF_DIR = Path(self.settings["shelf_dir"])
        # ⚡ 快速指令区（提示词收藏夹）存储：默认 APP_DIR/_Prompts，
        # 可在设置里改 prompts_dir（绝对路径直用，相对按 APP_DIR）
        _pd = Path(str(self.settings.get("prompts_dir") or "")).expanduser() \
            if str(self.settings.get("prompts_dir") or "").strip() else APP_DIR / "_Prompts"
        if not _pd.is_absolute():
            _pd = APP_DIR / _pd
        self.prompts = PromptsStore(_pd.resolve())
        SHELF_DIR.mkdir(parents=True, exist_ok=True)
        SHELF_REAL = os.path.realpath(SHELF_DIR)

        HISTORY_DIR = Path(self.settings.get("history_dir", str(APP_DIR / "_History")))
        HISTORY_DIR.mkdir(parents=True, exist_ok=True)

        PINNED_DIR = Path(self.settings.get("pinned_dir", str(APP_DIR / "_Pinned")))
        PINNED_DIR.mkdir(parents=True, exist_ok=True)

        self._pinned = True
        self._collapsed = False
        self._paused = False            # 暂停捕获开关（F10 / 托盘菜单）
        self._drag_active = False       # OLE 拖拽模态循环进行中（期间挂起重入操作）
        self._pending_clip = False      # 拖拽期间积累的剪贴板事件
        self._ignore_hash = ""
        self._suppress_until = 0
        self._suppress_sig = None
        self._last_text = ""
        self._last_img_hash = ""
        self._settings_dlg = None
        self._preview_dlg = None
        self._glass_ok = False
        self.entries = []

        self.app_qss = build_qss(PALETTES[self.settings["theme"]],
                                 bool(self.settings.get("glass")))

        self.setWindowTitle("轻松剪贴板")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint
                            | Qt.WindowType.WindowStaysOnTopHint
                            | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAcceptDrops(True)
        # 【必须开启，否则光标反馈不生效】
        # 不开 MouseTracking 时，鼠标不按下就收不到 mouseMoveEvent，
        # 于是 mouseMoveEvent 里的 setCursor 永远不执行 —— 用户把鼠标
        # 移到边缘，光标不会变成缩放箭头，看不到任何提示，自然以为
        # “拉伸没实现”。
        self.setMouseTracking(True)
        self.setMinimumSize(320, 240)      # 允许四角四边缩放，只设下限
        self.resize(WIN_W, WIN_H)
        self.setStyleSheet(self.app_qss)

        self._load_manifest()
        self._build_ui()
        self._build_tray()
        self._register_pause_hotkey()
        self._register_hotkey()
        self._paint_pin_state()
        # 【核心内置看护】初始化并启动内置剪贴板后台看护守护线程
        self.watcher = ClipboardWatcher(
            shelf_dir=SHELF_DIR,
            history_dir=HISTORY_DIR,
            min_text_len=int(self.settings.get("min_text_len", 2)),
            parent=self
        )
        self.watcher.entry_captured.connect(self._on_item_captured)
        self.watcher.pause_state_changed.connect(self._on_watcher_pause_changed)
        self.watcher.start()

        self._commit()
        self._place_top_right()


        # 轮询：manifest 变化 → 刷新；.show_sig → F9 呼出/隐藏；.paused → 状态同步
        self._manifest_mtime = 0
        # 启动时清掉残留信号，防止旧信号让刚启动的窗口立刻被隐藏
        try:
            (SHELF_DIR / ".show_sig").unlink(missing_ok=True)
        except OSError:
            pass
        poll = QTimer(self)
        poll.setInterval(500)
        poll.timeout.connect(self._poll_backend)
        poll.start()

        # 内存自愈守护：空闲与后台工作集修剪（每 30 秒自检）
        # 当窗口处于折叠态、隐藏态或连续无交互时，自动清空缓存并归还闲置物理页
        self._idle_ticks = 0
        self._mem_timer = QTimer(self)
        self._mem_timer.setInterval(30000)
        self._mem_timer.timeout.connect(self._on_idle_mem_trim)
        self._mem_timer.start()

        # 缩放光标状态：边缘热区常被各种子控件覆盖（滚动区/按钮/信息等），
        # 它们自带的光标会盖住父窗口的光标 —— 这就是“缩放能用但图标不变”
        # 的根因。修复：全局事件过滤器直接对【鼠标命中的那个控件】设/恢复
        # 缩放光标（见 eventFilter）。_scaled_cursor_widget 记录上一次被改
        # 过光标的控件，划出热区时 unsetCursor 还原。
        self._scaled_cursor_widget = None
        app = QApplication.instance()
        if app is not None and os.environ.get("SHELF_NO_GLOB_FILTER") != "1":
            app.installEventFilter(self)

        # 全局空格键极速预览快捷键（无死角响应）
        self._space_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Space), self)
        self._space_shortcut.activated.connect(self._trigger_space_preview)

    def _on_item_captured(self, entry: dict):
        """内置看护器捕获到新条目时的秒级直连响应"""
        self._idle_ticks = 0
        self._load_manifest()
        self._sync_ui()

    def _on_watcher_pause_changed(self, paused: bool):
        """内置看护器暂停状态同步"""
        self._paused = paused
        if hasattr(self, "pause_act") and self.pause_act:
            self.pause_act.setText("▶ 恢复捕获 (F10)" if paused else "⏸ 暂停捕获 (F10)")
        if hasattr(self, "count_lab") and self.count_lab:
            if paused:
                self.count_lab.setText("⏸ 已暂停捕获")
            else:
                self._update_counter()

    def _poll_backend(self):
        try:
            mt = (SHELF_DIR / MANIFEST_NAME).stat().st_mtime
        except OSError:
            mt = 0
        if mt != getattr(self, "_manifest_mtime", -1):
            self._manifest_mtime = mt
            self._idle_ticks = 0
            self._load_manifest()
            self._sync_ui()
        sig = SHELF_DIR / ".show_sig"
        if sig.exists():
            try:
                sig.unlink()
            except OSError:
                pass
            self.toggle_visible()
        paused = (SHELF_DIR / ".paused").exists()
        if paused != self._paused:
            self._paused = paused
            self._update_counter()
            self._toast("已暂停捕获" if paused else "已恢复捕获")

    def _on_idle_mem_trim(self):
        """后台内存自愈修剪：如果窗口不可见、折叠为小方块或持续空闲，主动释放物理内存"""
        try:
            is_hidden_or_collapsed = (not self.isVisible()) or getattr(self, "_collapsed", False)
            if is_hidden_or_collapsed:
                trim_working_set()
            else:
                self._idle_ticks += 1
                if self._idle_ticks >= 2:  # 前台连续 60 秒无新内容捕获，收缩空闲工作集
                    self._idle_ticks = 0
                    trim_working_set()
        except Exception:
            pass

    # ------------------------------------------------------------ 界面构建
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        body = QFrame(objectName="root")
        # 【必须给 body 也开 MouseTracking】
        # body 覆盖整个窗口，鼠标在 body 上移动时事件给 body。
        # body 不开 MouseTracking 就收不到 mouseMoveEvent，也就不会
        # 冒泡到 Shelf —— Shelf 的 setCursor 光标反馈永远不执行，
        # 用户把鼠标移到边缘看不到缩放箭头，以为“拉伸没实现”。
        body.setMouseTracking(True)
        root.addWidget(body)
        self.body = body

        v = QVBoxLayout(body)
        v.setContentsMargins(14, 10, 14, 12)
        v.setSpacing(8)

        # 1. 顶栏
        self.titlebar = QFrame()
        self.titlebar.setFixedHeight(30)
        self.titlebar.setStyleSheet("background:transparent;")
        self.titlebar.installEventFilter(self)
        h = QHBoxLayout(self.titlebar)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(6)

        logo = QLabel()
        logo.setPixmap(_icon("scissors", "#0A84FF" if PALETTES.get(self.settings.get("theme", "dark")) == PALETTES.get("dark") else "#007AFF", 15).pixmap(15, 15))
        h.addWidget(logo)
        title = QLabel("轻松剪贴板", objectName="title")
        self.count_lab = QLabel("", objectName="countPill")
        # 顶栏行内提示位（_toast 的载体）。默认隐藏，有消息才显示，
        # TOAST_DURATION_MS 后自动消失。QLabel 不消费鼠标事件（已实测会冒泡），
        # 所以它不会影响 titlebar 的拖动/双击折叠。
        self.toast_lab = QLabel("", objectName="toastPill")
        self.toast_lab.setMaximumWidth(240)
        self.toast_lab.setTextFormat(Qt.TextFormat.PlainText)
        self.toast_lab.hide()
        h.addWidget(title)
        h.addWidget(self.count_lab)
        h.addWidget(self.toast_lab)
        h.addStretch(1)

        # 「▾」折叠按钮已删除：用户反馈它太小难按，折叠动作由「—」承担。
        # （标题栏双击折叠仍在 eventFilter 里，不依赖这个按钮。）

        self.select_all_btn = QPushButton("全选")
        self.select_all_btn.setProperty("class", "iconBtn")
        self.select_all_btn.setToolTip("切换全选 / 全不选")
        self.select_all_btn.clicked.connect(self.toggle_select_all)
        h.addWidget(self.select_all_btn)

        self.help_btn = QPushButton("?", objectName="helpBtn")
        self.help_btn.setToolTip("使用帮助（完整功能与快捷键指南）")
        self.help_btn.setFixedSize(24, 24)
        self.help_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.help_btn.clicked.connect(self.open_help_dialog)
        h.addWidget(self.help_btn)

        self.gear_btn = QPushButton("")
        self.gear_btn.setProperty("class", "iconBtn")
        self.gear_btn.setToolTip("设置 (主题、路径、热键、开机自启)")
        self.gear_btn.setFixedSize(26, 24)
        self.gear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.gear_btn.setIcon(_icon("gear", PALETTES[self.settings.get("theme", "dark")]["icon"]))
        self.gear_btn.setIconSize(QSize(16, 16))
        self.gear_btn.clicked.connect(self.open_settings)
        h.addWidget(self.gear_btn)

        self.pin_btn = QPushButton("")
        self.pin_btn.setProperty("class", "iconBtn")
        self.pin_btn.setObjectName("pinOn")
        self.pin_btn.setToolTip("置顶 / 取消置顶")
        self.pin_btn.setFixedWidth(26)
        self.pin_btn.clicked.connect(self.toggle_pin)
        h.addWidget(self.pin_btn)

        mini_btn = QPushButton("—")
        mini_btn.setProperty("class", "iconBtn")
        mini_btn.setToolTip("最小化：缩成小方块贴在右上角，点方块展开（双击标题栏同样有效）")
        mini_btn.setFixedWidth(26)
        mini_btn.clicked.connect(self.toggle_collapse)
        h.addWidget(mini_btn)

        close_btn = QPushButton("✕", objectName="closeBtn")
        close_btn.setProperty("class", "iconBtn")
        close_btn.setToolTip("关闭窗口（软件在后台继续运行，F9 随时唤回）")
        close_btn.setFixedWidth(26)
        close_btn.clicked.connect(self.hide)
        h.addWidget(close_btn)

        v.addWidget(self.titlebar)

        # 1.5 视图栈：素材双栏页 / 暂存区内览页
        self.view_stack = QStackedWidget()
        v.addWidget(self.view_stack, stretch=1)

        # 2. 素材页：左右双栏结构
        self.dual_page = QWidget()
        dual_v = QVBoxLayout(self.dual_page)
        dual_v.setContentsMargins(0, 0, 0, 0)
        dual_v.setSpacing(8)
        cols_layout = QHBoxLayout()
        cols_layout.setSpacing(10)

        # --- 左栏：附件与截图 (Files & Images)
        left_col = QVBoxLayout()
        left_col.setSpacing(6)

        lh = QHBoxLayout()
        lh_title = QLabel("附件与截图 · 按住可拖出")
        lh_title.setProperty("class", "colHeader")
        lh.addWidget(lh_title)
        self.left_count_lab = QLabel("", objectName="countPill")
        lh.addWidget(self.left_count_lab)
        lh.addStretch(1)
        left_col.addLayout(lh)

        self.left_host = QWidget()
        self.cards_box_files = QVBoxLayout(self.left_host)
        self.cards_box_files.setContentsMargins(0, 0, 2, 0)
        self.cards_box_files.setSpacing(5)

        self.empty_files = QLabel("暂无附件\n复制文件或截图进入", objectName="emptyText")
        self.empty_files.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_files.setFixedHeight(240)
        self.cards_box_files.addWidget(self.empty_files)
        self.cards_box_files.addStretch(1)

        self.scroll_files = QScrollArea()
        self.scroll_files.setWidgetResizable(True)
        self.scroll_files.setWidget(self.left_host)
        self.scroll_files.setFrameShape(QFrame.Shape.NoFrame)
        left_col.addWidget(self.scroll_files, stretch=1)

        self.btn_drag_files = DragOutButton(
            "按住拖出全部选中附件",
            "按住不放，拖到微信/文件夹里松手；纯点击无效果")
        self.btn_drag_files.drag_requested.connect(self.start_batch_drag)
        left_col.addWidget(self.btn_drag_files)

        cols_layout.addLayout(left_col, stretch=1)

        # 分割线
        div = QFrame(objectName="colDivider")
        div.setFixedWidth(1)
        cols_layout.addWidget(div)

        # --- 右栏：纯文字碎片 (Text Snippets)
        right_col = QVBoxLayout()
        right_col.setSpacing(6)

        rh = QHBoxLayout()
        rh_title = QLabel("文字碎片 · 点击即拷")
        rh_title.setProperty("class", "colHeader")
        rh.addWidget(rh_title)
        self.right_count_lab = QLabel("", objectName="countPill")
        rh.addWidget(self.right_count_lab)
        rh.addStretch(1)
        right_col.addLayout(rh)

        self.right_host = QWidget()
        self.cards_box_text = QVBoxLayout(self.right_host)
        self.cards_box_text.setContentsMargins(0, 0, 2, 0)
        self.cards_box_text.setSpacing(5)

        self.empty_text = QLabel("暂无文字\n复制文字或语音输入进入", objectName="emptyText")
        self.empty_text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_text.setFixedHeight(240)
        self.cards_box_text.addWidget(self.empty_text)
        self.cards_box_text.addStretch(1)

        self.scroll_text = QScrollArea()
        self.scroll_text.setWidgetResizable(True)
        self.scroll_text.setWidget(self.right_host)
        self.scroll_text.setFrameShape(QFrame.Shape.NoFrame)
        right_col.addWidget(self.scroll_text, stretch=1)

        self.btn_copy_text = QPushButton(" 合并复制选中文字")
        self.btn_copy_text.setProperty("class", "colActionBtn")
        self.btn_copy_text.setObjectName("primaryColBtn")
        self.btn_copy_text.setToolTip("合并当前勾选的纯文字，去微信输入框直接 Ctrl+V")
        self.btn_copy_text.clicked.connect(self.copy_merged_text)
        right_col.addWidget(self.btn_copy_text)

        cols_layout.addLayout(right_col, stretch=1)

        dual_v.addLayout(cols_layout, stretch=1)

        # 底部通用动作栏（素材页内）
        foot_bar = QHBoxLayout()
        foot_bar.setSpacing(8)

        theme_cfg = PALETTES.get(self.settings.get("theme", "dark"), PALETTES["dark"])
        ic_col = theme_cfg["icon"]

        self.quick_btn = QPushButton(" 快速访问")
        self.quick_btn.setIcon(_icon("star", ic_col))
        self.quick_btn.setIconSize(QSize(15, 15))
        self.quick_btn.setProperty("class", "footerBtn")
        self.quick_btn.setToolTip("你固定的常用文件夹与文件，随时点开直达")
        self.quick_btn.clicked.connect(lambda: self._switch_view(1))
        foot_bar.addWidget(self.quick_btn)

        self.journal_btn2 = QPushButton(" 今日日志")
        self.journal_btn2.setIcon(_icon("doc", ic_col))
        self.journal_btn2.setIconSize(QSize(15, 15))
        self.journal_btn2.setProperty("class", "footerBtn")
        self.journal_btn2.setToolTip("在应用内查看今天的复制日志（不弹外部程序）")
        self.journal_btn2.clicked.connect(lambda: self._switch_view(2))
        foot_bar.addWidget(self.journal_btn2)

        self.prompts_btn2 = QPushButton(" 快速指令")
        self.prompts_btn2.setIcon(_icon("bolt", theme_cfg["btn_primary"]))
        self.prompts_btn2.setIconSize(QSize(15, 15))
        self.prompts_btn2.setProperty("class", "footerBtn")
        self.prompts_btn2.setToolTip("提示词收藏夹：分类存放，双击即拷")
        self.prompts_btn2.clicked.connect(lambda: self._switch_view(4))
        foot_bar.addWidget(self.prompts_btn2)

        foot_bar.addStretch(1)

        self.purge_btn = QPushButton(" 清空当前批次", objectName="purgeBtn")
        self.purge_btn.setIcon(_icon("trash", theme_cfg.get("danger", "#ef4444")))
        self.purge_btn.setIconSize(QSize(15, 15))
        self.purge_btn.setProperty("class", "footerBtn")
        self.purge_btn.setToolTip("清空当前临时托盘（每日工作日志受严格保护，绝不被清空）")
        self.purge_btn.clicked.connect(self.purge)
        foot_bar.addWidget(self.purge_btn)

        dual_v.addLayout(foot_bar)

        self.view_stack.addWidget(self.dual_page)

        # ---- 快速访问页：固定常用文件夹/文件（_Pinned 专属区），随时直达
        self.quick_page = QWidget()
        qv = QVBoxLayout(self.quick_page)
        qv.setContentsMargins(0, 0, 0, 0)
        qv.setSpacing(8)

        qh = QHBoxLayout()
        qh.addWidget(QLabel("快速访问（双击直达 · 固定不消失）", objectName="colHeader"))
        qh.addStretch(1)
        addf_btn = QPushButton(" 加文件夹")
        addf_btn.setIcon(_icon("plus", PALETTES.get(self.settings.get("theme", "dark"), PALETTES["dark"])["meta"]))
        addf_btn.setIconSize(QSize(12, 12))
        addf_btn.setProperty("class", "footerBtn")
        addf_btn.setToolTip("把常用文件夹加入快速访问（原位置不动，这里建快捷入口）")
        addf_btn.clicked.connect(self.quick_add_folder)
        qh.addWidget(addf_btn)
        addfile_btn = QPushButton(" 加文件")
        addfile_btn.setIcon(_icon("plus", PALETTES.get(self.settings.get("theme", "dark"), PALETTES["dark"])["meta"]))
        addfile_btn.setIconSize(QSize(12, 12))
        addfile_btn.setProperty("class", "footerBtn")
        addfile_btn.clicked.connect(self.quick_add_file)
        qh.addWidget(addfile_btn)
        back_btn = QPushButton(" 返回素材")
        back_btn.setIcon(_icon("back", PALETTES.get(self.settings.get("theme", "dark"), PALETTES["dark"])["meta"]))
        back_btn.setIconSize(QSize(12, 12))
        back_btn.setProperty("class", "footerBtn")
        back_btn.clicked.connect(lambda: self._switch_view(0))
        qh.addWidget(back_btn)
        qv.addLayout(qh)

        self.quick_list = QuickList(self)
        self.quick_list.itemDoubleClicked.connect(
            lambda item: self._open_pinned_item(item.data(Qt.ItemDataRole.UserRole)))
        qv.addWidget(self.quick_list, stretch=1)
        self.quick_hint_lab = QLabel("文件夹式操作：Ctrl+C 复制 · Ctrl+X 剪切 · Ctrl+V 粘贴 · Delete 删除 · 拖入收纳 · 拖出外发",
                                     objectName="cardMeta")
        qv.addWidget(self.quick_hint_lab)
        qv.addWidget(QLabel("右键条目可移除入口；清空批次绝不影响这里", objectName="cardMeta"))

        self.view_stack.addWidget(self.quick_page)

        # ---- 今日日志页：应用内展示（不再弹外部程序）
        self.journal_page = QWidget()
        jv = QVBoxLayout(self.journal_page)
        jv.setContentsMargins(0, 0, 0, 0)
        jv.setSpacing(8)

        jh = QHBoxLayout()
        jh.addWidget(QLabel("今日复制日志", objectName="colHeader"))
        jh.addStretch(1)
        jr_btn = QPushButton(" 刷新")
        jr_btn.setIcon(_icon("refresh", PALETTES.get(self.settings.get("theme", "dark"), PALETTES["dark"])["meta"]))
        jr_btn.setIconSize(QSize(12, 12))
        jr_btn.setProperty("class", "footerBtn")
        jr_btn.clicked.connect(self.refresh_journal_page)
        jh.addWidget(jr_btn)
        jext_btn = QPushButton(" 外部打开")
        jext_btn.setIcon(_icon("folder", PALETTES.get(self.settings.get("theme", "dark"), PALETTES["dark"])["meta"]))
        jext_btn.setIconSize(QSize(12, 12))
        jext_btn.setProperty("class", "footerBtn")
        jext_btn.setToolTip("仍可用系统程序打开当天 md 文件")
        jext_btn.clicked.connect(self.open_today_journal)
        jh.addWidget(jext_btn)
        jback_btn = QPushButton(" 返回素材")
        jback_btn.setIcon(_icon("back", PALETTES.get(self.settings.get("theme", "dark"), PALETTES["dark"])["meta"]))
        jback_btn.setIconSize(QSize(12, 12))
        jback_btn.setProperty("class", "footerBtn")
        jback_btn.clicked.connect(lambda: self._switch_view(0))
        jh.addWidget(jback_btn)
        jv.addLayout(jh)

        self.journal_host = QWidget()
        self.journal_box = QVBoxLayout(self.journal_host)
        self.journal_box.setContentsMargins(0, 2, 2, 2)
        self.journal_box.setSpacing(4)
        j_scroll = QScrollArea()
        j_scroll.setWidgetResizable(True)
        j_scroll.setWidget(self.journal_host)
        j_scroll.setFrameShape(QFrame.Shape.NoFrame)
        jv.addWidget(j_scroll, stretch=1)

        self.view_stack.addWidget(self.journal_page)

        # ---- 使用帮助页（第 4 页）
        self.help_page = QWidget()
        hv = QVBoxLayout(self.help_page)
        hv.setContentsMargins(0, 0, 0, 0)
        hv.setSpacing(8)
        hh = QHBoxLayout()
        hh.addWidget(QLabel("使用帮助", objectName="colHeader"))
        hh.addStretch(1)
        hback_btn = QPushButton(" 返回素材")
        hback_btn.setIcon(_icon("back", PALETTES.get(self.settings.get("theme", "dark"), PALETTES["dark"])["meta"]))
        hback_btn.setIconSize(QSize(12, 12))
        hback_btn.setProperty("class", "footerBtn")
        hback_btn.clicked.connect(lambda: self._switch_view(0))
        hh.addWidget(hback_btn)
        hv.addLayout(hh)
        self.help_view = QPlainTextEdit()
        self.help_view.setReadOnly(True)
        self.help_view.setObjectName("previewBody")
        self.help_view.setPlainText(HELP_TEXT)
        hv.addWidget(self.help_view, stretch=1)
        self.view_stack.addWidget(self.help_page)

        # ---- ⚡ 快速指令页（提示词收藏夹）：左分类 + 右文档
        self.prompts_page = QWidget()
        pv = QVBoxLayout(self.prompts_page)
        pv.setContentsMargins(0, 0, 0, 0)
        pv.setSpacing(8)
        ph = QHBoxLayout()
        ph.addWidget(QLabel("快速指令（提示词收藏夹）", objectName="colHeader"))
        ph.addStretch(1)
        newcat_btn = QPushButton(" 新建分类")
        newcat_btn.setIcon(_icon("plus", PALETTES.get(self.settings.get("theme", "dark"), PALETTES["dark"])["meta"]))
        newcat_btn.setIconSize(QSize(12, 12))
        newcat_btn.setProperty("class", "footerBtn")
        newcat_btn.clicked.connect(self._prompt_new_category)
        ph.addWidget(newcat_btn)

        popen_btn = QPushButton(" 打开目录")
        popen_btn.setIcon(_icon("folder", PALETTES.get(self.settings.get("theme", "dark"), PALETTES["dark"])["meta"]))
        popen_btn.setIconSize(QSize(12, 12))
        popen_btn.setProperty("class", "footerBtn")
        popen_btn.setToolTip("在资源管理器中打开当前分类文件夹")
        popen_btn.clicked.connect(self._prompt_open_current_folder)
        ph.addWidget(popen_btn)

        prefresh_btn = QPushButton(" 刷新")
        prefresh_btn.setIcon(_icon("refresh", PALETTES.get(self.settings.get("theme", "dark"), PALETTES["dark"])["meta"]))
        prefresh_btn.setIconSize(QSize(12, 12))
        prefresh_btn.setProperty("class", "footerBtn")
        prefresh_btn.setToolTip("从磁盘重新扫描并刷新快速指令")
        prefresh_btn.clicked.connect(self.refresh_prompts_page)
        ph.addWidget(prefresh_btn)

        pback_btn = QPushButton(" 返回素材")
        pback_btn.setIcon(_icon("back", PALETTES.get(self.settings.get("theme", "dark"), PALETTES["dark"])["meta"]))
        pback_btn.setIconSize(QSize(12, 12))
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
        pv.addWidget(QLabel("双击复制 · 右键在资源管理器中打开 / 编辑 / 改名", objectName="empty"))
        self.view_stack.addWidget(self.prompts_page)   # index 4

        # ---- 右下角缩放把手（展开态拖动调整窗口大小）
        grip_row = QHBoxLayout()
        grip_row.setContentsMargins(0, 0, 0, 0)
        grip_row.addStretch(1)
        self.size_hint_lab = QLabel("◢", objectName="sizeHint")
        self.size_hint_lab.setFixedSize(18, 14)
        self.size_hint_lab.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom)
        self.size_hint_lab.setToolTip("拖动缩放窗口")
        grip_row.addWidget(self.size_hint_lab)
        v.addLayout(grip_row)

        QShortcut(QKeySequence("Esc"), self).activated.connect(self.hide)

    # ------------------------------------------------------------ 视图切换与折叠
    def _switch_view(self, idx: int):
        self.view_stack.setCurrentIndex(idx)
        if idx == 4:
            self.refresh_prompts_page()
        if idx == 1:
            self.refresh_quick_page()
        elif idx == 2:
            self.refresh_journal_page()
        elif idx == 3:
            self.help_view.setPlainText(HELP_TEXT)

    # ---- 快速访问（_Pinned + 外部快捷入口）
    def _quick_paths_file(self) -> Path:
        return Path(self.settings.get("pinned_dir", str(PINNED_DIR))) / "_links.json"

    def _load_quick_links(self) -> list:
        fp = self._quick_paths_file()
        if fp.exists():
            try:
                return json.loads(fp.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                return []
        return []

    def _save_quick_links(self, links: list):
        try:
            self._quick_paths_file().write_text(
                json.dumps(links, ensure_ascii=False, indent=1), encoding="utf-8")
        except OSError as e:
            print(f"[Shelf] 快速访问保存失败: {e}", file=sys.stderr)

    def refresh_quick_page(self):
        self.quick_list.clear()
        # 1) 外部快捷入口（pinned_dir/_links.json）
        for p in self._load_quick_links():
            if os.path.isdir(p):
                item = QListWidgetItem(f"📁  {p}")
            elif os.path.exists(p):
                item = QListWidgetItem(f"📄  {p}")
            else:
                item = QListWidgetItem(f"⚠️  已失效: {p}")
            item.setData(Qt.ItemDataRole.UserRole, p)
            self.quick_list.addItem(item)
        # 2) _Pinned 专属区内的实体文件/文件夹
        pdir = Path(self.settings.get("pinned_dir", str(PINNED_DIR)))
        try:
            names = sorted(os.listdir(pdir))
        except OSError:
            names = []
        for n in names:
            if n.startswith("_"):
                continue
            p = os.path.join(pdir, n)
            if os.path.isdir(p):
                item = QListWidgetItem(f"📁  {n}")
            else:
                item = QListWidgetItem(f"📄  {n}   ·   {fmt_size(os.path.getsize(p))}")
            item.setData(Qt.ItemDataRole.UserRole, p)
            self.quick_list.addItem(item)

    def quick_add_folder(self):
        d = QFileDialog.getExistingDirectory(self, "选择要固定的文件夹")
        if d:
            links = self._load_quick_links()
            rd = os.path.realpath(d)
            if rd not in links:
                links.append(rd)
                self._save_quick_links(links)
            self.refresh_quick_page()
            self._toast("已加入快速访问")

    def quick_add_file(self):
        f, _ = QFileDialog.getOpenFileName(self, "选择要固定的文件")
        if f:
            links = self._load_quick_links()
            rd = os.path.realpath(f)
            if rd not in links:
                links.append(rd)
                self._save_quick_links(links)
            self.refresh_quick_page()
            self._toast("已加入快速访问")

    def quick_ingest_files(self, paths):
        """拖入快速访问区：实体拷入 _Pinned 托管区（像拷进一个文件夹），源文件不动"""
        ok, fail = 0, 0
        for src in paths:
            if not os.path.exists(src):
                continue
            try:
                dst = unique_pinned_dest(os.path.basename(src))
                if os.path.isdir(src):
                    shutil.copytree(src, dst)
                else:
                    shutil.copy2(src, dst)
                ok += 1
            except (OSError, ValueError) as e:
                fail += 1
                print(f"[Shelf] 快速访问收录失败 {src}: {e}", file=sys.stderr)
        self.refresh_quick_page()
        if ok:
            self._qtoast(f"已收进快速访问 {ok} 项" + (f"（{fail} 项失败）" if fail else ""))
        elif fail:
            self._qtoast(f"{fail} 项收录失败")

    # ---- 快速访问的文件操作（复制 / 剪切 / 粘贴 / 删除）
    def _quick_selection_paths(self) -> list:
        return [i.data(Qt.ItemDataRole.UserRole)
                for i in self.quick_list.selectedItems()
                if i.data(Qt.ItemDataRole.UserRole)]

    def quick_copy_selected(self, cut: bool):
        """复制/剪切选中条目：写入系统剪贴板（资源管理器可直接粘贴）+ 内部缓存"""
        paths = [p for p in self._quick_selection_paths() if os.path.exists(p)]
        if not paths:
            self._qtoast("没有选中条目")
            return
        self._qclip = (paths, cut)
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(p) for p in paths])
        QGuiApplication.clipboard().setMimeData(mime)
        action = "已剪切" if cut else "已复制"
        self._qtoast(f"{action} {len(paths)} 项（在文件夹里 Ctrl+V 也可粘贴）")

    def quick_paste(self):
        """粘贴进 _Pinned：优先取系统剪贴板里的文件；剪切项为移动语义"""
        cb_urls = []
        mime = QGuiApplication.clipboard().mimeData()
        if mime.hasUrls():
            cb_urls = [u.toLocalFile() for u in mime.urls() if u.isLocalFile()
                       and os.path.exists(u.toLocalFile())]
        srcs, cut = getattr(self, "_qclip", ([], False))
        if not cb_urls and srcs:
            cb_urls = [p for p in srcs if os.path.exists(p)]
        if not cb_urls:
            self._qtoast("剪贴板里没有可粘贴的文件")
            return
        real_cut = cut and bool(srcs)
        ok, fail = 0, 0
        for src in cb_urls:
            try:
                dst = unique_pinned_dest(os.path.basename(src))
                if os.path.isdir(src):
                    shutil.copytree(src, dst)
                    if real_cut and os.path.realpath(src) != os.path.realpath(dst):
                        shutil.rmtree(src, ignore_errors=True)
                else:
                    shutil.copy2(src, dst)
                    if real_cut and os.path.realpath(src) != os.path.realpath(dst):
                        os.remove(src)
                ok += 1
            except (OSError, ValueError) as e:
                fail += 1
                print(f"[Shelf] 粘贴失败 {src}: {e}", file=sys.stderr)
        if real_cut:
            self._qclip = ([], False)
        self.refresh_quick_page()
        verb = "移动" if real_cut else "拷入"
        self._qtoast(f"已{verb} {ok} 项" + (f"（{fail} 项失败）" if fail else ""))

    def quick_delete_selected(self):
        """删除选中条目的 _Pinned 实体（外部快捷入口仅移除入口）"""
        paths = self._quick_selection_paths()
        if not paths:
            self._qtoast("没有选中条目")
            return
        ret = QMessageBox.question(
            self, "删除确认",
            f"将删除快速访问区里的 {len(paths)} 个文件（外部源文件不受影响）。\n确认删除？")
        if ret != QMessageBox.StandardButton.Yes:
            return
        links = self._load_quick_links()
        for p in paths:
            try:
                inside = os.path.commonpath(
                    [os.path.realpath(p), os.path.realpath(PINNED_DIR)]) \
                    == os.path.realpath(PINNED_DIR)
            except ValueError:
                inside = False
            if inside and os.path.exists(p):
                try:
                    if os.path.isdir(p):
                        shutil.rmtree(p, ignore_errors=True)
                    else:
                        os.remove(p)
                except OSError:
                    pass
            links = [q for q in links
                     if os.path.normpath(q) != os.path.normpath(p)]
        self._save_quick_links(links)
        self.refresh_quick_page()
        self._qtoast(f"已删除 {len(paths)} 项")

    def _qtoast(self, msg: str):
        """零打扰原则：只在快速访问页头部行内显示，不弹任何系统通知"""
        if hasattr(self, "quick_hint_lab") and self.quick_hint_lab is not None:
            self.quick_hint_lab.setText(msg)

    def _quick_context_menu(self, pos):
        item = self.quick_list.itemAt(pos)
        menu = QMenu(self)
        has_sel = bool(self._quick_selection_paths())
        act_open = menu.addAction("打开")
        menu.addSeparator()
        act_copy = menu.addAction("复制    Ctrl+C")
        act_cut = menu.addAction("剪切    Ctrl+X")
        act_paste = menu.addAction("粘贴    Ctrl+V")
        menu.addSeparator()
        act_del = menu.addAction("删除    Del")
        chosen = menu.exec(self.quick_list.mapToGlobal(pos))
        if chosen == act_open and item is not None:
            self._open_pinned_item(item.data(Qt.ItemDataRole.UserRole))
        elif chosen == act_copy and has_sel:
            self.quick_copy_selected(cut=False)
        elif chosen == act_cut and has_sel:
            self.quick_copy_selected(cut=True)
        elif chosen == act_paste:
            self.quick_paste()
        elif chosen == act_del and has_sel:
            self.quick_delete_selected()

    def _open_pinned_item(self, path):
        if not path or not os.path.exists(path):
            self._toast("路径已失效")
            return
        try:
            os.startfile(path)    # noqa - Windows（文件夹/文件均适用）
        except OSError as e:
            self._toast(f"打开失败: {e}")

    # ---- 今日日志（应用内展示，滚动吸底）
    def _journal_dir(self) -> Path:
        return HISTORY_DIR

    def _journal_fp(self) -> Path:
        return self._journal_dir() / f"{datetime.now():%Y-%m-%d}.md"

    def _parse_journal(self, md: str) -> list:
        """解析每日日志为 [(时间戳, 正文), ...]（按 '### HH:MM:SS' 分段）"""
        entries = []
        cur_ts, cur_body = None, []
        for line in md.splitlines():
            if line.startswith("### "):
                if cur_ts is not None:
                    entries.append((cur_ts, "\n".join(cur_body).strip()))
                cur_ts, cur_body = line[4:].strip(), []
            elif line.strip() in ("---", "") and cur_ts is None:
                continue                          # 头部说明区
            elif cur_ts is not None and line.strip() != "---":
                cur_body.append(line)
        if cur_ts is not None:
            entries.append((cur_ts, "\n".join(cur_body).strip()))
        return entries

    def refresh_journal_page(self):
        fp = self._journal_fp()
        md = ""
        if fp.exists():
            try:
                md = fp.read_text(encoding="utf-8")
            except OSError as e:
                md = f"日志读取失败: {e}"
        # 清空旧渲染（保留 stretch）
        while (item := self.journal_box.takeAt(0)) is not None:
            w = item.widget()
            if w is not None:
                w.deleteLater()
        parsed = self._parse_journal(md)
        if not parsed:
            empty = QLabel("今天还没有复制记录\n\n去任意窗口复制文字，会按时间自动留痕在这里",
                           objectName="empty")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.journal_box.addWidget(empty)
        # 内存与控件安全保护：UI 仅渲染最新 80 条记录，防止海量碎片导致 GDI 句柄泄漏与卡顿
        MAX_JOURNAL_ROWS = 80
        show_items = list(reversed(parsed))
        if len(show_items) > MAX_JOURNAL_ROWS:
            notice = QLabel(f"ℹ️ 仅展示今日最新 {MAX_JOURNAL_ROWS} 条记录（全量 {len(show_items)} 条已安全保存在本地 Markdown 文件中）",
                            objectName="cardMeta")
            notice.setStyleSheet("color: #94a3b8; font-size: 11px; padding: 4px 8px;")
            self.journal_box.addWidget(notice)
            show_items = show_items[:MAX_JOURNAL_ROWS]

        for ts, body in show_items:
            self.journal_box.addWidget(self._make_journal_row(ts, body))
        self.journal_box.addStretch(1)

    def _make_journal_row(self, ts: str, body: str) -> QFrame:
        row = QFrame(objectName="card")
        row.setFixedHeight(44)
        h = QHBoxLayout(row)
        h.setContentsMargins(10, 6, 8, 6)
        h.setSpacing(8)
        ts_lab = QLabel(ts, objectName="cardMeta")
        ts_lab.setFixedWidth(52)
        h.addWidget(ts_lab)
        first = body.splitlines()[0] if body.strip() else "（空白）"
        h.addWidget(elided_label(first, 250, "cardName"), stretch=1)
        qp = QPushButton("", objectName="hoverActionBtn")
        qp.setFixedSize(24, 24)
        qp.setIcon(_icon("bolt", PALETTES.get(self.settings.get("theme", "dark"), PALETTES["dark"])["btn_primary"], 12))
        qp.setIconSize(QSize(12, 12))
        qp.setToolTip("收进快速指令（提示词收藏夹）")
        qp.clicked.connect(lambda *a, b=body: self.add_prompt_text(b))
        h.addWidget(qp)
        cp = QPushButton("", objectName="hoverActionBtn")
        cp.setFixedSize(24, 24)
        cp.setIcon(_icon("copy", PALETTES.get(self.settings.get("theme", "dark"), PALETTES["dark"])["meta"], 12))
        cp.setIconSize(QSize(12, 12))
        cp.setToolTip("复制这一条")
        cp.clicked.connect(lambda *a, b=body, t=ts: self._copy_journal_entry(b))
        h.addWidget(cp)
        return row

    def _copy_journal_entry(self, body: str):
        mime = QMimeData()
        mime.setText(body)
        self._write_own_clipboard(mime, self._suppress_signature([], body))
        self._toast("已复制这一条")

    # ------------------------------------------------------ ⚡ 快速指令区（提示词收藏夹）
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
            [("● " if self.prompts._index["folders"].get(f, {}).get("pinned") else "") + f
             for f in folders])
        idx = folders.index(cur) if cur in folders else 0
        self.prompt_cat_list.setCurrentRow(idx)
        self.prompt_cat_list.blockSignals(blocker)
        self.refresh_prompt_docs(folders[idx])

    def refresh_prompt_docs(self, folder=""):
        """刷文档卡片；folder 列表项可能带 ● 前缀，需剥离。"""
        if isinstance(folder, str):
            folder = folder.lstrip("● ")
        if not folder:
            item = self.prompt_cat_list.currentItem()
            folder = item.text().lstrip("● ") if item is not None else ""
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

    def _reveal_in_explorer(self, target_path: str):
        """在系统资源管理器 / 访达中打开目录，或定位高亮选中具体文件。"""
        try:
            p = os.path.abspath(target_path)
            if sys.platform == "win32":
                if os.path.isfile(p):
                    subprocess.Popen(["explorer", f"/select,{os.path.normpath(p)}"])
                elif os.path.isdir(p):
                    os.startfile(p)
                else:
                    parent = os.path.dirname(p)
                    if os.path.exists(parent):
                        os.startfile(parent)
                    else:
                        os.makedirs(p, exist_ok=True)
                        os.startfile(p)
            elif sys.platform == "darwin":
                if os.path.isfile(p):
                    subprocess.Popen(["open", "-R", p])
                else:
                    os.makedirs(p, exist_ok=True)
                    subprocess.Popen(["open", p])
            else:
                target = p if os.path.isdir(p) else os.path.dirname(p)
                os.makedirs(target, exist_ok=True)
                subprocess.Popen(["xdg-open", target])
        except Exception as e:
            self._toast(f"打开文件管理器失败：{e}")

    def _prompt_open_current_folder(self):
        """在资源管理器中打开当前选中的分类文件夹（或快速指令根目录）。"""
        fold = self._prompt_current_folder()
        if fold:
            fpath = os.path.abspath(str(self.prompts.root / fold))
        else:
            fpath = os.path.abspath(str(self.prompts.root))
        os.makedirs(fpath, exist_ok=True)
        self._reveal_in_explorer(fpath)

    def _prompt_current_folder(self):
        item = self.prompt_cat_list.currentItem()
        return item.text().lstrip("● ") if item is not None else ""

    def _prompt_new_category(self):
        name, ok = QInputDialog.getText(self, "新建分类", "分类名称（对应文件夹）：")
        if ok and str(name).strip():
            self.prompts.ensure_folder(str(name).strip())
            self.refresh_prompts_page()
            self._toast(f"已建分类「{name.strip()}」")

    def _prompt_cat_ctx(self, pos):
        item = self.prompt_cat_list.itemAt(pos)
        menu = QMenu(self)
        if item is None:
            a_new = menu.addAction("新建分类")
            a_open_root = menu.addAction("在资源管理器中打开")
            a_refresh = menu.addAction("刷新列表")
            chosen = menu.exec(self.prompt_cat_list.mapToGlobal(pos))
            if chosen == a_new:
                self._prompt_new_category()
            elif chosen == a_open_root:
                root_path = os.path.abspath(str(self.prompts.root))
                os.makedirs(root_path, exist_ok=True)
                self._reveal_in_explorer(root_path)
            elif chosen == a_refresh:
                self.refresh_prompts_page()
            return

        name = item.text().lstrip("● ")
        a_open = menu.addAction("在资源管理器中打开")
        a_new = menu.addAction("新建分类")
        menu.addSeparator()
        a_rename = menu.addAction("改名")
        pinned = self.prompts._index["folders"].get(name, {}).get("pinned", False)
        a_pin = menu.addAction("取消置顶" if pinned else "置顶")
        menu.addSeparator()
        a_del = menu.addAction("删除分类")
        chosen = menu.exec(self.prompt_cat_list.mapToGlobal(pos))
        if chosen == a_open:
            fpath = os.path.abspath(str(self.prompts.root / name))
            os.makedirs(fpath, exist_ok=True)
            self._reveal_in_explorer(fpath)
        elif chosen == a_new:
            self._prompt_new_category()
        elif chosen == a_rename:
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
        a_open = menu.addAction("在资源管理器中打开")
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
        elif chosen == a_open:
            doc_path = card.info.get("path") or str(self.prompts.root / fold / f"{name}.md")
            if os.path.exists(doc_path):
                self._reveal_in_explorer(doc_path)
            else:
                fpath = os.path.abspath(str(self.prompts.root / fold))
                os.makedirs(fpath, exist_ok=True)
                self._reveal_in_explorer(fpath)
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
        try:
            if dlg.exec() == QDialog.DialogCode.Accepted:
                folder = dlg.selected_folder()
                try:
                    path = self.prompts.add_text(text, folder)
                    self._toast(f"已收进「{folder}」：{path.stem}")
                    if self.view_stack.currentIndex() == 4:
                        self.refresh_prompts_page()
                except ValueError:
                    self._toast("内容为空，未收藏")
        finally:
            if hasattr(dlg, "deleteLater"):
                dlg.deleteLater()

    # ---- 素材卡片右键：文字=加入快速/删除；附件=加入快速访问区/删除 ----
    def _card_context_menu(self, card, pos):
        e = card.entry
        menu = QMenu(self)
        if e["kind"] == "text":
            a_add = menu.addAction("加入快速…")
        else:
            a_add = menu.addAction("加入快速访问区")
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

    def toggle_collapse(self):
        """折叠：主窗隐藏，右上角原地出现圆润小方块；点方块展开原窗"""
        if not self._collapsed:
            g = self.frameGeometry()
            self._mini = SmallBlock()
            self._mini.clicked.connect(self._expand_from_block)
            self._mini.setStyleSheet(
                "#miniBlock { background: qlineargradient(x1:0,y1:0,x2:1,y2:1,"
                "stop:0 #2b3b57, stop:1 #1e2233);"
                " border: 1px solid #3b82f6; border-radius: 28px; }")
            # 小方块放右上角：若本次运行期间用户拖过它，回到用户拖到的位置
            last = getattr(self, "_mini_last_pos", None)
            if last is not None and QGuiApplication.screenAt(last) is not None:
                self._mini.move(last)
            else:
                self._mini.move(g.right() - 108, g.top() + 4)
            self._mini.show()
            self.hide()
            self._collapsed = True
        else:
            self._expand_from_block()

    def _expand_from_block(self):
        if getattr(self, "_mini", None) is not None:
            self._mini_last_pos = self._mini.pos()  # 记住用户拖到的位置
            self._mini.close()
            self._mini = None
        self._collapsed = False
        self._place_top_right()
        self.show()
        self.raise_()
        self.activateWindow()

    def _build_tray(self):
        try:
            self.tray = QSystemTrayIcon(make_tray_icon(), self)
            menu = QMenu()
            act = QAction("显示 / 隐藏 (F9)", menu)
            act.triggered.connect(self.toggle_visible)
            self.pause_act = QAction("⏸ 暂停捕获 (F10)", menu)
            self.pause_act.setToolTip("复制密码/敏感内容前暂停，避免误入暂存与日志")
            self.pause_act.triggered.connect(self.toggle_pause)
            j_act = QAction("打开今日日志", menu)
            j_act.triggered.connect(self.open_today_journal)
            set_act = QAction("设置", menu)
            set_act.triggered.connect(self.open_settings)
            quit_act = QAction("退出", menu)
            quit_act.triggered.connect(QApplication.instance().quit)
            menu.addAction(act)
            menu.addAction(self.pause_act)
            menu.addAction(j_act)
            menu.addAction(set_act)
            menu.addAction(quit_act)
            self.tray.setContextMenu(menu)
            self.tray.activated.connect(
                lambda r: self.toggle_visible()
                if r == QSystemTrayIcon.ActivationReason.Trigger else None)
            self.tray.setToolTip("轻松剪贴板 — F9 呼出")
            self.tray.show()
        except Exception:
            self.tray = None

    def toggle_pause(self):
        """暂停/恢复捕获：复制密码等敏感内容前用；重启后自动恢复捕获"""
        if hasattr(self, "watcher") and self.watcher:
            self._paused = self.watcher.toggle_pause()
        else:
            self._paused = not getattr(self, "_paused", False)
        if self._paused:
            if hasattr(self, "pause_act"):
                self.pause_act.setText("▶ 恢复捕获 (F10)")
            if hasattr(self, "count_lab"):
                self.count_lab.setText("⏸ 已暂停捕获")
            self._toast("已暂停捕获——期间的复制不会进入暂存与日志")
        else:
            if hasattr(self, "pause_act"):
                self.pause_act.setText("⏸ 暂停捕获 (F10)")
            self._update_counter()
            self._toast("已恢复捕获")


    def _register_pause_hotkey(self):
        # 与 F9 相同的钩子线程标志 + GUI 轮询消费模式
        self._pause_pending = False
        try:
            import keyboard
            keyboard.add_hotkey("f10", lambda: setattr(self, "_pause_pending", True))
        except Exception as e:
            print(f"[Shelf] F10 热键注册失败：{e}", file=sys.stderr)
            QShortcut(QKeySequence("F10"), self).activated.connect(self.toggle_pause)

        poll2 = QTimer(self)
        poll2.setInterval(150)
        poll2.timeout.connect(self._consume_pause_hotkey)
        poll2.start()

    def _consume_pause_hotkey(self):
        if getattr(self, "_pause_pending", False):
            self._pause_pending = False
            self.toggle_pause()

    def _register_hotkey(self):
        """按设置注册全局呼出热键（支持重新注册换键）；失败退化为窗口内快捷键"""
        self._hotkey_pending = False
        hk = self.settings.get("hotkey", HOTKEY)
        try:
            import keyboard
            if getattr(self, "_hotkey_handler", None) is not None:
                try:
                    keyboard.remove_hotkey(self._hotkey_handler)
                except (KeyError, ValueError):
                    pass
            self._hotkey_handler = keyboard.add_hotkey(
                hk, lambda: setattr(self, "_hotkey_pending", True))
            self._hotkey_inapp_only = False
        except Exception as e:
            print(f"[Shelf] 全局热键注册失败：{e}", file=sys.stderr)
            self._hotkey_inapp_only = True
            QShortcut(QKeySequence(hk.upper()), self).activated.connect(
                self.toggle_visible)

        if not hasattr(self, "_hotkey_poll_started"):
            self._hotkey_poll_started = True
            poll = QTimer(self)
            poll.setInterval(120)
            poll.timeout.connect(self._consume_hotkey)
            poll.start()

    def _consume_hotkey(self):
        if getattr(self, "_hotkey_pending", False):
            if self._drag_active:
                return                    # 拖拽模态循环中挂起 F9，拖完再消费
            self._hotkey_pending = False
            self.toggle_visible()

    def _place_top_right(self):
        g = QGuiApplication.primaryScreen().availableGeometry()
        self.move(g.right() - self.width() - 20, g.top() + 20)

    # ------------------------------------------------------------ 外观与设置
    def _apply_rounded_corners(self):
        """DWM 原生圆角（Windows 11 22621+）。

        为什么不靠 QSS border-radius：WA_TranslucentBackground + 玻璃效果
        下，DWM 直接渲染整个窗口，QSS 的 border-radius 可能被忽略，
        四个角变成直角（用户截图确认）。
        DWMWA_WINDOW_CORNER_PREFERENCE = 33 是 Windows 11 原生 API，
        DWMWCP_ROUND = 2 强制给窗口加圆角，与 QSS 无关，绝对可靠。
        """
        try:
            if sys.platform != "win32" or sys.getwindowsversion().build < 22621:
                return False
            dwm = ctypes.windll.dwmapi
            DWMWA_WINDOW_CORNER_PREFERENCE = 33
            DWMWCP_ROUND = 2
            pref = ctypes.c_int(DWMWCP_ROUND)
            hr = dwm.DwmSetWindowAttribute(
                ctypes.c_void_p(int(self.winId())),
                DWMWA_WINDOW_CORNER_PREFERENCE,
                ctypes.byref(pref), 4)
            return hr == 0
        except Exception:                        # noqa: BLE001
            return False

    def apply_look(self):
        theme = PALETTES[self.settings["theme"]]
        glass = bool(self.settings.get("glass"))
        self.app_qss = build_qss(theme, glass and self._glass_ok)
        self.setStyleSheet(self.app_qss)
        if self._settings_dlg is not None:
            self._settings_dlg.setStyleSheet(self.app_qss)
        self.setWindowOpacity(self.settings["opacity"] / 100)
        self._glass_ok = False
        if glass:
            self._glass_ok = enable_acrylic(int(self.winId()), theme.get("dwmdark") == 1)
            if self._glass_ok:
                self.app_qss = build_qss(theme, True)
                self.setStyleSheet(self.app_qss)
                if self._settings_dlg is not None:
                    self._settings_dlg.setStyleSheet(self.app_qss)
        # 圆角走 DWM（DWMWCP_ROUND），与玻璃效果互不冲突；
        # apply_look 在启动/主题切换/置顶切换时反复调用，DWM 属性幂等可重复设。
        self._apply_rounded_corners()
        self._refresh_icons()

    def _refresh_icons(self):
        """深色/浅色模式切换时，动态刷新所有常驻按钮的图标对比度与清晰度。"""
        try:
            theme = PALETTES[self.settings.get("theme", "dark")]
            ic_col = theme.get("icon", theme["title"])

            if hasattr(self, "gear_btn"):
                self.gear_btn.setIcon(_icon("gear", ic_col))
            if hasattr(self, "quick_btn"):
                self.quick_btn.setIcon(_icon("star", ic_col))
            if hasattr(self, "journal_btn2"):
                self.journal_btn2.setIcon(_icon("doc", ic_col))
            if hasattr(self, "prompts_btn2"):
                self.prompts_btn2.setIcon(_icon("bolt", theme["btn_primary"]))
            if hasattr(self, "purge_btn"):
                self.purge_btn.setIcon(_icon("trash", theme.get("danger", "#ef4444")))
        except Exception:
            pass

    def showEvent(self, ev):
        super().showEvent(ev)
        # 窗口创建后 HWND 才真正存在，此时设置 DWM 圆角最可靠。
        # 不设置的话四角是直角（用户截图确认）。
        # 注意：WS_THICKFRAME/nativeEvent 方案已废弃（见下方注释），
        # 缩放由 Qt 层面 mousePress/Move/Release 完成，与圆角互不干扰。
        self._apply_rounded_corners()
        QTimer.singleShot(60, self.apply_look)

    def hideEvent(self, ev):
        super().hideEvent(ev)
        trim_working_set()

    def open_help_dialog(self):
        if not hasattr(self, "_help_dlg") or self._help_dlg is None:
            self._help_dlg = HelpDialog(self)
        self._help_dlg.show()
        self._help_dlg.raise_()
        self._help_dlg.activateWindow()
        g = self.frameGeometry()
        screen_geo = QGuiApplication.primaryScreen().availableGeometry()
        w, h = self._help_dlg.width(), self._help_dlg.height()
        x = max(20, min(screen_geo.right() - w - 20, g.left() + (g.width() - w) // 2))
        y = max(20, min(screen_geo.bottom() - h - 20, g.top() + (g.height() - h) // 2))
        self._help_dlg.move(x, y)

    def open_settings(self):
        if not hasattr(self, "_settings_dlg") or self._settings_dlg is None:
            self._settings_dlg = SettingsDialog(self)
        else:
            if hasattr(self._settings_dlg, "refresh_values"):
                self._settings_dlg.refresh_values()

        # 无论之前是隐藏、最小化还是初次打开，必须显式调用 show() 保证可见
        self._settings_dlg.show()
        self._settings_dlg.raise_()
        self._settings_dlg.activateWindow()

        # 智能动态计算居中与贴靠位置（适配多显示器与可用工作区）
        screen = None
        if self.isVisible():
            screen = QGuiApplication.screenAt(self.geometry().center())
        if screen is None:
            screen = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()

        screen_geo = screen.availableGeometry() if screen else QRect(0, 0, 1920, 1080)
        dlg_w = self._settings_dlg.width()
        dlg_h = self._settings_dlg.height()

        if self.isVisible():
            g = self.frameGeometry()
            # 优先摆在主窗口左侧，保持 8px 呼吸间隔（彻底解决过去 -380 导致的 80px 严重遮挡重叠）
            if g.left() - dlg_w - 8 >= screen_geo.left():
                x = g.left() - dlg_w - 8
            # 若左侧空间不够，摆在主窗口右侧
            elif g.right() + 8 + dlg_w <= screen_geo.right():
                x = g.right() + 8
            # 若左右均不够，屏幕水平居中
            else:
                x = screen_geo.left() + max(10, (screen_geo.width() - dlg_w) // 2)

            # 纵向对齐：优先与主窗口对齐，严格限制在屏幕可用高度内（防止底部确定按钮被任务栏遮挡）
            y = max(screen_geo.top() + 10, min(screen_geo.bottom() - dlg_h - 10, g.top()))
        else:
            # 主窗口未显示时（如托盘右键直接打开选项设置），直接居中显示
            x = screen_geo.left() + max(10, (screen_geo.width() - dlg_w) // 2)
            y = screen_geo.top() + max(10, (screen_geo.height() - dlg_h) // 2)

        self._settings_dlg.move(x, y)
        self._settings_dlg.show()
        self._settings_dlg.raise_()
        self._settings_dlg.activateWindow()

    def set_setting(self, key: str, value):
        self.settings[key] = value
        save_settings(self.settings)
        if key in ("theme", "opacity", "glass"):
            self.apply_look()
        elif key == "history_dir":
            global HISTORY_DIR
            HISTORY_DIR = Path(value)
            HISTORY_DIR.mkdir(parents=True, exist_ok=True)
            if hasattr(self, "watcher") and self.watcher:
                self.watcher.update_config(history_dir=HISTORY_DIR)
        elif key == "shelf_dir":
            global SHELF_DIR, SHELF_REAL
            SHELF_DIR = Path(value)
            SHELF_REAL = os.path.realpath(SHELF_DIR)
            SHELF_DIR.mkdir(parents=True, exist_ok=True)
            if hasattr(self, "watcher") and self.watcher:
                self.watcher.update_config(shelf_dir=SHELF_DIR)
        elif key == "pinned_dir":
            global PINNED_DIR
            PINNED_DIR = Path(value)
            PINNED_DIR.mkdir(parents=True, exist_ok=True)
        elif key == "min_text_len":
            if hasattr(self, "watcher") and self.watcher:
                self.watcher.update_config(min_text_len=int(value))

    # ------------------------------------------------------------ 开机自启
    AUTOSTART_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
    AUTOSTART_NAME = "EasyClipboard"

    @staticmethod
    def _autostart_command() -> str:
        """开机自启命令：直接指向主程序本体（带 --tray 参数静默启动常驻系统托盘）。
        【彻底消灭黑框】：
        - 打包态：直接是无控制台的「轻松剪贴板.exe --tray」，100% 纯净无窗口；
        - 开发态：使用 pythonw.exe 跑 shelf_app.py，严禁调用 python.exe。
        """
        if getattr(sys, "frozen", False):
            return f'"{sys.executable}" --tray'

        py_dir = Path(sys.executable).resolve().parent
        pythonw = py_dir / "pythonw.exe"
        interp = pythonw if pythonw.exists() else Path(sys.executable).resolve()
        script = APP_DIR / "shelf_app.py"
        return f'"{interp}" "{script}" --tray'

    # ---------------------------------------------------------- 一体化看护保障
    def _watchdog_alive(self) -> bool:
        """一体化架构：看护器作为内部后台守护线程，始终与主程序同生共死"""
        return hasattr(self, "watcher") and self.watcher is not None and self.watcher._running

    def ensure_watchdog(self):
        """确保内置看护守护线程正常运行（零子进程，零外部黑框）"""
        if hasattr(self, "watcher") and self.watcher:
            self.watcher.start()


    def autostart_enabled(self) -> bool:
        if sys.platform != "win32":
            return False
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                self.AUTOSTART_KEY, 0,
                                winreg.KEY_READ) as k:
                winreg.QueryValueEx(k, self.AUTOSTART_NAME)
                return True
        except (OSError, ImportError):
            return False

    def set_autostart(self, enabled: bool):
        if sys.platform != "win32":
            self.settings["autostart"] = enabled
            save_settings(self.settings)
            return
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, self.AUTOSTART_KEY, 0,
                                winreg.KEY_SET_VALUE) as k:
                if enabled:
                    winreg.SetValueEx(k, self.AUTOSTART_NAME, 0,
                                      winreg.REG_SZ, self._autostart_command())
                    self._toast("已开启开机自启")
                else:
                    try:
                        winreg.DeleteValue(k, self.AUTOSTART_NAME)
                    except FileNotFoundError:
                        pass
                    self._toast("已关闭开机自启")
            self.settings["autostart"] = enabled
            save_settings(self.settings)
        except (OSError, ImportError) as e:
            self._toast(f"自启设置失败: {e}")

    def eventFilter(self, obj, ev):
        # 八向缩放的光标反馈：直接对鼠标命中的子控件设缩放光标。
        # （热区里覆盖着滚动区/按钮/信息标签等子控件，它们的光标优先级
        #  高于父窗口，父级 setCursor 根本显示不出来。）
        # 注意：本函数是 Qt 虚函数回调，任何 Python 异常都会 qFatal 杀进程
        # （BUG-001 教训），因此整个分支包 try；对已删除的控件包装对象
        # （sip runtime deleted）也单独防护。
        try:
            if (ev.type() == QEvent.Type.MouseMove and isinstance(obj, QWidget)
                    and obj.window() is self
                    and ev.buttons() == Qt.MouseButton.NoButton
                    and not getattr(self, "_resizing", False)):
                p = self.mapFromGlobal(ev.globalPosition().toPoint())
                hit = self._hit_test(p.x(), p.y())
                prev = getattr(self, "_scaled_cursor_widget", None)
                if hit:
                    if obj is not prev:
                        if prev is not None:
                            try:
                                prev.unsetCursor()
                            except RuntimeError:
                                pass
                        obj.setCursor(Qt.CursorShape(self._CURSOR_MAP[hit]))
                        self._scaled_cursor_widget = obj
                else:
                    if prev is not None:
                        try:
                            prev.unsetCursor()
                        except RuntimeError:
                            pass
                        self._scaled_cursor_widget = None
        except Exception:
            pass
        if obj is self.titlebar:
            t = ev.type()
            if t == ev.Type.MouseButtonDblClick and ev.button() == Qt.MouseButton.LeftButton:
                self.toggle_collapse()
                return True
            if t == ev.Type.MouseButtonPress and ev.button() == Qt.MouseButton.LeftButton:
                self._win_offset = ev.globalPosition().toPoint() - self.frameGeometry().topLeft()
            elif t == ev.Type.MouseMove and (ev.buttons() & Qt.MouseButton.LeftButton) \
                    and hasattr(self, "_win_offset"):
                self.move(ev.globalPosition().toPoint() - self._win_offset)
        return super().eventFilter(obj, ev)

    # ------------------------------------------------------------ 剪贴板管道与每日日志
    def _on_clipboard_changed(self):
        # 铁律：信号处理器内绝不直接读剪贴板（源程序可能仍持有剪贴板/延迟渲染未就绪，
        # 重入访问在部分 Qt 版本上会原生崩溃）。一律延迟 80ms 再处理。
        QTimer.singleShot(80, self._process_clipboard)

    def _process_clipboard(self):
        # 暂停捕获开关：复制密码/敏感内容前可一键暂停（托盘菜单或 F10）
        if getattr(self, "_paused", False):
            return
        # OLE 拖拽模态循环中只挂起标记，拖拽结束后统一补处理（期间重建 UI 会原生崩溃）
        if self._drag_active:
            self._pending_clip = True
            return
        try:
            self._process_clipboard_inner()
        except Exception:
            # 管道内任何异常都记录后吞掉——绝不能让信号处理器里的错误杀死进程
            import traceback
            traceback.print_exc(file=sys.stderr)

    def _process_clipboard_inner(self):
        if time.time() < getattr(self, "_suppress_until", 0):
            mime = QGuiApplication.clipboard().mimeData()
            text = QGuiApplication.clipboard().text() if mime.hasText() else ""
            sig = (frozenset(os.path.normpath(u.toLocalFile())
                             for u in mime.urls() if u.isLocalFile()),
                   hashlib.sha256(text.encode("utf-8", "ignore")).hexdigest())
            if sig == getattr(self, "_suppress_sig", None):
                return
            self._suppress_until = 0

        cb = QGuiApplication.clipboard()
        mime = cb.mimeData()

        # 诊断埋点：右键复制不进暂存时，这里能看到当时收到的数据形态
        print(f"[Shelf] 剪贴板变更: img={mime.hasImage()} urls={mime.hasUrls()} "
              f"text={mime.hasText()} formats={mime.formats()[:4]}",
              file=sys.stderr, flush=True)

        if mime.hasImage():
            img = cb.image()
            if img.isNull():
                # 延迟渲染兜底：某些程序右键复制时只声明格式，尝试直接按 PNG 字节取
                data = mime.data("image/png")
                if data is not None and len(data) > 0:
                    print("[Shelf] image() 为空，改从 image/png 原始字节摄取",
                          file=sys.stderr, flush=True)
                    self._ingest_image_bytes(bytes(data))
                    return
                print("[Shelf] 声明有图但读不到数据（延迟渲染未就绪），丢弃",
                      file=sys.stderr, flush=True)
                return
            self._ingest_image(img)
            return

        if mime.hasUrls():
            locals_ = [u.toLocalFile() for u in mime.urls() if u.isLocalFile()]
            if locals_:
                self._ingest_files(locals_)
                return
            if mime.hasText():
                self._ingest_text(cb.text())
            return

        if mime.hasText():
            self._ingest_text(cb.text())

    def _ingest_image_bytes(self, data: bytes):
        """延迟渲染兜底：直接消费 PNG 原始字节"""
        h = hashlib.sha256(data).hexdigest()
        if h == self._ignore_hash or any(
                e["kind"] == "image" and e.get("hash") == h for e in self.entries):
            return
        name = f"img_{datetime.now():%Y%m%d_%H%M%S}.png"
        try:
            dst = unique_dest(name)
            Path(dst).write_bytes(data)
        except (OSError, ValueError) as e:
            print(f"[Shelf] 截图落盘失败: {e}", file=sys.stderr)
            return
        self._add_entry({"kind": "image", "name": os.path.basename(dst),
                         "hash": h, "ts": datetime.now().strftime("%H:%M:%S")})

    def _ingest_image(self, img):
        if img.isNull():
            return
        ba = QByteArray()
        buf = QBuffer(ba)
        buf.open(QIODevice.OpenModeFlag.WriteOnly)
        img.save(buf, "PNG")
        data = bytes(ba)
        h = hashlib.sha256(data).hexdigest()
        if h == self._ignore_hash:
            self._ignore_hash = ""
            return
        if any(e["kind"] == "image" and e.get("hash") == h for e in self.entries):
            return
        name = f"img_{datetime.now():%Y%m%d_%H%M%S}.png"
        try:
            dst = unique_dest(name)
            Path(dst).write_bytes(data)
        except (OSError, ValueError) as e:
            print(f"[Shelf] 截图落盘失败: {e}", file=sys.stderr)
            return
        self._last_img_hash = h
        self._add_entry({"kind": "image", "name": os.path.basename(dst),
                         "hash": h, "ts": datetime.now().strftime("%H:%M:%S")})

    def _ingest_text(self, text: str):
        if not text or not text.strip():
            return
        # 防误入：过短碎片（如临时复制单个字符）不入架不写日志
        min_len = int(self.settings.get("min_text_len", 2))
        if len(text.strip()) < min_len:
            print(f"[Shelf] 过短碎片未收录（{len(text.strip())} 字 < {min_len}）",
                  file=sys.stderr, flush=True)
            return
        h = hashlib.sha256(text.encode("utf-8", "ignore")).hexdigest()
        if h == self._ignore_hash:
            self._ignore_hash = ""
            return
        if any(e["kind"] == "text" and e.get("text") == text for e in self.entries):
            print(f"[Shelf] 重复文本已跳过（暂存中已存在，去重不等于丢失，日志仍会留痕上一条）",
                  file=sys.stderr, flush=True)
            return
        self._last_text = text
        ts = datetime.now().strftime("%H:%M:%S")
        self._add_entry({"kind": "text", "text": text, "ts": ts})

        # 核心：自动追加进入当天的剪贴板日志
        self._append_daily_journal(text, ts)

    def _append_daily_journal(self, text: str, ts: str):
        try:
            today_str = datetime.now().strftime("%Y-%m-%d")
            journal_path = HISTORY_DIR / f"{today_str}.md"
            is_new = not journal_path.exists() or journal_path.stat().st_size == 0

            content = ""
            if is_new:
                content += f"# 剪贴板工作日志 — {today_str}\n\n"
                content += "> 记录今日复制与输入的文字碎片，沉淀为个人工作记忆与知识库。\n\n---\n\n"

            content += f"### {ts}\n\n{text.strip()}\n\n---\n\n"
            with journal_path.open("a", encoding="utf-8") as f:
                f.write(content)
        except Exception as e:
            print(f"[Shelf] 写入每日日志失败: {e}", file=sys.stderr)

    def open_today_journal(self):
        today_str = datetime.now().strftime("%Y-%m-%d")
        journal_path = HISTORY_DIR / f"{today_str}.md"
        if not journal_path.exists():
            try:
                journal_path.write_text(
                    f"# 剪贴板工作日志 — {today_str}\n\n> 今日暂无文本记录。\n\n---\n\n",
                    encoding="utf-8"
                )
            except OSError:
                pass
        try:
            os.startfile(journal_path)
        except OSError:
            pass

    @staticmethod
    def _path_size(p: str) -> int:
        if os.path.isfile(p):
            return os.path.getsize(p)
        total = 0
        for root, _, files in os.walk(p):
            for f in files:
                try:
                    total += os.path.getsize(os.path.join(root, f))
                except OSError:
                    pass
        return total

    def _ingest_files(self, paths):
        for src in paths:
            if not os.path.exists(src):
                continue
            real_src = os.path.realpath(src)
            # 1. 防自吞噬：暂存区目录自身内部的产物（截图cap_*.bmp、manifest等）绝不当作外部文件导入
            try:
                if os.path.commonpath([real_src, SHELF_REAL]) == SHELF_REAL:
                    continue
            except Exception:
                pass
            # 2. 查重：已收录的同路径外部文件跳过
            if any(e.get("kind") == "file" and e.get("src") == real_src for e in self.entries):
                continue
            # 3. 查重：若同名图片已在暂存区存在，跳过
            base_n = os.path.basename(real_src)
            if any(e.get("kind") == "image" and e.get("name") == base_n for e in self.entries):
                continue
            self._add_entry({"kind": "file", "name": base_n,
                             "src": real_src, "size": self._path_size(real_src),
                             "ts": datetime.now().strftime("%H:%M:%S")})


    def _add_entry(self, entry: dict):
        entry.setdefault("on", False)
        entry.setdefault("at", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        self.entries.append(entry)
        self._commit()

    # ------------------------------------------------------------ 持久化与双栏渲染
    def _entry_path(self, name: str) -> str:
        return safe_dest(name)

    def _persist_manifest(self):
        """纯数据落盘：写 manifest + 草稿，不触碰任何 UI 控件。

        单独抽出本函数的原因：__init__ 中 _load_manifest() 早于 _build_ui()，
        而 _commit() 末尾会调 _sync_ui()（访问 cards_box_files 等尚未创建的控件）。
        保留策略清理需要在启动早期就落盘，所以必须走不依赖 UI 的路径。
        """
        try:
            mp = Path(self._entry_path(MANIFEST_NAME))
            mp.write_text(json.dumps(self.entries, ensure_ascii=False), encoding="utf-8")
            blocks = []
            for e in self.entries:
                if not e.get("on", False):
                    continue
                if e["kind"] == "text":
                    blocks.append(e["text"])
                elif e["kind"] == "image":
                    blocks.append(f"![]({e['name']})")
                else:
                    blocks.append(f"附件  {e['name']}（{fmt_size(e.get('size', 0))}）")
            dp = Path(self._entry_path(DRAFT_NAME))
            dp.write_text("\n\n".join(blocks), encoding="utf-8")
        except (OSError, ValueError):
            pass

    def _commit(self):
        self._persist_manifest()
        self._sync_ui()

    def _load_manifest(self):
        p = SHELF_DIR / MANIFEST_NAME
        if p.exists():
            try:
                self.entries = json.loads(p.read_text(encoding="utf-8"))
                for e in self.entries:
                    e.setdefault("on", False)
            except (OSError, ValueError):
                self.entries = []
        else:
            self.entries = []
        self._apply_retention()          # 保留策略：按设置清理过期条目（默认永不）

        # 脏数据自愈：剔除把暂存区内截图/素材误当成外部文件收录的冗余条目
        cleaned = []
        dirty = False
        img_names = {e.get("name") for e in self.entries if e.get("kind") == "image"}
        for e in self.entries:
            if e.get("kind") == "file":
                src = e.get("src", "")
                name = e.get("name", "")
                # 如果指向暂存区内部，或者与现有截图重名，判定为环回拖拽产生的冗余脏数据
                try:
                    if src and os.path.commonpath([os.path.realpath(src), SHELF_REAL]) == SHELF_REAL:
                        dirty = True
                        continue
                except Exception:
                    pass
                if name in img_names:
                    dirty = True
                    continue
            cleaned.append(e)
        if dirty:
            self.entries = cleaned
            self._persist_manifest()

        if self.entries and not p.exists():
            self._persist_manifest()


    def _apply_retention(self):
        """保留策略：auto_clear_hours=0 永不自动清除（手动清空为准）；
        >0 时启动时清理超龄条目（截图等自产文件一并删除，源文件绝不触碰）"""
        hours = int(self.settings.get("auto_clear_hours", 0) or 0)
        if hours <= 0 or not self.entries:
            return
        cutoff = datetime.now().timestamp() - hours * 3600
        kept, removed = [], []
        for e in self.entries:
            at = e.get("at") or e.get("ts", "")
            try:
                created = datetime.strptime(
                    at if "-" in at else
                    f"{datetime.now():%Y-%m-%d} {at}", "%Y-%m-%d %H:%M:%S").timestamp()
            except ValueError:
                kept.append(e)           # 无有效时间戳的条目不清理
                continue
            if created >= cutoff:
                kept.append(e)
            else:
                removed.append(e)
        if not removed:
            return
        for e in removed:                # 自产截图物理清理；文件类仅移除引用
            if e["kind"] == "image":
                try:
                    p = self._entry_path(e["name"])
                    if os.path.exists(p):
                        os.remove(p)
                except (OSError, ValueError):
                    pass
        self.entries = kept
        # 清理结果必须立即落盘：本方法已物理删除过期截图，但看守进程下次捕获时是
        # load_manifest() → 追加 → save_manifest()，若不清理落盘，已删文件的死引用
        # 会被看守原样写回，保留策略静默失效。走 _persist_manifest 而非 _commit，
        # 因为本方法可能在 _build_ui() 之前被调用（此时 UI 控件尚不存在）。
        self._persist_manifest()
        print(f"[Shelf] 保留策略：已清理 {len(removed)} 条超过 {hours} 小时的素材",
              file=sys.stderr, flush=True)

    def _sync_ui(self):
        # 1. 刷新左栏（附件/截图）
        while (item := self.cards_box_files.takeAt(0)) is not None:
            w = item.widget()
            if w is not None and w is not self.empty_files:
                w.deleteLater()

        file_entries = [e for e in self.entries if e["kind"] in ("image", "file")]
        if not file_entries:
            self.empty_files.show()
            self.cards_box_files.addWidget(self.empty_files)
        else:
            self.empty_files.hide()
            for e in reversed(file_entries):
                self.cards_box_files.addWidget(ShelfCard(e, self, is_file_col=True))
        self.cards_box_files.addStretch(1)

        # 2. 刷新右栏（文字碎片）
        while (item := self.cards_box_text.takeAt(0)) is not None:
            w = item.widget()
            if w is not None and w is not self.empty_text:
                w.deleteLater()

        text_entries = [e for e in self.entries if e["kind"] == "text"]
        if not text_entries:
            self.empty_text.show()
            self.cards_box_text.addWidget(self.empty_text)
        else:
            self.empty_text.hide()
            for e in reversed(text_entries):
                self.cards_box_text.addWidget(ShelfCard(e, self, is_file_col=False))
        self.cards_box_text.addStretch(1)

        self._update_counter()

    def _on_entry_selection_changed(self):
        self._update_counter()
        try:
            mp = Path(self._entry_path(MANIFEST_NAME))
            mp.write_text(json.dumps(self.entries, ensure_ascii=False), encoding="utf-8")
        except (OSError, ValueError):
            pass

    def _update_counter(self):
        f_all = [e for e in self.entries if e["kind"] in ("image", "file")]
        f_sel = [e for e in f_all if e.get("on", False)]
        t_all = [e for e in self.entries if e["kind"] == "text"]
        t_sel = [e for e in t_all if e.get("on", False)]

        self.left_count_lab.setText(f"{len(f_sel)}/{len(f_all)}" if f_all else "")
        self.right_count_lab.setText(f"{len(t_sel)}/{len(t_all)}" if t_all else "")

        total = len(self.entries)
        selected = len(f_sel) + len(t_sel)
        if total == 0:
            self.count_lab.setText("")
            self.select_all_btn.setText("全选")
        else:
            self.count_lab.setText(f"{total} 项 · 选 {selected}")
            self.select_all_btn.setText("全不选" if selected == total else "全选")

        self.btn_drag_files.setText(f"拖出选中的 {len(f_sel)} 个附件" if f_sel else "暂无选中附件")
        self.btn_copy_text.setText(f"合并复制选中的 {len(t_sel)} 段文字" if t_sel else "暂无选中文本")

    # ------------------------------------------------------------ 快捷操作与交付
    def toggle_select_all(self):
        # 全未选时点按钮应执行"全选"（all(空序列)=True 会导致永远全不选）
        all_selected = bool(self.entries) and all(e.get("on", False) for e in self.entries)
        target = not all_selected
        for e in self.entries:
            e["on"] = target
        self._commit()

    def _trigger_space_preview(self):
        """空格键极速快照预览（手感媲美 macOS QuickLook）：
        - 若当前预览弹窗已经打开，再次按空格直接关闭（Toggle 模式）
        - 优先取鼠标悬停卡片（_hovered_entry）
        - 其次取点击选中卡片（_selected_entry）
        - 再次取当前已勾选的第一项
        - 最后取素材列表的第一项
        """
        if self._preview_dlg is not None and self._preview_dlg.isVisible():
            self._preview_dlg.close()
            self._preview_dlg = None
            return

        entry = getattr(self, "_hovered_entry", None) or getattr(self, "_selected_entry", None)
        if not entry:
            for e in getattr(self, "entries", []):
                if e.get("on"):
                    entry = e
                    break
        if not entry and getattr(self, "entries", []):
            entry = self.entries[0]

        if entry:
            self.show_quick_preview(entry)

    def keyPressEvent(self, ev):
        if ev.key() == Qt.Key.Key_Space:
            self._trigger_space_preview()
            ev.accept()
            return
        super().keyPressEvent(ev)

    def show_quick_preview(self, entry: dict):
        if self._preview_dlg is not None:
            self._preview_dlg.close()
            self._preview_dlg = None
        self._preview_dlg = QuickPreviewPopup(entry, self)
        self._preview_dlg.show()

    def copy_single_entry(self, entry: dict):
        mime = QMimeData()
        if entry["kind"] == "text":
            mime.setText(entry["text"])
            self._write_own_clipboard(mime, self._suppress_signature([], entry["text"]))
        elif entry["kind"] == "image":
            p = self._entry_path(entry["name"])
            if os.path.exists(p):
                pm = QPixmap(p)
                mime.setImageData(pm.toImage())
                mime.setUrls([QUrl.fromLocalFile(p)])
                self._write_own_clipboard(mime, self._suppress_signature([p], ""))
        else:
            src = entry.get("src", "")
            if src and os.path.exists(src):
                mime.setUrls([QUrl.fromLocalFile(src)])
                mime.setText(src)
                self._write_own_clipboard(mime, self._suppress_signature([src], src))

    def copy_merged_text(self):
        text_entries = [e for e in self.entries if e["kind"] == "text" and e.get("on", False)]
        if not text_entries:
            return

        merged_text = "\n\n".join(e["text"].strip() for e in text_entries)
        mime = QMimeData()
        mime.setText(merged_text)
        self._write_own_clipboard(mime, self._suppress_signature([], merged_text))

        n = len(text_entries)
        orig_text = self.btn_copy_text.text()
        self.btn_copy_text.setText(f"已复制 {n} 段文字 · 去微信 Ctrl+V")
        QTimer.singleShot(1600, lambda: self.btn_copy_text.setText(orig_text))

    def delete_entry(self, entry: dict):
        if entry["kind"] == "image":
            try:
                p = self._entry_path(entry["name"])
                if os.path.exists(p):
                    os.remove(p)
            except OSError:
                pass
        if entry in self.entries:
            self.entries.remove(entry)
        self._commit()

    def open_entry(self, entry: dict):
        if entry["kind"] == "image":
            p = self._entry_path(entry["name"])
            if os.path.exists(p):
                try:
                    os.startfile(p)
                except OSError:
                    pass
        elif entry["kind"] == "file":
            src = entry.get("src", "")
            if src and os.path.exists(src):
                try:
                    # 列表参数形式杜绝命令注入（src 来自外部文件名，不可拼接进 shell）
                    subprocess.run(["explorer", f"/select,{src}"], check=False)
                except Exception:
                    try:
                        os.startfile(os.path.dirname(src))
                    except OSError:
                        pass

    # ------------------------------------------------------------ 拖拽实现
    def _toast(self, msg: str):
        """顶栏行内提示（零打扰原则：绝不弹任何系统通知）。

        【为什么必须实装】
        原实现只有一行 `return`，而全仓有 15 处调用点：
            "没有勾选的附件"、"N 个源文件已失效"、"路径已失效"、
            "打开失败: ..."、"已复制这一条"、"已加入快速访问"……
        它们【全部静默】。后果不是“少一句提示”，而是【失败与成功无法区分】：
        用户拖不动时不知道是因为没勾选，还是功能根本没做；复制成功了也
        看不到任何反馈 —— 这正是“这个功能一直实现不了”的另一半真相。

        同一产品里 _qtoast（快速访问页）已经建立了正确的行内反馈范式，
        本方法沿用同一思路，不新造弹窗、不抢焦点、不阻断操作。
        """
        lab = getattr(self, "toast_lab", None)
        if lab is None:
            # 可能在 _build_ui() 之前被调用（如 set_paused）：此时控件尚不存在，
            # 静默返回。绝不能在这里抛异常——调用方多为事件处理器，
            # PyQt6 下会走 qFatal 静默杀进程（见 BUG-001）。
            return
        lab.setText(msg)
        lab.setToolTip(msg)          # 长消息被截断时，悬停可看全文
        lab.show()
        timer = getattr(self, "_toast_timer", None)
        if timer is None:
            timer = QTimer(self)
            timer.setSingleShot(True)
            timer.timeout.connect(self._clear_toast)
            self._toast_timer = timer
        # 新消息到来时重置计时，避免连续操作时提示提前消失
        timer.start(TOAST_DURATION_MS)

    def _clear_toast(self):
        """自动淡出：到时清空并隐藏，不留残留。"""
        lab = getattr(self, "toast_lab", None)
        if lab is not None:
            lab.setText("")
            lab.setToolTip("")
            lab.hide()

    def start_batch_drag(self):
        """按住底栏按钮向外拖：整包拖出全部勾选附件"""
        files, missing = self._collect_drag_files()
        if missing:
            self._toast(f"{len(missing)} 个源文件已失效，已跳过")
        if not files:
            self._toast("没有勾选的附件")
            return
        self._execute_drag(files)

    def _on_drag_button_clicked(self):
        """兼容保留"""
        self.start_batch_drag()

    def _on_drag_button_clicked(self):
        """兼容保留"""
        self.start_batch_drag()

    # ------------------------------------------------------------ 右下角缩放
    def _resize_hot_rect(self) -> QRect:
        """缩放热区 = 【看得见的 ◢】 ∩ 【窗口真右下角】的并集。

        【为什么原本拖不动 —— 实测数据】
        ◢ 是由 layout 摆进去的（shelf_app.py:1461 grip_row.addStretch(1) 后
        addWidget），而 body 的 layout 边距是 v.setContentsMargins(14,10,14,12)
        （:1174），所以 ◢ 被推到了窗口边缘【内侧】：
            窗口 900x620 时 ◢ = QRect(867, 593, 18, 14)
        而原本的热区是“从窗口边缘算 18x18”：
            QRect(882, 602, 18, 18)
        两者交集只有 QRect(882,602,3,5) = 15 像素，即【按住 ◢ 只有 6.0%
        的面积能真的触发缩放】，◢ 的中心 (875,599) 实测 _near_resize_corner
        返回 False。用户照着 ◢ 拖，按到的却是热区外的空白 —— 这就是
        “右下角一直实现不了”的真因（三种窗口尺寸下错位比例完全一致）。

        修法：热区不再用硬编码的窗口边角，而是直接取 ◢ 的实际几何，
        保证【看得见 = 摸得着】；同时 united 上原来的右下角 18x18，
        不回归旧行为（贴着窗口边缘拖依然可以缩放）。
        """
        rect = QRect(self.width() - 18, self.height() - 18, 18, 18)
        lab = getattr(self, "size_hint_lab", None)
        if lab is not None and lab.isVisible():
            tl = lab.mapTo(self, QPoint(0, 0))
            visual = QRect(tl.x(), tl.y(), lab.width(), lab.height())
            # 向下右各留 6px 容差：手指/鼠标很难精准压在 18x14 的小图标上
            visual.adjust(0, 0, 6, 6)
            rect = rect.united(visual)
        return rect

    # ------------------------------------------------------------ 原生八向缩放
    def _resize_border_px(self) -> int:
        """边缘命中宽度（逻辑像素），按 DPR 放大保证好命中。

        实测：4K 屏 200% 缩放时 DPR=2.0，系统度量 SM_CXSIZEFRAME=5 +
        SM_CXPADDEDBORDER=8 = 13 物理像素，换算成逻辑像素只有 6.5 ——
        太窄了鼠标很难压准。按 RESIZE_BORDER_MIN_LOGICAL_PX 取下限。
        """
        dpr = self.devicePixelRatioF() or 1.0
        sys_px = _u32.GetSystemMetrics(SM_CXSIZEFRAME) + \
            _u32.GetSystemMetrics(SM_CXPADDEDBORDER)
        logical = sys_px / dpr if dpr else sys_px
        return max(int(round(logical)), RESIZE_BORDER_MIN_LOGICAL_PX)

    def _hit_test(self, cx: int, cy: int) -> int:
        """把客户区坐标映射成 WM_NCHITTEST 命中码（八向）。

        先判角再判边：角落是两条边的交集，必须先报角码，
        否则左上角会被当成左边而只能横向拉。
        """
        b = self._resize_border_px()
        w, h = self.width(), self.height()
        if cx < 0 or cy < 0 or cx >= w or cy >= h:
            return 0                        # 0 = 不接管，交给系统默认

        # [PROTECT TITLEBAR DRAG] When the cursor is inside the titlebar rect,
        # do NOT claim the edge - let eventFilter handle window dragging.
        # Otherwise WM_NCHITTEST returns non-HTCLIENT, Windows sends
        # WM_NCLBUTTONDOWN, and Qt's eventFilter never sees MouseButtonPress,
        # so titlebar dragging silently breaks.
        tb = getattr(self, "titlebar", None)
        if tb is not None and tb.isVisible():
            tb_rect = QRect(tb.mapTo(self, QPoint(0, 0)), tb.size())
            if tb_rect.contains(QPoint(cx, cy)):
                return 0

        left, right = cx < b, cx >= w - b
        top, bottom = cy < b, cy >= h - b

        if top and left:
            return HTTOPLEFT
        if top and right:
            return HTTOPRIGHT
        if bottom and left:
            return HTBOTTOMLEFT
        if bottom and right:
            return HTBOTTOMRIGHT
        if left:
            return HTLEFT
        if right:
            return HTRIGHT
        if top:
            return HTTOP
        if bottom:
            return HTBOTTOM
        return 0

    # nativeEvent 方案已废弃：WA_TranslucentBackground 的 layered window
    # 下 Windows 不派发 WM_NCHITTEST，且 WS_THICKFRAME 破坏圆角。
    # 改用 Qt 层面的八向缩放（mousePress/Move/Release + 光标反馈）。

    def _ensure_native_resize(self):
        """已废弃：不再补 WS_THICKFRAME（会破坏圆角且对半透明窗口无效）。"""
        pass

    def _near_resize_corner(self, pos) -> bool:
        """兼容旧接口：该点是否落在可缩放区域。"""
        return bool(self._hit_test(pos.x(), pos.y()))

    # ------------------------------------------------------------ 八向缩放（Qt 层面）
    # 为什么不用 nativeEvent + WS_THICKFRAME：
    #   WA_TranslucentBackground 的窗口是 layered window，Windows 不派发
    #   WM_NCHITTEST，且 WS_THICKFRAME 会破坏圆角（用户截图确认）。
    # Qt 层面的 mousePress/Move/Release 对半透明窗口完全可靠。

    _CURSOR_MAP = {
        HTLEFT: Qt.CursorShape.SizeHorCursor,
        HTRIGHT: Qt.CursorShape.SizeHorCursor,
        HTTOP: Qt.CursorShape.SizeVerCursor,
        HTBOTTOM: Qt.CursorShape.SizeVerCursor,
        HTTOPLEFT: Qt.CursorShape.SizeFDiagCursor,
        HTBOTTOMRIGHT: Qt.CursorShape.SizeFDiagCursor,
        HTTOPRIGHT: Qt.CursorShape.SizeBDiagCursor,
        HTBOTTOMLEFT: Qt.CursorShape.SizeBDiagCursor,
    }

    def mousePressEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton:
            hit = self._hit_test(ev.position().toPoint().x(),
                                 ev.position().toPoint().y())
            if hit:
                self._resizing = True
                self._resize_hit = hit
                self._resize_origin = ev.globalPosition().toPoint()
                self._resize_geo = self.geometry()
                self.grabMouse()
                return
        super().mousePressEvent(ev)

    def mouseMoveEvent(self, ev):
        if getattr(self, "_resizing", False) \
                and (ev.buttons() & Qt.MouseButton.LeftButton):
            gp = ev.globalPosition().toPoint()
            dx = gp.x() - self._resize_origin.x()
            dy = gp.y() - self._resize_origin.y()
            g = self._resize_geo
            hit = getattr(self, "_resize_hit", 0)
            x, y, w, h = g.x(), g.y(), g.width(), g.height()
            min_w, min_h = 320, 240

            if hit in (HTLEFT, HTTOPLEFT, HTBOTTOMLEFT):
                new_w = max(min_w, w - dx)
                x = x + w - new_w
                w = new_w
            if hit in (HTRIGHT, HTTOPRIGHT, HTBOTTOMRIGHT):
                w = max(min_w, w + dx)
            if hit in (HTTOP, HTTOPLEFT, HTTOPRIGHT):
                new_h = max(min_h, h - dy)
                y = y + h - new_h
                h = new_h
            if hit in (HTBOTTOM, HTBOTTOMLEFT, HTBOTTOMRIGHT):
                h = max(min_h, h + dy)

            self.setGeometry(x, y, w, h)
            return

        # 无按钮悬停的光标反馈由全局 eventFilter 统一处理：
        # 热区常被子控件覆盖，必须 setCursor 到【命中控件】上
        # （在这里调 self.setCursor 改写的是 Shelf 的光标，会被
        #  覆盖其上的子控件光标盖住，显示不出来）。
        super().mouseMoveEvent(ev)

    def mouseReleaseEvent(self, ev):
        if getattr(self, "_resizing", False):
            self._resizing = False
            self._resize_hit = 0
            self.releaseMouse()
            self.unsetCursor()
            # 缩放结束后恢复热区里被子控件改过的光标
            if self._scaled_cursor_widget is not None:
                self._scaled_cursor_widget.unsetCursor()
                self._scaled_cursor_widget = None
        super().mouseReleaseEvent(ev)

    def start_card_drag(self, entry: dict):
        """统一卡片拖拽入口：文本拖出纯文字；图片/文件拖本体（勾选卡片=整包）"""
        # 隐藏窗口上启动 QDrag 会原生崩溃（F9 竞速防护）
        if not self.isVisible():
            print("[Shelf] 窗口已隐藏，放弃本次拖出", file=sys.stderr, flush=True)
            return
        if entry["kind"] == "text":
            mime = QMimeData()
            mime.setText(entry["text"])
            self._drag_active = True
            try:
                drag = QDrag(self)
                drag.setMimeData(mime)
                drag.setPixmap(self._make_drag_pixmap(1))
                drag.setHotSpot(QPoint(30, 20))
                drag.exec(Qt.DropAction.CopyAction)
            finally:
                self._drag_active = False
                gc.collect()
            return
        self.start_files_drag(entry)

    def start_files_drag(self, entry: dict):
        selected_files = self._get_selected_files()
        # 产品铁律：默认全不选，on 的默认值必须为 False（全仓其余 12 处均为 False）。
        # 此处原写 True，与铁律相反。当前 entry 的 on 键总存在
        # （_add_entry / _load_manifest 均做 setdefault("on", False)），故该默认值
        # 分支不可达，不构成现行为错误；但属于同类地雷，统一为 False 以防未来回归。
        is_current_on = entry.get("on", False)
        if is_current_on and len(selected_files) > 1:
            drag_files = selected_files
        else:
            drag_files = self._get_entry_files(entry)

        if drag_files:
            self._execute_drag(drag_files)
        else:
            # 【不得静默】源文件已被移动/删除时，_get_entry_files 返回空，
            # 原本直接什么都不做 —— 用户拖了没反应也不知道为什么。
            self._toast("源文件已失效，无法拖出")
            print(f"[Shelf] 拖出中止：源文件已失效 kind={entry.get('kind')} "
                  f"name={entry.get('name')!r}", file=sys.stderr, flush=True)

    def _execute_drag(self, drag_files: list[str]):
        # F9 隐藏与拖拽启动存在竞速：窗口不可见时放弃拖拽（在隐藏窗口上启动 QDrag 会原生崩溃）
        if not self.isVisible():
            print("[Shelf] 窗口已隐藏，放弃本次拖出", file=sys.stderr, flush=True)
            return
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(f) for f in drag_files])

        drag = QDrag(self)
        drag.setMimeData(mime)
        drag.setPixmap(self._make_drag_pixmap(len(drag_files)))
        drag.setHotSpot(QPoint(30, 20))

        print(f"[Shelf] 开始直接拖出: {len(drag_files)} 个附件", file=sys.stderr, flush=True)
        self._drag_active = True
        try:
            drag.exec(Qt.DropAction.CopyAction)
        finally:
            self._drag_active = False
        # 拖拽结束：统一补处理拖拽期间积累的剪贴板事件
        if self._pending_clip:
            self._pending_clip = False
            QTimer.singleShot(0, self._on_clipboard_changed)
        gc.collect()

    def _get_entry_files(self, e: dict) -> list[str]:
        files = []
        if e["kind"] == "image":
            try:
                p = self._entry_path(e["name"])
                if os.path.exists(p):
                    files.append(p)
            except ValueError:
                pass
        elif e["kind"] == "file":
            src = e.get("src", "")
            if src and os.path.exists(src):
                files.append(src)
        return files

    def _get_selected_files(self) -> list[str]:
        files = []
        for e in self.entries:
            if not e.get("on", False):
                continue
            files.extend(self._get_entry_files(e))
        return files

    def _collect_drag_files(self):
        files = self._get_selected_files()
        missing = []
        for e in self.entries:
            if not e.get("on", False):
                continue
            if e["kind"] == "file":
                src = e.get("src", "")
                if not src or not os.path.exists(src):
                    missing.append(e["name"])
        return files, missing

    def _make_drag_pixmap(self, count: int) -> QPixmap:
        dpr = self.devicePixelRatioF()
        w, h = 90, 44
        pm = QPixmap(int(w * dpr), int(h * dpr))
        pm.setDevicePixelRatio(dpr)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        p.setBrush(QColor(30, 41, 59, 235))
        p.setPen(QColor("#2563eb"))
        p.drawRoundedRect(2, 2, 86, 40, 7, 7)
        p.setPen(QColor("white"))
        p.setFont(QFont("Microsoft YaHei UI", 9, QFont.Weight.Bold))
        text = f"{count} 项附件" if count > 1 else "1 项附件"
        p.drawText(QRect(2, 2, 86, 40), Qt.AlignmentFlag.AlignCenter, text)
        p.end()
        return pm

    # ------------------------------------------------------------ 交付与清空
    def copy_all_text(self):
        self.copy_merged_text()

    def deliver(self):
        files = self._get_selected_files()
        text_entries = [e for e in self.entries if e["kind"] == "text" and e.get("on", False)]
        text = "\n\n".join(e["text"] for e in text_entries)
        mime = QMimeData()
        if files:
            mime.setUrls([QUrl.fromLocalFile(f) for f in files])
        if text:
            mime.setText(text)
        self._write_own_clipboard(mime, self._suppress_signature(files, text))

    @staticmethod
    def _suppress_signature(files, text):
        return (frozenset(os.path.normpath(f) for f in files),
                hashlib.sha256(text.encode("utf-8", "ignore")).hexdigest() if text else "")

    def _write_own_clipboard(self, mime, signature):
        self._suppress_sig = signature
        self._suppress_until = time.time() + 1.5
        QGuiApplication.clipboard().setMimeData(mime)

    def open_shelf_dir(self):
        SHELF_DIR.mkdir(parents=True, exist_ok=True)
        try:
            os.startfile(SHELF_DIR)
        except OSError:
            pass

    def purge(self):
        try:
            existing = os.listdir(SHELF_DIR)
        except OSError:
            existing = []
        if not self.entries and not existing:
            return
        ret = QMessageBox.question(
            self, "清空托盘",
            "确定清空当前临时托盘？\n（注：每日工作日志已永久保存在 _History，不受任何影响）")
        if ret != QMessageBox.StandardButton.Yes:
            return

        for name in existing:
            try:
                p = self._entry_path(name)
            except ValueError:
                continue
            if os.path.isdir(p):
                shutil.rmtree(p, ignore_errors=True)
            else:
                try:
                    os.remove(p)
                except OSError:
                    pass
        self.entries = []
        self._last_text = ""
        self._last_img_hash = ""
        self._commit()
        # 触发主动内存深度清理与工作集收缩
        trim_working_set()

    # ------------------------------------------------------------ 窗口管理
    def show_and_activate(self):
        """外部唤醒/双击桌面快捷方式时调用：展开并置顶显示主窗口"""
        if getattr(self, "_collapsed", False):
            self._expand_from_block()
        else:
            self._place_top_right()
            self.show()
            self.raise_()
            self.activateWindow()

    def toggle_visible(self):
        if self.isVisible():
            self.hide()
            trim_working_set()
        else:
            self.show_and_activate()


    def toggle_pin(self):
        self._pinned = not self._pinned
        flags = self.windowFlags()
        if self._pinned:
            flags |= Qt.WindowType.WindowStaysOnTopHint
        else:
            flags &= ~Qt.WindowType.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        # 【关键】setWindowFlags 会重建窗口（HWND 重建后 DWM 圆角属性丢失），
        # 必须重设 DWM 圆角，否则切换置顶后四角变回直角。
        self._apply_rounded_corners()
        self._paint_pin_state()
        self.apply_look()
        self.show()
        self._toast("已置顶——永远浮在所有窗口上方" if self._pinned
                    else "已取消置顶——窗口可被其他窗口遮挡")

    def _paint_pin_state(self):
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
        self.pin_btn.setObjectName("pinBtn")

    def _is_self_drag(self, ev) -> bool:
        """判定拖拽源是否来自当前应用内部组件（防止放回自己时错误二次收录）"""
        if getattr(self, "_drag_active", False):
            return True
        src = ev.source()
        if src is not None:
            if src is self or (hasattr(src, "window") and src.window() is self):
                return True
        return False

    def dragEnterEvent(self, ev):
        if self._is_self_drag(ev):
            ev.ignore()
            return
        if ev.mimeData().hasUrls():
            ev.acceptProposedAction()

    def dragMoveEvent(self, ev):
        if self._is_self_drag(ev):
            ev.ignore()
            return
        if ev.mimeData().hasUrls():
            ev.acceptProposedAction()

    def dropEvent(self, ev):
        if self._is_self_drag(ev):
            ev.ignore()
            return
        locals_ = [u.toLocalFile() for u in ev.mimeData().urls() if u.isLocalFile()]
        if locals_:
            self._ingest_files(locals_)
        ev.acceptProposedAction()



# ------------------------------------------------------------------ 单实例保障
_server = None


def _ensure_stdio() -> None:
    r"""【P0 / BUG-007】windowed exe 下 sys.stdout/sys.stderr 是 None，必须先接住。

    实测结论（tests/e2e_launchui_ab_test.py，四组对照全部复现）：
        Failed to execute script 'shelf_app' due to unhandled exception:
        sys.stderr is None

    PyInstaller 以 console=False 打包时进程没有控制台，CPython 会把
    sys.stdout / sys.stderr 置为 None。而 main() 里的 faulthandler.enable()
    在 stderr 为 None 时【直接抛 RuntimeError: sys.stderr is None】（已单独
    复现验证）。这行异常发生在 QApplication 创建之前，于是界面 exe 100%
    起不来，用户双击只看到 PyInstaller 的崩溃对话框。

    与启动方式、环境变量均无关：os.startfile / subprocess.Popen、
    带 PYTHONHOME / 剥离 PYTHONHOME，四组全崩 —— 证明不是环境问题。

    顺带修掉一个连带缺陷：打包版里所有 print(..., file=sys.stderr) 的诊断
    输出全部静默丢失（print 到 None 是安全的，只是没地方去），现场无从
    排障。这里把 None 的 stdio 接到日志文件，一举两得。

    只在 stdio 为 None 时才接管：脚本模式与测试模式完全不受影响（零行为变化）。
    """
    if sys.stderr is not None and sys.stdout is not None:
        return
    try:
        f = open(APP_DIR / "shelf_app.log", "a", buffering=1,
                 encoding="utf-8", errors="replace")
    except OSError:
        # 日志文件都开不了（只读目录等）：退回黑洞，绝不能让启动失败
        try:
            f = open(os.devnull, "a", encoding="utf-8")
        except OSError:
            return
    if sys.stderr is None:
        sys.stderr = f
    if sys.stdout is None:
        sys.stdout = f


# ------------------------------------------------------------------ 快速指令区 UI 组件
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
            pin = QLabel()
            pin.setPixmap(_icon("pin", PALETTES.get(
                shelf.settings.get("theme", "dark"), PALETTES["dark"])["btn_primary"], 11).pixmap(11, 11))
            pin.setFixedWidth(14)
            h.addWidget(pin)
        col = QVBoxLayout()
        col.setSpacing(1)
        col.setContentsMargins(0, 0, 0, 0)
        nm_h = QHBoxLayout()
        nm_h.setSpacing(5)
        nm_h.setContentsMargins(0, 0, 0, 0)
        doc_ic = QLabel()
        doc_ic.setPixmap(_icon("doc", PALETTES.get(self.shelf.settings.get("theme", "dark"), PALETTES["dark"])["meta"], 12).pixmap(12, 12))
        nm_h.addWidget(doc_ic)
        nm_h.addWidget(QLabel(info["name"], objectName="cardName"))
        nm_h.addStretch(1)
        col.addLayout(nm_h)
        meta = f"{info["preview"]} · {info["chars"]}字" if info["preview"] \
            else f"{info["chars"]}字"
        col.addWidget(elided_label(meta, 380, "cardMeta"))
        h.addLayout(col, stretch=1)

    def mouseDoubleClickEvent(self, ev):
        self.shelf._prompt_copy(self.folder, self.info["name"])
        if ev is not None:
            super().mouseDoubleClickEvent(ev)


class PromptCategoryDialog(QDialog):
    """「加入快速」分类选择对话框：下拉直接选已有分类文件夹，也可输入新建。"""

    def __init__(self, shelf):
        super().__init__(shelf)
        self.shelf = shelf
        self.setWindowTitle("加入快速")
        self.setModal(True)
        self.setFixedSize(320, 205)
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
        v.setContentsMargins(16, 14, 16, 14)
        v.setSpacing(8)

        v.addWidget(QLabel("收进快速指令", objectName="previewTitle"))

        # 1. 已有分类下拉列表（带 📁 图标与清晰箭头）
        v.addWidget(QLabel("选择已有分类文件夹：", objectName="cardMeta"))
        self.combo = QComboBox()
        self.combo.setFixedHeight(32)
        folders = shelf.prompts.folders()
        if not folders:
            shelf.prompts.ensure_folder("默认")
            folders = shelf.prompts.folders()
        for f in folders:
            self.combo.addItem(f"📁 {f}", f)
        v.addWidget(self.combo)

        # 2. 新建分类输入框
        v.addWidget(QLabel("或新建分类文件夹：", objectName="cardMeta"))
        self.new_folder_edit = QLineEdit()
        self.new_folder_edit.setFixedHeight(30)
        self.new_folder_edit.setPlaceholderText("输入新分类名（留空则使用上方选中的分类）")
        v.addWidget(self.new_folder_edit)

        bts = QHBoxLayout()
        bts.setContentsMargins(0, 4, 0, 0)
        bts.addStretch(1)
        ok_btn = QPushButton("收进去")
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
        new_name = str(self.new_folder_edit.text()).strip()
        if new_name:
            return new_name
        data = self.combo.currentData()
        if data and str(data).strip():
            return str(data).strip()
        txt = str(self.combo.currentText()).strip()
        txt = txt.lstrip("📁 ").strip()
        return txt or "默认"


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
        v.addWidget(QLabel(name, objectName="previewTitle"))

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


def acquire_single_instance(on_activate=None) -> bool:
    global _server
    from PyQt6.QtNetwork import QLocalServer, QLocalSocket
    key = "SmartStagingShelf.LocalSocket"
    sock = QLocalSocket()
    sock.connectToServer(key)
    if sock.waitForConnected(300):
        # 说明已有实例在跑，发送唤醒信号并退出当前新实例
        try:
            sock.write(b"SHOW\n")
            sock.flush()
            sock.waitForBytesWritten(300)
            sock.disconnectFromServer()
        except Exception:
            pass
        return False

    QLocalServer.removeServer(key)
    _server = QLocalServer()
    if on_activate:
        def _handle_conn():
            client = _server.nextPendingConnection()
            if client:
                def _on_read():
                    try:
                        data = client.readAll().data().decode("utf-8", errors="ignore")
                        if "SHOW" in data:
                            on_activate()
                    except Exception:
                        pass
                    client.disconnectFromServer()
                client.readyRead.connect(_on_read)
        _server.newConnection.connect(_handle_conn)

    _server.listen(key)
    return True


def _enable_high_dpi():
    """开启 Windows 硬件级 Per-Monitor DPI Aware V2 原生高清渲染。
    彻底杜绝 Windows DWM 双线性插值拉伸导致的字体泛白发虚和低分辨率感！
    """
    if sys.platform == "win32":
        try:
            # Win10 1703+ DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = -4
            ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
        except Exception:
            try:
                # Win8.1 / Win10 早期：PROCESS_PER_MONITOR_DPI_AWARE = 2
                ctypes.windll.shcore.SetProcessDpiAwareness(2)
            except Exception:
                try:
                    ctypes.windll.user32.SetProcessDPIAware()
                except Exception:
                    pass


def main():
    _ensure_stdio()
    _enable_high_dpi()
    import faulthandler
    faulthandler.enable()                # 任何原生崩溃都在 stderr 留下完整调用栈
    try:
        QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    except Exception:
        pass
    app = QApplication(sys.argv)
    app.setApplicationName("SmartStagingShelf")
    app.setQuitOnLastWindowClosed(False)
    try:
        QPixmapCache.setCacheLimit(2048)
    except Exception:
        pass

    shelf_ref = []

    def _on_remote_activate():
        if shelf_ref and shelf_ref[0]:
            shelf_ref[0].show_and_activate()

    if not acquire_single_instance(_on_remote_activate):
        print("[Shelf] 已有实例在运行，已唤醒已有窗口")
        return 0

    shelf = Shelf()
    shelf_ref.append(shelf)
    shelf.ensure_watchdog()
    shelf.apply_look()

    # 启动模式解析：若包含 --tray 或 --minimized，则开机静默常驻托盘；否则正常弹出主窗口
    start_in_tray = ("--tray" in sys.argv) or ("--minimized" in sys.argv)
    if not start_in_tray:
        shelf.show_and_activate()
    else:
        trim_working_set()

    sys.exit(app.exec())



if __name__ == "__main__":
    main()

# -*- mode: python ; coding: utf-8 -*-
"""
轻松剪贴板 — PyInstaller 打包配置（onedir：启动快、杀软误报低）

【本配置的核心修正】此前只打包了界面进程 shelf_app.py，看守进程 watchdog.pyw
完全没有被打包。而按双进程架构（交接文档 §1）：
    看守 = 唯一常驻方，负责剪贴板捕获、每日日志、持有 F9/F10 全局热键
    界面 = 按需展示与交付，且【完全不监听剪贴板】
没有看守，装出来的产品根本不工作：不捕获任何内容、F9 也无反应。
因此这里打包【两个 EXE】到同一个 onedir 目录：

    dist/EasyClipboard/
    ├── 轻松剪贴板.exe          <- 界面进程（shelf_app.py）
    ├── 轻松剪贴板-看守.exe      <- 看守进程（watchdog.pyw）
    └── _internal/              <- 共享依赖（PyQt6 等）

两个 exe 名必须与源码常量一致，否则互相拉不起来：
    shelf_app.py : WD_EXE_NAME = "轻松剪贴板-看守.exe"
    watchdog.pyw : UI_EXE_NAME = "轻松剪贴板.exe"

【路径约定】两个进程在 frozen 模式下都以 sys.executable 的父目录为 APP_DIR
（见各自的 _resolve_app_dir()，实测于 tests/frozen_probe.py）。这样 _TempShelf /
_History / _Pinned / shelf_settings.json 都落在 dist/EasyClipboard/ 下，
而不是 _internal/ 里面 —— 否则用户覆盖安装时素材与日志会丢失。

【开机自启】注册表 Run 项必须指向【看守 exe】（界面侧 _autostart_command 已修正）。
"""

block_cipher = None

UI_NAME = "轻松剪贴板"
WD_NAME = "轻松剪贴板-看守"

# ------------------------------------------------------------------ Qt 模块裁剪
# 内存优化（用户要求运行内存控制到 100MB 量级）：
# 本机 PyQt6 全量安装共 109 个 Qt dll，若被 PyInstaller 的依赖分析拖进来，
# 安装包体积和运行时映射都会无谓膨胀。界面进程实际只用到
# QtCore / QtGui / QtWidgets / QtNetwork（单实例锁），其余模块一律排除
# —— 不参与 import 图，自然不打包、不加载、不占内存。
# 注意：若日后界面引入新 Qt 模块（比如 QtSvg 画矢量图标），需同步放行。
QT_EXCLUDES = [
    "PyQt6.QAxContainer", "PyQt6.QtBluetooth", "PyQt6.QtDBus",
    "PyQt6.QtDesigner", "PyQt6.QtHelp", "PyQt6.QtMultimedia",
    "PyQt6.QtMultimediaWidgets", "PyQt6.QtNfc", "PyQt6.QtOpenGL",
    "PyQt6.QtOpenGLWidgets", "PyQt6.QtPdf", "PyQt6.QtPdfWidgets",
    "PyQt6.QtPositioning", "PyQt6.QtPrintSupport", "PyQt6.QtQml",
    "PyQt6.QtQuick", "PyQt6.QtQuick3D", "PyQt6.QtQuickWidgets",
    "PyQt6.QtRemoteObjects", "PyQt6.QtSensors", "PyQt6.QtSerialPort",
    "PyQt6.QtSpatialAudio", "PyQt6.QtSql", "PyQt6.QtStateMachine",
    "PyQt6.QtSvg", "PyQt6.QtSvgWidgets", "PyQt6.QtTest",
    "PyQt6.QtTextToSpeech", "PyQt6.QtWebChannel", "PyQt6.QtWebSockets",
    "PyQt6.QtXml",
]

# -------------- 二进制/资源裁剪（实测于 2026-09-08 打包产物）--------------
# excludes 只能挡 Python 模块；Qt dll / 插件 / 翻译是 PyInstaller 的
# PyQt6 hooks 成批收集的，必须按文件名再砍一刀：
#   opengl32sw.dll  20MB  软件 OpenGL 兼容层（纯 2D 界面用不到）
#   Qt6Pdf.dll      4.5MB 模块已排除但 dll 被 hook 拖进来，不加载它只看名字
#   libcrypto/ssl   5MB+  应用只走本地 socket，不联网，不 import ssl
#   translations    6.8MB Qt 官方多语言包（界面是自定义中文文案）
#   冷门插件       qpdf/qsvg/qtga/qtiff/qwbmp/qwebp/qicns/qminimal/
#                  qoffscreen/qtuiotouchplugin/tls*/networkinformation
# 保留：qwindows 平台、styles、imageformats 的 qjpeg/qgif/qico
# （用户可能拖入 jpg/gif/ico 图片）。
_DROP_BIN_NAMES = {
    "opengl32sw.dll", "qt6pdf.dll", "libcrypto-3.dll", "libssl-3.dll",
    "qsvgicon.dll", "qpdf.dll", "qsvg.dll", "qtga.dll", "qtiff.dll",
    "qwbmp.dll", "qwebp.dll", "qicns.dll", "qminimal.dll", "qoffscreen.dll",
    "qtuiotouchplugin.dll", "qnetworklistmanager.dll",
    "qcertonlybackend.dll", "qopensslbackend.dll", "qschannelbackend.dll",
}


def _prune_analysis(analysis):
    analysis.binaries = [
        b for b in analysis.binaries
        if b[0].replace("\\", "/").rsplit("/", 1)[-1].lower() not in _DROP_BIN_NAMES
    ]
    analysis.datas = [
        d for d in analysis.datas
        if "translations" not in d[0].replace("\\", "/").lower()
        and "qt6pdf.dll" not in d[0].replace("\\", "/").lower()
    ]

# ------------------------------------------------------------------ 一体化主程序（界面与看护融合）
ui_analysis = Analysis(
    ["shelf_app.py"],
    pathex=[],
    binaries=[],
    datas=[('assets', 'assets')],
    hiddenimports=["keyboard", "prompts_store", "icons", "clipboard_watcher"],
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "numpy", "pandas", "scipy", "PIL", *QT_EXCLUDES],
    cipher=block_cipher,
    noarchive=False,
)
_prune_analysis(ui_analysis)
ui_pyz = PYZ(ui_analysis.pure, ui_analysis.zipped_data, cipher=block_cipher)
ui_exe = EXE(
    ui_pyz,
    ui_analysis.scripts,
    [],
    exclude_binaries=True,
    name=UI_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,                     # UPX 压缩会显著提高杀软误报率，禁用
    console=False,                 # 纯净图形应用：100% 绝无任何控制台黑框！
    icon='assets/app.ico',         # 挂载全新官方高清定制图标
)

# ------------------------------------------------------------------ 输出打包产物
coll = COLLECT(
    ui_exe,
    ui_analysis.binaries,
    ui_analysis.zipfiles,
    ui_analysis.datas,
    strip=False,
    upx=False,
    name="EasyClipboard",
)


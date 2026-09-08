#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
轻松剪贴板 · 常驻看守进程（无 Qt，纯 Python + Win32，常驻内存 ~10MB）

职责：
- 轮询剪贴板序列号（不打开剪贴板，零风险），变更时安全捕获：
  文字 → 暂存 manifest + 每日日志；图片 → BMP 落盘；文件引用 → 记录来源
- F9 呼出/隐藏界面进程（未运行则拉起）；F10 暂停/恢复捕获
- 与界面进程通过 _TempShelf 内信号文件通信，互不依赖
"""

import ctypes
import gc
import hashlib
import json
import os
import struct
import sys
import time
from datetime import datetime
from pathlib import Path

import keyboard


def trim_working_set() -> None:
    """看守进程工作集收缩：保持常驻物理内存在 3MB~8MB 的极低状态。"""
    try:
        gc.collect()
        if sys.platform == "win32":
            ctypes.windll.kernel32.SetProcessWorkingSetSize(
                ctypes.windll.kernel32.GetCurrentProcess(), -1, -1)
    except Exception:
        pass

# ------------------------------------------------------------------ 路径
def _resolve_app_dir() -> Path:
    """解析程序根目录，兼容【脚本运行】与【PyInstaller 打包】两种模式。

    必须与 shelf_app.py 的同名函数解析结果完全一致——两个进程靠
    _TempShelf 下的 manifest / .show_sig / .paused 文件通信，一旦两边
    算出不同的根目录，通信就断了。

    实测结论（PyInstaller 6.12 onedir，tests/frozen_probe.py 验证）：
    frozen 时 sys.executable 指向 exe 本体目录，而 __file__ 指向
    _internal 子目录，两者 dirname 不相同。若仍用 __file__，数据目录
    会被建到 _internal 里面，用户覆盖安装时素材与日志会丢失。
    """
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        # 若看守 exe 被收纳在 _internal 目录下（保证根目录仅唯一入口），
        # 则 APP_DIR 自动上溯为其父级目录，保证数据落盘在软件主根目录
        if exe_dir.name.lower() == "_internal":
            return exe_dir.parent
        return exe_dir
    return Path(os.path.dirname(os.path.abspath(__file__)))


APP_DIR = _resolve_app_dir()
SETTINGS_PATH = APP_DIR / "shelf_settings.json"
# [BUG-008 修复] 数据目录改为从 settings 读取（见下方 _cfg_dir）

MANIFEST_NAME = ".manifest.json"



# 界面进程可执行文件名（打包后与看守 exe 同目录）
UI_EXE_NAME = "轻松剪贴板.exe"
# 看守自己的互斥锁名（单实例）：界面进程也靠这个名字检测看守是否在跑
MUTEX_NAME = "EasyClipboardWatchdog"

CF_UNICODETEXT = 13
CF_HDROP = 15
CF_DIB = 8
GA_ROOT = 2

DEFAULTS = {"min_text_len": 2, "hotkey": "f9", "pause_hotkey": "f10"}


def load_cfg() -> dict:
    try:
        d = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
        d.update({k: v for k, v in DEFAULTS.items() if k not in d})
        return d
    except (OSError, ValueError):
        return dict(DEFAULTS)


CFG = load_cfg()


def _cfg_dir(key: str, default: Path) -> Path:
    """从 settings 取自定义数据目录。

    [BUG-008] 此前看守硬编码 APP_DIR/_TempShelf、APP_DIR/_History，
    从不看 settings 里的 shelf_dir / history_dir —— 打包版放到 dist/
    运行时，界面按 settings 读项目根素材目录、看守却把新捕获写到
    dist/ 下的默认目录，通信断裂、捕获的新条目界面看不到
    （2026-09-08 实测发生）。现在与界面规则一致：支持绝对路径，
    相对路径按 APP_DIR 解析；settings 缺失时回落默认目录。
    """
    raw = str(CFG.get(key) or "").strip()
    p = Path(raw) if raw else Path(default)
    if not p.is_absolute():
        p = APP_DIR / p
    return p.resolve()


SHELF_DIR = _cfg_dir("shelf_dir", APP_DIR / "_TempShelf")
HISTORY_DIR = _cfg_dir("history_dir", APP_DIR / "_History")
SHOW_SIG = SHELF_DIR / ".show_sig"
PAUSE_SIG = SHELF_DIR / ".paused"
MIN_TEXT_LEN = int(CFG.get("min_text_len", 2))
HOTKEY = str(CFG.get("hotkey", "f9"))
PAUSE_HOTKEY = str(CFG.get("pause_hotkey", "f10"))


def _ensure_stdio() -> None:
    """[P0/BUG-007 companion] windowed exe: sys.stderr is None -> all logs lost.

    The watchdog itself does NOT crash from this (print to None is safe; only
    faulthandler.enable() raises RuntimeError, and the watchdog never calls it).
    But the consequence is still severe: the handover doc says the FIRST thing
    to check is "does watchdog.log contain '看守启动'" -- and the packaged build
    produces no log at all, leaving field failures undiagnosable.

    Nothing in the source ever wrote watchdog.log: in script mode it was purely
    the product of external redirection (pythonw watchdog.pyw 2> watchdog.log).
    After packaging nobody redirects, so output vanished. Attaching the None
    stdio to a log file fixes both modes at once.

    Only takes over when stdio IS None -- script mode external redirection keeps
    working, so behaviour is unchanged there (zero-regression).
    """
    if sys.stderr is not None and sys.stdout is not None:
        return
    try:
        f = open(APP_DIR / "watchdog.log", "a", buffering=1,
                 encoding="utf-8", errors="replace")
    except OSError:
        try:
            f = open(os.devnull, "a", encoding="utf-8")
        except OSError:
            return
    if sys.stderr is None:
        sys.stderr = f
    if sys.stdout is None:
        sys.stdout = f


def log(msg: str):
    line = f"[WD {datetime.now():%H:%M:%S}] {msg}"
    print(line, file=sys.stderr, flush=True)


# ------------------------------------------------------------------ 剪贴板原语
user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
shell32 = ctypes.windll.shell32

# ------------------------------------------------------------------ Win32 签名声明
# 【P0 必修】ctypes 默认 restype = c_long（4 字节），argtypes 不校验。
# 在 64 位 Windows 上，返回句柄/指针的 API 实际返回 8 字节，会被直接截断：
#     GetClipboardData 真实值 0x0000020858D84CD0 → 截断后 0x58D84CD0
# 截断后的地址再交给 GlobalLock / wstring_at，必然 access violation。
#
# 实测证据：看守日志里反复出现的
#     循环异常(已忽略): exception: access violation reading 0x000000003A8C1B30
# 地址【高位全是 0】就是被截断的指针（tests/test_win32_signatures.py 验证）。
#
# 【纠正交接文档 §4 坑 #14 的错误诊断】那里把这些 access violation 归因为
# “与其他进程争抢剪贴板，捕获后跳过即可，实测已稳定”。真因是指针截断；
# try/except 只是把崩溃吞掉，后果是【文字/图片/文件全部捕获不到】，
# 产品核心功能静默失效。声明签名后仍保留那层 try/except（跨进程争抢确实存在），
# 但它不再是唯一防线。
_c = ctypes
_u32 = _c.c_uint32

# --- user32 ---
user32.GetClipboardSequenceNumber.restype = _u32
user32.GetClipboardSequenceNumber.argtypes = []
user32.OpenClipboard.restype = _c.c_bool
user32.OpenClipboard.argtypes = [_c.c_void_p]
user32.CloseClipboard.restype = _c.c_bool
user32.CloseClipboard.argtypes = []
user32.IsClipboardFormatAvailable.restype = _c.c_bool
user32.IsClipboardFormatAvailable.argtypes = [_u32]
user32.GetClipboardData.restype = _c.c_void_p      # HANDLE，必须 c_void_p
user32.GetClipboardData.argtypes = [_u32]

# --- kernel32 ---
kernel32.GlobalLock.restype = _c.c_void_p          # LPVOID，必须 c_void_p
kernel32.GlobalLock.argtypes = [_c.c_void_p]
kernel32.GlobalUnlock.restype = _c.c_bool
kernel32.GlobalUnlock.argtypes = [_c.c_void_p]
kernel32.GlobalSize.restype = _c.c_size_t          # SIZE_T
kernel32.GlobalSize.argtypes = [_c.c_void_p]
kernel32.CreateFileW.restype = _c.c_void_p         # HANDLE
kernel32.CreateFileW.argtypes = [_c.c_wchar_p, _u32, _u32, _c.c_void_p,
                                 _u32, _u32, _c.c_void_p]
kernel32.CloseHandle.restype = _c.c_bool
kernel32.CloseHandle.argtypes = [_c.c_void_p]
# 【P0】CreateMutexW 必须用 use_last_error=True，并通过 ctypes.get_last_error() 读取。
# 实测证明：直接调 kernel32.GetLastError() 拿到的不是 CreateMutexW 的错误码——
# ctypes 在两次 FFI 调用之间会自己调用其他 Win32 API（参数转换/内存管理），
# 那些调用会覆盖线程的 last error。
#     已存在时：kernel32.GetLastError() = 0（错）  ctypes.get_last_error() = 183（对）
# 后果是单实例锁【行为不确定】：误判 183 则看守直接退出（产品不工作），
# 漏判则多个看守同时跑（重复捕获、互相覆盖 manifest）。
kernel32.GetLastError.restype = _u32
kernel32.GetLastError.argtypes = []
# 裸函数也一并声明：单实例判定用下方的 use_last_error 包装器，
# 但 kernel32.CreateMutexW 这个入口仍然存在，不声明就会退回默认 c_long，
# 未来误用时又是一次指针截断。不变量：凡返回句柄/指针的 API 必须声明 restype。
kernel32.CreateMutexW.restype = _c.c_void_p        # HANDLE
kernel32.CreateMutexW.argtypes = [_c.c_void_p, _c.c_bool, _c.c_wchar_p]
CreateMutexW = _c.WINFUNCTYPE(
    _c.c_void_p, _c.c_void_p, _c.c_bool, _c.c_wchar_p,
    use_last_error=True)(("CreateMutexW", kernel32))
ERROR_ALREADY_EXISTS = 183

# --- shell32 ---
# HDROP 是句柄；lpszFile 传 None 时仅返回文件计数
shell32.DragQueryFileW.restype = _u32
shell32.DragQueryFileW.argtypes = [_c.c_void_p, _u32, _c.c_wchar_p, _u32]


def seq_number() -> int:
    return user32.GetClipboardSequenceNumber()


def open_clipboard() -> bool:
    return bool(user32.OpenClipboard(None))


def close_clipboard():
    user32.CloseClipboard()


def get_handle(fmt: int):
    return user32.GetClipboardData(fmt)


def get_text() -> str:
    h = get_handle(CF_UNICODETEXT)
    if not h:
        return ""
    ptr = kernel32.GlobalLock(h)
    if not ptr:
        return ""
    try:
        return ctypes.wstring_at(ptr)
    finally:
        kernel32.GlobalUnlock(h)


def get_files() -> list:
    h = get_handle(CF_HDROP)
    if not h:
        return []
    count = ctypes.windll.shell32.DragQueryFileW(h, 0xFFFFFFFF, None, 0)
    out = []
    buf = ctypes.create_unicode_buffer(2600)
    for i in range(count):
        if ctypes.windll.shell32.DragQueryFileW(h, i, buf, 2600):
            out.append(buf.value)
    return out


def get_dib() -> bytes:
    """CF_DIB → 可直接落盘的 BMP 字节（BITMAPFILEHEADER + DIB）"""
    h = get_handle(CF_DIB)
    if not h:
        return b""
    size = kernel32.GlobalSize(h)
    ptr = kernel32.GlobalLock(h)
    if not ptr or not size:
        kernel32.GlobalUnlock(h)
        return b""
    try:
        dib = ctypes.string_at(ptr, size)
    finally:
        kernel32.GlobalUnlock(h)
    # DIB 以 BITMAPINFOHEADER 开头；bmp 头 14 字节 + pal 估算
    header_size = struct.unpack_from("<I", dib, 0)[0] if len(dib) >= 4 else 40
    bpp = struct.unpack_from("<H", dib, 14)[0] if len(dib) >= 16 else 32
    pal = 0
    colors = struct.unpack_from("<I", dib, 32)[0] if len(dib) >= 36 else 0
    if bpp <= 8 and colors == 0:
        colors = 1 << bpp
    pal = colors * 4
    bf = struct.pack("<2sIHHI", b"BM", 14 + size, 0, 0, 14 + header_size + pal)
    return bf + dib


# ------------------------------------------------------------------ 暂存写入
def safe_dest(name: str) -> Path:
    name = os.path.basename(name).strip()
    if not name or name in {".", ".."} or ".." in name:
        name = "unnamed"
    dest = os.path.realpath(os.path.join(SHELF_DIR, name))
    real = os.path.realpath(SHELF_DIR)
    try:
        inside = os.path.commonpath([dest, real]) == real
    except ValueError:
        inside = False
    if not inside:
        raise ValueError(name)
    return Path(dest)


def unique_dest(name: str) -> Path:
    base, ext = os.path.splitext(os.path.basename(name))
    if not base:
        base = "unnamed"
    cand, i = f"{base}{ext}", 0
    while (safe_dest(cand)).exists():
        i += 1
        cand = f"{base}_{i}{ext}"
    return safe_dest(cand)


def load_manifest() -> list:
    p = SHELF_DIR / MANIFEST_NAME
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def save_manifest(entries: list):
    p = SHELF_DIR / MANIFEST_NAME
    p.write_text(json.dumps(entries, ensure_ascii=False), encoding="utf-8")


def append_journal(text: str, ts: str):
    try:
        HISTORY_DIR.mkdir(parents=True, exist_ok=True)
        today = datetime.now().strftime("%Y-%m-%d")
        fp = HISTORY_DIR / f"{today}.md"
        norm = text.strip()
        if fp.exists():
            body = fp.read_text(encoding="utf-8")
            # 严格解析并比对上一条日志正文，同内容连续复制绝不重复记录
            parts = [p.strip() for p in body.split("---") if p.strip()]
            if parts:
                lines = parts[-1].splitlines()
                last_content = "\n".join(lines[1:]).strip() if len(lines) > 1 else ""
                if last_content == norm:
                    return                          # 与上一条完全相同，去重不刷屏
        else:
            body = (f"# 剪贴板工作日志 — {today}\n\n"
                    f"> 记录今日复制与输入的文字碎片，"
                    f"沉淀为个人工作记忆与知识库。\n\n---\n\n")
        fp.write_text(body + f"### {ts}\n\n{norm}\n\n---\n\n",
                      encoding="utf-8")
    except OSError as e:
        log(f"日志写入失败: {e}")


def append_entry(entry: dict):
    entries = load_manifest()
    entries.append(entry)
    save_manifest(entries)


# ------------------------------------------------------------------ 捕获
def _commit_pending_text():
    """把 pending 的文本正式入账（manifest + 每日日志）。

    [去重=MRU 语义] 若本批次已有同内容（strip 归一化）的条目，
    不丢弃这次复制 —— 把已有条目【取到最上面】：移到 manifest 最新位置
    （列表尾部），并更新其时间戳；日志按流水照常记一笔。
    完全没见过的内容才新增条目。
    """
    pend = getattr(state, "pending_text", None)
    if not pend:
        return
    state.pending_text = None
    text, norm = pend["text"], pend["norm"]
    if norm == getattr(state, "last_text", None):
        # 连按去重（strip 归一化）：连续两次同内容只占一个位置
        return
    ts = datetime.now().strftime("%H:%M:%S")
    entries = load_manifest()
    for i, e in enumerate(entries):
        if e.get("kind") == "text" and str(e.get("text", "")).strip() == norm:
            entries.pop(i)                       # MRU：已有条目取到最新位置
            e["ts"] = ts
            entries.append(e)
            save_manifest(entries)
            state.last_text = norm
            append_journal(e.get("text", text), ts)
            log(f"文本上移 {len(e.get('text', text))} 字")
            return
    append_entry({"kind": "text", "text": text, "ts": ts})
    state.last_text = norm
    append_journal(text, ts)
    log(f"文本捕获 {len(text)} 字")


def flush_due_pending():
    """静默 0.7s 后把 pending 文本收账（主循环每 tick 都调用）。

    [BUG-009 防截段] 某些应用（AI 生成器/富文本编辑器）复制长文本时会把
    内容分多次连续写剪贴板（每次只放一部分），被 0.4s 轮询逐段捕获，
    一次复制在 manifest 和日志里被切成好几段。改为延迟合并：
    静默期收齐后才一次性入账。
    """
    pend = getattr(state, "pending_text", None)
    if pend and time.time() - pend["ts"] >= 0.7:
        _commit_pending_text()


def capture_text():
    text = get_text().replace("\x00", "")
    norm = text.strip()
    if not norm:
        return
    min_len = int(load_cfg().get("min_text_len", MIN_TEXT_LEN))
    if len(norm) < min_len:
        return                                  # 过滤小于最小字数的单字误触
    if norm == getattr(state, "last_text", None):
        return                                  # 连按去重（strip 归一化）
    # 批次内命中交由 commit 以 MRU 语义处理（取到最上面），此处不再拦截
    now = time.time()
    pend = getattr(state, "pending_text", None)
    if pend and (norm in pend["norm"] or pend["norm"] in norm):
        # 与 pending 有包含关系 = 同一次复制的不同长度版本，保留更长的；
        # 短版本进来不顶替，只刷新静默计时（防止流式回退写把长版冲掉）
        if len(norm) >= len(pend["norm"]):
            state.pending_text = {"text": text, "norm": norm, "ts": now}
        else:
            pend["ts"] = now
        return
    if pend:
        _commit_pending_text()                  # 内容无关：先给旧 pending 收账
    state.pending_text = {"text": text, "norm": norm, "ts": now}


def capture_dib():
    h = get_handle(CF_DIB)
    if not h:
        return
    size = kernel32.GlobalSize(h)
    ptr = kernel32.GlobalLock(h)
    if not ptr or not size:
        return
    try:
        dib = ctypes.string_at(ptr, size)
    finally:
        kernel32.GlobalUnlock(h)
    if len(dib) < 64:
        return
    hsha = hashlib.sha1(dib).hexdigest()
    if hsha == getattr(state, "last_dib_sha1", None):
        return                                  # 同图连击去重
    state.last_dib_sha1 = hsha
    header_size = struct.unpack_from("<I", dib, 0)[0]
    w, hh = struct.unpack_from("<ii", dib, 4)
    if w <= 0 or hh == 0:
        return
    ts = datetime.now()
    name = f"cap_{ts:%Y%m%d_%H%M%S}.bmp"
    dst = unique_dest(name)
    bf = struct.pack("<2sIHHI", b"BM", 14 + len(dib), 0, 0, 14 + header_size)
    dst.write_bytes(bf + dib)
    append_entry({"kind": "image", "name": dst.name,
                  "ts": ts.strftime("%H:%M:%S")})
    log(f"图片捕获 {w}x{hh}")


def capture_files():
    files = get_files()
    if not files:
        return
    key = tuple(sorted(os.path.realpath(f) for f in files))
    if key == getattr(state, "last_files", None):
        return                                  # 同批文件连击去重
    state.last_files = key
    entries = load_manifest()
    added = 0
    for src in files:
        real = os.path.realpath(src)
        if any(e["kind"] == "file" and e.get("src") == real for e in entries):
            continue
        size = 0
        if os.path.isfile(real):
            size = os.path.getsize(real)
        elif os.path.isdir(real):
            for root, _, fs in os.walk(real):
                for f in fs:
                    try:
                        size += os.path.getsize(os.path.join(root, f))
                    except OSError:
                        pass
        append_entry({"kind": "file", "name": os.path.basename(real),
                      "src": real, "size": size,
                      "ts": datetime.now().strftime("%H:%M:%S")})
        added += 1
    if added:
        log(f"文件引用捕获 {added} 个")


# ------------------------------------------------------------------ 看守循环
class state:
    last_seq = 0
    last_text = None
    pending_text = None      # debounce 中的待收账文本（防截段）
    last_dib_sha1 = None     # 上一张已捕获图片的 sha1（同图连击去重）
    last_files = None        # 上一批已捕获文件路径集合（同批连击去重）
    paused = False


def clipboard_event():
    """变更后安全读取一次并分发（仅此一处接触剪贴板内容）"""
    if not open_clipboard():
        return
    try:
        if user32.IsClipboardFormatAvailable(CF_DIB):
            capture_dib()
            return
        if user32.IsClipboardFormatAvailable(CF_HDROP):
            capture_files()
            return
        if user32.IsClipboardFormatAvailable(CF_UNICODETEXT):
            capture_text()
    finally:
        close_clipboard()


def ensure_dirs():
    SHELF_DIR.mkdir(parents=True, exist_ok=True)
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)


def ui_running() -> bool:
    try:
        GENERIC_RW = 0xC0000000
        h = kernel32.CreateFileW(r"\\.\pipe\SmartStagingShelf.LocalSocket",
                                 GENERIC_RW, 0, None, 3, 0, None)
        if h in (-1, 0xFFFFFFFFFFFFFFFF):
            return False
        kernel32.CloseHandle(h)
        return True
    except Exception:
        return False


def launch_ui():
    """拉起界面进程。区分打包态与开发态，两者可执行体完全不同。

    【打包态的关键坑】frozen 时 sys.executable 是【看守自己的 exe】。
    若仍走 subprocess.Popen([sys.executable, script])，会变成“看守启动看守”，
    被 main() 里的 CreateMutexW 单实例锁拦住后直接退出，界面永远起不来，
    表现为 F9 按下完全没反应。打包态必须直接启动同目录的界面 exe。
    """
    # 1) 打包态：看守与界面两个 exe 由同一个 spec 打包到同一目录
    if getattr(sys, "frozen", False):
        ui_exe = APP_DIR / UI_EXE_NAME
        if ui_exe.exists():
            os.startfile(str(ui_exe))    # noqa
            log(f"已拉起界面 exe: {ui_exe.name}")
        else:
            log(f"找不到界面 exe（预期：{ui_exe}），无法拉起")
        return

    # 2) 开发态：看守跑在项目根，可能指向已打包的 dist 产物（便于混合调试）
    ui_exe = APP_DIR / "dist" / "EasyClipboard" / "轻松剪贴板.exe"
    if ui_exe.exists():
        os.startfile(str(ui_exe))    # noqa
        return
    script = APP_DIR / "shelf_app.py"
    if script.exists():
        import subprocess
        # 3) 开发态：直接跑脚本。必须隔离可能被外部工具注入、会导致子进程
        #    启动即崩的环境变量（实测：PYTHONHOME 指向另一套 Python 时，子进程
        #    因 init_import_site / SRE module mismatch 直接 Fatal，表现为 F9 无反应）
        env = dict(os.environ)
        for k in ("PYTHONHOME", "PYTHONPATH"):
            env.pop(k, None)
        subprocess.Popen([sys.executable, str(script)], cwd=str(APP_DIR),
                         env=env,
                         creationflags=0x08000000)   # CREATE_NO_WINDOW
    else:
        log(f"找不到界面脚本（预期：{script}），无法拉起")


def main():
    _ensure_stdio()      # must precede any log(): stderr is None in windowed exe
    ensure_dirs()
    mutex = CreateMutexW(None, False, MUTEX_NAME)
    if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
        log("看守已在运行，退出")
        return

    # F9：唤起/隐藏界面（界面未运行则拉起）。
    # 信号文件若残留（界面关闭瞬间写入但无人消费），启动时清掉，防止新实例被误隐藏。
    try:
        SHOW_SIG.unlink(missing_ok=True)
    except OSError:
        pass

    def on_f9():
        if ui_running():
            try:
                SHOW_SIG.write_text("toggle", encoding="utf-8")
            except OSError:
                pass
        else:
            launch_ui()

    # F10：暂停/恢复捕获
    def on_f10():
        state.paused = not state.paused
        try:
            if state.paused:
                PAUSE_SIG.write_text("1", encoding="utf-8")
            else:
                PAUSE_SIG.unlink(missing_ok=True)
        except OSError:
            pass
        log(f"暂停捕获 = {state.paused}")

    keyboard.add_hotkey(HOTKEY, on_f9)
    keyboard.add_hotkey(PAUSE_HOTKEY, on_f10)
    log(f"看守启动 hotkey={HOTKEY}/{PAUSE_HOTKEY}")

    state.last_seq = seq_number()
    idle_ticks = 0
    while True:
        time.sleep(0.4)
        idle_ticks += 1
        if idle_ticks >= 100:  # 约 40 秒无剪贴板动作，自动执行一次轻量工作集收缩
            idle_ticks = 0
            trim_working_set()
        try:
            flush_due_pending()              # 静默期到 → 收账 pending 文本
            seq = seq_number()
            if seq == state.last_seq:
                continue
            state.last_seq = seq
            idle_ticks = 0                   # 发生剪贴板事件重置计时
            if state.paused:
                continue
            if open_clipboard():
                try:
                    if user32.IsClipboardFormatAvailable(CF_DIB):
                        _commit_pending_text()   # 动作切换：先把文字收账
                        capture_dib()
                        trim_working_set()
                    elif user32.IsClipboardFormatAvailable(CF_HDROP):
                        _commit_pending_text()
                        capture_files()
                        trim_working_set()
                    elif user32.IsClipboardFormatAvailable(CF_UNICODETEXT):
                        capture_text()
                finally:
                    close_clipboard()
        except Exception as e:
            log(f"循环异常(已忽略): {e}")


if __name__ == "__main__":
    main()

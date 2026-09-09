#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
轻松剪贴板 (EasyClipboard) — 内置剪贴板看护守护线程 (ClipboardWatcher)

将 Win32 剪贴板底层捕获、每日 Markdown 日志写入、防截段与去重机制
深度融合进主程序内部，彻底替代旧的独立命令行看守进程 (watchdog.pyw)，
实现真正的 All-in-One 单进程纯净运行。
"""

import ctypes
import hashlib
import json
import os
import struct
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import QObject, pyqtSignal

# ------------------------------------------------------------------ Win32 剪贴板常量
CF_UNICODETEXT = 13
CF_HDROP = 15
CF_DIB = 8

# ------------------------------------------------------------------ Win32 API 签名声明
_c = ctypes
_u32 = _c.c_uint32

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
shell32 = ctypes.windll.shell32

# user32
user32.GetClipboardSequenceNumber.restype = _u32
user32.GetClipboardSequenceNumber.argtypes = []
user32.OpenClipboard.restype = _c.c_bool
user32.OpenClipboard.argtypes = [_c.c_void_p]
user32.CloseClipboard.restype = _c.c_bool
user32.CloseClipboard.argtypes = []
user32.IsClipboardFormatAvailable.restype = _c.c_bool
user32.IsClipboardFormatAvailable.argtypes = [_u32]
user32.GetClipboardData.restype = _c.c_void_p
user32.GetClipboardData.argtypes = [_u32]

# kernel32
kernel32.GlobalLock.restype = _c.c_void_p
kernel32.GlobalLock.argtypes = [_c.c_void_p]
kernel32.GlobalUnlock.restype = _c.c_bool
kernel32.GlobalUnlock.argtypes = [_c.c_void_p]
kernel32.GlobalSize.restype = _c.c_size_t
kernel32.GlobalSize.argtypes = [_c.c_void_p]

# shell32
shell32.DragQueryFileW.restype = _u32
shell32.DragQueryFileW.argtypes = [_c.c_void_p, _u32, _c.c_wchar_p, _u32]


class ClipboardWatcher(QObject):
    """主程序内置的剪贴板看护器（后台守护线程）。

    功能：
    1. 监听 Win32 剪贴板序列号变化；
    2. 捕获文本（防截段 0.7s 防抖 + MRU 提序）；
    3. 捕获图片（DIB 转 BMP，sha1 去重）；
    4. 捕获文件（记录真实路径引用，同批去重）；
    5. 自动追加写入每日 Markdown 工作日志（_History/YYYY-MM-DD.md）；
    6. 更新 _TempShelf/.manifest.json，并通过 Qt 信号通知主界面秒级刷新。
    """

    entry_captured = pyqtSignal(dict)
    pause_state_changed = pyqtSignal(bool)

    def __init__(self, shelf_dir: Path, history_dir: Path, min_text_len: int = 2, parent=None):
        super().__init__(parent)
        self.shelf_dir = Path(shelf_dir)
        self.history_dir = Path(history_dir)
        self.min_text_len = int(min_text_len)
        self.manifest_name = ".manifest.json"

        self._running = False
        self._paused = False
        self._thread: Optional[threading.Thread] = None

        self._last_seq = 0
        self._last_text = None
        self._pending_text = None
        self._last_dib_sha1 = None
        self._last_files = None

        self._ensure_dirs()

    def _ensure_dirs(self):
        try:
            self.shelf_dir.mkdir(parents=True, exist_ok=True)
            self.history_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass

    def update_config(self, shelf_dir: Optional[Path] = None,
                      history_dir: Optional[Path] = None,
                      min_text_len: Optional[int] = None):
        """动态同步设置面板修改的目录与配置"""
        if shelf_dir is not None:
            self.shelf_dir = Path(shelf_dir)
        if history_dir is not None:
            self.history_dir = Path(history_dir)
        if min_text_len is not None:
            self.min_text_len = int(min_text_len)
        self._ensure_dirs()

    @property
    def is_paused(self) -> bool:
        return self._paused

    def set_paused(self, paused: bool):
        if self._paused != paused:
            self._paused = paused
            self.pause_state_changed.emit(self._paused)

    def toggle_pause(self) -> bool:
        self.set_paused(not self._paused)
        return self._paused

    def start(self):
        if self._running:
            return
        self._running = True
        self._last_seq = user32.GetClipboardSequenceNumber()
        self._thread = threading.Thread(target=self._worker_loop, daemon=True, name="ClipboardWatcher")
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        self._thread = None

    def _safe_dest(self, name: str) -> Path:
        name = os.path.basename(name).strip()
        if not name or name in {".", ".."} or ".." in name:
            name = "unnamed"
        dest = os.path.realpath(os.path.join(self.shelf_dir, name))
        real = os.path.realpath(self.shelf_dir)
        try:
            inside = os.path.commonpath([dest, real]) == real
        except ValueError:
            inside = False
        if not inside:
            raise ValueError(name)
        return Path(dest)

    def _unique_dest(self, name: str) -> Path:
        base, ext = os.path.splitext(os.path.basename(name))
        if not base:
            base = "unnamed"
        cand, i = f"{base}{ext}", 0
        while (self._safe_dest(cand)).exists():
            i += 1
            cand = f"{base}_{i}{ext}"
        return self._safe_dest(cand)

    def _load_manifest(self) -> list:
        p = self.shelf_dir / self.manifest_name
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []

    def _save_manifest(self, entries: list):
        p = self.shelf_dir / self.manifest_name
        try:
            p.write_text(json.dumps(entries, ensure_ascii=False, indent=1), encoding="utf-8")
        except OSError:
            pass

    def _append_journal(self, text: str, ts: str):
        """沉淀进每日 Markdown 工作日志"""
        try:
            self.history_dir.mkdir(parents=True, exist_ok=True)
            today = datetime.now().strftime("%Y-%m-%d")
            fp = self.history_dir / f"{today}.md"
            norm = text.strip()
            if fp.exists():
                body = fp.read_text(encoding="utf-8")
                parts = [p.strip() for p in body.split("---") if p.strip()]
                if parts:
                    lines = parts[-1].splitlines()
                    last_content = "\n".join(lines[1:]).strip() if len(lines) > 1 else ""
                    if last_content == norm:
                        return
            else:
                body = (f"# 剪贴板工作日志 — {today}\n\n"
                        f"> 记录今日复制与输入的文字碎片，"
                        f"沉淀为个人工作记忆与知识库。\n\n---\n\n")
            fp.write_text(body + f"### {ts}\n\n{norm}\n\n---\n\n", encoding="utf-8")
        except OSError:
            pass

    def _get_text(self) -> str:
        h = user32.GetClipboardData(CF_UNICODETEXT)
        if not h:
            return ""
        ptr = kernel32.GlobalLock(h)
        if not ptr:
            return ""
        try:
            return ctypes.wstring_at(ptr)
        finally:
            kernel32.GlobalUnlock(h)

    def _get_files(self) -> list:
        h = user32.GetClipboardData(CF_HDROP)
        if not h:
            return []
        count = shell32.DragQueryFileW(h, 0xFFFFFFFF, None, 0)
        out = []
        buf = ctypes.create_unicode_buffer(2600)
        for i in range(count):
            if shell32.DragQueryFileW(h, i, buf, 2600):
                out.append(buf.value)
        return out

    def _commit_pending_text(self):
        pend = self._pending_text
        if not pend:
            return
        self._pending_text = None
        text, norm = pend["text"], pend["norm"]
        if norm == self._last_text:
            return

        ts = datetime.now().strftime("%H:%M:%S")
        entries = self._load_manifest()

        # MRU 语义：已有同内容则置顶最新位置
        for i, e in enumerate(entries):
            if e.get("kind") == "text" and str(e.get("text", "")).strip() == norm:
                target_entry = entries.pop(i)
                target_entry["ts"] = ts
                entries.append(target_entry)
                self._save_manifest(entries)
                self._last_text = norm
                self._append_journal(target_entry.get("text", text), ts)
                self.entry_captured.emit(target_entry)
                return

        new_entry = {"kind": "text", "text": text, "ts": ts}
        entries.append(new_entry)
        self._save_manifest(entries)
        self._last_text = norm
        self._append_journal(text, ts)
        self.entry_captured.emit(new_entry)

    def _flush_due_pending(self):
        pend = self._pending_text
        if pend and (time.time() - pend["ts"] >= 0.7):
            self._commit_pending_text()

    def _capture_text(self):
        text = self._get_text().replace("\x00", "")
        norm = text.strip()
        if not norm or len(norm) < self.min_text_len:
            return
        if norm == self._last_text:
            return

        now = time.time()
        pend = self._pending_text
        if pend and (norm in pend["norm"] or pend["norm"] in norm):
            if len(norm) >= len(pend["norm"]):
                self._pending_text = {"text": text, "norm": norm, "ts": now}
            else:
                pend["ts"] = now
            return
        if pend:
            self._commit_pending_text()
        self._pending_text = {"text": text, "norm": norm, "ts": now}

    def _capture_dib(self):
        h = user32.GetClipboardData(CF_DIB)
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
        if hsha == self._last_dib_sha1:
            return
        self._last_dib_sha1 = hsha

        header_size = struct.unpack_from("<I", dib, 0)[0]
        w, hh = struct.unpack_from("<ii", dib, 4)
        if w <= 0 or hh == 0:
            return

        ts = datetime.now()
        name = f"cap_{ts:%Y%m%d_%H%M%S}.bmp"
        dst = self._unique_dest(name)
        bf = struct.pack("<2sIHHI", b"BM", 14 + len(dib), 0, 0, 14 + header_size)
        dst.write_bytes(bf + dib)

        entry = {"kind": "image", "name": dst.name, "ts": ts.strftime("%H:%M:%S")}
        entries = self._load_manifest()
        entries.append(entry)
        self._save_manifest(entries)
        self.entry_captured.emit(entry)

    def _capture_files(self):
        files = self._get_files()
        if not files:
            return
        key = tuple(sorted(os.path.realpath(f) for f in files))
        if key == self._last_files:
            return
        self._last_files = key

        entries = self._load_manifest()
        last_added = None
        for src in files:
            real = os.path.realpath(src)
            if any(e.get("kind") == "file" and e.get("src") == real for e in entries):
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
            entry = {
                "kind": "file",
                "name": os.path.basename(real),
                "src": real,
                "size": size,
                "ts": datetime.now().strftime("%H:%M:%S")
            }
            entries.append(entry)
            last_added = entry

        if last_added:
            self._save_manifest(entries)
            self.entry_captured.emit(last_added)

    def _worker_loop(self):
        while self._running:
            time.sleep(0.35)
            try:
                self._flush_due_pending()
                seq = user32.GetClipboardSequenceNumber()
                if seq == self._last_seq:
                    continue
                self._last_seq = seq

                if self._paused:
                    continue

                if user32.OpenClipboard(None):
                    try:
                        if user32.IsClipboardFormatAvailable(CF_DIB):
                            self._commit_pending_text()
                            self._capture_dib()
                        elif user32.IsClipboardFormatAvailable(CF_HDROP):
                            self._commit_pending_text()
                            self._capture_files()
                        elif user32.IsClipboardFormatAvailable(CF_UNICODETEXT):
                            self._capture_text()
                    finally:
                        user32.CloseClipboard()
            except Exception:
                pass

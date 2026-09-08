"""一次性编辑脚本：给 watchdog.pyw 落 BUG-009 修复（去重+防抖合并）。
执行后本文件可保留作变更记录。"""
from pathlib import Path

p = Path(r"E:\项目搭建\剪贴板\watchdog.pyw")
src = p.read_text(encoding="utf-8")

def rep(old, new, tag):
    global src
    assert src.count(old) == 1, f"{tag} 锚点匹配 {src.count(old)} 处"
    src = src.replace(old, new)

# 1) imports 加 hashlib
rep("import ctypes\nimport json\nimport os\nimport struct",
    "import ctypes\nimport hashlib\nimport json\nimport os\nimport struct",
    "imports")

# 2) capture_text 更换为 debounce 版本
OLD_CAPTURE = '''def capture_text():
    text = get_text().replace("\\x00", "")
    if not text.strip():
        return
    if text.strip() == getattr(state, "last_text", None):
        return                                  # 连按去重
    entries = load_manifest()
    if any(e["kind"] == "text" and e.get("text") == text for e in entries):
        return                                  # 已在暂存
    ts = datetime.now().strftime("%H:%M:%S")
    append_entry({"kind": "text", "text": text, "ts": ts})
    state.last_text = text
    append_journal(text, ts)
    log(f"文本捕获 {len(text)} 字")'''
NEW_CAPTURE = '''def _text_seen(norm: str) -> bool:
    """strip 归一化后的查重：本批次 manifest 里是否已有同内容文本。"""
    return any(e.get("kind") == "text" and str(e.get("text", "")).strip() == norm
               for e in load_manifest())


def _commit_pending_text():
    """把 pending 的文本正式入账（manifest + 每日日志）。"""
    pend = getattr(state, "pending_text", None)
    if not pend:
        return
    state.pending_text = None
    text, norm = pend["text"], pend["norm"]
    if norm == getattr(state, "last_text", None):
        return                                  # 连按去重（strip 归一化）
    if _text_seen(norm):
        return                                  # 已在暂存（strip 归一化）
    ts = datetime.now().strftime("%H:%M:%S")
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
    text = get_text().replace("\\x00", "")
    if not text.strip():
        return
    norm = text.strip()
    if norm == getattr(state, "last_text", None):
        return                                  # 连按去重（strip 归一化）
    if _text_seen(norm):
        return                                  # 批次内去重（strip 归一化）
    now = time.time()
    pend = getattr(state, "pending_text", None)
    if pend and (norm in pend["norm"] or pend["norm"] in norm):
        # 与 pending 有包含关系 = 同一次复制的更完整版本，替换 pending
        state.pending_text = {"text": text, "norm": norm, "ts": now}
        return
    if pend:
        _commit_pending_text()                  # 内容无关：先给旧 pending 收账
    state.pending_text = {"text": text, "norm": norm, "ts": now}'''
rep(OLD_CAPTURE, NEW_CAPTURE, "capture_text")

# 3) capture_dib 同图连击去重
rep('''    if len(dib) < 64:
        return
    header_size = struct.unpack_from("<I", dib, 0)[0]''',
    '''    if len(dib) < 64:
        return
    hsha = hashlib.sha1(dib).hexdigest()
    if hsha == getattr(state, "last_dib_sha1", None):
        return                                  # 同图连击去重
    state.last_dib_sha1 = hsha
    header_size = struct.unpack_from("<I", dib, 0)[0]''',
    "dib")

# 4) capture_files 同批连击去重
rep('''def capture_files():
    files = get_files()
    if not files:
        return
    entries = load_manifest()''',
    '''def capture_files():
    files = get_files()
    if not files:
        return
    key = tuple(sorted(os.path.realpath(f) for f in files))
    if key == getattr(state, "last_files", None):
        return                                  # 同批文件连击去重
    state.last_files = key
    entries = load_manifest()''',
    "files")

# 5) state 补字段
rep('''class state:
    last_seq = 0
    last_text = None
    paused = False''',
    '''class state:
    last_seq = 0
    last_text = None
    pending_text = None      # debounce 中的待收账文本（防截段）
    last_dib_sha1 = None     # 上一张已捕获图片的 sha1（同图连击去重）
    last_files = None        # 上一批已捕获文件路径集合（同批连击去重）
    paused = False''',
    "state")

# 6) 主循环 tick 首行 flush
rep('''    state.last_seq = seq_number()
    while True:
        time.sleep(0.4)
        try:
            seq = seq_number()''',
    '''    state.last_seq = seq_number()
    while True:
        time.sleep(0.4)
        try:
            flush_due_pending()              # 静默期到 → 收账 pending 文本
            seq = seq_number()''',
    "loop")

# 7) 非文本捕获前先结清文本
rep('''            if open_clipboard():
                try:
                    if user32.IsClipboardFormatAvailable(CF_DIB):
                        capture_dib()
                    elif user32.IsClipboardFormatAvailable(CF_HDROP):
                        capture_files()
                    elif user32.IsClipboardFormatAvailable(CF_UNICODETEXT):
                        capture_text()''',
    '''            if open_clipboard():
                try:
                    if user32.IsClipboardFormatAvailable(CF_DIB):
                        _commit_pending_text()   # 动作切换：先把文字收账
                        capture_dib()
                    elif user32.IsClipboardFormatAvailable(CF_HDROP):
                        _commit_pending_text()
                        capture_files()
                    elif user32.IsClipboardFormatAvailable(CF_UNICODETEXT):
                        capture_text()''',
    "dispatch")

p.write_text(src, encoding="utf-8")
print("ALL 7 EDITS OK")

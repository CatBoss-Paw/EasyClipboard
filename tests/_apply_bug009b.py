"""BUG-009 修正补丁：MRU 上移语义 + pending 保长版。

需求澄清（用户原话）：
  A->B->A 场景下，第二次复制 A 不该被丢弃，应把已有的 A 条目
  取到最上面（移到 manifest 最新位置 = 列表尾部，并更新时间戳）。
"""
from pathlib import Path

p = Path(r"E:\项目搭建\剪贴板\watchdog.pyw")
src = p.read_text(encoding="utf-8")

# ---- 1) _commit_pending_text：命中批次已有条目时 MRU 上移 ----
OLD = '''def _commit_pending_text():
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
    log(f"文本捕获 {len(text)} 字")'''
NEW = '''def _commit_pending_text():
    """把 pending 的文本正式入账（manifest + 每日日志）。

    [去重=MRU 语义] 若本批次已有同内容（strip 归一化）的条目，
    不丢弃这次复制 —— 把已有条目【取到最上面】：移到 manifest 最新位置
    （列表尾部），并更新 its 时间戳；日志按流水照常记一笔。
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
    log(f"文本捕获 {len(text)} 字")'''
assert src.count(OLD) == 1, f"commit 锚点 {src.count(OLD)}"
src = src.replace(OLD, NEW)

# ---- 2) capture_text：pending 替换只保更长版 ----
OLD = '''    if pend and (norm in pend["norm"] or pend["norm"] in norm):
        # 与 pending 有包含关系 = 同一次复制的更完整版本，替换 pending
        state.pending_text = {"text": text, "norm": norm, "ts": now}
        return'''
NEW = '''    if pend and (norm in pend["norm"] or pend["norm"] in norm):
        # 与 pending 有包含关系 = 同一次复制的不同长度版本，保留更长的；
        # 短版本进来不顶替，只刷新静默计时（防止流式回退写把长版冲掉）
        if len(norm) >= len(pend["norm"]):
            state.pending_text = {"text": text, "norm": norm, "ts": now}
        else:
            pend["ts"] = now
        return'''
assert src.count(OLD) == 1, f"pend 锚点 {src.count(OLD)}"
src = src.replace(OLD, NEW)

p.write_text(src, encoding="utf-8")
print("BUG009b EDITS OK")

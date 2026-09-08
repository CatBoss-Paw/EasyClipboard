"""BUG-009 回归测试：文本去重（strip 归一化）+ 防抖合并（防截段）+ 图片/文件连击跳过。

隔离方式：把 watchdog.pyw 复制到临时沙盒目录，并在旁边放置一份指向
沙盒数据目录的 shelf_settings.json —— 模块载入时 load_cfg/_cfg_dir 会
解析到沙盒，绝不触碰真实 _TempShelf / _History（产品铁律）。

覆盖：
  1) 连按去重按 strip 归一化比较（"abc" 与 "abc " 视为同一条）
  2) 本批次 manifest 内 strip 去重（已收账过就不再入）
  3) 防截段：增长式连续文本（"你好" → "你好世界"）合并为一条最长
  4) 防截段：静默 0.7s 后收账；未到期不收账
  5) 无包含关系的内容先给旧 pending 收账，不丢条目
  6) 图片同内容连击跳过（sha1）且文件落盘一次
  7) 同批文件连击跳过
"""
import importlib.machinery
import importlib.util
import json
import shutil
import sys
import tempfile
import time
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="wd_dedupe_"))
SANDBOX = TMP / "sandbox"
SANDBOX.mkdir(parents=True)

# 复制 watchdog 源码到沙盒，并放置指向沙盒数据目录的 settings
SRC = Path(__file__).resolve().parent.parent / "watchdog.pyw"
shutil.copy(SRC, SANDBOX / "watchdog.pyw")
(SANDBOX / "shelf_settings.json").write_text(json.dumps({
    "shelf_dir": str(TMP / "_TempShelf"),
    "history_dir": str(TMP / "_History"),
    "min_text_len": 2, "hotkey": "f9", "pause_hotkey": "f10",
}, ensure_ascii=False), encoding="utf-8")

# 载入沙盒模块（不执行 main）
loader = importlib.machinery.SourceFileLoader("wdtest", str(SANDBOX / "watchdog.pyw"))
spec = importlib.util.spec_from_loader("wdtest", loader)
wd = importlib.util.module_from_spec(spec)
loader.exec_module(wd)

# 沙盒断言：目录解析应指向 settings 指定目录（顺带验证 BUG-008）
real_shelf = Path(r"E:\项目搭建\剪贴板\_TempShelf").resolve()
assert wd.SHELF_DIR == (TMP / "_TempShelf").resolve(), wd.SHELF_DIR
assert wd.HISTORY_DIR == (TMP / "_History").resolve(), wd.HISTORY_DIR
assert wd.SHELF_DIR != real_shelf, "隔离失败：会污染真实数据"

PASS = 0
FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  PASS {name}")
    else:
        FAIL += 1
        print(f"  FAIL {name}  {detail}")


def reset():
    wd.state.last_text = None
    wd.state.pending_text = None
    wd.state.last_dib_sha1 = None
    wd.state.last_files = None
    (TMP / "_TempShelf").mkdir(parents=True, exist_ok=True)
    (TMP / "_History").mkdir(parents=True, exist_ok=True)
    for f in (TMP / "_TempShelf").glob("*"):
        if f.name != "draft.md":
            f.unlink()
    wd.save_manifest([])


def manifest():
    return wd.load_manifest()


def set_clip(text):
    wd.get_text = lambda: text
    wd.capture_text()


def commit_pending():
    pend = wd.state.pending_text
    if pend:
        pend["ts"] = time.time() - 10   # 直接成熟
    wd.flush_due_pending()


# ---- 1) strip 连击去重 ----
reset()
set_clip("hello")
commit_pending()
set_clip("hello ")   # 尾部多空格应视为同一条
commit_pending()
check("strip 归一化连击去重", len(manifest()) == 1,
      f"entries={len(manifest())}")

# ---- 2) 批次内 strip 去重 ----
reset()
set_clip("prompt 第一段")
commit_pending()
set_clip("prompt 第一段\n")   # 尾部换行差异
commit_pending()
check("批次内 strip 去重", len(manifest()) == 1, f"entries={len(manifest())}")

# ---- 3) 增长式连续文本合并为一条 ----
reset()
set_clip("提示词开头")
set_clip("提示词开头，这是更完整的一段")   # 与 pending 有包含关系 → 替换
set_clip("提示词开头")                      # 缩回去也算同族，仍含于 pending·norm
commit_pending()
ents = manifest()
check("增长式合并只留一条", len(ents) == 1, f"entries={len(ents)}")
check("合并后保留最长版本",
      bool(ents) and "更完整" in ents[0]["text"], repr(ents[:1]))

# ---- 4) 静默 0.7s 后才收账 ----
reset()
set_clip("到期测试")
wd.flush_due_pending()          # 立即 flush，时间未到期
check("未到期不收账", len(manifest()) == 0, f"entries={len(manifest())}")
commit_pending()                # 篡改时间戳 → 到期
check("到期后收账", len(manifest()) == 1)

# ---- 5) 无关联内容先给旧 pending 收账 ----
reset()
set_clip("完全不同的A")
set_clip("完全不同的B")         # 无包含关系 → 先收 A
check("无关联内容立即给旧 pending 收账", len(manifest()) == 1
      and manifest()[0]["text"] == "完全不同的A", repr(manifest()))
commit_pending()
check("两条都保留", len(manifest()) == 2, f"entries={len(manifest())}")

# ---- 6) 图片同内容连击跳过 ----
reset()
# 构造最小合法 DIB：header_size=40, w=2, h=2, bpp=32 → 2*2*4=16 字节像素
import struct as _st
# biSizeImage=32：总长 40+32=72 字节，过 capture_dib 的 64 字节下限
dib = _st.pack("<IiiHHIIiiII", 40, 2, 4, 1, 32, 0, 32, 2835, 2835, 0, 0) + b"\x00" * 32


class _FakeK32:
    @staticmethod
    def GlobalSize(h):
        return len(dib)

    @staticmethod
    def GlobalLock(h):
        return h

    @staticmethod
    def GlobalUnlock(h):
        return True


import ctypes as _ct
_dib_buf = _ct.create_string_buffer(dib, len(dib))  # 保持引用防 GC 悬垂
fake_data_addr = _ct.addressof(_dib_buf)
_k32_backup = wd.kernel32
_geth_backup = wd.get_handle
try:
    # ctypes.string_at 读的是 get_handle 返回的指针：直接让 get_handle 返回
    # 我们 buffer 的地址即可绕开系统调用
    wd.kernel32 = _FakeK32
    wd.kernel32.GlobalLock = staticmethod(lambda h: fake_data_addr)
    wd.get_handle = lambda fmt: 12345
    wd.capture_dib()
    wd.capture_dib()   # 同内容连击
    imgs = [e for e in manifest() if e["kind"] == "image"]
    check("同图连击只入一次", len(imgs) == 1, f"images={len(imgs)}")
    bmps = list((TMP / "_TempShelf").glob("cap_*.bmp"))
    check("同图连击只落盘一份", len(bmps) == 1, f"bmps={len(bmps)}")
finally:
    wd.kernel32 = _k32_backup
    wd.get_handle = _geth_backup

# ---- 6.5) MRU 上移语义：A -> B -> A 取到最上面 ----
reset()
set_clip("内容A")
commit_pending()
set_clip("内容B")
commit_pending()
ts_a_before = next(e for e in manifest() if e["text"] == "内容A")["ts"]
time.sleep(1.1)   # 保证时间戳文本变化可见（断言时戳更新）
set_clip("内容A")          # 再次复制 A：不是丢弃，是把 A 取到最新位置
commit_pending()
ents = manifest()
check("MRU：条目数不变（不重复入）", len(ents) == 2, f"entries={len(ents)}")
check("MRU：A 被取到最上面（移至末尾=最新）",
      len(ents) == 2 and ents[-1]["text"] == "内容A" and ents[0]["text"] == "内容B",
      repr([e["text"] for e in ents]))
check("MRU：A 时间戳已更新",
      len(ents) == 2 and ents[-1]["ts"] != ts_a_before,
      f"before={ts_a_before} after={ents[-1]['ts'] if ents else None}")

# ---- 7) 同批文件连击跳过 ----
reset()
f1 = TMP / "外部A.txt"
f1.write_text("x", encoding="utf-8")
wd.get_files = lambda: [str(f1)]
wd.capture_files()
wd.capture_files()   # 同批连击
files = [e for e in manifest() if e["kind"] == "file"]
check("同批文件连击只入一次", len(files) == 1, f"files={len(files)}")

print(f"\n=== 结果: {PASS} PASS, {FAIL} FAIL ===")
sys.exit(0 if FAIL == 0 else 1)

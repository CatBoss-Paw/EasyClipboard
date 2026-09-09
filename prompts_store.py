"""快捷指令区（提示词收藏夹）存储层 —— 纯 Python，不依赖 Qt。

布局（后台独立文件夹，默认 APP_DIR/_Prompts，可在 settings.prompts_dir 自定义）：

    _Prompts/
      _index.json          # 置顶与自定义排序元数据（事实源=文件系统，索引可重建）
      工作/
        起名神器.md         # 每段提示词 = 独立 MD 文档
        视频分镜提示词.md
      学习/
        费曼学习法.md

职责边界：看守进程完全不接触此目录（看守只负责捕获）。
"""
from __future__ import annotations

import json
import re
from pathlib import Path

# Windows 文件名保留字符统一清洗为空格
_INVALID = r'[\\/:*?"<>|\r\n\t]+'
MAX_NAME_LEN = 30          # 文档名严格上限 30 字（用户体验与UI排版铁律约束）
NAME_FROM_TEXT = 20        # 从文本首行提取默认名的推荐长度


def clean_name(raw: str, fallback: str = "未命名") -> str:
    """把任意文本清洗成合法文件名（不含扩展名），严格限制最多 30 个字符。"""
    name = re.sub(_INVALID, " ", str(raw or "")).strip()
    name = re.sub(r"\s+", " ", name).strip(" .")
    if not name:
        name = fallback
    return name[:MAX_NAME_LEN]


def default_doc_name(text: str) -> str:
    """从提示词文本生成默认文档名：
    1. 取首个非空行；
    2. 智能剔除行首 Markdown 排版符（如 #、>、-、*、数字标号等）；
    3. 严格截取前 20~30 字，杜绝超长文件名问题。
    """
    for line in str(text or "").splitlines():
        line = line.strip()
        if line:
            # 清理行首 Markdown 排版标记，取真实标题文字
            line = re.sub(r"^(#{1,6}\s+|>\s+|[-*+]\s+|\d+\.\s+)", "", line).strip()
            if line:
                cleaned = clean_name(line)
                return cleaned[:NAME_FROM_TEXT] or "未命名"
    return "未命名"


class PromptsStore:
    """分类文件夹 + 独立 MD 文档的增删改查与置顶排序。"""

    INDEX_NAME = "_index.json"

    def __init__(self, root):
        self.root = Path(root)
        # 懒创建：构造零写入（避免测试/未使用场景污染真实目录）；
        # 首次写入（ensure_folder/add_text 等）才会落盘。
        self.index_path = self.root / self.INDEX_NAME
        self._index = self._load_index()

    # ---------------------------------------------------------------- 索引
    def _load_index(self) -> dict:
        try:
            data = json.loads(self.index_path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                data.setdefault("folders", {})
                data.setdefault("docs", {})
                return data
        except (OSError, ValueError):
            pass
        return {"folders": {}, "docs": {}}

    def _save_index(self) -> None:
        try:
            self.index_path.write_text(
                json.dumps(self._index, ensure_ascii=False, indent=1),
                encoding="utf-8")
        except OSError:
            pass

    def _folder_meta(self, name: str) -> dict:
        return self._index["folders"].setdefault(name, {"pinned": False, "order": 0})

    def _doc_key(self, folder: str, name: str) -> str:
        return f"{folder}/{name}"

    def _doc_meta(self, folder: str, name: str) -> dict:
        return self._index["docs"].setdefault(
            self._doc_key(folder, name), {"pinned": False, "order": 0})

    # ---------------------------------------------------------------- 分类
    def folders(self) -> list[str]:
        """按 [置顶, order, 名称] 排序返回分类名（与磁盘实况对账后）。"""
        real = sorted([p.name for p in self.root.iterdir()
                       if p.is_dir()]) if self.root.exists() else []
        for name in real:
            self._folder_meta(name)           # 补登记磁盘上已有的分类
        # 清理已经不存在的分类登记
        stale = [n for n in self._index["folders"] if n not in real]
        for n in stale:
            self._index["folders"].pop(n, None)
        if stale:
            self._save_index()
        return sorted(real, key=lambda n: (
            not self._index["folders"].get(n, {}).get("pinned", False),
            self._index["folders"].get(n, {}).get("order", 0),
            n.lower()))

    def ensure_folder(self, name: str) -> str:
        name = clean_name(name, fallback="默认")
        (self.root / name).mkdir(parents=True, exist_ok=True)
        self._folder_meta(name)
        self._save_index()
        return name

    def rename_folder(self, old: str, new: str) -> str:
        new = clean_name(new, fallback=old)
        if new == old:
            return old
        src = self.root / old
        dst = self.root / new
        if not src.is_dir():
            raise FileNotFoundError(old)
        if dst.exists():
            raise FileExistsError(new)
        src.rename(dst)
        meta = self._index["folders"].pop(old, {"pinned": False, "order": 0})
        self._index["folders"][new] = meta
        # 迁移该分类下所有文档的索引键
        for key in [k for k in self._index["docs"] if k.startswith(f"{old}/")]:
            self._index["docs"][f"{new}/{key.split('/', 1)[1]}"] = \
                self._index["docs"].pop(key)
        self._save_index()
        return new

    def delete_folder(self, name: str) -> bool:
        """仅允许删除空分类；非空返回 False（UI 提示先移走文档）。"""
        d = self.root / name
        if not d.is_dir():
            return True
        if any(d.iterdir()):
            return False
        d.rmdir()
        self._index["folders"].pop(name, None)
        self._save_index()
        return True

    def toggle_folder_pin(self, name: str) -> bool:
        meta = self._folder_meta(name)
        meta["pinned"] = not meta.get("pinned", False)
        # 置顶分类 order 按最小值排前
        if meta["pinned"]:
            meta["order"] = min(
                [m.get("order", 0) for m in self._index["folders"].values()]
                or [0]) - 1
        self._save_index()
        return meta["pinned"]

    # ---------------------------------------------------------------- 文档
    def docs(self, folder: str) -> list[dict]:
        """返回分类下文档：{name, path, preview, chars, pinned, mtime}。"""
        d = self.root / folder
        out = []
        if not d.is_dir():
            self._folder_meta(folder)
            return out
        for f in sorted(d.glob("*.md")):
            name = f.stem
            meta = self._doc_meta(folder, name)
            text = ""
            chars = 0
            preview = ""
            try:
                text = f.read_text(encoding="utf-8", errors="ignore")
                chars = len(text)
                for line in text.splitlines():
                    if line.strip():
                        preview = line.strip()
                        break
            except OSError:
                pass
            out.append({
                "name": name,
                "path": str(f),
                "preview": preview[:60],
                "chars": chars,
                "pinned": bool(meta.get("pinned", False)),
                "mtime": f.stat().st_mtime if f.exists() else 0,
            })
        out.sort(key=lambda x: (
            not x["pinned"],
            self._index["docs"].get(self._doc_key(folder, x["name"]), {})
                .get("order", 0),
            x["name"].lower()))
        return out

    def _unique_doc_path(self, folder: str, name: str) -> Path:
        folder = self.ensure_folder(folder)
        name = clean_name(name)
        cand = self.root / folder / f"{name}.md"
        i = 2
        while cand.exists():
            suffix = f"_{i}"
            base = name[:max(1, MAX_NAME_LEN - len(suffix))]
            cand = self.root / folder / f"{base}{suffix}.md"
            i += 1
        return cand

    def add_text(self, text: str, folder: str, name: str = "") -> Path:
        """把一段提示词存为独立 MD 文档并入库，返回文件路径。"""
        if not str(text or "").strip():
            raise ValueError("empty text")
        folder = self.ensure_folder(folder)
        final_name = clean_name(name) if name else default_doc_name(text)
        path = self._unique_doc_path(folder, final_name)
        path.write_text(str(text), encoding="utf-8")
        self._doc_meta(folder, path.stem)
        self._save_index()
        return path

    def read_doc(self, folder: str, name: str) -> str:
        clean = name[:-3] if name.lower().endswith(".md") else name
        p = self.root / folder / f"{clean}.md"
        if not p.is_file():
            p = self.root / folder / name
        try:
            return p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return ""

    def write_doc(self, folder: str, name: str, content: str) -> None:
        meta = self._doc_meta(folder, name)     # 确保登记
        (self.root / folder / f"{name}.md").write_text(
            str(content), encoding="utf-8")
        self._save_index()

    def rename_doc(self, folder: str, old: str, new: str) -> str:
        new = clean_name(new, fallback=old)
        if new == old:
            return old
        src = self.root / folder / f"{old}.md"
        dst = self.root / folder / f"{new}.md"
        if not src.is_file():
            raise FileNotFoundError(old)
        if dst.exists():
            raise FileExistsError(new)
        src.rename(dst)
        key_old = self._doc_key(folder, old)
        if key_old in self._index["docs"]:
            self._index["docs"][self._doc_key(folder, new)] = \
                self._index["docs"].pop(key_old)
        self._save_index()
        return new

    def delete_doc(self, folder: str, name: str) -> None:
        try:
            (self.root / folder / f"{name}.md").unlink()
        except OSError:
            pass
        self._index["docs"].pop(self._doc_key(folder, name), None)
        self._save_index()

    def toggle_doc_pin(self, folder: str, name: str) -> bool:
        meta = self._doc_meta(folder, name)
        meta["pinned"] = not meta.get("pinned", False)
        self._save_index()
        return meta["pinned"]

    def move_doc(self, folder: str, name: str, to_folder: str) -> None:
        to_folder = self.ensure_folder(to_folder)
        src = self.root / folder / f"{name}.md"
        if not src.is_file():
            raise FileNotFoundError(name)
        dst = self._unique_doc_path(to_folder, name)
        src.rename(dst)
        key_old = self._doc_key(folder, name)
        if key_old in self._index["docs"]:
            self._index["docs"][self._doc_key(to_folder, dst.stem)] = \
                self._index["docs"].pop(key_old)
        self._save_index()

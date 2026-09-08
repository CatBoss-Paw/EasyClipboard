from pathlib import Path

p = Path(r"E:\项目搭建\剪贴板\shelf_app.py")
src = p.read_text(encoding="utf-8")
old = "    def mouseDoubleClickEvent(self, ev):\n        self.shelf._prompt_copy(self.folder, self.info[\"name\"])\n        super().mouseDoubleClickEvent(ev)"
new = "    def mouseDoubleClickEvent(self, ev):\n        self.shelf._prompt_copy(self.folder, self.info[\"name\"])\n        if ev is not None:\n            super().mouseDoubleClickEvent(ev)"
assert src.count(old) == 1, src.count(old)
src = src.replace(old, new)
p.write_text(src, encoding="utf-8")
print("OK")

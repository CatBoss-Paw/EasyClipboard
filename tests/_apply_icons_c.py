"""图标化替换（阶段C）：清剩余 emoji（帮助页返回、快速访问列表、置顶前缀、菜单、draft 拼接、按钮文本、doc 卡置顶）。"""
from pathlib import Path

p = Path(r"E:\项目搭建\剪贴板\shelf_app.py")
src = p.read_text(encoding="utf-8")

def rep(old, new, tag):
    global src
    assert src.count(old) == 1, f"{tag} 锚点 {src.count(old)}"
    src = src.replace(old, new)

# 帮助页返回按钮
rep('''        hback_btn = QPushButton("🔙 返回素材")''',
    '''        hback_btn = QPushButton(" 返回素材")
        hback_btn.setIcon(_icon("back", PALETTES.get(self.settings.get("theme", "dark"), PALETTES["dark"])["meta"]))
        hback_btn.setIconSize(QSize(12, 12))''',
    "hback")

# 快速访问列表行前缀
src = src.replace('f"📁 {p}"', 'f"文件夹  {p}"')
src = src.replace('f"📄 {p}"', 'f"文件      {p}"')
src = src.replace('f"⚠ 已失效: {p}"', 'f"已失效  {p}"')
src = src.replace('f"📁 {n}"', 'f"文件夹  {n}"')
src = src.replace('f"📄 {n}   ·   {fmt_size(os.path.getsize', 'f"文件      {n}   ·   {fmt_size(os.path.getsize')

# 分类列表置顶前缀：📌 → ●（置顶圆点，跨平台轻符号）
src = src.replace('("📌 " if self.prompts._index["folders"].get(f, {}).get("pinned") else "") + f',
                  '("● " if self.prompts._index["folders"].get(f, {}).get("pinned") else "") + f')
src = src.replace('folder 列表项可能带 📌 前缀，需剥离。', 'folder 列表项可能带 ● 前缀，需剥离。')
src = src.replace('folder.lstrip("📌 ")', 'folder.lstrip("● ")')
src = src.replace('item.text().lstrip("📌 ") if item is not None else ""',
                  'item.text().lstrip("● ") if item is not None else ""')
src = src.replace('item.text().lstrip("📌 ")', 'item.text().lstrip("● ")')

# 卡片右键菜单/快速访问
rep('''            a_add = menu.addAction("⚡ 加入快速…")''',
    '''            a_add = menu.addAction("加入快速…")''',
    "menuadd")

# draft 拼接/docstring
src = src.replace('f"📎 {e[\'name\']}（{fmt_size(e.get(\'size\', 0))}）"',
                  'f"附件  {e[\'name\']}（{fmt_size(e.get(\'size\', 0))}）"')

# 按钮文本 emoji
src = src.replace('self.btn_drag_files.setText(f"📦 拖出选中的 {len(f_sel)} 个附件" if f_s',
                  'self.btn_drag_files.setText(f"拖出选中的 {len(f_sel)} 个附件" if f_s')
src = src.replace('self.btn_copy_text.setText(f"✅ 已复制 {n} 段文字！去微信 Ctrl+V")',
                  'self.btn_copy_text.setText(f"已复制 {n} 段文字 · 去微信 Ctrl+V")')
src = src.replace('text = f"📦 {count} 项附件" if count > 1 else "📎 1 项附件"',
                  'text = f"{count} 项附件" if count > 1 else "1 项附件"')

# HELP_TEXT 小贴士里的 📌
src = src.replace('顶栏 📌 显示当前置顶状态', '顶栏图钉按钮显示当前置顶状态')

# PromptDocCard 置顶 label：📌 → pin 图标
rep('''        if info["pinned"]:
            pin = QLabel("📌", objectName="cardMeta")
            pin.setFixedWidth(16)
            h.addWidget(pin)''',
    '''        if info["pinned"]:
            pin = QLabel()
            pin.setPixmap(_icon("pin", PALETTES.get(
                shelf.settings.get("theme", "dark"), PALETTES["dark"])["btn_primary"], 11).pixmap(11, 11))
            pin.setFixedWidth(14)
            h.addWidget(pin)''',
    "docpin")

# PromptCategoryDialog 标题
rep('''        v.addWidget(QLabel("⚡ 收进快速指令", objectName="previewTitle"))''',
    '''        v.addWidget(QLabel("收进快速指令", objectName="previewTitle"))''',
    "catdlg")

p.write_text(src, encoding="utf-8")
print("ICONS-C OK")

"""修复 shelf_app.py 中因 heredoc 转义丢失产生的断行字符串。"""
from pathlib import Path

p = Path(r"E:\项目搭建\剪贴板\shelf_app.py")
src = p.read_text(encoding="utf-8")

NL = chr(10)   # 真换行
BS_N = chr(92) + "n"   # 字面 \n 两字符

old = 'empty = QLabel("这个分类还没有提示词' + NL + NL + '"' + NL + '                               "在首页的文字碎片卡片上，右键「加入快速」即可收进来",'
new = 'empty = QLabel("这个分类还没有提示词' + BS_N + BS_N + '"' + NL + '                               "在首页的文字碎片卡片上，右键「加入快速」即可收进来",'
assert src.count(old) == 1, f"count={src.count(old)}"
src = src.replace(old, new)
p.write_text(src, encoding="utf-8")
print("FIXED")

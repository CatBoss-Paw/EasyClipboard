# -*- coding: utf-8 -*-
import os
import sys
import shutil
import tempfile
from pathlib import Path

BASE_DIR = Path(r'E:\项目搭建\剪贴板')
sys.path.insert(0, str(BASE_DIR))

os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from PyQt6.QtWidgets import QApplication, QListWidgetItem
from PyQt6.QtCore import Qt

import shelf_app
from prompts_store import PromptsStore

app = QApplication.instance() or QApplication(sys.argv)

def test_all():
    tmp_root = Path(tempfile.mkdtemp(prefix='easyclip_test_'))
    print(f'[TEST] 临时根目录: {tmp_root}')
    try:
        pinned_dir = tmp_root / '_Pinned'
        pinned_dir.mkdir(parents=True, exist_ok=True)
        prompts_dir = tmp_root / '_Prompts'
        prompts_dir.mkdir(parents=True, exist_ok=True)

        shelf_app.PINNED_DIR = pinned_dir
        shelf_app.APP_DIR = tmp_root

        shelf = shelf_app.Shelf.__new__(shelf_app.Shelf)
        shelf.settings = {
            'pinned_dir': str(pinned_dir),
            'prompts_dir': str(prompts_dir),
            'theme': 'dark'
        }
        shelf.prompts = PromptsStore(prompts_dir)
        shelf.quick_list = shelf_app.QuickList(shelf)
        shelf.quick_hint_lab = None
        shelf.quick_header_lab = None
        shelf.quick_up_btn = None
        shelf.quick_current_dir = pinned_dir.resolve()
        shelf._toasts = []
        shelf._toast = lambda msg: shelf._toasts.append(msg)
        shelf._qtoast_msgs = []
        shelf._qtoast = lambda msg: shelf._qtoast_msgs.append(msg)

        # 1. 测试子文件夹层级建立
        sub1 = pinned_dir / '资料合集'
        sub1.mkdir(parents=True, exist_ok=True)
        sub_nested = sub1 / '深度子目录'
        sub_nested.mkdir(parents=True, exist_ok=True)

        # 2. 测试卡片收录：必须为 .md 格式，包含 Markdown 一级标题
        txt_entry = {'kind': 'text', 'text': '关于架构重构的调研\n这是详细的调研内容'}
        shelf.ingest_entry_to_pinned(txt_entry, subfolder='资料合集')
        
        md_files = list(sub1.glob('*.md'))
        txt_files = list(sub1.glob('*.txt'))
        assert len(md_files) == 1, '必须生成 .md 格式文件'
        assert len(txt_files) == 0, '绝不允许生成任何 .txt 文本'
        
        md_text = md_files[0].read_text(encoding='utf-8')
        assert md_text.startswith('# '), '生成的 MD 文件必须具备合规标题'
        assert '这是详细的调研内容' in md_text
        print('1. 卡片存入快速访问区严格为 .md 格式测试通过！')

        # 3. 测试层层打开文件夹
        item_folder = QListWidgetItem()
        item_folder.setData(Qt.ItemDataRole.UserRole, str(sub1))
        # 双击进入 sub1
        shelf._on_quick_item_double_clicked(item_folder)
        assert shelf.quick_current_dir == sub1.resolve()
        print('2. 双击进入第 1 层文件夹通过')

        # 双击进入深度子目录
        item_nested = QListWidgetItem()
        item_nested.setData(Qt.ItemDataRole.UserRole, str(sub_nested))
        shelf._on_quick_item_double_clicked(item_nested)
        assert shelf.quick_current_dir == sub_nested.resolve()
        print('3. 双击进入第 2 层深度文件夹（层层打开）通过')

        # 返回上一级
        shelf.quick_nav_up()
        assert shelf.quick_current_dir == sub1.resolve()
        shelf.quick_nav_up()
        assert shelf.quick_current_dir == pinned_dir.resolve()
        print('4. 返回上级导航（层层返回）通过')

        # 4. 原路拖放防重测试
        existing_file = str(md_files[0])
        shelf.quick_ingest_files([existing_file], target_dir=sub1, is_internal=False)
        assert shelf._qtoast_msgs[-1] == '原路拖放，无需复制'
        assert len(list(sub1.glob('*.md'))) == 1
        print('5. 原路拖放防重且不产生 _1 副本测试通过')

        print('\n=== 全部关键升级项 100% 验证通过！===')
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)

if __name__ == '__main__':
    test_all()

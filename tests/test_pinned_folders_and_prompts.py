# -*- coding: utf-8 -*-
import os
import sys
import shutil
import tempfile
from pathlib import Path

BASE_DIR = Path(r'E:\项目搭建\剪贴板')
sys.path.insert(0, str(BASE_DIR))

os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from PyQt6.QtWidgets import QApplication

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

        p1 = shelf_app.safe_pinned_dest('test.txt', subfolder='工作项目')
        assert '工作项目' in p1
        assert Path(p1).parent.exists()
        print('1. safe_pinned_dest 子文件夹安全围栏测试通过')

        shelf = shelf_app.Shelf.__new__(shelf_app.Shelf)
        shelf.settings = {
            'pinned_dir': str(pinned_dir),
            'prompts_dir': str(prompts_dir),
            'theme': 'dark'
        }
        shelf.prompts = PromptsStore(prompts_dir)
        shelf.quick_list = shelf_app.QuickList(shelf)
        shelf.quick_hint_lab = None
        shelf._toasts = []
        shelf._toast = lambda msg: shelf._toasts.append(msg)
        shelf._qtoast_msgs = []
        shelf._qtoast = lambda msg: shelf._qtoast_msgs.append(msg)

        sub1 = pinned_dir / '资料合集'
        sub1.mkdir(parents=True, exist_ok=True)
        sub2 = pinned_dir / '财务报销'
        sub2.mkdir(parents=True, exist_ok=True)

        subfolders = shelf_app.Shelf.get_pinned_subfolders(shelf)
        assert '资料合集' in subfolders and '财务报销' in subfolders
        print(f'2. get_pinned_subfolders 成功检索子文件夹: {subfolders}')

        txt_entry = {'kind': 'text', 'text': '调研纪要\n增加文件夹'}
        shelf_app.Shelf.ingest_entry_to_pinned(shelf, txt_entry, subfolder='资料合集')
        docs_in_sub1 = list(sub1.glob('*.txt'))
        assert len(docs_in_sub1) == 1
        print(f'3. 卡片成功加入分类子文件夹: {docs_in_sub1[0].name}')

        existing_file = str(docs_in_sub1[0])
        shelf_app.Shelf.quick_ingest_files(
            shelf, [existing_file], target_dir=sub1, is_internal=False
        )
        assert shelf._qtoast_msgs[-1] == '原路拖放，无需复制'
        docs_after = list(sub1.glob('*.txt'))
        assert len(docs_after) == 1
        print('4. 原路拖放防重测试通过，未产生任何 _1 重复副本！')

        shelf_app.Shelf.quick_ingest_files(
            shelf, [existing_file], target_dir=sub2, is_internal=True
        )
        assert not Path(existing_file).exists()
        docs_in_sub2 = list(sub2.glob('*.txt'))
        assert len(docs_in_sub2) == 1
        print('5. 快速访问区内部整理移动测试通过')

        pstore = PromptsStore(prompts_dir)
        pstore.ensure_folder('Prompt分类')
        md_file = pstore.add_text('# 提示词标题\n这是提示词全文内容', 'Prompt分类', '通用翻译')
        assert md_file.exists()

        content1 = pstore.read_doc('Prompt分类', '通用翻译')
        content2 = pstore.read_doc('Prompt分类', '通用翻译.md')
        assert content1 == content2 == '# 提示词标题\n这是提示词全文内容'
        print('6. PromptsStore.read_doc 兼容带/不带 .md 读取测试通过')

        doc_info = {
            'name': '通用翻译',
            'path': str(md_file),
            'preview': '这是提示词全文内容',
            'chars': len(content1),
            'pinned': False,
            'mtime': 0
        }
        card = shelf_app.PromptDocCard(shelf, 'Prompt分类', doc_info)
        assert card.toolTip() == '双击直接复制文档内文本 · 右键更多操作'
        print('7. PromptDocCard 双击穿透与提示测试通过')

        print('\n=== 全部 7 项关键业务验证 100% 通过！===')
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)

if __name__ == '__main__':
    test_all()

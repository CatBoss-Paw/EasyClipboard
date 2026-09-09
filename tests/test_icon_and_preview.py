import sys, os, tempfile
from pathlib import Path
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt

app = QApplication.instance() or QApplication(sys.argv)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import shelf_app
from shelf_app import Shelf, ShelfCard, QuickPreviewPopup

print('--- 开始测试：系统原生图标提取与空格极速预览 ---')

with tempfile.TemporaryDirectory() as td:
    tpath = Path(td)
    # 创建一个测试文件夹
    test_dir = tpath / '2026-09-07_测试文件夹'
    test_dir.mkdir()
    
    # 创建一个测试文档
    test_doc = tpath / '财务报表.xlsx'
    test_doc.write_text('dummy excel content', encoding='utf-8')
    
    shelf = Shelf()
    
    # 1. 测试文件夹卡片图标
    folder_entry = {
        'id': 'f1',
        'kind': 'file',
        'name': test_dir.name,
        'src': str(test_dir),
        'is_dir': True,
        'ts': '06:45:00',
        'on': False
    }
    card_folder = ShelfCard(folder_entry, shelf, is_file_col=True)
    badge_folder = card_folder._create_badge()
    # 验证不是 FILE 徽标
    assert getattr(badge_folder, 'text', lambda: '')() != 'FILE', '文件夹不应显示为 FILE 徽标'
    assert badge_folder.pixmap() is not None and not badge_folder.pixmap().isNull(), '文件夹应成功生成图标'
    print('✅ 1. 文件夹原生图标提取通过！不再显示为 FILE！')
    
    # 2. 测试文件原生图标提取
    doc_entry = {
        'id': 'f2',
        'kind': 'file',
        'name': test_doc.name,
        'src': str(test_doc),
        'is_dir': False,
        'ts': '06:45:00',
        'size': 1024,
        'on': False
    }
    card_doc = ShelfCard(doc_entry, shelf, is_file_col=True)
    badge_doc = card_doc._create_badge()
    assert badge_doc.pixmap() is not None and not badge_doc.pixmap().isNull(), '真实文件应提取到系统关联图标'
    print('✅ 2. 真实文件系统关联图标提取通过！')
    
    # 3. 测试空格极速预览触发
    shelf._hovered_entry = folder_entry
    shelf._trigger_space_preview()
    assert shelf._preview_dlg is not None, '空格应成功触发极速快照预览弹窗'
    assert shelf._preview_dlg.isVisible(), '预览弹窗应处于显示状态'
    print('✅ 3. 空格键极速预览触发通过！')
    
    # 4. 测试再次按空格关闭（Toggle 模式）
    shelf._trigger_space_preview()
    assert shelf._preview_dlg is None, '再次按空格应瞬间关闭预览弹窗'
    print('✅ 4. 再次按空格瞬间关闭预览（Toggle）通过！')

print('\n🎉 全部图标与空格预览测试 100% 通过！')

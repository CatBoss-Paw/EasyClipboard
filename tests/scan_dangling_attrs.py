#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
静态扫描器：找出类内"只读未写"的悬空属性引用。

目的（Rule 3 / 2D 同模式扫描）：
    DragOutButton.mouseMoveEvent 从 ShelfCard 复制粘贴而来，引用了本类不存在的
    self._drag_start_pos / self.shelf / self.entry，导致 AttributeError。
    PyQt6 中此类异常发生在事件处理器内 = qFatal 静默杀进程。
    本扫描器系统性排查全文件，避免同类漏改点残留。

原理：
    对每个 ClassDef，收集
      W = 该类内所有 `self.X = ...` / `for self.X` / `del self.X` 的赋值目标名
      R = 该类内所有 `self.X` 的读取名
    候选悬空 = R - W - 该类自己定义的方法名 - 已知基类属性白名单
    基类属性无法静态解析，故输出为"需人工确认"，由人工判定是否真悬空。
"""
import ast
import sys
from pathlib import Path

TARGET = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("shelf_app.py")

tree = ast.parse(TARGET.read_text(encoding="utf-8"))

# PyQt/Qt 基类常见属性，静态上确实"只读未写"但合法
BASE_ATTR_WHITELIST = {
    "width", "height", "x", "y", "geometry", "rect", "size", "pos",
    "window", "parent", "children", "style", "font", "palette",
    "cursor", "toolTip", "objectName", "isVisible", "focusPolicy",
    "layout", "model", "viewport", "text", "icon", "sizeHint",
}


class SelfAttrCollector(ast.NodeVisitor):
    """收集一个 ClassDef 内的 self.X 写集合与读集合（含方法名与行号）"""

    def __init__(self):
        self.writes = set()
        self.reads = {}      # name -> [lineno...]
        self.methods = set()
        self.class_attrs = set()

    def visit_FunctionDef(self, node):
        self.methods.add(node.name)
        # 类属性级赋值（ClassDef 直接子节点里的 self.X = ...）
        self.generic_visit(node)

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Assign(self, node):
        for t in node.targets:
            self._collect_target(t)
        self.generic_visit(node)

    def visit_AugAssign(self, node):
        self._collect_target(node.target)
        self.generic_visit(node)

    def visit_AnnAssign(self, node):
        self._collect_target(node.target)
        self.generic_visit(node)

    def visit_For(self, node):
        self._collect_target(node.target)
        self.generic_visit(node)

    def visit_Delete(self, node):
        for t in node.targets:
            self._collect_target(t)
        self.generic_visit(node)

    def _collect_target(self, t):
        # self.X = ...
        if isinstance(t, ast.Attribute) and isinstance(t.value, ast.Name) \
                and t.value.id == "self":
            self.writes.add(t.attr)
        elif isinstance(t, (ast.Tuple, ast.List)):
            for e in t.elts:
                self._collect_target(e)

    def visit_Attribute(self, node):
        if isinstance(node.value, ast.Name) and node.value.id == "self":
            # 非赋值目标位置一律算读取（赋值目标已由 _collect_target 记录）
            if isinstance(node.ctx, ast.Load):
                self.reads.setdefault(node.attr, []).append(node.lineno)
            elif isinstance(node.ctx, ast.Store):
                self.writes.add(node.attr)
        self.generic_visit(node)


report = []
for node in tree.body:
    if not isinstance(node, ast.ClassDef):
        continue
    c = SelfAttrCollector()
    for sub in node.body:
        c.visit(sub)
    # ClassDef 直接的类属性赋值（X = pyqtSignal()）
    for sub in node.body:
        if isinstance(sub, ast.Assign):
            for t in sub.targets:
                if isinstance(t, ast.Name):
                    c.class_attrs.add(t.id)
        elif isinstance(sub, ast.AnnAssign) and isinstance(sub.target, ast.Name):
            c.class_attrs.add(sub.target.id)

    dangling = {
        k: v for k, v in c.reads.items()
        if k not in c.writes
        and k not in c.methods
        and k not in c.class_attrs
        and k not in BASE_ATTR_WHITELIST
    }
    if dangling:
        report.append((node.name, node.lineno, dangling))

if not report:
    print("未发现悬空属性引用。")
    sys.exit(0)

print("=" * 78)
print("悬空属性扫描报告：%s" % TARGET.name)
print("=" * 78)
for cls, lineno, dangling in report:
    print("\nclass %s (line %d)" % (cls, lineno))
    for attr, lines in sorted(dangling.items()):
        uniq = sorted(set(lines))
        shown = ", ".join(str(x) for x in uniq[:12])
        more = " ..." if len(uniq) > 12 else ""
        print("    self.%-24s 只读未写 @ %s%s" % (attr, shown, more))
print("\n注：基类（QWidget/QFrame/QPushButton/QDialog/QListWidget 等）提供的属性")
print("    无法静态解析，需人工确认；重点看以 _ 开头的私有属性，它们几乎不可能来自基类。")

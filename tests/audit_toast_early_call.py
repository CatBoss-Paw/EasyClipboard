#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AST 核实：_toast 的哪些调用点真的可能在 _build_ui() 之前被触发？

为什么必须核实（而不是假设）：
    我给 _toast 加了 `lab = getattr(self, "toast_lab", None); if lab is None: return`
    的早期调用防御，理由写的是"set_paused 可能在 _build_ui 之前被调用"。
    但 grep 发现 shelf_app.py 里【根本没有 set_paused 这个方法】——
    我引用的是自己记忆里的错误假设。

    防御代码留着无害（零成本），但【测试用例不能建立在虚构的前提上】，
    否则测的是不存在的东西。本脚本用 AST 把真实调用图算出来：
      1) _toast 的所有调用点分别属于哪个方法
      2) 这些方法是否在 Shelf.__init__ 中 _build_ui() 之前被调用
      3) _build_ui() 在 __init__ 中的行号 vs 其它调用点的行号
    只有算出来的结论才能决定"早期调用防御"这一项该怎么测。
"""
import ast
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "shelf_app.py"
tree = ast.parse(SRC.read_text(encoding="utf-8"))

# ---- 1) 找到 Shelf 类 ----
shelf_cls = next(n for n in tree.body
                 if isinstance(n, ast.ClassDef) and n.name == "Shelf")
methods = {n.name: n for n in shelf_cls.body if isinstance(n, ast.FunctionDef)}

# ---- 2) _toast 的所有调用点，归属到哪个方法 ----
print("=" * 78)
print("【1】_toast 调用点归属")
print("=" * 78)
callers = {}
for name, fn in methods.items():
    for node in ast.walk(fn):
        if isinstance(node, ast.Call):
            f = node.func
            if isinstance(f, ast.Attribute) and f.attr == "_toast":
                callers.setdefault(name, []).append(node.lineno)
for name, lines in sorted(callers.items(), key=lambda kv: kv[1][0]):
    print("  %-28s 行 %s" % (name, lines))
print("  调用点所属方法总数:", len(callers))
print()

# ---- 3) __init__ 里 _build_ui() 的行号，以及它之前调用了什么 ----
print("=" * 78)
print("【2】Shelf.__init__ 中 _build_ui() 之前调用的方法")
print("=" * 78)
init = methods.get("__init__")
if init is None:
    print("  未找到 __init__")
    sys.exit(1)

build_ui_line = None
pre_calls = []
for node in ast.walk(init):
    if isinstance(node, ast.Call):
        f = node.func
        mname = f.attr if isinstance(f, ast.Attribute) else (
            f.id if isinstance(f, ast.Name) else None)
        if mname == "_build_ui":
            build_ui_line = node.lineno
        elif mname:
            pre_calls.append((node.lineno, mname))

print("  _build_ui() 调用行号:", build_ui_line)
before = [(ln, m) for ln, m in pre_calls if build_ui_line and ln < build_ui_line]
after = [(ln, m) for ln, m in pre_calls if build_ui_line and ln > build_ui_line]
print("  在 _build_ui() 【之前】调用的方法:")
for ln, m in sorted(before):
    flag = "  <== 会调 _toast!" if m in callers else ""
    print("    行 %-6d %s%s" % (ln, m, flag))
print()
print("  在 _build_ui() 【之后】调用的方法:")
for ln, m in sorted(after):
    flag = "  <== 会调 _toast" if m in callers else ""
    print("    行 %-6d %s%s" % (ln, m, flag))
print()

# ---- 4) 传递闭包：_build_ui 之前的方法是否间接调到 _toast ----
print("=" * 78)
print("【3】传递闭包分析（间接调用也算）")
print("=" * 78)


def calls_of(fn, skip_lambda=True):
    """收集 fn 直接调用的方法名。

    【必须跳过 lambda / 嵌套 def 内部的调用】否则会产生误报：
        quick_list.itemDoubleClicked.connect(
            lambda item: self._open_pinned_item(...))
    这一行在 _build_ui() 里，但 lambda 体内的 _open_pinned_item 是
    【延迟到用户双击时才执行】，不是 _build_ui 期间立即调用。
    实测：第一版不跳过 lambda，报出了
        __init__ -> _build_ui -> _open_pinned_item -> _toast
    但 grep 证实 _open_pinned_item 只出现在 connect 的 lambda（:1405）和
    _quick_context_menu（:1693），都不是 _build_ui 期间直接调用 —— 误报。
    """
    out = set()

    class Skip(ast.NodeVisitor):
        def visit_Lambda(self, node):
            if not skip_lambda:
                self.generic_visit(node)

        def visit_FunctionDef(self, node):
            if node is not fn:
                return                       # 不进入嵌套 def
            self.generic_visit(node)

        def visit_Call(self, node):
            f = node.func
            m = f.attr if isinstance(f, ast.Attribute) else (
                f.id if isinstance(f, ast.Name) else None)
            if m:
                out.add(m)
            self.generic_visit(node)

    Skip().visit(fn)
    return out


def reaches_toast(start, seen=None):
    """从 start 方法出发，能否（直接或间接）到达 _toast。"""
    seen = seen or set()
    if start in seen:
        return None
    seen.add(start)
    fn = methods.get(start)
    if fn is None:
        return None
    if start in callers:
        return [start]
    for m in calls_of(fn):
        r = reaches_toast(m, seen)
        if r:
            return [start] + r
    return None


risk = []
for ln, m in sorted(before):
    chain = reaches_toast(m)
    if chain:
        risk.append((ln, m, chain))
        print("  !! 行 %-6d %s -> _toast  链路: %s"
              % (ln, m, " -> ".join(chain + ["_toast"])))
if not risk:
    print("  _build_ui() 之前的所有调用，均不会（直接或间接）到达 _toast")
print()

print("=" * 78)
print("【结论】")
print("=" * 78)
if risk:
    print("  早期调用风险【真实存在】：%d 条路径" % len(risk))
    print("  -> _toast 的 `if lab is None: return` 防御是【必要的】")
    print("  -> 测试必须构造真实的 _build_ui 之前状态来验证")
else:
    print("  早期调用风险【不存在】：没有任何 _build_ui 之前的路径会调 _toast")
    print("  -> 我给 _toast 加的 `if lab is None: return` 防御属于")
    print("     【预防性冗余】：留着无害（零成本），但它保护的场景当前不可达")
    print("  -> 之前那条测试断言基于虚构前提（源码里没有 set_paused 方法），")
    print("     应当改为直接验证防御逻辑本身，而不是断言存在真实调用路径")
print("=" * 78)

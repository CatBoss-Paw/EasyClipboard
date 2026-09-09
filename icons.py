"""细线单色矢量图标库（macOS 风格，1.5px 线宽）。

零外部资源：QPainter 在 16x16 逻辑画布上描路径，2x 位图输出（高分屏清晰）。
颜色随调用点传入（currentColor 语义，深/浅主题自动适配）。

用法：
    from icons import icon
    btn.setIcon(icon("star", "#86868b"))
    btn.setIconSize(QSize(14, 14))
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, QPointF, QRectF, QSize, QSizeF
from PyQt6.QtGui import (QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap,
                         QPolygonF)

_LINE = 2.0          # 线宽（逻辑像素，扎实清晰，高分屏不发虚）
S = 16.0             # 画布边长


def _pen(color: str, scale: float) -> QPen:
    pen = QPen(QColor(color))
    pen.setWidthF(_LINE * scale)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    return pen


def _circle(p: QPainter, cx: float, cy: float, r: float) -> None:
    p.drawEllipse(QPointF(cx, cy), r, r)


def _line(p: QPainter, x1, y1, x2, y2) -> None:
    p.drawLine(QPointF(x1, y1), QPointF(x2, y2))


def _poly(p: QPainter, pts) -> None:
    p.drawPolyline(QPolygonF([QPointF(x, y) for x, y in pts]))


# ------------------------------------------------------------------ 各图标
def draw_scissors(p: QPainter) -> None:
    _circle(p, 4.6, 4.9, 1.9)
    _circle(p, 4.6, 11.1, 1.9)
    _line(p, 6.2, 5.6, 12.8, 3.0)
    _line(p, 6.2, 10.4, 12.8, 13.0)


def draw_pin(p: QPainter) -> None:
    path = QPainterPath(QPointF(5.2, 9.6))
    path.lineTo(6.2, 3.2)
    path.lineTo(9.8, 3.2)
    path.lineTo(10.8, 9.6)
    p.drawPath(path)
    _line(p, 3.8, 9.6, 12.2, 9.6)
    _line(p, 8, 9.6, 8, 13.6)


def draw_gear(p: QPainter) -> None:
    _circle(p, 8, 8, 2.6)
    import math
    for i in range(8):
        a = math.radians(i * 45)
        x1, y1 = 8 + 4.4 * math.cos(a), 8 + 4.4 * math.sin(a)
        x2, y2 = 8 + 6.3 * math.cos(a), 8 + 6.3 * math.sin(a)
        _line(p, x1, y1, x2, y2)


def draw_help(p: QPainter) -> None:
    _circle(p, 8, 8, 6.2)
    path = QPainterPath(QPointF(6.2, 6.2))
    path.cubicTo(6.2, 4.6, 9.8, 4.6, 9.8, 6.6)
    path.cubicTo(9.8, 8.4, 8, 8.4, 8, 9.8)
    p.drawPath(path)
    _line(p, 8, 11.4, 8, 11.8)   # 点的近似


def draw_star(p: QPainter) -> None:
    import math
    pts = []
    for i in range(10):
        r = 6.6 if i % 2 == 0 else 2.9
        a = math.radians(-90 + i * 36)
        pts.append((8 + r * math.cos(a), 8 + r * math.sin(a)))
    pts.append(pts[0])
    _poly(p, pts)


def draw_doc(p: QPainter) -> None:
    path = QPainterPath(QPointF(4.6, 2.4))
    path.lineTo(9.4, 2.4)
    path.lineTo(11.6, 4.6)      # 右上角折角
    path.lineTo(11.6, 13.6)
    path.lineTo(4.6, 13.6)
    path.closeSubpath()
    p.drawPath(path)
    _line(p, 9.4, 2.4, 9.4, 4.7)
    _line(p, 9.4, 4.7, 11.6, 4.7)
    _line(p, 6.5, 7.6, 9.9, 7.6)
    _line(p, 6.5, 9.9, 9.9, 9.9)
    _line(p, 6.5, 12.2, 8.7, 12.2)


def draw_bolt(p: QPainter) -> None:
    _poly(p, [(9.6, 1.6), (4.6, 9.0), (7.3, 9.0),
              (6.4, 14.4), (11.4, 6.8), (8.7, 6.8), (9.6, 1.6)])


def draw_trash(p: QPainter) -> None:
    _poly(p, [(4.8, 5.4), (4.8, 13.2), (11.2, 13.2), (11.2, 5.4)])
    _line(p, 3.4, 5.4, 12.6, 5.4)
    _line(p, 6.4, 5.4, 6.8, 3.6)
    _line(p, 6.8, 3.6, 9.2, 3.6)
    _line(p, 9.2, 3.6, 9.6, 5.4)
    _line(p, 6.8, 7.6, 6.8, 11.4)
    _line(p, 9.2, 7.6, 9.2, 11.4)


def draw_folder(p: QPainter) -> None:
    path = QPainterPath(QPointF(2.6, 4.0))
    path.lineTo(6.4, 4.0)
    path.lineTo(7.8, 5.8)
    path.lineTo(13.4, 5.8)
    path.lineTo(13.4, 12.6)
    path.lineTo(2.6, 12.6)
    path.closeSubpath()
    p.drawPath(path)


def draw_copy(p: QPainter) -> None:
    p.drawRect(QRectF(2.8, 5.4, 6.8, 7.8))
    poly = QPolygonF([QPointF(6.4, 5.4), QPointF(6.4, 2.8),
                      QPointF(13.2, 2.8), QPointF(13.2, 10.6),
                      QPointF(9.6, 10.6)])
    p.drawPolyline(poly)


def draw_plus(p: QPainter) -> None:
    _line(p, 8, 3.4, 8, 12.6)
    _line(p, 3.4, 8, 12.6, 8)


def draw_back(p: QPainter) -> None:
    _poly(p, [(9.6, 3.4), (4.4, 8), (9.6, 12.6)])


def draw_edit(p: QPainter) -> None:
    _poly(p, [(3.2, 12.8), (11.2, 4.8)])
    _poly(p, [(10.0, 3.6), (12.4, 6.0)])
    _poly(p, [(3.2, 12.8), (4.4, 11.6)])


def draw_image(p: QPainter) -> None:
    p.drawRect(QRectF(3.0, 3.6, 10.0, 8.8))
    _circle(p, 6.0, 6.6, 1.2)
    _poly(p, [(4.2, 11.2), (6.8, 8.4), (8.8, 10.4), (10.4, 8.8), (11.8, 10.2)])


def draw_check(p: QPainter) -> None:
    _poly(p, [(3.4, 8.4), (6.6, 11.6), (12.6, 4.6)])


def draw_minus(p: QPainter) -> None:
    _line(p, 3.4, 8, 12.6, 8)


def draw_close(p: QPainter) -> None:
    _line(p, 4.6, 4.6, 11.4, 11.4)
    _line(p, 11.4, 4.6, 4.6, 11.4)


def draw_attach(p: QPainter) -> None:
    path = QPainterPath(QPointF(10.8, 4.2))
    path.cubicTo(12.6, 6.0, 12.6, 8.2, 10.8, 10.0)
    path.cubicTo(9.0, 11.8, 6.8, 11.8, 5.0, 10.0)
    path.cubicTo(3.6, 8.6, 3.6, 6.6, 5.2, 5.0)
    p.drawPath(path)
    path2 = QPainterPath(QPointF(6.2, 6.2))
    path2.cubicTo(5.4, 7.0, 5.4, 8.0, 6.4, 9.0)
    p.drawPath(path2)


def draw_refresh(p: QPainter) -> None:
    path = QPainterPath()
    path.arcMoveTo(3.2, 3.2, 9.6, 9.6, 40.0)
    path.arcTo(3.2, 3.2, 9.6, 9.6, 40.0, 300.0)
    p.drawPath(path)
    _poly(p, [(11.2, 1.6), (13.2, 4.2), (10.0, 5.0)])


def draw_text(p: QPainter) -> None:
    _line(p, 4.0, 4.6, 12.0, 4.6)
    _line(p, 4.0, 8.0, 12.0, 8.0)
    _line(p, 4.0, 11.4, 9.6, 11.4)


def draw_link(p: QPainter) -> None:
    path = QPainterPath(QPointF(6.8, 9.2))
    path.lineTo(5.0, 11.0)
    path.cubicTo(3.4, 12.6, 1.4, 10.6, 3.0, 9.0)
    path.lineTo(4.8, 7.2)
    p.drawPath(path)
    path2 = QPainterPath(QPointF(9.2, 6.8))
    path2.lineTo(11.0, 5.0)
    path2.cubicTo(12.6, 3.4, 10.6, 1.4, 9.0, 3.0)
    path2.lineTo(7.2, 4.8)
    p.drawPath(path2)
    _line(p, 5.5, 10.5, 10.5, 5.5)


DRAWERS = {
    "scissors": draw_scissors, "pin": draw_pin, "gear": draw_gear,
    "help": draw_help, "star": draw_star, "doc": draw_doc,
    "bolt": draw_bolt, "trash": draw_trash, "folder": draw_folder,
    "copy": draw_copy, "plus": draw_plus, "back": draw_back,
    "edit": draw_edit, "image": draw_image, "check": draw_check,
    "minus": draw_minus, "close": draw_close, "attach": draw_attach,
    "text": draw_text, "link": draw_link, "refresh": draw_refresh,
}


_ICON_CACHE: dict[tuple[str, str, int, float], QIcon] = {}


def clear_icon_cache() -> None:
    """主题切换或内存整理时清空图标缓存。"""
    _ICON_CACHE.clear()


def icon(name: str, color: str, size: int = 16, dpr: float = 2.0) -> QIcon:
    """渲染细线单色图标为 QIcon（2x 位图，高分屏清晰），带全局享元缓存。"""
    key = (name, str(color), int(size), float(dpr))
    cached = _ICON_CACHE.get(key)
    if cached is not None and not cached.isNull():
        return cached

    draw = DRAWERS.get(name)
    if draw is None:
        raise KeyError(f"unknown icon: {name}")
    pm = QPixmap(int(size * dpr), int(size * dpr))
    pm.fill(Qt.GlobalColor.transparent)
    qp = QPainter(pm)
    qp.setRenderHint(QPainter.RenderHint.Antialiasing)
    qp.setPen(_pen(color, dpr))
    qp.setBrush(Qt.BrushStyle.NoBrush)
    k = (size * dpr) / S
    qp.scale(k, k)
    draw(qp)
    qp.end()
    pm.setDevicePixelRatio(dpr)
    res = QIcon(pm)
    _ICON_CACHE[key] = res
    return res


def set_icon(widget, name: str, color: str, size: int = 15) -> None:
    """便捷：给按钮设置细线图标 + 图标尺寸。"""
    widget.setIcon(icon(name, color))
    widget.setIconSize(QSize(size, size))

"""Small line icons (drawn for Trail) and the app logo, rendered at runtime."""
from __future__ import annotations

from functools import lru_cache

from PySide6.QtCore import QByteArray, QPointF, QRectF, Qt
from PySide6.QtGui import (QColor, QIcon, QLinearGradient, QPainter,
                           QPainterPath, QPixmap)
from PySide6.QtSvg import QSvgRenderer

from . import theme

_PATHS = {
    "dashboard": '<rect x="3" y="3" width="8" height="10" rx="2"/><rect x="13" y="3" width="8" height="6" rx="2"/>'
                 '<rect x="13" y="11" width="8" height="10" rx="2"/><rect x="3" y="15" width="8" height="6" rx="2"/>',
    "activity": '<rect x="3" y="4" width="18" height="17" rx="2.5"/><path d="M3 9h18M8 2.5v3M16 2.5v3"/>'
                '<path d="M7 13h2M11 13h2M15 13h2M7 17h2M11 17h2"/>',
    "apps": '<path d="M12 3l9 4.5-9 4.5-9-4.5z"/><path d="M3 12l9 4.5 9-4.5"/><path d="M3 16.5l9 4.5 9-4.5"/>',
    "settings": '<path d="M4 6h10M18 6h2M4 12h4M12 12h8M4 18h12M20 18h0"/>'
                '<circle cx="16" cy="6" r="2"/><circle cx="10" cy="12" r="2"/><circle cx="18" cy="18" r="2"/>',
    "pause": '<rect x="6" y="5" width="4" height="14" rx="1"/><rect x="14" y="5" width="4" height="14" rx="1"/>',
    "play": '<path d="M7 4.5v15l12-7.5z"/>',
    "plus": '<path d="M12 5v14M5 12h14"/>',
    "trash": '<path d="M4 7h16M9 7V4.5h6V7M6.5 7l1 13h9l1-13M10 11v6M14 11v6"/>',
    "edit": '<path d="M4 20h4L19 9l-4-4L4 16z"/><path d="M13.5 6.5l4 4"/>',
    "search": '<circle cx="11" cy="11" r="6.5"/><path d="M16 16l4.5 4.5"/>',
    "sync": '<path d="M20 11a8 8 0 0 0-14.5-4.5L4 8M4 4v4h4"/><path d="M4 13a8 8 0 0 0 14.5 4.5L20 16M20 20v-4h-4"/>',
    "cloud": '<path d="M7 18h10a4 4 0 0 0 .5-8A6 6 0 0 0 6 9.5 4.3 4.3 0 0 0 7 18z"/>',
    "download": '<path d="M12 4v11M7.5 10.5L12 15l4.5-4.5M5 19h14"/>',
    "folder": '<path d="M3 7.5A1.5 1.5 0 0 1 4.5 6H9l2 2.5h8.5A1.5 1.5 0 0 1 21 10v8.5a1.5 1.5 0 0 1-1.5 1.5h-15A1.5 1.5 0 0 1 3 18.5z"/>',
    "flame": '<path d="M12 21c4 0 6.5-2.6 6.5-6.3 0-3.7-3-6-4.3-9.7-1.5 2.2-2.2 3.6-2.2 5.5-1.3-.8-2-2-2.2-3.5C8 9 5.5 11.5 5.5 14.7 5.5 18.4 8 21 12 21z"/>',
    "clock": '<circle cx="12" cy="12" r="8.5"/><path d="M12 7.5V12l3 2"/>',
    "target": '<circle cx="12" cy="12" r="8.5"/><circle cx="12" cy="12" r="4.5"/><circle cx="12" cy="12" r="0.8"/>',
    "calendar": '<rect x="3" y="4" width="18" height="17" rx="2.5"/><path d="M3 9h18M8 2.5v3M16 2.5v3"/>',
    "check": '<path d="M5 12.5l4.5 4.5L19 7.5"/>',
    "bell": '<path d="M6 16V11a6 6 0 0 1 12 0v5l1.5 2h-15z"/><path d="M10 20.5a2 2 0 0 0 4 0"/>',
    "eye": '<path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12z"/><circle cx="12" cy="12" r="3"/>',
    "info": '<circle cx="12" cy="12" r="8.5"/><path d="M12 11v5.5M12 7.6v.4"/>',
}


@lru_cache(maxsize=256)
def icon(name: str, color: str = theme.MUTED, size: int = 18) -> QIcon:
    return QIcon(pixmap(name, color, size))


@lru_cache(maxsize=256)
def pixmap(name: str, color: str = theme.MUTED, size: int = 18) -> QPixmap:
    fill = 'fill="currentColor"' if name in ("play", "pause") else 'fill="none"'
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" {fill} '
           f'stroke="currentColor" stroke-width="1.8" stroke-linecap="round" '
           f'stroke-linejoin="round" color="{color}">{_PATHS[name]}</svg>')
    svg = svg.replace("currentColor", color)
    renderer = QSvgRenderer(QByteArray(svg.encode()))
    scale = 2  # crisp on high-DPI screens
    pm = QPixmap(size * scale, size * scale)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    renderer.render(p)
    p.end()
    pm.setDevicePixelRatio(scale)
    return pm


def logo_pixmap(size: int = 64, muted: bool = False) -> QPixmap:
    """Trail logo: a rounded tile with a rising path of squares."""
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    s = size / 64
    grad = QLinearGradient(0, 0, size, size)
    if muted:
        grad.setColorAt(0, QColor("#4b5563"))
        grad.setColorAt(1, QColor("#374151"))
    else:
        grad.setColorAt(0, QColor("#2ea043"))
        grad.setColorAt(1, QColor("#1f6feb"))
    p.setPen(Qt.NoPen)
    p.setBrush(grad)
    p.drawRoundedRect(QRectF(1 * s, 1 * s, 62 * s, 62 * s), 15 * s, 15 * s)

    # rising trail: four squares stepping up, connected by a soft line
    pts = [(14, 44), (25, 37), (36, 29), (47, 19)]
    path = QPainterPath(QPointF(pts[0][0] * s, pts[0][1] * s))
    for x, y in pts[1:]:
        path.lineTo(x * s, y * s)
    pen_color = QColor(255, 255, 255, 90)
    p.setPen(pen_color)
    p.setBrush(Qt.NoBrush)
    p.drawPath(path)
    p.setPen(Qt.NoPen)
    for i, (x, y) in enumerate(pts):
        c = QColor(255, 255, 255)
        c.setAlphaF(0.55 + 0.15 * i)
        p.setBrush(c)
        half = (4.2 + i * 0.9) * s
        p.drawRoundedRect(QRectF(x * s - half, y * s - half, 2 * half, 2 * half), 2.2 * s, 2.2 * s)
    p.end()
    return pm


def logo_icon(muted: bool = False) -> QIcon:
    ic = QIcon()
    for sz in (16, 24, 32, 48, 64, 128, 256):
        ic.addPixmap(logo_pixmap(sz, muted))
    return ic

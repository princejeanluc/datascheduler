"""
DataScheduler — ui/icons.py
Logo et icônes de navigation personnalisés (chantier identité visuelle, phase 2) : tracés SVG
repris tels quels de la maquette validée avec l'utilisateur, embarqués en chaînes Python — même
convention que ui/help/content.py (rubriques d'aide) et ui/branding.py (icône), pour éviter toute
résolution de chemin sys._MEIPASS dans l'exe gelé. Rendus via QSvgRenderer plutôt que retranscrits
à la main en QPainterPath : plus fidèle à la maquette, et QtSvg est un sous-module standard de
PySide6 (pas une dépendance tierce).

Le reste de l'application continue d'utiliser qtawesome (ui.main_window.widgets._icon) pour toutes
les autres icônes — seuls le logo et les 6 icônes de la barre de navigation latérale sont
concernés ici.
"""

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

_SVG_WRAPPER = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
    'stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">{body}</svg>'
)

# Icônes de nav — tracés en traits, repris de la maquette (datascheduler-identity-mockup.html).
_NAV_ICON_BODIES = {
    "dashboard": (
        '<rect x="3" y="3" width="7" height="9" rx="1.5"/>'
        '<rect x="14" y="3" width="7" height="5" rx="1.5"/>'
        '<rect x="14" y="12" width="7" height="9" rx="1.5"/>'
        '<rect x="3" y="16" width="7" height="5" rx="1.5"/>'
    ),
    "pipelines": (
        '<circle cx="5" cy="6" r="2"/><circle cx="19" cy="12" r="2"/><circle cx="5" cy="18" r="2"/>'
        '<path d="M7 6h6a4 4 0 014 4M7 18h6a4 4 0 004-4"/>'
    ),
    "connexions": '<path d="M6 3v6a2 2 0 002 2h8a2 2 0 002-2V3M9 21v-6h6v6"/>',
    "requetes_sql": (
        '<ellipse cx="12" cy="5" rx="7" ry="2.5"/>'
        '<path d="M5 5v6c0 1.4 3.1 2.5 7 2.5s7-1.1 7-2.5V5M5 11v6c0 1.4 3.1 2.5 7 2.5s7-1.1 7-2.5v-6"/>'
    ),
    "historique": '<circle cx="12" cy="13" r="7.5"/><path d="M12 9v4l2.5 2M9 2h6"/>',
    "aide": (
        '<circle cx="12" cy="12" r="9"/>'
        '<path d="M9.5 9a2.5 2.5 0 015 .4c0 1.6-2.5 1.8-2.5 3.6"/>'
        '<circle cx="12" cy="16.6" r="0.4" fill="{color}" stroke="none"/>'
    ),
}

# Logo — repère "flux de pipelines" (3 nœuds reliés), toujours en couleur accent (c'est la marque).
_LOGO_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none">'
    '<circle cx="4.5" cy="6" r="2.3" fill="{color}"/>'
    '<circle cx="4.5" cy="18" r="2.3" fill="{color}"/>'
    '<circle cx="19.5" cy="12" r="2.6" fill="{color}"/>'
    '<path d="M6.6 6h5.4a3 3 0 013 3v0a3 3 0 003 3h1.5M6.6 18h5.4a3 3 0 003-3v0a3 3 0 013-3h1.5" '
    'stroke="{color}" stroke-width="1.6" stroke-linecap="round"/>'
    "</svg>"
)

# Motif "flux" simplifié pour les séparateurs de section (chantier identité, vague 2, idée 2) —
# 3 points reliés par 2 traits courts, tous dans le même plan vertical (viewBox non carré, y=7
# partout) : rendu SVG plutôt que QLabel+QFrame juxtaposés, dont les ancrages verticaux (baseline
# de texte vs geometrie de cadre) ne s'alignaient pas proprement (repéré sur une capture réelle).
_MOTIF_DOTS_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 26 14">'
    '<circle cx="3" cy="7" r="2" fill="{color}"/>'
    '<circle cx="13" cy="7" r="2" fill="{color}"/>'
    '<circle cx="23" cy="7" r="2" fill="{color}"/>'
    '<path d="M5 7h6M15 7h6" stroke="{color}" stroke-width="1.4"/>'
    "</svg>"
)


def _render_svg(svg_source: str, size: int) -> QIcon:
    return _render_svg_rect(svg_source, size, size)


def _render_svg_rect(svg_source: str, width: int, height: int) -> QIcon:
    renderer = QSvgRenderer(QByteArray(svg_source.encode("utf-8")))
    pixmap = QPixmap(width, height)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()
    return QIcon(pixmap)


def nav_icon(key: str, color: str, size: int = 64) -> QIcon:
    """Icône de la barre de navigation latérale (clés : voir _NAV_ICON_BODIES)."""
    body = _NAV_ICON_BODIES[key].format(color=color)
    svg = _SVG_WRAPPER.format(color=color, body=body)
    return _render_svg(svg, size)


def logo_icon(color: str, size: int = 64) -> QIcon:
    """Logo DataScheduler ("flux de pipelines"), à afficher en haut de la barre de navigation."""
    return _render_svg(_LOGO_SVG.format(color=color), size)


def motif_dots_icon(color: str, width: int = 52, height: int = 28) -> QIcon:
    """Motif "3 points reliés" des séparateurs de section (voir _MOTIF_DOTS_SVG)."""
    return _render_svg_rect(_MOTIF_DOTS_SVG.format(color=color), width, height)

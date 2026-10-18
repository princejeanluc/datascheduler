"""
DataScheduler — ui/components/banner.py
Bandeau partagé (refonte, lot A-Paramètres — FONDATIONS.md section 3 : « info, réussite,
avertissement, échec ; icône, titre, texte, actions »). Structure confirmée sur la maquette
Parametres-refus.html (variante danger) ; le mapping de couleur des 3 autres variantes est un
simple dict déjà entièrement rempli par COLORS (lot 0a) — aucune supposition de disposition,
donc construites dès maintenant même si seule `danger` est exercée dans ce lot.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel

from ui.styles import COLORS

_VARIANTS = {
    "info":    (COLORS["bg_info"], COLORS["border_info"], COLORS["signal_pale"]),
    "success": (COLORS["bg_success"], COLORS["border_success"], COLORS["success"]),
    "warning": (COLORS["bg_warning"], COLORS["border_warning"], COLORS["warning"]),
    "danger":  (COLORS["bg_danger"], COLORS["border_danger"], COLORS["danger"]),
}


def make_banner(variant: str, icon_name: str, title: str, text: str, actions=None) -> QWidget:
    """`actions` est un QWidget seul, une liste de QWidget, ou None (pas de zone d'actions)."""
    # Import différé : même raison que dans page_header.py (dépendance circulaire selon l'ordre
    # d'import).
    from ui.main_window.widgets import _icon

    bg, border, icon_color = _VARIANTS[variant]
    banner = QWidget()
    banner.setStyleSheet(
        f"background: {bg}; border: 1px solid {border}; border-radius: 8px;"
    )
    outer = QHBoxLayout(banner)
    outer.setContentsMargins(14, 12, 14, 12)
    outer.setSpacing(12)

    icon_lbl = QLabel()
    icon = _icon(icon_name, icon_color)
    if icon:
        icon_lbl.setPixmap(icon.pixmap(18, 18))
    outer.addWidget(icon_lbl, alignment=Qt.AlignTop)

    text_col = QVBoxLayout()
    text_col.setSpacing(4)
    title_lbl = QLabel(title)
    title_lbl.setStyleSheet(f"color: {COLORS['text_main']}; font-size: 13.5px; font-weight: 600;")
    text_col.addWidget(title_lbl)
    if text:
        text_lbl = QLabel(text)
        text_lbl.setWordWrap(True)
        text_lbl.setStyleSheet(f"color: {COLORS['text_soft']}; font-size: 12.5px;")
        text_col.addWidget(text_lbl)
    outer.addLayout(text_col, stretch=1)

    if actions is not None:
        actions_col = QVBoxLayout()
        actions_col.setSpacing(8)
        for widget in (actions if isinstance(actions, (list, tuple)) else (actions,)):
            actions_col.addWidget(widget)
        outer.addLayout(actions_col)

    return banner

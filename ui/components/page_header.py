"""
DataScheduler — ui/components/page_header.py
En-tête de page partagé (refonte, lot 0a — FONDATIONS.md sections 1/2/3). Structure confirmée sur
les maquettes (Parametres.html, Pipelines.html) : surtitre Mono en majuscules, titre 26px/600,
sous-titre optionnel, puis une zone d'actions poussée à droite par un espace extensible.
"""

from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout


def make_page_header(eyebrow: str, title: str, subtitle: str = "", actions=None) -> QWidget:
    """`actions` est un QWidget seul, une liste de QWidget (boutons alignés avec un espacement de
    10px, comme sur Pipelines.html), ou None (pas de zone d'actions)."""
    # Import différé : ui.main_window.widgets (via ui.main_window) importe lui-même ce module
    # (settings_view.py etc.) — un import en tête de fichier ici créerait une dépendance
    # circulaire selon l'ordre d'import (révélé par un test import ant ui.components en premier,
    # jamais par du code applicatif qui importe toujours ui.main_window.* en premier).
    from ui.main_window.widgets import _make_page_eyebrow, _make_page_title, _make_subtitle

    header = QWidget()
    row = QHBoxLayout(header)
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(10)

    left = QWidget()
    left_col = QVBoxLayout(left)
    left_col.setContentsMargins(0, 0, 0, 0)
    left_col.setSpacing(6)
    left_col.addWidget(_make_page_eyebrow(eyebrow))
    left_col.addWidget(_make_page_title(title))
    if subtitle:
        left_col.addWidget(_make_subtitle(subtitle))

    row.addWidget(left)
    row.addStretch(1)

    if actions is not None:
        for widget in (actions if isinstance(actions, (list, tuple)) else (actions,)):
            row.addWidget(widget)

    return header

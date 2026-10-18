"""
DataScheduler — ui/components/info_pill.py
Pastille d'information partagée (refonte, lot A-Paramètres — FONDATIONS.md section 3 : « texte
10,5 px dans un contour arrondi »). Structure et couleurs confirmées sur les 7 maquettes de
Paramètres : 3 variantes suffisent à ce lot. `warning` (pastille « en attente de redémarrage »,
lot C4) et `danger` ne sont pas construites ici — aucun consommateur, aucune maquette à valider
contre dans ce lot.
"""

from PySide6.QtWidgets import QLabel

from ui.styles import COLORS

# (couleur du texte, couleur de bordure ou None, couleur de fond ou None)
_VARIANTS = {
    "neutral": (COLORS["text_dim"], COLORS["border"], None),
    "success": (COLORS["success"], COLORS["border_success"], None),
    "info":    (COLORS["signal_pale"], None, COLORS["bg_info"]),
}


def make_info_pill(text: str, variant: str = "neutral", tooltip: str = "") -> QLabel:
    color, border, bg = _VARIANTS[variant]
    border_rule = f"border: 1px solid {border};" if border else "border: none;"
    bg_rule = f"background: {bg};" if bg else "background: transparent;"
    lbl = QLabel(text)
    lbl.setStyleSheet(
        f"color: {color}; {bg_rule} {border_rule} border-radius: 999px; "
        f"padding: 1px 7px; font-size: 10.5px; font-weight: 600;"
    )
    if tooltip:
        lbl.setToolTip(tooltip)
    return lbl

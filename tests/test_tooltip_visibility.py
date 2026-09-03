"""
DataScheduler — tests/test_tooltip_visibility.py
Bug réel signalé par l'utilisateur : sur certaines machines de bureau (jamais reproduit sur son
laptop), les infobulles s'affichaient comme un encadré vide (noir ou blanc selon la machine) —
aucune règle QToolTip explicite n'existait dans GLOBAL_STYLE, donc l'infobulle pouvait être peinte
par le chrome natif de l'OS (thème sombre/clair Windows) sur certaines machines, texte et fond
venant alors de deux sources différentes et pouvant se confondre. Verrouille qu'une règle QSS
explicite existe désormais, avec un fond et un texte de couleurs distinctes.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from ui.main_window.widgets import GLOBAL_STYLE
from ui.styles import COLORS


def test_global_style_declares_an_explicit_tooltip_rule():
    assert "QToolTip" in GLOBAL_STYLE


def test_tooltip_background_and_text_colors_are_distinct():
    assert COLORS["bg_card"] != COLORS["text_main"]
    assert COLORS["bg_card"] in GLOBAL_STYLE
    assert COLORS["text_main"] in GLOBAL_STYLE

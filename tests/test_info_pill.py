"""
DataScheduler — tests/test_info_pill.py
Refonte, lot A-Paramètres : make_info_pill() (ui/components/info_pill.py). Couleurs confirmées
sur les maquettes Parametres.html (neutral/success) et Parametres-recherche.html (info, chip de
catégorie).
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from ui.styles import COLORS


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_neutral_variant_uses_text_dim_and_border(qapp):
    from ui.components import make_info_pill

    pill = make_info_pill("au redémarrage", variant="neutral")
    style = pill.styleSheet()
    assert COLORS["text_dim"] in style
    assert COLORS["border"] in style
    assert "background: transparent" in style


def test_success_variant_uses_success_and_border_success(qapp):
    from ui.components import make_info_pill

    pill = make_info_pill("immédiat", variant="success")
    style = pill.styleSheet()
    assert COLORS["success"] in style
    assert COLORS["border_success"] in style


def test_info_variant_uses_signal_pale_and_filled_bg_info(qapp):
    from ui.components import make_info_pill

    pill = make_info_pill("Interface", variant="info")
    style = pill.styleSheet()
    assert COLORS["signal_pale"] in style
    assert COLORS["bg_info"] in style
    assert "border: none" in style


def test_text_is_kept_as_given(qapp):
    from ui.components import make_info_pill

    pill = make_info_pill("à la prochaine ouverture", variant="neutral")
    assert pill.text() == "à la prochaine ouverture"


def test_tooltip_is_set_when_given(qapp):
    from ui.components import make_info_pill

    pill = make_info_pill("au redémarrage", variant="neutral",
                           tooltip="Prend effet au prochain démarrage de Kulu")
    assert pill.toolTip() == "Prend effet au prochain démarrage de Kulu"


def test_no_tooltip_by_default(qapp):
    from ui.components import make_info_pill

    pill = make_info_pill("immédiat", variant="success")
    assert pill.toolTip() == ""

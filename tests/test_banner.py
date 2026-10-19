"""
DataScheduler — tests/test_banner.py
Refonte, lot A-Paramètres : make_banner() (ui/components/banner.py). Structure confirmée sur
Parametres-refus.html (variante danger).
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QPushButton, QLabel

from ui.styles import COLORS


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_danger_variant_uses_bg_danger_and_border_danger(qapp):
    from ui.components import make_banner

    banner = make_banner("danger", "fa5s.exclamation-circle", "Titre", "Texte")
    style = banner.styleSheet()
    assert COLORS["bg_danger"] in style
    assert COLORS["border_danger"] in style


def test_title_and_text_are_shown(qapp):
    from ui.components import make_banner

    banner = make_banner("danger", "fa5s.exclamation-circle", "Mon titre", "Mon texte")
    labels = [l.text() for l in banner.findChildren(QLabel)]
    assert "Mon titre" in labels
    assert "Mon texte" in labels


def test_empty_text_omits_the_text_label(qapp):
    from ui.components import make_banner

    banner = make_banner("danger", "fa5s.exclamation-circle", "Titre seul", "")
    labels = [l.text() for l in banner.findChildren(QLabel)]
    assert labels.count("") == 0 or "Titre seul" in labels


def test_no_actions_by_default(qapp):
    from ui.components import make_banner

    banner = make_banner("danger", "fa5s.exclamation-circle", "Titre", "Texte")
    assert banner.findChildren(QPushButton) == []


def test_single_action_widget_is_added(qapp):
    from ui.components import make_banner

    btn = QPushButton("Fermer")
    banner = make_banner("danger", "fa5s.exclamation-circle", "Titre", "Texte", actions=btn)
    assert banner.findChildren(QPushButton) == [btn]


def test_success_variant_uses_bg_success_and_border_success(qapp):
    from ui.components import make_banner

    banner = make_banner("success", "fa5s.check-circle", "Titre", "Texte")
    style = banner.styleSheet()
    assert COLORS["bg_success"] in style
    assert COLORS["border_success"] in style

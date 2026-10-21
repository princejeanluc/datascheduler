"""
DataScheduler — tests/test_connections_shared_widgets.py
Refonte, lot A-Connexions : assistants partagés de ui/main_window/widgets.py (_type_icon_badge,
_two_line_cell, _last_test_cell) — utilisés par connections_view.py (A3/A5/A7), les 7 dialogues de
profil (A8) et le bilan de santé (A10), pas un seul widget à eux.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from datetime import datetime, timedelta

import pytest
from PySide6.QtWidgets import QApplication, QLabel


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_type_icon_badge_covers_every_category(qapp):
    from ui.main_window.widgets import _TYPE_ICON, _type_icon_badge

    for category in _TYPE_ICON:
        badge = _type_icon_badge(category)
        assert badge.size().width() == 30
        assert not badge.pixmap().isNull()


def test_type_icon_badge_unknown_category_falls_back_without_raising(qapp):
    from ui.main_window.widgets import _type_icon_badge

    badge = _type_icon_badge("connexion-inconnue-future")
    assert not badge.pixmap().isNull()


def test_two_line_cell_omits_second_label_when_sub_text_empty(qapp):
    from ui.main_window.widgets import _two_line_cell

    cell = _two_line_cell("Kerberos KULU@HADOOP", "#fff")
    assert len(cell.findChildren(QLabel)) == 1

    cell_with_sub = _two_line_cell("Oracle CRM_PROD", "#fff", "Oracle", "#999")
    assert len(cell_with_sub.findChildren(QLabel)) == 2


def _texts(cell) -> list:
    """Libellés texte d'une cellule composite — exclut le point coloré (un QLabel vide, juste
    stylé en cercle)."""
    return [lbl.text() for lbl in cell.findChildren(QLabel) if lbl.text()]


def test_last_test_cell_shows_word_never_colored_and_without_tooltip_info_line(qapp):
    """A5 : jamais la couleur seule (le mot est toujours affiché), et pour "jamais testé" aucune
    seconde ligne (pas de date à montrer — distinct du cas "utilisée à 18:00", C3, gated)."""
    from ui.main_window.widgets import _last_test_cell

    cell = _last_test_cell(None, None)
    assert _texts(cell) == ["Jamais testé"]


def test_last_test_cell_shows_relative_time_as_visible_text_not_tooltip(qapp):
    from ui.main_window.widgets import _last_test_cell

    cell = _last_test_cell(True, datetime.utcnow() - timedelta(minutes=5))
    texts = _texts(cell)
    assert texts[0] == "OK"
    assert "il y a" in texts[1]
    sub_label = [lbl for lbl in cell.findChildren(QLabel) if lbl.text() == texts[1]][0]
    assert sub_label.toolTip() == ""  # visible, plus une infobulle (A5)


def test_last_test_cell_flags_stale_profiles_as_warning_and_dims_the_cell(qapp):
    from ui.main_window.widgets import _last_test_cell

    fresh = _last_test_cell(True, datetime.utcnow() - timedelta(days=5))
    stale = _last_test_cell(True, datetime.utcnow() - timedelta(days=41))

    assert fresh.graphicsEffect() is None
    assert stale.graphicsEffect() is not None
    assert "à retester" in _texts(stale)[1]

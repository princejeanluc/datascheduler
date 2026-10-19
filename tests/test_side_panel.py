"""
DataScheduler — tests/test_side_panel.py
Refonte, lot A-Aujourd'hui : SidePanel (ui/components/side_panel.py), premier composant
partagé "Panneau latéral" de FONDATIONS.md section 3 (glisse depuis la droite, 560px par défaut,
ombre, se ferme par Échap).

`_settle()` fait avancer l'animation jusqu'à sa fin via `QPropertyAnimation.setCurrentTime()`
(déterministe, synchrone) plutôt que d'attendre en temps réel via une QEventLoop imbriquée —
cette dernière approche, utilisée dans une première version de ce fichier, a provoqué un crash
("Windows fatal exception: access violation") lors d'une suite complète : seul fichier de test du
projet à imbriquer une vraie boucle d'événements avec attente réelle, probablement en interaction
avec un thread d'arrière-plan laissé vivant par un autre test (aucun autre test du projet n'utilise
ce patron). setCurrentTime() évite complètement le problème : aucune boucle d'événements imbriquée,
aucune attente réelle, le test reste déterministe et rapide.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt, QEvent
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication, QWidget, QLabel


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _host(qapp) -> QWidget:
    host = QWidget()
    host.resize(1000, 700)
    host.show()
    qapp.processEvents()
    return host


def _settle(qapp, panel):
    """Fait avancer l'animation en cours jusqu'à sa fin, de façon synchrone et déterministe —
    voir la docstring du module."""
    panel._anim.setCurrentTime(panel._anim.duration())
    qapp.processEvents()


def test_side_panel_defaults_to_560px_and_starts_hidden(qapp):
    from ui.components.side_panel import SidePanel

    host = _host(qapp)   # référence Python gardée : sinon GC détruit host, donc panel (enfant Qt)
    panel = SidePanel(host)
    assert panel._panel_width == 560
    assert not panel.isVisible()


def test_side_panel_custom_width(qapp):
    from ui.components.side_panel import SidePanel

    host = _host(qapp)
    panel = SidePanel(host, width=400)
    assert panel._panel_width == 400


def test_side_panel_set_content_replaces_previous_widget(qapp):
    from ui.components.side_panel import SidePanel

    host = _host(qapp)
    panel = SidePanel(host)
    first = QLabel("premier")
    panel.set_content(first)
    assert panel._content is first

    second = QLabel("second")
    panel.set_content(second)
    assert panel._content is second
    assert panel._content_host_layout.count() == 1   # le premier a bien été retiré, pas empilé


def test_side_panel_open_animates_to_resting_position_docked_right(qapp):
    from ui.components.side_panel import SidePanel

    host = _host(qapp)
    panel = SidePanel(host)

    panel.open()
    assert panel.isVisible()

    _settle(qapp, panel)
    assert panel.geometry().x() == host.width() - panel._panel_width
    assert panel.geometry().width() == panel._panel_width
    assert panel.geometry().height() == host.height()


def test_side_panel_close_emits_closed_and_hides(qapp):
    from ui.components.side_panel import SidePanel

    host = _host(qapp)
    panel = SidePanel(host)
    panel.open()
    _settle(qapp, panel)

    closed_calls = []
    panel.closed.connect(lambda: closed_calls.append(True))

    panel.close()
    _settle(qapp, panel)

    assert not panel.isVisible()
    assert closed_calls == [True]


def test_side_panel_escape_key_closes_it(qapp):
    from ui.components.side_panel import SidePanel

    host = _host(qapp)
    panel = SidePanel(host)
    panel.open()
    _settle(qapp, panel)
    assert panel.isVisible()

    event = QKeyEvent(QEvent.KeyPress, Qt.Key_Escape, Qt.NoModifier)
    panel.keyPressEvent(event)
    _settle(qapp, panel)

    assert not panel.isVisible()


def test_side_panel_close_button_closes_it(qapp):
    from ui.components.side_panel import SidePanel

    host = _host(qapp)
    panel = SidePanel(host)
    panel.open()
    _settle(qapp, panel)

    panel._btn_close.click()
    _settle(qapp, panel)

    assert not panel.isVisible()


def test_side_panel_tracks_parent_resize_while_open(qapp):
    from ui.components.side_panel import SidePanel

    host = _host(qapp)
    panel = SidePanel(host)
    panel.open()
    _settle(qapp, panel)

    host.resize(1200, 700)
    qapp.processEvents()

    assert panel.geometry().x() == host.width() - panel._panel_width

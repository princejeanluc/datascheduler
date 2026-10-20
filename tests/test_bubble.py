"""
DataScheduler — tests/test_bubble.py
Refonte, lot A-Historique : Bubble (ui/components/bubble.py), composant partagé "Bulle" de
FONDATIONS.md section 3 (ancrée à un élément, avec une flèche, se ferme par Échap ou clic en
dehors).
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt, QEvent, QPoint
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication, QWidget, QLabel, QPushButton


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _anchor(qapp) -> QPushButton:
    host = QWidget()
    host.resize(600, 400)
    anchor = QPushButton("case", host)
    anchor.move(50, 50)
    anchor.resize(10, 10)
    host.show()
    qapp.processEvents()
    anchor._host_ref = host   # référence Python gardée : sinon GC détruit host, donc anchor (enfant Qt)
    return anchor


def test_bubble_starts_hidden(qapp):
    from ui.components.bubble import Bubble

    anchor = _anchor(qapp)
    bubble = Bubble(anchor.window())
    assert not bubble.isVisible()


def test_bubble_set_content_replaces_previous_widget(qapp):
    from ui.components.bubble import Bubble

    anchor = _anchor(qapp)
    bubble = Bubble(anchor.window())
    first = QLabel("premier")
    bubble.set_content(first)
    assert bubble._content is first

    second = QLabel("second")
    bubble.set_content(second)
    assert bubble._content is second
    assert bubble._layout.count() == 1


def test_bubble_open_at_shows_it_near_the_anchor(qapp):
    from ui.components.bubble import Bubble

    anchor = _anchor(qapp)
    bubble = Bubble(anchor.window())
    bubble.set_content(QLabel("contenu"))

    bubble.open_at(anchor)
    qapp.processEvents()

    assert bubble.isVisible()
    # Positionnée à droite de l'ancre (coordonnées globales) — pas une valeur fixe arbitraire.
    assert bubble.pos().x() > anchor.mapToGlobal(QPoint(0, 0)).x()


def test_bubble_escape_key_closes_it(qapp):
    from ui.components.bubble import Bubble

    anchor = _anchor(qapp)
    bubble = Bubble(anchor.window())
    bubble.set_content(QLabel("contenu"))
    bubble.open_at(anchor)
    qapp.processEvents()
    assert bubble.isVisible()

    event = QKeyEvent(QEvent.KeyPress, Qt.Key_Escape, Qt.NoModifier)
    bubble.keyPressEvent(event)

    assert not bubble.isVisible()


def test_bubble_emits_closed_when_hidden(qapp):
    from ui.components.bubble import Bubble

    anchor = _anchor(qapp)
    bubble = Bubble(anchor.window())
    bubble.set_content(QLabel("contenu"))
    bubble.open_at(anchor)
    qapp.processEvents()

    closed_calls = []
    bubble.closed.connect(lambda: closed_calls.append(True))
    bubble.hide()

    assert closed_calls == [True]

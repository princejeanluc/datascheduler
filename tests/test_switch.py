"""
DataScheduler — tests/test_switch.py
Refonte, lot A-Paramètres : Switch (ui/components/switch.py). Structure confirmée sur les
maquettes Parametres*.html (role="switch", 38x22px, accent quand activé).
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_switch_is_checkable_and_unchecked_by_default(qapp):
    from ui.components import make_switch

    sw = make_switch()
    assert sw.isCheckable()
    assert not sw.isChecked()


def test_switch_fixed_size_38x22(qapp):
    from ui.components import make_switch

    sw = make_switch()
    assert sw.size().width() == 38
    assert sw.size().height() == 22


def test_switch_toggles_on_click(qapp):
    from PySide6.QtTest import QTest
    from PySide6.QtCore import Qt
    from ui.components import make_switch

    sw = make_switch()
    QTest.mouseClick(sw, Qt.LeftButton)
    assert sw.isChecked()
    QTest.mouseClick(sw, Qt.LeftButton)
    assert not sw.isChecked()


def test_switch_emits_toggled(qapp):
    from ui.components import make_switch

    sw = make_switch()
    calls = []
    sw.toggled.connect(calls.append)
    sw.setChecked(True)
    assert calls == [True]

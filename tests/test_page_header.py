"""
DataScheduler — tests/test_page_header.py
Refonte, lot 0a : make_page_header() (ui/components/page_header.py), premier composant partagé
du module ui/components/. Structure confirmée sur les maquettes Parametres.html/Pipelines.html.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QPushButton, QLabel


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_eyebrow_is_uppercased_and_styled_as_page_eyebrow(qapp):
    from ui.components import make_page_header

    header = make_page_header(eyebrow="ce poste · kulu 0.45", title="Paramètres")
    eyebrow_labels = [l for l in header.findChildren(QLabel) if l.objectName() == "page_eyebrow"]
    assert len(eyebrow_labels) == 1
    assert eyebrow_labels[0].text() == "CE POSTE · KULU 0.45"


def test_title_is_styled_as_page_title(qapp):
    from ui.components import make_page_header

    header = make_page_header(eyebrow="8 pipelines", title="Pipelines")
    title_labels = [l for l in header.findChildren(QLabel) if l.objectName() == "page_title"]
    assert len(title_labels) == 1
    assert title_labels[0].text() == "Pipelines"


def test_subtitle_is_absent_by_default(qapp):
    from ui.components import make_page_header

    header = make_page_header(eyebrow="E", title="T")
    subtitle_labels = [l for l in header.findChildren(QLabel) if l.objectName() == "subtitle"]
    assert subtitle_labels == []


def test_subtitle_is_added_when_given(qapp):
    from ui.components import make_page_header

    header = make_page_header(eyebrow="E", title="T", subtitle="Un sous-titre")
    subtitle_labels = [l for l in header.findChildren(QLabel) if l.objectName() == "subtitle"]
    assert len(subtitle_labels) == 1
    assert subtitle_labels[0].text() == "Un sous-titre"


def test_no_actions_by_default(qapp):
    from ui.components import make_page_header

    header = make_page_header(eyebrow="E", title="T")
    assert header.findChildren(QPushButton) == []


def test_single_action_widget_is_added(qapp):
    from ui.components import make_page_header

    btn = QPushButton("+ Nouveau pipeline")
    header = make_page_header(eyebrow="E", title="T", actions=btn)
    assert header.findChildren(QPushButton) == [btn]


def test_multiple_action_widgets_are_added_in_order(qapp):
    from ui.components import make_page_header

    btn1, btn2 = QPushButton("Importer"), QPushButton("+ Nouveau pipeline")
    header = make_page_header(eyebrow="E", title="T", actions=[btn1, btn2])
    assert header.findChildren(QPushButton) == [btn1, btn2]

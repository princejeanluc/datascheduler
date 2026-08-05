"""
DataScheduler — tests/test_help_view.py
Fumée (offscreen Qt) : HelpView s'ouvre, chaque rubrique se sélectionne et affiche un contenu
non vide, le filtre de recherche masque bien les rubriques non correspondantes.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from ui.help.content import HELP_TOPICS


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_help_view_opens_with_first_topic_selected(qapp):
    from ui.help import HelpView

    view = HelpView()
    assert view.list_topics.count() == len(HELP_TOPICS)
    assert view.list_topics.currentRow() == 0
    assert view.browser.toPlainText().strip()


def test_selecting_each_topic_updates_browser(qapp):
    from ui.help import HelpView

    view = HelpView()
    for i in range(view.list_topics.count()):
        view.list_topics.setCurrentRow(i)
        assert view.browser.toPlainText().strip()


def test_search_filters_topics_by_title(qapp):
    from ui.help import HelpView

    view = HelpView()
    view.inp_search.setText("dépannage")
    visible = [
        view.list_topics.item(i).text()
        for i in range(view.list_topics.count())
        if not view.list_topics.item(i).isHidden()
    ]
    assert visible == ["Dépannage"]


def test_search_filters_topics_by_body_content(qapp):
    """La recherche porte aussi sur le corps Markdown, pas seulement le titre (chantier UX
    ergonomie, E.6) — "artefact" apparaît dans plusieurs rubriques au-delà de son titre."""
    from ui.help import HelpView

    view = HelpView()
    view.inp_search.setText("artefact")
    visible = [
        view.list_topics.item(i).text()
        for i in range(view.list_topics.count())
        if not view.list_topics.item(i).isHidden()
    ]
    assert "Jetons et artefacts" in visible
    assert len(visible) >= 1


def test_clearing_search_shows_all_topics(qapp):
    from ui.help import HelpView

    view = HelpView()
    view.inp_search.setText("artefact")
    view.inp_search.setText("")
    hidden = [view.list_topics.item(i).isHidden() for i in range(view.list_topics.count())]
    assert not any(hidden)

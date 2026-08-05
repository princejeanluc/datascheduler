"""
DataScheduler — tests/test_help_search_body.py
Fumée (offscreen Qt) : la recherche de la section Aide (chantier UX ergonomie, E.6) ne testait
jusqu'ici que le titre affiché dans la liste — un utilisateur cherchant un terme technique
présent dans le corps d'une rubrique (ex. "kinit", mentionné uniquement dans le corps de
"Connexions (profils)") ne trouvait rien.
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


def test_search_term_present_only_in_body_still_matches(qapp):
    from ui.help.help_view import HelpView

    idx = next(i for i, t in enumerate(HELP_TOPICS) if "kinit" in t.markdown.lower())
    assert "kinit" not in HELP_TOPICS[idx].title.lower()   # confirme que ce n'est pas le titre

    view = HelpView()
    view.inp_search.setText("kinit")

    assert not view.list_topics.item(idx).isHidden()
    other_idx = next(i for i in range(len(HELP_TOPICS)) if i != idx and "kinit" not in HELP_TOPICS[i].markdown.lower())
    assert view.list_topics.item(other_idx).isHidden()


def test_search_still_matches_title(qapp):
    from ui.help.help_view import HelpView

    view = HelpView()
    view.inp_search.setText(HELP_TOPICS[0].title)
    assert not view.list_topics.item(0).isHidden()


def test_empty_search_shows_all_topics(qapp):
    from ui.help.help_view import HelpView

    view = HelpView()
    view.inp_search.setText("kinit")
    view.inp_search.setText("")
    assert all(not view.list_topics.item(i).isHidden() for i in range(len(HELP_TOPICS)))

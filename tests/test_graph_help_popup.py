"""
DataScheduler — tests/test_graph_help_popup.py
Fumée sur GraphHelpDialog (chantier UX éditeur, Lot 3, C2) : construction + rendu Markdown réel
ne plante pas, même réflexe que les autres smoke tests Qt de cette suite.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
import pytest

from ui.help.content import HelpTopic
from ui.graph_editor.help_popup import GraphHelpDialog


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_graph_help_dialog_renders_topic_without_crashing(qapp):
    topic = HelpTopic(key="t", title="Titre", icon="fa5s.info-circle", markdown="# Titre\n\nCorps.")

    dlg = GraphHelpDialog(topic)

    assert dlg.windowTitle() == "Titre"

"""
DataScheduler — tests/test_export_dialog.py
Fumée : le dialogue d'export s'ouvre sans erreur (offscreen Qt) — même réflexe que
tests/test_step_editor_dialogs.py après le bug de kwargs manquant du chantier 3.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from ui.dialogs import PipelineExportDialog


class _FakePipeline:
    id = 1
    name = "Mon pipeline"


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_export_dialog_opens_without_error(qapp):
    dlg = PipelineExportDialog(None, pipeline=_FakePipeline())
    assert dlg.windowTitle()
    assert dlg.inp_password.text() == ""

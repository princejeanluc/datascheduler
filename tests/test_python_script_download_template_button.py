"""
DataScheduler — tests/test_python_script_download_template_button.py
Bouton "Télécharger un modèle de script" du dialogue PYTHON_SCRIPT — écrit le modèle pédagogique
(ui/step_editor/python_script_template.py) à l'emplacement choisi par l'utilisateur.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QFileDialog

from ui.step_editor import _open_config_dialog
from ui.step_editor.python_script_template import PYTHON_SCRIPT_TEMPLATE


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _open():
    return _open_config_dialog(
        "PYTHON_SCRIPT", {}, None, [], [], [],
        smtp_profiles=[], db_profiles=[], prior_steps=[],
    )


def test_download_template_writes_file_at_chosen_path(qapp, monkeypatch, tmp_path):
    target = tmp_path / "mon_script.py"
    monkeypatch.setattr(QFileDialog, "getSaveFileName",
                         staticmethod(lambda *a, **k: (str(target), "")))

    dlg = _open()
    dlg._download_template()

    assert target.exists()
    assert target.read_text(encoding="utf-8") == PYTHON_SCRIPT_TEMPLATE


def test_download_template_does_nothing_when_dialog_cancelled(qapp, monkeypatch, tmp_path):
    monkeypatch.setattr(QFileDialog, "getSaveFileName",
                         staticmethod(lambda *a, **k: ("", "")))

    dlg = _open()
    dlg._download_template()   # ne doit pas lever, ni créer de fichier

    assert list(tmp_path.iterdir()) == []

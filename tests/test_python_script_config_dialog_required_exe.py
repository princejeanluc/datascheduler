"""
DataScheduler — tests/test_python_script_config_dialog_required_exe.py
Le champ "Exécutable Python" de PYTHON_SCRIPT (chantier "script pour un utilisateur inconnu de
l'app") ne se pré-remplit plus avec sys.executable — un défaut trompeur qui, dans l'.exe
packagé, pointe vers KULU.exe lui-même (voir H.1). Devenu un champ obligatoire, comme
le chemin du script.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox

from ui.step_editor import _open_config_dialog


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _open(config=None):
    return _open_config_dialog(
        "PYTHON_SCRIPT", config or {}, None, [], [], [],
        smtp_profiles=[], db_profiles=[], prior_steps=[],
    )


def test_python_exe_field_is_empty_by_default_on_new_step(qapp):
    dlg = _open()
    assert dlg.inp_py_exe.text() == ""


def test_python_exe_field_preserved_when_editing_existing_step(qapp):
    dlg = _open(config={"python_executable": "C:/venv/mon_projet/Scripts/python.exe"})
    assert dlg.inp_py_exe.text() == "C:/venv/mon_projet/Scripts/python.exe"


def test_saving_without_python_exe_is_blocked(qapp, monkeypatch):
    from ui.step_editor import python_script_config_dialog as psd_module

    warnings = []
    monkeypatch.setattr(psd_module.QMessageBox, "warning",
                         lambda *a, **k: warnings.append(a) or None)

    dlg = _open()
    dlg.inp_script.setText("C:/scripts/traitement.py")
    dlg.inp_py_exe.setText("")   # laissé vide
    dlg._on_ok()

    assert warnings   # bloqué, pas d'accept() silencieux
    assert dlg.result() != QDialog.Accepted


def test_saving_with_python_exe_set_succeeds(qapp):
    dlg = _open()
    dlg.inp_script.setText("C:/scripts/traitement.py")
    dlg.inp_py_exe.setText("C:/venv/mon_projet/Scripts/python.exe")
    dlg._on_ok()

    assert dlg.result() == QDialog.Accepted
    config = dlg._collect_config()
    assert config["python_executable"] == "C:/venv/mon_projet/Scripts/python.exe"


def test_collect_config_never_falls_back_to_sys_executable(qapp):
    """Avant ce correctif, un champ vide était silencieusement remplacé par sys.executable —
    exactement la valeur piégée dans l'.exe packagé. Ne doit plus jamais arriver."""
    dlg = _open()
    dlg.inp_py_exe.setText("")
    config = dlg._collect_config()
    assert config["python_executable"] == ""

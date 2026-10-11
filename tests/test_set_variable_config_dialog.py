"""
DataScheduler — tests/test_set_variable_config_dialog.py
Dialogue SET_VARIABLE : liste dynamique d'assignations (variable cible <- expression), round-trip
collect/prefill, validation à la sauvegarde — y compris la vérification syntaxique de
l'expression via core/expr_lang.py::compile_expression(), nouvelle par rapport au patron
EXTRACT_VARIABLES (qui n'a pas de notion d'expression à valider).
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_starts_with_one_empty_assignment_row(qapp, test_db):
    from ui.step_editor.set_variable_config_dialog import _SetVariableConfigDialog

    dlg = _SetVariableConfigDialog({}, None, "")
    assert dlg.tbl_assignments.rowCount() == 1


def test_add_and_remove_assignment_rows(qapp, test_db):
    from ui.step_editor.set_variable_config_dialog import _SetVariableConfigDialog

    dlg = _SetVariableConfigDialog({}, None, "")
    dlg._add_assignment_row("a", "1")
    dlg._add_assignment_row("b", "2")
    assert dlg.tbl_assignments.rowCount() == 3

    dlg.tbl_assignments.selectRow(1)
    dlg._remove_selected_row()
    assert dlg.tbl_assignments.rowCount() == 2


def test_collect_and_prefill_round_trip(qapp, test_db):
    from ui.step_editor.set_variable_config_dialog import _SetVariableConfigDialog

    dlg = _SetVariableConfigDialog({}, None, "")
    dlg.tbl_assignments.item(0, 0).setText("date_limite")
    dlg.tbl_assignments.item(0, 1).setText("date_add(today(), -7)")

    config = dlg._collect_config()
    assert config["assignments"] == [{"target": "date_limite", "expression": "date_add(today(), -7)"}]

    dlg2 = _SetVariableConfigDialog(config, None, "")
    assert dlg2.tbl_assignments.rowCount() == 1
    assert dlg2.tbl_assignments.item(0, 0).text() == "date_limite"
    assert dlg2.tbl_assignments.item(0, 1).text() == "date_add(today(), -7)"


def test_on_ok_rejects_when_no_assignment_filled(qapp, test_db, monkeypatch):
    from ui.step_editor import set_variable_config_dialog as module
    from ui.step_editor.set_variable_config_dialog import _SetVariableConfigDialog

    warnings = []
    monkeypatch.setattr(module.QMessageBox, "warning", lambda *a, **kw: warnings.append(a) or None)

    dlg = _SetVariableConfigDialog({}, None, "")
    accepted = []
    monkeypatch.setattr(dlg, "accept", lambda: accepted.append(1))
    dlg._on_ok()

    assert warnings
    assert accepted == []


def test_on_ok_rejects_incomplete_assignment(qapp, test_db, monkeypatch):
    from ui.step_editor import set_variable_config_dialog as module
    from ui.step_editor.set_variable_config_dialog import _SetVariableConfigDialog

    warnings = []
    monkeypatch.setattr(module.QMessageBox, "warning", lambda *a, **kw: warnings.append(a) or None)

    dlg = _SetVariableConfigDialog({}, None, "")
    dlg.tbl_assignments.item(0, 0).setText("x")
    # Expression volontairement laissée vide.

    accepted = []
    monkeypatch.setattr(dlg, "accept", lambda: accepted.append(1))
    dlg._on_ok()

    assert warnings
    assert accepted == []


def test_on_ok_rejects_syntactically_invalid_expression(qapp, test_db, monkeypatch):
    from ui.step_editor import set_variable_config_dialog as module
    from ui.step_editor.set_variable_config_dialog import _SetVariableConfigDialog

    warnings = []
    monkeypatch.setattr(module.QMessageBox, "warning", lambda *a, **kw: warnings.append(a) or None)

    dlg = _SetVariableConfigDialog({}, None, "")
    dlg.tbl_assignments.item(0, 0).setText("x")
    dlg.tbl_assignments.item(0, 1).setText("1 +")

    accepted = []
    monkeypatch.setattr(dlg, "accept", lambda: accepted.append(1))
    dlg._on_ok()

    assert warnings
    assert accepted == []


def test_on_ok_rejects_duplicate_target_variable(qapp, test_db, monkeypatch):
    from ui.step_editor import set_variable_config_dialog as module
    from ui.step_editor.set_variable_config_dialog import _SetVariableConfigDialog

    warnings = []
    monkeypatch.setattr(module.QMessageBox, "warning", lambda *a, **kw: warnings.append(a) or None)

    dlg = _SetVariableConfigDialog({}, None, "")
    dlg.tbl_assignments.item(0, 0).setText("x")
    dlg.tbl_assignments.item(0, 1).setText("1")
    dlg._add_assignment_row("x", "2")

    accepted = []
    monkeypatch.setattr(dlg, "accept", lambda: accepted.append(1))
    dlg._on_ok()

    assert warnings
    assert accepted == []


def test_on_ok_accepts_a_complete_valid_assignment(qapp, test_db, monkeypatch):
    from ui.step_editor.set_variable_config_dialog import _SetVariableConfigDialog

    dlg = _SetVariableConfigDialog({}, None, "")
    dlg.tbl_assignments.item(0, 0).setText("x")
    dlg.tbl_assignments.item(0, 1).setText("1 + 1")

    accepted = []
    monkeypatch.setattr(dlg, "accept", lambda: accepted.append(1))
    dlg._on_ok()

    assert accepted == [1]


def test_timeout_s_round_trip(qapp, test_db):
    """Même garde que les autres dialogues (chantier J.1) : timeout_s ne doit jamais se
    réinitialiser silencieusement en rouvrant le dialogue."""
    from ui.step_editor.set_variable_config_dialog import _SetVariableConfigDialog

    dlg = _SetVariableConfigDialog({"timeout_s": 120}, None, "", timeout_s=120)
    assert dlg.inp_timeout.value() == 120
    assert dlg.result_step()["timeout_s"] == 120

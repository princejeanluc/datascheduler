"""
DataScheduler — tests/test_extract_variables_config_dialog.py
Dialogue EXTRACT_VARIABLES : la table de correspondances (premier dialogue de step à liste
dynamique — voir docstring du module), round-trip collect/prefill, visibilité du champ Format
liée au type choisi, et validation à la sauvegarde.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QMessageBox


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_starts_with_one_empty_mapping_row(qapp, test_db):
    from ui.step_editor.extract_variables_config_dialog import _ExtractVariablesConfigDialog

    dlg = _ExtractVariablesConfigDialog({}, None, "")
    assert dlg.tbl_mappings.rowCount() == 1


def test_add_and_remove_mapping_rows(qapp, test_db):
    from ui.step_editor.extract_variables_config_dialog import _ExtractVariablesConfigDialog

    dlg = _ExtractVariablesConfigDialog({}, None, "")
    dlg._add_mapping_row("A", "text", "", "a")
    dlg._add_mapping_row("B", "text", "", "b")
    assert dlg.tbl_mappings.rowCount() == 3

    dlg.tbl_mappings.selectRow(1)
    dlg._remove_selected_row()
    assert dlg.tbl_mappings.rowCount() == 2


def test_format_column_enabled_only_for_date_types(qapp, test_db):
    from ui.step_editor.extract_variables_config_dialog import (
        _ExtractVariablesConfigDialog, _COL_FORMAT, _COL_TYPE,
    )
    from PySide6.QtCore import Qt

    dlg = _ExtractVariablesConfigDialog({}, None, "")
    cb_type = dlg.tbl_mappings.cellWidget(0, _COL_TYPE)
    fmt_item = dlg.tbl_mappings.item(0, _COL_FORMAT)
    assert not (fmt_item.flags() & Qt.ItemIsEnabled)   # "text" par défaut : désactivé

    idx = cb_type.findData("date")
    cb_type.setCurrentIndex(idx)
    fmt_item = dlg.tbl_mappings.item(0, _COL_FORMAT)
    assert fmt_item.flags() & Qt.ItemIsEnabled

    idx = cb_type.findData("text")
    cb_type.setCurrentIndex(idx)
    fmt_item = dlg.tbl_mappings.item(0, _COL_FORMAT)
    assert not (fmt_item.flags() & Qt.ItemIsEnabled)


def test_collect_and_prefill_round_trip(qapp, test_db):
    from ui.step_editor.extract_variables_config_dialog import _ExtractVariablesConfigDialog

    dlg = _ExtractVariablesConfigDialog({}, None, "")
    dlg.inp_explicit_path.setText("C:/data/r.csv")
    row = dlg.tbl_mappings
    row.item(0, 0).setText("MAX_DATE")
    row.item(0, 3).setText("date_max")
    cb_type = row.cellWidget(0, 1)
    cb_type.setCurrentIndex(cb_type.findData("date"))
    row.item(0, 2).setText("{dd}/{MM}/{yyyy}")

    config = dlg._collect_config()
    assert config["explicit_path"] == "C:/data/r.csv"
    assert config["mappings"] == [
        {"source": "MAX_DATE", "target": "date_max", "type": "date", "date_format": "{dd}/{MM}/{yyyy}"}
    ]

    dlg2 = _ExtractVariablesConfigDialog(config, None, "")
    assert dlg2.inp_explicit_path.text() == "C:/data/r.csv"
    assert dlg2.tbl_mappings.rowCount() == 1
    assert dlg2.tbl_mappings.item(0, 0).text() == "MAX_DATE"
    assert dlg2.tbl_mappings.item(0, 3).text() == "date_max"
    assert dlg2.tbl_mappings.item(0, 2).text() == "{dd}/{MM}/{yyyy}"


def test_on_ok_rejects_when_no_mapping_filled(qapp, test_db, monkeypatch):
    from ui.step_editor import extract_variables_config_dialog as module
    from ui.step_editor.extract_variables_config_dialog import _ExtractVariablesConfigDialog

    warnings = []
    monkeypatch.setattr(module.QMessageBox, "warning", lambda *a, **kw: warnings.append(a) or None)

    dlg = _ExtractVariablesConfigDialog({}, None, "")
    accepted = []
    monkeypatch.setattr(dlg, "accept", lambda: accepted.append(1))
    dlg._on_ok()

    assert warnings
    assert accepted == []


def test_on_ok_rejects_date_mapping_without_format(qapp, test_db, monkeypatch):
    from ui.step_editor import extract_variables_config_dialog as module
    from ui.step_editor.extract_variables_config_dialog import _ExtractVariablesConfigDialog

    warnings = []
    monkeypatch.setattr(module.QMessageBox, "warning", lambda *a, **kw: warnings.append(a) or None)

    dlg = _ExtractVariablesConfigDialog({}, None, "")
    dlg.tbl_mappings.item(0, 0).setText("MAX_DATE")
    dlg.tbl_mappings.item(0, 3).setText("date_max")
    cb_type = dlg.tbl_mappings.cellWidget(0, 1)
    cb_type.setCurrentIndex(cb_type.findData("date"))
    # Format volontairement laissé vide.

    accepted = []
    monkeypatch.setattr(dlg, "accept", lambda: accepted.append(1))
    dlg._on_ok()

    assert warnings
    assert accepted == []


def test_on_ok_rejects_duplicate_target_variable(qapp, test_db, monkeypatch):
    from ui.step_editor import extract_variables_config_dialog as module
    from ui.step_editor.extract_variables_config_dialog import _ExtractVariablesConfigDialog

    warnings = []
    monkeypatch.setattr(module.QMessageBox, "warning", lambda *a, **kw: warnings.append(a) or None)

    dlg = _ExtractVariablesConfigDialog({}, None, "")
    dlg.tbl_mappings.item(0, 0).setText("A")
    dlg.tbl_mappings.item(0, 3).setText("x")
    dlg._add_mapping_row("B", "text", "", "x")

    accepted = []
    monkeypatch.setattr(dlg, "accept", lambda: accepted.append(1))
    dlg._on_ok()

    assert warnings
    assert accepted == []


def test_on_ok_accepts_a_complete_mapping(qapp, test_db, monkeypatch):
    from ui.step_editor.extract_variables_config_dialog import _ExtractVariablesConfigDialog

    dlg = _ExtractVariablesConfigDialog({}, None, "")
    dlg.tbl_mappings.item(0, 0).setText("A")
    dlg.tbl_mappings.item(0, 3).setText("a")

    accepted = []
    monkeypatch.setattr(dlg, "accept", lambda: accepted.append(1))
    dlg._on_ok()

    assert accepted == [1]


def test_timeout_s_round_trip(qapp, test_db):
    """Même garde que les autres dialogues (chantier J.1) : timeout_s ne doit jamais se
    réinitialiser silencieusement en rouvrant le dialogue."""
    from ui.step_editor.extract_variables_config_dialog import _ExtractVariablesConfigDialog

    dlg = _ExtractVariablesConfigDialog({"timeout_s": 120}, None, "", timeout_s=120)
    assert dlg.inp_timeout.value() == 120
    assert dlg.result_step()["timeout_s"] == 120

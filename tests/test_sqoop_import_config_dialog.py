"""
DataScheduler — tests/test_sqoop_import_config_dialog.py
Vérifie le dialogue SQOOP_IMPORT — round-trip collect/prefill, visibilité conditionnelle du
champ "Colonne de partitionnement" (masqué tant qu'un seul mapper est configuré, sans effet
sinon), et validation à la sauvegarde (mappers > 1 exige split_by).
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QMessageBox


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_defaults_and_split_by_hidden_by_default(qapp, test_db):
    from ui.step_editor.sqoop_import_config_dialog import _SqoopImportConfigDialog

    dlg = _SqoopImportConfigDialog({}, None, "")
    assert dlg.inp_mappers.value() == 1
    assert dlg.inp_split_by.isHidden()

    dlg.inp_mappers.setValue(4)
    assert not dlg.inp_split_by.isHidden()

    dlg.inp_mappers.setValue(1)
    assert dlg.inp_split_by.isHidden()


def test_collect_and_prefill_round_trip(qapp, test_db):
    from ui.step_editor.sqoop_import_config_dialog import _SqoopImportConfigDialog

    dlg = _SqoopImportConfigDialog({}, None, "")
    dlg.inp_oracle_table.setText("xxx.xxxxx")
    dlg.inp_hcat_db.setText("DD")
    dlg.inp_hcat_table.setText("FINAL_EQUIPEMENT_CLIENT")
    dlg.inp_mappers.setValue(4)
    dlg.inp_split_by.setText("ID_CLIENT")

    config = dlg._collect_config()
    assert config["oracle_table"] == "xxx.xxxxx"
    assert config["hcatalog_database"] == "DD"
    assert config["hcatalog_table"] == "FINAL_EQUIPEMENT_CLIENT"
    assert config["num_mappers"] == 4
    assert config["split_by_column"] == "ID_CLIENT"

    dlg2 = _SqoopImportConfigDialog(config, None, "")
    assert dlg2.inp_oracle_table.text() == "xxx.xxxxx"
    assert dlg2.inp_mappers.value() == 4
    assert dlg2.inp_split_by.text() == "ID_CLIENT"
    assert not dlg2.inp_split_by.isHidden()   # préremplissage doit aussi restaurer la visibilité


def test_timeout_s_round_trip(qapp, test_db):
    """Même garde que test_sqoop_export_config_dialog.py : un champ commun (timeout_s, chantier
    J.1) ne doit jamais se réinitialiser silencieusement en rouvrant le dialogue."""
    from ui.step_editor.sqoop_import_config_dialog import _SqoopImportConfigDialog

    dlg = _SqoopImportConfigDialog({"timeout_s": 120}, None, "", timeout_s=120)
    assert dlg.inp_timeout.value() == 120
    assert dlg.result_step()["timeout_s"] == 120


def test_on_ok_rejects_multiple_mappers_without_split_by(qapp, test_db, monkeypatch):
    from ui.step_editor import sqoop_import_config_dialog as module
    from ui.step_editor.sqoop_import_config_dialog import _SqoopImportConfigDialog

    warnings = []
    monkeypatch.setattr(module.QMessageBox, "warning", lambda *a, **kw: warnings.append(a) or None)

    dlg = _SqoopImportConfigDialog({}, None, "")
    dlg.cb_ssh.addItem("edge", 1); dlg.cb_ssh.setCurrentIndex(dlg.cb_ssh.count() - 1)
    dlg.cb_oracle.addItem("ora", 1); dlg.cb_oracle.setCurrentIndex(dlg.cb_oracle.count() - 1)
    dlg.inp_oracle_table.setText("xxx.t")
    dlg.inp_hcat_db.setText("DD")
    dlg.inp_hcat_table.setText("T")
    dlg.inp_mappers.setValue(4)   # pas de split_by

    accepted = []
    monkeypatch.setattr(dlg, "accept", lambda: accepted.append(1))
    dlg._on_ok()

    assert warnings
    assert accepted == []


def test_on_ok_accepts_multiple_mappers_with_split_by(qapp, test_db, monkeypatch):
    from ui.step_editor.sqoop_import_config_dialog import _SqoopImportConfigDialog

    dlg = _SqoopImportConfigDialog({}, None, "")
    dlg.cb_ssh.addItem("edge", 1); dlg.cb_ssh.setCurrentIndex(dlg.cb_ssh.count() - 1)
    dlg.cb_oracle.addItem("ora", 1); dlg.cb_oracle.setCurrentIndex(dlg.cb_oracle.count() - 1)
    dlg.inp_oracle_table.setText("xxx.t")
    dlg.inp_hcat_db.setText("DD")
    dlg.inp_hcat_table.setText("T")
    dlg.inp_mappers.setValue(4)
    dlg.inp_split_by.setText("ID_CLIENT")

    accepted = []
    monkeypatch.setattr(dlg, "accept", lambda: accepted.append(1))
    dlg._on_ok()

    assert accepted == [1]

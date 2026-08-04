"""
DataScheduler — tests/test_pipeline_dry_run_dialog.py
Fumée (offscreen Qt) : PipelineDryRunDialog (chantier UX autonomie, C.2) lance bien
dry_run_pipeline() dans un thread et affiche le résultat, sans passer par .exec() (bloquerait
indéfiniment sans utilisateur réel pour cliquer Fermer) — on attend la fin du thread directement.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from database import db_manager as db


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_dry_run_dialog_shows_success_for_clean_pipeline(qapp, test_db):
    from ui.dialogs import PipelineDryRunDialog

    p = db.create_pipeline(name="dryrun-dialog-clean")
    db.save_steps(p.id, [{"step_type": "PYTHON_SCRIPT", "config": {"script_path": "C:/scripts/x.py"}}])

    dlg = PipelineDryRunDialog(p.id, p.name, None)
    assert dlg._thread.wait(5000)
    qapp.processEvents()

    assert dlg.btn_close.isEnabled()
    assert dlg.list_findings.count() == 0
    assert "Aucun problème détecté" in dlg.lbl_status.text()


def test_dry_run_dialog_lists_errors_for_missing_reference(qapp, test_db):
    from ui.dialogs import PipelineDryRunDialog

    p = db.create_pipeline(name="dryrun-dialog-missing-ref")
    db.save_steps(p.id, [{
        "step_type": "DB_EXTRACT",
        "config": {"db_type": "ORACLE", "profile_id": 999999, "sql_query_id": 999999},
    }])

    dlg = PipelineDryRunDialog(p.id, p.name, None)
    assert dlg._thread.wait(5000)
    qapp.processEvents()

    assert dlg.list_findings.count() >= 1
    assert "échouée" in dlg.lbl_status.text()

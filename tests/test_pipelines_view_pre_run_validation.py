"""
DataScheduler — tests/test_pipelines_view_pre_run_validation.py
Chantier UX éditeur, Lot 1 (B2) : PipelinesView._on_run_pipeline() valide désormais la structure
du pipeline (dry_run_pipeline(test_connections=False) — jamais de test réseau réel ici, ça reste
le domaine exclusif de "Valider (à blanc)") avant de dispatcher vers RunProgressDialog/le worker.
Une erreur bloque, un avertissement seul propose de continuer, un pipeline propre ne montre
aucune boîte de dialogue (déjà couvert implicitement par tests/test_pipelines_view_background_mode.py,
qui utilise des pipelines valides et ne mocke aucun QMessageBox).
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox

from database import db_manager as db


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_run_pipeline_blocks_on_structural_error_and_never_dispatches(qapp, test_db, monkeypatch):
    """LOCAL_COPY seul, sans producteur en amont ni chemin explicite : REQUIRES non satisfait,
    aucune arête, run_always=False -> erreur bloquante (validate_step_sequence)."""
    from ui.main_window.pipelines_view import PipelinesView

    p = db.create_pipeline(name="pre-run-error-test")
    db.save_steps(p.id, [{"step_type": "LOCAL_COPY", "config": {}}])
    view = PipelinesView()

    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: warnings.append(a)))
    exec_calls = []
    monkeypatch.setattr(QDialog, "exec", lambda self: exec_calls.append(True) or QDialog.Accepted)

    view._on_run_pipeline(p.id)

    assert len(warnings) == 1
    assert exec_calls == []   # jamais dispatché — ni RunProgressDialog ni aucun autre dialogue
    assert db.get_pending_worker_commands() == []


def test_run_pipeline_warning_confirmed_proceeds_to_dispatch(qapp, test_db, monkeypatch):
    """Même pipeline structurellement incomplet, mais run_always=True : la même carence devient
    un avertissement (pas une erreur) — "continuer quand même ?" confirmé -> le run part."""
    from ui.main_window.pipelines_view import PipelinesView

    p = db.create_pipeline(name="pre-run-warning-yes-test")
    db.save_steps(p.id, [{"step_type": "LOCAL_COPY", "config": {}, "run_always": True}])
    view = PipelinesView()

    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.Yes))
    exec_calls = []
    monkeypatch.setattr(QDialog, "exec", lambda self: exec_calls.append(True) or QDialog.Accepted)

    view._on_run_pipeline(p.id)

    assert exec_calls == [True]   # RunProgressDialog().exec() bien atteint


def test_run_pipeline_warning_declined_never_dispatches(qapp, test_db, monkeypatch):
    from ui.main_window.pipelines_view import PipelinesView

    p = db.create_pipeline(name="pre-run-warning-no-test")
    db.save_steps(p.id, [{"step_type": "LOCAL_COPY", "config": {}, "run_always": True}])
    view = PipelinesView()

    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.No))
    exec_calls = []
    monkeypatch.setattr(QDialog, "exec", lambda self: exec_calls.append(True) or QDialog.Accepted)

    view._on_run_pipeline(p.id)

    assert exec_calls == []
    assert db.get_pending_worker_commands() == []

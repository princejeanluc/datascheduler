"""
DataScheduler — tests/test_pipeline_editor_dialog.py
Fumée : PipelineEditorDialog s'ouvre sans erreur (offscreen Qt, même réflexe que
tests/test_export_dialog.py) — vérifie en particulier la confirmation à la suppression d'une
étape, ajoutée pour éviter qu'un clic malheureux supprime une étape sans retour arrière possible
(persona "Amélie", étude UX).
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QMessageBox

from ui.step_editor import PipelineEditorDialog


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _dialog_with_one_step(qapp, test_db):
    dlg = PipelineEditorDialog(None)
    dlg._steps_data = [
        {"step_type": "DB_EXTRACT", "label": "Ma source", "config": {}, "retry_count": 0, "run_always": False},
    ]
    return dlg


def test_delete_step_asks_for_confirmation(qapp, test_db, monkeypatch):
    dlg = _dialog_with_one_step(qapp, test_db)

    asked = {}
    def fake_question(*args, **kwargs):
        asked["called"] = True
        return QMessageBox.No
    monkeypatch.setattr(QMessageBox, "question", staticmethod(fake_question))

    dlg._delete_step(0)

    assert asked.get("called")
    assert len(dlg._steps_data) == 1   # refusé -> rien supprimé


def test_delete_step_proceeds_when_confirmed(qapp, test_db, monkeypatch):
    dlg = _dialog_with_one_step(qapp, test_db)

    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.Yes))

    dlg._delete_step(0)

    assert dlg._steps_data == []


def test_delete_step_confirmation_message_names_the_step(qapp, test_db, monkeypatch):
    dlg = _dialog_with_one_step(qapp, test_db)

    captured = {}
    def fake_question(parent, title, text, *a, **k):
        captured["text"] = text
        return QMessageBox.No
    monkeypatch.setattr(QMessageBox, "question", staticmethod(fake_question))

    dlg._delete_step(0)

    assert "Ma source" in captured["text"]


# ──────────────────────────────────────────────
#  Déclenchement conditionnel (chantier P)
# ──────────────────────────────────────────────

def test_trigger_parent_combo_excludes_self_when_editing(qapp, test_db):
    from database import db_manager as db

    a = db.create_pipeline(name="A")
    db.create_pipeline(name="B")

    dlg = PipelineEditorDialog(None, pipeline=a)
    labels = [dlg.cb_trigger_parent.itemText(i) for i in range(dlg.cb_trigger_parent.count())]
    assert "B" in labels
    assert "A" not in labels


def test_save_sets_trigger_configuration(qapp, test_db):
    from database import db_manager as db

    a = db.create_pipeline(name="A")
    dlg = _dialog_with_one_step(qapp, test_db)
    dlg.inp_name.setText("B")
    idx = dlg.cb_trigger_parent.findData(a.id)
    dlg.cb_trigger_parent.setCurrentIndex(idx)
    idx_cond = dlg.cb_trigger_condition.findData("FAILURE")
    dlg.cb_trigger_condition.setCurrentIndex(idx_cond)

    dlg._on_save()

    b = next(p for p in db.get_pipelines() if p.name == "B")
    assert b.trigger_after_pipeline_id == a.id
    assert str(b.trigger_condition).replace("TriggerCondition.", "") == "FAILURE"


# ──────────────────────────────────────────────
#  (Re)planification immédiate à l'enregistrement
# ──────────────────────────────────────────────
#
# Bug réel signalé par l'utilisateur : un pipeline créé/modifié avec une fréquence Quotidien ou
# Cron ne s'exécutait jamais — le job APScheduler n'était (re)créé qu'au prochain redémarrage de
# l'app ou à un aller-retour actif/inactif, jamais à l'enregistrement lui-même.

def test_save_schedules_the_pipeline_with_apscheduler(qapp, test_db, monkeypatch):
    import core.scheduler as scheduler_module

    calls = []
    fake_sched = type("Fake", (), {"schedule_pipeline": lambda self, pid: calls.append(pid)})()
    monkeypatch.setattr(scheduler_module, "get_scheduler", lambda: fake_sched)

    dlg = _dialog_with_one_step(qapp, test_db)
    dlg.inp_name.setText("scheduled-on-save")

    dlg._on_save()

    from database import db_manager as db
    p = next(p for p in db.get_pipelines() if p.name == "scheduled-on-save")
    assert calls == [p.id]


def test_save_does_not_crash_when_scheduler_not_initialized(qapp, test_db):
    """Tous les autres tests de ce fichier appellent _on_save() sans init_scheduler() — la
    RuntimeError levée par get_scheduler() doit être avalée silencieusement, pas remonter."""
    dlg = _dialog_with_one_step(qapp, test_db)
    dlg.inp_name.setText("no-scheduler-test")

    dlg._on_save()   # ne doit pas lever d'exception

    from database import db_manager as db
    assert any(p.name == "no-scheduler-test" for p in db.get_pipelines())


def test_save_rejects_cycle_and_warns_without_crashing(qapp, test_db, monkeypatch):
    from database import db_manager as db

    a = db.create_pipeline(name="A")
    b = db.create_pipeline(name="B")
    db.set_pipeline_trigger(b.id, a.id, "SUCCESS")   # B se lance déjà après A

    warned = {}
    monkeypatch.setattr(QMessageBox, "warning",
                         staticmethod(lambda *a_, **k: warned.setdefault("called", True)))

    dlg = _dialog_with_one_step(qapp, test_db)
    dlg.inp_name.setText("A")
    dlg._pipeline = a   # édition de A
    idx = dlg.cb_trigger_parent.findData(b.id)
    dlg.cb_trigger_parent.setCurrentIndex(idx)   # A après B -> boucle A->B->A

    dlg._on_save()

    assert warned.get("called")
    assert db.get_pipeline(a.id).trigger_after_pipeline_id is None

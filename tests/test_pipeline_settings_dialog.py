"""
DataScheduler — tests/test_pipeline_settings_dialog.py
Fumée : PipelineSettingsDialog — métadonnées seules (nom/description/actif/planification/
déclenchement conditionnel). Jamais les étapes : l'ancien PipelineEditorDialog les gérait aussi,
mais save_steps() ne touchait jamais aux PipelineEdge, et pouvait donc casser silencieusement un
pipeline construit avec des branches dans l'éditeur graphique — retiré, voir
ui/step_editor/pipeline_settings_dialog.py. Toujours construit sur un pipeline déjà existant
(pas de mode "création" ici — voir PipelinesView._on_new_pipeline pour la création).
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QMessageBox

from ui.step_editor.pipeline_settings_dialog import PipelineSettingsDialog
from ui.styles import COLORS


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _dialog_for(pipeline):
    return PipelineSettingsDialog(None, pipeline=pipeline)


# ──────────────────────────────────────────────
#  Pipeline actif (nouveau — auparavant uniquement dans le menu ⋯ de la liste)
# ──────────────────────────────────────────────

def test_active_checkbox_prefilled_from_pipeline(qapp, test_db):
    from database import db_manager as db

    p = db.create_pipeline(name="settings-active-prefill")
    dlg = _dialog_for(p)
    assert dlg.chk_active.isChecked()   # create_pipeline() -> actif par défaut

    db.set_pipeline_active(p.id, False)
    dlg2 = _dialog_for(db.get_pipeline(p.id))
    assert not dlg2.chk_active.isChecked()


def test_unchecking_active_deactivates_pipeline_on_save(qapp, test_db):
    from database import db_manager as db

    p = db.create_pipeline(name="settings-deactivate-on-save")
    dlg = _dialog_for(p)
    dlg.chk_active.setChecked(False)

    dlg._on_save()

    assert db.get_pipeline(p.id).is_active is False


def test_checking_active_reactivates_pipeline_on_save(qapp, test_db):
    from database import db_manager as db

    p = db.create_pipeline(name="settings-reactivate-on-save")
    db.set_pipeline_active(p.id, False)
    dlg = _dialog_for(db.get_pipeline(p.id))
    dlg.chk_active.setChecked(True)

    dlg._on_save()

    assert db.get_pipeline(p.id).is_active is True


# ──────────────────────────────────────────────
#  Validation
# ──────────────────────────────────────────────

def test_save_rejects_empty_name(qapp, test_db):
    from database import db_manager as db

    p = db.create_pipeline(name="settings-name-required")
    dlg = _dialog_for(p)
    dlg.inp_name.setText("")

    dlg._on_save()

    assert db.get_pipeline(p.id).name == "settings-name-required"   # jamais écrasé
    assert COLORS["danger"] in dlg.inp_name.styleSheet()


# ──────────────────────────────────────────────
#  Déclenchement conditionnel (chantier P)
# ──────────────────────────────────────────────

def test_trigger_parent_combo_excludes_self_when_editing(qapp, test_db):
    from database import db_manager as db

    a = db.create_pipeline(name="settings-trigger-A")
    db.create_pipeline(name="settings-trigger-B")

    dlg = _dialog_for(a)
    labels = [dlg.cb_trigger_parent.itemText(i) for i in range(dlg.cb_trigger_parent.count())]
    assert "settings-trigger-B" in labels
    assert "settings-trigger-A" not in labels


def test_save_sets_trigger_configuration(qapp, test_db):
    from database import db_manager as db

    a = db.create_pipeline(name="settings-trigger-parent")
    b = db.create_pipeline(name="settings-trigger-child")
    dlg = _dialog_for(b)
    idx = dlg.cb_trigger_parent.findData(a.id)
    dlg.cb_trigger_parent.setCurrentIndex(idx)
    idx_cond = dlg.cb_trigger_condition.findData("FAILURE")
    dlg.cb_trigger_condition.setCurrentIndex(idx_cond)

    dlg._on_save()

    reloaded = db.get_pipeline(b.id)
    assert reloaded.trigger_after_pipeline_id == a.id
    assert str(reloaded.trigger_condition).replace("TriggerCondition.", "") == "FAILURE"


def test_save_rejects_cycle_and_warns_without_crashing(qapp, test_db, monkeypatch):
    from database import db_manager as db

    a = db.create_pipeline(name="settings-cycle-A")
    b = db.create_pipeline(name="settings-cycle-B")
    db.set_pipeline_trigger(b.id, a.id, "SUCCESS")   # B se lance déjà après A

    warned = {}
    monkeypatch.setattr(QMessageBox, "warning",
                         staticmethod(lambda *a_, **k: warned.setdefault("called", True)))

    dlg = _dialog_for(a)
    idx = dlg.cb_trigger_parent.findData(b.id)
    dlg.cb_trigger_parent.setCurrentIndex(idx)   # A après B -> boucle A->B->A

    dlg._on_save()

    assert warned.get("called")
    assert db.get_pipeline(a.id).trigger_after_pipeline_id is None


# ──────────────────────────────────────────────
#  Parallélisme intra-pipeline (chantier dédié)
# ──────────────────────────────────────────────

def test_parallel_execution_defaults_unchecked_and_branches_row_hidden(qapp, test_db):
    from database import db_manager as db

    p = db.create_pipeline(name="settings-parallel-default")
    dlg = _dialog_for(p)
    assert not dlg.chk_parallel_execution.isChecked()
    assert dlg._w_parallel_branches.isHidden()


def test_checking_parallel_execution_reveals_branches_spinbox(qapp, test_db):
    from database import db_manager as db

    p = db.create_pipeline(name="settings-parallel-toggle")
    dlg = _dialog_for(p)
    dlg.chk_parallel_execution.setChecked(True)
    assert not dlg._w_parallel_branches.isHidden()

    dlg.chk_parallel_execution.setChecked(False)
    assert dlg._w_parallel_branches.isHidden()


def test_save_persists_parallel_execution_settings(qapp, test_db):
    from database import db_manager as db

    p = db.create_pipeline(name="settings-parallel-save")
    dlg = _dialog_for(p)
    dlg.chk_parallel_execution.setChecked(True)
    dlg.spin_max_parallel_branches.setValue(8)

    dlg._on_save()

    reloaded = db.get_pipeline(p.id)
    assert reloaded.parallel_execution_enabled is True
    assert reloaded.max_parallel_branches == 8


def test_editing_existing_pipeline_prefills_parallel_execution_settings(qapp, test_db):
    from database import db_manager as db

    existing = db.create_pipeline(
        name="settings-parallel-prefill", parallel_execution_enabled=True, max_parallel_branches=10,
    )
    dlg = _dialog_for(existing)

    assert dlg.chk_parallel_execution.isChecked()
    assert not dlg._w_parallel_branches.isHidden()
    assert dlg.spin_max_parallel_branches.value() == 10


# ──────────────────────────────────────────────
#  (Re)planification immédiate à l'enregistrement
# ──────────────────────────────────────────────

def test_save_schedules_the_pipeline_with_apscheduler(qapp, test_db, monkeypatch):
    import core.scheduler as scheduler_module
    from database import db_manager as db

    calls = []
    fake_sched = type("Fake", (), {"schedule_pipeline": lambda self, pid: calls.append(pid)})()
    monkeypatch.setattr(scheduler_module, "get_scheduler", lambda: fake_sched)

    p = db.create_pipeline(name="settings-schedule-on-save")
    dlg = _dialog_for(p)

    dlg._on_save()

    assert calls == [p.id]


def test_save_delegates_to_worker_instead_of_local_scheduler_in_background_mode(qapp, test_db, monkeypatch):
    """Chantier exécution en arrière-plan : en mode BACKGROUND, _on_save() ne doit JAMAIS
    appeler get_scheduler() localement — le worker est le seul exécuteur, la (re)planification
    passe uniquement par la file de commandes (RELOAD)."""
    import core.scheduler as scheduler_module
    from database import db_manager as db

    db.update_app_settings(execution_mode="BACKGROUND")
    monkeypatch.setattr(
        scheduler_module, "get_scheduler",
        lambda: (_ for _ in ()).throw(AssertionError("ne doit pas être appelé en mode arrière-plan")),
    )

    p = db.create_pipeline(name="settings-schedule-background")
    dlg = _dialog_for(p)

    dlg._on_save()   # ne doit pas lever (get_scheduler() jamais appelé)

    pending = db.get_pending_worker_commands()
    assert any(c.command == "RELOAD" for c in pending)


def test_save_does_not_crash_when_scheduler_not_initialized(qapp, test_db):
    """Tous les autres tests de ce fichier appellent _on_save() sans init_scheduler() — la
    RuntimeError levée par get_scheduler() doit être avalée silencieusement, pas remonter."""
    from database import db_manager as db

    p = db.create_pipeline(name="settings-no-scheduler")
    dlg = _dialog_for(p)

    dlg._on_save()   # ne doit pas lever d'exception

    assert db.get_pipeline(p.id) is not None


def test_save_logs_an_audit_event(qapp, test_db):
    """db.update_pipeline() journalise déjà un événement d'audit — contrairement à l'ancienne
    mutation de session brute de PipelineEditorDialog._on_save(), qui n'en journalisait aucun."""
    from database import db_manager as db

    p = db.create_pipeline(name="settings-audit-log")
    dlg = _dialog_for(p)
    dlg.inp_desc.setText("nouvelle description")

    dlg._on_save()

    events = db.get_audit_events(pipeline_id=p.id)
    assert any(e.event_type == "pipeline_edited" for e in events)

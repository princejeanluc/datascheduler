"""
DataScheduler — tests/test_run_progress_dialog.py
Bug réel signalé par l'utilisateur : RunProgressDialog ("Exécuter maintenant") ne pouvait être
fermé de quelque façon que ce soit tant que le pipeline tournait — ni pour juste fermer la
fenêtre (le laisser continuer en arrière-plan), ni pour l'arrêter. Corrigé : "Fermer" est
désormais toujours actif (ferme sans arrêter — le thread reste protégé du ramasse-miettes tant
que le dialogue, parenté à un widget réel, existe), et un nouveau bouton "Arrêter" déclenche
l'interruption coopérative déjà utilisée ailleurs (pipelines_view.py::_on_run_pipeline).

RunProgressThread.start() est neutralisé (monkeypatch) dans tous ces tests : on ne veut pas
qu'un vrai thread d'arrière-plan touche la base SQLite pendant qu'on teste seulement le
comportement des boutons — le dialogue reste donc bloqué en "Initialisation…", ce qui est
exactement l'état qu'on veut inspecter.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QDialog

from database import db_manager as db


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _inert_dialog(monkeypatch, name: str):
    from ui.dialogs.run_progress_dialog import RunProgressDialog, RunProgressThread
    monkeypatch.setattr(RunProgressThread, "start", lambda self: None)
    p = db.create_pipeline(name=name)
    return RunProgressDialog(p.id, p.name, None), p


def test_close_button_is_enabled_while_running(qapp, test_db, monkeypatch):
    dlg, _ = _inert_dialog(monkeypatch, "close-enabled-test")
    assert dlg.btn_close.isEnabled()


def test_close_button_accepts_the_dialog_without_stopping_the_pipeline(qapp, test_db, monkeypatch):
    dlg, _ = _inert_dialog(monkeypatch, "close-accepts-test")

    dlg.btn_close.click()

    assert dlg.result() == QDialog.Accepted


def test_stop_button_requests_cooperative_cancel(qapp, test_db, monkeypatch):
    dlg, p = _inert_dialog(monkeypatch, "stop-test")

    import core.pipeline as pipeline_module
    calls = []
    monkeypatch.setattr(pipeline_module, "request_cancel", lambda pid: calls.append(pid))

    dlg._on_stop_clicked()

    assert calls == [p.id]
    assert not dlg.btn_stop.isEnabled()
    assert "Arrêt demandé" in dlg.lbl_step.text()


def test_closing_while_running_keeps_a_strong_reference_until_finished(qapp, test_db, monkeypatch):
    """Bug réel : fermer la fenêtre pendant l'exécution laissait le pipeline continuer dans un
    QThread référencé seulement par l'attribut Python du dialogue — sans rien de plus, ce
    dialogue devient inatteignable dès que _on_run_pipeline() ne le référence plus après
    .exec(), et le ramasse-miettes peut le récupérer en pleine exécution ("QThread: Destroyed
    while thread is still running", crash confirmé). _background_runs doit empêcher ça."""
    from ui.dialogs.run_progress_dialog import _background_runs

    dlg, _ = _inert_dialog(monkeypatch, "keepalive-test")

    class _FakeRunningThread:
        def isRunning(self):
            return True

    dlg._thread = _FakeRunningThread()
    dlg._on_close_clicked()

    assert dlg in _background_runs


def test_finished_releases_the_keepalive_reference(qapp, test_db, monkeypatch):
    from core.pipeline import PipelineResult
    from ui.dialogs.run_progress_dialog import _background_runs

    dlg, _ = _inert_dialog(monkeypatch, "keepalive-release-test")

    class _FakeRunningThread:
        def isRunning(self):
            return True

    dlg._thread = _FakeRunningThread()
    dlg._on_close_clicked()
    assert dlg in _background_runs

    result = PipelineResult()
    result.success = True
    result.finish()
    dlg._on_finished(result)

    assert dlg not in _background_runs


def test_closing_when_not_running_does_not_register_a_keepalive(qapp, test_db, monkeypatch):
    """self._thread reste None tant que _start() (neutralisé ici) ne l'a pas assigné — fermer
    dans cet état ne doit rien ajouter au registre (rien à protéger)."""
    from ui.dialogs.run_progress_dialog import _background_runs

    dlg, _ = _inert_dialog(monkeypatch, "no-keepalive-test")
    dlg._thread = None

    dlg._on_close_clicked()

    assert dlg not in _background_runs


def test_on_finished_hides_the_stop_button(qapp, test_db, monkeypatch):
    from core.pipeline import PipelineResult

    dlg, _ = _inert_dialog(monkeypatch, "finished-hides-stop-test")
    assert not dlg.btn_stop.isHidden()

    result = PipelineResult()
    result.success = True
    result.finish()
    dlg._on_finished(result)

    assert dlg.btn_stop.isHidden()


# ──────────────────────────────────────────────
#  Étapes actives en parallèle (chantier parallélisme intra-pipeline)
# ──────────────────────────────────────────────

def test_poll_active_steps_stays_hidden_before_the_run_is_discovered(qapp, test_db, monkeypatch):
    dlg, _ = _inert_dialog(monkeypatch, "active-steps-not-discovered-test")

    dlg._poll_active_steps()

    assert dlg._active_steps_run_id is None
    assert dlg.lbl_active_steps.isHidden()


def test_poll_active_steps_stays_hidden_with_only_one_active_step(qapp, test_db, monkeypatch):
    dlg, p = _inert_dialog(monkeypatch, "active-steps-single-test")
    run = db.create_run(p.id)
    db.update_run_active_steps(run.id, {"a": {"label": "Étape A", "pct": 40}})

    dlg._poll_active_steps()

    assert dlg._active_steps_run_id == run.id
    assert dlg.lbl_active_steps.isHidden()


def test_poll_active_steps_shows_list_when_multiple_steps_active(qapp, test_db, monkeypatch):
    dlg, p = _inert_dialog(monkeypatch, "active-steps-multi-test")
    run = db.create_run(p.id)
    db.update_run_active_steps(run.id, {
        "a": {"label": "Étape A", "pct": 40},
        "b": {"label": "Étape B", "pct": 10},
    })

    dlg._poll_active_steps()

    assert not dlg.lbl_active_steps.isHidden()
    assert "Étape A" in dlg.lbl_active_steps.text()
    assert "Étape B" in dlg.lbl_active_steps.text()


def test_poll_active_steps_ignores_a_run_started_before_this_dialog_opened(qapp, test_db, monkeypatch):
    """Même patron que remote_run_dialog.py : un run RUNNING antérieur à l'ouverture de CE
    dialogue (ex: un autre lancement laissé en arrière-plan) ne doit jamais être confondu avec
    celui que ce dialogue vient de démarrer."""
    from datetime import datetime, timedelta

    dlg, p = _inert_dialog(monkeypatch, "active-steps-stale-run-test")
    stale_run = db.create_run(p.id)
    with db.get_session() as s:
        from database.models import PipelineRun
        s.get(PipelineRun, stale_run.id).started_at = datetime.utcnow() - timedelta(minutes=5)
    db.update_run_active_steps(stale_run.id, {"old": {"label": "Vieille étape", "pct": 90}})

    dlg._poll_active_steps()

    assert dlg._active_steps_run_id is None
    assert dlg.lbl_active_steps.isHidden()


def test_on_finished_stops_the_active_steps_timer_and_hides_the_label(qapp, test_db, monkeypatch):
    from core.pipeline import PipelineResult

    dlg, p = _inert_dialog(monkeypatch, "active-steps-finish-test")
    run = db.create_run(p.id)
    db.update_run_active_steps(run.id, {
        "a": {"label": "Étape A", "pct": 40}, "b": {"label": "Étape B", "pct": 10},
    })
    dlg._poll_active_steps()
    assert not dlg.lbl_active_steps.isHidden()

    result = PipelineResult()
    result.success = True
    result.finish()
    dlg._on_finished(result)

    assert dlg.lbl_active_steps.isHidden()
    assert not dlg._active_steps_timer.isActive()

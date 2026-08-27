"""
DataScheduler — tests/test_retry_interval.py
Intervalle de relance configurable par étape (demande utilisateur : "réessayer chaque 30 min,
max 4 tentatives" — un délai fixe de 5s codé en dur ne pouvait pas exprimer ça). Couvre le
moteur (_interruptible_sleep, _run_step_with_policy) et le round-trip DB/export-import.
L'attente reste bloquante pour le thread (choix simple assumé après discussion avec
l'utilisateur — voir RETRY_DELAY_S_DEFAULT dans core/pipeline.py) : seule la réactivité de
l'annulation change, pas l'occupation de la ressource pendant l'attente.
"""

import threading
from types import SimpleNamespace

import core.pipeline as pipeline_module
from core.pipeline import _interruptible_sleep, _run_step_with_policy, PipelineResult
from core.steps.base import BaseStep, StepContext, StepResult


def _fake_step(retry_count=0, retry_interval_s=0, timeout_s=0, run_always=False):
    return SimpleNamespace(retry_count=retry_count, retry_interval_s=retry_interval_s,
                            timeout_s=timeout_s, run_always=run_always)


class _AlwaysFailsStep(BaseStep):
    def __init__(self, config=None):
        super().__init__(config or {})
        self.calls = 0

    def run(self, ctx, cancel_event=None, on_progress=None):
        self.calls += 1
        return StepResult(success=False, error="échec simulé")


# ── _interruptible_sleep ──────────────────────────────

def test_interruptible_sleep_stops_immediately_if_already_cancelled(monkeypatch):
    sleep_calls = []
    monkeypatch.setattr(pipeline_module.time, "sleep", lambda s: sleep_calls.append(s))
    cancel_event = threading.Event()
    cancel_event.set()

    _interruptible_sleep(1800, cancel_event)

    assert sleep_calls == []


def test_interruptible_sleep_stops_as_soon_as_cancellation_is_detected(monkeypatch):
    cancel_event = threading.Event()
    call_count = {"n": 0}

    def _fake_sleep(s):
        call_count["n"] += 1
        if call_count["n"] == 3:
            cancel_event.set()
    monkeypatch.setattr(pipeline_module.time, "sleep", _fake_sleep)

    _interruptible_sleep(1800, cancel_event)   # durerait 1800 tranches sans annulation

    assert call_count["n"] == 3   # s'arrête dès la détection, pas 1800 fois


def test_interruptible_sleep_without_cancellation_sleeps_the_full_duration(monkeypatch):
    sleep_calls = []
    monkeypatch.setattr(pipeline_module.time, "sleep", lambda s: sleep_calls.append(s))

    _interruptible_sleep(2.5, None)

    assert sleep_calls == [1, 1, 0.5]   # tranches de _CANCEL_POLL_INTERVAL_S=1, dernière partielle
    assert sum(sleep_calls) == 2.5


def test_interruptible_sleep_works_without_a_cancel_event():
    """cancel_event=None (pas de chantier annulation coopérative en jeu) ne doit jamais lever."""
    _interruptible_sleep(0, None)   # ne doit pas lever, ne dort pas (durée nulle)


# ── _run_step_with_policy : lit bien l'intervalle CONFIGURÉ, pas un délai fixe ──────────

def test_run_step_with_policy_uses_the_steps_configured_retry_interval(monkeypatch):
    recorded = []
    monkeypatch.setattr(
        pipeline_module, "_interruptible_sleep",
        lambda duration, cancel_event: recorded.append(duration),
    )

    executor = _AlwaysFailsStep()
    result = PipelineResult()
    step = _fake_step(retry_count=2, retry_interval_s=1800)

    _run_step_with_policy(executor, StepContext(), step, lambda *a: None, result)

    assert recorded == [1800, 1800]   # une attente par tentative supplémentaire, à la bonne valeur
    assert executor.calls == 3   # 1 tentative initiale + 2 relances


def test_run_step_with_policy_falls_back_to_default_when_interval_is_none(monkeypatch):
    """Une ligne PipelineStep jamais migrée (théorique — la colonne est NOT NULL) ou un fake de
    test incomplet ne doit pas planter : repli sur RETRY_DELAY_S_DEFAULT."""
    recorded = []
    monkeypatch.setattr(
        pipeline_module, "_interruptible_sleep",
        lambda duration, cancel_event: recorded.append(duration),
    )

    executor = _AlwaysFailsStep()
    result = PipelineResult()
    step = SimpleNamespace(retry_count=1, retry_interval_s=None, timeout_s=0, run_always=False)

    _run_step_with_policy(executor, StepContext(), step, lambda *a: None, result)

    assert recorded == [pipeline_module.RETRY_DELAY_S_DEFAULT]


def test_run_step_with_policy_treats_a_configured_zero_interval_as_immediate(monkeypatch):
    """Contrairement à retry_count/timeout_s, 0 est une vraie valeur de délai (relance
    immédiate) pour retry_interval_s — ne doit jamais silencieusement retomber sur le défaut."""
    recorded = []
    monkeypatch.setattr(
        pipeline_module, "_interruptible_sleep",
        lambda duration, cancel_event: recorded.append(duration),
    )

    executor = _AlwaysFailsStep()
    result = PipelineResult()
    step = _fake_step(retry_count=1, retry_interval_s=0)

    _run_step_with_policy(executor, StepContext(), step, lambda *a: None, result)

    assert recorded == [0]


def test_run_step_with_policy_succeeds_without_waiting_out_the_full_retry_budget(monkeypatch):
    """Si une tentative réussit, la boucle s'arrête immédiatement — pas d'attente ni de
    tentative supplémentaire inutile."""
    monkeypatch.setattr(
        pipeline_module, "_interruptible_sleep",
        lambda *a: (_ for _ in ()).throw(AssertionError("ne devrait jamais dormir ici")),
    )

    class _SucceedsSecondTry(BaseStep):
        def __init__(self):
            super().__init__({})
            self.calls = 0

        def run(self, ctx, cancel_event=None, on_progress=None):
            self.calls += 1
            return StepResult(success=(self.calls >= 1))

    executor = _SucceedsSecondTry()
    result = PipelineResult()
    step = _fake_step(retry_count=4, retry_interval_s=1800)

    step_result = _run_step_with_policy(executor, StepContext(), step, lambda *a: None, result)

    assert step_result.success
    assert executor.calls == 1   # réussi du premier coup, jamais de sleep appelé (voir monkeypatch)


# ── UI : le nouveau champ dans les deux styles de constructeur de dialogue ──────────────
# (11 dialogues "**_" type LocalCopy, 4 à signature explicite type DbExtract — voir
# ui/step_editor/base_config_dialog.py et ui/step_editor/__init__.py::_open_config_dialog)

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_local_copy_dialog_retry_interval_default_and_round_trip(qapp):
    from ui.step_editor.local_copy_config_dialog import _LocalCopyConfigDialog

    dlg = _LocalCopyConfigDialog({}, None, "test-label")
    assert dlg.inp_retry_interval.value() == 5   # défaut — comportement historique inchangé

    dlg.inp_retry.setValue(3)
    dlg.inp_retry_interval.setValue(1800)
    step = dlg.result_step()

    assert step["retry_interval_s"] == 1800


def test_db_extract_dialog_retry_interval_default_and_round_trip(qapp):
    """Constructeur à signature explicite (pas **_) — l'autre des deux styles existants."""
    from ui.step_editor.db_extract_config_dialog import _DbExtractConfigDialog

    dlg = _DbExtractConfigDialog({}, None, "test-label")
    assert dlg.inp_retry_interval.value() == 5

    dlg.inp_retry.setValue(4)
    dlg.inp_retry_interval.setValue(1800)
    step = dlg.result_step()

    assert step["retry_count"] == 4
    assert step["retry_interval_s"] == 1800


def test_retry_interval_prefills_from_existing_step_config(qapp):
    from ui.step_editor.local_copy_config_dialog import _LocalCopyConfigDialog

    dlg = _LocalCopyConfigDialog(
        {}, None, "test-label",
        retry_count=4, retry_interval_s=1800, run_always=False, timeout_s=0,
    )

    assert dlg.inp_retry_interval.value() == 1800


def test_retry_interval_row_hidden_when_no_retries_configured(qapp):
    """Un champ sans effet (0 tentative supplémentaire configurée) ne doit pas rester affiché
    par défaut — évite de laisser croire qu'il fait quelque chose."""
    from ui.step_editor.local_copy_config_dialog import _LocalCopyConfigDialog

    dlg = _LocalCopyConfigDialog({}, None, "test-label")   # retry_count=0 par défaut
    assert dlg.inp_retry_interval.isHidden()

    dlg.inp_retry.setValue(2)
    assert not dlg.inp_retry_interval.isHidden()

    dlg.inp_retry.setValue(0)
    assert dlg.inp_retry_interval.isHidden()


# ── Persistance DB : save_pipeline_graph() est le chemin réel (seul éditeur de pipeline) ──

def test_save_pipeline_graph_persists_and_reloads_retry_interval(qapp, test_db):
    from database import db_manager as db

    pipeline = db.create_pipeline(name="retry-interval-persist-test")
    db.save_pipeline_graph(pipeline.id, steps=[{
        "step_type": "LOCAL_COPY", "label": "", "config": {"_step_key": "a"},
        "retry_count": 4, "retry_interval_s": 1800, "run_always": False, "timeout_s": 0,
    }], edges=[])

    steps = db.get_steps(pipeline.id)
    assert len(steps) == 1
    assert steps[0].retry_count == 4
    assert steps[0].retry_interval_s == 1800


def test_save_pipeline_graph_defaults_retry_interval_when_omitted(qapp, test_db):
    """Un appelant qui n'a pas encore le champ (ex: un vieux test) ne doit pas planter — même
    repli que retry_count/timeout_s."""
    from database import db_manager as db

    pipeline = db.create_pipeline(name="retry-interval-default-test")
    db.save_pipeline_graph(pipeline.id, steps=[{
        "step_type": "LOCAL_COPY", "label": "", "config": {"_step_key": "a"},
    }], edges=[])

    steps = db.get_steps(pipeline.id)
    assert steps[0].retry_interval_s == 5

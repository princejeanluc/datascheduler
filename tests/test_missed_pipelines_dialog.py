"""
DataScheduler — tests/test_missed_pipelines_dialog.py
MissedPipelinesDialog (chantier rattrapage des pipelines manqués au démarrage).
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from datetime import datetime, timedelta

import pytest
from PySide6.QtWidgets import QApplication

from ui.dialogs.missed_pipelines_dialog import MissedPipelinesDialog


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _missed(pipeline_id=1, name="EXPORT_VENTES_QUOTIDIEN", late_minutes=192):
    return {
        "pipeline_id": pipeline_id, "name": name,
        "expected_at": datetime(2026, 8, 25, 6, 0), "late_minutes": late_minutes,
    }


def test_dialog_opens_without_error(qapp):
    dlg = MissedPipelinesDialog(None, [_missed(1, "A"), _missed(2, "B")])
    assert dlg.windowTitle()


def test_singular_title_for_one_pipeline(qapp):
    dlg = MissedPipelinesDialog(None, [_missed(1, "A")])
    assert "1 pipeline manqué" in dlg.windowTitle()
    assert "pipelines" not in dlg.windowTitle()


def test_plural_title_for_several_pipelines(qapp):
    dlg = MissedPipelinesDialog(None, [_missed(1, "A"), _missed(2, "B")])
    assert "2 pipelines manqués" in dlg.windowTitle()


def test_all_checkboxes_checked_by_default(qapp):
    dlg = MissedPipelinesDialog(None, [_missed(1, "A"), _missed(2, "B")])
    assert all(cb.isChecked() for cb in dlg._checkboxes.values())


def test_selection_hint_reflects_checked_count(qapp):
    dlg = MissedPipelinesDialog(None, [_missed(1, "A"), _missed(2, "B")])
    assert dlg.lbl_selected.text() == "2 sur 2 sélectionnés"

    dlg._checkboxes[2].setChecked(False)

    assert dlg.lbl_selected.text() == "1 sur 2 sélectionnés"


def test_launch_button_disabled_when_nothing_checked(qapp):
    dlg = MissedPipelinesDialog(None, [_missed(1, "A")])
    dlg._checkboxes[1].setChecked(False)
    assert not dlg.btn_launch.isEnabled()


def test_launch_selected_triggers_only_checked_and_resolves_them(qapp, test_db, monkeypatch):
    import core.scheduler as scheduler_module
    from core import missed_runs

    triggered = []
    fake_sched = type("Fake", (), {"trigger_now": lambda self, pid: triggered.append(pid)})()
    monkeypatch.setattr(scheduler_module, "get_scheduler", lambda: fake_sched)

    missed_runs._pending.clear()
    missed_runs._pending[1] = _missed(1, "A")
    missed_runs._pending[2] = _missed(2, "B")

    dlg = MissedPipelinesDialog(None, [_missed(1, "A"), _missed(2, "B")])
    dlg._checkboxes[2].setChecked(False)   # B laissé en attente

    dlg._on_launch_selected()

    assert triggered == [1]
    assert [m["pipeline_id"] for m in missed_runs.get_pending()] == [2]


def test_later_button_resolves_nothing(qapp, test_db):
    from core import missed_runs

    missed_runs._pending.clear()
    missed_runs._pending[1] = _missed(1, "A")
    missed_runs._pending[2] = _missed(2, "B")

    dlg = MissedPipelinesDialog(None, [_missed(1, "A"), _missed(2, "B")])

    dlg.reject()

    assert {m["pipeline_id"] for m in missed_runs.get_pending()} == {1, 2}


def test_launch_selected_works_without_an_initialized_scheduler(qapp, test_db, monkeypatch):
    """Le scheduler peut ne pas être initialisé (contexte de test direct) — même garde
    défensive que PipelineSettingsDialog._on_save()."""
    import core.scheduler as scheduler_module
    from core import missed_runs

    def _raise():
        raise RuntimeError("Scheduler non initialisé.")
    monkeypatch.setattr(scheduler_module, "get_scheduler", _raise)

    missed_runs._pending.clear()
    missed_runs._pending[1] = _missed(1, "A")

    dlg = MissedPipelinesDialog(None, [_missed(1, "A")])

    dlg._on_launch_selected()   # ne doit pas lever

    assert missed_runs.get_pending() == []

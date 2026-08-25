"""
DataScheduler — tests/test_dashboard_missed_banner.py
Bandeau "pipelines manqués" du Dashboard (chantier rattrapage au démarrage, phase 4) — ce que le
dialogue de démarrage (MissedPipelinesDialog) n'a pas résolu doit rester visible ici jusqu'à
lancement ou "Ignorer" explicite.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from datetime import datetime

import pytest
from PySide6.QtWidgets import QApplication

from core import missed_runs


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _missed(pipeline_id=1, name="EXPORT_VENTES_QUOTIDIEN", late_minutes=192):
    return {
        "pipeline_id": pipeline_id, "name": name,
        "expected_at": datetime(2026, 8, 25, 6, 0), "late_minutes": late_minutes,
    }


@pytest.fixture(autouse=True)
def _clear_missed_runs():
    missed_runs._pending.clear()
    yield
    missed_runs._pending.clear()


def test_banner_hidden_when_nothing_pending(qapp, test_db):
    from ui.main_window.dashboard_view import DashboardView

    view = DashboardView()
    # isHidden(), pas isVisible() : ce dernier reflète aussi la visibilité des ancêtres et vaut
    # toujours False pour un widget jamais réellement affiché (offscreen, comme ici) — voir
    # PipelineImportPasswordDialog._clear_error() pour le même piège, déjà rencontré.
    assert view._missed_banner.isHidden()


def test_banner_visible_with_one_chip_per_pending_pipeline(qapp, test_db):
    from ui.main_window.dashboard_view import DashboardView

    missed_runs._pending[1] = _missed(1, "A")
    missed_runs._pending[2] = _missed(2, "B")

    view = DashboardView()

    assert not view._missed_banner.isHidden()
    assert view._missed_chips_layout.count() == 2
    assert "2 pipelines manqués" in view._lbl_missed_title.text()


def test_individual_launch_triggers_resolves_and_hides_banner(qapp, test_db, monkeypatch):
    import core.scheduler as scheduler_module
    from ui.main_window.dashboard_view import DashboardView

    triggered = []
    fake_sched = type("Fake", (), {"trigger_now": lambda self, pid: triggered.append(pid)})()
    monkeypatch.setattr(scheduler_module, "get_scheduler", lambda: fake_sched)

    missed_runs._pending[1] = _missed(1, "A")

    view = DashboardView()
    view._on_missed_launch_one(1)

    assert triggered == [1]
    assert missed_runs.get_pending() == []
    assert view._missed_banner.isHidden()


def test_launch_all_triggers_and_resolves_every_pending_pipeline(qapp, test_db, monkeypatch):
    import core.scheduler as scheduler_module
    from ui.main_window.dashboard_view import DashboardView

    triggered = []
    fake_sched = type("Fake", (), {"trigger_now": lambda self, pid: triggered.append(pid)})()
    monkeypatch.setattr(scheduler_module, "get_scheduler", lambda: fake_sched)

    missed_runs._pending[1] = _missed(1, "A")
    missed_runs._pending[2] = _missed(2, "B")

    view = DashboardView()
    view._on_missed_launch_all()

    assert sorted(triggered) == [1, 2]
    assert missed_runs.get_pending() == []


def test_ignore_all_resolves_without_triggering_anything(qapp, test_db, monkeypatch):
    import core.scheduler as scheduler_module
    from ui.main_window.dashboard_view import DashboardView

    fake_sched = type("Fake", (), {"trigger_now": lambda self, pid: pytest.fail("ne doit pas être appelé")})()
    monkeypatch.setattr(scheduler_module, "get_scheduler", lambda: fake_sched)

    missed_runs._pending[1] = _missed(1, "A")
    missed_runs._pending[2] = _missed(2, "B")

    view = DashboardView()
    view._on_missed_ignore_all()

    assert missed_runs.get_pending() == []


def test_launch_actions_work_without_an_initialized_scheduler(qapp, test_db, monkeypatch):
    import core.scheduler as scheduler_module
    from ui.main_window.dashboard_view import DashboardView

    def _raise():
        raise RuntimeError("Scheduler non initialisé.")
    monkeypatch.setattr(scheduler_module, "get_scheduler", _raise)

    missed_runs._pending[1] = _missed(1, "A")

    view = DashboardView()
    view._on_missed_launch_one(1)   # ne doit pas lever

    assert missed_runs.get_pending() == []

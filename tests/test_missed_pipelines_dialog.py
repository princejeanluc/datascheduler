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


# ── A11 ──────────────────────────────────────────────────────────────────

def test_format_late_extends_to_days():
    from ui.dialogs.missed_pipelines_dialog import _format_late

    assert _format_late(30) == "30 min"
    assert _format_late(90) == "1 h 30"
    assert _format_late(26 * 60) == "1 j 2 h"
    assert _format_late(24 * 60) == "1 j"


def test_format_expected_at_shows_french_weekday():
    from ui.dialogs.missed_pipelines_dialog import _format_expected_at

    # 2026-10-17 est un samedi.
    assert _format_expected_at(datetime(2026, 10, 17, 7, 0)) == "samedi 07:00"


def test_row_card_style_is_id_scoped_not_a_bare_rule(qapp):
    """Régression : une première version posait le style de la carte via une règle QSS nue
    (setStyleSheet("background: ...; border: ...") sans sélecteur sur le type QFrame) — QLabel
    hérite de QFrame en Qt, la règle se propageait donc à chaque QLabel enfant sans bordure
    propre, encadrant à tort la ligne "prévue..." séparément du reste de la carte (bug constaté
    à l'écran, reproduit isolément par capture). Corrigé en scopant à un sélecteur d'ID."""
    dlg = MissedPipelinesDialog(None, [_missed(1, "A")])
    row = dlg._checkboxes[1].parentWidget()

    assert row.objectName() == "missed_row"
    assert "QFrame#missed_row" in row.styleSheet()

"""
DataScheduler — tests/test_history_status_filter_and_navigation.py
Fumée (offscreen Qt) : filtre de statut sur l'Historique + navigation depuis les cartes cliquables
du Dashboard (chantier UX ergonomie, E.2) — la critique UX/UI notait que "Succès (30j)"/
"Échecs (30j)" n'étaient que des chiffres inertes, et que l'Historique n'offrait aucun moyen
d'isoler les échecs sans relire toute la liste.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QLabel
from PySide6.QtTest import QTest

from database import db_manager as db


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _make_run(name: str, status: str):
    pipeline = db.create_pipeline(name=name)
    run = db.create_run(pipeline.id)
    db.finish_run(run.id, status=status)
    return run


def test_status_filter_hides_non_matching_rows(qapp, test_db):
    from ui.main_window.history_view import HistoryView

    _make_run("hist-filter-success", "SUCCESS")
    _make_run("hist-filter-failed", "FAILED")

    view = HistoryView()
    assert view.table.rowCount() == 2

    view.set_status_filter("FAILED")
    hidden = [view.table.isRowHidden(r) for r in range(view.table.rowCount())]
    visible_names = [
        view.table.item(r, 0).text()
        for r in range(view.table.rowCount())
        if not view.table.isRowHidden(r)
    ]
    assert visible_names == ["hist-filter-failed"]
    assert any(hidden)


def test_status_filter_combines_with_text_search(qapp, test_db):
    from ui.main_window.history_view import HistoryView

    _make_run("hist-combo-alpha", "FAILED")
    _make_run("hist-combo-beta", "FAILED")

    view = HistoryView()
    view.set_status_filter("FAILED")
    view.inp_search.setText("alpha")

    visible_names = [
        view.table.item(r, 0).text()
        for r in range(view.table.rowCount())
        if not view.table.isRowHidden(r)
    ]
    assert visible_names == ["hist-combo-alpha"]


def test_status_filter_all_shows_every_row(qapp, test_db):
    from ui.main_window.history_view import HistoryView

    _make_run("hist-all-a", "SUCCESS")
    _make_run("hist-all-b", "FAILED")

    view = HistoryView()
    view.set_status_filter("FAILED")
    view.set_status_filter(None)

    assert all(not view.table.isRowHidden(r) for r in range(view.table.rowCount()))


def test_stat_card_emits_clicked_only_when_clickable():
    from ui.main_window.widgets import StatCard

    received = []
    card = StatCard("Titre", clickable=True)
    card.clicked.connect(lambda: received.append(True))
    QTest.mouseClick(card, Qt.LeftButton)
    assert received == [True]

    silent_card = StatCard("Titre")
    silent_received = []
    silent_card.clicked.connect(lambda: silent_received.append(True))
    QTest.mouseClick(silent_card, Qt.LeftButton)
    assert silent_received == []


def test_stat_card_accepts_border_accent_and_defaults_to_signal():
    from ui.main_window.widgets import StatCard
    from ui.styles import COLORS

    default_card = StatCard("Titre")
    assert COLORS["signal"] in default_card.styleSheet()

    custom_card = StatCard("Titre", border_accent=COLORS["danger"])
    assert COLORS["danger"] in custom_card.styleSheet()


def test_dashboard_emits_navigate_to_history_on_card_click(qapp, test_db):
    from ui.main_window.dashboard_view import DashboardView

    view = DashboardView()
    received = []
    view.navigate_to_history.connect(received.append)

    QTest.mouseClick(view._card_failed, Qt.LeftButton)
    assert received == ["FAILED"]

    QTest.mouseClick(view._card_success, Qt.LeftButton)
    assert received == ["FAILED", "SUCCESS"]


def test_dashboard_rail_shows_placeholder_when_nothing_scheduled(qapp, test_db):
    """Rail "Prochaines & en cours" (chantier identité, vague 1, idée 1) — repli discret plutôt
    qu'un rail vide/cassé quand aucun pipeline actif n'est planifié."""
    from ui.main_window.dashboard_view import DashboardView

    view = DashboardView()
    assert view._rail_layout.count() == 1
    placeholder = view._rail_layout.itemAt(0).widget()
    assert isinstance(placeholder, QLabel)
    assert "planifiée" in placeholder.text()


def test_dashboard_rail_shows_an_upcoming_chip_for_a_scheduled_pipeline(qapp, test_db):
    from datetime import datetime, timedelta

    from database.models import Pipeline
    from ui.main_window.dashboard_view import DashboardView

    p = db.create_pipeline(name="rail-upcoming")
    with db.get_session() as s:
        obj = s.get(Pipeline, p.id)
        obj.next_run_at = datetime.utcnow() + timedelta(hours=2)

    view = DashboardView()
    chip_texts = []
    for i in range(view._rail_layout.count()):
        widget = view._rail_layout.itemAt(i).widget()
        if widget is not None:
            chip_texts.append(widget.findChildren(QLabel))
    all_texts = [lbl.text() for chips in chip_texts for lbl in chips]
    assert any("rail-upcoming" in t for t in all_texts)


def test_main_window_navigates_to_filtered_history_on_dashboard_signal(qapp, test_db):
    from core.scheduler import init_scheduler
    from ui.main_window.window import MainWindow

    sched = init_scheduler()
    try:
        _make_run("mw-nav-failed", "FAILED")
        _make_run("mw-nav-success", "SUCCESS")

        win = MainWindow()
        win._on_dashboard_navigate_to_history("FAILED")

        assert win._stack.currentIndex() == 4
        history_view = win._views[4]
        visible_names = [
            history_view.table.item(r, 0).text()
            for r in range(history_view.table.rowCount())
            if not history_view.table.isRowHidden(r)
        ]
        assert visible_names == ["mw-nav-failed"]
    finally:
        sched.stop()
        import core.scheduler as scheduler_module
        scheduler_module._scheduler_instance = None


def test_make_status_badge_pulses_only_for_running(qapp):
    """Pulsation du badge RUNNING (chantier identité, vague 1, idée 3) — centralisée dans
    _make_status_badge() pour bénéficier au Dashboard, Pipelines et Historique d'un coup."""
    from ui.main_window.widgets import _make_status_badge

    running_badge = _make_status_badge("RUNNING", "badge_running")
    assert running_badge.graphicsEffect() is not None
    assert hasattr(running_badge, "_pulse_anim")

    success_badge = _make_status_badge("SUCCESS", "badge_success")
    assert success_badge.graphicsEffect() is None
    assert not hasattr(success_badge, "_pulse_anim")


def test_ordered_with_chains_indents_children_after_their_parent():
    """Chaînes de déclenchement visibles (chantier identité, vague 1, idée 9)."""
    from types import SimpleNamespace
    from ui.main_window.pipelines_view import _ordered_with_chains

    root_a = SimpleNamespace(id=1, trigger_after_pipeline_id=None)
    root_b = SimpleNamespace(id=2, trigger_after_pipeline_id=None)
    child_of_a = SimpleNamespace(id=3, trigger_after_pipeline_id=1)
    grandchild_of_a = SimpleNamespace(id=4, trigger_after_pipeline_id=3)

    ordered = _ordered_with_chains([root_b, grandchild_of_a, root_a, child_of_a])

    assert [(p.id, depth) for p, depth in ordered] == [
        (2, 0), (1, 0), (3, 1), (4, 2),
    ]


def test_ordered_with_chains_ignores_a_self_referential_entry():
    """Filet de sécurité — la création empêche déjà les cycles réels (chantier P), ce test couvre
    seulement la garde défensive de la fonction elle-même."""
    from types import SimpleNamespace
    from ui.main_window.pipelines_view import _ordered_with_chains

    corrupted = SimpleNamespace(id=1, trigger_after_pipeline_id=1)
    ordered = _ordered_with_chains([corrupted])
    assert ordered == []

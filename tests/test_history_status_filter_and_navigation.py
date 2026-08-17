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


def test_stat_card_accepts_a_custom_height():
    """setMinimumHeight, pas setFixedHeight (voir StatCard) — un plancher, pas un plafond qui
    rognerait le contenu si les marges/polices compactes en avaient besoin d'un peu plus."""
    from ui.main_window.widgets import StatCard

    compact = StatCard("Titre", height=88)
    assert compact.minimumHeight() == 88


def test_ring_arcs_empty_when_no_data():
    from ui.main_window.widgets import _ring_arcs

    assert _ring_arcs(0, 0) == []


def test_ring_arcs_full_circle_when_all_success():
    from ui.main_window.widgets import _ring_arcs

    arcs = _ring_arcs(4, 0)
    assert len(arcs) == 1
    color, start, span = arcs[0]
    assert color == "success"
    assert start == 90.0
    assert span == -360.0


def test_ring_arcs_splits_proportionally_between_success_and_danger(qapp):
    from ui.main_window.widgets import _ring_arcs

    arcs = _ring_arcs(3, 1)
    assert [a[0] for a in arcs] == ["success", "danger"]
    (_, s_start, s_span), (_, d_start, d_span) = arcs
    assert s_start == 90.0
    assert s_span == pytest.approx(-270.0)
    assert d_start == pytest.approx(90.0 - 270.0)
    assert d_span == pytest.approx(-90.0)


def test_health_ring_widget_set_data_does_not_raise(qapp):
    from ui.main_window.widgets import HealthRingWidget

    ring = HealthRingWidget()
    ring.set_data(3, 1)
    ring.set_data(0, 0)


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


def test_cap_topology_preview_keeps_whole_chains():
    """Plafond de l'aperçu du Dashboard (chantier "vue globale des pipelines") — une chaîne
    (racine + descendants) n'est jamais coupée en plein milieu."""
    from types import SimpleNamespace

    from ui.main_window.dashboard_view import _cap_topology_preview

    root_a = SimpleNamespace(id=1)
    child_a = SimpleNamespace(id=2)
    root_b = SimpleNamespace(id=3)
    ordered = [(root_a, 0), (child_a, 1), (root_b, 0)]

    capped = _cap_topology_preview(ordered, max_chains=1)

    assert capped == [(root_a, 0), (child_a, 1)]   # la chaîne A entière, pas la racine B


def test_dashboard_shows_see_all_link_only_when_pipelines_exceed_the_cap(qapp, test_db):
    from ui.main_window.dashboard_view import DashboardView

    for i in range(8):
        db.create_pipeline(name=f"cap-test-{i}")

    view = DashboardView()
    assert not view._btn_see_all_topology.isHidden()
    assert "8" in view._btn_see_all_topology.text()


def test_dashboard_hides_see_all_link_when_under_the_cap(qapp, test_db):
    from ui.main_window.dashboard_view import DashboardView

    db.create_pipeline(name="under-cap-only")

    view = DashboardView()
    assert view._btn_see_all_topology.isHidden()


def test_dashboard_health_block_reflects_last_status_per_active_pipeline(qapp, test_db):
    """Bloc santé asymétrique (chantier identité, vague 2, idée 4) — l'anneau ne compte que le
    dernier statut connu par pipeline actif, pas un agrégat de tous les runs des 30 derniers
    jours (voir HealthRingWidget)."""
    from database.models import Pipeline
    from ui.main_window.dashboard_view import DashboardView

    p_ok = db.create_pipeline(name="health-ok")
    p_bad = db.create_pipeline(name="health-bad")
    db.create_pipeline(name="health-never-run")   # reste IDLE — jamais exécuté
    with db.get_session() as s:
        s.get(Pipeline, p_ok.id).last_status = "SUCCESS"
        s.get(Pipeline, p_bad.id).last_status = "FAILED"

    view = DashboardView()
    assert view._health_ring._success == 1
    assert view._health_ring._danger == 1
    assert "health-bad" in view._lbl_health_danger.text()
    assert "1" in view._lbl_health_success.text()
    assert "1" in view._lbl_health_idle.text() and "jamais exécuté" in view._lbl_health_idle.text()
    assert view._card_avg_duration._lbl_value.text() != ""


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


def test_main_window_navigates_to_settings_notifications_on_dashboard_bell_click(qapp, test_db):
    """Chantier écran "Paramètres" : le bouton 🔔 du Dashboard (autrefois
    NotificationSettingsDialog) amène désormais sur la vue Paramètres, catégorie
    Notifications — même patron que le renvoi vers Historique ci-dessus."""
    from core.scheduler import init_scheduler
    from ui.main_window.window import MainWindow

    sched = init_scheduler()
    try:
        win = MainWindow()
        win._on_dashboard_navigate_to_settings("notifications")

        assert win._stack.currentIndex() == 6
        settings_view = win._views[6]
        assert settings_view._active_category == "notifications"
    finally:
        sched.stop()
        import core.scheduler as scheduler_module
        scheduler_module._scheduler_instance = None


def test_dashboard_bell_button_emits_navigate_to_settings(qapp, test_db):
    from ui.main_window.dashboard_view import DashboardView

    view = DashboardView()
    captured = []
    view.navigate_to_settings.connect(captured.append)

    view._on_notifications()

    assert captured == ["notifications"]


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


def test_ordered_with_chains_still_importable_from_widgets(qapp):
    """_ordered_with_chains a déménagé vers widgets.py (chantier identité, vague 3, idée 5 — la
    mini-topologie du Dashboard en a besoin aussi) ; pipelines_view.py la ré-exporte pour ne rien
    casser côté import existant."""
    from ui.main_window.widgets import _ordered_with_chains as from_widgets
    from ui.main_window.pipelines_view import _ordered_with_chains as from_pipelines_view

    assert from_widgets is from_pipelines_view


def test_pipeline_flow_thumbnail_handles_zero_one_and_many_colors(qapp):
    from ui.main_window.widgets import PipelineFlowThumbnail

    PipelineFlowThumbnail([])
    PipelineFlowThumbnail(["#FF7900"])
    PipelineFlowThumbnail(["#FF7900", "#3fb950", "#f85149"])


def test_layout_topology_nodes_keeps_a_chain_on_one_row(qapp):
    from types import SimpleNamespace
    from ui.main_window.widgets import _layout_topology_nodes, PipelineTopologyWidget

    root = SimpleNamespace(id=1, name="root")
    child = SimpleNamespace(id=2, name="child")
    ordered = [(root, 0), (child, 1)]

    positions = _layout_topology_nodes(ordered, max_width=2000)

    assert len(positions) == 2
    (_p1, _d1, x1, y1, parent1), (_p2, _d2, x2, y2, parent2) = positions
    assert y1 == y2                      # même chaîne = même ligne
    assert x2 > x1                       # l'enfant est placé après le parent
    assert parent1 is None
    assert parent2 == root.id


def test_layout_topology_nodes_wraps_to_a_new_row_when_too_narrow(qapp):
    from types import SimpleNamespace
    from ui.main_window.widgets import _layout_topology_nodes

    a = SimpleNamespace(id=1, name="a")
    b = SimpleNamespace(id=2, name="b")
    ordered = [(a, 0), (b, 0)]   # deux racines indépendantes

    positions = _layout_topology_nodes(ordered, max_width=180)   # trop étroit pour 2 nœuds côte à côte

    (_pa, _da, xa, ya, _parenta), (_pb, _db, xb, yb, _parentb) = positions
    assert ya != yb   # repasse à la ligne


def test_pipeline_topology_widget_set_data_does_not_raise(qapp):
    from types import SimpleNamespace

    from ui.main_window.widgets import PipelineTopologyWidget

    solo = SimpleNamespace(id=1, name="solo", is_active=True, last_status="SUCCESS")
    widget = PipelineTopologyWidget()
    widget.set_data([])
    widget.set_data([(solo, 0)])


def test_run_history_dots_handles_various_statuses(qapp):
    from ui.main_window.widgets import RunHistoryDots

    RunHistoryDots([])
    dots = RunHistoryDots(["SUCCESS", "FAILED", "CANCELLED", "RUNNING"])
    dots.set_statuses(["SUCCESS"])


def test_heatmap_day_color_key_worst_result_wins():
    """Calendrier de fréquence (chantier identité, vague 4, idée 13) : un seul échec dans la
    journée colore la case en danger, même si d'autres runs ce jour-là ont réussi."""
    from ui.main_window.widgets import _heatmap_day_color_key

    assert _heatmap_day_color_key({"success": 2, "failed": 1, "cancelled": 0}) == "danger"
    assert _heatmap_day_color_key({"success": 3, "failed": 0, "cancelled": 0}) == "success"
    assert _heatmap_day_color_key({"success": 0, "failed": 0, "cancelled": 0}) == "border"
    assert _heatmap_day_color_key({}) == "border"


def test_run_frequency_heatmap_constructs_without_error(qapp):
    from ui.main_window.widgets import RunFrequencyHeatmap

    RunFrequencyHeatmap([])
    widget = RunFrequencyHeatmap([
        {"success": 1, "failed": 0, "cancelled": 0},
        {"success": 0, "failed": 1, "cancelled": 0},
        {"success": 0, "failed": 0, "cancelled": 0},
    ])
    widget.set_counts([{"success": 1, "failed": 0, "cancelled": 0}])


def test_heatmap_day_tooltip_is_specific_to_that_day():
    """Le survol doit renseigner CE jour précis (date + détail), pas un texte générique
    identique sur toutes les cases — c'est ce qui rendait le calendrier peu informatif."""
    from datetime import date

    from ui.main_window.widgets import _heatmap_day_tooltip

    d = date(2026, 8, 12)
    assert _heatmap_day_tooltip({"date": d, "success": 0, "failed": 0, "cancelled": 0}) == \
        "12/08/2026 — aucune exécution"
    assert _heatmap_day_tooltip({"date": d, "success": 2, "failed": 1, "cancelled": 0}) == \
        "12/08/2026 — 2 succès, 1 échec"
    assert _heatmap_day_tooltip({"date": d, "success": 0, "failed": 2, "cancelled": 1}) == \
        "12/08/2026 — 2 échecs, 1 annulé"


def test_run_frequency_heatmap_emits_day_clicked_only_for_days_with_data(qapp):
    from PySide6.QtCore import QPoint
    from PySide6.QtTest import QTest
    from datetime import date

    from ui.main_window.widgets import RunFrequencyHeatmap

    empty_day = date(2026, 8, 10)
    active_day = date(2026, 8, 11)
    widget = RunFrequencyHeatmap([
        {"date": empty_day, "success": 0, "failed": 0, "cancelled": 0},
        {"date": active_day, "success": 1, "failed": 0, "cancelled": 0},
    ])
    widget.show()

    clicks = []
    widget.day_clicked.connect(clicks.append)

    step = widget.SQUARE + widget.GAP
    QTest.mouseClick(widget, Qt.LeftButton, pos=QPoint(step * 0 + 4, 4))
    assert clicks == []   # jour vide — pas d'exécution à montrer, pas de signal

    QTest.mouseClick(widget, Qt.LeftButton, pos=QPoint(step * 1 + 4, 4))
    assert clicks == [active_day]


def test_history_view_shows_frequency_row_per_active_pipeline(qapp, test_db):
    from ui.main_window.history_view import HistoryView

    active = db.create_pipeline(name="freq-active")
    inactive = db.create_pipeline(name="freq-inactive")
    db.set_pipeline_active(inactive.id, False)
    run = db.create_run(active.id)
    db.finish_run(run.id, status="SUCCESS")

    view = HistoryView()
    names = [
        view._freq_rows_layout.itemAt(i).widget().findChild(QLabel).toolTip()
        for i in range(view._freq_rows_layout.count())
    ]
    assert "freq-active" in names
    assert "freq-inactive" not in names


def test_dashboard_runs_table_groups_multiple_runs_of_the_same_pipeline_into_one_row(qapp, test_db):
    """Dernières exécutions regroupées par pipeline (chantier identité, vague 3, idée 7) — un
    pipeline avec plusieurs runs récents n'occupe qu'une ligne, avec une bande de pastilles pour
    l'historique plutôt qu'un flux chronologique plat."""
    from ui.main_window.dashboard_view import DashboardView

    p = db.create_pipeline(name="dots-pipeline")
    for status in ("SUCCESS", "FAILED", "SUCCESS"):
        run = db.create_run(p.id)
        db.finish_run(run.id, status=status)
    _make_run("other-pipeline", "SUCCESS")

    view = DashboardView()
    assert view.table.rowCount() == 2   # 2 pipelines distincts, pas 4 runs

    names = [view.table.item(r, 0).text() for r in range(view.table.rowCount())]
    assert set(names) == {"dots-pipeline", "other-pipeline"}

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
from PySide6.QtWidgets import QApplication, QLabel, QPushButton
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


def _visible_pipeline_names(view):
    """Noms de pipeline (colonne 1 — Heure est désormais la colonne 0, A5 refonte lot
    A-Historique) des lignes de run visibles, en ignorant les lignes d'en-tête de groupe de jour
    (`view._run_ids[r] is None`)."""
    return [
        view.table.item(r, 1).text()
        for r in range(view.table.rowCount())
        if view._run_ids[r] is not None and not view.table.isRowHidden(r)
    ]


def test_status_filter_hides_non_matching_rows(qapp, test_db):
    from ui.main_window.history_view import HistoryView

    _make_run("hist-filter-success", "SUCCESS")
    _make_run("hist-filter-failed", "FAILED")

    view = HistoryView()
    # 1 ligne d'en-tête de groupe ("AUJOURD'HUI") + 2 runs (A5).
    assert view.table.rowCount() == 3

    view.set_status_filter("FAILED")
    hidden = [view.table.isRowHidden(r) for r in range(view.table.rowCount())]
    assert _visible_pipeline_names(view) == ["hist-filter-failed"]
    assert any(hidden)


def test_status_filter_combines_with_text_search(qapp, test_db):
    from ui.main_window.history_view import HistoryView

    _make_run("hist-combo-alpha", "FAILED")
    _make_run("hist-combo-beta", "FAILED")

    view = HistoryView()
    view.set_status_filter("FAILED")
    view.inp_search.setText("alpha")

    assert _visible_pipeline_names(view) == ["hist-combo-alpha"]


def test_search_matches_run_error_message(qapp, test_db):
    """A2 : la recherche libre porte aussi sur le message d'erreur du run, pas seulement sur les
    colonnes visibles du tableau — retrouver un échec par son message sans déjà savoir quel
    pipeline l'a produit."""
    from ui.main_window.history_view import HistoryView

    p = db.create_pipeline(name="hist-search-error")
    run = db.create_run(p.id)
    db.finish_run(run.id, status="FAILED", error_message="connexion refusée par le serveur distant")
    other = db.create_run(p.id)
    db.finish_run(other.id, status="SUCCESS")

    view = HistoryView()
    view.inp_search.setText("refusée")

    assert _visible_pipeline_names(view) == ["hist-search-error"]


def test_status_filter_uses_segmented_buttons_not_a_combobox(qapp, test_db):
    """A3 : le filtre de statut est désormais 5 boutons segmentés (même patron que
    ResourcesView._set_active_range), pas une QComboBox — set_status_filter garde le même
    contrat public (accepte None/""/un code)."""
    from ui.main_window.history_view import HistoryView

    _make_run("hist-segmented-ok", "SUCCESS")
    _make_run("hist-segmented-ko", "FAILED")

    view = HistoryView()
    assert not hasattr(view, "cb_status")
    assert set(view._status_buttons.keys()) == {None, "SUCCESS", "FAILED", "RUNNING", "CANCELLED"}

    view.set_status_filter("FAILED")
    assert view._status_filter == "FAILED"
    assert _visible_pipeline_names(view) == ["hist-segmented-ko"]

    view.set_status_filter("")
    assert view._status_filter is None
    assert set(_visible_pipeline_names(view)) == {"hist-segmented-ok", "hist-segmented-ko"}


def test_status_filter_all_shows_every_row(qapp, test_db):
    from ui.main_window.history_view import HistoryView

    _make_run("hist-all-a", "SUCCESS")
    _make_run("hist-all-b", "FAILED")

    view = HistoryView()
    view.set_status_filter("FAILED")
    view.set_status_filter(None)

    assert all(not view.table.isRowHidden(r) for r in range(view.table.rowCount()))


def test_history_view_tabs_switch_between_executions_and_modifications(qapp, test_db):
    from ui.main_window.history_view import HistoryView

    view = HistoryView()
    assert view._tabs_stack.currentIndex() == 0

    view._set_active_tab(1)
    assert view._tabs_stack.currentIndex() == 1

    view._set_active_tab(0)
    assert view._tabs_stack.currentIndex() == 0


def test_history_view_eyebrow_counts_runs_and_failures_over_7_days(qapp, test_db):
    from ui.main_window.history_view import HistoryView

    _make_run("hist-eyebrow-ok", "SUCCESS")
    _make_run("hist-eyebrow-ko", "FAILED")

    view = HistoryView()
    assert view._eyebrow_lbl.text() == "2 EXÉCUTIONS SUR 7 JOURS · 1 ÉCHEC"


def test_format_duration_short_matches_pipelines_format():
    from ui.main_window.history_view import _format_duration_short

    assert _format_duration_short(None) == "—"
    assert _format_duration_short(0) == "0 s"
    assert _format_duration_short(38) == "38 s"
    assert _format_duration_short(124) == "2 min 04"


def test_history_view_table_groups_todays_runs_under_a_day_header(qapp, test_db):
    """A5 : une ligne d'en-tête non sélectionnable, fusionnée sur toute la largeur, précède les
    runs d'aujourd'hui — un seul QTableWidget, pas des tableaux séparés par jour (question 6)."""
    from ui.main_window.history_view import HistoryView

    run = _make_run("hist-group-today", "SUCCESS")

    view = HistoryView()
    assert view._run_ids[0] is None
    assert view.table.item(0, 0).text() == "AUJOURD'HUI"
    assert not (view.table.item(0, 0).flags() & Qt.ItemIsSelectable)
    assert view.table.columnSpan(0, 0) == 7
    assert view._run_ids[1] == run.id


def test_history_view_rows_exported_distinguishes_zero_from_none(qapp, test_db):
    """A6 : "0" quand rows_exported vaut réellement 0, "—" seulement quand il est absent — les
    deux cas rendaient autrefois le même tiret."""
    from ui.main_window.history_view import HistoryView

    p = db.create_pipeline(name="hist-rows-zero")
    r_zero = db.create_run(p.id)
    db.finish_run(r_zero.id, status="SUCCESS", rows_exported=0)
    r_none = db.create_run(p.id)
    db.finish_run(r_none.id, status="FAILED")

    view = HistoryView()
    row_zero = view._run_ids.index(r_zero.id)
    row_none = view._run_ids.index(r_none.id)
    assert view.table.item(row_zero, 3).text() == "0"
    assert view.table.item(row_none, 3).text() == "—"


def test_history_view_status_badge_is_french_with_status_code_property(qapp, test_db):
    """A7 : le badge affiche un libellé français, mais garde le code anglais en propriété
    `status_code` — _apply_filters en dépend (badge.text() ne peut plus servir de clé de
    comparaison une fois le texte traduit)."""
    from ui.main_window.history_view import HistoryView

    run = _make_run("hist-badge-fr", "FAILED")

    view = HistoryView()
    row = view._run_ids.index(run.id)
    badge = view.table.cellWidget(row, 4)
    assert badge.text() == "Échec"
    assert badge.property("status_code") == "FAILED"


def test_history_view_row_actions_drop_magnifier_and_add_resume(qapp, test_db):
    """A8 : la loupe "Voir le log complet" disparaît (ouverture par double-clic désormais) ;
    "Reprendre depuis l'échec" apparaît uniquement pour un run avec un état de reprise
    persisté."""
    from PySide6.QtWidgets import QPushButton

    from ui.main_window.history_view import HistoryView

    p = db.create_pipeline(name="hist-resume")
    run = db.create_run(p.id)
    db.finish_run(run.id, status="FAILED", resumable_state_json="{}")
    other = db.create_run(p.id)
    db.finish_run(other.id, status="FAILED")

    view = HistoryView()
    row = view._run_ids.index(run.id)
    row_other = view._run_ids.index(other.id)
    buttons = view.table.cellWidget(row, 6).findChildren(QPushButton)
    tooltips = {b.toolTip() for b in buttons}
    assert "Voir le log complet" not in tooltips
    assert "Reprendre depuis l'échec" in tooltips

    buttons_other = view.table.cellWidget(row_other, 6).findChildren(QPushButton)
    assert "Reprendre depuis l'échec" not in {b.toolTip() for b in buttons_other}


def test_convert_log_text_times_reconstructs_local_time_and_handles_midnight_rollover(test_db):
    """A10/T3 : PipelineResult.log() (core/pipeline.py) écrit chaque ligne en UTC, heure seule —
    la fonction doit reconstruire la date complète depuis started_at et la faire avancer d'un
    jour quand l'heure analysée est plus tôt que celle de la ligne précédente (minuit franchi)."""
    from datetime import datetime

    from ui.main_window.history_view import _convert_log_text_times

    # Fuseau explicitement UTC (le défaut d'une base neuve suit le fuseau de la machine qui
    # l'a créée, voir database/models.py::_default_timezone) — pour que to_display() soit
    # l'identité ici et que la reconstruction de date reste testée telle quelle.
    db.update_app_settings(timezone="UTC")
    started = datetime(2026, 10, 19, 23, 50, 0)
    log_text = "[23:50:05] démarrage\n[00:00:02] après minuit\nligne sans horodatage"

    out = _convert_log_text_times(log_text, started)
    lines = out.splitlines()
    assert lines[0] == "[23:50:05] démarrage"
    assert lines[1] == "[00:00:02] après minuit"
    assert lines[2] == "ligne sans horodatage"


def test_convert_log_text_times_handles_empty_input():
    from ui.main_window.history_view import _convert_log_text_times

    assert _convert_log_text_times("", None) == ""
    assert _convert_log_text_times(None, None) == ""


def test_history_view_run_panel_shows_resume_and_graph_buttons_for_a_resumable_failure(qapp, test_db):
    """A10 : le pied du panneau propose "Reprendre depuis l'échec" (état de reprise persisté) et
    "Voir dans le graphe" (échec avec un nœud fautif identifié) — jamais "Exporter le journal"
    (C7, gated)."""
    from ui.main_window.history_view import HistoryView

    p = db.create_pipeline(name="hist-panel-buttons")
    run = db.create_run(p.id)
    db.finish_run(
        run.id, status="FAILED", failed_step_key="step-1",
        resumable_state_json="{}", error_message="échec réseau",
    )

    view = HistoryView()
    view._open_run_panel(run.id)

    buttons = [b for b in view._side_panel.findChildren(QPushButton) if b.text()]
    texts = {b.text() for b in buttons}
    assert "Reprendre depuis l'échec" in texts
    assert "Voir dans le graphe" in texts
    assert "Exporter le journal" not in texts


def test_history_view_run_panel_graph_button_emits_open_atelier_run_requested(qapp, test_db):
    """C9 (Atelier-echec) : le bouton "Voir dans le graphe" du panneau de run émet
    open_atelier_run_requested(pipeline_id, run_id, failed_step_key) — avec l'id du run, pas
    seulement highlight_step_key (voir test_history_view_graph_link.py pour le même changement
    côté lien de la ligne principale)."""
    from ui.main_window.history_view import HistoryView

    p = db.create_pipeline(name="hist-panel-graph-signal")
    run = db.create_run(p.id)
    db.finish_run(run.id, status="FAILED", failed_step_key="step-1")

    view = HistoryView()
    captured = []
    view.open_atelier_run_requested.connect(lambda *args: captured.append(args))
    view._open_run_panel(run.id)

    btn_graph = next(b for b in view._side_panel.findChildren(QPushButton) if b.text() == "Voir dans le graphe")
    btn_graph.click()

    assert captured == [(p.id, run.id, "step-1")]


def test_history_view_run_panel_missing_run_does_not_raise(qapp, test_db):
    from ui.main_window.history_view import HistoryView

    view = HistoryView()
    view._open_run_panel(999_999)   # pas de run -> ne doit pas lever, panneau reste fermé
    assert view._side_panel.isHidden()


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
        assert _visible_pipeline_names(history_view) == ["mw-nav-failed"]
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
    """Calendrier de fréquence (chantier identité, vague 4, idée 13 ; refonte lot A-Historique,
    A4/T2 : 4 niveaux) : un seul échec dans la journée colore la case en danger, même si d'autres
    runs ce jour-là ont réussi ; une case sans exécution est bg_card (fond de carte, pas une
    bordure) ; exactement 1 réussite sans échec a sa propre teinte (success_dim), plus discrète
    qu'une vraie séquence de réussites (success, 2+)."""
    from ui.main_window.widgets import _heatmap_day_color_key

    assert _heatmap_day_color_key({"success": 2, "failed": 1, "cancelled": 0}) == "danger"
    assert _heatmap_day_color_key({"success": 3, "failed": 0, "cancelled": 0}) == "success"
    assert _heatmap_day_color_key({"success": 1, "failed": 0, "cancelled": 0}) == "success_dim"
    assert _heatmap_day_color_key({"success": 0, "failed": 0, "cancelled": 0}) == "bg_card"
    assert _heatmap_day_color_key({}) == "bg_card"


def test_run_frequency_heatmap_constructs_without_error(qapp):
    from ui.main_window.widgets import RunFrequencyHeatmap

    RunFrequencyHeatmap([])
    widget = RunFrequencyHeatmap([
        {"success": 1, "failed": 0, "cancelled": 0},
        {"success": 0, "failed": 1, "cancelled": 0},
        {"success": 0, "failed": 0, "cancelled": 0},
    ])
    widget.set_counts([{"success": 1, "failed": 0, "cancelled": 0}])


def test_heatmap_month_markers_constructs_without_error(qapp):
    from ui.main_window.widgets import HeatmapMonthMarkers

    HeatmapMonthMarkers(0)
    markers = HeatmapMonthMarkers(90)
    assert markers.width() > 0


def test_make_heatmap_legend_has_four_entries(qapp):
    from PySide6.QtWidgets import QLabel

    from ui.main_window.widgets import make_heatmap_legend

    legend = make_heatmap_legend()
    labels = [lbl.text() for lbl in legend.findChildren(QLabel) if lbl.text()]
    assert labels == ["aucune", "1 réussie", "plusieurs réussies", "au moins un échec"]


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


def _freq_row_names(view) -> list[str]:
    return [
        view._freq_rows_layout.itemAt(i).widget().findChild(QLabel).toolTip()
        for i in range(view._freq_rows_layout.count())
    ]


def test_history_view_frequency_section_caps_at_ten_by_default(qapp, test_db):
    """Passage à l'échelle — sans recherche, la section ne montre que les 10 pipelines actifs les
    plus actifs, pas tous (voir db.get_most_active_pipelines)."""
    from ui.main_window.history_view import HistoryView

    for i in range(15):
        db.create_pipeline(name=f"freq-scale-{i}")

    view = HistoryView()
    assert len(_freq_row_names(view)) == 10


def test_history_view_search_reveals_pipeline_excluded_by_default_cap(qapp, test_db):
    """Un pipeline peu actif, hors du top 10 par défaut, doit redevenir visible dans la section
    fréquence dès qu'on le cherche par nom — c'est tout l'objet du câblage recherche <-> fréquence."""
    from ui.main_window.history_view import HistoryView

    target = db.create_pipeline(name="freq-search-target")
    for i in range(12):
        busy = db.create_pipeline(name=f"freq-search-noise-{i}")
        run = db.create_run(busy.id)
        db.finish_run(run.id, status="SUCCESS")

    view = HistoryView()
    assert "freq-search-target" not in _freq_row_names(view)

    view.inp_search.setText("freq-search-target")
    assert _freq_row_names(view) == ["freq-search-target"]

    view.inp_search.setText("")
    assert "freq-search-target" not in _freq_row_names(view)


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

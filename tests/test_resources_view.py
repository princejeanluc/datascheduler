"""
DataScheduler — tests/test_resources_view.py
Chantier suivi des ressources : construction de ResourcesView/_TimeSeriesChart, synchronisation
du curseur au survol, et panneau de corrélation ("pipelines actifs à l'instant survolé") —
déduit de PipelineRun.started_at/finished_at déjà chargés pour la fenêtre visible, pas d'une
nouvelle requête par mouvement de souris.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from datetime import datetime, timedelta

import pytest
from PySide6.QtWidgets import QApplication

from database import db_manager as db


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _panel_text(view) -> str:
    """Texte concaténé de tous les QLabel du panneau de corrélation — pour vérifier son contenu
    sans dépendre de la structure exacte des puces (chips)."""
    from PySide6.QtWidgets import QLabel
    return " ".join(lbl.text() for lbl in view._correlate_panel.findChildren(QLabel))


def test_time_series_chart_constructs_and_renders_without_error(qapp):
    from ui.main_window.resources_view import _TimeSeriesChart

    chart = _TimeSeriesChart("#3987e5")
    chart.set_data([])
    chart.set_data([10.0, 20.0, 15.0, 30.0])
    chart.resize(200, 80)
    chart.repaint()


def test_time_series_chart_index_at_x_maps_across_full_width(qapp):
    from ui.main_window.resources_view import _TimeSeriesChart

    chart = _TimeSeriesChart("#3987e5")
    chart.set_data([1.0, 2.0, 3.0, 4.0, 5.0])
    chart.resize(100, 80)

    plot = chart._plot_rect()
    assert chart._index_at_x(plot.left()) == 0
    assert chart._index_at_x(plot.right()) == 4


def test_time_series_chart_emits_hovered_on_mouse_move(qapp):
    from ui.main_window.resources_view import _TimeSeriesChart

    chart = _TimeSeriesChart("#3987e5")
    chart.set_data([1.0, 2.0, 3.0])
    chart.resize(90, 80)

    captured = []
    chart.hovered.connect(captured.append)
    idx = chart._index_at_x(chart._plot_rect().right())
    chart.hovered.emit(idx)   # même effet que mouseMoveEvent, sans simuler un vrai événement souris

    assert captured == [2]


def test_resources_view_constructs_without_error(qapp, test_db):
    from ui.main_window.resources_view import ResourcesView

    view = ResourcesView()
    assert view._samples == []   # aucun échantillon enregistré dans test_db


def test_resources_view_loads_samples_and_updates_charts(qapp, test_db):
    from ui.main_window.resources_view import ResourcesView

    db.record_resource_sample(cpu_percent=10.0, memory_mb=200.0)
    db.record_resource_sample(cpu_percent=20.0, memory_mb=210.0)

    view = ResourcesView()

    assert len(view._samples) == 2
    assert view._chart_cpu._values == [10.0, 20.0]


def test_resources_view_correlate_panel_lists_active_pipelines_at_hovered_instant(qapp, test_db):
    from ui.main_window.resources_view import ResourcesView

    pipeline = db.create_pipeline(name="hover-test-pipeline")
    run = db.create_run(pipeline.id)   # started_at ~ maintenant, finished_at NULL (en cours)
    db.record_resource_sample(cpu_percent=42.0, memory_mb=300.0)

    view = ResourcesView()
    assert len(view._samples) == 1

    view._on_chart_hover(0)

    # Le panneau ne contient plus le message vide, et une puce nomme le pipeline en cours.
    labels_text = _panel_text(view)
    assert "hover-test-pipeline" in labels_text


def test_resources_view_chip_row_ends_with_a_stretch_not_full_width_chip(qapp, test_db):
    """Bug réel trouvé en usage : sans ressort final, une puce unique s'étirait pour occuper
    toute la largeur du panneau au lieu de rester compacte alignée à gauche."""
    from ui.main_window.resources_view import ResourcesView

    pipeline = db.create_pipeline(name="stretch-test-pipeline")
    db.create_run(pipeline.id)
    db.record_resource_sample(cpu_percent=1.0, memory_mb=100.0)

    view = ResourcesView()
    view._on_chart_hover(0)

    layout = view._correlate_chips_layout
    assert layout.count() >= 2   # au moins le chip + le ressort final
    last_item = layout.itemAt(layout.count() - 1)
    assert last_item.widget() is None   # le dernier élément est un espaceur, pas un widget
    assert last_item.spacerItem() is not None


def test_resources_view_correlate_panel_shows_empty_state_when_nothing_running(qapp, test_db):
    from ui.main_window.resources_view import ResourcesView

    db.record_resource_sample(cpu_percent=5.0, memory_mb=150.0)
    view = ResourcesView()

    view._on_chart_hover(0)

    assert "Aucun pipeline en cours" in _panel_text(view)


def test_resources_view_hover_left_resets_crosshair_and_panel(qapp, test_db):
    from ui.main_window.resources_view import ResourcesView

    db.record_resource_sample(cpu_percent=5.0, memory_mb=150.0)
    view = ResourcesView()
    view._on_chart_hover(0)

    view._on_chart_hover_left()

    assert view._chart_cpu._crosshair_index is None
    assert not view._correlate_empty.isHidden()


def test_resources_view_survives_repeated_hover_cycles(qapp, test_db):
    """Bug réel trouvé en usage : _correlate_empty était réinjecté dans le layout via
    addWidget() après une boucle qui videait le layout au deleteLater() de tout ce qu'il
    contenait — dès que _correlate_empty s'y trouvait déjà au moment du nettoyage suivant, il
    était supprimé pour de bon (RuntimeError: Internal C++ object already deleted au survol
    suivant). Ce test répète plusieurs cycles survol/sortie/survol pour verrouiller que les
    widgets persistants (_correlate_empty, _correlate_time_lbl) ne sont jamais détruits."""
    from ui.main_window.resources_view import ResourcesView

    pipeline = db.create_pipeline(name="repeat-hover-pipeline")
    db.create_run(pipeline.id)   # en cours (finished_at NULL)
    for _ in range(3):
        db.record_resource_sample(cpu_percent=10.0, memory_mb=200.0)

    view = ResourcesView()

    for _ in range(5):
        view._on_chart_hover(0)
        view._on_chart_hover_left()
        view._on_chart_hover(1)
        view._on_chart_hover_left()

    # Ne doit lever aucune RuntimeError — et les widgets persistants doivent toujours exister.
    assert not view._correlate_empty.isHidden()
    assert view._correlate_time_lbl.isHidden()


def test_resources_view_running_count_at_reflects_overlapping_runs(qapp, test_db):
    from ui.main_window.resources_view import ResourcesView
    from database.models import PipelineRun

    pipeline = db.create_pipeline(name="count-test-pipeline")
    run = db.create_run(pipeline.id)
    with db.get_session() as s:
        r = s.get(PipelineRun, run.id)
        r.started_at = datetime.utcnow() - timedelta(minutes=10)
        r.finished_at = datetime.utcnow() - timedelta(minutes=5)   # déjà terminé

    view = ResourcesView()
    view._runs = db.get_runs_overlapping_window(
        datetime.utcnow() - timedelta(hours=1), datetime.utcnow()
    )

    # À l'instant du démarrage : en cours. Maintenant : terminé.
    assert view._running_count_at(datetime.utcnow() - timedelta(minutes=8)) == 1
    assert view._running_count_at(datetime.utcnow()) == 0


def test_resources_view_range_buttons_change_range_hours(qapp, test_db):
    from ui.main_window.resources_view import ResourcesView

    view = ResourcesView()
    assert view._range_hours == 24

    view._on_range_changed(1)
    assert view._range_hours == 1


# ── A2 : graduations verticales ────────────────────────────────────────────

def test_nice_ceiling_rounds_up_to_a_round_step():
    from ui.main_window.resources_view import _nice_ceiling

    assert _nice_ceiling(182) == 200
    assert _nice_ceiling(587) == 1000
    assert _nice_ceiling(3) == 5
    assert _nice_ceiling(0) == 1.0


def test_chart_max_value_accounts_for_reference_line(qapp):
    from ui.main_window.resources_view import _TimeSeriesChart

    chart = _TimeSeriesChart("#d95926")
    chart.set_data([1.0, 2.0])
    chart.set_reference(6.0, "plafond 6")

    # Sans la référence, le maximum "rond" serait ancré sur les données (2 * 1.15 -> 5) ; la
    # ligne de plafond (6) doit rester visible même si les données ne l'atteignent jamais.
    assert chart._max_value() >= 6.0


# ── A3 : axe du temps commun ───────────────────────────────────────────────

def _minutes_span(start: datetime, count: int, step_minutes: int) -> list[datetime]:
    return [start + timedelta(minutes=i * step_minutes) for i in range(count)]


def test_time_axis_ticks_every_3h_over_a_24h_span_without_adjacent_duplicates(qapp, test_db):
    from ui.main_window.resources_view import _TimeAxis

    axis = _TimeAxis()
    start = datetime(2026, 10, 18, 14, 31)   # pas aligné sur une limite ronde, comme un vrai survol
    axis.set_data(_minutes_span(start, 24 * 60, 1))

    ticks = axis._tick_indices()
    assert len(ticks) >= 6   # ~8 graduations attendues sur 24h au pas de 3h

    # Régression : le premier échantillon ne doit jamais être une graduation forcée — sinon un
    # libellé apparaissait collé au suivant, à quelques minutes d'écart (chevauchement constaté).
    assert 0 not in ticks

    # Deux graduations consécutives doivent rester à au moins ~2h d'écart (jamais quelques
    # minutes), peu importe où tombe la première limite de case par rapport au départ.
    local_times = [axis_dt for axis_dt in (axis._timestamps[i] for i in ticks)]
    gaps = [
        (local_times[i + 1] - local_times[i]).total_seconds() / 60
        for i in range(len(local_times) - 1)
    ]
    assert all(gap >= 90 for gap in gaps)


def test_time_axis_ticks_once_per_calendar_day_over_a_7_day_span(qapp, test_db):
    from ui.main_window.resources_view import _TimeAxis

    axis = _TimeAxis()
    start = datetime(2026, 10, 12, 9, 17)
    axis.set_data(_minutes_span(start, 7 * 24 * 6, 10))   # un point toutes les 10 min, 7 jours

    ticks = axis._tick_indices()
    labels = [axis._label_for(axis._timestamps[i]) for i in ticks]

    assert len(ticks) in (6, 7)   # un par limite de jour traversée
    assert all("h" not in label for label in labels)   # format "jour. N", pas "HH:MM"


def test_resources_view_hover_syncs_time_axis_crosshair(qapp, test_db):
    from ui.main_window.resources_view import ResourcesView

    db.record_resource_sample(cpu_percent=5.0, memory_mb=150.0)
    view = ResourcesView()

    view._on_chart_hover(0)
    assert view._time_axis._crosshair_index == 0

    view._on_chart_hover_left()
    assert view._time_axis._crosshair_index is None


# ── A5 : titre de graphique, valeur survolée vs dernière valeur ────────────

def test_resources_view_chart_title_shows_last_value_and_maintenant_at_rest(qapp, test_db):
    from ui.main_window.resources_view import ResourcesView

    db.record_resource_sample(cpu_percent=12.0, memory_mb=321.0)
    view = ResourcesView()

    assert view._lbl_latest_cpu.text() == "12 %"
    assert view._lbl_latest_cpu_qual.text() == "maintenant"
    assert view._lbl_latest_ram_qual.text() == "maintenant"
    assert view._lbl_latest_count_qual.text() == "maintenant"


def test_resources_view_chart_title_shows_hovered_value_while_hovering(qapp, test_db):
    from ui.main_window.resources_view import ResourcesView

    db.record_resource_sample(cpu_percent=12.0, memory_mb=321.0)
    db.record_resource_sample(cpu_percent=77.0, memory_mb=410.0)
    view = ResourcesView()

    view._on_chart_hover(0)   # premier échantillon, pas le dernier

    assert view._lbl_latest_cpu.text() == "12 %"
    assert view._lbl_latest_cpu_qual.text() == "à l'instant survolé"


def test_resources_view_chart_title_restores_maintenant_after_hover_left(qapp, test_db):
    from ui.main_window.resources_view import ResourcesView

    db.record_resource_sample(cpu_percent=12.0, memory_mb=321.0)
    db.record_resource_sample(cpu_percent=77.0, memory_mb=410.0)
    view = ResourcesView()

    view._on_chart_hover(0)
    view._on_chart_hover_left()

    # Revient à la DERNIÈRE valeur (77 %), pas à celle qui était survolée (12 %).
    assert view._lbl_latest_cpu.text() == "77 %"
    assert view._lbl_latest_cpu_qual.text() == "maintenant"


# ── A6 : ligne pointillée du plafond ────────────────────────────────────────

def test_resources_view_sets_reference_line_from_max_concurrent_runs(qapp, test_db):
    from ui.main_window.resources_view import ResourcesView

    db.record_resource_sample(cpu_percent=5.0, memory_mb=150.0)
    db.update_app_settings(max_concurrent_runs=9)

    view = ResourcesView()
    view.refresh()

    assert view._chart_count._reference_value == 9
    assert view._chart_count._reference_label == "plafond 9"
    # Seul le graphique "pipelines en cours" porte la référence (A6) — jamais CPU/RAM.
    assert view._chart_cpu._reference_value is None
    assert view._chart_ram._reference_value is None


# ── A7 : heure du pic sur la carte Pic CPU ──────────────────────────────────

def test_format_peak_time_shows_aujourdhui_when_peak_is_today():
    from ui.main_window.resources_view import _format_peak_time
    from datetime import date

    peak = datetime(2026, 10, 18, 7, 5)
    assert _format_peak_time(peak, date(2026, 10, 18)) == "aujourd'hui 07:05"


def test_format_peak_time_shows_date_when_peak_is_not_today():
    from ui.main_window.resources_view import _format_peak_time
    from datetime import date

    peak = datetime(2026, 10, 15, 7, 5)
    assert _format_peak_time(peak, date(2026, 10, 18)) == "15/10 07:05"


def test_resources_view_peak_cpu_card_shows_subtitle_at_the_time_of_the_peak(qapp, test_db):
    from ui.main_window.resources_view import ResourcesView
    from database.models import ResourceSample

    now = datetime.utcnow()
    with db.get_session() as s:
        s.add(ResourceSample(timestamp=now - timedelta(minutes=10), cpu_percent=5.0, memory_mb=100.0))
        s.add(ResourceSample(timestamp=now - timedelta(minutes=5), cpu_percent=88.0, memory_mb=100.0))
        s.add(ResourceSample(timestamp=now, cpu_percent=5.0, memory_mb=100.0))

    view = ResourcesView()

    assert view._card_peak_cpu._lbl_value.text() == "88 %"
    assert "aujourd'hui" in view._card_peak_cpu._lbl_sub.text()


# ── A8 : ligne de résumé au survol ──────────────────────────────────────────

def test_resources_view_hover_summary_line_includes_count_cpu_and_memory(qapp, test_db):
    from ui.main_window.resources_view import ResourcesView

    pipeline = db.create_pipeline(name="summary-test-pipeline")
    db.create_run(pipeline.id)   # en cours
    db.record_resource_sample(cpu_percent=73.0, memory_mb=256.0)

    view = ResourcesView()
    view._on_chart_hover(0)

    text = view._correlate_time_lbl.text()
    assert "1 pipeline actif" in text
    assert "CPU 73 %" in text
    assert "mémoire 256 Mo" in text


def test_resources_view_hover_summary_line_shown_even_with_no_active_pipeline(qapp, test_db):
    from ui.main_window.resources_view import ResourcesView

    db.record_resource_sample(cpu_percent=4.0, memory_mb=120.0)
    view = ResourcesView()
    view._on_chart_hover(0)

    text = view._correlate_time_lbl.text()
    assert "0 pipeline actif" in text
    assert "CPU 4 %" in text


# ── A9 : état vide ──────────────────────────────────────────────────────────

def test_resources_view_shows_empty_state_without_any_sample(qapp, test_db):
    from ui.main_window.resources_view import ResourcesView

    view = ResourcesView()

    # isHidden() (pas isVisible()) : la vue n'est jamais .show()-ée dans ce test, isVisible()
    # renverrait False pour tout le monde (ancêtre non affiché), comme déjà pratiqué par les
    # autres tests de ce fichier (_correlate_time_lbl.isHidden() ci-dessus).
    assert not view._empty_state.isHidden()
    assert not view._empty_footer_hint.isHidden()
    assert view._charts_frame.isHidden()
    assert view._correlate_panel.isHidden()
    # Les 4 cartes du haut restent visibles même sans échantillon (Ressources-vide.html).
    assert not view._card_running.isHidden()
    assert not view._card_samples.isHidden()


def test_resources_view_hides_empty_state_once_a_sample_exists(qapp, test_db):
    from ui.main_window.resources_view import ResourcesView

    view = ResourcesView()
    assert not view._empty_state.isHidden()

    db.record_resource_sample(cpu_percent=5.0, memory_mb=150.0)
    view.refresh()

    assert view._empty_state.isHidden()
    assert view._empty_footer_hint.isHidden()
    assert not view._charts_frame.isHidden()
    assert not view._correlate_panel.isHidden()

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

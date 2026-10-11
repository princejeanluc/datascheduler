"""
DataScheduler — tests/test_atelier_sidebar.py
Sidebar de pipelines de l'Atelier Pipelines (chantier Atelier Pipelines, écran 2) — même patron
de test que tests/test_nav_rail_collapse.py (NavRail), dont AtelierSidebar reprend le patron de
repli (largeurs fixes, bascule explicite, signal collapsed_changed sans persistance interne) sans
en être une sous-classe. Composant autonome, sans dépendance à MainWindow/AppSettings — la
persistance (AppSettings.atelier_sidebar_collapsed, voir tests/test_atelier_sidebar_collapse.py)
est câblée par l'appelant (AtelierPipelinesView), pas testée ici.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication
from ui.styles import COLORS

_PIPELINES = [
    {"id": 1, "name": "Export ventes", "status": "SUCCESS", "is_active": True},
    {"id": 2, "name": "Import stock",   "status": "FAILED",  "is_active": True},
    {"id": 3, "name": "Archive legacy", "status": "IDLE",     "is_active": False},
]


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


# ──────────────────────────────────────────────
#  AtelierPipelineRow — le plus élémentaire, sans AtelierSidebar
# ──────────────────────────────────────────────

def test_row_expanded_by_default_shows_name_and_badge(qapp):
    from ui.main_window.atelier_sidebar import AtelierPipelineRow

    # isHidden(), pas isVisible() : ce dernier dépend aussi de la visibilité des ancêtres (donc
    # toujours False tant que la ligne n'a jamais été réellement affichée, voir widgets.py
    # ::_on_toggle_minimap pour la même remarque ailleurs dans ce projet) — isHidden() ne reflète
    # que l'état explicitement demandé sur ce widget-ci.
    row = AtelierPipelineRow(1, "Export ventes", "SUCCESS", True)
    assert row._name_lbl.isHidden() is False
    assert row._badge.isHidden() is False
    assert row._dot.isHidden() is True
    assert row.toolTip() == ""


def test_row_collapsed_shows_dot_only_with_tooltip(qapp):
    from ui.main_window.atelier_sidebar import AtelierPipelineRow

    row = AtelierPipelineRow(1, "Export ventes", "SUCCESS", True)
    row.set_collapsed(True)
    assert row._name_lbl.isHidden() is True
    assert row._badge.isHidden() is True
    assert row._dot.isHidden() is False
    assert row.toolTip() == "Export ventes"


def test_row_inactive_pipeline_shows_idle_badge_regardless_of_status(qapp):
    from ui.main_window.atelier_sidebar import AtelierPipelineRow

    row = AtelierPipelineRow(1, "Archive legacy", "SUCCESS", False)
    assert row._badge.text() == "INACTIF"


def test_row_click_emits_clicked_pipeline(qapp):
    from ui.main_window.atelier_sidebar import AtelierPipelineRow
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    row = AtelierPipelineRow(42, "Export ventes", "SUCCESS", True)
    captured = []
    row.clicked_pipeline.connect(captured.append)

    QTest.mouseClick(row, Qt.LeftButton)

    assert captured == [42]


# ──────────────────────────────────────────────
#  AtelierSidebar — composant autonome
# ──────────────────────────────────────────────

def test_sidebar_starts_expanded_by_default(qapp):
    from ui.main_window.atelier_sidebar import AtelierSidebar, WIDTH

    sidebar = AtelierSidebar()
    assert sidebar.is_collapsed is False
    assert sidebar.width() == WIDTH
    assert sidebar._title_lbl.isHidden() is False
    assert "Réduire" in sidebar._toggle_btn.text()
    assert sidebar._toggle_btn.toolTip() == ""


def test_sidebar_can_start_collapsed(qapp):
    from ui.main_window.atelier_sidebar import AtelierSidebar, WIDTH_COLLAPSED

    sidebar = AtelierSidebar(initial_collapsed=True)
    assert sidebar.is_collapsed is True
    assert sidebar.width() == WIDTH_COLLAPSED
    assert sidebar._title_lbl.isHidden() is True


def test_toggle_collapsed_updates_everything(qapp):
    from ui.main_window.atelier_sidebar import AtelierSidebar, WIDTH_COLLAPSED

    sidebar = AtelierSidebar()
    sidebar.set_pipelines(_PIPELINES)
    sidebar.toggle_collapsed()

    assert sidebar.is_collapsed is True
    assert sidebar.width() == WIDTH_COLLAPSED
    assert sidebar._title_lbl.isHidden() is True
    for row in sidebar._rows:
        assert row._name_lbl.isHidden() is True
        assert row.toolTip()   # jamais un jeu de mémoire icône-seule
    assert sidebar._toggle_btn.text() == ""
    assert "Agrandir" in sidebar._toggle_btn.toolTip()


def test_toggle_twice_returns_to_expanded(qapp):
    from ui.main_window.atelier_sidebar import AtelierSidebar, WIDTH

    sidebar = AtelierSidebar()
    sidebar.toggle_collapsed()
    sidebar.toggle_collapsed()

    assert sidebar.is_collapsed is False
    assert sidebar.width() == WIDTH


def test_toggle_emits_collapsed_changed_signal(qapp):
    from ui.main_window.atelier_sidebar import AtelierSidebar

    sidebar = AtelierSidebar()
    captured = []
    sidebar.collapsed_changed.connect(captured.append)

    sidebar.toggle_collapsed()
    assert captured == [True]
    sidebar.toggle_collapsed()
    assert captured == [True, False]


def test_set_pipelines_replaces_rows_and_respects_current_collapsed_state(qapp):
    from ui.main_window.atelier_sidebar import AtelierSidebar

    sidebar = AtelierSidebar(initial_collapsed=True)
    sidebar.set_pipelines(_PIPELINES)

    assert len(sidebar._rows) == 3
    assert all(row._name_lbl.isHidden() is True for row in sidebar._rows)

    sidebar.set_pipelines(_PIPELINES[:1])
    assert len(sidebar._rows) == 1


def test_select_pipeline_marks_only_that_row_active(qapp):
    from ui.main_window.atelier_sidebar import AtelierSidebar

    sidebar = AtelierSidebar()
    sidebar.set_pipelines(_PIPELINES)
    sidebar.select_pipeline(2)

    # set_active() ne stocke pas d'état lisible publiquement — on vérifie indirectement via le
    # style appliqué (border gauche accentuée uniquement sur la ligne sélectionnée).
    accent = COLORS["accent"]
    styles = {row.pipeline_id: row.styleSheet() for row in sidebar._rows}
    assert accent in styles[2]
    assert accent not in styles[1]
    assert accent not in styles[3]


def test_clicking_a_row_emits_pipeline_selected(qapp):
    from ui.main_window.atelier_sidebar import AtelierSidebar

    sidebar = AtelierSidebar()
    sidebar.set_pipelines(_PIPELINES)
    captured = []
    sidebar.pipeline_selected.connect(captured.append)

    sidebar._rows[1].clicked_pipeline.emit(sidebar._rows[1].pipeline_id)
    assert captured == [2]

"""
DataScheduler — tests/test_step_insertion.py
C7 (Atelier-ajout) : ouverture/fermeture du panneau "Ajouter" côté PipelineGraphEditorWidget,
synchronisation avec l'aperçu, et les trois façons d'insérer une étape — greffée sur une arête
sélectionnée, après un nœud sélectionné, ou flottante (bouton/Entrée et glisser-déposer). Le
dialogue de compatibilité (PipelineGraphEditorDialog) garde son flux modal inchangé — vérifié ici
pour ne jamais régresser silencieusement si _on_add_step était retouché plus tard.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QPointF
from PySide6.QtWidgets import QApplication, QDialog

from database import db_manager as db
from ui.graph_editor import PipelineGraphEditorDialog, PipelineGraphEditorWidget
from ui.graph_editor.step_library_panel import StepLibraryPanel
from ui.graph_editor.step_preview_panel import StepPreviewPanel


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


class _FakeConfigDialog:
    """Remplace _open_config_dialog — jamais une vraie modale bloquante dans ces tests."""

    def __init__(self, step_key: str, step_type: str, accepted: bool = True):
        self._step_key = step_key
        self._step_type = step_type
        self._accepted = accepted

    def exec(self):
        return self._accepted

    def result_step(self):
        return {"step_type": self._step_type, "config": {"_step_key": self._step_key}, "label": ""}


def _patch_config_dialog(monkeypatch, dlg):
    import ui.step_editor as step_editor_mod
    monkeypatch.setattr(step_editor_mod, "_open_config_dialog", lambda *a, **k: dlg)


def _linear_pipeline():
    p = db.create_pipeline(name="c7-insertion-test")
    db.save_pipeline_graph(p.id, steps=[
        {"step_type": "DB_EXTRACT", "label": "A", "config": {"_step_key": "a"}},
        {"step_type": "LOCAL_COPY", "label": "B", "config": {"_step_key": "b"}},
    ], edges=[{"from_step_key": "a", "from_port": "output_file", "to_step_key": "b"}])
    return p


# ── Ouverture / fermeture / synchronisation avec l'aperçu ──────────────────

def test_open_step_library_creates_the_panels_only_once(qapp, test_db):
    p = db.create_pipeline(name="c7-open-once")
    widget = PipelineGraphEditorWidget(pipeline=p, show_settings_shortcut_button=False)

    widget.open_step_library()
    panel, preview = widget._library_panel, widget.preview_panel

    widget.close_step_library()
    widget.open_step_library()

    assert widget._library_panel is panel   # pas recréé à chaque ouverture
    assert widget.preview_panel is preview


def test_open_step_library_emits_step_library_toggled_true(qapp, test_db):
    p = db.create_pipeline(name="c7-toggle-true")
    widget = PipelineGraphEditorWidget(pipeline=p, show_settings_shortcut_button=False)
    received = []
    widget.step_library_toggled.connect(received.append)

    widget.open_step_library()

    assert received == [True]


def test_close_step_library_emits_step_library_toggled_false_and_hides_panel(qapp, test_db):
    p = db.create_pipeline(name="c7-toggle-false")
    widget = PipelineGraphEditorWidget(pipeline=p, show_settings_shortcut_button=False)
    widget.open_step_library()
    received = []
    widget.step_library_toggled.connect(received.append)

    widget.close_step_library()

    assert received == [False]
    assert widget._library_panel.isHidden()


def test_selecting_a_card_updates_the_preview_panel(qapp, test_db):
    p = db.create_pipeline(name="c7-preview-sync")
    widget = PipelineGraphEditorWidget(pipeline=p, show_settings_shortcut_button=False)
    widget.open_step_library()

    widget._library_panel._select("LOCAL_COPY", {})

    assert widget.preview_panel._step_type == "LOCAL_COPY"


def test_legacy_compat_dialog_never_builds_a_library_panel(qapp, test_db, monkeypatch):
    """Le dialogue de compatibilité garde StepTypeChooserDialog — jamais le nouveau panneau."""
    p = db.create_pipeline(name="c7-legacy-untouched")
    dlg = PipelineGraphEditorDialog(None, pipeline=p)

    opened = []

    class _FakeChooser:
        def exec(self):
            opened.append(True)
            return QDialog.Rejected

    import ui.graph_editor.graph_editor_widget as module
    monkeypatch.setattr(module, "StepTypeChooserDialog", lambda *a, **k: _FakeChooser())

    dlg._on_add_step()

    assert opened == [True]
    assert dlg._editor._library_panel is None


# ── Insertion : greffe sur arête sélectionnée ───────────────────────────────

def test_insertion_with_a_selected_edge_splices_the_new_node_in(qapp, test_db, monkeypatch):
    p = _linear_pipeline()
    widget = PipelineGraphEditorWidget(pipeline=p, show_settings_shortcut_button=False)
    _patch_config_dialog(monkeypatch, _FakeConfigDialog("spliced", "COMPRESS"))

    edge = widget._scene.edges[0]
    edge.setSelected(True)
    widget.open_step_library()
    widget._library_panel._select("COMPRESS", {})
    widget._on_library_insert_requested()

    edges = {(e.from_node.step_key, e.from_port, e.to_node.step_key) for e in widget._scene.edges}
    assert "spliced" in widget._scene.nodes
    assert ("a", "output_file", "spliced") in edges
    assert ("spliced", "output_file", "b") in edges
    assert len(widget._scene.edges) == 2   # l'ancienne arête a-b a disparu, pas juste ajoutée


def test_insertion_closes_the_library_panel_on_success(qapp, test_db, monkeypatch):
    p = _linear_pipeline()
    widget = PipelineGraphEditorWidget(pipeline=p, show_settings_shortcut_button=False)
    _patch_config_dialog(monkeypatch, _FakeConfigDialog("x1", "COMPRESS"))

    widget.open_step_library()
    widget._library_panel._select("COMPRESS", {})
    widget._on_library_insert_requested()

    assert widget._library_panel.isHidden()


def test_insertion_cancelled_in_the_config_dialog_inserts_nothing_and_keeps_panel_open(qapp, test_db, monkeypatch):
    p = _linear_pipeline()
    widget = PipelineGraphEditorWidget(pipeline=p, show_settings_shortcut_button=False)
    _patch_config_dialog(monkeypatch, _FakeConfigDialog("never", "COMPRESS", accepted=False))

    widget.open_step_library()
    widget._library_panel._select("COMPRESS", {})
    widget._on_library_insert_requested()

    assert "never" not in widget._scene.nodes
    assert not widget._library_panel.isHidden()


# ── Insertion : après un nœud sélectionné (pas d'arête) ─────────────────────

def test_insertion_with_a_selected_node_and_no_edge_wires_after_it(qapp, test_db, monkeypatch):
    p = _linear_pipeline()
    widget = PipelineGraphEditorWidget(pipeline=p, show_settings_shortcut_button=False)
    _patch_config_dialog(monkeypatch, _FakeConfigDialog("after1", "COMPRESS"))

    widget._scene.nodes["b"].setSelected(True)
    widget.open_step_library()
    widget._library_panel._select("COMPRESS", {})
    widget._on_library_insert_requested()

    edges = {(e.from_node.step_key, e.from_port, e.to_node.step_key) for e in widget._scene.edges}
    assert ("b", "output_file", "after1") in edges
    # L'arête a-b d'origine n'est jamais touchée par ce chemin.
    assert ("a", "output_file", "b") in edges


# ── Insertion : flottante (rien de sélectionné) ─────────────────────────────

def test_insertion_with_nothing_selected_adds_a_floating_unconnected_node(qapp, test_db, monkeypatch):
    p = _linear_pipeline()
    widget = PipelineGraphEditorWidget(pipeline=p, show_settings_shortcut_button=False)
    _patch_config_dialog(monkeypatch, _FakeConfigDialog("floating1", "COMPRESS"))

    widget.open_step_library()
    widget._library_panel._select("COMPRESS", {})
    widget._on_library_insert_requested()

    assert "floating1" in widget._scene.nodes
    assert not any(e.from_node.step_key == "floating1" or e.to_node.step_key == "floating1"
                   for e in widget._scene.edges)


def test_insertion_with_multiple_items_selected_falls_back_to_floating(qapp, test_db, monkeypatch):
    """Ambiguïté (plusieurs éléments sélectionnés à la fois) : repli sur le comportement le plus
    sûr, jamais un choix arbitraire parmi plusieurs cibles possibles."""
    p = _linear_pipeline()
    widget = PipelineGraphEditorWidget(pipeline=p, show_settings_shortcut_button=False)
    _patch_config_dialog(monkeypatch, _FakeConfigDialog("ambiguous1", "COMPRESS"))

    widget._scene.nodes["a"].setSelected(True)
    widget._scene.nodes["b"].setSelected(True)
    widget.open_step_library()
    widget._library_panel._select("COMPRESS", {})
    widget._on_library_insert_requested()

    assert "ambiguous1" in widget._scene.nodes
    assert not any(e.to_node.step_key == "ambiguous1" for e in widget._scene.edges)


def test_enter_in_the_search_box_inserts_the_selected_type(qapp, test_db, monkeypatch):
    p = _linear_pipeline()
    widget = PipelineGraphEditorWidget(pipeline=p, show_settings_shortcut_button=False)
    _patch_config_dialog(monkeypatch, _FakeConfigDialog("enter1", "COMPRESS"))

    widget.open_step_library()
    widget._library_panel._select("COMPRESS", {})
    widget._library_panel.inp_search.returnPressed.emit()

    assert "enter1" in widget._scene.nodes


# ── Glisser-déposer ──────────────────────────────────────────────────────

def test_handle_library_drop_on_empty_canvas_adds_a_node_at_the_drop_position(qapp, test_db, monkeypatch):
    p = _linear_pipeline()
    widget = PipelineGraphEditorWidget(pipeline=p, show_settings_shortcut_button=False)
    _patch_config_dialog(monkeypatch, _FakeConfigDialog("dropped1", "COMPRESS"))

    widget.open_step_library()
    widget.handle_library_drop("COMPRESS", {}, QPointF(400, 250), None)

    assert widget._scene.nodes["dropped1"].pos() == QPointF(400, 250)


def test_handle_library_drop_on_an_edge_splices_like_the_button_path(qapp, test_db, monkeypatch):
    p = _linear_pipeline()
    widget = PipelineGraphEditorWidget(pipeline=p, show_settings_shortcut_button=False)
    _patch_config_dialog(monkeypatch, _FakeConfigDialog("dropped2", "COMPRESS"))

    widget.open_step_library()
    edge = widget._scene.edges[0]
    widget.handle_library_drop("COMPRESS", {}, QPointF(0, 0), edge)

    edges = {(e.from_node.step_key, e.from_port, e.to_node.step_key) for e in widget._scene.edges}
    assert ("a", "output_file", "dropped2") in edges
    assert ("dropped2", "output_file", "b") in edges


# ── Point de greffe : résolution pure ────────────────────────────────────

def test_resolve_insertion_target_prefers_a_selected_edge_over_a_selected_node(qapp, test_db):
    p = _linear_pipeline()
    widget = PipelineGraphEditorWidget(pipeline=p, show_settings_shortcut_button=False)
    widget._scene.edges[0].setSelected(True)
    widget._scene.nodes["a"].setSelected(True)

    kind, ref = widget._resolve_insertion_target()

    assert kind == "splice"
    assert ref is widget._scene.edges[0]

"""
DataScheduler — tests/test_graph_editor_dialog.py
Fumée : PipelineGraphEditorDialog s'ouvre sans erreur (offscreen Qt, même réflexe que
tests/test_export_dialog.py et tests/test_step_editor_dialogs.py), charge correctement un
graphe déjà enregistré, et le round-trip charger/modifier/enregistrer préserve steps et edges.
Pas de simulation de drag souris réelle (hors de portée raisonnable d'un test automatisé) —
les interactions scene.add_node()/add_edge()/remove_node() sont exercées directement, ce sont
elles que le drag-to-connect appelle en interne (voir ui/graph_editor/graph_scene.py).
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
import pytest

from database import db_manager as db
from ui.graph_editor import PipelineGraphEditorDialog
from ui.graph_editor.node_item import StepNodeItem
from ui.graph_editor.edge_item import EdgeItem


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


# ──────────────────────────────────────────────
#  Rendu des ports (chantier port d'erreur générique) — fonction pure, pas besoin de qapp
# ──────────────────────────────────────────────

def test_port_visual_true_false_and_error_have_distinct_colors():
    from ui.graph_editor.node_item import _port_visual
    true_color, true_label   = _port_visual("true")
    false_color, false_label = _port_visual("false")
    error_color, error_label = _port_visual("error")
    assert len({true_color, false_color, error_color}) == 3
    assert (true_label, false_label, error_label) == ("V", "F", "!")


def test_port_visual_unknown_port_falls_back_to_neutral_no_label():
    from ui.graph_editor.node_item import _port_visual
    color, label = _port_visual("output_file")
    assert label == ""
    assert color == "text_dim"


# ──────────────────────────────────────────────
#  Fond de carte teinté par type (chantier identité visuelle) — fonction pure, pas besoin de qapp
# ──────────────────────────────────────────────

def test_tinted_bg_zero_ratio_returns_base_unchanged(qapp):
    from ui.graph_editor.node_item import _tinted_bg
    from PySide6.QtGui import QColor
    base = QColor(36, 34, 32)
    accent = QColor(255, 121, 0)
    result = _tinted_bg(base, accent, ratio=0.0)
    assert (result.red(), result.green(), result.blue()) == (36, 34, 32)


def test_tinted_bg_full_ratio_returns_accent_unchanged(qapp):
    from ui.graph_editor.node_item import _tinted_bg
    from PySide6.QtGui import QColor
    base = QColor(36, 34, 32)
    accent = QColor(255, 121, 0)
    result = _tinted_bg(base, accent, ratio=1.0)
    assert (result.red(), result.green(), result.blue()) == (255, 121, 0)


def test_tinted_bg_interpolates_between_base_and_accent(qapp):
    from ui.graph_editor.node_item import _tinted_bg
    from PySide6.QtGui import QColor
    base = QColor(0, 0, 0)
    accent = QColor(200, 100, 50)
    result = _tinted_bg(base, accent, ratio=0.5)
    assert (result.red(), result.green(), result.blue()) == (100, 50, 25)


def test_tinted_bg_clamps_out_of_range_ratio(qapp):
    from ui.graph_editor.node_item import _tinted_bg
    from PySide6.QtGui import QColor
    base = QColor(10, 10, 10)
    accent = QColor(200, 200, 200)
    assert (_tinted_bg(base, accent, ratio=-5).red(),) == (10,)
    assert (_tinted_bg(base, accent, ratio=5).red(),) == (200,)


# ──────────────────────────────────────────────
#  Nœuds de routage en losange (chantier UX éditeur, Lot 1)
# ──────────────────────────────────────────────

def test_diamond_port_local_pos_single_port_is_the_right_vertex():
    from ui.graph_editor.node_item import _diamond_port_local_pos
    assert _diamond_port_local_pos(200, 64, 0, 1) == (200, 32)


def test_diamond_port_local_pos_three_ports_are_distinct_and_symmetric():
    from ui.graph_editor.node_item import _diamond_port_local_pos
    positions = [_diamond_port_local_pos(200, 64, i, 3) for i in range(3)]
    # 3 points distincts — sinon 2 ports se superposeraient et seraient impossibles à cliquer
    # individuellement (le vrai bug qu'aurait causé une répartition verticale sur x=WIDTH).
    assert len(set(positions)) == 3
    top, mid, bottom = positions
    # Le port du milieu tombe exactement sur le sommet droit du losange.
    assert mid == (200, 32)
    # Symétrie verticale autour du sommet droit (même x, y équidistants de 32).
    assert top[0] == bottom[0]
    assert abs(top[1] - 32) == abs(bottom[1] - 32)
    # Les deux ports obliques sont bien à l'intérieur du losange (x < WIDTH), pas sur le bord
    # droit du rectangle englobant — c'est ce qui les distingue géométriquement d'un nœud normal.
    assert top[0] < 200 and bottom[0] < 200


def test_diamond_port_local_pos_matches_rectangle_symmetry_convention():
    """Même formule step*(idx+1) que l'ancienne répartition verticale (voir node_item.py) —
    juste appliquée à une coordonnée curviligne plutôt qu'à une ligne droite : les positions
    doivent rester symétriques autour du centre, comme avant pour un nœud rectangulaire."""
    from ui.graph_editor.node_item import _diamond_port_local_pos
    a = _diamond_port_local_pos(200, 64, 0, 2)
    b = _diamond_port_local_pos(200, 64, 1, 2)
    assert a[1] < 32 < b[1]
    assert abs(a[1] - 32) == pytest.approx(abs(b[1] - 32))


# ──────────────────────────────────────────────
#  Port d'erreur toujours au bord/sommet bas (chantier placement du port d'erreur)
# ──────────────────────────────────────────────

def test_error_port_local_pos_is_bottom_center_for_any_shape():
    from ui.graph_editor.node_item import _error_port_local_pos
    assert _error_port_local_pos(200, 64) == (100, 64)


def test_gateway_parallel_output_and_error_ports_are_well_separated():
    """Non-régression directe du bug constaté par capture d'écran : avec seulement 2 ports
    (output_file + error, le cas de GATEWAY_PARALLEL/GATEWAY_JOIN), l'ancienne répartition
    générique les faisait atterrir tous les deux à quelques pixels du sommet droit du losange.
    Désormais "error" est toujours à part (bord bas) — "output_file" redevient seul occupant du
    sommet droit, sans compétition."""
    node = StepNodeItem({"step_type": "GATEWAY_PARALLEL", "config": {"_step_key": "gw"}})
    assert node.output_ports == ("output_file", "error")

    out_pos = node.output_port_pos("output_file")
    err_pos = node.output_port_pos("error")

    assert out_pos.x() == node.pos().x() + node.WIDTH   # sommet droit, seul occupant
    assert out_pos.y() == node.pos().y() + node.HEIGHT / 2
    assert err_pos.x() == node.pos().x() + node.WIDTH / 2   # sommet bas
    assert err_pos.y() == node.pos().y() + node.HEIGHT
    # Nettement séparés, plus de clustering près du sommet droit.
    assert abs(out_pos.x() - err_pos.x()) > 50


def test_condition_node_output_ports_use_diamond_geometry_not_vertical_line():
    """Les 3 ports de sortie d'un nœud CONDITION (true/false/error) doivent être répartis sur
    le losange, pas alignés verticalement sur x=WIDTH comme un nœud rectangulaire — sinon ils se
    superposeraient (voir test_diamond_port_local_pos_three_ports_are_distinct_and_symmetric)."""
    node = StepNodeItem({"step_type": "CONDITION", "config": {"_step_key": "cond"}})
    assert node.is_routing_node is True

    positions = {port: node.output_port_pos(port) for port in node.output_ports}
    assert len({(p.x(), p.y()) for p in positions.values()}) == 3
    # "error" est toujours à part, au sommet BAS (chantier placement du port d'erreur) — jamais
    # mêlé à la répartition de true/false, qui reste sur le losange proprement dit.
    assert positions["error"].x() == node.pos().x() + node.WIDTH / 2
    assert positions["error"].y() == node.pos().y() + node.HEIGHT
    # true/false (2 ports normaux) restent répartis sur le losange, ni l'un ni l'autre au
    # sommet droit exact désormais qu'ils ne sont plus que 2 (voir _diamond_port_local_pos).
    assert positions["true"].x() < node.pos().x() + node.WIDTH
    assert positions["false"].x() < node.pos().x() + node.WIDTH


def test_gateway_parallel_node_is_a_routing_node_diamond():
    """Chantier Gateway — GATEWAY_PARALLEL hérite du rendu en losange générique (Lot 1) sans
    aucun changement dans node_item.py, juste IS_ROUTING_NODE=True sur la classe du step."""
    node = StepNodeItem({"step_type": "GATEWAY_PARALLEL", "config": {"_step_key": "gw"}})
    assert node.is_routing_node is True


def test_gateway_join_node_is_a_routing_node_diamond():
    node = StepNodeItem({"step_type": "GATEWAY_JOIN", "config": {"_step_key": "join"}})
    assert node.is_routing_node is True


# ──────────────────────────────────────────────
#  Glyphes centraux façon BPMN (chantier identité visuelle) — fonction pure, pas besoin de qapp
# ──────────────────────────────────────────────

def test_gateway_glyph_condition_is_cross():
    from ui.graph_editor.node_item import _gateway_glyph
    assert _gateway_glyph("CONDITION", {}) == "cross"


def test_gateway_glyph_parallel_is_plus():
    from ui.graph_editor.node_item import _gateway_glyph
    assert _gateway_glyph("GATEWAY_PARALLEL", {}) == "plus"


def test_gateway_glyph_join_and_mode_is_plus():
    from ui.graph_editor.node_item import _gateway_glyph
    assert _gateway_glyph("GATEWAY_JOIN", {"join_mode": "AND"}) == "plus"


def test_gateway_glyph_join_or_mode_or_default_is_circle():
    from ui.graph_editor.node_item import _gateway_glyph
    assert _gateway_glyph("GATEWAY_JOIN", {"join_mode": "OR"}) == "circle"
    assert _gateway_glyph("GATEWAY_JOIN", {}) == "circle"


def test_gateway_glyph_non_routing_type_is_none():
    from ui.graph_editor.node_item import _gateway_glyph
    assert _gateway_glyph("DB_EXTRACT", {}) is None


# ──────────────────────────────────────────────
#  Marge basse (chantier identité visuelle) — plus haute pour un losange (légende + glyphe
#  remplaçant le texte à l'intérieur) qu'un rectangle (texte inchangé, resté à l'intérieur).
# ──────────────────────────────────────────────

def test_routing_node_bounding_rect_taller_than_regular_node():
    routing_node = StepNodeItem({"step_type": "CONDITION", "config": {"_step_key": "cond"}})
    regular_node = StepNodeItem({"step_type": "DB_EXTRACT", "config": {"_step_key": "a"}})
    assert routing_node.boundingRect().height() > regular_node.boundingRect().height()


@pytest.mark.parametrize("step_type,config", [
    ("CONDITION", {"expression": "rows_count > 0"}),
    ("GATEWAY_PARALLEL", {}),
    ("GATEWAY_JOIN", {"join_mode": "AND"}),
    ("GATEWAY_JOIN", {"join_mode": "OR"}),
])
def test_routing_node_paint_does_not_crash(qapp, step_type, config):
    """Fumée — un vrai repaint (QPixmap/QPainter), pas juste un appel direct à paint() avec un
    contexte incomplet, même réflexe que les autres widgets de ce chantier (mini-carte, fond
    quadrillé)."""
    from PySide6.QtGui import QPixmap, QPainter as RealQPainter

    node = StepNodeItem({"step_type": step_type, "label": "légende",
                          "config": {"_step_key": "n", **config}})
    rect = node.boundingRect()
    pixmap = QPixmap(int(rect.width()) + 20, int(rect.height()) + 20)
    painter = RealQPainter(pixmap)
    try:
        painter.translate(-rect.left(), -rect.top())
        node.paint(painter, None, None)
    finally:
        painter.end()


def test_regular_step_output_ports_unaffected_by_diamond_change():
    """Non-régression : le port normal d'un nœud rectangulaire garde exactement la répartition
    verticale d'avant, sur la ligne x=WIDTH — seul "error" est désormais à part (bord bas)."""
    node = StepNodeItem({"step_type": "DB_EXTRACT", "config": {"_step_key": "a"}})
    assert node.is_routing_node is False

    assert node.output_port_pos("output_file").x() == node.pos().x() + node.WIDTH
    assert node.output_port_pos("error").x() == node.pos().x() + node.WIDTH / 2
    assert node.output_port_pos("error").y() == node.pos().y() + node.HEIGHT


def test_edge_item_arrow_points_toward_the_target_node(qapp):
    """Flèche de direction (chantier identité, vague 1, idée 14a) — la pointe recule juste avant
    le port d'entrée sans le chevaucher, et le triangle pointe vers +x (la tangente en fin de
    tracé est toujours horizontale par construction de update_path())."""
    from_node = StepNodeItem({"step_type": "DB_EXTRACT", "config": {"_step_key": "a"}})
    to_node = StepNodeItem({"step_type": "LOCAL_COPY", "config": {"_step_key": "b"}})
    to_node.setPos(400, 0)
    edge = EdgeItem(from_node, "output_file", to_node)

    tip, base1, base2 = edge._arrow_points()
    input_x = to_node.input_port_pos().x()

    assert tip.x() < input_x
    assert base1.x() < tip.x() and base2.x() < tip.x()
    assert base1.y() < tip.y() < base2.y() or base2.y() < tip.y() < base1.y()


def test_dialog_opens_on_empty_pipeline(qapp, test_db):
    pipeline = db.create_pipeline(name="empty")
    dlg = PipelineGraphEditorDialog(None, pipeline=pipeline)
    assert dlg.windowTitle()
    assert dlg._scene.nodes == {}
    assert dlg._scene.edges == []


def test_dialog_loads_existing_graph(qapp, test_db):
    pipeline = db.create_pipeline(name="loaded-graph")
    db.save_pipeline_graph(pipeline.id, steps=[
        {"step_type": "DB_EXTRACT", "config": {"_step_key": "a"}},
        {"step_type": "CONDITION", "config": {"_step_key": "b", "expression": "rows_count > 0"}},
        {"step_type": "LOCAL_COPY", "config": {"_step_key": "c"}},
        {"step_type": "FTP_UPLOAD", "config": {"_step_key": "d"}},
    ], edges=[
        {"from_step_key": "a", "from_port": "output_file", "to_step_key": "b", "to_port": "input"},
        {"from_step_key": "b", "from_port": "true", "to_step_key": "c", "to_port": "input"},
        {"from_step_key": "b", "from_port": "false", "to_step_key": "d", "to_port": "input"},
    ])

    dlg = PipelineGraphEditorDialog(None, pipeline=pipeline)

    assert set(dlg._scene.nodes.keys()) == {"a", "b", "c", "d"}
    assert len(dlg._scene.edges) == 3
    for node in dlg._scene.nodes.values():
        assert isinstance(node, StepNodeItem)
    for edge in dlg._scene.edges:
        assert isinstance(edge, EdgeItem)

    condition_node = dlg._scene.nodes["b"]
    assert condition_node.output_ports == ("true", "false", "error")


def test_add_node_cascades_position_and_saves(qapp, test_db):
    pipeline = db.create_pipeline(name="add-node-test")
    dlg = PipelineGraphEditorDialog(None, pipeline=pipeline)

    node1 = dlg._scene.add_node(
        {"step_type": "DB_EXTRACT", "config": {"_step_key": "x"}}, dlg._next_new_node_pos()
    )
    pos2 = dlg._next_new_node_pos()
    node2 = dlg._scene.add_node(
        {"step_type": "LOCAL_COPY", "config": {"_step_key": "y"}}, pos2
    )
    assert pos2.x() > node1.pos().x()

    edge = dlg._scene.add_edge("x", "output_file", "y")
    assert edge is not None

    dlg._on_save()

    saved_steps = db.get_steps(pipeline.id)
    saved_edges = db.get_edges(pipeline.id)
    assert len(saved_steps) == 2
    assert len(saved_edges) == 1
    assert {s.pos_x for s in saved_steps} == {int(node1.pos().x()), int(node2.pos().x())}


def test_editing_node_updates_step_dict(qapp, test_db):
    pipeline = db.create_pipeline(name="edit-node-test")
    db.save_pipeline_graph(pipeline.id, steps=[
        {"step_type": "DB_EXTRACT", "config": {"_step_key": "a"}},
    ], edges=[])

    dlg = PipelineGraphEditorDialog(None, pipeline=pipeline)
    node = dlg._scene.nodes["a"]

    # Simule ce que _on_node_double_clicked ferait après confirmation du dialogue de config
    # (sans passer par le vrai double-clic souris) — même config, mais avec un libellé.
    node.step = {**node.step, "label": "Ma source"}
    node.update()

    dlg._on_save()
    reloaded = db.get_steps(pipeline.id)
    assert reloaded[0].label == "Ma source"


def test_remove_node_removes_connected_edges_before_save(qapp, test_db):
    pipeline = db.create_pipeline(name="remove-node-test")
    db.save_pipeline_graph(pipeline.id, steps=[
        {"step_type": "DB_EXTRACT", "config": {"_step_key": "a"}},
        {"step_type": "LOCAL_COPY", "config": {"_step_key": "b"}},
    ], edges=[
        {"from_step_key": "a", "from_port": "output_file", "to_step_key": "b", "to_port": "input"},
    ])

    dlg = PipelineGraphEditorDialog(None, pipeline=pipeline)
    assert len(dlg._scene.edges) == 1

    dlg._scene.remove_node(dlg._scene.nodes["b"])
    assert len(dlg._scene.edges) == 0
    assert "b" not in dlg._scene.nodes

    dlg._on_save()
    assert len(db.get_steps(pipeline.id)) == 1
    assert len(db.get_edges(pipeline.id)) == 0


# ──────────────────────────────────────────────
#  Surlignage "échec" post-mortem (chantier UX éditeur, Lot 1, B1)
# ──────────────────────────────────────────────

def test_highlight_step_key_marks_node_and_incoming_edge_as_failed(qapp, test_db):
    pipeline = db.create_pipeline(name="highlight-failed-test")
    db.save_pipeline_graph(pipeline.id, steps=[
        {"step_type": "DB_EXTRACT", "config": {"_step_key": "a"}},
        {"step_type": "LOCAL_COPY", "config": {"_step_key": "b"}},
    ], edges=[
        {"from_step_key": "a", "from_port": "output_file", "to_step_key": "b", "to_port": "input"},
    ])

    dlg = PipelineGraphEditorDialog(None, pipeline=pipeline, highlight_step_key="b")

    assert dlg._scene.nodes["b"]._is_failed
    assert not dlg._scene.nodes["a"]._is_failed
    edge_ab = next(e for e in dlg._scene.edges if e.to_node is dlg._scene.nodes["b"])
    assert edge_ab._is_failed


def test_highlight_step_key_skips_the_live_polling_timer(qapp, test_db):
    """get_running_step_keys_multi()/get_running_step_keys() ne trouvent structurellement
    jamais un run FAILED (filtrés sur RUNNING) — lancer le sondage serait du travail perdu."""
    pipeline = db.create_pipeline(name="highlight-no-timer-test")
    db.save_pipeline_graph(pipeline.id, steps=[
        {"step_type": "DB_EXTRACT", "config": {"_step_key": "a"}},
    ], edges=[])

    dlg = PipelineGraphEditorDialog(None, pipeline=pipeline, highlight_step_key="a")

    assert not hasattr(dlg, "_executing_timer")


def test_highlight_step_key_unknown_key_is_a_no_op(qapp, test_db):
    """Le nœud fautif a pu être supprimé du graphe depuis — ne doit pas planter."""
    pipeline = db.create_pipeline(name="highlight-unknown-test")
    db.save_pipeline_graph(pipeline.id, steps=[
        {"step_type": "DB_EXTRACT", "config": {"_step_key": "a"}},
    ], edges=[])

    dlg = PipelineGraphEditorDialog(None, pipeline=pipeline, highlight_step_key="does-not-exist")

    assert not dlg._scene.nodes["a"]._is_failed


def test_without_highlight_step_key_the_live_timer_still_starts(qapp, test_db):
    """Non-régression : le comportement par défaut (aucun highlight_step_key) garde le sondage
    live existant, inchangé."""
    pipeline = db.create_pipeline(name="no-highlight-default-timer-test")
    db.save_pipeline_graph(pipeline.id, steps=[
        {"step_type": "DB_EXTRACT", "config": {"_step_key": "a"}},
    ], edges=[])

    dlg = PipelineGraphEditorDialog(None, pipeline=pipeline)

    assert hasattr(dlg, "_executing_timer")
    assert dlg._executing_timer.isActive()


def test_set_executing_step_keys_highlights_node_and_incoming_edges(qapp, test_db):
    """Traçage lumineux (chantier identité, vague 4, idée 14b) : surligne le nœud en cours
    d'exécution + ses arêtes entrantes, retire le surlignage précédent au changement d'étape."""
    pipeline = db.create_pipeline(name="trace-glow-test")
    db.save_pipeline_graph(pipeline.id, steps=[
        {"step_type": "DB_EXTRACT", "config": {"_step_key": "a"}},
        {"step_type": "LOCAL_COPY", "config": {"_step_key": "b"}},
        {"step_type": "FTP_UPLOAD", "config": {"_step_key": "c"}},
    ], edges=[
        {"from_step_key": "a", "from_port": "output_file", "to_step_key": "b", "to_port": "input"},
        {"from_step_key": "b", "from_port": "output_file", "to_step_key": "c", "to_port": "input"},
    ])
    dlg = PipelineGraphEditorDialog(None, pipeline=pipeline)
    scene = dlg._scene
    edge_ab = next(e for e in scene.edges if e.from_node is scene.nodes["a"])
    edge_bc = next(e for e in scene.edges if e.from_node is scene.nodes["b"])

    scene.set_executing_step_keys({"b"})
    assert scene.nodes["b"]._is_executing
    assert not scene.nodes["a"]._is_executing
    assert edge_ab._is_executing    # entrante vers b
    assert not edge_bc._is_executing   # sortante de b, pas entrante

    scene.set_executing_step_keys({"c"})
    assert not scene.nodes["b"]._is_executing
    assert not edge_ab._is_executing
    assert scene.nodes["c"]._is_executing
    assert edge_bc._is_executing

    scene.set_executing_step_keys(None)   # run terminé — plus rien surligné
    assert not scene.nodes["c"]._is_executing
    assert not edge_bc._is_executing


def test_set_executing_step_keys_highlights_multiple_nodes_at_once(qapp, test_db):
    """Chantier parallélisme intra-pipeline : deux branches indépendantes actives en même
    temps doivent toutes les deux se surligner — pas seulement la dernière."""
    pipeline = db.create_pipeline(name="trace-glow-multi-test")
    db.save_pipeline_graph(pipeline.id, steps=[
        {"step_type": "DB_EXTRACT", "config": {"_step_key": "a"}},
        {"step_type": "LOCAL_COPY", "config": {"_step_key": "b"}},
        {"step_type": "FTP_UPLOAD", "config": {"_step_key": "c"}},
    ], edges=[
        {"from_step_key": "a", "from_port": "output_file", "to_step_key": "b", "to_port": "input"},
        {"from_step_key": "a", "from_port": "output_file", "to_step_key": "c", "to_port": "input"},
    ])
    dlg = PipelineGraphEditorDialog(None, pipeline=pipeline)
    scene = dlg._scene

    scene.set_executing_step_keys({"b", "c"})
    assert scene.nodes["b"]._is_executing
    assert scene.nodes["c"]._is_executing
    assert not scene.nodes["a"]._is_executing

    # "b" se termine, "c" tourne toujours — surlignage individuel, pas tout-ou-rien.
    scene.set_executing_step_keys({"c"})
    assert not scene.nodes["b"]._is_executing
    assert scene.nodes["c"]._is_executing


def test_set_executing_step_keys_unknown_key_is_a_no_op(qapp, test_db):
    pipeline = db.create_pipeline(name="trace-glow-unknown-key")
    db.save_pipeline_graph(pipeline.id, steps=[
        {"step_type": "DB_EXTRACT", "config": {"_step_key": "a"}},
    ], edges=[])
    dlg = PipelineGraphEditorDialog(None, pipeline=pipeline)

    dlg._scene.set_executing_step_keys({"does-not-exist"})   # ne doit pas lever d'exception
    assert not dlg._scene.nodes["a"]._is_executing


def test_poll_executing_step_calls_scene_with_running_step_key(qapp, test_db, monkeypatch):
    """Le QTimer de polling interroge get_running_step_keys() et répercute le résultat sur la
    scène — vérifié directement sur la méthode plutôt qu'en attendant un vrai déclenchement du
    QTimer (pas d'exécution réelle de pipeline dans ce test)."""
    pipeline = db.create_pipeline(name="trace-glow-poll")
    db.save_pipeline_graph(pipeline.id, steps=[
        {"step_type": "DB_EXTRACT", "config": {"_step_key": "a"}},
    ], edges=[])
    dlg = PipelineGraphEditorDialog(None, pipeline=pipeline)

    monkeypatch.setattr(db, "get_running_step_keys", lambda: {pipeline.id: "a"})
    dlg._poll_executing_step()
    assert dlg._scene.nodes["a"]._is_executing

    monkeypatch.setattr(db, "get_running_step_keys", lambda: {})
    dlg._poll_executing_step()
    assert not dlg._scene.nodes["a"]._is_executing


def test_incoming_prior_steps_returns_only_connected_upstream_steps(qapp, test_db):
    """Régression : _on_add_step()/_on_node_double_clicked() passaient prior_steps=[] en dur au
    dialogue de config d'étape, donc le sélecteur "Source"/bouton "+ Artefact" (chantier 3)
    n'affichaient jamais les étapes réellement connectées dans l'éditeur graphique (toujours
    "étape précédente (par défaut)", contrairement à l'éditeur linéaire où prior_steps a toujours
    été correctement rempli)."""
    pipeline = db.create_pipeline(name="incoming-prior-steps-test")
    db.save_pipeline_graph(pipeline.id, steps=[
        {"step_type": "DB_EXTRACT", "config": {"_step_key": "a"}},
        {"step_type": "DB_EXTRACT", "config": {"_step_key": "b"}},
        {"step_type": "LOCAL_COPY", "config": {"_step_key": "c"}},
    ], edges=[
        {"from_step_key": "a", "from_port": "output_file", "to_step_key": "c", "to_port": "input"},
        {"from_step_key": "b", "from_port": "output_file", "to_step_key": "c", "to_port": "input"},
    ])
    dlg = PipelineGraphEditorDialog(None, pipeline=pipeline)

    prior = dlg._incoming_prior_steps(dlg._scene.nodes["c"])
    assert {s["config"]["_step_key"] for s in prior} == {"a", "b"}

    # "a" n'a aucune arête entrante — sa liste doit rester vide, pas celle du nœud "c".
    assert dlg._incoming_prior_steps(dlg._scene.nodes["a"]) == []


def test_on_node_double_clicked_passes_connected_steps_to_config_dialog(qapp, test_db, monkeypatch):
    from PySide6.QtWidgets import QDialog
    import ui.step_editor as step_editor_module

    pipeline = db.create_pipeline(name="double-click-prior-steps-test")
    db.save_pipeline_graph(pipeline.id, steps=[
        {"step_type": "DB_EXTRACT", "config": {"_step_key": "a"}},
        {"step_type": "LOCAL_COPY", "config": {"_step_key": "b"}},
    ], edges=[
        {"from_step_key": "a", "from_port": "output_file", "to_step_key": "b", "to_port": "input"},
    ])
    dlg = PipelineGraphEditorDialog(None, pipeline=pipeline)

    captured = {}

    class _FakeConfigDialog:
        def exec(self):
            return QDialog.Rejected

    def _fake_open_config_dialog(*args, **kwargs):
        captured["prior_steps"] = kwargs.get("prior_steps")
        return _FakeConfigDialog()

    monkeypatch.setattr(step_editor_module, "_open_config_dialog", _fake_open_config_dialog)

    dlg._on_node_double_clicked(dlg._scene.nodes["b"])

    assert [s["config"]["_step_key"] for s in captured["prior_steps"]] == ["a"]


def test_on_add_step_passes_all_scene_steps_as_prior_steps(qapp, test_db, monkeypatch):
    """À l'ajout, le nouveau nœud n'a encore aucune arête (il n'existe pas sur le canevas) — même
    souplesse que l'éditeur linéaire à l'ajout (prior_steps=self._steps_data, la liste complète) :
    tous les nœuds déjà présents sont proposés, à connecter ensuite par glisser-déposer."""
    from PySide6.QtWidgets import QDialog
    import ui.step_editor as step_editor_module
    from ui.step_editor.step_type_chooser_dialog import StepTypeChooserDialog

    pipeline = db.create_pipeline(name="add-step-prior-steps-test")
    db.save_pipeline_graph(pipeline.id, steps=[
        {"step_type": "DB_EXTRACT", "config": {"_step_key": "a"}},
    ], edges=[])
    dlg = PipelineGraphEditorDialog(None, pipeline=pipeline)

    monkeypatch.setattr(StepTypeChooserDialog, "exec", lambda self: QDialog.Accepted)
    monkeypatch.setattr(StepTypeChooserDialog, "chosen_type", "LOCAL_COPY", raising=False)

    captured = {}

    class _FakeConfigDialog:
        def exec(self):
            return QDialog.Rejected

    def _fake_open_config_dialog(*args, **kwargs):
        captured["prior_steps"] = kwargs.get("prior_steps")
        return _FakeConfigDialog()

    monkeypatch.setattr(step_editor_module, "_open_config_dialog", _fake_open_config_dialog)

    dlg._on_add_step()

    assert [s["config"]["_step_key"] for s in captured["prior_steps"]] == ["a"]


def test_settings_button_opens_settings_dialog_and_refreshes_title(qapp, test_db, monkeypatch):
    """Raccourci vers les métadonnées du pipeline (chantier déclenchement conditionnel, puis
    fusion des éditeurs) — évite l'aller-retour "fermer, retrouver la ligne, cliquer Paramètres"
    juste pour la planification/le déclenchement, que ce dialogue ne gère pas lui-même."""
    from PySide6.QtWidgets import QDialog
    import ui.step_editor as step_editor_module

    pipeline = db.create_pipeline(name="settings-shortcut-test")
    dlg = PipelineGraphEditorDialog(None, pipeline=pipeline)

    captured = {}
    class _FakeSettingsDialog:
        def __init__(self, parent, pipeline):
            captured["pipeline_id"] = pipeline.id

        def exec(self):
            # Simule un renommage effectué dans le panneau Paramètres, comme le ferait un vrai
            # PipelineSettingsDialog._on_save().
            db.update_pipeline(pipeline.id, name="renamed-via-settings-dialog")
            return QDialog.Accepted

    monkeypatch.setattr(step_editor_module, "PipelineSettingsDialog", _FakeSettingsDialog)

    dlg._on_open_settings_dialog()

    assert captured["pipeline_id"] == pipeline.id
    assert dlg._pipeline.name == "renamed-via-settings-dialog"
    assert "renamed-via-settings-dialog" in dlg.windowTitle()


# ──────────────────────────────────────────────
#  Rangement automatique (chantier UX éditeur, Lot 1)
# ──────────────────────────────────────────────

def test_auto_layout_assigns_columns_by_rank(qapp, test_db):
    pipeline = db.create_pipeline(name="auto-layout-linear")
    db.save_pipeline_graph(pipeline.id, steps=[
        {"step_type": "DB_EXTRACT", "config": {"_step_key": "a"}},
        {"step_type": "LOCAL_COPY", "config": {"_step_key": "b"}},
        {"step_type": "LOCAL_COPY", "config": {"_step_key": "c"}},
    ], edges=[
        {"from_step_key": "a", "from_port": "output_file", "to_step_key": "b", "to_port": "input"},
        {"from_step_key": "b", "from_port": "output_file", "to_step_key": "c", "to_port": "input"},
    ])
    dlg = PipelineGraphEditorDialog(None, pipeline=pipeline)

    dlg._on_auto_layout()

    xa = dlg._scene.nodes["a"].pos().x()
    xb = dlg._scene.nodes["b"].pos().x()
    xc = dlg._scene.nodes["c"].pos().x()
    assert xa < xb < xc
    assert dlg._btn_undo_layout.isEnabled()


def test_auto_layout_orders_diamond_branches_by_barycenter(qapp, test_db):
    """a -> b, a -> c, b -> d, c -> d : b et c doivent finir au même rang (même colonne),
    d au rang suivant — pas juste "quelque part", la colonne compte, pas la ligne exacte."""
    pipeline = db.create_pipeline(name="auto-layout-diamond")
    db.save_pipeline_graph(pipeline.id, steps=[
        {"step_type": "DB_EXTRACT", "config": {"_step_key": "a"}},
        {"step_type": "LOCAL_COPY", "config": {"_step_key": "b"}},
        {"step_type": "LOCAL_COPY", "config": {"_step_key": "c"}},
        {"step_type": "LOCAL_COPY", "config": {"_step_key": "d"}},
    ], edges=[
        {"from_step_key": "a", "from_port": "output_file", "to_step_key": "b", "to_port": "input"},
        {"from_step_key": "a", "from_port": "output_file", "to_step_key": "c", "to_port": "input"},
        {"from_step_key": "b", "from_port": "output_file", "to_step_key": "d", "to_port": "input"},
        {"from_step_key": "c", "from_port": "output_file", "to_step_key": "d", "to_port": "input"},
    ])
    dlg = PipelineGraphEditorDialog(None, pipeline=pipeline)

    dlg._on_auto_layout()

    xa = dlg._scene.nodes["a"].pos().x()
    xb = dlg._scene.nodes["b"].pos().x()
    xc = dlg._scene.nodes["c"].pos().x()
    xd = dlg._scene.nodes["d"].pos().x()
    assert xa < xb == xc < xd
    assert dlg._scene.nodes["b"].pos().y() != dlg._scene.nodes["c"].pos().y()


def test_auto_layout_warns_and_leaves_positions_unchanged_on_cycle(qapp, test_db, monkeypatch):
    import ui.graph_editor.graph_editor_dialog as dialog_module

    pipeline = db.create_pipeline(name="auto-layout-cycle")
    db.save_pipeline_graph(pipeline.id, steps=[
        {"step_type": "DB_EXTRACT", "config": {"_step_key": "a"}},
        {"step_type": "LOCAL_COPY", "config": {"_step_key": "b"}},
    ], edges=[
        {"from_step_key": "a", "from_port": "output_file", "to_step_key": "b", "to_port": "input"},
        {"from_step_key": "b", "from_port": "output_file", "to_step_key": "a", "to_port": "input"},
    ])
    dlg = PipelineGraphEditorDialog(None, pipeline=pipeline)
    before = {k: n.pos() for k, n in dlg._scene.nodes.items()}

    warnings = []
    monkeypatch.setattr(dialog_module.QMessageBox, "warning",
                         staticmethod(lambda *a, **k: warnings.append(a)))

    dlg._on_auto_layout()

    assert len(warnings) == 1
    assert {k: n.pos() for k, n in dlg._scene.nodes.items()} == before
    assert not dlg._btn_undo_layout.isEnabled()


def test_undo_layout_restores_previous_positions(qapp, test_db):
    pipeline = db.create_pipeline(name="auto-layout-undo")
    db.save_pipeline_graph(pipeline.id, steps=[
        {"step_type": "DB_EXTRACT", "config": {"_step_key": "a"}},
        {"step_type": "LOCAL_COPY", "config": {"_step_key": "b"}},
    ], edges=[
        {"from_step_key": "a", "from_port": "output_file", "to_step_key": "b", "to_port": "input"},
    ])
    dlg = PipelineGraphEditorDialog(None, pipeline=pipeline)
    before = {k: (n.pos().x(), n.pos().y()) for k, n in dlg._scene.nodes.items()}

    dlg._on_auto_layout()
    assert {k: (n.pos().x(), n.pos().y()) for k, n in dlg._scene.nodes.items()} != before
    assert dlg._btn_undo_layout.isEnabled()

    dlg._on_undo_layout()

    assert {k: (n.pos().x(), n.pos().y()) for k, n in dlg._scene.nodes.items()} == before
    assert not dlg._btn_undo_layout.isEnabled()


def test_undo_layout_button_disabled_by_default(qapp, test_db):
    pipeline = db.create_pipeline(name="auto-layout-default")
    db.save_pipeline_graph(pipeline.id, steps=[
        {"step_type": "DB_EXTRACT", "config": {"_step_key": "a"}},
    ], edges=[])
    dlg = PipelineGraphEditorDialog(None, pipeline=pipeline)

    assert not dlg._btn_undo_layout.isEnabled()


# ──────────────────────────────────────────────
#  Ranger la sélection (chantier UX éditeur, Lot 3, A6)
# ──────────────────────────────────────────────

def test_compute_auto_layout_positions_node_subset_leaves_others_untouched(qapp, test_db):
    pipeline = db.create_pipeline(name="auto-layout-subset")
    db.save_pipeline_graph(pipeline.id, steps=[
        {"step_type": "DB_EXTRACT", "config": {"_step_key": "a"}},
        {"step_type": "LOCAL_COPY", "config": {"_step_key": "b"}},
        {"step_type": "LOCAL_COPY", "config": {"_step_key": "c"}},
    ], edges=[
        {"from_step_key": "a", "from_port": "output_file", "to_step_key": "b", "to_port": "input"},
        {"from_step_key": "b", "from_port": "output_file", "to_step_key": "c", "to_port": "input"},
    ])
    dlg = PipelineGraphEditorDialog(None, pipeline=pipeline)

    positions = dlg._compute_auto_layout_positions(node_subset={"b"})

    assert positions is not None
    assert set(positions.keys()) == {"b"}


def test_arrange_selection_moves_only_selected_nodes(qapp, test_db):
    pipeline = db.create_pipeline(name="arrange-selection")
    db.save_pipeline_graph(pipeline.id, steps=[
        {"step_type": "DB_EXTRACT", "config": {"_step_key": "a"}},
        {"step_type": "LOCAL_COPY", "config": {"_step_key": "b"}},
        {"step_type": "LOCAL_COPY", "config": {"_step_key": "c"}},
    ], edges=[
        {"from_step_key": "a", "from_port": "output_file", "to_step_key": "b", "to_port": "input"},
        {"from_step_key": "b", "from_port": "output_file", "to_step_key": "c", "to_port": "input"},
    ])
    dlg = PipelineGraphEditorDialog(None, pipeline=pipeline)
    pos_a_before = dlg._scene.nodes["a"].pos()
    pos_c_before = dlg._scene.nodes["c"].pos()
    dlg._scene.nodes["b"].setSelected(True)

    dlg._on_arrange_selection()

    assert dlg._scene.nodes["a"].pos() == pos_a_before
    assert dlg._scene.nodes["c"].pos() == pos_c_before
    assert dlg._btn_undo_layout.isEnabled()


def test_arrange_selection_no_selection_is_a_no_op(qapp, test_db):
    pipeline = db.create_pipeline(name="arrange-selection-empty")
    db.save_pipeline_graph(pipeline.id, steps=[
        {"step_type": "DB_EXTRACT", "config": {"_step_key": "a"}},
    ], edges=[])
    dlg = PipelineGraphEditorDialog(None, pipeline=pipeline)
    before = dlg._scene.nodes["a"].pos()

    dlg._on_arrange_selection()

    assert dlg._scene.nodes["a"].pos() == before
    assert not dlg._btn_undo_layout.isEnabled()


def test_undo_after_arrange_selection_restores_all_positions(qapp, test_db):
    pipeline = db.create_pipeline(name="arrange-selection-undo")
    db.save_pipeline_graph(pipeline.id, steps=[
        {"step_type": "DB_EXTRACT", "config": {"_step_key": "a"}},
        {"step_type": "LOCAL_COPY", "config": {"_step_key": "b"}},
    ], edges=[
        {"from_step_key": "a", "from_port": "output_file", "to_step_key": "b", "to_port": "input"},
    ])
    dlg = PipelineGraphEditorDialog(None, pipeline=pipeline)
    before = {k: (n.pos().x(), n.pos().y()) for k, n in dlg._scene.nodes.items()}
    dlg._scene.nodes["b"].setSelected(True)

    dlg._on_arrange_selection()
    dlg._on_undo_layout()

    assert {k: (n.pos().x(), n.pos().y()) for k, n in dlg._scene.nodes.items()} == before
    assert not dlg._btn_undo_layout.isEnabled()


# ──────────────────────────────────────────────
#  Recherche textuelle (chantier UX éditeur, Lot 2, B3)
# ──────────────────────────────────────────────

def test_search_text_matches_type_label_and_user_label():
    node = StepNodeItem({
        "step_type": "DB_EXTRACT", "label": "Ventes Q3",
        "config": {"_step_key": "a"},
    })
    text = node.search_text()
    assert "ventes q3" in text
    # Le libellé de type peint (STEP_META) doit aussi apparaître, pas seulement le libellé
    # utilisateur — une recherche sur le type doit fonctionner même sans libellé personnalisé.
    from ui.step_editor import STEP_META
    assert STEP_META["DB_EXTRACT"]["label"].lower() in text


def test_search_text_tolerates_missing_user_label():
    node = StepNodeItem({"step_type": "LOCAL_COPY", "config": {"_step_key": "a"}})
    assert node.search_text()   # ne plante pas, jamais None


def test_on_search_changed_marks_matching_nodes_and_dims_the_rest(qapp, test_db):
    pipeline = db.create_pipeline(name="search-dim-test")
    db.save_pipeline_graph(pipeline.id, steps=[
        {"step_type": "DB_EXTRACT", "label": "Ventes", "config": {"_step_key": "a"}},
        {"step_type": "LOCAL_COPY", "label": "Archive", "config": {"_step_key": "b"}},
    ], edges=[
        {"from_step_key": "a", "from_port": "output_file", "to_step_key": "b", "to_port": "input"},
    ])
    dlg = PipelineGraphEditorDialog(None, pipeline=pipeline)

    dlg._on_search_changed("ventes")

    node_a, node_b = dlg._scene.nodes["a"], dlg._scene.nodes["b"]
    assert node_a.is_search_hit and node_a.opacity() == 1.0
    assert not node_b.is_search_hit and node_b.opacity() < 1.0
    # L'arête touche un nœud correspondant ("a") — reste pleinement visible pour donner du
    # contexte autour du résultat, seul le nœud non correspondant est atténué.
    assert dlg._scene.edges[0].opacity() == 1.0
    assert dlg._search_matches == [node_a]


def test_on_search_changed_empty_needle_restores_full_opacity(qapp, test_db):
    pipeline = db.create_pipeline(name="search-clear-test")
    db.save_pipeline_graph(pipeline.id, steps=[
        {"step_type": "DB_EXTRACT", "label": "Ventes", "config": {"_step_key": "a"}},
        {"step_type": "LOCAL_COPY", "label": "Archive", "config": {"_step_key": "b"}},
    ], edges=[])
    dlg = PipelineGraphEditorDialog(None, pipeline=pipeline)

    dlg._on_search_changed("ventes")
    dlg._on_search_changed("")

    for node in dlg._scene.nodes.values():
        assert not node.is_search_hit
        assert node.opacity() == 1.0
    assert dlg._search_matches == []


def test_on_search_changed_never_dims_an_executing_or_failed_node(qapp, test_db):
    """Une recherche sans rapport avec le nœud en cours/en échec ne doit jamais l'enterrer
    visuellement — l'état d'exécution/échec reste toujours la priorité la plus haute."""
    pipeline = db.create_pipeline(name="search-protects-state-test")
    db.save_pipeline_graph(pipeline.id, steps=[
        {"step_type": "DB_EXTRACT", "label": "Ventes", "config": {"_step_key": "a"}},
        {"step_type": "LOCAL_COPY", "label": "Archive", "config": {"_step_key": "b"}},
    ], edges=[
        {"from_step_key": "a", "from_port": "output_file", "to_step_key": "b", "to_port": "input"},
    ])
    dlg = PipelineGraphEditorDialog(None, pipeline=pipeline)
    dlg._scene.nodes["b"].set_executing(True)

    dlg._on_search_changed("ne correspond à rien")

    assert dlg._scene.nodes["b"].opacity() == 1.0
    assert dlg._scene.nodes["a"].opacity() < 1.0


def test_on_search_jump_cycles_through_matches_and_centers_view(qapp, test_db, monkeypatch):
    pipeline = db.create_pipeline(name="search-jump-test")
    db.save_pipeline_graph(pipeline.id, steps=[
        {"step_type": "DB_EXTRACT", "label": "Extraction A", "config": {"_step_key": "a"}},
        {"step_type": "LOCAL_COPY", "label": "Extraction B", "config": {"_step_key": "b"}},
    ], edges=[])
    dlg = PipelineGraphEditorDialog(None, pipeline=pipeline)

    centered = []
    monkeypatch.setattr(dlg._view, "centerOn", lambda item: centered.append(item))

    dlg._on_search_changed("extraction")
    assert len(dlg._search_matches) == 2

    dlg._on_search_jump()
    dlg._on_search_jump()
    dlg._on_search_jump()

    assert centered == [dlg._search_matches[0], dlg._search_matches[1], dlg._search_matches[0]]


def test_on_search_jump_with_no_matches_is_a_no_op(qapp, test_db, monkeypatch):
    pipeline = db.create_pipeline(name="search-jump-empty-test")
    db.save_pipeline_graph(pipeline.id, steps=[
        {"step_type": "DB_EXTRACT", "config": {"_step_key": "a"}},
    ], edges=[])
    dlg = PipelineGraphEditorDialog(None, pipeline=pipeline)

    centered = []
    monkeypatch.setattr(dlg._view, "centerOn", lambda item: centered.append(item))

    dlg._on_search_changed("introuvable")
    dlg._on_search_jump()

    assert centered == []

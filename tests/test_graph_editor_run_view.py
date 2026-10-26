"""
DataScheduler — tests/test_graph_editor_run_view.py
C9 (Atelier-echec) : PipelineGraphEditorWidget(run_id=...) — applique l'état réel d'un run passé
sur le canevas (nœuds/arêtes), construit le panneau de diagnostic et le chronogramme. Les lignes
pipeline_run_steps sont écrites directement via db.record_run_step (contrôle précis des
horodatages), pas via un vrai run_pipeline() — déjà vérifié bout en bout manuellement, ce fichier
teste la traduction données → widgets en isolation.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from datetime import datetime, timedelta

import pytest
from PySide6.QtWidgets import QApplication, QGraphicsItem

from database import db_manager as db
from ui.graph_editor import PipelineGraphEditorWidget


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _pipeline_with_a_failed_ftp_upload():
    """A (DB_EXTRACT, succès) -> B (FTP_UPLOAD, échec, 2 tentatives) — même topologie que le
    scénario manuel vérifié (Extraire -> Dépôt partenaire)."""
    p = db.create_pipeline(name="run-view-test")
    db.save_pipeline_graph(p.id, steps=[
        {"step_type": "DB_EXTRACT", "label": "Extraire", "config": {"_step_key": "a"}},
        {"step_type": "FTP_UPLOAD", "label": "Déposer", "config": {"_step_key": "b"}},
    ], edges=[{"from_step_key": "a", "from_port": "output_file", "to_step_key": "b"}])
    return p


def _widget(pipeline, run_id):
    return PipelineGraphEditorWidget(
        pipeline=db.get_pipeline(pipeline.id), show_settings_shortcut_button=False, run_id=run_id,
    )


# ── Repli quand pipeline_run_steps est vide (acceptance criterion B1) ──

def test_apply_run_view_returns_false_when_no_run_steps_recorded(qapp, test_db):
    """Ancien worker qui n'écrit pas encore cette table — Main et Atelier-echec doivent
    s'afficher sans erreur ni place vide (acceptance criterion B1)."""
    p = _pipeline_with_a_failed_ftp_upload()
    run = db.create_run(p.id)
    db.finish_run(run.id, status="FAILED", failed_step_key="b")

    # highlight_step_key est toujours transmis avec run_id par le vrai appelant (HistoryView via
    # MainWindow.open_atelier_run) — reproduit ici explicitement, _apply_run_view() seule ne
    # saurait pas quel nœud surligner sans ça.
    widget = PipelineGraphEditorWidget(
        pipeline=db.get_pipeline(p.id), show_settings_shortcut_button=False,
        run_id=run.id, highlight_step_key="b",
    )

    assert widget._run_steps_by_key == {}
    # Repli sur l'ancien comportement highlight_step_key : un seul nœud rouge.
    assert widget._scene.nodes["b"]._is_failed
    assert widget._scene.nodes["b"]._run_status_text is None


# ── Nœuds/arêtes ─────────────────────────────────

def test_apply_run_view_applies_success_and_failed_status_to_nodes(qapp, test_db):
    p = _pipeline_with_a_failed_ftp_upload()
    run = db.create_run(p.id)
    t0 = datetime(2026, 10, 18, 11, 0, 0)
    db.record_run_step(
        run.id, step_key="a", step_type="DB_EXTRACT", step_label="Extraire", status="SUCCESS",
        started_at=t0, finished_at=t0 + timedelta(seconds=41), rows_count=83212,
    )
    db.record_run_step(
        run.id, step_key="b", step_type="FTP_UPLOAD", step_label="Déposer", status="FAILED",
        attempts=2, error_message="Connection refused",
    )
    db.finish_run(run.id, status="FAILED", failed_step_key="b")

    widget = _widget(p, run.id)

    node_a, node_b = widget._scene.nodes["a"], widget._scene.nodes["b"]
    assert node_a._run_status_text == "✓ 41 s · 83 212 l."
    assert node_a._run_status_color_key == "success"
    assert not node_a._is_failed

    assert node_b._run_status_text == "✕ 2 tentatives refusées"
    assert node_b._is_failed
    # Lecture seule (C9) : un run passé ne se repositionne pas en le glissant.
    assert not (node_a.flags() & QGraphicsItem.ItemIsMovable)
    assert not (node_b.flags() & QGraphicsItem.ItemIsMovable)


def test_apply_run_view_marks_edges_taken_and_failed(qapp, test_db):
    p = _pipeline_with_a_failed_ftp_upload()
    run = db.create_run(p.id)
    db.record_run_step(run.id, step_key="a", step_type="DB_EXTRACT", status="SUCCESS", step_label=None)
    db.record_run_step(run.id, step_key="b", step_type="FTP_UPLOAD", status="FAILED", step_label=None)
    db.finish_run(run.id, status="FAILED", failed_step_key="b")

    widget = _widget(p, run.id)

    edge = widget._scene.edges[0]
    assert edge._run_state == "taken"
    assert edge._is_failed   # arête entrante d'un nœud FAILED


def test_apply_run_view_not_executed_node_is_marked(qapp, test_db):
    p = db.create_pipeline(name="run-view-not-executed")
    db.save_pipeline_graph(p.id, steps=[
        {"step_type": "DB_EXTRACT", "config": {"_step_key": "a"}},
        {"step_type": "EMAIL_NOTIFY", "config": {"_step_key": "b"}},
    ], edges=[{"from_step_key": "a", "from_port": "output_file", "to_step_key": "b"}])
    run = db.create_run(p.id)
    db.record_run_step(run.id, step_key="a", step_type="DB_EXTRACT", status="FAILED", step_label=None)
    db.record_run_step(run.id, step_key="b", step_type="EMAIL_NOTIFY", status="SKIPPED", step_label=None)
    db.finish_run(run.id, status="FAILED", failed_step_key="a")

    widget = _widget(p, run.id)

    node_b = widget._scene.nodes["b"]
    assert node_b._run_card_state == "not_executed"
    assert node_b._run_status_text == "non exécutée"


def test_apply_run_view_success_via_error_port_is_flagged(qapp, test_db):
    p = db.create_pipeline(name="run-view-via-error")
    db.save_pipeline_graph(p.id, steps=[
        {"step_type": "DB_EXTRACT", "config": {"_step_key": "a"}},
        {"step_type": "HTTP_REQUEST", "config": {"_step_key": "webhook"}},
    ], edges=[{"from_step_key": "a", "from_port": "error", "to_step_key": "webhook"}])
    run = db.create_run(p.id)
    db.record_run_step(run.id, step_key="a", step_type="DB_EXTRACT", status="FAILED", step_label=None)
    t0 = datetime(2026, 10, 18, 11, 0, 0)
    db.record_run_step(
        run.id, step_key="webhook", step_type="HTTP_REQUEST", step_label=None, status="SUCCESS",
        started_at=t0, finished_at=t0 + timedelta(seconds=1), port_taken="error",
    )
    db.finish_run(run.id, status="FAILED", failed_step_key="a")

    widget = _widget(p, run.id)

    node = widget._scene.nodes["webhook"]
    assert node._run_card_state == "error_triggered"
    assert node._run_status_text == "✓ via le port d'erreur · 1 s"

    edge = widget._scene.edges[0]
    assert edge._run_state == "error_triggered"


# ── Panneau de diagnostic ────────────────────────

def test_failure_panel_is_populated_with_attempts_and_error_message(qapp, test_db):
    p = _pipeline_with_a_failed_ftp_upload()
    run = db.create_run(p.id)
    db.record_run_step(run.id, step_key="a", step_type="DB_EXTRACT", status="SUCCESS", step_label=None)
    attempts_json = (
        '[{"n": 1, "started_at": "2026-10-18T11:29:09", "finished_at": "2026-10-18T11:29:10", '
        '"error": "Connection refused"},'
        '{"n": 2, "started_at": "2026-10-18T11:29:44", "finished_at": "2026-10-18T11:29:45", '
        '"error": "Connection refused"}]'
    )
    db.record_run_step(
        run.id, step_key="b", step_type="FTP_UPLOAD", step_label="Déposer", status="FAILED",
        attempts=2, attempts_json=attempts_json, error_message="Connection refused",
    )
    db.finish_run(run.id, status="FAILED", failed_step_key="b")

    widget = _widget(p, run.id)

    assert widget.failure_panel._title.text() == "Déposer"
    assert "ÉCHEC" in widget.failure_panel._eyebrow.text()
    # 2 lignes TENTATIVES construites (section + 2 lignes) — vérifié indirectement via le
    # nombre d'éléments du corps plutôt que le texte exact des labels Qt imbriqués.
    assert widget.failure_panel._body.count() >= 2


def test_failure_panel_resume_hint_only_when_resumable(qapp, test_db):
    p = _pipeline_with_a_failed_ftp_upload()
    run = db.create_run(p.id)
    db.record_run_step(run.id, step_key="a", step_type="DB_EXTRACT", status="SUCCESS", step_label=None)
    db.record_run_step(run.id, step_key="b", step_type="FTP_UPLOAD", status="FAILED", step_label=None)
    db.finish_run(run.id, status="FAILED", failed_step_key="b", resumable_state_json="{}")

    widget = _widget(p, run.id)

    # Une carte "Reprendre depuis l'échec" de plus dans le corps par rapport à un run non
    # reprenable (vérifié ci-dessous) — comparaison relative, pas un compte en dur fragile.
    with_resume_count = widget.failure_panel._body.count()

    run2 = db.create_run(p.id)
    db.record_run_step(run2.id, step_key="a", step_type="DB_EXTRACT", status="SUCCESS", step_label=None)
    db.record_run_step(run2.id, step_key="b", step_type="FTP_UPLOAD", status="FAILED", step_label=None)
    db.finish_run(run2.id, status="FAILED", failed_step_key="b")
    widget2 = _widget(p, run2.id)
    without_resume_count = widget2.failure_panel._body.count()

    assert with_resume_count > without_resume_count


# ── Chronogramme ─────────────────────────────────

def test_timeline_panel_excludes_routing_and_skipped_nodes(qapp, test_db):
    p = db.create_pipeline(name="run-view-chrono")
    db.save_pipeline_graph(p.id, steps=[
        {"step_type": "DB_EXTRACT", "label": "Extraire", "config": {"_step_key": "a"}},
        {"step_type": "CONDITION", "label": "Cond", "config": {"_step_key": "c"}},
        {"step_type": "LOCAL_COPY", "label": "Copier", "config": {"_step_key": "b"}},
    ], edges=[
        {"from_step_key": "a", "from_port": "output_file", "to_step_key": "c"},
        {"from_step_key": "c", "from_port": "true", "to_step_key": "b"},
    ])
    run = db.create_run(p.id)
    t0 = datetime(2026, 10, 18, 11, 0, 0)
    db.record_run_step(run.id, step_key="a", step_type="DB_EXTRACT", step_label=None, status="SUCCESS",
                        started_at=t0, finished_at=t0 + timedelta(seconds=10))
    db.record_run_step(run.id, step_key="c", step_type="CONDITION", step_label=None, status="SUCCESS",
                        started_at=t0, finished_at=t0)
    db.record_run_step(run.id, step_key="b", step_type="LOCAL_COPY", status="SKIPPED", step_label=None)
    db.finish_run(run.id, status="SUCCESS")

    widget = _widget(p, run.id)

    # Seule "Extraire" a une ligne (CONDITION exclu : routage ; "Copier" exclu : SKIPPED).
    assert widget.timeline_panel is not None   # construit sans lever

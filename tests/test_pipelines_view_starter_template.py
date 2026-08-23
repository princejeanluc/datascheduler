"""
DataScheduler — tests/test_pipelines_view_starter_template.py
Chantier UX éditeur, Lot 1 (C1) : bouton "Commencer avec un modèle" sur l'état vide de
PipelinesView — importe database/pipeline_templates.py::build_starter_template_bundle() via le
même mécanisme que l'import d'un vrai fichier .dspipeline (plan_import()/apply_import()
n'exigent pas qu'un bundle vienne d'un vrai export), puis ouvre l'éditeur graphique dessus.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QDialog

from database import db_manager as db


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_starter_template_bundle_is_a_fresh_dict_each_call():
    """plan_import()/apply_import() ne doivent jamais recevoir deux fois le même dict muté en
    place — chaque appel doit reconstruire le bundle, pas partager une constante."""
    from database.pipeline_templates import build_starter_template_bundle

    a = build_starter_template_bundle()
    b = build_starter_template_bundle()
    assert a is not b
    assert a == b


def test_starter_template_imports_cleanly_with_expected_steps_and_edge(test_db):
    from database.export_import import plan_import, apply_import
    from database.pipeline_templates import build_starter_template_bundle

    plan = plan_import(build_starter_template_bundle())
    assert plan.success, plan.error

    result = apply_import(plan)
    assert result.success, result.error

    steps = db.get_steps(result.pipeline_id)
    step_types = sorted(str(s.step_type).replace("StepType.", "") for s in steps)
    assert step_types == ["DB_EXTRACT", "LOCAL_COPY"]

    edges = db.get_edges(result.pipeline_id)
    assert len(edges) == 1
    assert edges[0].from_step_key == "extraction"
    assert edges[0].to_step_key == "depot"


def test_starter_template_button_creates_pipeline_and_opens_graph_editor(qapp, test_db, monkeypatch):
    from ui.main_window.pipelines_view import PipelinesView

    view = PipelinesView()
    assert db.get_pipelines() == []

    exec_calls = []
    monkeypatch.setattr(QDialog, "exec", lambda self: exec_calls.append(True) or QDialog.Accepted)

    view._on_start_from_template()

    pipelines = db.get_pipelines()
    assert len(pipelines) == 1
    assert exec_calls == [True]   # PipelineGraphEditorDialog().exec() bien atteint


def test_starter_template_can_be_created_more_than_once(test_db):
    """Un nom unique (_unique_name côté apply_import, même mécanisme que duplicate_pipeline)
    évite toute collision si l'utilisateur clique le bouton plusieurs fois."""
    from database.export_import import plan_import, apply_import
    from database.pipeline_templates import build_starter_template_bundle

    result1 = apply_import(plan_import(build_starter_template_bundle()))
    result2 = apply_import(plan_import(build_starter_template_bundle()))

    assert result1.success and result2.success
    names = {p.name for p in db.get_pipelines()}
    assert len(names) == 2

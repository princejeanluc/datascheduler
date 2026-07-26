"""
DataScheduler — tests/test_export_dialog.py
Fumée : le dialogue d'export s'ouvre sans erreur (offscreen Qt) — même réflexe que
tests/test_step_editor_dialogs.py après le bug de kwargs manquant du chantier 3.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from ui.dialogs import PipelineExportDialog, PipelineImportPasswordDialog, PipelineImportReviewDialog


class _FakePipeline:
    id = 1
    name = "Mon pipeline"


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_export_dialog_opens_without_error(qapp):
    dlg = PipelineExportDialog(None, pipeline=_FakePipeline())
    assert dlg.windowTitle()
    assert dlg.inp_password.text() == ""


def test_import_password_dialog_opens_without_error(qapp):
    dlg = PipelineImportPasswordDialog(None)
    assert dlg.windowTitle()
    assert dlg.password() == ""


def test_import_review_dialog_opens_and_confirm_mutates_plan(qapp, test_db):
    from database import db_manager as db
    from database.export_import import export_pipeline, plan_import

    profile = db.create_oracle_profile(
        name="ORACLE_PROD", host="h", port=1521,
        username="u", password="p", service_name="S",
    )
    pipeline = db.create_pipeline(name="review-test")
    db.save_steps(pipeline.id, [{
        "step_type": "DB_EXTRACT",
        "config": {"db_type": "ORACLE", "profile_id": profile.id},
    }])
    export_result = export_pipeline(pipeline.id)
    plan = plan_import(export_result.bundle)
    assert plan.pipeline_action == "collision"

    dlg = PipelineImportReviewDialog(None, plan=plan)
    assert dlg.windowTitle()
    assert dlg.rb_overwrite is not None

    dlg.rb_overwrite.setChecked(True)
    dlg._on_confirm()

    assert plan.pipeline_action == "overwrite"

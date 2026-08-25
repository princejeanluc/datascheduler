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


def test_import_password_dialog_without_verify_accepts_unconditionally(qapp):
    """Comportement historique préservé pour tout appelant qui ne passe pas verify=."""
    from PySide6.QtWidgets import QDialog

    dlg = PipelineImportPasswordDialog(None)
    dlg.inp_password.setText("peu importe")

    dlg._on_validate()

    assert dlg.result() == QDialog.Accepted


def test_import_password_dialog_accepts_on_successful_verify(qapp):
    from PySide6.QtWidgets import QDialog
    from database.export_import import ImportPlan

    fake_plan = ImportPlan(success=True)
    dlg = PipelineImportPasswordDialog(None, verify=lambda pwd: fake_plan)
    dlg.inp_password.setText("bon-mot-de-passe")

    dlg._on_validate()

    assert dlg.result() == QDialog.Accepted
    assert dlg.plan is fake_plan


def test_import_password_dialog_shows_error_and_stays_open_on_failed_verify(qapp):
    """Correctif friction d'import : un mot de passe incorrect ne doit plus fermer le
    dialogue — juste afficher l'erreur sur place, pour une nouvelle tentative immédiate."""
    from PySide6.QtWidgets import QDialog
    from database.export_import import ImportPlan

    dlg = PipelineImportPasswordDialog(
        None, verify=lambda pwd: ImportPlan(success=False, error="Mot de passe incorrect."),
    )
    dlg.inp_password.setText("mauvais-mot-de-passe")

    dlg._on_validate()

    assert dlg.result() != QDialog.Accepted
    assert dlg.plan is None
    assert not dlg.lbl_error.isHidden()
    assert dlg.lbl_error.text() == "Mot de passe incorrect."


def test_import_password_dialog_clears_error_when_retyping(qapp):
    from database.export_import import ImportPlan

    dlg = PipelineImportPasswordDialog(
        None, verify=lambda pwd: ImportPlan(success=False, error="Mot de passe incorrect."),
    )
    dlg.inp_password.setText("mauvais")
    dlg._on_validate()
    assert not dlg.lbl_error.isHidden()

    dlg.inp_password.setText("mauvais2")

    assert dlg.lbl_error.isHidden()


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


def test_import_review_dialog_handles_ssh_kerberos_elevation_categories(qapp, test_db):
    """Ces 3 catégories (chantiers D.1/K/L) doivent être traitées comme les autres : libellé
    lisible, nom affiché pour une décision "reuse", et proposées dans le menu de remappage —
    jamais couvert avant ce test, l'écran de revue avait été laissé de côté à leur introduction."""
    from database import db_manager as db
    from database.export_import import export_pipeline, plan_import

    edge = db.create_ssh_profile(name="EDGE01", host="edge01", port=22, username="u", password="p")
    krb = db.create_kerberos_profile(name="KRB1", principal="u@REALM", password="p")
    elevation = db.create_elevation_profile(name="NIFI", target_user="nifi", password="p")
    pipeline = db.create_pipeline(name="review-ssh-test")
    db.save_steps(pipeline.id, [{
        "step_type": "SQOOP_EXPORT",
        "config": {
            "edge_profile_id": edge.id, "kerberos_profile_id": krb.id,
            "elevation_profile_id": elevation.id,
        },
    }])
    export_result = export_pipeline(pipeline.id)
    assert export_result.success, export_result.error

    # Base fraîche : les 3 profils n'existent pas encore localement -> décisions "create",
    # exactement le cas où le menu de remappage doit apparaître.
    db.delete_ssh_profile(edge.id)
    db.delete_kerberos_profile(krb.id)
    db.delete_elevation_profile(elevation.id)
    # Un profil du même type déjà présent en local, pour vérifier qu'il apparaît bien comme
    # option de remappage dans le menu (pas juste "Créer un nouveau profil").
    db.create_ssh_profile(name="EDGE_LOCAL", host="edgelocal", port=22, username="u", password="p")

    plan = plan_import(export_result.bundle)
    ssh_decisions = [d for d in plan.profile_decisions if d.category == "ssh"]
    assert ssh_decisions and ssh_decisions[0].action == "create"

    dlg = PipelineImportReviewDialog(None, plan=plan)
    categories_shown = {dlg._CATEGORY_LABELS.get(d.category, d.category)
                         for d in plan.profile_decisions}
    assert "SSH (nœud edge)" in categories_shown
    assert "Kerberos" in categories_shown
    assert "Élévation (sudo su)" in categories_shown

    ssh_combo = next(combo for decision, combo in dlg._combo_by_decision
                      if decision.category == "ssh")
    combo_labels = [ssh_combo.itemText(i) for i in range(ssh_combo.count())]
    assert any("EDGE_LOCAL" in label for label in combo_labels)

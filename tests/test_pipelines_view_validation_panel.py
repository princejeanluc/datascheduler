"""
DataScheduler — tests/test_pipelines_view_validation_panel.py
Refonte, lot A-Pipelines : A10 (validation à blanc dans un panneau latéral partagé, remplace
PipelineDryRunDialog pour PipelinesView).
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QLabel

from database import db_manager as db


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _settle(qapp, view):
    view._side_panel._anim.setCurrentTime(view._side_panel._anim.duration())
    qapp.processEvents()


def test_validate_opens_side_panel_not_modal_dialog(qapp, test_db, monkeypatch):
    from ui.main_window.pipelines_view import PipelinesView
    from ui.dialogs import PipelineDryRunDialog

    opened = []
    monkeypatch.setattr(PipelineDryRunDialog, "__init__", lambda self, *a, **k: opened.append(True))

    p = db.create_pipeline(name="validate-panel-test")
    view = PipelinesView()
    view._on_validate_pipeline(p.id, p.name)
    view._validation_thread.wait(5000)
    qapp.processEvents()

    assert not opened   # l'ancien dialogue modal n'est plus jamais instancié depuis cette vue
    assert not view._side_panel.isHidden()


def test_validation_panel_shows_pipeline_name_and_surtitle(qapp, test_db):
    from ui.main_window.pipelines_view import PipelinesView

    p = db.create_pipeline(name="validate-surtitle-test")
    view = PipelinesView()
    view._on_validate_pipeline(p.id, p.name)
    view._validation_thread.wait(5000)
    qapp.processEvents()

    text = " ".join(lbl.text() for lbl in view._side_panel.findChildren(QLabel))
    assert "VALIDATION À BLANC" in text
    assert "validate-surtitle-test" in text


def test_validation_panel_shows_errors_for_invalid_pipeline(qapp, test_db):
    from ui.main_window.pipelines_view import PipelinesView

    # Pipeline sans étape -> dry_run_pipeline() renvoie une erreur de forme.
    p = db.create_pipeline(name="validate-error-test")
    view = PipelinesView()
    view._on_validate_pipeline(p.id, p.name)
    view._validation_thread.wait(5000)
    qapp.processEvents()

    assert view._lbl_validation_errors.text() != "0"
    assert "échouée" in view._lbl_validation_status.text()


def test_validation_panel_rerun_button_relaunches_thread(qapp, test_db):
    from ui.main_window.pipelines_view import PipelinesView

    p = db.create_pipeline(name="validate-rerun-test")
    view = PipelinesView()
    view._on_validate_pipeline(p.id, p.name)
    view._validation_thread.wait(5000)
    qapp.processEvents()

    first_thread = view._validation_thread
    view._btn_validation_rerun.click()
    assert view._validation_thread is not first_thread
    view._validation_thread.wait(5000)
    qapp.processEvents()


def test_validation_panel_blocks_close_while_running(qapp, test_db):
    """A10 : même garantie que l'ancien PipelineDryRunDialog.closeEvent() — fermeture bloquée
    tant que la validation tourne (SidePanel.set_close_guard)."""
    from ui.main_window.pipelines_view import PipelinesView

    p = db.create_pipeline(name="validate-blocked-close-test")
    view = PipelinesView()
    view._on_validate_pipeline(p.id, p.name)
    _settle(qapp, view)

    # Pendant que le thread tourne, le guard doit refuser la fermeture — on le vérifie
    # directement plutôt que de dépendre d'une fenêtre de course sur un vrai thread réseau.
    assert view._side_panel._close_guard is not None

    view._validation_thread.wait(5000)
    qapp.processEvents()
    assert view._side_panel._close_guard is None   # relâché une fois le résultat reçu


def test_validation_panel_reused_as_single_instance(qapp, test_db):
    """Un seul SidePanel construit dans _build_ui, son contenu remplacé à chaque validation —
    même patron que Aujourd'hui (A9/A10 de ce lot-là)."""
    from ui.main_window.pipelines_view import PipelinesView

    p1 = db.create_pipeline(name="validate-reuse-1")
    p2 = db.create_pipeline(name="validate-reuse-2")
    view = PipelinesView()

    view._on_validate_pipeline(p1.id, p1.name)
    view._validation_thread.wait(5000)
    qapp.processEvents()
    panel_id = id(view._side_panel)

    view._on_validate_pipeline(p2.id, p2.name)
    view._validation_thread.wait(5000)
    qapp.processEvents()

    assert id(view._side_panel) == panel_id
    # removeWidget() + deleteLater() (SidePanel.set_content) ne détruit l'ancien contenu qu'au
    # prochain tour de boucle d'événements — on vérifie le contenu actuel (._content), pas un
    # findChildren() global qui peut encore voir l'ancien widget en sursis.
    text = " ".join(lbl.text() for lbl in view._side_panel._content.findChildren(QLabel))
    assert "validate-reuse-2" in text
    assert "validate-reuse-1" not in text

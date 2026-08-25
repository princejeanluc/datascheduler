"""
DataScheduler — tests/test_pipelines_view_action_menu.py
Fumée (offscreen Qt) : la colonne "Actions" de PipelinesView (chantier UX ergonomie E.3, puis
fusion des éditeurs) garde en accès direct "Exécuter"/"Ouvrir l'éditeur"/"Paramètres du
pipeline" — les 5 actions secondaires (Activer/Désactiver, Valider, Dupliquer, Exporter,
Supprimer) sont regroupées dans un QMenu attaché au bouton "⋯", et chacune reste câblée sur le
bon callback. "Éditeur graphique" a été retiré du menu — redondant avec le bouton direct.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QHeaderView, QPushButton

from database import db_manager as db


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _get_more_button_and_menu(view, row: int):
    cell = view.table.cellWidget(row, 5)
    for btn in cell.findChildren(QPushButton):
        menu = btn.menu()
        if menu is not None:
            return btn, menu
    raise AssertionError("Aucun bouton avec menu trouvé dans la cellule Actions.")


def test_actions_column_has_only_four_buttons(qapp, test_db):
    from ui.main_window.pipelines_view import PipelinesView

    db.create_pipeline(name="menu-count-test")
    view = PipelinesView()
    cell = view.table.cellWidget(0, 5)
    buttons = cell.findChildren(QPushButton)
    assert len(buttons) == 4


def test_actions_column_width_is_fixed_not_auto_shrunk(qapp, test_db):
    """Régression : la colonne Actions avait sa largeur posée via setColumnWidth() mais son mode
    de redimensionnement laissé à ResizeToContents (hérité de _configure_columns) — Qt
    recalculait alors une largeur trop étroite pour les boutons compacts, qui se chevauchaient
    visuellement dans l'exe réel. Doit rester en mode Fixed, comme la colonne "Statut" juste
    au-dessus dans le code."""
    from ui.main_window.pipelines_view import PipelinesView

    db.create_pipeline(name="fixed-width-test")
    view = PipelinesView()
    mode = view.table.horizontalHeader().sectionResizeMode(5)
    assert mode == QHeaderView.Fixed
    assert view.table.columnWidth(5) >= 140   # assez large pour 4 boutons + marges/espacements


def test_overflow_menu_contains_expected_actions(qapp, test_db):
    from ui.main_window.pipelines_view import PipelinesView

    db.create_pipeline(name="menu-actions-test")
    view = PipelinesView()
    _, menu = _get_more_button_and_menu(view, 0)
    labels = [a.text() for a in menu.actions() if not a.isSeparator()]
    assert labels == ["Désactiver", "Valider (à blanc)", "Dupliquer", "Exporter", "Supprimer"]


def test_overflow_menu_toggle_action_triggers_callback(qapp, test_db, monkeypatch):
    from ui.main_window.pipelines_view import PipelinesView

    p = db.create_pipeline(name="menu-toggle-test")
    view = PipelinesView()

    calls = []
    monkeypatch.setattr(view, "_on_toggle_pipeline", lambda i, a: calls.append((i, a)))
    _, menu = _get_more_button_and_menu(view, 0)
    menu.actions()[0].trigger()

    assert calls == [(p.id, True)]


def test_overflow_menu_offers_interrupt_only_while_running(qapp, test_db, monkeypatch):
    """Bug réel : fermer RunProgressDialog pendant l'exécution ne laissait plus aucun moyen
    direct d'interrompre un run devenu invisible (voir ui/dialogs/run_progress_dialog.py) —
    ajouté en tête de menu, uniquement quand une exécution est effectivement en cours."""
    import core.pipeline as pipeline_module
    from ui.main_window.pipelines_view import PipelinesView

    db.create_pipeline(name="menu-interrupt-idle-test")
    view = PipelinesView()
    _, menu = _get_more_button_and_menu(view, 0)
    labels = [a.text() for a in menu.actions() if not a.isSeparator()]
    assert "Interrompre l'exécution en cours" not in labels

    monkeypatch.setattr(pipeline_module, "is_pipeline_running", lambda pid: True)
    view.refresh()
    _, menu = _get_more_button_and_menu(view, 0)
    labels = [a.text() for a in menu.actions() if not a.isSeparator()]
    assert labels[0] == "Interrompre l'exécution en cours"


def test_overflow_menu_interrupt_action_triggers_callback(qapp, test_db, monkeypatch):
    import core.pipeline as pipeline_module
    from ui.main_window.pipelines_view import PipelinesView

    p = db.create_pipeline(name="menu-interrupt-trigger-test")
    monkeypatch.setattr(pipeline_module, "is_pipeline_running", lambda pid: True)
    view = PipelinesView()

    calls = []
    monkeypatch.setattr(view, "_on_interrupt_pipeline", lambda i, n: calls.append((i, n)))
    _, menu = _get_more_button_and_menu(view, 0)
    menu.actions()[0].trigger()

    assert calls == [(p.id, "menu-interrupt-trigger-test")]


def test_on_interrupt_pipeline_requests_cancel_after_confirmation(qapp, test_db, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    import core.pipeline as pipeline_module
    from ui.main_window.pipelines_view import PipelinesView

    p = db.create_pipeline(name="interrupt-confirm-test")
    view = PipelinesView()

    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.Yes))
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: None))
    calls = []
    monkeypatch.setattr(pipeline_module, "request_cancel", lambda pid: calls.append(pid))

    view._on_interrupt_pipeline(p.id, p.name)

    assert calls == [p.id]


def test_on_interrupt_pipeline_does_nothing_without_confirmation(qapp, test_db, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    import core.pipeline as pipeline_module
    from ui.main_window.pipelines_view import PipelinesView

    p = db.create_pipeline(name="interrupt-no-confirm-test")
    view = PipelinesView()

    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.No))
    calls = []
    monkeypatch.setattr(pipeline_module, "request_cancel", lambda pid: calls.append(pid))

    view._on_interrupt_pipeline(p.id, p.name)

    assert calls == []


def test_overflow_menu_delete_action_triggers_callback(qapp, test_db, monkeypatch):
    from ui.main_window.pipelines_view import PipelinesView

    p = db.create_pipeline(name="menu-delete-test")
    view = PipelinesView()

    calls = []
    monkeypatch.setattr(view, "_on_delete_pipeline", lambda i: calls.append(i))
    _, menu = _get_more_button_and_menu(view, 0)
    menu.actions()[-1].trigger()

    assert calls == [p.id]

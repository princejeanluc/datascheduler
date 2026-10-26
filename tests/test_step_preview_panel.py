"""
DataScheduler — tests/test_step_preview_panel.py
StepPreviewPanel (C7, Atelier-ajout) : aperçu "Reçoit/Produit/Connexion/Port d'erreur" d'un type
d'étape sélectionné dans le panneau "Ajouter". "Reçoit"/"Produit" viennent de core.steps
(get_step_requirements/step_produces_output_file), jamais une chaîne en dur par type — ce fichier
vérifie surtout que l'affichage suit bien ces fonctions, pas une liste figée.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from ui.graph_editor.step_preview_panel import (
    StepPreviewPanel, step_connection_label, step_fields_to_fill,
    step_receives_label, step_produces_label,
)


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_starts_with_no_type_selected_and_insert_button_disabled(qapp):
    panel = StepPreviewPanel()
    assert panel._step_type is None
    assert not panel.btn_insert.isEnabled()


def test_set_step_enables_the_insert_button_and_fills_the_title(qapp):
    panel = StepPreviewPanel()
    panel.set_step("LOCAL_COPY", {})
    assert panel.btn_insert.isEnabled()
    assert panel._title.text() == "Copie locale"


def test_set_step_none_disables_the_button_again(qapp):
    panel = StepPreviewPanel()
    panel.set_step("LOCAL_COPY", {})
    panel.set_step(None)
    assert not panel.btn_insert.isEnabled()
    assert panel._title.text() == "Sélectionnez un type d'étape"


def test_receives_reflects_requires_output_file(qapp):
    # LOCAL_COPY REQUIRES output_file (lit le fichier produit en amont) ; CONDITION n'exige rien.
    assert step_receives_label("LOCAL_COPY") == "un fichier de l'étape amont"
    assert step_receives_label("CONDITION") == "aucune donnée requise"


def test_produces_reflects_step_produces_output_file(qapp):
    assert step_produces_label("LOCAL_COPY") == "output_file"
    # GATEWAY_JOIN ne produit qu'avec artifact_source_step_key en config — {} par défaut à
    # l'aperçu (type pas encore configuré) donne donc "aucun", pas "output_file".
    assert step_produces_label("GATEWAY_JOIN") == "aucun"


def test_error_port_row_is_constant_true_for_every_known_type(qapp):
    panel = StepPreviewPanel()
    for step_type in ("LOCAL_COPY", "CONDITION", "GATEWAY_PARALLEL", "EMAIL_NOTIFY"):
        panel.set_step(step_type, {})
        assert panel._row_error.text() == "oui, comme toutes les étapes"


def test_connection_label_distinguishes_profile_based_types_from_none(qapp):
    assert step_connection_label("DB_EXTRACT") == "Profil de base de données"
    assert step_connection_label("FTP_UPLOAD") == "Profil FTP / FTPS / SFTP"
    assert step_connection_label("LOCAL_COPY") == "aucune"


def test_fields_to_fill_has_a_non_placeholder_entry_for_every_known_step_type(qapp):
    from core.steps import known_step_types
    for step_type in known_step_types():
        assert step_fields_to_fill(step_type) != "—", step_type

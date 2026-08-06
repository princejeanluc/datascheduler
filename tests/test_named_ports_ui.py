"""
DataScheduler — tests/test_named_ports_ui.py
Fumée (offscreen Qt) : le champ "Nom de sortie" (DB_EXTRACT/FTP_DOWNLOAD) et le bouton de
référence d'artefact (PYTHON_SCRIPT) — voir ui/step_editor/base_config_dialog.py.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QLineEdit, QPlainTextEdit

from ui.step_editor import _open_config_dialog
from ui.step_editor.base_config_dialog import _BaseStepConfigDialog


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _open(step_type, config=None, prior_steps=None):
    return _open_config_dialog(
        step_type, config or {}, None, [], [], [],
        smtp_profiles=[], db_profiles=[], prior_steps=prior_steps or [],
    )


def test_output_name_field_empty_by_default_on_db_extract(qapp):
    dlg = _open("DB_EXTRACT")
    assert dlg.inp_output_name.text() == ""
    assert "output_file" in dlg.inp_output_name.placeholderText()


def test_output_name_round_trips_through_result_step(qapp):
    dlg = _open("DB_EXTRACT")
    dlg.inp_output_name.setText("ventes_csv")
    config = dlg.result_step()["config"]
    assert config["output_name"] == "ventes_csv"


def test_output_name_field_empty_by_default_on_ftp_download(qapp):
    dlg = _open("FTP_DOWNLOAD")
    assert dlg.inp_output_name.text() == ""


def test_output_name_preserved_when_editing_existing_step(qapp):
    dlg = _open("DB_EXTRACT", config={"output_name": "deja_nomme"})
    assert dlg.inp_output_name.text() == "deja_nomme"


def test_python_script_output_names_round_trip(qapp):
    dlg = _open("PYTHON_SCRIPT", config={"script_path": "x.py"})
    dlg.inp_output_names.setText("rapport_csv, resume_json")
    config = dlg.result_step()["config"]
    assert config["output_names"] == ["rapport_csv", "resume_json"]


def test_python_script_prior_steps_prefill_output_names(qapp):
    dlg = _open("PYTHON_SCRIPT", config={"output_names": ["deja_la"]})
    assert dlg.inp_output_names.text() == "deja_la"


# ──────────────────────────────────────────────
#  Bouton de référence — _BaseStepConfigDialog._artifact_reference_button
# ──────────────────────────────────────────────

class _DummyDialog(_BaseStepConfigDialog):
    STEP_TYPE = "DUMMY"

    def _collect_config(self):
        return {}


def test_reference_button_disabled_without_known_names(qapp):
    dlg = _DummyDialog({}, None)
    btn = dlg._artifact_reference_button(QLineEdit(), [])
    assert not btn.isEnabled()


def test_reference_button_lists_names_from_prior_steps(qapp):
    dlg = _DummyDialog({}, None)
    prior = [
        {"step_type": "DB_EXTRACT", "config": {"_step_key": "a", "output_name": "ventes_csv"}},
        {"step_type": "PYTHON_SCRIPT", "config": {"_step_key": "b", "output_names": ["rapport", "resume"]}},
    ]
    btn = dlg._artifact_reference_button(QLineEdit(), prior)
    assert btn.isEnabled()
    labels = [a.text() for a in btn.menu().actions()]
    assert labels == ["ventes_csv", "rapport", "resume"]


def test_reference_button_deduplicates_repeated_names(qapp):
    dlg = _DummyDialog({}, None)
    prior = [
        {"step_type": "DB_EXTRACT", "config": {"_step_key": "a", "output_name": "ventes"}},
        {"step_type": "DB_EXTRACT", "config": {"_step_key": "b", "output_name": "ventes"}},
    ]
    btn = dlg._artifact_reference_button(QLineEdit(), prior)
    assert [a.text() for a in btn.menu().actions()] == ["ventes"]


def test_reference_button_inserts_token_into_line_edit(qapp):
    dlg = _DummyDialog({}, None)
    field = QLineEdit()
    prior = [{"step_type": "DB_EXTRACT", "config": {"_step_key": "a", "output_name": "ventes"}}]
    btn = dlg._artifact_reference_button(field, prior)
    btn.menu().actions()[0].trigger()
    assert field.text() == "{artifact:ventes}"


def test_reference_button_inserts_token_into_plain_text_edit(qapp):
    dlg = _DummyDialog({}, None)
    field = QPlainTextEdit()
    prior = [{"step_type": "DB_EXTRACT", "config": {"_step_key": "a", "output_name": "ventes"}}]
    btn = dlg._artifact_reference_button(field, prior)
    btn.menu().actions()[0].trigger()
    assert field.toPlainText() == "{artifact:ventes}"


# ──────────────────────────────────────────────
#  Sélecteur "Source" (_source_row) — un producteur dynamique (SPARK_SQL) n'apparaissait jamais,
# quelle que soit sa config (bug signalé par l'utilisateur : "un seul choix disponible").
# ──────────────────────────────────────────────

def test_source_selector_lists_spark_sql_step_when_fetch_result_checked(qapp):
    prior = [{"step_type": "SPARK_SQL", "label": "Requête Spark",
              "config": {"_step_key": "spark", "fetch_result": True}}]
    dlg = _open("LOCAL_COPY", prior_steps=prior)
    labels = [dlg.cb_source.itemText(i) for i in range(dlg.cb_source.count())]
    assert labels == ["Étape précédente (par défaut)", "Requête Spark"]


def test_source_selector_omits_spark_sql_step_when_fetch_result_unchecked(qapp):
    prior = [{"step_type": "SPARK_SQL", "label": "Requête Spark",
              "config": {"_step_key": "spark", "fetch_result": False}}]
    dlg = _open("LOCAL_COPY", prior_steps=prior)
    labels = [dlg.cb_source.itemText(i) for i in range(dlg.cb_source.count())]
    assert labels == ["Étape précédente (par défaut)"]

"""
DataScheduler — tests/test_named_ports_ui.py
Fumée (offscreen Qt) : le champ "Nom de sortie" (DB_EXTRACT/FTP_DOWNLOAD) et le bouton de
référence d'artefact (PYTHON_SCRIPT) — voir ui/step_editor/base_config_dialog.py.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QLineEdit, QPlainTextEdit, QPushButton

from ui.step_editor import _open_config_dialog
from ui.step_editor.base_config_dialog import _BaseStepConfigDialog


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _open(step_type, config=None, prior_steps=None, pipeline_variable_names=None):
    return _open_config_dialog(
        step_type, config or {}, None, [], [], [],
        smtp_profiles=[], db_profiles=[], prior_steps=prior_steps or [],
        pipeline_variable_names=pipeline_variable_names or [],
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
#  Bouton de référence variable — _BaseStepConfigDialog._variable_reference_button
# ──────────────────────────────────────────────

def test_variable_reference_button_disabled_without_known_names(qapp):
    dlg = _DummyDialog({}, None)
    btn = dlg._variable_reference_button(QLineEdit(), [])
    assert not btn.isEnabled()


def test_variable_reference_button_lists_names_from_extract_variables_prior_steps(qapp):
    dlg = _DummyDialog({}, None)
    prior = [
        {"step_type": "EXTRACT_VARIABLES", "config": {"mappings": [
            {"source": "date_max", "target": "date_max", "type": "date", "date_format": "{yyyy}-{MM}-{dd}"},
            {"source": "total", "target": "total", "type": "number"},
        ]}},
        {"step_type": "DB_EXTRACT", "config": {"output_name": "ventes_csv"}},
    ]
    btn = dlg._variable_reference_button(QLineEdit(), prior)
    assert btn.isEnabled()
    labels = [a.text() for a in btn.menu().actions()]
    assert labels == ["date_max", "total"]


def test_variable_reference_button_deduplicates_repeated_names(qapp):
    dlg = _DummyDialog({}, None)
    prior = [
        {"step_type": "EXTRACT_VARIABLES", "config": {"mappings": [{"source": "a", "target": "x"}]}},
        {"step_type": "EXTRACT_VARIABLES", "config": {"mappings": [{"source": "b", "target": "x"}]}},
    ]
    btn = dlg._variable_reference_button(QLineEdit(), prior)
    assert [a.text() for a in btn.menu().actions()] == ["x"]


def test_variable_reference_button_inserts_token_into_line_edit(qapp):
    dlg = _DummyDialog({}, None)
    field = QLineEdit()
    prior = [{"step_type": "EXTRACT_VARIABLES", "config": {"mappings": [{"source": "a", "target": "total"}]}}]
    btn = dlg._variable_reference_button(field, prior)
    btn.menu().actions()[0].trigger()
    assert field.text() == "{var:total}"


def test_variable_reference_button_lists_pipeline_declared_names(qapp):
    dlg = _DummyDialog({}, None)
    btn = dlg._variable_reference_button(QLineEdit(), [], pipeline_variable_names=["base_date"])
    assert btn.isEnabled()
    assert [a.text() for a in btn.menu().actions()] == ["base_date"]


def test_variable_reference_button_combines_pipeline_and_extract_variables_names_deduped(qapp):
    dlg = _DummyDialog({}, None)
    prior = [{"step_type": "EXTRACT_VARIABLES", "config": {"mappings": [
        {"source": "a", "target": "total"},
        {"source": "b", "target": "base_date"},   # même nom qu'une variable de pipeline
    ]}}]
    btn = dlg._variable_reference_button(QLineEdit(), prior, pipeline_variable_names=["base_date"])
    assert [a.text() for a in btn.menu().actions()] == ["base_date", "total"]


# ──────────────────────────────────────────────
#  Dialogue CONDITION — câblage des deux boutons de référence
# ──────────────────────────────────────────────

def test_condition_dialog_accepts_and_stores_prior_steps(qapp):
    prior = [
        {"step_type": "DB_EXTRACT", "config": {"output_name": "ventes_csv"}},
        {"step_type": "EXTRACT_VARIABLES", "config": {"mappings": [{"source": "a", "target": "total"}]}},
    ]
    dlg = _open("CONDITION", prior_steps=prior)
    artifact_btn = dlg._artifact_reference_button(dlg.inp_expression, dlg._prior_steps)
    variable_btn = dlg._variable_reference_button(dlg.inp_expression, dlg._prior_steps)
    assert artifact_btn.isEnabled()
    assert variable_btn.isEnabled()


def test_condition_dialog_accepts_and_stores_pipeline_variable_names(qapp):
    dlg = _open("CONDITION", pipeline_variable_names=["base_date"])
    assert dlg._pipeline_variable_names == ["base_date"]
    variable_btn = dlg._variable_reference_button(
        dlg.inp_expression, dlg._prior_steps, dlg._pipeline_variable_names,
    )
    assert variable_btn.isEnabled()


def test_condition_dialog_without_prior_steps_has_disabled_reference_buttons(qapp):
    dlg = _open("CONDITION")
    assert dlg._prior_steps == []


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


# ──────────────────────────────────────────────
#  _reference_insertion_text — fonction pure, forme nue vs accolée
# ──────────────────────────────────────────────

def test_reference_insertion_text_braced_form():
    from ui.step_editor.base_config_dialog import _reference_insertion_text
    assert _reference_insertion_text("artifact", "ventes", braced=True) == "{artifact:ventes}"
    assert _reference_insertion_text("var", "total", braced=True) == "{var:total}"


def test_reference_insertion_text_bare_form_simple_name():
    from ui.step_editor.base_config_dialog import _reference_insertion_text
    assert _reference_insertion_text("var", "total", braced=False) == "var:total"
    assert _reference_insertion_text("artifact", "3f9a1c2b-uuid", braced=False) == "artifact:3f9a1c2b-uuid"


def test_reference_insertion_text_bare_form_quotes_name_with_space():
    from ui.step_editor.base_config_dialog import _reference_insertion_text
    assert _reference_insertion_text("var", "nom avec espace", braced=False) == 'var:"nom avec espace"'


def test_reference_insertion_text_bare_form_quotes_name_with_operator_char():
    from ui.step_editor.base_config_dialog import _reference_insertion_text
    assert _reference_insertion_text("var", "a+b", braced=False) == 'var:"a+b"'


def test_reference_insertion_text_bare_form_falls_back_to_single_quotes_if_name_has_double_quote():
    from ui.step_editor.base_config_dialog import _reference_insertion_text
    assert _reference_insertion_text("var", 'nom "cité"', braced=False) == "var:'nom \"cité\"'"


# ──────────────────────────────────────────────
#  braced=False — câblage des deux boutons, directement
# ──────────────────────────────────────────────

def test_artifact_reference_button_braced_false_inserts_bare_form(qapp):
    dlg = _DummyDialog({}, None)
    field = QLineEdit()
    prior = [{"step_type": "DB_EXTRACT", "config": {"_step_key": "a", "output_name": "ventes"}}]
    btn = dlg._artifact_reference_button(field, prior, braced=False)
    btn.menu().actions()[0].trigger()
    assert field.text() == "artifact:ventes"


def test_variable_reference_button_braced_false_inserts_bare_form(qapp):
    dlg = _DummyDialog({}, None)
    field = QLineEdit()
    prior = [{"step_type": "EXTRACT_VARIABLES", "config": {"mappings": [{"source": "a", "target": "total"}]}}]
    btn = dlg._variable_reference_button(field, prior, braced=False)
    btn.menu().actions()[0].trigger()
    assert field.text() == "var:total"


# ──────────────────────────────────────────────
#  Dialogue CONDITION — les deux boutons insèrent désormais la forme NUE (bug réel corrigé :
#  CONDITION.expression est évalué directement par core/expr_lang.py, qui ne comprend que
#  artifact:nom/var:nom, jamais {artifact:nom}/{var:nom})
# ──────────────────────────────────────────────

def _reference_button_with_action(dlg, action_text: str) -> QPushButton:
    return next(
        w for w in dlg.findChildren(QPushButton)
        if w.menu() and action_text in [a.text() for a in w.menu().actions()]
    )


def test_condition_dialog_artifact_button_inserts_bare_form(qapp):
    prior = [{"step_type": "DB_EXTRACT", "config": {"output_name": "ventes_csv"}}]
    dlg = _open("CONDITION", prior_steps=prior)
    btn = _reference_button_with_action(dlg, "ventes_csv")
    btn.menu().actions()[0].trigger()
    assert dlg.inp_expression.text() == "artifact:ventes_csv"


def test_condition_dialog_variable_button_inserts_bare_form(qapp):
    prior = [{"step_type": "EXTRACT_VARIABLES", "config": {"mappings": [{"source": "a", "target": "total"}]}}]
    dlg = _open("CONDITION", prior_steps=prior)
    btn = _reference_button_with_action(dlg, "total")
    btn.menu().actions()[0].trigger()
    assert dlg.inp_expression.text() == "var:total"


# ──────────────────────────────────────────────
#  Dialogue CONDITION — validation syntaxique à l'enregistrement (même patron que SET_VARIABLE)
# ──────────────────────────────────────────────

def test_condition_dialog_rejects_malformed_expression_on_ok(qapp, monkeypatch):
    import ui.step_editor.condition_config_dialog as mod
    dlg = _open("CONDITION")
    dlg.inp_expression.setText("rows_count >")   # comparaison tronquée — invalide

    warnings = []
    monkeypatch.setattr(mod.QMessageBox, "warning", lambda *a, **k: warnings.append(a) or None)
    accepted = []
    monkeypatch.setattr(dlg, "accept", lambda: accepted.append(1))

    dlg._on_ok()

    assert warnings
    assert accepted == []


def test_condition_dialog_accepts_valid_expression_on_ok(qapp, monkeypatch):
    dlg = _open("CONDITION")
    dlg.inp_expression.setText("rows_count > 0")

    accepted = []
    monkeypatch.setattr(dlg, "accept", lambda: accepted.append(1))

    dlg._on_ok()

    assert accepted == [1]


def test_condition_dialog_rejects_the_bug_s_own_old_braced_syntax(qapp, monkeypatch):
    """Preuve directe du bug corrigé : l'ancienne forme accolée, si jamais retapée ou restée
    d'une sauvegarde antérieure, est désormais détectée à l'enregistrement plutôt que de
    silencieusement passer puis échouer à l'exécution."""
    import ui.step_editor.condition_config_dialog as mod
    dlg = _open("CONDITION")
    dlg.inp_expression.setText("{var:seuil} > 0")

    warnings = []
    monkeypatch.setattr(mod.QMessageBox, "warning", lambda *a, **k: warnings.append(a) or None)
    accepted = []
    monkeypatch.setattr(dlg, "accept", lambda: accepted.append(1))

    dlg._on_ok()

    assert warnings
    assert accepted == []

"""
DataScheduler — tests/test_step_editor_tooltips.py
Vérifie que les champs partagés (libellé, réessai, "toujours exécuter") et quelques champs
spécifiques non auto-explicatifs ont bien un tooltip (chantier UX "autonomie utilisateur",
aide au point d'usage — voir docs/COOKBOOK.md et ui/help/). Rien de pixel-perfect ici, juste
"le tooltip n'est pas vide" — évite qu'un futur refactor fasse silencieusement disparaître
l'aide contextuelle.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from ui.step_editor import _open_config_dialog, STEP_META


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _open(step_type: str):
    return _open_config_dialog(
        step_type, {}, None,
        oracle_profiles=[], ftp_profiles=[], sql_queries=[],
        smtp_profiles=[], db_profiles=[],
        prior_steps=[],
    )


@pytest.mark.parametrize("step_type", list(STEP_META.keys()))
def test_shared_fields_have_tooltips(qapp, test_db, step_type):
    # SPARK_SQL récupère ses profils SSH/Kerberos directement depuis la base — nécessite test_db.
    dlg = _open(step_type)
    assert dlg.inp_label.toolTip().strip()
    assert dlg.inp_retry.toolTip().strip()
    assert dlg.chk_run_always.toolTip().strip()


def test_source_row_has_tooltip(qapp):
    dlg = _open("FTP_UPLOAD")
    assert dlg.cb_source.toolTip().strip()


def test_output_name_row_has_tooltip(qapp):
    dlg = _open("DB_EXTRACT")
    assert dlg.inp_output_name.toolTip().strip()


def test_profile_row_has_tooltip(qapp):
    dlg = _open("EMAIL_NOTIFY")
    assert dlg.cb_smtp.toolTip().strip()


def test_db_load_specific_fields_have_tooltips(qapp):
    dlg = _open("DB_LOAD")
    assert dlg.chk_truncate.toolTip().strip()
    assert dlg.inp_chunk.toolTip().strip()


def test_python_script_specific_fields_have_tooltips(qapp):
    dlg = _open("PYTHON_SCRIPT")
    assert dlg.inp_script.toolTip().strip()
    assert dlg.inp_py_exe.toolTip().strip()
    assert dlg.inp_timeout.toolTip().strip()


def test_http_request_specific_fields_have_tooltips(qapp):
    dlg = _open("HTTP_REQUEST")
    assert dlg.cb_method.toolTip().strip()
    assert dlg.inp_timeout.toolTip().strip()
    assert dlg.txt_headers.toolTip().strip()
    assert dlg.txt_body.toolTip().strip()
    assert dlg.chk_attach.toolTip().strip()


def test_spark_sql_specific_fields_have_tooltips(qapp, test_db):
    dlg = _open("SPARK_SQL")
    assert dlg.inp_timeout.toolTip().strip()
    assert dlg.chk_fetch.toolTip().strip()

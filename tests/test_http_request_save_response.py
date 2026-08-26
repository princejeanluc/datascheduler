"""
DataScheduler — tests/test_http_request_save_response.py
Dialogue de configuration HTTP_REQUEST — nouvelle case "Sauvegarder la réponse" (voir
core/steps/http_request.py pour la logique d'exécution). Verrouille le round-trip
collect/prefill, la valeur par défaut (décochée — zéro changement pour un pipeline existant) et
la visibilité conditionnelle du champ "Nom de sortie".
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from ui.step_editor.http_request_config_dialog import _HttpRequestConfigDialog


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_save_response_unchecked_by_default(qapp):
    dlg = _HttpRequestConfigDialog({}, None, "test-label")
    assert not dlg.chk_save_response.isChecked()
    assert dlg._collect_config()["save_response"] is False


def test_output_name_row_hidden_until_checked(qapp):
    dlg = _HttpRequestConfigDialog({}, None, "test-label")
    assert dlg.inp_output_name.isHidden()

    dlg.chk_save_response.setChecked(True)
    assert not dlg.inp_output_name.isHidden()

    dlg.chk_save_response.setChecked(False)
    assert dlg.inp_output_name.isHidden()


def test_collect_config_includes_save_response_and_output_name(qapp):
    dlg = _HttpRequestConfigDialog({}, None, "test-label")
    dlg.inp_url.setText("https://example.test/data")
    dlg.chk_save_response.setChecked(True)
    dlg.inp_output_name.setText("api_result")

    config = dlg._collect_config()

    assert config["save_response"] is True
    assert config["output_name"] == "api_result"


def test_prefill_restores_save_response_and_output_name(qapp):
    dlg = _HttpRequestConfigDialog(
        {"url_tpl": "https://example.test/data", "save_response": True,
         "output_name": "api_result"},
        None, "test-label",
    )
    assert dlg.chk_save_response.isChecked()
    assert dlg.inp_output_name.text() == "api_result"

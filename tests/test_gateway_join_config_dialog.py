"""
DataScheduler — tests/test_gateway_join_config_dialog.py
Dialogue GATEWAY_JOIN (chantier Gateway) : mode de jonction (ET/OU) et désignation d'artefact —
via _source_row() étendu (empty_label/tooltip personnalisés, ui/step_editor/base_config_dialog.py)
plutôt qu'un mécanisme neuf.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from ui.step_editor.gateway_join_config_dialog import _GatewayJoinConfigDialog


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_defaults_to_or_mode_and_no_designation(qapp):
    dlg = _GatewayJoinConfigDialog({}, None, "")
    assert dlg.cb_join_mode.currentData() == "OR"
    assert dlg.cb_source.currentData() is None
    step = dlg.result_step()
    assert step["config"]["join_mode"] == "OR"
    assert step["config"]["artifact_source_step_key"] is None


def test_prefill_restores_and_mode_and_designated_source(qapp):
    prior_steps = [
        {"step_type": "DB_EXTRACT", "label": "Branche A", "config": {"_step_key": "a"}},
        {"step_type": "FTP_DOWNLOAD", "label": "Branche B", "config": {"_step_key": "b"}},
    ]
    dlg = _GatewayJoinConfigDialog(
        {"join_mode": "AND", "artifact_source_step_key": "b"}, None, "",
        prior_steps=prior_steps,
    )
    assert dlg.cb_join_mode.currentData() == "AND"
    assert dlg.cb_source.currentData() == "b"


def test_source_combo_only_lists_producing_prior_steps(qapp):
    prior_steps = [
        {"step_type": "DB_EXTRACT", "label": "Producteur", "config": {"_step_key": "a"}},
        {"step_type": "EMAIL_NOTIFY", "label": "Ne produit rien", "config": {"_step_key": "b"}},
    ]
    dlg = _GatewayJoinConfigDialog({}, None, "", prior_steps=prior_steps)
    labels = [dlg.cb_source.itemText(i) for i in range(dlg.cb_source.count())]
    assert "Producteur" in labels
    assert "Ne produit rien" not in labels


def test_collect_config_round_trips_and_mode(qapp):
    dlg = _GatewayJoinConfigDialog({}, None, "")
    idx = dlg.cb_join_mode.findData("AND")
    dlg.cb_join_mode.setCurrentIndex(idx)
    assert dlg.result_step()["config"]["join_mode"] == "AND"

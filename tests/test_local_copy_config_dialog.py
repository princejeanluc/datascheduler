"""
DataScheduler — tests/test_local_copy_config_dialog.py
Chantier identité visuelle : LOCAL_COPY gagne un champ "Nom de sortie" (comme les autres
producteurs, ex. db_extract_config_dialog.py) maintenant qu'il republie ctx.output_file.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from ui.step_editor.local_copy_config_dialog import _LocalCopyConfigDialog


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_output_name_prefill_and_collect_round_trip(qapp):
    dlg = _LocalCopyConfigDialog(
        {"dest_dir": "C:/backup", "output_name": "copie_ventes"}, None, "",
    )
    assert dlg.inp_output_name.text() == "copie_ventes"
    assert dlg.result_step()["config"]["output_name"] == "copie_ventes"


def test_output_name_defaults_to_empty(qapp):
    dlg = _LocalCopyConfigDialog({"dest_dir": "C:/backup"}, None, "")
    assert dlg.inp_output_name.text() == ""
    assert dlg.result_step()["config"]["output_name"] == ""

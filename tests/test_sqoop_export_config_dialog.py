"""
DataScheduler — tests/test_sqoop_export_config_dialog.py
Vérifie que le dialogue SQOOP_EXPORT prend bien en charge le champ timeout_s (chantier J.1,
mergé après la conception initiale de SQOOP_EXPORT — cette étape doit en bénéficier comme tout
autre type d'étape, sans quoi éditer une étape avec un délai déjà configuré l'aurait
silencieusement réinitialisé à 0 en rouvrant le dialogue).
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_prefill_and_collect_roundtrip_timeout_s(qapp, test_db):
    from ui.step_editor.sqoop_export_config_dialog import _SqoopExportConfigDialog

    dlg = _SqoopExportConfigDialog(
        {"timeout_s": 120, "edge_profile_id": None, "kerberos_profile_id": None,
         "oracle_profile_id": None, "hcatalog_database": "", "hcatalog_table": "",
         "oracle_table": ""},
        None, "", timeout_s=120,
    )
    assert dlg.inp_timeout.value() == 120
    assert dlg.result_step()["timeout_s"] == 120

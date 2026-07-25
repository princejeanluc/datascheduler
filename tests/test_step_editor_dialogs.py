"""
DataScheduler — tests/test_step_editor_dialogs.py
Fumée : chaque type d'étape doit pouvoir ouvrir son dialogue de configuration via
_open_config_dialog() avec le kwargs partagé complet, sans lever d'erreur — évite les
régressions du type "un dialogue a une signature explicite qui ne tolère pas un
nouveau paramètre ajouté au dict partagé" (voir mémoire projet, chantier 3).

Nécessite QT_QPA_PLATFORM=offscreen (fixé ici, avant tout import PySide6) pour
tourner sans affichage.
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


@pytest.mark.parametrize("step_type", list(STEP_META.keys()))
def test_config_dialog_opens_for_every_step_type(qapp, step_type):
    dlg = _open_config_dialog(
        step_type, {}, None,
        oracle_profiles=[], ftp_profiles=[], sql_queries=[],
        smtp_profiles=[], db_profiles=[],
        prior_steps=[],
    )
    assert dlg is not None

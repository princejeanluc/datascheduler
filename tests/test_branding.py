"""
DataScheduler — tests/test_branding.py
Vérifie ui/branding.py::app_icon() — l'icône embarquée en base64 (voir "est-ce qu'en ouvrant
l'application on voit le logo ?" : l'icône de l'exe, DataScheduler.spec, ne suffit pas, Qt ne la
reprend pas automatiquement pour la fenêtre affichée — QApplication.setWindowIcon() est requis).
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_app_icon_is_not_null(qapp):
    from ui.branding import app_icon

    icon = app_icon()
    assert not icon.isNull()


def test_app_icon_pixmap_has_expected_size(qapp):
    from ui.branding import app_icon

    icon = app_icon()
    pixmap = icon.pixmap(128, 128)
    assert pixmap.width() == 128
    assert pixmap.height() == 128


def test_base64_payload_decodes_to_valid_png():
    import base64
    from ui.branding import _ICON_PNG_B64

    data = base64.b64decode(_ICON_PNG_B64)
    assert data[:8] == b"\x89PNG\r\n\x1a\n"   # signature PNG

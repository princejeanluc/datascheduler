"""
DataScheduler — tests/test_fonts.py
Vérifie ui/fonts.py (chantier identité visuelle) : les 7 polices embarquées (IBM Plex Sans,
JetBrains Mono) décodent en TTF valides et s'enregistrent auprès de Qt sans jamais lever — un
échec d'enregistrement doit être absorbé silencieusement (voir GLOBAL_STYLE/DIALOG_STYLE qui
gardent toujours une chaîne de repli vers Segoe UI/Consolas).
"""

import base64
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_all_embedded_fonts_decode_to_valid_ttf():
    from ui.fonts import _ALL_FONTS_B64

    assert len(_ALL_FONTS_B64) == 7
    for encoded in _ALL_FONTS_B64:
        data = base64.b64decode(encoded)
        assert data[:4] in (b"\x00\x01\x00\x00", b"OTTO", b"true")  # signatures TTF/OTF valides


def test_register_app_fonts_never_raises(qapp):
    from ui.fonts import register_app_fonts

    register_app_fonts()  # ne doit lever aucune exception


def test_register_app_fonts_makes_families_available(qapp):
    from PySide6.QtGui import QFontDatabase

    from ui.fonts import register_app_fonts
    from ui.styles import FONT_UI, FONT_MONO

    register_app_fonts()
    families = QFontDatabase.families()
    assert FONT_UI in families
    assert FONT_MONO in families

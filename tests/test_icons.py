"""
DataScheduler — tests/test_icons.py
Vérifie ui/icons.py (chantier identité visuelle, phase 2) : les tracés SVG embarqués (logo +
icônes de navigation) sont valides et se rendent en QIcon non nulles.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtCore import QByteArray
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_all_nav_icon_bodies_produce_valid_svg():
    from ui.icons import _NAV_ICON_BODIES, _SVG_WRAPPER

    assert len(_NAV_ICON_BODIES) == 8   # +1 "ressources" (chantier suivi des ressources)
    for key, body in _NAV_ICON_BODIES.items():
        svg = _SVG_WRAPPER.format(color="#ffffff", body=body.format(color="#ffffff"))
        renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
        assert renderer.isValid(), f"SVG invalide pour l'icône '{key}'"


def test_logo_svg_is_valid():
    from ui.icons import _LOGO_SVG

    renderer = QSvgRenderer(QByteArray(_LOGO_SVG.format(color="#FF7900").encode("utf-8")))
    assert renderer.isValid()


def test_nav_icon_returns_non_null_icon_for_every_key(qapp):
    from ui.icons import nav_icon, _NAV_ICON_BODIES

    for key in _NAV_ICON_BODIES:
        icon = nav_icon(key, "#f2efeb")
        assert not icon.isNull()


def test_logo_icon_returns_non_null_icon(qapp):
    from ui.icons import logo_icon

    icon = logo_icon("#FF7900")
    assert not icon.isNull()


def test_nav_icon_raises_key_error_for_unknown_key(qapp):
    from ui.icons import nav_icon

    with pytest.raises(KeyError):
        nav_icon("inexistant", "#ffffff")

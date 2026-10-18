"""
DataScheduler — tests/test_capture_views.py
Refonte, lot 0a : scripts/capture_views.py doit s'importer et produire un PNG par vue
enregistrée, sans toucher à la vraie base applicative.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import sys
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_registry_is_not_empty(qapp):
    from scripts.capture_views import REGISTRY
    assert len(REGISTRY) >= 1


def test_capture_all_produces_one_png_per_registered_view(qapp, tmp_path, test_db):
    """capture_all() pose GLOBAL_STYLE sur l'application (même patron que window.py::run()) —
    remis à "" après coup, pour ne pas fuiter sur les tests suivants de la même session Qt
    (même précaution que test_pipeline_settings_dialog.py)."""
    from scripts.capture_views import capture_all, REGISTRY

    try:
        produced = capture_all(tmp_path)
    finally:
        qapp.setStyleSheet("")

    assert len(produced) == len(REGISTRY)
    for path in produced:
        assert path.exists()
        assert path.stat().st_size > 0

"""
DataScheduler — tests/conftest.py
Fixtures partagées. La règle d'or (voir docs/COOKBOOK.md, "tester sans polluer vos
vraies données") : db.init_db() sans argument pointe vers la vraie base applicative —
un test ne doit jamais l'appeler sans lui passer un chemin jetable explicite.
"""

import pytest

from database import db_manager as db


@pytest.fixture
def test_db(tmp_path):
    """Base SQLite jetable, isolée de %APPDATA%/DataScheduler/datascheduler.db."""
    db_path = tmp_path / "test.db"
    db.init_db(db_path)
    yield db
    db._engine = None
    db._SessionFactory = None

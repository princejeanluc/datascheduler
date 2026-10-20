"""
DataScheduler — tests/test_connection_health.py
Vérifie le bilan de santé des connexions (chantier UX fiabilité, D.2) : migration idempotente sur
une base legacy, persistance de record_profile_test_result() sur les 4 catégories, et le
dialogue ConnectionHealthDialog (offscreen Qt).
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from sqlalchemy import create_engine, text

import pytest
from PySide6.QtWidgets import QApplication, QLabel

from database import db_manager as db


def _cell_texts(table, row, col) -> list:
    """Libellés texte d'une cellule composite (refonte, lot A-Connexions : icône de type,
    `_status_dot_row`) — exclut le point coloré (un QLabel vide, juste stylé en cercle)."""
    widget = table.cellWidget(row, col)
    return [lbl.text() for lbl in widget.findChildren(QLabel) if lbl.text()]


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


# ──────────────────────────────────────────────
#  Migration
# ──────────────────────────────────────────────

def test_migrate_adds_health_columns_on_legacy_db(tmp_path):
    db_path = tmp_path / "legacy_health.db"
    engine = create_engine(f"sqlite:///{db_path}")

    with engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE oracle_profiles (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                uuid         VARCHAR(36) UNIQUE,
                name         VARCHAR(100) NOT NULL UNIQUE,
                host         VARCHAR(255) NOT NULL,
                port         INTEGER NOT NULL DEFAULT 1521,
                service_name VARCHAR(100),
                sid          VARCHAR(100),
                username     VARCHAR(100) NOT NULL,
                password     VARCHAR(255) NOT NULL,
                auth_mode    VARCHAR(20) NOT NULL DEFAULT 'DEFAULT',
                created_at   DATETIME,
                updated_at   DATETIME
            )
        """))
        conn.execute(text(
            "INSERT INTO oracle_profiles (uuid, name, host, port, username, password, auth_mode) "
            "VALUES ('u1', 'LEGACY', 'h', 1521, 'u', 'p', 'DEFAULT')"
        ))
        conn.commit()
    engine.dispose()

    db.init_db(db_path)
    cols = {r[1] for r in create_engine(f"sqlite:///{db_path}").connect()
            .execute(text("PRAGMA table_info(oracle_profiles)")).fetchall()}
    assert "last_tested_at" in cols
    assert "last_test_success" in cols

    profile = db.get_oracle_profiles()[0]
    assert profile.last_tested_at is None
    assert profile.last_test_success is None

    # Idempotence : un second démarrage ne doit pas planter.
    db.init_db(db_path)

    db._engine = None
    db._SessionFactory = None


# ──────────────────────────────────────────────
#  record_profile_test_result
# ──────────────────────────────────────────────

@pytest.mark.parametrize("category, create_fn, kwargs", [
    ("oracle", "create_oracle_profile", dict(name="ORA1", host="h", port=1521, username="u", password="p", service_name="S")),
    ("ftp", "create_ftp_profile", dict(name="FTP1", host="h", port=21, username="u", password="p")),
    ("smtp", "create_smtp_profile", dict(name="SMTP1", host="h", port=587, from_address="a@b.c")),
    ("database", "create_database_profile", dict(name="DBP1", db_type="MYSQL", host="h", port=3306, username="u", password="p")),
])
def test_record_profile_test_result_persists_for_each_category(test_db, category, create_fn, kwargs):
    profile = getattr(db, create_fn)(**kwargs)
    assert profile.last_tested_at is None

    db.record_profile_test_result(category, profile.id, True)
    getter = {
        "oracle": db.get_oracle_profile, "ftp": db.get_ftp_profile,
        "smtp": db.get_smtp_profile, "database": db.get_database_profile,
    }[category]
    refreshed = getter(profile.id)
    assert refreshed.last_test_success is True
    assert refreshed.last_tested_at is not None

    db.record_profile_test_result(category, profile.id, False)
    assert getter(profile.id).last_test_success is False


def test_record_profile_test_result_unknown_category_is_noop(test_db):
    p = db.create_oracle_profile(name="ORA2", host="h", port=1521, username="u", password="p", service_name="S")
    db.record_profile_test_result("unknown", p.id, True)   # ne doit pas lever


def test_record_profile_test_result_missing_profile_is_noop(test_db):
    db.record_profile_test_result("oracle", 999999, True)   # ne doit pas lever


# ──────────────────────────────────────────────
#  ConnectionHealthDialog (offscreen Qt)
# ──────────────────────────────────────────────

def test_dialog_lists_all_profile_categories(qapp, test_db):
    from ui.dialogs import ConnectionHealthDialog

    db.create_oracle_profile(name="ORA1", host="h", port=1521, username="u", password="p", service_name="S")
    db.create_ftp_profile(name="FTP1", host="h", port=21, username="u", password="p")
    db.create_smtp_profile(name="SMTP1", host="h", port=587, from_address="a@b.c")
    db.create_database_profile(name="DBP1", db_type="MYSQL", host="h", port=3306, username="u", password="p")

    dlg = ConnectionHealthDialog(None)
    assert dlg.table.rowCount() == 4
    # A10 : la "Catégorie" en texte disparaît au profit d'une icône de type (colonne 0) ;
    # vérifiée indirectement via le set de catégories collectées, pas une colonne affichée.
    categories = {row["category"] for row in dlg._rows}
    assert categories == {"oracle", "ftp", "smtp", "database"}
    for i in range(4):
        assert _cell_texts(dlg.table, i, 2) == ["Jamais testé"]


def test_dialog_shows_type_icon_instead_of_category_text(qapp, test_db):
    """A10 : la colonne 0 est une icône de type (même dictionnaire que les tableaux de
    ConnectionsView et les 7 dialogues de profil), pas un texte de catégorie."""
    from ui.dialogs import ConnectionHealthDialog

    db.create_ftp_profile(name="FTP1", host="h", port=21, username="u", password="p")

    dlg = ConnectionHealthDialog(None)
    icon_widget = dlg.table.cellWidget(0, 0)
    assert icon_widget is not None
    assert not icon_widget.pixmap().isNull()


def test_dialog_shows_message_in_clear_text_and_relative_time(qapp, test_db):
    """A10 : le message n'est plus réservé à l'infobulle, et l'heure passe en relatif
    (`fmt_relative`), pas l'horodatage absolu d'avant ce lot."""
    from datetime import datetime, timedelta

    from ui.dialogs import ConnectionHealthDialog

    db.create_ftp_profile(name="FTP-health", host="h", port=21, username="u", password="p")

    dlg = ConnectionHealthDialog(None)
    dlg._render_row(0, datetime.utcnow() - timedelta(minutes=5), True, "dossier accessible")

    assert dlg.table.item(0, 3).text() == "dossier accessible"
    assert "il y a" in dlg.table.item(0, 4).text()


def test_dialog_test_all_updates_rows_and_persists(qapp, test_db):
    from ui.dialogs import ConnectionHealthDialog

    profile = db.create_oracle_profile(
        name="ORA-health", host="127.0.0.1", port=1521, username="u", password="p", service_name="S",
    )

    dlg = ConnectionHealthDialog(None)
    dlg._on_test_all()
    assert dlg._thread.wait(15000)
    qapp.processEvents()

    assert _cell_texts(dlg.table, 0, 2) != ["Jamais testé"]
    assert _cell_texts(dlg.table, 0, 2)[0] in ("OK", "Échec")

    refreshed = db.get_oracle_profile(profile.id)
    assert refreshed.last_tested_at is not None
    assert refreshed.last_test_success is not None

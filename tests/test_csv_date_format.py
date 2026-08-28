"""
DataScheduler — tests/test_csv_date_format.py
Filet de sécurité "format des dates" pour DB_EXTRACT (demande utilisateur, bug réel observé) :
une colonne date/heure oubliée par un TO_CHAR côté SQL revenait typée datetime64 par pandas et
était donc écrite en CSV au format ISO par défaut (yyyy-MM-dd), quel que soit le format demandé
ailleurs dans la requête pour d'autres colonnes. Nouveau réglage optionnel par étape, appliqué à
toute colonne encore typée date à l'arrivée — écrit avec les mêmes tokens ({dd}/{MM}/{yyyy}...)
que partout ailleurs dans l'appli, jamais la syntaxe strftime brute exposée à l'utilisateur.
"""

import pandas as pd

import core.sql_db as sql_db_module
from core.sql_db import SqlExporter
from core.steps.db_extract import _translate_date_format


class _FakeConnector:
    def __init__(self):
        self.connection = object()
        self.engine = object()


# ── _translate_date_format ────────────────────────────

def test_translate_date_format_maps_the_apps_own_tokens_to_strftime():
    assert _translate_date_format("{dd}/{MM}/{yyyy}") == "%d/%m/%Y"


def test_translate_date_format_handles_time_tokens_too():
    assert _translate_date_format("{yyyy}-{MM}-{dd} {HH}:{mm}:{ss}") == "%Y-%m-%d %H:%M:%S"


def test_translate_date_format_leaves_unrecognized_text_untouched():
    """Un token inconnu (faute de frappe, ou texte libre) reste littéral — un résultat visiblement
    faux dans le CSV plutôt qu'un plantage."""
    assert _translate_date_format("{jj}/{MM}/{yyyy}") == "{jj}/%m/%Y"


def test_translate_date_format_no_collision_between_yy_and_yyyy():
    assert _translate_date_format("{yyyy}") == "%Y"
    assert _translate_date_format("{yy}") == "%y"


# ── SqlExporter : le mécanisme réel, bout en bout sur un vrai to_csv() ──────────

def test_sql_exporter_without_date_format_uses_pandas_default_iso(tmp_path, monkeypatch):
    """Reproduit exactement le bug signalé : une colonne datetime64 sans date_format= explicite
    sort au format ISO de pandas, jamais celui demandé côté SQL pour d'autres colonnes."""
    chunk = pd.DataFrame({
        "msisdn": ["600000001"],
        "last_date_c2c": pd.to_datetime(["2026-08-28"]),
    })
    monkeypatch.setattr(sql_db_module.pd, "read_sql", lambda *a, **k: iter([chunk]))

    out = tmp_path / "out.csv"
    exporter = SqlExporter(connector=_FakeConnector(), sql="SELECT 1", output_path=out)
    result = exporter.export()

    assert result.success, result.error
    content = out.read_text(encoding="utf-8-sig")
    assert "2026-08-28" in content
    assert "28/08/2026" not in content


def test_sql_exporter_with_date_format_overrides_the_iso_default(tmp_path, monkeypatch):
    chunk = pd.DataFrame({
        "msisdn": ["600000001"],
        "last_date_c2c": pd.to_datetime(["2026-08-28"]),
    })
    monkeypatch.setattr(sql_db_module.pd, "read_sql", lambda *a, **k: iter([chunk]))

    out = tmp_path / "out.csv"
    exporter = SqlExporter(
        connector=_FakeConnector(), sql="SELECT 1", output_path=out, date_format="%d/%m/%Y",
    )
    result = exporter.export()

    assert result.success, result.error
    content = out.read_text(encoding="utf-8-sig")
    assert "28/08/2026" in content
    assert "2026-08-28" not in content


def test_sql_exporter_date_format_leaves_non_date_columns_untouched(tmp_path, monkeypatch):
    chunk = pd.DataFrame({
        "msisdn": ["600000001"],
        "montant": [12345],
        "last_date_c2c": pd.to_datetime(["2026-08-28"]),
    })
    monkeypatch.setattr(sql_db_module.pd, "read_sql", lambda *a, **k: iter([chunk]))

    out = tmp_path / "out.csv"
    exporter = SqlExporter(
        connector=_FakeConnector(), sql="SELECT 1", output_path=out, date_format="%d/%m/%Y",
    )
    exporter.export()

    content = out.read_text(encoding="utf-8-sig")
    assert "600000001" in content
    assert "12345" in content


# ── DbExtractStep : lit csv_date_format, traduit les tokens, transmet à SqlExporter ──

def test_db_extract_step_translates_and_forwards_date_format(monkeypatch, test_db):
    from database import db_manager as db
    from core.steps.base import StepContext
    from core.steps.db_extract import DbExtractStep

    profile = db.create_oracle_profile(
        name="ORACLE_TEST", host="10.0.0.1", port=1521,
        username="scott", password="tiger", service_name="TEST",
    )
    query = db.create_sql_query(name="Q", sql_text="SELECT * FROM t")

    captured = {}

    class _FakeSqlConnector:
        def __init__(self, cfg):
            pass

        def connect(self):
            pass

        def disconnect(self):
            pass

    class _FakeSqlExporter:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        def export(self):
            from core.sql_db import ExportResult
            return ExportResult(success=True, rows_exported=0)

    monkeypatch.setattr("core.sql_db.SqlConnector", _FakeSqlConnector)
    monkeypatch.setattr("core.sql_db.SqlExporter", _FakeSqlExporter)

    step = DbExtractStep({
        "db_type": "ORACLE", "profile_id": profile.id, "sql_query_id": query.id,
        "csv_date_format": "{dd}/{MM}/{yyyy}",
    })
    result = step.run(StepContext())

    assert result.success, result.error
    assert captured["date_format"] == "%d/%m/%Y"


def test_db_extract_step_leaves_date_format_none_when_not_configured(monkeypatch, test_db):
    """Zéro changement de comportement pour une étape existante — champ jamais configuré."""
    from database import db_manager as db
    from core.steps.base import StepContext
    from core.steps.db_extract import DbExtractStep

    profile = db.create_oracle_profile(
        name="ORACLE_TEST2", host="10.0.0.1", port=1521,
        username="scott", password="tiger", service_name="TEST",
    )
    query = db.create_sql_query(name="Q2", sql_text="SELECT * FROM t")

    captured = {}

    class _FakeSqlConnector:
        def __init__(self, cfg):
            pass

        def connect(self):
            pass

        def disconnect(self):
            pass

    class _FakeSqlExporter:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        def export(self):
            from core.sql_db import ExportResult
            return ExportResult(success=True, rows_exported=0)

    monkeypatch.setattr("core.sql_db.SqlConnector", _FakeSqlConnector)
    monkeypatch.setattr("core.sql_db.SqlExporter", _FakeSqlExporter)

    step = DbExtractStep({
        "db_type": "ORACLE", "profile_id": profile.id, "sql_query_id": query.id,
    })
    result = step.run(StepContext())

    assert result.success, result.error
    assert captured["date_format"] is None


# ── UI : round-trip du nouveau champ dans le dialogue de configuration ────────────

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_db_extract_dialog_date_format_empty_by_default(qapp):
    from ui.step_editor.db_extract_config_dialog import _DbExtractConfigDialog

    dlg = _DbExtractConfigDialog({}, None, "test-label")
    assert dlg.inp_date_format.text() == ""
    assert dlg._collect_config()["csv_date_format"] == ""


def test_db_extract_dialog_date_format_round_trip(qapp):
    from ui.step_editor.db_extract_config_dialog import _DbExtractConfigDialog

    dlg = _DbExtractConfigDialog({}, None, "test-label")
    dlg.inp_date_format.setText("{dd}/{MM}/{yyyy}")
    assert dlg._collect_config()["csv_date_format"] == "{dd}/{MM}/{yyyy}"


def test_db_extract_dialog_date_format_prefills_from_existing_config(qapp):
    from ui.step_editor.db_extract_config_dialog import _DbExtractConfigDialog

    dlg = _DbExtractConfigDialog({"csv_date_format": "{dd}/{MM}/{yyyy}"}, None, "test-label")
    assert dlg.inp_date_format.text() == "{dd}/{MM}/{yyyy}"

"""
DataScheduler — tests/test_sql_db_cancellation.py
Vérifie l'annulation coopérative (chantier dédié) de core.sql_db.SqlExporter/SqlLoader —
utilisées par DB_EXTRACT/DB_LOAD, seul chemin réellement emprunté aujourd'hui pour tout moteur
(core.oracle.OracleExporter/OracleLoader sont un chemin legacy non utilisé par aucune étape en
production). pandas.read_sql/read_csv/DataFrame.to_sql sont mockés — aucune vraie base ou aucun
vrai fichier CSV nécessaire, seul le comportement de la boucle de chunks est sous test.
"""

import threading

import pandas as pd

import core.sql_db as sql_db_module
from core.sql_db import SqlExporter, SqlLoader


class _FakeConnector:
    def __init__(self):
        self.connection = object()
        self.engine = object()


def test_sql_exporter_stops_between_chunks_when_cancelled(tmp_path, monkeypatch):
    chunks = [pd.DataFrame({"a": [1, 2]}), pd.DataFrame({"a": [3, 4]}), pd.DataFrame({"a": [5, 6]})]
    monkeypatch.setattr(sql_db_module.pd, "read_sql", lambda *a, **k: iter(chunks))

    cancel_event = threading.Event()

    def _on_progress(rows, chunk_idx):
        if chunk_idx == 1:
            cancel_event.set()   # annule juste après l'écriture du 1er chunk

    exporter = SqlExporter(
        connector=_FakeConnector(), sql="SELECT 1", output_path=tmp_path / "out.csv",
        chunk_size=2, on_progress=_on_progress, cancel_event=cancel_event,
    )
    result = exporter.export()

    assert not result.success
    assert "Annulé" in result.error
    assert result.chunks_count == 1   # jamais atteint le 2e ou 3e chunk


def test_sql_exporter_without_cancel_event_runs_to_completion(tmp_path, monkeypatch):
    """cancel_event=None (défaut, comportement historique) — ne doit jamais interrompre
    l'export, quel que soit le nombre de chunks."""
    chunks = [pd.DataFrame({"a": [1, 2]}), pd.DataFrame({"a": [3, 4]})]
    monkeypatch.setattr(sql_db_module.pd, "read_sql", lambda *a, **k: iter(chunks))

    exporter = SqlExporter(
        connector=_FakeConnector(), sql="SELECT 1", output_path=tmp_path / "out.csv",
        chunk_size=2,
    )
    result = exporter.export()

    assert result.success, result.error
    assert result.chunks_count == 2


def test_sql_loader_stops_between_chunks_when_cancelled(tmp_path, monkeypatch):
    csv_path = tmp_path / "in.csv"
    csv_path.write_text("a\n1\n2\n3\n4\n5\n6\n")

    chunks = [pd.DataFrame({"a": [1, 2]}), pd.DataFrame({"a": [3, 4]}), pd.DataFrame({"a": [5, 6]})]
    monkeypatch.setattr(sql_db_module.pd, "read_csv", lambda *a, **k: iter(chunks))
    monkeypatch.setattr(pd.DataFrame, "to_sql", lambda self, *a, **k: None)

    cancel_event = threading.Event()

    def _on_progress(rows, chunk_idx):
        if chunk_idx == 1:
            cancel_event.set()

    loader = SqlLoader(
        connector=_FakeConnector(), csv_path=csv_path, table_name="T",
        chunk_size=2, on_progress=_on_progress, cancel_event=cancel_event,
    )
    result = loader.load()

    assert not result.success
    assert "Annulé" in result.error
    assert result.chunks_count == 1


def test_sql_loader_without_cancel_event_runs_to_completion(tmp_path, monkeypatch):
    csv_path = tmp_path / "in.csv"
    csv_path.write_text("a\n1\n2\n3\n4\n")

    chunks = [pd.DataFrame({"a": [1, 2]}), pd.DataFrame({"a": [3, 4]})]
    monkeypatch.setattr(sql_db_module.pd, "read_csv", lambda *a, **k: iter(chunks))
    monkeypatch.setattr(pd.DataFrame, "to_sql", lambda self, *a, **k: None)

    loader = SqlLoader(connector=_FakeConnector(), csv_path=csv_path, table_name="T", chunk_size=2)
    result = loader.load()

    assert result.success, result.error
    assert result.chunks_count == 2

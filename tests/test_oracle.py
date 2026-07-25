"""
DataScheduler — tests/test_oracle.py
Teste core/oracle.py sans connexion Oracle réelle.
"""

import csv
import tempfile
from pathlib import Path
from datetime import datetime
from unittest.mock import MagicMock, patch

import pandas as pd

from core.oracle import (
    OracleConfig,
    OracleConnector,
    OracleExporter,
    resolve_template,
    config_from_profile,
)


def test_oracle_config_dsn():
    cfg = OracleConfig(host="10.10.1.15", port=1521, username="user",
                        password="pass", service_name="PROD")
    dsn = cfg.dsn()
    assert "10.10.1.15" in dsn
    assert "1521" in dsn

    cfg2 = OracleConfig(host="10.10.1.15", port=1521, username="user",
                         password="pass", sid="ORCLSID")
    assert "ORCLSID" in cfg2.dsn()

    cfg3 = OracleConfig(host="h", port=1521, username="u", password="p")
    try:
        cfg3.dsn()
        assert False, "Aurait dû lever ValueError"
    except ValueError:
        pass


def test_connection_success():
    cfg = OracleConfig(host="h", port=1521, username="u",
                        password="p", service_name="S")
    connector = OracleConnector(cfg)

    mock_conn = MagicMock()
    mock_conn.version = "19.3.0.0.0"
    mock_conn.__enter__ = lambda s: mock_conn
    mock_conn.__exit__ = MagicMock(return_value=False)

    with patch("core.oracle.oracledb.connect", return_value=mock_conn):
        result = connector.test_connection()

    assert result.success is True
    assert result.db_version == "19.3.0.0.0"
    assert result.duration_ms is not None


def test_connection_failure():
    import oracledb as _oracledb

    cfg = OracleConfig(host="bad_host", port=1521,
                        username="u", password="p", service_name="S")
    connector = OracleConnector(cfg)

    with patch("core.oracle.oracledb.connect",
               side_effect=_oracledb.DatabaseError("ORA-12541: no listener")):
        result = connector.test_connection()

    assert result.success is False
    assert "ORA-12541" in result.message


def test_export_csv_chunks():
    def make_chunks():
        for i in range(3):
            yield pd.DataFrame({
                "id":    range(i * 5, i * 5 + 5),
                "name":  [f"item_{j}" for j in range(i * 5, i * 5 + 5)],
                "value": [float(j) * 1.5 for j in range(i * 5, i * 5 + 5)],
            })

    connector = OracleConnector.__new__(OracleConnector)
    connector.config = MagicMock()
    connector._connection = MagicMock()

    progress_calls = []

    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "export_test.csv"

        exporter = OracleExporter(
            connector=connector,
            sql="SELECT id, name, value FROM test_table",
            output_path=output_path,
            separator=";",
            encoding="utf-8-sig",
            chunk_size=5,
            on_progress=lambda rows, chunk: progress_calls.append((rows, chunk)),
        )

        with patch("core.oracle.pd.read_sql", return_value=make_chunks()):
            result = exporter.export()

        assert result.success is True
        assert result.rows_exported == 15
        assert result.chunks_count == 3
        assert output_path.exists()

        with open(output_path, encoding="utf-8-sig") as f:
            rows = list(csv.DictReader(f, delimiter=";"))

        assert len(rows) == 15
        assert rows[0]["name"] == "item_0"
        assert rows[14]["name"] == "item_14"

        # QUOTE_NONNUMERIC (mode par défaut) entoure de guillemets les champs non
        # numériques, y compris les en-têtes.
        content = output_path.read_text(encoding="utf-8-sig")
        assert content.count('"id";"name";"value"') == 1

        assert len(progress_calls) == 3
        assert progress_calls[0] == (5, 1)
        assert progress_calls[2] == (15, 3)


def test_resolve_template():
    dt = datetime(2026, 6, 8, 6, 0, 30)

    assert resolve_template("ventes_{yyyyMMdd}.csv", dt) == "ventes_20260608.csv"
    assert resolve_template("/export/{yyyy}/{MM}/", dt) == "/export/2026/06/"
    assert resolve_template("data_{yyyyMMddHHmm}.csv", dt) == "data_202606080600.csv"
    assert resolve_template("fichier_{yy}{MM}.csv", dt) == "fichier_2606.csv"
    assert resolve_template("sans_token.csv", dt) == "sans_token.csv"


def test_config_from_profile():
    from database import crypto

    profile = MagicMock()
    profile.host = "10.0.0.1"
    profile.port = 1521
    profile.username = "scott"
    profile.password = crypto.encrypt("tiger")
    profile.service_name = "ORCL"
    profile.sid = None
    profile.auth_mode = "DEFAULT"

    cfg = config_from_profile(profile)
    assert cfg.host == "10.0.0.1"
    assert cfg.service_name == "ORCL"
    assert cfg.username == "scott"
    assert cfg.password == "tiger"

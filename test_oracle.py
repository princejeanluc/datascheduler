"""
test_oracle.py — Teste core/oracle.py sans connexion Oracle réelle.
Lance avec : python test_oracle.py
"""

import sys
import csv
import tempfile
from pathlib import Path
from datetime import datetime
from unittest.mock import MagicMock, patch, call
import io

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.oracle import (
    OracleConfig,
    OracleConnector,
    OracleExporter,
    ExportResult,
    ConnectionTestResult,
    resolve_template,
    config_from_profile,
)
import pandas as pd


# ──────────────────────────────────────────────
#  TEST 1 — OracleConfig DSN
# ──────────────────────────────────────────────

def test_oracle_config_dsn():
    # Avec service_name
    cfg = OracleConfig(
        host="10.10.1.15", port=1521,
        username="user", password="pass",
        service_name="PROD"
    )
    dsn = cfg.dsn()
    assert "10.10.1.15" in dsn
    assert "1521" in dsn
    print("✅  OracleConfig DSN (service_name) OK")

    # Avec SID
    cfg2 = OracleConfig(
        host="10.10.1.15", port=1521,
        username="user", password="pass",
        sid="ORCLSID"
    )
    dsn2 = cfg2.dsn()
    assert "ORCLSID" in dsn2
    print("✅  OracleConfig DSN (SID) OK")

    # Sans service_name ni SID → doit lever ValueError
    cfg3 = OracleConfig(host="h", port=1521, username="u", password="p")
    try:
        cfg3.dsn()
        assert False, "Aurait dû lever ValueError"
    except ValueError:
        print("✅  OracleConfig DSN (ValueError sans SID/service) OK")


# ──────────────────────────────────────────────
#  TEST 2 — test_connection succès
# ──────────────────────────────────────────────

def test_connection_success():
    cfg = OracleConfig(host="h", port=1521, username="u",
                       password="p", service_name="S")
    connector = OracleConnector(cfg)

    mock_conn = MagicMock()
    mock_conn.version = "19.3.0.0.0"
    mock_conn.__enter__ = lambda s: mock_conn
    mock_conn.__exit__  = MagicMock(return_value=False)

    with patch("DataScheduler.core.oracle.oracledb.connect",
               return_value=mock_conn):
        result = connector.test_connection()

    assert result.success is True
    assert result.db_version == "19.3.0.0.0"
    assert result.duration_ms is not None
    print("✅  test_connection (succès) OK")


# ──────────────────────────────────────────────
#  TEST 3 — test_connection échec
# ──────────────────────────────────────────────

def test_connection_failure():
    import oracledb as _oracledb

    cfg = OracleConfig(host="bad_host", port=1521,
                       username="u", password="p", service_name="S")
    connector = OracleConnector(cfg)

    with patch("DataScheduler.core.oracle.oracledb.connect",
               side_effect=_oracledb.DatabaseError("ORA-12541: no listener")):
        result = connector.test_connection()

    assert result.success is False
    assert "ORA-12541" in result.message
    print("✅  test_connection (échec) OK")


# ──────────────────────────────────────────────
#  TEST 4 — Export CSV par chunks
# ──────────────────────────────────────────────

def test_export_csv_chunks():
    # Préparer des données factices en 3 chunks de 5 lignes
    def make_chunks():
        for i in range(3):
            yield pd.DataFrame({
                "id":    range(i * 5, i * 5 + 5),
                "name":  [f"item_{j}" for j in range(i * 5, i * 5 + 5)],
                "value": [float(j) * 1.5 for j in range(i * 5, i * 5 + 5)],
            })

    mock_conn = MagicMock()
    mock_conn.connection = MagicMock()  # connexion interne

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

        with patch("DataScheduler.core.oracle.pd.read_sql",
                   return_value=make_chunks()):
            result = exporter.export()

        assert result.success is True
        assert result.rows_exported == 15
        assert result.chunks_count  == 3
        assert output_path.exists()

        # Vérifier le contenu CSV
        with open(output_path, encoding="utf-8-sig") as f:
            reader = csv.DictReader(f, delimiter=";")
            rows = list(reader)

        assert len(rows) == 15
        assert rows[0]["name"] == "item_0"
        assert rows[14]["name"] == "item_14"

        # Header présent une seule fois
        content = output_path.read_text(encoding="utf-8-sig")
        print(content.count("id;name;value"))
        assert content.count("id;name;value") == 1

        # Callbacks appelés 3 fois
        assert len(progress_calls) == 3
        assert progress_calls[0] == (5, 1)
        assert progress_calls[2] == (15, 3)

    print("✅  Export CSV par chunks OK")
    print(f"     → 15 lignes / 3 chunks / header unique / callbacks OK")


# ──────────────────────────────────────────────
#  TEST 5 — resolve_template
# ──────────────────────────────────────────────

def test_resolve_template():
    dt = datetime(2026, 6, 8, 6, 0, 30)

    assert resolve_template("ventes_{yyyyMMdd}.csv", dt)    == "ventes_20260608.csv"
    assert resolve_template("/export/{yyyy}/{MM}/",  dt)    == "/export/2026/06/"
    assert resolve_template("data_{yyyyMMddHHmm}.csv", dt)  == "data_202606080600.csv"
    assert resolve_template("fichier_{yy}{MM}.csv", dt)     == "fichier_2606.csv"
    assert resolve_template("sans_token.csv", dt)           == "sans_token.csv"

    print("✅  resolve_template OK")
    print(f"     → ventes_20260608.csv")
    print(f"     → /export/2026/06/")
    print(f"     → data_202606080600.csv")


# ──────────────────────────────────────────────
#  TEST 6 — config_from_profile
# ──────────────────────────────────────────────

def test_config_from_profile():
    profile = MagicMock()
    profile.host         = "10.0.0.1"
    profile.port         = 1521
    profile.username     = "scott"
    profile.password     = "tiger"
    profile.service_name = "ORCL"
    profile.sid          = None

    cfg = config_from_profile(profile)
    assert cfg.host         == "10.0.0.1"
    assert cfg.service_name == "ORCL"
    assert cfg.username     == "scott"
    print("✅  config_from_profile OK")


# ──────────────────────────────────────────────
#  MAIN
# ──────────────────────────────────────────────

if __name__ == "__main__":
    print("\n🔧  Tests core/oracle.py\n")
    test_oracle_config_dsn()
    test_connection_success()
    test_connection_failure()
    test_export_csv_chunks()
    test_resolve_template()
    test_config_from_profile()
    print("\n🎉  Tous les tests passent !\n")
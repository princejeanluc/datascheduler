"""
DataScheduler — tests/test_sqoop_jdbc_url.py
Vérifie core.sqoop.build_oracle_jdbc_url() : format TNS complet, SERVICE_NAME vs SID.
"""

from core.sql_db import SqlDbConfig
from core.sqoop import build_oracle_jdbc_url


def test_uses_service_name_when_present():
    cfg = SqlDbConfig(db_type="ORACLE", host="10.0.0.5", port=1521, username="u", password="p",
                       service_name="PRODDB")
    url = build_oracle_jdbc_url(cfg)
    assert url == (
        "jdbc:oracle:thin:@(DESCRIPTION=(ADDRESS_LIST=(ADDRESS=(PROTOCOL=TCP)"
        "(HOST=10.0.0.5)(PORT=1521)))(CONNECT_DATA=(SERVICE_NAME=PRODDB)))"
    )


def test_falls_back_to_sid_when_no_service_name():
    cfg = SqlDbConfig(db_type="ORACLE", host="10.0.0.5", port=1521, username="u", password="p",
                       service_name=None, sid="ORCL")
    url = build_oracle_jdbc_url(cfg)
    assert "SID=ORCL" in url
    assert "SERVICE_NAME" not in url

"""
DataScheduler — tests/test_step_reliability_fixes.py
Non-régression pour 4 problèmes trouvés en relisant les 10 implémentations de step directement
(pas seulement leurs dialogues de config) :

1. validate_step_sequence()/validate_pipeline_graph() rejetaient à tort un pipeline autonome
   (DB_LOAD/FTP_UPLOAD/LOCAL_COPY avec `explicit_path`) — REQUIRES statique ignorait explicit_path.
2. DB_EXTRACT n'appliquait jamais resolve_tokens() sur le texte SQL, contrairement à DB_EXECUTE
   qui le fait sur le même champ (SqlQuery.sql_text) — un jeton de date restait littéral.
3. DB_EXTRACT/DB_EXECUTE/DB_LOAD ne fermaient pas la connexion DB si l'opération levait une
   exception (pas de try/finally autour de connect()/disconnect()) — fuite de session.
4. DB_EXTRACT/FTP_DOWNLOAD créaient leur fichier temporaire avant de savoir si l'opération allait
   réussir ; en cas d'échec, jamais publié dans ctx.artifacts donc jamais nettoyé par
   run_pipeline() — fuite de fichier dans %TEMP%.
"""

from datetime import datetime

import core.sql_db as sql_db_module
from core.pipeline import validate_pipeline_graph, validate_step_sequence
from core.steps.base import StepContext
from core.steps.db_execute import DbExecuteStep
from core.steps.db_extract import DbExtractStep
from core.steps.db_load import DbLoadStep
from core.steps.ftp_download import FtpDownloadStep


# ──────────────────────────────────────────────
#  1. validate_step_sequence / validate_pipeline_graph — explicit_path
# ──────────────────────────────────────────────

def _standalone_step(step_type: str, extra_config: dict) -> dict:
    return {
        "step_type": step_type,
        "label": "Étape autonome",
        "config": {"explicit_path": "C:/data/export.csv", "_step_key": "k1", **extra_config},
        "run_always": False,
    }


def test_explicit_path_satisfies_requires_in_linear_validation():
    steps = [_standalone_step("FTP_UPLOAD", {"ftp_profile_id": 1})]
    errors, warnings = validate_step_sequence(steps)
    assert errors == []
    assert warnings == []


def test_explicit_path_satisfies_requires_in_graph_validation():
    steps = [_standalone_step("DB_LOAD", {"db_type": "ORACLE", "profile_id": 1, "table_name": "T"})]
    errors, warnings = validate_pipeline_graph(steps, edges=[])
    assert errors == []
    assert warnings == []


def test_missing_requirement_without_explicit_path_still_blocks():
    """Contrôle : le correctif ne doit pas créer de faux négatif — sans explicit_path, une
    étape qui a réellement besoin d'un output_file en amont reste bloquée."""
    steps = [{
        "step_type": "LOCAL_COPY", "label": "Sans source",
        "config": {"dest_dir": "C:/backup"}, "run_always": False,
    }]
    errors, _ = validate_step_sequence(steps)
    assert errors != []


# ──────────────────────────────────────────────
#  2/3/4. DB_EXTRACT — fakes pour SqlConnector/SqlExporter
# ──────────────────────────────────────────────

class _FakeDbProfile:
    host = "db-host"
    port = 1521


class _FakeExportResult:
    def __init__(self, success=True, error=None):
        self.success = success
        self.error = error
        self.rows_exported = 3
        self.duration_s = 0.01
        self.chunks_count = 1


class _FakeSqlConnector:
    disconnect_calls = 0

    def __init__(self, cfg):
        pass

    def connect(self):
        pass

    def disconnect(self):
        _FakeSqlConnector.disconnect_calls += 1


class _RecordingSqlExporter:
    """Capture le sql= et le output_path= reçus ; mode pilote le comportement d'export()."""
    last_sql = None
    last_output_path = None
    mode = "success"   # "success" | "fail" | "raise"

    def __init__(self, **kwargs):
        _RecordingSqlExporter.last_sql = kwargs["sql"]
        _RecordingSqlExporter.last_output_path = kwargs["output_path"]

    def export(self):
        if _RecordingSqlExporter.mode == "raise":
            raise RuntimeError("export explosion")
        if _RecordingSqlExporter.mode == "fail":
            return _FakeExportResult(success=False, error="boom")
        _RecordingSqlExporter.last_output_path.write_text("a,b\n1,2\n")
        return _FakeExportResult(success=True)


class _FakeSqlQuery:
    sql_text = "SELECT * FROM sales WHERE dt = '{yyyyMMdd}'"


def _patch_db_extract(monkeypatch, mode="success"):
    monkeypatch.setattr(sql_db_module, "get_profile_object", lambda db_type, profile_id: _FakeDbProfile())
    monkeypatch.setattr(sql_db_module, "config_from_profile", lambda db_type, profile: object())
    monkeypatch.setattr(sql_db_module, "SqlConnector", _FakeSqlConnector)
    monkeypatch.setattr(sql_db_module, "SqlExporter", _RecordingSqlExporter)
    import database.db_manager as db
    monkeypatch.setattr(db, "get_sql_query", lambda query_id: _FakeSqlQuery())
    _FakeSqlConnector.disconnect_calls = 0
    _RecordingSqlExporter.last_sql = None
    _RecordingSqlExporter.last_output_path = None
    _RecordingSqlExporter.mode = mode


def test_db_extract_resolves_tokens_in_sql_text(monkeypatch):
    _patch_db_extract(monkeypatch, mode="success")
    ctx = StepContext()
    step = DbExtractStep({"db_type": "ORACLE", "profile_id": 1, "sql_query_id": 1})
    result = step.run(ctx)

    assert result.success, result.error
    assert "{yyyyMMdd}" not in _RecordingSqlExporter.last_sql
    assert datetime.now().strftime("%Y%m%d") in _RecordingSqlExporter.last_sql


def test_db_extract_disconnects_even_when_export_raises(monkeypatch):
    _patch_db_extract(monkeypatch, mode="raise")
    ctx = StepContext()
    step = DbExtractStep({"db_type": "ORACLE", "profile_id": 1, "sql_query_id": 1})
    result = step.run(ctx)

    assert not result.success
    assert _FakeSqlConnector.disconnect_calls == 1


def test_db_extract_disconnects_on_success_too(monkeypatch):
    _patch_db_extract(monkeypatch, mode="success")
    ctx = StepContext()
    step = DbExtractStep({"db_type": "ORACLE", "profile_id": 1, "sql_query_id": 1})
    step.run(ctx)

    assert _FakeSqlConnector.disconnect_calls == 1


def test_db_extract_cleans_up_temp_file_on_export_failure(monkeypatch):
    _patch_db_extract(monkeypatch, mode="fail")
    ctx = StepContext()
    step = DbExtractStep({"db_type": "ORACLE", "profile_id": 1, "sql_query_id": 1})
    result = step.run(ctx)

    assert not result.success
    assert not _RecordingSqlExporter.last_output_path.exists()


def test_db_extract_cleans_up_temp_file_on_export_exception(monkeypatch):
    _patch_db_extract(monkeypatch, mode="raise")
    ctx = StepContext()
    step = DbExtractStep({"db_type": "ORACLE", "profile_id": 1, "sql_query_id": 1})
    step.run(ctx)

    assert not _RecordingSqlExporter.last_output_path.exists()


# ──────────────────────────────────────────────
#  3. DB_EXECUTE — connexion fermée même si l'exécution SQL lève
# ──────────────────────────────────────────────

class _RaisingConnection:
    def execute(self, *a, **kw):
        raise RuntimeError("execute explosion")


class _FakeExecuteConnector:
    disconnect_calls = 0

    def __init__(self, cfg):
        pass

    def connect(self):
        pass

    @property
    def connection(self):
        return _RaisingConnection()

    def disconnect(self):
        _FakeExecuteConnector.disconnect_calls += 1


def test_db_execute_disconnects_even_when_execute_raises(monkeypatch):
    monkeypatch.setattr(sql_db_module, "get_profile_object", lambda db_type, profile_id: _FakeDbProfile())
    monkeypatch.setattr(sql_db_module, "config_from_profile", lambda db_type, profile: object())
    monkeypatch.setattr(sql_db_module, "SqlConnector", _FakeExecuteConnector)
    import database.db_manager as db
    monkeypatch.setattr(db, "get_sql_query", lambda query_id: _FakeSqlQuery())
    _FakeExecuteConnector.disconnect_calls = 0

    ctx = StepContext()
    step = DbExecuteStep({"db_type": "ORACLE", "profile_id": 1, "sql_query_id": 1})
    result = step.run(ctx)

    assert not result.success
    assert _FakeExecuteConnector.disconnect_calls == 1


# ──────────────────────────────────────────────
#  3. DB_LOAD — connexion fermée même si le chargement lève
# ──────────────────────────────────────────────

class _RaisingSqlLoader:
    def __init__(self, **kwargs):
        pass

    def load(self):
        raise RuntimeError("load explosion")


def test_db_load_disconnects_even_when_load_raises(monkeypatch, tmp_path):
    monkeypatch.setattr(sql_db_module, "get_profile_object", lambda db_type, profile_id: _FakeDbProfile())
    monkeypatch.setattr(sql_db_module, "config_from_profile", lambda db_type, profile: object())
    monkeypatch.setattr(sql_db_module, "SqlConnector", _FakeSqlConnector)
    monkeypatch.setattr(sql_db_module, "SqlLoader", _RaisingSqlLoader)
    _FakeSqlConnector.disconnect_calls = 0

    src = tmp_path / "source.csv"
    src.write_text("a,b\n1,2\n")

    ctx = StepContext()
    step = DbLoadStep({
        "explicit_path": str(src), "db_type": "ORACLE", "profile_id": 1, "table_name": "T",
    })
    result = step.run(ctx)

    assert not result.success
    assert _FakeSqlConnector.disconnect_calls == 1


# ──────────────────────────────────────────────
#  4. FTP_DOWNLOAD — fichier temporaire nettoyé sur échec/exception
# ──────────────────────────────────────────────

class _FakeFtpProfile:
    host = "ftp-host"
    protocol = "SFTP"


class _RecordingFtpUploader:
    last_local_path = None
    mode = "success"   # "success" | "fail" | "raise"

    def __init__(self, cfg):
        pass

    def download(self, remote_path, local_path):
        from core.ftp import DownloadResult
        _RecordingFtpUploader.last_local_path = local_path
        if _RecordingFtpUploader.mode == "raise":
            raise RuntimeError("download explosion")
        if _RecordingFtpUploader.mode == "fail":
            return DownloadResult(success=False, error="boom")
        local_path.write_bytes(b"data")
        return DownloadResult(success=True, bytes_received=4)


def _patch_ftp_download(monkeypatch, mode="success"):
    import database.db_manager as db
    import core.ftp as ftp_module
    monkeypatch.setattr(db, "get_ftp_profile", lambda ftp_id: _FakeFtpProfile())
    monkeypatch.setattr(ftp_module, "config_from_profile", lambda profile: object())
    monkeypatch.setattr(ftp_module, "FtpUploader", _RecordingFtpUploader)
    _RecordingFtpUploader.last_local_path = None
    _RecordingFtpUploader.mode = mode


def test_ftp_download_cleans_up_temp_file_on_failure(monkeypatch):
    _patch_ftp_download(monkeypatch, mode="fail")
    ctx = StepContext()
    step = FtpDownloadStep({"ftp_profile_id": 1, "remote_path_tpl": "/export/x.csv"})
    result = step.run(ctx)

    assert not result.success
    assert not _RecordingFtpUploader.last_local_path.exists()


def test_ftp_download_cleans_up_temp_file_on_exception(monkeypatch):
    _patch_ftp_download(monkeypatch, mode="raise")
    ctx = StepContext()
    step = FtpDownloadStep({"ftp_profile_id": 1, "remote_path_tpl": "/export/x.csv"})
    step.run(ctx)

    assert not _RecordingFtpUploader.last_local_path.exists()


def test_ftp_download_keeps_temp_file_on_success(monkeypatch):
    _patch_ftp_download(monkeypatch, mode="success")
    ctx = StepContext()
    step = FtpDownloadStep({"ftp_profile_id": 1, "remote_path_tpl": "/export/x.csv"})
    result = step.run(ctx)

    assert result.success, result.error
    assert _RecordingFtpUploader.last_local_path.exists()
    assert ctx.output_file == _RecordingFtpUploader.last_local_path

"""
DataScheduler — tests/test_step_explicit_path.py
Vérifie le nouveau champ `explicit_path` (facultatif) sur les 3 étapes qui exigeaient jusqu'ici
un ctx.output_file déjà rempli par une étape amont (DB_LOAD, FTP_UPLOAD, LOCAL_COPY) : renseigné,
il devient prioritaire et rend l'étape utilisable seule dans un pipeline ; vide, le comportement
historique (ctx.output_file / erreur si absent) reste strictement inchangé.
"""

from core.steps.local_copy import LocalCopyStep
from core.steps.db_load import DbLoadStep
from core.steps.ftp_upload import FtpUploadStep
from core.steps.base import StepContext


# ──────────────────────────────────────────────
#  LOCAL_COPY — pas de mock nécessaire, juste le système de fichiers
# ──────────────────────────────────────────────

def test_local_copy_uses_explicit_path_when_set(tmp_path):
    src = tmp_path / "source.csv"
    src.write_text("a,b\n1,2\n")
    dest_dir = tmp_path / "dest"

    ctx = StepContext()   # ctx.output_file volontairement None : rien en amont
    step = LocalCopyStep({"explicit_path": str(src), "dest_dir": str(dest_dir)})
    result = step.run(ctx)

    assert result.success, result.error
    assert (dest_dir / "source.csv").read_text() == "a,b\n1,2\n"


def test_local_copy_falls_back_to_context_when_no_explicit_path(tmp_path):
    src = tmp_path / "from_ctx.csv"
    src.write_text("x")
    dest_dir = tmp_path / "dest"

    ctx = StepContext()
    ctx.output_file = src
    step = LocalCopyStep({"dest_dir": str(dest_dir)})   # pas d'explicit_path
    result = step.run(ctx)

    assert result.success, result.error
    assert (dest_dir / "from_ctx.csv").read_text() == "x"


def test_local_copy_fails_cleanly_without_explicit_path_or_context(tmp_path):
    ctx = StepContext()   # ni explicit_path, ni ctx.output_file
    step = LocalCopyStep({"dest_dir": str(tmp_path / "dest")})
    result = step.run(ctx)

    assert not result.success
    assert "Aucun fichier source" in result.error


# ──────────────────────────────────────────────
#  DB_LOAD — SqlConnector/SqlLoader substitués
# ──────────────────────────────────────────────

class _FakeDbProfile:
    host = "db-host"
    port = 1521


class _FakeLoadResult:
    success = True
    error = None
    rows_loaded = 3
    duration_s = 0.01
    chunks_count = 1


class _FakeSqlLoader:
    last_csv_path = None

    def __init__(self, **kwargs):
        _FakeSqlLoader.last_csv_path = kwargs["csv_path"]

    def load(self):
        return _FakeLoadResult()


class _FakeSqlConnector:
    def __init__(self, cfg):
        pass

    def connect(self):
        pass

    def disconnect(self):
        pass


def _patch_sql_db(monkeypatch):
    import core.sql_db as sql_db
    monkeypatch.setattr(sql_db, "get_profile_object", lambda db_type, profile_id: _FakeDbProfile())
    monkeypatch.setattr(sql_db, "config_from_profile", lambda db_type, profile: object())
    monkeypatch.setattr(sql_db, "SqlConnector", _FakeSqlConnector)
    monkeypatch.setattr(sql_db, "SqlLoader", _FakeSqlLoader)


def test_db_load_uses_explicit_path_when_set(tmp_path, monkeypatch):
    _patch_sql_db(monkeypatch)
    src = tmp_path / "explicit.csv"
    src.write_text("a")

    ctx = StepContext()   # ctx.output_file resté None
    step = DbLoadStep({
        "explicit_path": str(src), "db_type": "ORACLE", "profile_id": 1, "table_name": "T",
    })
    result = step.run(ctx)

    assert result.success, result.error
    assert _FakeSqlLoader.last_csv_path == src


def test_db_load_falls_back_to_context_when_no_explicit_path(tmp_path, monkeypatch):
    _patch_sql_db(monkeypatch)
    src = tmp_path / "from_ctx.csv"
    src.write_text("a")

    ctx = StepContext()
    ctx.output_file = src
    step = DbLoadStep({"db_type": "ORACLE", "profile_id": 1, "table_name": "T"})
    result = step.run(ctx)

    assert result.success, result.error
    assert _FakeSqlLoader.last_csv_path == src


def test_db_load_fails_cleanly_without_explicit_path_or_context(monkeypatch):
    _patch_sql_db(monkeypatch)
    ctx = StepContext()
    step = DbLoadStep({"db_type": "ORACLE", "profile_id": 1, "table_name": "T"})
    result = step.run(ctx)

    assert not result.success
    assert "Aucun fichier source" in result.error


# ──────────────────────────────────────────────
#  FTP_UPLOAD — db_manager.get_ftp_profile / FtpUploader substitués
# ──────────────────────────────────────────────

class _FakeFtpProfile:
    host = "ftp-host"


class _FakeUploadResult:
    success = True
    error = None
    remote_path = "/export/x.csv"
    bytes_sent = 10
    duration_s = 0.01


class _FakeFtpUploader:
    last_local_path = None

    def __init__(self, cfg):
        pass

    def upload(self, local_path, remote):
        _FakeFtpUploader.last_local_path = local_path
        return _FakeUploadResult()


def _patch_ftp(monkeypatch):
    from database import db_manager
    import core.ftp as ftp_module
    monkeypatch.setattr(db_manager, "get_ftp_profile", lambda ftp_id: _FakeFtpProfile())
    monkeypatch.setattr(ftp_module, "config_from_profile", lambda profile: object())
    monkeypatch.setattr(ftp_module, "FtpUploader", _FakeFtpUploader)


def test_ftp_upload_uses_explicit_path_when_set(tmp_path, monkeypatch):
    _patch_ftp(monkeypatch)
    src = tmp_path / "explicit.csv"
    src.write_text("a")

    ctx = StepContext()
    step = FtpUploadStep({"explicit_path": str(src), "ftp_profile_id": 1})
    result = step.run(ctx)

    assert result.success, result.error
    assert _FakeFtpUploader.last_local_path == src


def test_ftp_upload_falls_back_to_context_when_no_explicit_path(tmp_path, monkeypatch):
    _patch_ftp(monkeypatch)
    src = tmp_path / "from_ctx.csv"
    src.write_text("a")

    ctx = StepContext()
    ctx.output_file = src
    step = FtpUploadStep({"ftp_profile_id": 1})
    result = step.run(ctx)

    assert result.success, result.error
    assert _FakeFtpUploader.last_local_path == src


def test_ftp_upload_fails_cleanly_without_explicit_path_or_context(monkeypatch):
    _patch_ftp(monkeypatch)
    ctx = StepContext()
    step = FtpUploadStep({"ftp_profile_id": 1})
    result = step.run(ctx)

    assert not result.success
    assert "Aucun fichier source" in result.error

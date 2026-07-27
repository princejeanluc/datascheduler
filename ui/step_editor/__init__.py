"""
DataScheduler — ui/step_editor/__init__.py
Package de l'éditeur de pipeline (éclaté depuis l'ancien ui/step_editor.py, un fichier
par dialogue — voir docs/ARCHITECTURE.md). Réexporte tout ce qui était public et porte
la factory `_open_config_dialog()`, même principe que core/steps/__init__.py.
"""

from .common import STEP_META
from .pipeline_editor_dialog import PipelineEditorDialog
from .base_config_dialog import _BaseStepConfigDialog
from .db_extract_config_dialog import _DbExtractConfigDialog
from .ftp_upload_config_dialog import _FtpUploadConfigDialog
from .local_copy_config_dialog import _LocalCopyConfigDialog
from .python_script_config_dialog import _PythonScriptConfigDialog
from .db_execute_config_dialog import _DbExecuteConfigDialog
from .ftp_download_config_dialog import _FtpDownloadConfigDialog
from .db_load_config_dialog import _DbLoadConfigDialog
from .email_notify_config_dialog import _EmailNotifyConfigDialog
from .http_request_config_dialog import _HttpRequestConfigDialog
from .condition_config_dialog import _ConditionConfigDialog

__all__ = ["STEP_META", "PipelineEditorDialog", "_open_config_dialog"]


def _open_config_dialog(step_type: str, config: dict, parent,
                        oracle_profiles, ftp_profiles, sql_queries,
                        smtp_profiles=None, db_profiles=None,
                        label: str = "", retry_count: int = 0,
                        run_always: bool = False,
                        prior_steps: list | None = None) -> _BaseStepConfigDialog | None:
    kwargs = dict(
        config=config, parent=parent, label=label,
        oracle_profiles=oracle_profiles,
        ftp_profiles=ftp_profiles,
        sql_queries=sql_queries,
        smtp_profiles=smtp_profiles,
        db_profiles=db_profiles,
        retry_count=retry_count,
        run_always=run_always,
        prior_steps=prior_steps,
    )
    mapping = {
        "DB_EXTRACT":     _DbExtractConfigDialog,
        "FTP_UPLOAD":     _FtpUploadConfigDialog,
        "LOCAL_COPY":     _LocalCopyConfigDialog,
        "PYTHON_SCRIPT":  _PythonScriptConfigDialog,
        "DB_EXECUTE":     _DbExecuteConfigDialog,
        "FTP_DOWNLOAD":   _FtpDownloadConfigDialog,
        "DB_LOAD":        _DbLoadConfigDialog,
        "EMAIL_NOTIFY":   _EmailNotifyConfigDialog,
        "HTTP_REQUEST":   _HttpRequestConfigDialog,
        "CONDITION":      _ConditionConfigDialog,
    }
    cls = mapping.get(step_type)
    return cls(**kwargs) if cls else None

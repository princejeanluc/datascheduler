"""
DataScheduler — ui/dialogs/__init__.py
Package des dialogues profils/pipeline (éclaté depuis l'ancien ui/dialogs.py, un fichier par
dialogue — voir docs/ARCHITECTURE.md). Réexporte tout ce qui était public : les sites d'appel
existants (`from ui.dialogs import X`) n'ont pas besoin de changer.
"""

from .oracle_dialog import OracleTestThread, OracleDialog
from .ftp_dialog import FtpTestThread, FtpDialog
from .smtp_dialog import SmtpTestThread, SmtpDialog
from .database_profile_dialog import (
    DB_TYPE_META,
    DbTypeChooserDialog,
    DatabaseProfileTestThread,
    DatabaseProfileDialog,
)
from .run_progress_dialog import RunProgressThread, RunProgressDialog
from .sql_query_dialog import SqlQueryDialog
from .pipeline_export_dialog import PipelineExportDialog
from .pipeline_import_dialogs import PipelineImportPasswordDialog, PipelineImportReviewDialog

__all__ = [
    "OracleTestThread", "OracleDialog",
    "FtpTestThread", "FtpDialog",
    "SmtpTestThread", "SmtpDialog",
    "DB_TYPE_META", "DbTypeChooserDialog", "DatabaseProfileTestThread", "DatabaseProfileDialog",
    "RunProgressThread", "RunProgressDialog",
    "SqlQueryDialog",
    "PipelineExportDialog",
    "PipelineImportPasswordDialog", "PipelineImportReviewDialog",
]

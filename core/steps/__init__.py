from .base           import StepContext, StepResult, BaseStep
from .ftp_upload     import FtpUploadStep
from .local_copy     import LocalCopyStep
from .python_script  import PythonScriptStep
from .ftp_download   import FtpDownloadStep
from .email_notify   import EmailNotifyStep
from .http_request   import HttpRequestStep
from .db_extract     import DbExtractStep
from .db_execute     import DbExecuteStep
from .db_load        import DbLoadStep
from .condition      import ConditionStep
from .spark_sql      import SparkSqlStep

_REGISTRY: dict[str, type[BaseStep]] = {
    "FTP_UPLOAD":     FtpUploadStep,
    "LOCAL_COPY":     LocalCopyStep,
    "PYTHON_SCRIPT":  PythonScriptStep,
    "FTP_DOWNLOAD":   FtpDownloadStep,
    "EMAIL_NOTIFY":   EmailNotifyStep,
    "HTTP_REQUEST":   HttpRequestStep,
    "DB_EXTRACT":     DbExtractStep,
    "DB_EXECUTE":     DbExecuteStep,
    "DB_LOAD":        DbLoadStep,
    "CONDITION":      ConditionStep,
    "SPARK_SQL":      SparkSqlStep,
}


def get_step(step_type: str, config: dict) -> BaseStep:
    cls = _REGISTRY.get(step_type)
    if cls is None:
        raise ValueError(f"Type d'étape inconnu : {step_type!r}")
    return cls(config)


def get_step_requirements(step_type: str) -> tuple[set[str], set[str]]:
    """Retourne (REQUIRES, PRODUCES) pour un type d'étape, sans l'instancier."""
    cls = _REGISTRY.get(step_type)
    if cls is None:
        return set(), set()
    return set(cls.REQUIRES), set(cls.PRODUCES)


def get_step_output_ports(step_type: str) -> tuple[str, ...]:
    """Retourne les ports de sortie nommés d'un type d'étape (chantier 6a) — un seul port
    implicite ("output_file") pour tous les steps existants ; plusieurs pour un nœud comme
    ConditionStep ("true", "false")."""
    cls = _REGISTRY.get(step_type)
    return cls.OUTPUT_PORTS if cls is not None else ("output_file",)

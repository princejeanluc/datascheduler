from .base           import StepContext, StepResult, BaseStep
from .oracle_extract import OracleExtractStep
from .ftp_upload     import FtpUploadStep
from .local_copy     import LocalCopyStep
from .python_script  import PythonScriptStep
from .oracle_execute import OracleExecuteStep
from .ftp_download   import FtpDownloadStep
from .oracle_load    import OracleLoadStep
from .email_notify   import EmailNotifyStep
from .http_request   import HttpRequestStep

_REGISTRY: dict[str, type[BaseStep]] = {
    "ORACLE_EXTRACT": OracleExtractStep,
    "FTP_UPLOAD":     FtpUploadStep,
    "LOCAL_COPY":     LocalCopyStep,
    "PYTHON_SCRIPT":  PythonScriptStep,
    "ORACLE_EXECUTE": OracleExecuteStep,
    "FTP_DOWNLOAD":   FtpDownloadStep,
    "ORACLE_LOAD":    OracleLoadStep,
    "EMAIL_NOTIFY":   EmailNotifyStep,
    "HTTP_REQUEST":   HttpRequestStep,
}


def get_step(step_type: str, config: dict) -> BaseStep:
    cls = _REGISTRY.get(step_type)
    if cls is None:
        raise ValueError(f"Type d'étape inconnu : {step_type!r}")
    return cls(config)

from .base           import StepContext, StepResult, BaseStep
from .oracle_extract import OracleExtractStep
from .ftp_upload     import FtpUploadStep
from .local_copy     import LocalCopyStep
from .python_script  import PythonScriptStep

_REGISTRY: dict[str, type[BaseStep]] = {
    "ORACLE_EXTRACT": OracleExtractStep,
    "FTP_UPLOAD":     FtpUploadStep,
    "LOCAL_COPY":     LocalCopyStep,
    "PYTHON_SCRIPT":  PythonScriptStep,
}


def get_step(step_type: str, config: dict) -> BaseStep:
    cls = _REGISTRY.get(step_type)
    if cls is None:
        raise ValueError(f"Type d'étape inconnu : {step_type!r}")
    return cls(config)

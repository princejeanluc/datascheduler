"""
DataScheduler — core/steps/base.py
Contexte partagé entre étapes + classe abstraite BaseStep.
"""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path


@dataclass
class StepContext:
    """État transmis d'étape en étape lors d'une exécution de pipeline."""

    started_at:  datetime      = field(default_factory=datetime.utcnow)
    output_file: Path | None   = None    # fichier produit par l'étape précédente
    rows_count:  int           = 0
    log_lines:   list[str]     = field(default_factory=list)
    extra:       dict          = field(default_factory=dict)

    def log(self, msg: str) -> None:
        ts = datetime.utcnow().strftime("%H:%M:%S")
        self.log_lines.append(f"[{ts}] {msg}")

    def resolve_tokens(self, template: str) -> str:
        """Remplace {yyyy}, {MM}, {dd}, {HH}, {mm}, {output_file}, etc."""
        now = datetime.now()
        t   = template
        t   = t.replace("{yyyy}",           now.strftime("%Y"))
        t   = t.replace("{yy}",             now.strftime("%y"))
        t   = t.replace("{MM}",             now.strftime("%m"))
        t   = t.replace("{dd}",             now.strftime("%d"))
        t   = t.replace("{HH}",             now.strftime("%H"))
        t   = t.replace("{mm}",             now.strftime("%M"))
        t   = t.replace("{yyyyMMdd}",       now.strftime("%Y%m%d"))
        t   = t.replace("{yyyyMMddHHmm}",   now.strftime("%Y%m%d%H%M"))
        t   = t.replace("{rows_count}",     str(self.rows_count))
        if self.output_file:
            t = t.replace("{output_file}", str(self.output_file))
        return t


@dataclass
class StepResult:
    success: bool       = False
    error:   str | None = None


class BaseStep:
    def __init__(self, config: dict):
        self.config = config

    def run(self, ctx: StepContext, on_progress=None) -> StepResult:
        raise NotImplementedError

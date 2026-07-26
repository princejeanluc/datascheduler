"""
DataScheduler — core/steps/base.py
Contexte partagé entre étapes + classe abstraite BaseStep.
"""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path


@dataclass
class StepContext:
    """
    État transmis d'étape en étape lors d'une exécution de pipeline.

    `artifacts` est un dict nommé/adressable (ex: plusieurs fichiers produits par
    plusieurs étapes, vivants simultanément) — `output_file` reste une propriété de
    compatibilité pointant vers artifacts["output_file"], le nom par défaut sous
    lequel une étape publie sa sortie tant qu'aucune clé spécifique n'est demandée.
    Les steps eux-mêmes n'ont pas à changer : ils continuent de lire/écrire
    ctx.output_file exactement comme avant — c'est l'exécuteur (core/pipeline.py)
    qui republie en plus sous une clé stable par étape et qui réoriente ce même
    slot quand une étape consommatrice cible explicitement une source antérieure.
    """

    started_at:  datetime      = field(default_factory=datetime.utcnow)
    artifacts:   dict          = field(default_factory=dict)
    rows_count:  int           = 0
    log_lines:   list[str]     = field(default_factory=list)
    extra:       dict          = field(default_factory=dict)

    @property
    def output_file(self) -> Path | None:
        return self.artifacts.get("output_file")

    @output_file.setter
    def output_file(self, value: Path | None) -> None:
        self.artifacts["output_file"] = value

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
        t   = t.replace("{ss}",             now.strftime("%S"))
        t   = t.replace("{yyyyMMdd}",       now.strftime("%Y%m%d"))
        t   = t.replace("{yyyyMMddHHmm}",   now.strftime("%Y%m%d%H%M"))
        t   = t.replace("{rows_count}",     str(self.rows_count))
        t   = t.replace("{error}",          str(self.extra.get("error_message", "")))
        t   = t.replace("{failed_step}",    str(self.extra.get("failed_step_label", "")))
        if self.output_file:
            t = t.replace("{output_file}", str(self.output_file))
        return t


@dataclass
class StepResult:
    success:     bool       = False
    error:       str | None = None
    # Port de sortie actif pour les nœuds à ports multiples (ex: ConditionStep, "true"/"false") —
    # None pour tous les steps existants, qui n'ont qu'un seul port de sortie implicite.
    active_port: str | None = None


class BaseStep:
    # Ce que ce type d'étape exige déjà présent dans ctx pour fonctionner
    # (ex: {"output_file"}) — utilisé par la validation statique à la sauvegarde.
    REQUIRES: set[str] = set()
    # Ce que ce type d'étape garantit avoir rempli dans ctx en cas de succès.
    PRODUCES: set[str] = set()
    # Ports de sortie nommés (chantier 6a) — un seul port implicite pour tous les steps
    # existants ; un nœud à ports multiples (ex: ConditionStep) le redéfinit ("true", "false").
    OUTPUT_PORTS: tuple[str, ...] = ("output_file",)

    def __init__(self, config: dict):
        self.config = config

    def run(self, ctx: StepContext, on_progress=None) -> StepResult:
        raise NotImplementedError

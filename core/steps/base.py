"""
DataScheduler — core/steps/base.py
Contexte partagé entre étapes + classe abstraite BaseStep.
"""

import re
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

    def fork(self) -> "StepContext":
        """
        Copie isolée pour l'exécution concurrente d'une étape (chantier parallélisme
        intra-pipeline) — son propre dict `artifacts` (copie superficielle : les valeurs sont
        des `Path`, immuables, donc une copie superficielle suffit à isoler complètement les
        écritures) et son propre `log_lines`, pour qu'aucune écriture faite par une étape en
        train de tourner dans un thread n'affecte jamais une autre étape concurrente avant que
        le coordinateur ne fusionne son résultat après coup — un seul thread (le coordinateur)
        touche jamais le `StepContext` partagé, voir core/pipeline.py::_execute_graph_parallel.

        `extra` partagé par référence à dessein (lu par les steps — ex: `{error}`/
        `{failed_step}` dans resolve_tokens — jamais écrit par eux) ; `started_at` copié tel
        quel (purement informatif, jamais utilisé pour une décision d'exécution).
        """
        return StepContext(
            started_at=self.started_at,
            artifacts=dict(self.artifacts),
            rows_count=self.rows_count,
            log_lines=[],
            extra=self.extra,
        )

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
        # {artifact:nom} — référence générique à un artefact nommé (chantier UX ports nommés),
        # utilisable dans n'importe quel champ templaté, pas seulement PYTHON_SCRIPT. Même
        # convention que {output_file} ci-dessus : non résolu si absent (reste littéral dans le
        # texte — un échec visible à l'exécution plutôt qu'une valeur silencieusement vidée).
        t = re.sub(
            r"\{artifact:([^}]+)\}",
            lambda m: str(self.artifacts[m.group(1)]) if m.group(1) in self.artifacts else m.group(0),
            t,
        )
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
    # Nœud de routage/jonction (chantier UX éditeur, losange plutôt que rectangle sur le
    # canevas) — False pour tous les steps existants ; ConditionStep le redéfinit à True, un
    # futur type GATEWAY en hériterait de même. Centralisé ici (jamais une liste de types en
    # dur côté rendu Qt) — même principe que OUTPUT_PORTS ci-dessus.
    IS_ROUTING_NODE: bool = False
    # Passerelle de jonction ET/OU (chantier Gateway) — False pour tous les steps existants ;
    # GatewayJoinStep le redéfinit à True. Pilote get_join_mode() (core/steps/__init__.py), qui
    # à son tour pilote la sémantique ET dans core/pipeline.py (_execute_graph/
    # _execute_graph_parallel) — jamais un littéral "GATEWAY_JOIN" codé en dur dans le moteur,
    # même principe d'indirection que IS_ROUTING_NODE/is_routing_node().
    IS_JOIN_GATEWAY: bool = False

    def __init__(self, config: dict):
        self.config = config

    def run(self, ctx: StepContext, cancel_event=None, on_progress=None) -> StepResult:
        """
        `cancel_event` (threading.Event | None, chantier annulation coopérative) : positionné
        quand l'utilisateur demande l'arrêt d'un run en cours (voir core.pipeline.request_cancel).
        Optionnel — un type d'étape n'est pas obligé de le consulter (comportement historique
        inchangé, appel bloquant unique jusqu'à son terme) ; ceux qui ont un vrai point
        d'interruption sûr (boucle de chunks, sous-processus, sondage réseau) sont encouragés à
        vérifier cancel_event.is_set() et à retourner StepResult(success=False, ...) au plus tôt.
        """
        raise NotImplementedError

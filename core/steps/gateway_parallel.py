"""
DataScheduler — core/steps/gateway_parallel.py
Passerelle de fork parallèle (chantier Gateway, inspiré BPMN) : marqueur structurel qui rend
explicite dans le graphe un point où le flux se divise en plusieurs branches — exécutées en
parallèle si le pipeline a activé parallel_execution_enabled (core/pipeline.py::
_execute_graph_parallel). Ne fait AUCUNE transformation propre : le fan-out réel (plusieurs
arêtes sortantes depuis ce même port) fonctionne déjà nativement dans le moteur de graphe (aucune
limite sur le nombre d'arêtes sortantes d'un même port, voir ui/graph_editor/graph_scene.py::
add_edge()) — ce type n'ajoute qu'une identité visuelle/organisationnelle à un motif déjà
supporté. Consommé uniquement par l'éditeur graphique (comme ConditionStep) ; pas de case dans
STEP_META pour l'éditeur linéaire.

run() est un pur no-op délibéré : republier ctx.artifacts[step_key] soi-même à l'intérieur de
run() NE SUFFIT PAS dans le moteur parallèle (_execute_graph_parallel), qui exécute chaque étape
contre une COPIE isolée de ctx (StepContext.fork()) — un écrit fait ici serait perdu, la copie
étant jetée après le thread. La republication doit donc passer par le mécanisme générique déjà
existant du moteur (comparaison avec l'instantané pris juste avant run(), core/pipeline.py) —
PRODUCES = {"output_file"} déclare que ce type produit TOUJOURS quelque chose quand il réussit
(comme DB_EXTRACT/FTP_DOWNLOAD/COMPRESS), ce qui suffit à déclencher la republication même quand
la valeur observée n'a en apparence "pas changé" (voir le commentaire correspondant dans
_execute_graph/_execute_graph_parallel).
"""

from .base import BaseStep, StepContext, StepResult


class GatewayParallelStep(BaseStep):
    REQUIRES: set[str] = set()
    PRODUCES: set[str] = {"output_file"}
    IS_ROUTING_NODE = True

    def run(self, ctx: StepContext, cancel_event=None, on_progress=None) -> StepResult:
        return StepResult(success=True)

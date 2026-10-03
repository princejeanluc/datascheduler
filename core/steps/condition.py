"""
DataScheduler — core/steps/condition.py
Étape de branchement conditionnel (chantier 6a, enrichi — chantier vocabulaire des conditions,
puis chantier évaluateur d'expressions généralisé) : évalue une expression sur le contexte,
détermine quel port de sortie ("true"/"false") est actif — voir core/pipeline.py, exécution DAG
(_execute_graph). Consommé uniquement par l'éditeur graphique (chantier 6b) ; pas de case dans
STEP_META/l'éditeur linéaire (un nœud à ports multiples n'y a pas de sens).

La grammaire elle-même (tokenizer + parseur, toujours volontairement non-eval()) vit désormais
dans core/expr_lang.py — ConditionStep n'en est qu'un consommateur parmi d'autres (voir aussi le
token {expr:...} de StepContext.resolve_tokens(), core/steps/base.py). Le vocabulaire disponible
dépasse maintenant la simple comparaison : arithmétique (+ - * /) et fonctions (date_add, now,
today, fmt, concat, upper, lower, round) sont utilisables dans l'expression d'une condition,
pas seulement dans un {expr:...} ailleurs. Une expression sans comparaison (ex. "rows_count") est
légale et résolue par troncature de vérité Python — comportement voulu, pas un cas particulier.
"""

from core.expr_lang import evaluate
from .base import BaseStep, StepContext, StepResult


class ConditionStep(BaseStep):
    REQUIRES: set[str] = set()
    # Passe-plat : run() ne touche jamais ctx.output_file, mais sans PRODUCES le moteur ne
    # républie pas l'artefact sous la clé de cette étape, et l'étape suivante (réorientée vers
    # ctx.artifacts[clé de la condition]) perdait le fichier amont — même mécanisme que
    # GatewayParallelStep.
    PRODUCES: set[str] = {"output_file"}
    OUTPUT_PORTS = ("true", "false")
    IS_ROUTING_NODE = True

    def run(self, ctx: StepContext, cancel_event=None, on_progress=None) -> StepResult:
        expression = self.config.get("expression", "")
        try:
            active = evaluate(expression, ctx)
        except ValueError as e:
            return StepResult(success=False, error=f"Expression invalide : {e}")

        port = "true" if active else "false"
        ctx.log(f"Condition « {expression} » → {port}")
        return StepResult(success=True, active_port=port)

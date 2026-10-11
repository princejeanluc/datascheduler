"""
DataScheduler — core/steps/set_variable.py
Étape : calcule une ou plusieurs variables nommées via core/expr_lang.py::evaluate(), sans
dépendre d'un fichier amont (contrairement à EXTRACT_VARIABLES, qui exige une source CSV à une
seule ligne). Utile pour une valeur purement calculée (date_add(today(), -7), un total dérivé
d'une variable existante, un littéral) qu'on veut rendre disponible via var:nom sans construire
de fichier intermédiaire juste pour ça.

run() construit toutes les valeurs dans un dict temporaire puis ne met à jour ctx.variables
qu'une fois TOUTES les expressions évaluées avec succès (même principe que
ExtractVariablesStep.run() : jamais d'écriture partielle si une assignation échoue en cours de
route).
"""

from core.expr_lang import evaluate
from .base import BaseStep, StepContext, StepResult


class SetVariableStep(BaseStep):
    # Volontairement vide : une expression peut référencer rows_count/artifact:/var:/des
    # littéraux, mais rien n'est obligatoire — contrairement à EXTRACT_VARIABLES qui exige un
    # fichier source déjà produit. C'est ce qui fait de SET_VARIABLE une étape réellement
    # autonome ("sans connexion").
    REQUIRES: set[str] = set()
    # Passe-plat : run() ne touche jamais ctx.output_file, mais sans PRODUCES le moteur ne
    # republie pas l'artefact sous la clé de cette étape, et l'étape suivante (réorientée vers
    # ctx.artifacts[clé de cette étape]) perdrait le fichier amont — même mécanisme que
    # ConditionStep/ExtractVariablesStep (voir core/steps/condition.py).
    PRODUCES: set[str] = {"output_file"}

    def run(self, ctx: StepContext, cancel_event=None, on_progress=None) -> StepResult:
        result = StepResult()

        assignments = self.config.get("assignments") or []
        if not assignments:
            result.error = "Aucune assignation configurée."
            return result

        computed: dict = {}
        for assignment in assignments:
            target = (assignment.get("target") or "").strip()
            expression = assignment.get("expression") or ""
            if not target:
                result.error = "Assignation incomplète (variable cible manquante)."
                return result
            try:
                computed[target] = evaluate(expression, ctx)
            except ValueError as e:
                result.error = f"Variable « {target} » : expression invalide — {e}"
                return result

        ctx.variables.update(computed)
        ctx.log(f"Variables définies : {', '.join(computed.keys())}")
        result.success = True
        return result

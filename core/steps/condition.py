"""
DataScheduler — core/steps/condition.py
Étape de branchement conditionnel (chantier 6a) : évalue une expression simple et sûre sur le
contexte, détermine quel port de sortie ("true"/"false") est actif — voir core/pipeline.py,
exécution DAG (_execute_graph). Consommé uniquement par le futur éditeur graphique (chantier 6b) ;
pas de case dans STEP_META/l'éditeur linéaire (un nœud à ports multiples n'y a pas de sens).
"""

import operator

from .base import BaseStep, StepContext, StepResult

_OPS = {
    "==": operator.eq,
    "!=": operator.ne,
    ">=": operator.ge,
    "<=": operator.le,
    ">":  operator.gt,
    "<":  operator.lt,
}
# Trié par longueur décroissante pour tester ">=" avant ">" lors du split.
_OPS_BY_LENGTH = sorted(_OPS, key=len, reverse=True)


def _resolve_operand(token: str, ctx: StepContext):
    """Résout un opérande : `rows_count`, `artifact:<nom>` (présence -> bool, ou son chemin en
    texte), ou un littéral (nombre si possible, sinon chaîne)."""
    token = token.strip()
    if token == "rows_count":
        return ctx.rows_count
    if token.startswith("artifact:"):
        name = token[len("artifact:"):]
        value = ctx.artifacts.get(name)
        return str(value) if value is not None else None
    try:
        return float(token) if "." in token else int(token)
    except ValueError:
        return token.strip("\"'")


def _evaluate(expression: str, ctx: StepContext) -> bool:
    """
    Grammaire volontairement minimale et sûre — pas d'`eval()` sur une chaîne arbitraire (même
    dans un outil interne mono-utilisateur, un config_json par ailleurs éditable à la main ne
    doit pas devenir un vecteur d'exécution de code) : "<champ> <opérateur> <valeur>".
    Champs supportés : rows_count, artifact:<nom> (présence/valeur d'un artefact produit par une
    étape précédente).
    """
    expr = (expression or "").strip()
    if not expr:
        raise ValueError("Expression vide.")

    for op in _OPS_BY_LENGTH:
        if op in expr:
            left, _, right = expr.partition(op)
            if not left.strip() or not right.strip():
                continue
            left_val  = _resolve_operand(left, ctx)
            right_val = _resolve_operand(right, ctx)
            try:
                return _OPS[op](left_val, right_val)
            except TypeError as e:
                raise ValueError(f"Comparaison invalide ({left_val!r} {op} {right_val!r}) : {e}")

    raise ValueError(
        f"Expression non reconnue : {expr!r} (opérateurs supportés : {', '.join(_OPS)})"
    )


class ConditionStep(BaseStep):
    REQUIRES: set[str] = set()
    PRODUCES: set[str] = set()
    OUTPUT_PORTS = ("true", "false")

    def run(self, ctx: StepContext, on_progress=None) -> StepResult:
        expression = self.config.get("expression", "")
        try:
            active = _evaluate(expression, ctx)
        except ValueError as e:
            return StepResult(success=False, error=f"Expression invalide : {e}")

        port = "true" if active else "false"
        ctx.log(f"Condition « {expression} » → {port}")
        return StepResult(success=True, active_port=port)

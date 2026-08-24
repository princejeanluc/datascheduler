"""
DataScheduler — core/steps/condition.py
Étape de branchement conditionnel (chantier 6a, enrichi — chantier vocabulaire des conditions) :
évalue une expression booléenne sûre sur le contexte, détermine quel port de sortie ("true"/
"false") est actif — voir core/pipeline.py, exécution DAG (_execute_graph). Consommé uniquement
par l'éditeur graphique (chantier 6b) ; pas de case dans STEP_META/l'éditeur linéaire (un nœud à
ports multiples n'y a pas de sens).

Grammaire volontairement non-eval() (config_json reste un blob éditable à la main — ne doit jamais
devenir un vecteur d'exécution de code), mais compose désormais plusieurs comparaisons via
and/or/not et parenthèses, ex. : "rows_count > 0 and artifact:rapport != \"\"".
"""

import operator
import re

from .base import BaseStep, StepContext, StepResult

_OPS = {
    "==": operator.eq,
    "!=": operator.ne,
    ">=": operator.ge,
    "<=": operator.le,
    ">":  operator.gt,
    "<":  operator.lt,
}

_KEYWORDS = {"and", "or", "not"}

# Profondeur max de récursion (parenthèses imbriquées / chaîne de "not") — une vraie expression
# humaine ne dépasse jamais quelques niveaux ; ce plafond évite qu'une expression pathologique
# (des centaines de parenthèses dans un config_json édité à la main) ne fasse planter le parseur
# par une RecursionError Python non catchée, plutôt qu'un ValueError propre comme tout le reste
# de cette grammaire.
_MAX_NESTING_DEPTH = 50

# Un seul regex combiné, alternatives les plus spécifiques en premier (l'ordre conditionne quelle
# alternative "gagne" à une position donnée) :
#   - artifact:"nom cité"/'nom cité' avant la forme non citée, elle-même avant l'identifiant
#     générique (sinon "artifact:xxx" serait déjà entièrement absorbé par IDENT, qui tolère ":"
#     mais pas les tirets/espaces/accents d'un nom d'artefact réel — voir docstring de
#     _resolve_operand).
#   - opérateurs à 2 caractères (==, !=, >=, <=) avant ceux à 1 caractère (>, <), sinon ">=`
#     serait scindé en ">" puis un "=" orphelin non reconnu.
_TOKEN_RE = re.compile(r"""
    (?P<WS>\s+)
  | (?P<ARTIFACT_Q>artifact:"[^"]*"|artifact:'[^']*')
  | (?P<ARTIFACT>artifact:[^\s()=!<>]+)
  | (?P<OP>==|!=|>=|<=|>|<)
  | (?P<LPAREN>\()
  | (?P<RPAREN>\))
  | (?P<STR>"[^"]*"|'[^']*')
  | (?P<NUM>-?\d+(?:\.\d+)?)
  | (?P<IDENT>[A-Za-z_][A-Za-z0-9_:]*)
""", re.VERBOSE)


def _tokenize(expr: str) -> list[tuple[str, str]]:
    """Découpe l'expression en tokens (type, texte). Remplace l'ancien découpage par recherche de
    sous-chaîne (`if op in expr`), incapable de distinguer un mot-clé booléen d'un mot identique
    apparaissant entre guillemets (ex. `artifact:label == "sales and marketing"`) ni de gérer plus
    d'une comparaison. Lève ValueError sur tout caractère non reconnu — jamais de passage
    silencieux."""
    tokens: list[tuple[str, str]] = []
    pos = 0
    length = len(expr)
    while pos < length:
        m = _TOKEN_RE.match(expr, pos)
        if not m or m.end() == pos:
            raise ValueError(f"Caractère inattendu dans l'expression, autour de : {expr[pos:pos + 12]!r}")
        kind = m.lastgroup
        text = m.group()
        pos = m.end()
        if kind == "WS":
            continue
        if kind in ("ARTIFACT_Q", "ARTIFACT"):
            tokens.append(("OPERAND", text))
        elif kind == "OP":
            tokens.append(("OP", text))
        elif kind == "LPAREN":
            tokens.append(("LPAREN", text))
        elif kind == "RPAREN":
            tokens.append(("RPAREN", text))
        elif kind in ("STR", "NUM"):
            tokens.append(("OPERAND", text))
        else:  # IDENT
            lowered = text.lower()
            if lowered in _KEYWORDS:
                tokens.append((lowered.upper(), text))   # "AND" / "OR" / "NOT"
            else:
                tokens.append(("OPERAND", text))
    return tokens


def _resolve_operand(token: str, ctx: StepContext):
    """Résout un opérande : `rows_count`, `artifact:<nom>` (présence -> bool, ou son chemin en
    texte ; `<nom>` peut être cité — `artifact:"nom avec espace"` — le dépouillement de guillemets
    ci-dessous s'applique alors au nom, en plus du dépouillement générique déjà existant pour un
    littéral cité), ou un littéral (nombre si possible, sinon chaîne)."""
    token = token.strip()
    if token == "rows_count":
        return ctx.rows_count
    if token.startswith("artifact:"):
        name = token[len("artifact:"):].strip("\"'")
        value = ctx.artifacts.get(name)
        return str(value) if value is not None else None
    try:
        return float(token) if "." in token else int(token)
    except ValueError:
        return token.strip("\"'")


class _ExpressionParser:
    """Descente récursive, précédence croissante or < and < not < comparaison/parenthèses —
    voir la grammaire dans le docstring du module. Analyse et évaluation ne sont PAS séparées en
    deux passes (pas d'arbre intermédiaire) : and/or évaluent donc toujours leurs deux membres,
    sans court-circuit — choix délibéré, sans conséquence ici puisqu'aucune résolution d'opérande
    n'a d'effet de bord."""

    def __init__(self, tokens: list[tuple[str, str]], ctx: StepContext):
        self._tokens = tokens
        self._pos = 0
        self._ctx = ctx
        self._depth = 0

    def parse(self) -> bool:
        result = self._or_expr()
        trailing = self._peek()
        if trailing is not None:
            raise ValueError(f"Jeton inattendu après la fin de l'expression : {trailing[1]!r}")
        return result

    def _peek(self):
        return self._tokens[self._pos] if self._pos < len(self._tokens) else None

    def _advance(self):
        tok = self._peek()
        if tok is None:
            raise ValueError("Fin d'expression inattendue.")
        self._pos += 1
        return tok

    def _enter_nested(self):
        self._depth += 1
        if self._depth > _MAX_NESTING_DEPTH:
            raise ValueError("Expression trop imbriquée (parenthèses/négations).")

    def _or_expr(self) -> bool:
        result = self._and_expr()
        while self._peek() and self._peek()[0] == "OR":
            self._advance()
            rhs = self._and_expr()
            result = result or rhs
        return result

    def _and_expr(self) -> bool:
        result = self._unary()
        while self._peek() and self._peek()[0] == "AND":
            self._advance()
            rhs = self._unary()
            result = result and rhs
        return result

    def _unary(self) -> bool:
        if self._peek() and self._peek()[0] == "NOT":
            self._advance()
            self._enter_nested()
            try:
                return not self._unary()
            finally:
                self._depth -= 1
        return self._primary()

    def _primary(self) -> bool:
        tok = self._peek()
        if tok is None:
            raise ValueError("Expression incomplète.")
        if tok[0] == "LPAREN":
            self._advance()
            self._enter_nested()
            try:
                result = self._or_expr()
            finally:
                self._depth -= 1
            close = self._peek()
            if not close or close[0] != "RPAREN":
                raise ValueError("Parenthèse fermante manquante.")
            self._advance()
            return result
        return self._comparison()

    def _comparison(self) -> bool:
        left_tok = self._advance()
        if left_tok[0] != "OPERAND":
            raise ValueError(f"Opérande attendu, trouvé {left_tok[1]!r}.")
        op_tok = self._peek()
        if not op_tok or op_tok[0] != "OP":
            raise ValueError(f"Opérateur de comparaison attendu après {left_tok[1]!r}.")
        self._advance()
        right_tok = self._advance()
        if right_tok[0] != "OPERAND":
            raise ValueError(f"Opérande attendu, trouvé {right_tok[1]!r}.")
        left_val = _resolve_operand(left_tok[1], self._ctx)
        right_val = _resolve_operand(right_tok[1], self._ctx)
        try:
            return _OPS[op_tok[1]](left_val, right_val)
        except TypeError as e:
            raise ValueError(f"Comparaison invalide ({left_val!r} {op_tok[1]} {right_val!r}) : {e}")


def _evaluate(expression: str, ctx: StepContext) -> bool:
    expr = (expression or "").strip()
    if not expr:
        raise ValueError("Expression vide.")
    tokens = _tokenize(expr)
    return _ExpressionParser(tokens, ctx).parse()


class ConditionStep(BaseStep):
    REQUIRES: set[str] = set()
    PRODUCES: set[str] = set()
    OUTPUT_PORTS = ("true", "false")
    IS_ROUTING_NODE = True

    def run(self, ctx: StepContext, cancel_event=None, on_progress=None) -> StepResult:
        expression = self.config.get("expression", "")
        try:
            active = _evaluate(expression, ctx)
        except ValueError as e:
            return StepResult(success=False, error=f"Expression invalide : {e}")

        port = "true" if active else "false"
        ctx.log(f"Condition « {expression} » → {port}")
        return StepResult(success=True, active_port=port)

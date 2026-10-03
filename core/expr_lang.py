"""
DataScheduler — core/expr_lang.py
Évaluateur d'expressions partagé — généralisation de la grammaire booléenne autrefois propre à
core/steps/condition.py (chantier vocabulaire des conditions), étendue de « comparaisons
combinables via and/or/not » à un petit langage de calcul (arithmétique + fonctions texte/date).
Trois consommateurs : ConditionStep (core/steps/condition.py, détermine son port de sortie),
le token {expr:...} (StepContext.resolve_tokens(), core/steps/base.py, utilisable dans n'importe
quel champ templaté), et la validation à blanc (core/pipeline.py::dry_run_pipeline(), via
compile_expression() seul — voir plus bas pourquoi ce découplage existe).

Grammaire volontairement non-eval() (config_json reste un blob éditable à la main — ne doit
jamais devenir un vecteur d'exécution de code) : tokenizer dédié + descente récursive vers un
petit AST, aucune fonction accessible hors de la liste blanche _FUNCTIONS ci-dessous.

Analyse et évaluation sont délibérément DEUX passes séparées (contrairement à l'ancien design
mono-passe de condition.py) :
    compile_expression(expr) -> _Node   — tokenize + parse, AUCUN ctx requis, valide aussi
                                           l'arité des appels de fonction à ce stade.
    evaluate(expr, ctx)      -> Any     — compile_expression(expr).eval(ctx)

Ce découplage existe pour que dry_run_pipeline() puisse valider la SYNTAXE d'une expression
avant toute exécution réelle (ctx.variables/ctx.artifacts ne sont peuplés qu'à l'exécution) sans
produire de faux positif : évaluer contre un ctx factice ferait échouer à tort toute expression
référençant une variable/un artefact légitime mais pas encore connu à cet instant (ex. var:y
résolu à None puis utilisé dans une division). En n'appelant jamais .eval(), le dry-run ne
détecte que les erreurs de forme (jeton inattendu, parenthèse manquante, fonction inconnue,
arité invalide) — jamais une « erreur » qui dépend simplement du moment où on regarde.
"""

import operator
import re
from datetime import datetime, timedelta

from core.date_tokens import translate_date_format

# Même convention ISO-8601 que core/steps/extract_variables.py (_ISO_DATE/_ISO_DATETIME) :
# l'ordre lexicographique d'une chaîne ISO coïncide avec l'ordre chronologique, ce qui permet à
# ce module de comparer/dater sans jamais faire transiter un objet date/datetime réel à travers
# ctx.variables — redéclarées ici plutôt qu'importées (ces constantes sont privées à ce fichier
# côté extract_variables.py) ; si l'une des deux évolue, l'autre doit être mise à jour en miroir.
_ISO_DATE = "%Y-%m-%d"
_ISO_DATETIME = "%Y-%m-%dT%H:%M:%S"

_OPS = {
    "==": operator.eq,
    "!=": operator.ne,
    ">=": operator.ge,
    "<=": operator.le,
    ">":  operator.gt,
    "<":  operator.lt,
}

_KEYWORDS = {"and", "or", "not"}

# Profondeur max de récursion (parenthèses imbriquées, chaîne de "not", arguments de fonction
# imbriqués) — une vraie expression humaine ne dépasse jamais quelques niveaux ; ce plafond évite
# qu'une expression pathologique (config_json édité à la main) ne fasse planter le parseur par
# une RecursionError Python non catchée, plutôt qu'un ValueError propre comme tout le reste de
# cette grammaire.
_MAX_NESTING_DEPTH = 50

# Un seul regex combiné, alternatives les plus spécifiques en premier (l'ordre conditionne quelle
# alternative "gagne" à une position donnée) :
#   - artifact:"nom cité"/'nom cité' et var:"nom cité"/'nom cité' avant leur forme non citée,
#     elles-mêmes avant l'identifiant générique (sinon "artifact:xxx"/"var:xxx" seraient déjà
#     entièrement absorbés par IDENT, qui tolère ":" mais pas les tirets/espaces/accents d'un nom
#     réel — voir docstring de _resolve_operand).
#   - opérateurs à 2 caractères (==, !=, >=, <=) avant ceux à 1 caractère (>, <), sinon ">="
#     serait scindé en ">" puis un "=" orphelin non reconnu.
#   - NUM est désormais TOUJOURS non signé (pas de "-?" en tête) : un signe moins est un token
#     MINUS à part entière, utilisable en opérateur binaire (soustraction) OU en préfixe unaire
#     (via la grammaire, pas le lexer) — avant ce changement, "rows_count - 5" se tokenisait en
#     deux OPERAND adjacents sans opérateur entre eux (le "-5" était absorbé tout entier comme un
#     seul nombre signé), ce qui rend la soustraction impossible à parser. Voir _ExpressionParser.
#   - "-" reste volontairement AUTORISÉ (non exclu) dans un nom artifact:/var: non cité — exigé
#     par les _step_key de type UUID (ex. artifact:3f9a1c2b-...), déjà couvert par un test
#     existant. Conséquence acceptée : "artifact:x-5" sans espace est lu comme UN SEUL nom
#     ("x-5"), jamais comme "artifact:x moins 5" — un espace désambiguïse
#     ("artifact:x - 5" se tokenise bien en nom puis opérateur). "+", "*", "/", "," restent eux
#     exclus du nom : aucun usage existant ne s'appuyait dessus avant l'ajout de l'arithmétique.
_TOKEN_RE = re.compile(r"""
    (?P<WS>\s+)
  | (?P<ARTIFACT_Q>artifact:"[^"]*"|artifact:'[^']*')
  | (?P<ARTIFACT>artifact:[^\s()=!<>+*/,]+)
  | (?P<VAR_Q>var:"[^"]*"|var:'[^']*')
  | (?P<VAR>var:[^\s()=!<>+*/,]+)
  | (?P<OP>==|!=|>=|<=|>|<)
  | (?P<LPAREN>\()
  | (?P<RPAREN>\))
  | (?P<COMMA>,)
  | (?P<PLUS>\+)
  | (?P<MINUS>-)
  | (?P<STAR>\*)
  | (?P<SLASH>/)
  | (?P<STR>"[^"]*"|'[^']*')
  | (?P<NUM>\d+(?:\.\d+)?)
  | (?P<IDENT>[A-Za-z_][A-Za-z0-9_:]*)
""", re.VERBOSE)


def _tokenize(expr: str) -> list[tuple[str, str]]:
    """Découpe l'expression en tokens (type, texte). Lève ValueError sur tout caractère non
    reconnu — jamais de passage silencieux."""
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
        if kind in ("ARTIFACT_Q", "ARTIFACT", "VAR_Q", "VAR"):
            tokens.append(("OPERAND", text))
        elif kind == "OP":
            tokens.append(("OP", text))
        elif kind in ("LPAREN", "RPAREN", "COMMA", "PLUS", "MINUS", "STAR", "SLASH"):
            tokens.append((kind, text))
        elif kind in ("STR", "NUM"):
            tokens.append(("OPERAND", text))
        else:  # IDENT
            lowered = text.lower()
            if lowered in _KEYWORDS:
                tokens.append((lowered.upper(), text))   # "AND" / "OR" / "NOT"
            else:
                tokens.append(("IDENT", text))
    return tokens


def _resolve_operand(token: str, ctx):
    """Résout un opérande : `rows_count`, `artifact:<nom>` (présence -> bool, ou son chemin en
    texte ; `<nom>` peut être cité — `artifact:"nom avec espace"`), `var:<nom>` (valeur déjà
    typée — int/float/str, ou une chaîne ISO-8601 pour une date/heure — telle que déposée dans
    ctx.variables, jamais repassée par str() contrairement à artifact: puisqu'un calcul/une
    comparaison numérique ou chronologique a besoin du type d'origine, pas de son rendu texte),
    ou un littéral (nombre si possible, sinon chaîne)."""
    token = token.strip()
    if token == "rows_count":
        return ctx.rows_count
    if token.startswith("artifact:"):
        name = token[len("artifact:"):].strip("\"'")
        value = ctx.artifacts.get(name)
        return str(value) if value is not None else None
    if token.startswith("var:"):
        name = token[len("var:"):].strip("\"'")
        return ctx.variables.get(name)
    try:
        return float(token) if "." in token else int(token)
    except ValueError:
        return token.strip("\"'")


# ──────────────────────────────────────────────
#  AST — construit par _ExpressionParser, évalué par .eval(ctx)
# ──────────────────────────────────────────────

class _Lit:
    __slots__ = ("value",)

    def __init__(self, value):
        self.value = value

    def eval(self, ctx):
        return self.value


class _Operand:
    __slots__ = ("raw",)

    def __init__(self, raw: str):
        self.raw = raw

    def eval(self, ctx):
        return _resolve_operand(self.raw, ctx)


class _UnaryOp:
    __slots__ = ("op", "operand")

    def __init__(self, op: str, operand):
        self.op = op
        self.operand = operand

    def eval(self, ctx):
        value = self.operand.eval(ctx)
        if self.op == "-":
            try:
                return operator.neg(value)
            except TypeError as e:
                raise ValueError(f"Négation invalide ({value!r}) : {e}")
        return not value   # "not"


class _BinOp:
    __slots__ = ("op", "left", "right")

    _ARITH = {"+": operator.add, "-": operator.sub, "*": operator.mul, "/": operator.truediv}

    def __init__(self, op: str, left, right):
        self.op = op
        self.left = left
        self.right = right

    def eval(self, ctx):
        left_val = self.left.eval(ctx)
        right_val = self.right.eval(ctx)
        if self.op == "and":
            return left_val and right_val
        if self.op == "or":
            return left_val or right_val
        if self.op in _OPS:
            try:
                return _OPS[self.op](left_val, right_val)
            except TypeError as e:
                raise ValueError(f"Comparaison invalide ({left_val!r} {self.op} {right_val!r}) : {e}")
        fn = self._ARITH[self.op]
        try:
            return fn(left_val, right_val)
        except TypeError as e:
            raise ValueError(f"Opération invalide ({left_val!r} {self.op} {right_val!r}) : {e}")
        except ZeroDivisionError:
            raise ValueError(f"Division par zéro ({left_val!r} {self.op} {right_val!r}).")


class _Call:
    __slots__ = ("name", "args")

    def __init__(self, name: str, args: list):
        self.name = name
        self.args = args

    def eval(self, ctx):
        fn, _ = _FUNCTIONS[self.name]
        values = [a.eval(ctx) for a in self.args]
        try:
            return fn(*values)
        except ValueError as e:
            raise ValueError(f"Fonction « {self.name} » : {e}")
        except TypeError as e:
            raise ValueError(f"Fonction « {self.name} » : {e}")


# ──────────────────────────────────────────────
#  Bibliothèque de fonctions — liste blanche explicite, jamais de dispatch générique/eval()
# ──────────────────────────────────────────────

def _parse_iso(value: str) -> tuple[datetime, str]:
    """Essaie datetime (motif le plus strict/long) avant date seule — même ordre que
    extract_variables.py pour "datetime" vs "date". Retourne (objet, format ISO d'origine) pour
    pouvoir re-émettre dans le même format par défaut."""
    value = str(value)
    try:
        return datetime.strptime(value, _ISO_DATETIME), _ISO_DATETIME
    except ValueError:
        pass
    try:
        return datetime.strptime(value, _ISO_DATE), _ISO_DATE
    except ValueError:
        raise ValueError(f"valeur {value!r} n'est pas une date ISO-8601 valide.")


def _fn_date_add(date_str, days, fmt=None):
    dt, iso_fmt = _parse_iso(date_str)
    dt = dt + timedelta(days=int(days))
    if fmt:
        return dt.strftime(translate_date_format(str(fmt)))
    return dt.strftime(iso_fmt)


def _fn_now():
    return datetime.now().strftime(_ISO_DATETIME)


def _fn_today():
    return datetime.now().strftime(_ISO_DATE)


def _fn_fmt(value, fmt):
    dt, _ = _parse_iso(value)
    return dt.strftime(translate_date_format(str(fmt)))


def _fn_concat(*args):
    return "".join(str(a) for a in args)


def _fn_upper(s):
    return str(s).upper()


def _fn_lower(s):
    return str(s).lower()


def _fn_round(number, ndigits):
    try:
        return round(number, int(ndigits))
    except TypeError as e:
        raise ValueError(str(e))


# nom exposé -> (implémentation, (arité_min, arité_max ou None=illimité))
_FUNCTIONS: dict[str, tuple] = {
    "date_add": (_fn_date_add, (2, 3)),
    "now":      (_fn_now, (0, 0)),
    "today":    (_fn_today, (0, 0)),
    "fmt":      (_fn_fmt, (2, 2)),
    "concat":   (_fn_concat, (1, None)),
    "upper":    (_fn_upper, (1, 1)),
    "lower":    (_fn_lower, (1, 1)),
    "round":    (_fn_round, (2, 2)),
}


# ──────────────────────────────────────────────
#  Parseur — descente récursive, précédence croissante :
#  or < and < not < comparaison (optionnelle) < additif < multiplicatif < unaire < primaire
# ──────────────────────────────────────────────

class _ExpressionParser:
    def __init__(self, tokens: list[tuple[str, str]]):
        self._tokens = tokens
        self._pos = 0
        self._depth = 0

    def parse(self):
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
            raise ValueError("Expression trop imbriquée (parenthèses/négations/appels de fonction).")

    def _or_expr(self):
        result = self._and_expr()
        while self._peek() and self._peek()[0] == "OR":
            self._advance()
            result = _BinOp("or", result, self._and_expr())
        return result

    def _and_expr(self):
        result = self._not_expr()
        while self._peek() and self._peek()[0] == "AND":
            self._advance()
            result = _BinOp("and", result, self._not_expr())
        return result

    def _not_expr(self):
        if self._peek() and self._peek()[0] == "NOT":
            self._advance()
            self._enter_nested()
            try:
                return _UnaryOp("not", self._not_expr())
            finally:
                self._depth -= 1
        return self._comparison()

    def _comparison(self):
        left = self._additive()
        tok = self._peek()
        if tok and tok[0] == "OP":
            self._advance()
            right = self._additive()
            return _BinOp(tok[1], left, right)
        return left

    def _additive(self):
        result = self._multiplicative()
        while self._peek() and self._peek()[0] in ("PLUS", "MINUS"):
            op = self._advance()
            result = _BinOp("+" if op[0] == "PLUS" else "-", result, self._multiplicative())
        return result

    def _multiplicative(self):
        result = self._unary()
        while self._peek() and self._peek()[0] in ("STAR", "SLASH"):
            op = self._advance()
            result = _BinOp("*" if op[0] == "STAR" else "/", result, self._unary())
        return result

    def _unary(self):
        if self._peek() and self._peek()[0] == "MINUS":
            self._advance()
            return _UnaryOp("-", self._unary())
        return self._primary()

    def _primary(self):
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
        if tok[0] == "IDENT" and self._next_is_lparen():
            return self._call()
        if tok[0] in ("OPERAND", "IDENT"):
            self._advance()
            return _Operand(tok[1])
        raise ValueError(f"Opérande attendu, trouvé {tok[1]!r}.")

    def _next_is_lparen(self) -> bool:
        nxt = self._tokens[self._pos + 1] if self._pos + 1 < len(self._tokens) else None
        return nxt is not None and nxt[0] == "LPAREN"

    def _call(self):
        name_tok = self._advance()
        name = name_tok[1]
        if name not in _FUNCTIONS:
            raise ValueError(f"Fonction inconnue : {name!r}.")
        self._advance()   # LPAREN
        self._enter_nested()
        try:
            args = []
            if not (self._peek() and self._peek()[0] == "RPAREN"):
                args.append(self._or_expr())
                while self._peek() and self._peek()[0] == "COMMA":
                    self._advance()
                    args.append(self._or_expr())
            close = self._peek()
            if not close or close[0] != "RPAREN":
                raise ValueError(f"Parenthèse fermante manquante pour l'appel de « {name} ».")
            self._advance()
        finally:
            self._depth -= 1
        min_a, max_a = _FUNCTIONS[name][1]
        if len(args) < min_a or (max_a is not None and len(args) > max_a):
            raise ValueError(f"Fonction « {name} » : nombre d'arguments invalide ({len(args)}).")
        return _Call(name, args)


def compile_expression(expr: str):
    """Tokenize + parse SEULEMENT — aucun ctx requis, n'évalue rien. Valide la forme de
    l'expression (jetons, parenthèses, arité des appels de fonction) indépendamment de toute
    donnée réelle — c'est ce qui permet à dry_run_pipeline() de détecter une expression
    malformée avant exécution sans jamais produire de faux positif sur une référence var:/
    artifact: légitime mais pas encore connue à cet instant."""
    text = (expr or "").strip()
    if not text:
        raise ValueError("Expression vide.")
    tokens = _tokenize(text)
    return _ExpressionParser(tokens).parse()


def evaluate(expr: str, ctx):
    """Compile puis évalue contre un ctx réel (StepContext ou tout objet exposant .rows_count/
    .artifacts/.variables). Résultat typé (bool/int/float/str) — pas de coercition ici, chaque
    appelant décide (ConditionStep applique la troncature de vérité Python, resolve_tokens()
    stringifie)."""
    return compile_expression(expr).eval(ctx)

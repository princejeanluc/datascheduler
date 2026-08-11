"""
DataScheduler — core/pipeline.py
Exécuteur de pipeline : itère sur les PipelineStep dans l'ordre et passe le contexte.
"""

import hashlib
import json
import logging
import threading
import time
from datetime import datetime
from pathlib import Path

from database import db_manager as db
from core.steps import get_step, get_step_requirements, step_produces_output_file, StepContext, StepResult

logger = logging.getLogger(__name__)

RETRY_DELAY_S = 5


# ──────────────────────────────────────────────
#  RÉSULTAT D'EXÉCUTION
# ──────────────────────────────────────────────

class PipelineResult:
    def __init__(self):
        self.success       = False
        self.rows_exported = 0
        self.remote_path   = None
        self.error         = None
        self.log_lines     = []
        self.started_at    = datetime.utcnow()
        self.finished_at   = None
        # ID du PipelineRun créé pour cette exécution — absent (None) si l'échec est survenu
        # avant l'enregistrement du run (pipeline introuvable, aucune étape, reprise invalide...).
        # Permet à l'UI de proposer une reprise sans requête DB supplémentaire (chantier J.2).
        self.run_id: int | None = None

    def log(self, msg: str):
        ts = datetime.utcnow().strftime("%H:%M:%S")
        self.log_lines.append(f"[{ts}] {msg}")
        logger.info(msg)

    def fail(self, msg: str):
        self.error = msg
        self.log(f"ERREUR : {msg}")

    def finish(self):
        self.finished_at = datetime.utcnow()

    @property
    def duration_s(self) -> float:
        if self.finished_at:
            return (self.finished_at - self.started_at).total_seconds()
        return 0.0

    @property
    def log_text(self) -> str:
        return "\n".join(self.log_lines)


# ──────────────────────────────────────────────
#  VERROU ANTI-CHEVAUCHEMENT (opt-in par pipeline)
# ──────────────────────────────────────────────

_active_runs: dict[int, threading.Event] = {}
_active_runs_lock = threading.Lock()


def is_pipeline_running(pipeline_id: int) -> bool:
    """Indique si un run de ce pipeline est actuellement en cours."""
    with _active_runs_lock:
        return pipeline_id in _active_runs


def request_cancel(pipeline_id: int) -> bool:
    """
    Demande l'arrêt coopératif d'un run en cours pour ce pipeline — effectif à la
    prochaine limite d'étape, pas instantanément. Retourne False si aucun run n'était
    en cours.
    """
    with _active_runs_lock:
        event = _active_runs.get(pipeline_id)
    if event is None:
        return False
    event.set()
    return True


def is_cancel_requested(pipeline_id: int) -> bool:
    """
    Indique si un arrêt a été demandé pour le run en cours de ce pipeline mais n'a pas
    encore abouti (l'étape en cours n'a pas encore atteint sa prochaine limite) — utilisé
    par l'UI pour afficher un état "Arrêt en cours" plutôt que de laisser l'utilisateur
    sans retour visuel après avoir demandé une interruption (voir PipelinesView.refresh()).
    """
    with _active_runs_lock:
        event = _active_runs.get(pipeline_id)
    return bool(event and event.is_set())


# ──────────────────────────────────────────────
#  VALIDATION STATIQUE D'UNE SÉQUENCE D'ÉTAPES
# ──────────────────────────────────────────────

def _duplicate_output_name_errors(steps: list[dict]) -> list[str]:
    """
    Un nom de sortie personnalisé (config["output_name"]/["output_names"] — voir
    core/pipeline.py, publication d'alias en plus de _step_key) utilisé par plusieurs étapes
    du même pipeline se marcherait dessus dans ctx.artifacts. Partagé par
    validate_step_sequence() et validate_pipeline_graph() — même règle dans les deux éditeurs.
    """
    seen: dict[str, list[str]] = {}
    for step in steps:
        label = step.get("label") or step.get("step_type", "")
        config = step.get("config") or {}
        names = []
        if config.get("output_name"):
            names.append(config["output_name"])
        names.extend(config.get("output_names") or [])
        for name in names:
            seen.setdefault(name, []).append(label)

    errors = []
    for name, labels in seen.items():
        if len(labels) > 1:
            errors.append(
                f"Le nom de sortie « {name} » est utilisé par plusieurs étapes "
                f"({', '.join(labels)}) — chaque nom doit être unique dans le pipeline."
            )
    return errors

def validate_step_sequence(steps: list[dict]) -> tuple[list[str], list[str]]:
    """
    Simule la séquence d'étapes (sans rien exécuter) et vérifie que chaque étape trouve
    dans le contexte ce qu'elle REQUIRES, d'après ce que les étapes précédentes PRODUCES.

    Une étape peut cibler explicitement une source antérieure précise via
    config["reads_from_step_key"] (sélecteur "Source" de l'éditeur) — dans ce cas la
    vérification porte sur cette clé spécifique plutôt que sur le tag générique
    "output_file" (comportement par défaut, inchangé, quand aucune cible n'est choisie).

    Retourne (erreurs_bloquantes, avertissements) :
      - une étape normale dont un REQUIRES n'est pas satisfait → erreur bloquante.
      - une étape "toujours exécutée" (run_always) dans le même cas → avertissement
        seulement, car son contexte réel au moment de l'exécution est imprévisible
        (elle peut tourner après un échec précoce qui a empêché la production attendue).
    """
    errors: list[str] = []
    warnings: list[str] = []
    available: set[str] = set()
    available_keys: set[str] = set()

    for i, step in enumerate(steps):
        step_type  = step.get("step_type", "")
        label      = step.get("label") or step_type
        run_always = bool(step.get("run_always"))
        config     = step.get("config") or {}

        requires, produces = get_step_requirements(step_type)
        # Complète le PRODUCES statique par la production réelle de CETTE instance — un step
        # comme SPARK_SQL a un PRODUCES vide (conditionnel à sa config, pas connaissable
        # statiquement par la classe), mais peut légitimement être ciblé comme source explicite.
        if step_produces_output_file(step_type, config):
            produces = produces | {"output_file"}
        target_key = config.get("reads_from_step_key")

        # Un chemin source explicite (DB_LOAD/FTP_UPLOAD/LOCAL_COPY) rend l'étape autonome —
        # elle ne dépend plus de ctx.output_file, donc "output_file" ne doit plus être exigé
        # par cette vérification statique, qui ne connaît que REQUIRES/PRODUCES déclarés (elle
        # ignore explicit_path). Sans ce retrait, un pipeline à une seule étape avec un chemin
        # explicite est bloqué à l'enregistrement alors qu'il s'exécute correctement.
        if config.get("explicit_path"):
            requires = requires - {"output_file"}

        if requires:
            if target_key:
                missing = target_key not in available_keys
                msg = (
                    f"Étape {i + 1} ({label}) : la source ciblée n'a pas encore été produite "
                    "à ce stade (étape supprimée, déplacée après, ou jamais réenregistrée)."
                )
            else:
                missing = bool(requires - available)
                msg = f"Étape {i + 1} ({label}) : nécessite {', '.join(sorted(requires))}, non garanti par les étapes précédentes."

            if missing:
                if run_always:
                    warnings.append(msg)
                else:
                    errors.append(msg)

        available |= produces
        step_key = config.get("_step_key")
        if produces and step_key:
            available_keys.add(step_key)

    errors.extend(_duplicate_output_name_errors(steps))
    return errors, warnings


# ──────────────────────────────────────────────
#  EXÉCUTION D'UNE ÉTAPE — timeout + relance (partagé linéaire/graphe)
# ──────────────────────────────────────────────

def _run_step_with_policy(executor, ctx, step, step_progress, result):
    """
    Exécute une étape avec sa politique de délai (timeout_s) et de relance (retry_count).
    Un timeout est traité comme n'importe quel échec par la boucle de relance qui suit
    (retenter a du sens pour un blocage réseau transitoire).

    CPython ne peut pas tuer un thread de force : un appel réellement bloqué (socket SSH/
    FTP/HTTP sans timeout propre) continue en arrière-plan au-delà de timeout_s — le
    *pipeline*, lui, avance et marque l'étape en échec. C'est le compromis standard des
    orchestrateurs sur exécuteur non-forké (ex : execution_timeout d'Airflow) ; une vraie
    interruption exigerait du multiprocessing et une refonte de StepContext pour être sûre
    entre process, hors scope. Volontairement pas de concurrent.futures.ThreadPoolExecutor
    ici : son shutdown(wait=True) implicite à la sortie d'un `with` bloquerait quand même
    jusqu'à la fin de l'appel bloquant (annulant l'effet du timeout), et ses threads sont
    suivis par un joiner atexit qui empêcherait la fermeture de l'app tant qu'un appel
    resterait bloqué — un thread daemon simple n'a ni l'un ni l'autre défaut.
    """
    retry_count = step.retry_count or 0
    timeout_s   = step.timeout_s or 0
    attempt     = 0
    while True:
        if not timeout_s:
            step_result = executor.run(ctx, on_progress=step_progress)
        else:
            box = {}
            def _runner():
                box["result"] = executor.run(ctx, on_progress=step_progress)
            t = threading.Thread(target=_runner, daemon=True, name="step_timeout")
            t.start()
            t.join(timeout_s)
            if t.is_alive():
                step_result = StepResult(success=False, error=f"Délai dépassé ({timeout_s}s) — étape abandonnée.")
            else:
                step_result = box.get("result") or StepResult(success=False, error="Étape terminée sans résultat.")

        for line in ctx.log_lines:
            result.log_lines.append(line)
        ctx.log_lines.clear()

        if step_result.success or attempt >= retry_count:
            return step_result
        attempt += 1
        result.log(f"Tentative {attempt}/{retry_count} après échec : {step_result.error}")
        time.sleep(RETRY_DELAY_S)


# ──────────────────────────────────────────────
#  REPRISE DEPUIS L'ÉCHEC (chantier J.2) — empreintes, purge, snapshot
# ──────────────────────────────────────────────

def _step_fingerprint(config: dict) -> str:
    """Empreinte stable de la config d'une étape — sert à détecter qu'une étape déjà "réussie"
    lors d'un run précédent a été modifiée depuis (sa _step_key, elle, survit à une édition :
    save_steps()/save_pipeline_graph() ne la régénèrent jamais)."""
    return hashlib.sha1(json.dumps(config, sort_keys=True).encode("utf-8")).hexdigest()


def _edges_fingerprint(edges) -> str | None:
    """None pour un pipeline linéaire (pas d'arêtes) — distinct d'une empreinte d'une liste
    vide, pour ne jamais invalider une reprise sur un pipeline qui n'a jamais eu d'arêtes."""
    if not edges:
        return None
    canon = sorted((e.from_step_key, e.from_port, e.to_step_key, e.to_port) for e in edges)
    return hashlib.sha1(json.dumps(canon).encode("utf-8")).hexdigest()


def _purge_resumable_run(run) -> None:
    """Supprime les fichiers temporaires référencés par un état de reprise devenu périmé (un
    nouveau run pour ce pipeline démarre, repris ou non, mais pas CE run précis) et efface la
    colonne — appelé par run_pipeline() avant toute exécution, sous _active_runs_lock."""
    try:
        state = json.loads(run.resumable_state_json or "{}")
    except (ValueError, TypeError):
        state = {}
    for p in (state.get("artifacts") or {}).values():
        path = Path(p)
        if path.exists():
            try:
                path.unlink()
            except OSError:
                pass
    db.clear_resumable_state(run.id)


def _build_resumable_state_json(steps, edges, completed_step_keys: set[str],
                                 active_ports: dict[str, str], ctx: StepContext) -> str:
    """Snapshot persisté quand un run échoue/est annulé avec au moins une étape déjà réussie —
    voir _step_fingerprint()/_edges_fingerprint() pour la détection de fraîcheur à la reprise."""
    configs_by_key: dict[str, dict] = {}
    for s in steps:
        cfg = json.loads(s.config_json or "{}")
        k = cfg.get("_step_key")
        if k:
            configs_by_key[k] = cfg
    step_fingerprints = {
        k: _step_fingerprint(configs_by_key[k])
        for k in completed_step_keys if k in configs_by_key
    }
    state = {
        "completed_step_keys": sorted(completed_step_keys),
        "step_fingerprints":   step_fingerprints,
        "edges_fingerprint":   _edges_fingerprint(edges),
        "active_ports":        {k: v for k, v in active_ports.items() if k in completed_step_keys},
        # Snapshot complet de ctx.artifacts (pas seulement les entrées indexées par
        # completed_step_keys) — une étape juste après le préfixe repris peut lire
        # ctx.output_file par défaut (sans reads_from_step_key explicite), ou un alias
        # output_name, qui doivent donc aussi survivre au réamorçage.
        "artifacts":           {k: str(v) for k, v in ctx.artifacts.items() if isinstance(v, Path)},
        "rows_count":          ctx.rows_count,
    }
    return json.dumps(state)


# ──────────────────────────────────────────────
#  EXÉCUTION LINÉAIRE (comportement historique, inchangé)
# ──────────────────────────────────────────────

def _execute_linear(steps, ctx, progress, result, cancel_event,
                     skip_step_keys: frozenset = frozenset()) -> tuple:
    """
    Boucle d'exécution actuelle, extraite telle quelle de run_pipeline() — chemin emprunté
    pour tout pipeline sans arête explicite (`db.get_edges()` vide), donc pour tous les
    pipelines existants et pour l'éditeur linéaire (PipelineEditorDialog), inchangés par le
    chantier 6a. Retourne (pipeline_failed, pipeline_cancelled, completed_step_keys, {}) — le
    4e élément (ports actifs) est toujours vide en mode linéaire, présent uniquement pour un
    type de retour uniforme avec _execute_graph (chantier J.2).

    skip_step_keys (chantier J.2) : étapes déjà réussies lors d'un run précédent, dont la
    sortie a été réamorcée dans ctx.artifacts par run_pipeline() avant l'appel — on ne les
    ré-exécute pas, on se contente de les compter comme réussies.
    """
    total = len(steps)
    pipeline_failed  = False
    pipeline_cancelled = False
    completed_step_keys: set = set(skip_step_keys)

    for i, step in enumerate(steps):
        if cancel_event.is_set():
            pipeline_cancelled = True
            result.fail("Exécution interrompue par l'utilisateur.")
            break

        step_type  = str(step.step_type).replace("StepType.", "")
        step_label = step.label or step_type
        config     = json.loads(step.config_json or "{}")
        step_key   = config.get("_step_key")

        if step_key and step_key in skip_step_keys:
            next_pct = int((i + 1) * 90 / total)
            result.log(f"--- Étape {i + 1}/{total} : {step_label} déjà réussie (reprise) — ignorée. ---")
            progress(f"Étape {i + 1}/{total} : {step_label} (reprise)", next_pct)
            continue

        if pipeline_failed and not step.run_always:
            continue

        # Ciblage explicite d'une source antérieure (sélecteur "Source" de l'éditeur) —
        # réoriente le slot par défaut avant l'exécution ; l'étape elle-même lit
        # ctx.output_file sans rien savoir de ce réaiguillage.
        target_key = config.get("reads_from_step_key")
        if target_key:
            ctx.output_file = ctx.artifacts.get(target_key)

        # Snapshot pris juste avant l'exécution — sert à détecter après coup si CETTE étape a
        # réellement produit un fichier (voir plus bas), plutôt que de se fier au seul PRODUCES
        # statique de la classe, qui ne peut pas exprimer une production conditionnelle à la
        # config (ex: SPARK_SQL avec la case "Récupérer le résultat").
        before_output_file = ctx.output_file

        base_pct = int(i * 90 / total)       # 0 → 90 %
        next_pct = int((i + 1) * 90 / total)

        def step_progress(msg: str, pct: int, _bp=base_pct, _np=next_pct):
            scaled = _bp + int(pct * (_np - _bp) / 100)
            progress(msg, scaled)

        progress(f"Étape {i + 1}/{total} : {step_label}", base_pct)
        result.log(f"--- Étape {i + 1}/{total} : {step_label} ({step_type}) ---")

        executor    = get_step(step_type, config)
        step_result = _run_step_with_policy(executor, ctx, step, step_progress, result)

        if step_result.success:
            # Publie en plus sous la clé stable de CETTE étape, pour qu'une étape
            # consommatrice ultérieure puisse cibler explicitement "la sortie de
            # cette étape précise" plutôt que "la dernière produite" (voir
            # docs/ARCHITECTURE.md, section StepContext).
            # Détection par comparaison avec le snapshot pris avant l'exécution — pas par le
            # PRODUCES statique de la classe (qui reste vide pour SPARK_SQL/PYTHON_SCRIPT,
            # une production conditionnelle à la config, pas connaissable avant l'exécution).
            if ctx.output_file != before_output_file and step_key:
                ctx.artifacts[step_key] = ctx.output_file
            # Alias cosmétique en plus (chantier UX — ports nommés) : ne remplace jamais la
            # publication sous step_key ci-dessus, qui reste seule responsable du câblage
            # réel (arêtes, reads_from_step_key). Renommer output_name ne casse donc jamais
            # le graphe — seul un script/token qui référençait l'ancien nom cesse de le
            # trouver, un échec visible plutôt qu'une corruption silencieuse.
            output_name = config.get("output_name")
            if output_name:
                ctx.artifacts[output_name] = ctx.output_file
            # Règle de sécurité (chantier J.2) : une étape run_always exécutée APRÈS que le
            # pipeline soit déjà en échec (ex : notification de secours) n'est jamais marquée
            # "complétée" pour une future reprise — sinon une 2e reprise qui échoue à nouveau
            # plus loin sauterait silencieusement cette étape, et l'utilisateur ne serait
            # jamais prévenu du second échec.
            if step_key and not (pipeline_failed and step.run_always):
                completed_step_keys.add(step_key)

        if not step_result.success:
            if not pipeline_failed:
                ctx.extra["failed_step_label"] = step_label
                ctx.extra["error_message"]     = step_result.error
                result.fail(f"Étape {i + 1} ({step_label}) : {step_result.error}")
                pipeline_failed = True
            elif step.run_always:
                result.log(f"Étape 'toujours exécutée' {i + 1} ({step_label}) en échec : {step_result.error}")

    return pipeline_failed, pipeline_cancelled, completed_step_keys, {}


# ──────────────────────────────────────────────
#  EXÉCUTION EN GRAPHE (chantier 6a)
# ──────────────────────────────────────────────

def _topological_order(steps, edges):
    """
    Ordre topologique des étapes (algorithme de Kahn) sur les `_step_key` référencés par les
    arêtes. Tie-break déterministe par `step_order` (ordre d'édition/création). Les étapes sans
    `_step_key` (ne peuvent avoir aucune arête) sont ajoutées à la fin dans leur step_order
    d'origine — cas résiduel, chaque étape enregistrée via _BaseStepConfigDialog.result_step()
    reçoit toujours une clé.

    Retourne None si le graphe contient un cycle.
    """
    configs = {id(s): json.loads(s.config_json or "{}") for s in steps}
    by_key  = {}
    key_order = {}
    for s in steps:
        key = configs[id(s)].get("_step_key")
        if key:
            by_key[key] = s
            key_order[key] = s.step_order

    incoming: dict = {k: [] for k in by_key}
    outgoing: dict = {k: [] for k in by_key}
    for e in edges:
        if e.from_step_key in by_key and e.to_step_key in by_key:
            incoming[e.to_step_key].append(e.from_step_key)
            outgoing[e.from_step_key].append(e.to_step_key)

    in_degree = {k: len(v) for k, v in incoming.items()}
    ready = [k for k, d in in_degree.items() if d == 0]
    ordered_keys: list[str] = []

    while ready:
        ready.sort(key=lambda k: key_order[k])
        k = ready.pop(0)
        ordered_keys.append(k)
        for nxt in outgoing[k]:
            in_degree[nxt] -= 1
            if in_degree[nxt] == 0:
                ready.append(nxt)

    if len(ordered_keys) != len(by_key):
        return None   # cycle détecté

    keyless = sorted(
        (s for s in steps if not configs[id(s)].get("_step_key")),
        key=lambda s: s.step_order,
    )
    return [by_key[k] for k in ordered_keys] + keyless


def _execute_graph(steps, edges, ctx, progress, result, cancel_event,
                    skip_step_keys: frozenset = frozenset(),
                    active_ports_seed: dict | None = None) -> tuple:
    """
    Exécution en ordre topologique. L'échec d'une étape ne bloque que ses dépendants (directs ou
    indirects) — les branches indépendantes continuent. Un nœud à ports multiples (ex:
    ConditionStep) détermine, via `StepResult.active_port`, quelle(s) arête(s) sortante(s) sont
    actives — les autres sont traitées comme une branche non sélectionnée (skip, pas un échec).

    Retourne (pipeline_failed, pipeline_cancelled, completed_step_keys, active_port) — le 4e
    élément est le dict complet des ports actifs en fin d'exécution (chantier J.2, persisté dans
    le snapshot de reprise pour qu'une étape en aval d'un routeur CONDITION déjà réussi retrouve
    la bonne branche active après réamorçage).

    skip_step_keys/active_ports_seed (chantier J.2) : étapes déjà réussies lors d'un run
    précédent — on ne les ré-exécute pas, on restaure directement leur statut "success" (et leur
    port actif) dès qu'on atteint leur tour dans l'ordre topologique, avant que la boucle
    n'atteigne un dépendant (garanti par construction : `order` est topologique).
    """
    active_ports_seed = active_ports_seed or {}
    order = _topological_order(steps, edges)
    if order is None:
        result.fail("Le graphe de ce pipeline contient un cycle — exécution impossible.")
        return True, False, set(), {}

    total = len(order)
    configs  = {id(s): json.loads(s.config_json or "{}") for s in order}
    key_of   = {id(s): configs[id(s)].get("_step_key") for s in order}

    incoming_by_key: dict = {}
    for e in edges:
        incoming_by_key.setdefault(e.to_step_key, []).append(e)

    step_status: dict = {}    # step_key -> "success" | "failed" | "skipped"
    active_port: dict = {}    # step_key -> port actif (steps à ports multiples)
    pipeline_failed    = False
    pipeline_cancelled = False
    completed_step_keys: set = set(skip_step_keys)

    for i, step in enumerate(order):
        if cancel_event.is_set():
            pipeline_cancelled = True
            result.fail("Exécution interrompue par l'utilisateur.")
            break

        step_type  = str(step.step_type).replace("StepType.", "")
        step_label = step.label or step_type
        config     = configs[id(step)]
        step_key   = key_of[id(step)]

        if step_key and step_key in skip_step_keys:
            step_status[step_key] = "success"
            if step_key in active_ports_seed:
                active_port[step_key] = active_ports_seed[step_key]
            next_pct = int((i + 1) * 90 / total)
            result.log(f"--- Étape {i + 1}/{total} : {step_label} déjà réussie (reprise) — ignorée. ---")
            progress(f"Étape {i + 1}/{total} : {step_label} (reprise)", next_pct)
            continue

        incoming    = incoming_by_key.get(step_key, []) if step_key else []
        unavailable = []
        for e in incoming:
            src_status = step_status.get(e.from_step_key)
            if src_status in ("failed", "skipped"):
                unavailable.append(e)
                continue
            src_active_port = active_port.get(e.from_step_key)
            if src_active_port is not None and e.from_port != src_active_port:
                unavailable.append(e)   # branche non sélectionnée par un nœud Condition en amont

        base_pct = int(i * 90 / total)
        next_pct = int((i + 1) * 90 / total)

        should_skip = bool(incoming) and len(unavailable) == len(incoming) and not step.run_always
        if should_skip:
            if step_key:
                step_status[step_key] = "skipped"
            failed_upstream = any(
                step_status.get(e.from_step_key) in ("failed", "skipped") for e in unavailable
            )
            reason = "dépendance en échec" if failed_upstream else "branche non sélectionnée"
            result.log(f"--- Étape {i + 1}/{total} : {step_label} ignorée ({reason}) ---")
            progress(f"Étape {i + 1}/{total} : {step_label} (ignorée)", next_pct)
            continue

        # Réoriente ctx.output_file vers l'artefact de la source, si une unique arête de donnée
        # entrante active existe — généralisation exacte de reads_from_step_key (chantier 3),
        # pilotée ici par la table d'arêtes plutôt que par le champ de config.
        data_incoming = [e for e in incoming if e not in unavailable]
        if len(data_incoming) == 1:
            ctx.output_file = ctx.artifacts.get(data_incoming[0].from_step_key)

        # Snapshot pris juste avant l'exécution — sert à détecter après coup si CETTE étape a
        # réellement produit un fichier (voir plus bas), plutôt que de se fier au seul PRODUCES
        # statique de la classe, qui ne peut pas exprimer une production conditionnelle à la
        # config (ex: SPARK_SQL avec la case "Récupérer le résultat").
        before_output_file = ctx.output_file

        def step_progress(msg: str, pct: int, _bp=base_pct, _np=next_pct):
            scaled = _bp + int(pct * (_np - _bp) / 100)
            progress(msg, scaled)

        progress(f"Étape {i + 1}/{total} : {step_label}", base_pct)
        result.log(f"--- Étape {i + 1}/{total} : {step_label} ({step_type}) ---")

        executor    = get_step(step_type, config)
        step_result = _run_step_with_policy(executor, ctx, step, step_progress, result)

        if step_result.success:
            # Détection par comparaison avec le snapshot pris avant l'exécution — pas par le
            # PRODUCES statique de la classe (voir _execute_linear pour la même logique et son
            # commentaire complet).
            if ctx.output_file != before_output_file and step_key:
                ctx.artifacts[step_key] = ctx.output_file
            output_name = config.get("output_name")
            if output_name:
                ctx.artifacts[output_name] = ctx.output_file
            if step_key:
                step_status[step_key] = "success"
                if step_result.active_port:
                    active_port[step_key] = step_result.active_port
                # Règle de sécurité (chantier J.2) : voir le commentaire équivalent dans
                # _execute_linear — une étape run_always exécutée après un échec déjà survenu
                # n'est jamais marquée "complétée" pour une future reprise.
                if not (pipeline_failed and step.run_always):
                    completed_step_keys.add(step_key)
        else:
            if step_key:
                step_status[step_key] = "failed"
            pipeline_failed = True
            result.log(f"Étape {i + 1} ({step_label}) en échec : {step_result.error}")
            if not ctx.extra.get("failed_step_label"):
                ctx.extra["failed_step_label"] = step_label
                ctx.extra["error_message"]     = step_result.error
                result.fail(f"Étape {i + 1} ({step_label}) : {step_result.error}")

    return pipeline_failed, pipeline_cancelled, completed_step_keys, active_port


# ──────────────────────────────────────────────
#  VALIDATION STATIQUE D'UN GRAPHE (chantier 6a)
# ──────────────────────────────────────────────

def validate_pipeline_graph(steps: list[dict], edges: list[dict]) -> tuple[list[str], list[str]]:
    """
    Équivalent graphe de validate_step_sequence(), pour le futur éditeur graphique (6b) — steps
    et edges en dicts en mémoire, avant toute sauvegarde en base (même moment d'appel que
    validate_step_sequence() dans PipelineEditorDialog._on_save()).

    Détecte les cycles (algorithme de Kahn — si tous les nœuds n'atteignent pas un in-degree de
    0, cycle) puis vérifie que chaque étape dont REQUIRES est non vide a au moins une arête
    entrante — plus besoin du repli heuristique "dernière production" de validate_step_sequence :
    dans un graphe, l'arête EST la déclaration explicite de la source.
    """
    errors: list[str] = []
    warnings: list[str] = []

    by_key = {}
    for s in steps:
        key = (s.get("config") or {}).get("_step_key")
        if key:
            by_key[key] = s

    incoming: dict = {k: [] for k in by_key}
    in_degree: dict = {k: 0 for k in by_key}
    for e in edges:
        if e.get("from_step_key") in by_key and e.get("to_step_key") in by_key:
            incoming[e["to_step_key"]].append(e)
            in_degree[e["to_step_key"]] += 1

    ready = [k for k, d in in_degree.items() if d == 0]
    visited = 0
    outgoing: dict = {k: [] for k in by_key}
    for e in edges:
        if e.get("from_step_key") in by_key and e.get("to_step_key") in by_key:
            outgoing[e["from_step_key"]].append(e["to_step_key"])
    remaining = dict(in_degree)
    while ready:
        k = ready.pop()
        visited += 1
        for nxt in outgoing[k]:
            remaining[nxt] -= 1
            if remaining[nxt] == 0:
                ready.append(nxt)

    if visited != len(by_key):
        errors.append("Le graphe contient un cycle — impossible de déterminer un ordre d'exécution.")
        return errors, warnings

    for key, step in by_key.items():
        step_type  = step.get("step_type", "")
        label      = step.get("label") or step_type
        run_always = bool(step.get("run_always"))
        config     = step.get("config") or {}
        requires, _ = get_step_requirements(step_type)
        # Voir validate_step_sequence() — un chemin source explicite rend l'étape autonome,
        # aucune arête entrante n'est alors nécessaire pour "output_file".
        if config.get("explicit_path"):
            requires = requires - {"output_file"}
        if requires and not incoming.get(key):
            msg = f"Étape « {label} » : nécessite {', '.join(sorted(requires))}, aucune arête entrante."
            (warnings if run_always else errors).append(msg)

    errors.extend(_duplicate_output_name_errors(steps))
    return errors, warnings


# ──────────────────────────────────────────────
#  VALIDATION À BLANC (dry-run) — chantier UX autonomie
# ──────────────────────────────────────────────

class DryRunResult:
    def __init__(self, success: bool, errors: list[str], warnings: list[str],
                 checked_connections: int = 0):
        self.success = success
        self.errors = errors
        self.warnings = warnings
        self.checked_connections = checked_connections


def _steps_to_dicts(pipeline_id: int) -> list[dict]:
    """Même conversion ORM → dict que PipelineEditorDialog._fill_fields()
    (ui/step_editor/pipeline_editor_dialog.py) — la forme attendue par validate_step_sequence()/
    validate_pipeline_graph() et par _STEP_REFERENCES (database/export_import.py)."""
    return [
        {
            "step_type":   str(s.step_type).replace("StepType.", ""),
            "label":       s.label or "",
            "config":      json.loads(s.config_json or "{}"),
            "retry_count": s.retry_count or 0,
            "run_always":  bool(s.run_always),
            "timeout_s":   s.timeout_s or 0,
        }
        for s in db.get_steps(pipeline_id)
    ]


def _test_reference_connection(ref_type: str, config: dict, obj) -> tuple[bool, str]:
    """Teste une connexion réelle pour l'entité déjà résolue par _resolve_reference() —
    réutilise les mêmes connecteurs/config_from_profile que les dialogues de profil et
    core/steps/*.py à l'exécution. Ne lève jamais (les test_connection() sous-jacents non plus)."""
    try:
        if ref_type == "db_profile":
            from core.sql_db import SqlConnector, config_from_profile
            cfg = config_from_profile(config.get("db_type", "ORACLE"), obj)
            result = SqlConnector(cfg).test_connection()
        elif ref_type == "ftp_profile":
            from core.ftp import FtpUploader, config_from_profile
            result = FtpUploader(config_from_profile(obj)).test_connection()
        elif ref_type == "smtp_profile":
            from core.email import EmailSender, config_from_profile
            result = EmailSender(config_from_profile(obj)).test_connection()
        elif ref_type == "edge_profile":
            from core.spark import test_ssh_connection, config_from_profile
            result = test_ssh_connection(config_from_profile(obj))
        elif ref_type == "kerberos_profile":
            # Un ticket Kerberos ne se teste pas seul (kinit doit tourner depuis une machine) —
            # emprunte le profil SSH de cette même étape plutôt que de rester no-op. Si ce
            # profil est lui-même absent, c'est déjà remonté comme erreur bloquante par la
            # boucle de dry_run_pipeline() sur la référence "edge_profile" — ici, avertissement
            # seulement (comportement générique de cette fonction pour tout échec de connexion).
            edge_id = config.get("edge_profile_id")
            if not edge_id:
                return False, "Aucun profil SSH configuré sur cette étape."
            edge_profile = db.get_ssh_profile(edge_id)
            if not edge_profile:
                return False, "Profil SSH introuvable pour le test Kerberos."
            from core.spark import test_kerberos_auth, config_from_profile, kerberos_config_from_profile
            ssh_cfg = config_from_profile(edge_profile)
            krb_cfg = kerberos_config_from_profile(obj)
            result = test_kerberos_auth(ssh_cfg, krb_cfg)
        else:
            # sql_query : une requête enregistrée n'est pas une "connexion" à tester ici —
            # son profil associé (db_profile) est déjà testé séparément dans la même étape.
            return True, "—"
        return result.success, result.message
    except Exception as e:
        return False, str(e)


def dry_run_pipeline(pipeline_id: int, test_connections: bool = True) -> DryRunResult:
    """
    Valide un pipeline sans l'exécuter : (1) la forme (mêmes règles que
    validate_step_sequence()/validate_pipeline_graph(), la même bascule linéaire/graphe que
    run_pipeline() utilise déjà — db.get_edges() non vide → chemin graphe), (2) que chaque
    profil/requête référencé existe encore (réutilise _STEP_REFERENCES/_resolve_reference de
    database/export_import.py — même table déclarative que l'export, pas de logique dupliquée),
    et (3) si test_connections, qu'une connexion réelle réussit pour chaque profil résolu.

    Une référence absente est une erreur bloquante (le pipeline ne peut pas s'exécuter tel
    quel) ; un échec de connexion réel est un avertissement (un blip réseau transitoire ne doit
    pas bloquer indéfiniment, contrairement à une référence structurellement manquante).
    """
    from database.export_import import _STEP_REFERENCES, _resolve_reference

    pipeline = db.get_pipeline(pipeline_id)
    if not pipeline:
        return DryRunResult(success=False, errors=[f"Pipeline ID {pipeline_id} introuvable."], warnings=[])

    steps = _steps_to_dicts(pipeline_id)
    if not steps:
        return DryRunResult(success=False, errors=["Ce pipeline ne contient aucune étape."], warnings=[])

    edges_orm = db.get_edges(pipeline_id)
    if edges_orm:
        edges = [
            {"from_step_key": e.from_step_key, "from_port": e.from_port,
             "to_step_key": e.to_step_key, "to_port": e.to_port}
            for e in edges_orm
        ]
        errors, warnings = validate_pipeline_graph(steps, edges)
    else:
        errors, warnings = validate_step_sequence(steps)

    checked = 0
    for i, step in enumerate(steps):
        step_type = step["step_type"]
        config    = step["config"]
        label     = step["label"] or f"Étape {i + 1}"

        for config_key, ref_type in _STEP_REFERENCES.get(step_type, []):
            raw_id = config.get(config_key)
            if not raw_id:
                continue
            obj, _category = _resolve_reference(ref_type, config, raw_id)
            if obj is None:
                errors.append(
                    f"Étape {i + 1} ({label}) : la référence « {ref_type} » (#{raw_id}) n'existe plus."
                )
                continue
            # sql_query n'est pas une connexion — son profil associé (db_profile) est déjà
            # testé séparément par cette même boucle, rien de plus à vérifier ici.
            if test_connections and ref_type != "sql_query":
                checked += 1
                ok, message = _test_reference_connection(ref_type, config, obj)
                if not ok:
                    warnings.append(
                        f"Étape {i + 1} ({label}) : échec du test de connexion « {ref_type} » — {message}"
                    )

    return DryRunResult(success=not errors, errors=errors, warnings=warnings, checked_connections=checked)


# ──────────────────────────────────────────────
#  EXÉCUTEUR PRINCIPAL
# ──────────────────────────────────────────────

def run_pipeline(pipeline_id: int, on_progress=None, resume_from_run_id: int | None = None) -> PipelineResult:
    """
    Exécute un pipeline en enchaînant ses PipelineStep dans l'ordre.
    Le contexte (fichier, nombre de lignes, etc.) est transmis d'étape en étape.

    Paramètres :
        pipeline_id         : ID du pipeline en base
        on_progress         : callback(step: str, pct: int) pour alimenter l'UI
        resume_from_run_id  : (chantier J.2) reprend depuis l'échec d'un run précédent — les
                               étapes déjà réussies ne sont pas ré-exécutées, leurs artefacts
                               sont réamorcés dans le contexte. Voir _build_resumable_state_json.

    Retourne un PipelineResult (ne lève jamais d'exception).
    """
    result = PipelineResult()
    run_id = None

    def progress(msg: str, pct: int):
        if on_progress:
            on_progress(msg, pct)
        # Écriture incrémentale (chantier N) — visible dès qu'un run existe (run_id devient
        # non-None après create_run() plus bas ; capturé par référence, pas par valeur, donc
        # cette fermeture voit toujours l'état courant). Seul point d'accroche nécessaire :
        # appelée par _execute_linear/_execute_graph à chaque étape ET par chaque exécuteur
        # d'étape via step_progress() — aucun autre fichier n'a besoin d'être modifié.
        # Le chantier O (granularité fine dans SPARK_SQL/SQOOP_EXPORT) multiplie la fréquence
        # d'appel — un incident SQLite transitoire (verrou, antivirus) ne doit jamais faire
        # échouer une vraie opération réseau en cours pour un simple souci d'affichage.
        if run_id is not None:
            try:
                db.update_run_progress(run_id, msg, result.log_text)
            except Exception:
                logger.warning("Échec de la mise à jour de progression du run %s (ignoré).", run_id)

    try:
        # ── Chargement ───────────────────────────
        progress("Chargement…", 0)
        pipeline = db.get_pipeline(pipeline_id)
        if not pipeline:
            result.fail(f"Pipeline ID {pipeline_id} introuvable.")
            result.finish(); return result

        # ── Verrou anti-chevauchement (opt-in) ────
        if pipeline.prevent_overlap and is_pipeline_running(pipeline_id):
            result.fail("Ignoré : ce pipeline est déjà en cours d'exécution.")
            result.finish()
            logger.warning("Pipeline %s : run ignoré (déjà en cours, prevent_overlap=True).", pipeline.name)
            return result

        steps = db.get_steps(pipeline_id)
        if not steps:
            result.fail("Ce pipeline ne contient aucune étape.")
            result.finish(); return result

        result.log(f"Pipeline : {pipeline.name} ({len(steps)} étape(s))")

        # ── Reprise depuis l'échec (chantier J.2) ──
        # Effectuée AVANT create_run() : un échec de validation de reprise ne doit pas laisser
        # de ligne d'historique vide, comme les autres sorties anticipées ci-dessus.
        ctx = StepContext()
        skip_step_keys: set = set()
        active_ports_seed: dict = {}

        # Réclamation protégée par _active_runs_lock — évite que deux run_pipeline() concurrents
        # pour le même pipeline_id ne touchent les mêmes fichiers temporaires du même état de
        # reprise (purge et consommation sont donc mutuellement exclusives avec tout autre run
        # déjà en cours pour ce pipeline).
        # La purge elle-même reste À L'INTÉRIEUR du verrou (pas seulement sa détection) : sinon
        # deux appels concurrents pourraient tous deux lire le même état périmé avant que l'un
        # des deux ait eu le temps de le purger, et tenter de supprimer les mêmes fichiers en
        # parallèle. Section courte (une poignée d'unlink() au pire), coût de contention
        # négligeable sur ce chemin froid (une seule fois par démarrage de run).
        with _active_runs_lock:
            already_running = pipeline_id in _active_runs
            if not already_running:
                stale = db.get_last_resumable_run(pipeline_id)
                if stale and stale.id != resume_from_run_id:
                    _purge_resumable_run(stale)

        if resume_from_run_id:
            if already_running:
                result.fail("Reprise impossible : un autre run de ce pipeline est déjà en cours.")
                result.finish(); return result

            resume_run = db.get_run(resume_from_run_id)
            state = None
            if resume_run and resume_run.resumable_state_json:
                try:
                    state = json.loads(resume_run.resumable_state_json)
                except (ValueError, TypeError):
                    state = None
            if not state:
                result.fail("Reprise impossible : aucun état de reprise disponible pour ce run.")
                result.finish(); return result

            configs_by_key = {}
            for s in steps:
                cfg = json.loads(s.config_json or "{}")
                k = cfg.get("_step_key")
                if k:
                    configs_by_key[k] = cfg
            edges_now = db.get_edges(pipeline_id)

            invalid = False
            for key, fp in (state.get("step_fingerprints") or {}).items():
                cfg = configs_by_key.get(key)
                if cfg is None or _step_fingerprint(cfg) != fp:
                    invalid = True
                    break
            if not invalid and state.get("edges_fingerprint") != _edges_fingerprint(edges_now):
                invalid = True
            if not invalid:
                for p in (state.get("artifacts") or {}).values():
                    if not Path(p).exists():
                        invalid = True
                        break

            if invalid:
                result.fail(
                    "Reprise impossible : le pipeline a été modifié ou les fichiers temporaires "
                    "ont expiré depuis l'échec — relancez une exécution complète."
                )
                result.finish(); return result

            for k, p in (state.get("artifacts") or {}).items():
                ctx.artifacts[k] = Path(p)
            ctx.rows_count     = state.get("rows_count", 0)
            skip_step_keys     = set(state.get("completed_step_keys") or [])
            active_ports_seed  = dict(state.get("active_ports") or {})
            db.clear_resumable_state(resume_from_run_id)
            result.log(
                f"Reprise du run #{resume_from_run_id} — "
                f"{len(skip_step_keys)} étape(s) déjà réussie(s) ignorée(s)."
            )

        # ── Enregistrement du run ─────────────────
        run    = db.create_run(pipeline_id)
        run_id = run.id
        result.run_id = run_id
        result.log(f"Run ID : {run_id}")
        _update_pipeline_status(pipeline_id, "RUNNING")

        # ── Enregistrement du verrou ──────────────
        cancel_event = threading.Event()
        with _active_runs_lock:
            _active_runs[pipeline_id] = cancel_event

        # ── Exécution des étapes ──────────────────
        # Chemin DAG (chantier 6a) seulement si ce pipeline a des arêtes explicites (enregistré
        # au moins une fois via le futur éditeur graphique) — sinon la boucle linéaire actuelle,
        # inchangée : zéro changement de comportement pour tous les pipelines existants.
        edges = db.get_edges(pipeline_id)
        if edges:
            pipeline_failed, pipeline_cancelled, completed_step_keys, active_ports = _execute_graph(
                steps, edges, ctx, progress, result, cancel_event, skip_step_keys, active_ports_seed
            )
        else:
            pipeline_failed, pipeline_cancelled, completed_step_keys, active_ports = _execute_linear(
                steps, ctx, progress, result, cancel_event, skip_step_keys
            )

        # ── Nettoyage des fichiers temporaires ────
        # Sauté quand un état de reprise va être persisté (échec/annulation avec au moins une
        # étape réussie) — les fichiers doivent survivre pour une reprise éventuelle. Comportement
        # inchangé dans tous les autres cas (succès, ou échec/annulation sans rien à reprendre).
        preserve_for_resume = (pipeline_failed or pipeline_cancelled) and bool(completed_step_keys)
        if not preserve_for_resume:
            # Plusieurs artefacts nommés peuvent être vivants simultanément (ex : deux DB_EXTRACT
            # en amont de deux consommateurs différents) — le set déduplique le cas courant où le
            # même Path apparaît à la fois sous "output_file" et sous une clé d'étape spécifique.
            temp_paths = {p for p in ctx.artifacts.values() if isinstance(p, Path)}
            for p in temp_paths:
                if p.exists():
                    try:
                        p.unlink()
                        result.log(f"Fichier temporaire supprimé : {p}")
                    except Exception as e:
                        result.log(f"Avertissement : impossible de supprimer le tmp {p} : {e}")

        resumable_json = None
        if preserve_for_resume:
            resumable_json = _build_resumable_state_json(steps, edges, completed_step_keys, active_ports, ctx)

        # ── Issue ─────────────────────────────────
        result.finish()
        if pipeline_cancelled:
            _update_run(run_id, "CANCELLED", result, resumable_json, resume_from_run_id)
            _update_pipeline_status(pipeline_id, "CANCELLED")
            with _active_runs_lock:
                _active_runs.pop(pipeline_id, None)
            return result

        if pipeline_failed:
            _update_run(run_id, "FAILED", result, resumable_json, resume_from_run_id)
            _update_pipeline_status(pipeline_id, "FAILED")
            with _active_runs_lock:
                _active_runs.pop(pipeline_id, None)
            return result

        result.success       = True
        result.rows_exported = ctx.rows_count
        result.remote_path   = ctx.extra.get("remote_path") or ctx.extra.get("local_path")
        progress("Terminé ✓", 100)
        result.log(
            f"Pipeline terminé en {result.duration_s:.1f}s"
            + (f" — {result.rows_exported:,} lignes exportées." if result.rows_exported else ".")
        )
        _update_run(run_id, "SUCCESS", result, None, resume_from_run_id)
        _update_pipeline_status(pipeline_id, "SUCCESS")
        with _active_runs_lock:
            _active_runs.pop(pipeline_id, None)
        return result

    except Exception as e:
        with _active_runs_lock:
            _active_runs.pop(pipeline_id, None)
        result.fail(f"Exception inattendue : {e}")
        result.finish()
        if run_id:
            _update_run(run_id, "FAILED", result)
        _update_pipeline_status(pipeline_id, "FAILED")
        logger.exception("Erreur pipeline %s", pipeline_id)
        return result


# ──────────────────────────────────────────────
#  HELPERS DB
# ──────────────────────────────────────────────

def _update_run(run_id: int, status: str, result: PipelineResult,
                 resumable_state_json: str | None = None, resumed_from_run_id: int | None = None):
    db.finish_run(
        run_id,
        status=status,
        rows_exported=result.rows_exported,
        remote_path=result.remote_path,
        error_message=result.error,
        log_text=result.log_text,
        resumable_state_json=resumable_state_json,
        resumed_from_run_id=resumed_from_run_id,
    )


def _update_pipeline_status(pipeline_id: int, status: str):
    with db.get_session() as s:
        from database.models import Pipeline
        p = s.get(Pipeline, pipeline_id)
        if p:
            p.last_status = status
            p.last_run_at = datetime.utcnow()

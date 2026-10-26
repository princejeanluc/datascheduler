"""
DataScheduler — ui/graph_editor/run_status.py
Fonctions pures (aucune dépendance Qt) pour la vue d'un run en échec (C9, frame Atelier-echec) —
traduisent des lignes `PipelineRunStep` (ou tout objet portant les mêmes attributs : `status`,
`attempts`, `attempts_json`, `started_at`, `finished_at`, `rows_count`, `output_size_bytes`,
`port_taken`, `error_message`, `reused_from_resume`) en texte/couleur affichables, sans jamais
toucher la DB ni Qt — testable en isolation, même philosophie que `edge_item.py::edge_base_visual`/
`node_item.py::_node_opacity`.
"""

import json


def format_step_duration(seconds) -> str:
    """« 1 min 02 » / « 41 s » — même format que pipelines_view.py::_format_duration_short,
    dupliqué ici pour la même raison déjà invoquée ailleurs dans ce projet (petite fonction,
    pas de module partagé dédié aux formats courts)."""
    if not seconds:
        return "0 s"
    m, s = divmod(int(seconds), 60)
    return f"{m} min {s:02d}" if m else f"{s} s"


def format_rows_count(rows_count) -> str | None:
    if not rows_count:
        return None
    return f"{rows_count:,}".replace(",", " ") + " l."


def format_bytes_fr(n) -> str | None:
    """« 4,1 Mo » — virgule française, pas de module de format d'octets existant dans ce projet
    (grep confirmé) : plus petite unité utile seulement (o/Ko/Mo), pas Go (jamais vu ici)."""
    if not n:
        return None
    if n < 1024:
        return f"{n} o"
    if n < 1024 * 1024:
        return f"{n / 1024:.1f} Ko".replace(".", ",")
    return f"{n / (1024 * 1024):.1f} Mo".replace(".", ",")


def _step_duration_seconds(step_row) -> float:
    if not step_row.started_at or not step_row.finished_at:
        return 0.0
    return (step_row.finished_at - step_row.started_at).total_seconds()


def node_status_text(step_row, via_error_port: bool = False) -> tuple[str, str] | None:
    """(texte, clé de couleur COLORS) pour la 3e ligne de la carte (remplace l'objet principal
    habituel en mode vue d'un run — jamais une ligne en plus, la maquette garde la même hauteur
    de carte). None si `step_row` est None (nœud absent de ce run — ajouté au graphe après coup,
    ou un ancien worker qui n'écrit pas encore pipeline_run_steps, voir note d'impact)."""
    if step_row is None:
        return None

    status = step_row.status
    if status == "SUCCESS":
        duration = format_step_duration(_step_duration_seconds(step_row))
        extra = format_rows_count(step_row.rows_count) or format_bytes_fr(step_row.output_size_bytes)
        prefix = "✓ via le port d'erreur" if via_error_port else "✓"
        text = f"{prefix} · {duration}" if via_error_port else f"{prefix} {duration}"
        if extra:
            text += f" · {extra}"
        return text, "success"

    if status == "FAILED":
        attempts = step_row.attempts or 1
        word = "échouée" if attempts <= 1 else f"{attempts} tentatives refusées"
        return f"✗ {word}", "danger"

    if status == "SKIPPED_RESUME":
        return "réutilisée (reprise)", "text_dim"

    if status == "SKIPPED":
        return "non exécutée", "text_dim"

    if status == "CANCELLED":
        return "annulée", "text_dim"

    if status == "RUNNING":
        return "en cours", "signal"

    return status, "text_dim"


def node_card_state(step_row, via_error_port: bool = False) -> str | None:
    """État de carte additionnel à `set_failed()` (qui reste la seule source pour FAILED, jamais
    dupliqué ici) : "not_executed" (bordure pointillée, texte atténué) ou "error_triggered"
    (bordure/fond ambre, un succès atteint PAR le port d'erreur). None = apparence normale."""
    if step_row is None:
        return None
    if step_row.status in ("SKIPPED", "CANCELLED"):
        return "not_executed"
    if step_row.status == "SUCCESS" and via_error_port:
        return "error_triggered"
    return None


def edge_run_state(from_port: str, from_step_row, to_step_row) -> str | None:
    """"taken" (vert plein), "not_taken" (gris pointillé — déjà l'apparence par défaut, rien à
    repeindre), "error_waiting"/"error_triggered" (port d'erreur) — None = laisser edge_item.py
    décider seul (true/false restent inchangés par le run, voir note d'impact)."""
    if from_port in ("true", "false"):
        return None
    if from_port == "error":
        return "error_triggered" if to_step_row is not None else "error_waiting"
    taken = from_step_row is not None and from_step_row.status == "SUCCESS" and to_step_row is not None
    return "taken" if taken else "not_taken"


def summarize_run_steps(step_rows) -> dict:
    """Bandeau résumé bas-gauche du canevas : compte par statut + nombre de chemins d'erreur
    effectivement suivis (port_taken == "error" sur une ligne SUCCESS/FAILED, pas "en attente")."""
    counts = {"SUCCESS": 0, "FAILED": 0, "SKIPPED": 0, "SKIPPED_RESUME": 0, "CANCELLED": 0}
    error_paths_followed = 0
    for row in step_rows:
        counts[row.status] = counts.get(row.status, 0) + 1
        if row.port_taken == "error" and row.status in ("SUCCESS", "FAILED"):
            error_paths_followed += 1
    return {
        "success": counts.get("SUCCESS", 0),
        "failed": counts.get("FAILED", 0),
        "not_executed": counts.get("SKIPPED", 0) + counts.get("SKIPPED_RESUME", 0) + counts.get("CANCELLED", 0),
        "error_paths_followed": error_paths_followed,
    }


def parse_attempts(step_row) -> list[dict]:
    """Liste des tentatives horodatées (TENTATIVES) — [] si attempts_json absent/invalide
    (robuste à une ligne écrite par une version plus ancienne du moteur, avant ce champ)."""
    if not step_row or not step_row.attempts_json:
        return []
    try:
        data = json.loads(step_row.attempts_json)
    except (ValueError, TypeError):
        return []
    return data if isinstance(data, list) else []


def what_happened_next(failed_step_key: str, successors: list[tuple[str, str]], steps_by_key: dict) -> list[str]:
    """« CE QUI S'EST PASSÉ ENSUITE » — jamais un texte généré par des règles spécifiques
    ("jonction ET" codé en dur) : réutilise le `error_message` déjà écrit par core/pipeline.py sur
    la ligne du successeur lui-même (qui, pour une jonction ET en échec, contient déjà "Passerelle
    de jonction (ET) : au moins une branche entrante n'a pas abouti" — pas besoin de le
    régénérer). `successors` : [(to_step_key, from_port), ...] — arêtes sortant de l'étape en
    échec, `steps_by_key` : step_key -> ligne PipelineRunStep (ou None si jamais apparue)."""
    lines = []
    for to_key, from_port in successors:
        target = steps_by_key.get(to_key)
        label = target.step_label if target else None
        if target is None:
            continue
        if from_port == "error":
            outcome = "a réussi" if target.status == "SUCCESS" else "a échoué"
            lines.append(f"Port d'erreur suivi : {label or to_key} {outcome}.")
        elif target.status == "FAILED":
            msg = target.error_message or "a échoué."
            lines.append(f"{label or to_key} a échoué : {msg}")
        elif target.status in ("SKIPPED", "CANCELLED"):
            lines.append(f"{label or to_key} n'a pas été exécutée.")
    return lines

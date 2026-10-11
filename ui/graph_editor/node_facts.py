"""
DataScheduler — ui/graph_editor/node_facts.py
Résumé "faits clés" + variables lues/écrites par étape (chantier relooking des nœuds) — contenu
du panneau déplié d'un StepNodeItem (ui/graph_editor/node_item.py). Module entièrement pur : ni
Qt, ni accès DB/session — un nœud du canevas ne doit jamais faire sa propre requête (les noms de
profil sont résolus via `profile_names`, construit une fois par
PipelineGraphEditorWidget._build_profile_names() à partir de ses listes déjà chargées en
mémoire, jamais par ce module).
"""

import re

# {var:nom} — StepContext.resolve_tokens() (core/steps/base.py), n'importe quel champ templaté
# de n'importe quel type (chemins, URLs, corps de mail, arguments de script...).
_BRACED_VAR_RE = re.compile(r"\{var:([^}]+)\}")
# var:nom / var:"nom cité" / var:'nom cité' — core/expr_lang.py (_TOKEN_RE), uniquement
# CONDITION.expression et SET_VARIABLE.assignments[].expression. Les formes citées d'abord
# (même ordre de priorité que _TOKEN_RE) ; exclusion des mêmes caractères que son lexer.
_BARE_VAR_RE = re.compile(r'var:"([^"]*)"|var:\'([^\']*)\'|var:([^\s()=!<>+*/,{}]+)')


def extract_var_references(text: str) -> list[str]:
    """Noms de variables LUES dans `text` (les deux syntaxes — accolées et nues), ordre
    d'apparition, sans doublon."""
    if not text:
        return []
    names: list[str] = []
    for m in _BRACED_VAR_RE.finditer(text):
        name = m.group(1)
        if name not in names:
            names.append(name)
    for m in _BARE_VAR_RE.finditer(text):
        name = next(g for g in m.groups() if g is not None)
        if name not in names:
            names.append(name)
    return names


def extract_var_references_from_config(config: dict) -> list[str]:
    """Scan récursif de TOUTES les valeurs string de `config` (listes/dicts imbriqués compris —
    mappings/assignments) — aucune liste blanche de champs par type à entretenir : couvre tout
    champ templaté existant ou futur sans qu'il faille y penser ici."""
    names: list[str] = []

    def _walk(value):
        if isinstance(value, str):
            for name in extract_var_references(value):
                if name not in names:
                    names.append(name)
        elif isinstance(value, dict):
            for v in value.values():
                _walk(v)
        elif isinstance(value, (list, tuple)):
            for v in value:
                _walk(v)

    _walk(config or {})
    return names


def compute_written_variables(step_type: str, config: dict) -> list[str]:
    """SEULS SET_VARIABLE (assignments[].target) et EXTRACT_VARIABLES (mappings[].target)
    écrivent dans ctx.variables (confirmé par grep exhaustif sur core/steps/*.py) — [] pour tout
    autre type."""
    config = config or {}
    if step_type == "SET_VARIABLE":
        return [a.get("target") for a in (config.get("assignments") or []) if a.get("target")]
    if step_type == "EXTRACT_VARIABLES":
        return [m.get("target") for m in (config.get("mappings") or []) if m.get("target")]
    return []


# ──────────────────────────────────────────────
#  Résolution de profils — jamais de requête DB, uniquement `profile_names` déjà en mémoire
# ──────────────────────────────────────────────

def _db_profile_label(profile_names: dict, db_type, profile_id) -> str:
    """profile_names["db"] est keyé par (db_type, id) — list_all_db_profiles() fusionne
    OracleProfile et DatabaseProfile, dont les id PEUVENT se chevaucher entre les deux tables."""
    if not profile_id:
        return "—"
    name = (profile_names.get("db") or {}).get((db_type, profile_id))
    return f"{name} ({db_type})" if name else f"#{profile_id} ({db_type})"


def _simple_profile_label(profile_names: dict, group: str, profile_id) -> str:
    if not profile_id:
        return "—"
    name = (profile_names.get(group) or {}).get(profile_id)
    # Repli sur l'ID brut si le profil a été supprimé entre-temps ou que la liste n'a pas encore
    # été rafraîchie — même tolérance que l'existant pour les profils obsolètes ailleurs dans
    # l'app (ex. combos de sélection de profil dans les dialogues de configuration).
    return name if name else f"#{profile_id}"


def _format_source(config: dict, source_label: str | None) -> str:
    if config.get("reads_from_step_key"):
        return source_label or "(étape amont)"
    if config.get("explicit_path"):
        return config["explicit_path"]
    return "—"


# ──────────────────────────────────────────────
#  Dispatch table — un builder par type (2-4 faits), voir le plan pour le détail par type
# ──────────────────────────────────────────────

def _f_db_extract(c, pn, src):
    facts = [
        {"label": "Profil",  "value": _db_profile_label(pn, c.get("db_type"), c.get("profile_id"))},
        {"label": "Requête", "value": _simple_profile_label(pn, "sql_query", c.get("sql_query_id"))},
    ]
    if c.get("output_name"):
        facts.append({"label": "Sortie", "value": c["output_name"]})
    return facts


def _f_db_load(c, pn, src):
    return [
        {"label": "Profil",               "value": _db_profile_label(pn, c.get("db_type"), c.get("profile_id"))},
        {"label": "Table",                "value": c.get("table_name") or "—"},
        {"label": "Tronque avant charge", "value": "Oui" if c.get("truncate_before_load") else "Non"},
        {"label": "Source",               "value": _format_source(c, src)},
    ]


def _f_ftp_download(c, pn, src):
    facts = [
        {"label": "Profil FTP",     "value": _simple_profile_label(pn, "ftp", c.get("ftp_profile_id"))},
        {"label": "Chemin distant", "value": c.get("remote_path_tpl") or "—"},
    ]
    if c.get("output_name"):
        facts.append({"label": "Sortie", "value": c["output_name"]})
    return facts


def _f_ftp_upload(c, pn, src):
    return [
        {"label": "Profil FTP",     "value": _simple_profile_label(pn, "ftp", c.get("ftp_profile_id"))},
        {"label": "Chemin distant", "value": c.get("remote_path_tpl") or "—"},
        {"label": "Fichier",       "value": c.get("filename_tpl") or "—"},
        {"label": "Source",       "value": _format_source(c, src)},
    ]


def _f_local_copy(c, pn, src):
    facts = [
        {"label": "Dossier cible", "value": c.get("dest_dir") or "—"},
        {"label": "Fichier",       "value": c.get("filename_tpl") or "—"},
        {"label": "Source",       "value": _format_source(c, src)},
    ]
    if c.get("output_name"):
        facts.append({"label": "Sortie", "value": c["output_name"]})
    return facts


def _f_compress(c, pn, src):
    facts = [
        {"label": "Source",  "value": _format_source(c, src)},
        {"label": "Archive", "value": c.get("archive_name_tpl") or "—"},
    ]
    if c.get("output_name"):
        facts.append({"label": "Sortie", "value": c["output_name"]})
    return facts


def _f_db_execute(c, pn, src):
    return [
        {"label": "Profil",  "value": _db_profile_label(pn, c.get("db_type"), c.get("profile_id"))},
        {"label": "Requête", "value": _simple_profile_label(pn, "sql_query", c.get("sql_query_id"))},
        {"label": "Commit",  "value": "Oui" if c.get("commit") else "Non"},
    ]


def _f_python_script(c, pn, src):
    args = c.get("args")
    if isinstance(args, (list, tuple)):
        args_str = " ".join(str(a) for a in args) if args else "—"
    else:
        args_str = args or "—"
    return [
        {"label": "Script",       "value": c.get("script_path") or "—"},
        {"label": "Interpréteur", "value": c.get("python_executable") or "python (PATH)"},
        {"label": "Arguments",    "value": args_str},
        {"label": "Délai max",    "value": f"{c['timeout']}s" if c.get("timeout") else "Aucun"},
    ]


def _f_spark_sql(c, pn, src):
    return [
        {"label": "Nœud edge",         "value": _simple_profile_label(pn, "ssh", c.get("edge_profile_id"))},
        {"label": "Kerberos",          "value": _simple_profile_label(pn, "kerberos", c.get("kerberos_profile_id"))},
        {"label": "Requête",           "value": _simple_profile_label(pn, "sql_query", c.get("sql_query_id"))},
        {"label": "Récupère résultat", "value": "Oui" if c.get("fetch_result") else "Non"},
    ]


def _f_sqoop_export(c, pn, src):
    hive = f"{c.get('hcatalog_database')}.{c.get('hcatalog_table')}" if c.get("hcatalog_table") else "—"
    return [
        {"label": "Nœud edge",          "value": _simple_profile_label(pn, "ssh", c.get("edge_profile_id"))},
        {"label": "Source Hive",        "value": hive},
        {"label": "Table Oracle cible", "value": c.get("oracle_table") or "—"},
        {"label": "Profil Oracle",      "value": _simple_profile_label(pn, "oracle", c.get("oracle_profile_id"))},
    ]


def _f_sqoop_import(c, pn, src):
    hive = f"{c.get('hcatalog_database')}.{c.get('hcatalog_table')}" if c.get("hcatalog_table") else "—"
    return [
        {"label": "Nœud edge",           "value": _simple_profile_label(pn, "ssh", c.get("edge_profile_id"))},
        {"label": "Table Oracle source", "value": c.get("oracle_table") or "—"},
        {"label": "Cible Hive",          "value": hive},
        {"label": "Mappers",             "value": str(c["num_mappers"]) if c.get("num_mappers") else "—"},
    ]


def _f_email_notify(c, pn, src):
    return [
        {"label": "Profil SMTP",   "value": _simple_profile_label(pn, "smtp", c.get("smtp_profile_id"))},
        {"label": "Destinataires", "value": c.get("to") or "—"},
        {"label": "Sujet",         "value": c.get("subject_tpl") or "—"},
        {"label": "Pièce jointe",  "value": "Oui" if c.get("attach_output_file") else "Non"},
    ]


def _f_http_request(c, pn, src):
    return [
        {"label": "Méthode",            "value": c.get("method") or "GET"},
        {"label": "URL",                "value": c.get("url_tpl") or "—"},
        {"label": "Sauvegarde réponse", "value": "Oui" if c.get("save_response") else "Non"},
    ]


def _f_condition(c, pn, src):
    # Un seul fait — suffisant, CONDITION n'a pas d'autre config ; "2-4" est un volume indicatif,
    # pas un minimum imposé type par type.
    return [{"label": "Expression", "value": c.get("expression") or "—"}]


def _f_gateway_parallel(c, pn, src):
    # Config toujours {} — le contenu déplié retombe sur le placeholder générique "Aucun détail
    # de configuration." (voir node_item.py) ; le chevron reste cohérent/cliquable pour tous les
    # types plutôt que caché au cas par cas.
    return []


def _f_gateway_join(c, pn, src):
    key = c.get("artifact_source_step_key")
    value = (src or "(étape amont)") if key else "(aucun — synchronisation seule)"
    return [
        {"label": "Mode",             "value": c.get("join_mode") or "OR"},
        {"label": "Artefact propagé", "value": value},
    ]


def _f_extract_variables(c, pn, src):
    mappings = c.get("mappings") or []
    return [
        {"label": "Source",   "value": _format_source(c, src)},
        {"label": "Mappings", "value": f"{len(mappings)} variable(s)" if mappings else "Aucun"},
    ]


def _f_set_variable(c, pn, src):
    assignments = c.get("assignments") or []
    return [{"label": "Affectations", "value": f"{len(assignments)} variable(s)" if assignments else "Aucune"}]


_FACT_BUILDERS = {
    "DB_EXTRACT": _f_db_extract, "DB_LOAD": _f_db_load,
    "FTP_DOWNLOAD": _f_ftp_download, "FTP_UPLOAD": _f_ftp_upload,
    "LOCAL_COPY": _f_local_copy, "COMPRESS": _f_compress,
    "DB_EXECUTE": _f_db_execute, "PYTHON_SCRIPT": _f_python_script,
    "SPARK_SQL": _f_spark_sql, "SQOOP_EXPORT": _f_sqoop_export, "SQOOP_IMPORT": _f_sqoop_import,
    "EMAIL_NOTIFY": _f_email_notify, "HTTP_REQUEST": _f_http_request,
    "CONDITION": _f_condition, "GATEWAY_PARALLEL": _f_gateway_parallel, "GATEWAY_JOIN": _f_gateway_join,
    "EXTRACT_VARIABLES": _f_extract_variables, "SET_VARIABLE": _f_set_variable,
}


def compute_node_facts(step_type: str, config: dict, profile_names: dict | None = None,
                        source_label: str | None = None) -> list[dict]:
    """Faits clés propres à `step_type` (2-4 paires {"label","value"}, voir le plan pour le
    détail par type) — `profile_names` et `source_label` doivent déjà être résolus par
    l'appelant (jamais de requête DB depuis ici). Type inconnu -> []."""
    builder = _FACT_BUILDERS.get(step_type)
    if builder is None:
        return []
    return builder(config or {}, profile_names or {}, source_label)

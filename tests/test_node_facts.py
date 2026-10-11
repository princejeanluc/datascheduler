"""
DataScheduler — tests/test_node_facts.py
Fonctions pures de ui/graph_editor/node_facts.py (chantier relooking des nœuds) — ni Qt, ni DB.
"""

from ui.graph_editor.node_facts import (
    extract_var_references, extract_var_references_from_config,
    compute_written_variables, compute_node_facts,
)


# ──────────────────────────────────────────────
#  extract_var_references — les deux syntaxes
# ──────────────────────────────────────────────

def test_extract_var_references_braced_form():
    assert extract_var_references("{var:seuil}") == ["seuil"]


def test_extract_var_references_bare_form():
    assert extract_var_references("rows_count > var:seuil") == ["seuil"]


def test_extract_var_references_bare_quoted_forms():
    assert extract_var_references('var:"nom cité"') == ["nom cité"]
    assert extract_var_references("var:'nom cité'") == ["nom cité"]


def test_extract_var_references_mixed_syntaxes_in_one_string():
    text = "{var:a} puis var:b dans le même champ"
    assert extract_var_references(text) == ["a", "b"]


def test_extract_var_references_deduplicates_in_order():
    assert extract_var_references("var:a et encore var:a puis var:b") == ["a", "b"]


def test_extract_var_references_empty_or_none():
    assert extract_var_references("") == []
    assert extract_var_references(None) == []


def test_extract_var_references_no_reference():
    assert extract_var_references("rows_count > 0") == []


# ──────────────────────────────────────────────
#  extract_var_references_from_config — scan récursif générique
# ──────────────────────────────────────────────

def test_extract_var_references_from_config_scans_nested_list_of_dicts():
    config = {"assignments": [
        {"target": "limite", "expression": "date_add(var:base_date, -7)"},
        {"target": "autre",  "expression": "1 + 1"},
    ]}
    assert extract_var_references_from_config(config) == ["base_date"]


def test_extract_var_references_from_config_scans_top_level_strings():
    config = {"explicit_path": "/export/{var:env}/ventes.csv"}
    assert extract_var_references_from_config(config) == ["env"]


def test_extract_var_references_from_config_ignores_non_string_values_without_raising():
    config = {"timeout": 30, "fetch_result": True, "mappings": None, "args": [1, 2.5, None]}
    assert extract_var_references_from_config(config) == []


def test_extract_var_references_from_config_empty_or_none():
    assert extract_var_references_from_config({}) == []
    assert extract_var_references_from_config(None) == []


def test_extract_var_references_from_config_deduplicates_across_fields():
    config = {"a": "var:x", "b": "{var:x}", "c": ["var:x", "var:y"]}
    assert extract_var_references_from_config(config) == ["x", "y"]


# ──────────────────────────────────────────────
#  compute_written_variables
# ──────────────────────────────────────────────

def test_compute_written_variables_set_variable():
    config = {"assignments": [{"target": "a", "expression": "1"}, {"target": "b", "expression": "2"}]}
    assert compute_written_variables("SET_VARIABLE", config) == ["a", "b"]


def test_compute_written_variables_extract_variables():
    config = {"mappings": [{"source": "col1", "target": "total"}, {"source": "col2", "target": "moyenne"}]}
    assert compute_written_variables("EXTRACT_VARIABLES", config) == ["total", "moyenne"]


def test_compute_written_variables_ignores_entries_without_target():
    config = {"assignments": [{"target": "", "expression": "1"}, {"expression": "2"}]}
    assert compute_written_variables("SET_VARIABLE", config) == []


def test_compute_written_variables_other_types_return_empty():
    assert compute_written_variables("DB_EXTRACT", {"profile_id": 1}) == []
    assert compute_written_variables("CONDITION", {"expression": "var:x > 0"}) == []


# ──────────────────────────────────────────────
#  compute_node_facts — résolution de profils
# ──────────────────────────────────────────────

def test_db_profile_label_known_profile():
    pn = {"db": {("ORACLE", 1): "Ventes_Prod"}}
    facts = compute_node_facts("DB_EXTRACT", {"db_type": "ORACLE", "profile_id": 1}, pn)
    assert {"label": "Profil", "value": "Ventes_Prod (ORACLE)"} in facts


def test_db_profile_label_unknown_profile_falls_back_to_raw_id():
    pn = {"db": {}}
    facts = compute_node_facts("DB_EXTRACT", {"db_type": "ORACLE", "profile_id": 42}, pn)
    assert {"label": "Profil", "value": "#42 (ORACLE)"} in facts


def test_db_profile_label_missing_profile_id():
    facts = compute_node_facts("DB_EXTRACT", {"db_type": "ORACLE", "profile_id": None}, {})
    assert {"label": "Profil", "value": "—"} in facts


def test_db_profile_label_resolves_by_composite_key_not_id_alone():
    """list_all_db_profiles() fusionne OracleProfile et DatabaseProfile — leurs id PEUVENT se
    chevaucher entre les deux tables, d'où la clé composite (db_type, id)."""
    pn = {"db": {("ORACLE", 1): "Oracle_Un", ("POSTGRES", 1): "Postgres_Un"}}
    oracle_facts = compute_node_facts("DB_EXTRACT", {"db_type": "ORACLE", "profile_id": 1}, pn)
    pg_facts = compute_node_facts("DB_EXTRACT", {"db_type": "POSTGRES", "profile_id": 1}, pn)
    assert {"label": "Profil", "value": "Oracle_Un (ORACLE)"} in oracle_facts
    assert {"label": "Profil", "value": "Postgres_Un (POSTGRES)"} in pg_facts


def test_simple_profile_label_known_unknown_and_absent():
    pn = {"ftp": {7: "SFTP_PARTENAIRE"}}
    known = compute_node_facts("FTP_UPLOAD", {"ftp_profile_id": 7}, pn)
    unknown = compute_node_facts("FTP_UPLOAD", {"ftp_profile_id": 99}, pn)
    absent = compute_node_facts("FTP_UPLOAD", {"ftp_profile_id": None}, pn)
    assert {"label": "Profil FTP", "value": "SFTP_PARTENAIRE"} in known
    assert {"label": "Profil FTP", "value": "#99"} in unknown
    assert {"label": "Profil FTP", "value": "—"} in absent


def test_format_source_reads_from_step_key_with_label():
    config = {"reads_from_step_key": "a"}
    facts = compute_node_facts("LOCAL_COPY", config, {}, source_label="Extraction Oracle")
    assert {"label": "Source", "value": "Extraction Oracle"} in facts


def test_format_source_reads_from_step_key_without_label_falls_back():
    config = {"reads_from_step_key": "a"}
    facts = compute_node_facts("LOCAL_COPY", config, {}, source_label=None)
    assert {"label": "Source", "value": "(étape amont)"} in facts


def test_format_source_explicit_path():
    config = {"explicit_path": "/tmp/fichier.csv"}
    facts = compute_node_facts("LOCAL_COPY", config, {})
    assert {"label": "Source", "value": "/tmp/fichier.csv"} in facts


def test_format_source_neither_set():
    facts = compute_node_facts("LOCAL_COPY", {}, {})
    assert {"label": "Source", "value": "—"} in facts


# ──────────────────────────────────────────────
#  compute_node_facts — un test par type (19) + type inconnu
# ──────────────────────────────────────────────

def test_facts_db_extract():
    facts = compute_node_facts("DB_EXTRACT", {"db_type": "ORACLE", "profile_id": 1, "sql_query_id": 2}, {})
    assert len(facts) == 2
    assert facts[0]["label"] == "Profil"


def test_facts_db_load():
    facts = compute_node_facts("DB_LOAD", {"table_name": "VENTES"}, {})
    assert len(facts) == 4
    assert {"label": "Table", "value": "VENTES"} in facts


def test_facts_ftp_download():
    facts = compute_node_facts("FTP_DOWNLOAD", {"remote_path_tpl": "/in/"}, {})
    assert len(facts) == 2


def test_facts_ftp_upload():
    facts = compute_node_facts("FTP_UPLOAD", {"remote_path_tpl": "/out/", "filename_tpl": "x.csv"}, {})
    assert len(facts) == 4


def test_facts_local_copy():
    facts = compute_node_facts("LOCAL_COPY", {"dest_dir": "C:/data"}, {})
    assert len(facts) == 3
    assert {"label": "Dossier cible", "value": "C:/data"} in facts


def test_facts_compress():
    facts = compute_node_facts("COMPRESS", {"archive_name_tpl": "archive_{yyyyMMdd}.zip"}, {})
    assert len(facts) == 2


def test_facts_db_execute():
    facts = compute_node_facts("DB_EXECUTE", {"commit": True}, {})
    assert len(facts) == 3
    assert {"label": "Commit", "value": "Oui"} in facts


def test_facts_python_script_with_args_list():
    facts = compute_node_facts(
        "PYTHON_SCRIPT", {"script_path": "run.py", "args": ["--env", "prod"], "timeout": 60}, {},
    )
    assert len(facts) == 4
    assert {"label": "Arguments", "value": "--env prod"} in facts
    assert {"label": "Délai max", "value": "60s"} in facts


def test_facts_spark_sql():
    facts = compute_node_facts("SPARK_SQL", {"fetch_result": False}, {})
    assert len(facts) == 4
    assert {"label": "Récupère résultat", "value": "Non"} in facts


def test_facts_sqoop_export():
    facts = compute_node_facts(
        "SQOOP_EXPORT",
        {"hcatalog_database": "db1", "hcatalog_table": "t1", "oracle_table": "ORA_T"}, {},
    )
    assert len(facts) == 4
    assert {"label": "Source Hive", "value": "db1.t1"} in facts
    assert {"label": "Table Oracle cible", "value": "ORA_T"} in facts


def test_facts_sqoop_import():
    facts = compute_node_facts("SQOOP_IMPORT", {"num_mappers": 4}, {})
    assert len(facts) == 4
    assert {"label": "Mappers", "value": "4"} in facts


def test_facts_email_notify():
    facts = compute_node_facts("EMAIL_NOTIFY", {"to": "a@b.c", "attach_output_file": True}, {})
    assert len(facts) == 4
    assert {"label": "Pièce jointe", "value": "Oui"} in facts


def test_facts_http_request():
    facts = compute_node_facts("HTTP_REQUEST", {"method": "POST", "url_tpl": "https://x"}, {})
    assert len(facts) == 3
    assert {"label": "Méthode", "value": "POST"} in facts


def test_facts_condition():
    facts = compute_node_facts("CONDITION", {"expression": "rows_count > 0"}, {})
    assert facts == [{"label": "Expression", "value": "rows_count > 0"}]


def test_facts_gateway_parallel_is_empty():
    assert compute_node_facts("GATEWAY_PARALLEL", {}, {}) == []


def test_facts_gateway_join_with_artifact_source():
    facts = compute_node_facts(
        "GATEWAY_JOIN", {"join_mode": "AND", "artifact_source_step_key": "a"}, {}, source_label="Extraction",
    )
    assert {"label": "Mode", "value": "AND"} in facts
    assert {"label": "Artefact propagé", "value": "Extraction"} in facts


def test_facts_gateway_join_without_artifact_source():
    facts = compute_node_facts("GATEWAY_JOIN", {"join_mode": "OR"}, {})
    assert {"label": "Artefact propagé", "value": "(aucun — synchronisation seule)"} in facts


def test_facts_extract_variables():
    facts = compute_node_facts(
        "EXTRACT_VARIABLES", {"mappings": [{"source": "a", "target": "b"}]}, {},
    )
    assert len(facts) == 2
    assert {"label": "Mappings", "value": "1 variable(s)"} in facts


def test_facts_set_variable():
    facts = compute_node_facts("SET_VARIABLE", {"assignments": [{"target": "a", "expression": "1"}]}, {})
    assert facts == [{"label": "Affectations", "value": "1 variable(s)"}]


def test_facts_unknown_type_returns_empty():
    assert compute_node_facts("INCONNU", {}, {}) == []

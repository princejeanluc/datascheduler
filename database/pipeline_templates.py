"""
DataScheduler — database/pipeline_templates.py
Modèle de pipeline de démarrage (chantier UX éditeur, Lot 1, C1) — accessible depuis l'état vide
de PipelinesView, pour dupliquer/adapter plutôt que de partir d'une toile blanche. Aucun
précédent de contenu de pipeline codé en dur n'existait avant ce chantier (le seul précédent
proche, ui/step_editor/python_script_template.py::PYTHON_SCRIPT_TEMPLATE, est un template de
SCRIPT, pas de pipeline).

Le squelette (extraction DB → dépôt local) est le schéma le plus courant identifié dans la
genèse du produit — un point de départ réaliste à éditer, pas un pipeline zéro-configuration
factice (un CONDITION seul serait auto-suffisant mais pédagogiquement creux). Les références de
profil (profile_id) sont délibérément ABSENTES de la config plutôt que pointées vers un profil
fictif — _STEP_REFERENCES/plan_import() tolèrent déjà une référence absente (voir SQOOP_EXPORT,
Kerberos/élévation optionnels, même mécanisme), donc l'étape s'ouvre simplement avec "aucun
profil sélectionné", exactement ce qu'un nouvel utilisateur doit remplir.

Bundle au format exact d'export_pipeline() (database/export_import.py) — plan_import()/
apply_import() n'exigent pas qu'un bundle vienne d'un vrai export, ils acceptent un dict direct,
le même mécanisme déjà emprunté par l'import d'un fichier .dspipeline réel.
"""

from datetime import datetime, timezone

from database.export_import import CURRENT_SCHEMA_VERSION
from version import __version__

STARTER_TEMPLATE_NAME = "Modèle — extraction puis dépôt local"


def build_starter_template_bundle() -> dict:
    """Reconstruit le bundle à chaque appel (pas une constante partagée) — plan_import()/
    apply_import() ne doivent jamais recevoir deux fois le même dict muté en place."""
    return {
        "schema_version": CURRENT_SCHEMA_VERSION,
        "app_version":    __version__,
        "exported_at":    datetime.now(timezone.utc).isoformat(),
        "kind":           "pipeline",
        "pipeline": {
            "uuid":            None,
            "name":            STARTER_TEMPLATE_NAME,
            "description": (
                "Modèle de démarrage : une étape d'extraction base de données suivie d'un dépôt "
                "local. Complétez le profil de connexion et la requête de l'étape d'extraction, "
                "puis le dossier de destination du dépôt, avant de planifier ou d'exécuter."
            ),
            "frequency":       "DAILY",
            "cron_expression": None,
            "scheduled_time":  "06:00",
            "scheduled_day":   None,
            "prevent_overlap": False,
            "parallel_execution_enabled": False,
            "max_parallel_branches":      4,
            "steps": [
                {
                    "step_order":  0,
                    "step_type":   "DB_EXTRACT",
                    "label":       "Extraction — à configurer",
                    "config":      {"_step_key": "extraction"},
                    "retry_count": 0,
                    "run_always":  False,
                    "timeout_s":   0,
                    "pos_x":       60,
                    "pos_y":       60,
                },
                {
                    "step_order":  1,
                    "step_type":   "LOCAL_COPY",
                    "label":       "Dépôt local — à configurer",
                    "config":      {"_step_key": "depot", "dest_dir": "", "filename_tpl": ""},
                    "retry_count": 0,
                    "run_always":  False,
                    "timeout_s":   0,
                    "pos_x":       300,
                    "pos_y":       60,
                },
            ],
            "edges": [
                {
                    "from_step_key": "extraction", "from_port": "output_file",
                    "to_step_key":   "depot",       "to_port":   "input",
                },
            ],
        },
        "profiles":    {"oracle": [], "ftp": [], "smtp": [], "database": [],
                         "ssh": [], "kerberos": [], "elevation": []},
        "sql_queries": [],
    }

"""
DataScheduler — ui/step_editor/common.py
Constantes et petit helper partagés par tout le package step_editor.
"""

from ui.styles import COLORS

try:
    import qtawesome as qta
    def _icon(name, color=None): return qta.icon(name, color=color or COLORS["text_dim"])
except ImportError:
    def _icon(name, color=None): return None


# ──────────────────────────────────────────────
#  MÉTADONNÉES PAR TYPE D'ÉTAPE
# ──────────────────────────────────────────────

# Couleur par famille (refonte, lot 0a — maquette Grammaire) : « la couleur dit la famille, le
# texte dit le moteur ». Remplace les 18 couleurs par type qui existaient avant ce lot — une
# famille n'est PAS la "category" ci-dessous (qui pilote les sections de StepTypeChooserDialog) :
# Big Data par exemple n'a pas sa propre section, ses types restent rangés dans "Exécution &
# scripts" (_CATEGORY_ORDER, step_type_chooser_dialog.py), inchangée par ce lot.
_FAMILY_COLORS = {
    "Extraction et chargement": "#6BB4CF",
    "Transfert et diffusion":   "#b5c96a",
    "Exécution et scripts":     "#d68fb8",
    "Big Data":                 "#4fb3a0",
    "Notification":             "#c9a37a",
    "Variables":                "#b8b2a8",
    "Passerelles":               "#a58cf0",
}

# "category" regroupe les types dans le sélecteur (StepTypeChooserDialog) — voir
# _CATEGORY_ORDER dans step_type_chooser_dialog.py pour l'ordre d'affichage des sections.
STEP_META = {
    "DB_EXTRACT":     {"label": "Extraction base de données", "family": "Extraction et chargement",
                       "category": "Extraction & chargement", "icon": "fa5s.file-export"},
    "FTP_DOWNLOAD":   {"label": "Téléchargement FTP",  "family": "Extraction et chargement",
                       "category": "Extraction & chargement", "icon": "fa5s.cloud-download-alt"},
    "DB_LOAD":        {"label": "Chargement base de données", "family": "Extraction et chargement",
                       "category": "Extraction & chargement", "icon": "fa5s.file-import"},
    "FTP_UPLOAD":     {"label": "Envoi FTP",          "family": "Transfert et diffusion",
                       "category": "Transfert & diffusion", "icon": "fa5s.cloud-upload-alt"},
    "LOCAL_COPY":     {"label": "Copie locale",       "family": "Transfert et diffusion",
                       "category": "Transfert & diffusion", "icon": "fa5s.copy"},
    "COMPRESS":       {"label": "Compression (ZIP)",  "family": "Transfert et diffusion",
                       "category": "Transfert & diffusion", "icon": "fa5s.file-archive"},
    "DB_EXECUTE":     {"label": "Exécution base de données", "family": "Exécution et scripts",
                       "category": "Exécution & scripts", "icon": "fa5s.terminal"},
    "PYTHON_SCRIPT":  {"label": "Script Python",      "family": "Exécution et scripts",
                       "category": "Exécution & scripts", "icon": "fa5b.python"},
    "SPARK_SQL":      {"label": "Spark SQL",          "family": "Big Data",
                       "category": "Exécution & scripts", "icon": "fa5s.fire"},
    "SQOOP_EXPORT":   {"label": "Export Sqoop (→ Oracle)", "family": "Big Data",
                       "category": "Exécution & scripts", "icon": "fa5s.exchange-alt"},
    "SQOOP_IMPORT":   {"label": "Import Sqoop (Oracle →)", "family": "Big Data",
                       "category": "Exécution & scripts", "icon": "fa5s.random"},
    "EMAIL_NOTIFY":   {"label": "Notification email", "family": "Notification",
                       "category": "Notification & intégration", "icon": "fa5s.envelope"},
    "HTTP_REQUEST":   {"label": "Appel HTTP",          "family": "Notification",
                       "category": "Notification & intégration", "icon": "fa5s.globe"},
    "CONDITION":      {"label": "Condition / Routeur", "family": "Passerelles",
                       "category": "Contrôle de flux", "icon": "fa5s.code-branch"},
    "GATEWAY_PARALLEL": {"label": "Passerelle parallèle", "family": "Passerelles",
                       "category": "Contrôle de flux", "icon": "fa5s.share-alt"},
    "GATEWAY_JOIN":   {"label": "Passerelle de jonction", "family": "Passerelles",
                       "category": "Contrôle de flux", "icon": "fa5s.compress-arrows-alt"},
    "EXTRACT_VARIABLES": {"label": "Extraction de variables", "family": "Variables",
                       "category": "Contrôle de flux", "icon": "fa5s.tags"},
    "SET_VARIABLE":   {"label": "Définir une variable", "family": "Variables",
                       "category": "Contrôle de flux", "icon": "fa5s.equals"},
}

for _meta in STEP_META.values():
    _meta["color"] = _FAMILY_COLORS[_meta["family"]]
del _meta

DAYS_OF_WEEK = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]

TOKENS_HINT = "{yyyy}  {yy}  {MM}  {dd}  {HH}  {mm}  {yyyyMMdd}  {yyyyMMddHHmm}  {output_file}  {rows_count}"

# ──────────────────────────────────────────────
#  OPTIONS CSV — partagées par tout dialogue produisant un fichier texte (DB_EXTRACT,
#  SPARK_SQL, ...) : une seule liste à faire évoluer pour que tous ces écrans restent
#  cohérents entre eux, plutôt qu'une copie par dialogue qui dérive au fil du temps.
# ──────────────────────────────────────────────

CSV_SEPARATORS = [("Point-virgule  ;", ";"), ("Virgule  ,", ","),
                   ("Pipe  |", "|"), ("Tabulation  \\t", "\t")]
CSV_ENCODINGS  = [("UTF-8 BOM (Excel)", "utf-8-sig"), ("UTF-8", "utf-8"),
                   ("Latin-1", "latin-1"), ("CP1252", "cp1252")]
CSV_QUOTINGS   = [
    ("Chaînes & dates seulement", "QUOTE_NONNUMERIC"),
    ("Minimal — si nécessaire",   "QUOTE_MINIMAL"),
    ("Tout entre guillemets",     "QUOTE_ALL"),
    ("Aucun guillemet",           "QUOTE_NONE"),
]

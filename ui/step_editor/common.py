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

# "category" regroupe les types dans le sélecteur (StepTypeChooserDialog) — voir
# _CATEGORY_ORDER dans step_type_chooser_dialog.py pour l'ordre d'affichage des sections.
STEP_META = {
    "DB_EXTRACT":     {"label": "Extraction base de données", "color": "#4fc3f7",
                       "category": "Extraction & chargement", "icon": "fa5s.file-export"},
    "FTP_DOWNLOAD":   {"label": "Téléchargement FTP",  "color": "#ffa726",
                       "category": "Extraction & chargement", "icon": "fa5s.cloud-download-alt"},
    "DB_LOAD":        {"label": "Chargement base de données", "color": "#26a69a",
                       "category": "Extraction & chargement", "icon": "fa5s.file-import"},
    "FTP_UPLOAD":     {"label": "Envoi FTP",          "color": "#FF7900",
                       "category": "Transfert & diffusion", "icon": "fa5s.cloud-upload-alt"},
    "LOCAL_COPY":     {"label": "Copie locale",       "color": "#66bb6a",
                       "category": "Transfert & diffusion", "icon": "fa5s.copy"},
    "COMPRESS":       {"label": "Compression (ZIP)",  "color": "#8d6e63",
                       "category": "Transfert & diffusion", "icon": "fa5s.file-archive"},
    "DB_EXECUTE":     {"label": "Exécution base de données", "color": "#29b6f6",
                       "category": "Exécution & scripts", "icon": "fa5s.terminal"},
    "PYTHON_SCRIPT":  {"label": "Script Python",      "color": "#ce93d8",
                       "category": "Exécution & scripts", "icon": "fa5b.python"},
    "SPARK_SQL":      {"label": "Spark SQL",          "color": "#e57373",
                       "category": "Exécution & scripts", "icon": "fa5s.fire"},
    "SQOOP_EXPORT":   {"label": "Export Sqoop (→ Oracle)", "color": "#f06292",
                       "category": "Exécution & scripts", "icon": "fa5s.exchange-alt"},
    "EMAIL_NOTIFY":   {"label": "Notification email", "color": "#ef5350",
                       "category": "Notification & intégration", "icon": "fa5s.envelope"},
    "HTTP_REQUEST":   {"label": "Appel HTTP",          "color": "#ab47bc",
                       "category": "Notification & intégration", "icon": "fa5s.globe"},
    "CONDITION":      {"label": "Condition / Routeur", "color": "#7e57c2",
                       "category": "Contrôle de flux", "icon": "fa5s.code-branch"},
}

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

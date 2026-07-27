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
                       "category": "Extraction & chargement"},
    "FTP_DOWNLOAD":   {"label": "Téléchargement FTP",  "color": "#ffa726",
                       "category": "Extraction & chargement"},
    "DB_LOAD":        {"label": "Chargement base de données", "color": "#26a69a",
                       "category": "Extraction & chargement"},
    "FTP_UPLOAD":     {"label": "Envoi FTP",          "color": "#FF7900",
                       "category": "Transfert & diffusion"},
    "LOCAL_COPY":     {"label": "Copie locale",       "color": "#66bb6a",
                       "category": "Transfert & diffusion"},
    "DB_EXECUTE":     {"label": "Exécution base de données", "color": "#29b6f6",
                       "category": "Exécution & scripts"},
    "PYTHON_SCRIPT":  {"label": "Script Python",      "color": "#ce93d8",
                       "category": "Exécution & scripts"},
    "EMAIL_NOTIFY":   {"label": "Notification email", "color": "#ef5350",
                       "category": "Notification & intégration"},
    "HTTP_REQUEST":   {"label": "Appel HTTP",          "color": "#ab47bc",
                       "category": "Notification & intégration"},
    "CONDITION":      {"label": "Condition / Routeur", "color": "#7e57c2",
                       "category": "Contrôle de flux"},
}

DAYS_OF_WEEK = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]

TOKENS_HINT = "{yyyy}  {yy}  {MM}  {dd}  {HH}  {mm}  {yyyyMMdd}  {yyyyMMddHHmm}  {output_file}  {rows_count}"

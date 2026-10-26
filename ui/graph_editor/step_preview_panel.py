"""
DataScheduler — ui/graph_editor/step_preview_panel.py
Aperçu d'un type d'étape sélectionné dans le panneau « Ajouter » (C7, frame Atelier-ajout) —
remplace le panneau « Paramètres du pipeline » tant que ce panneau est ouvert (bascule faite par
l'hôte, `AtelierPipelinesView`, jamais par ce widget lui-même). « Reçoit »/« Produit » viennent de
`core.steps` (get_step_requirements/step_produces_output_file), jamais une chaîne en dur par type
— voir docs/refonte/impact/c7-atelier-ajout.md pour la source de « Connexion »/« À remplir après
l'insertion », purement descriptives, sans fonction équivalente dans le code.
"""

from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame
from PySide6.QtCore import Qt, Signal

from ui.styles import COLORS, FONT_MONO_STACK
from ui.step_editor.common import STEP_META
from core.steps import get_step_requirements, step_produces_output_file, get_step_output_ports

# Dérivés des champs réels de chaque dialogue de config (ui/step_editor/*_config_dialog.py),
# vérifiés un par un — pas une invention. "aucune" = le step ne lit aucun profil enregistré.
_CONNECTION_LABEL = {
    "DB_EXTRACT": "Profil de base de données", "DB_EXECUTE": "Profil de base de données",
    "DB_LOAD": "Profil de base de données",
    "FTP_UPLOAD": "Profil FTP / FTPS / SFTP", "FTP_DOWNLOAD": "Profil FTP / FTPS / SFTP",
    "EMAIL_NOTIFY": "Profil SMTP",
    "SPARK_SQL": "Profil SSH (nœud edge)", "SQOOP_EXPORT": "Profil SSH (nœud edge)",
    "SQOOP_IMPORT": "Profil SSH (nœud edge)",
}

_FIELDS_TO_FILL = {
    "DB_EXTRACT": "Connexion, requête SQL", "DB_EXECUTE": "Connexion, instruction SQL",
    "DB_LOAD": "Connexion, table de destination",
    "FTP_UPLOAD": "Connexion, dossier distant", "FTP_DOWNLOAD": "Connexion, fichier distant",
    "LOCAL_COPY": "Dossier de destination, nom du fichier",
    "COMPRESS": "Nom de l'archive",
    "PYTHON_SCRIPT": "Script, arguments",
    "SPARK_SQL": "Connexion, requête Spark SQL",
    "SQOOP_EXPORT": "Connexion, table Hive, table Oracle",
    "SQOOP_IMPORT": "Connexion, table Oracle, table Hive",
    "EMAIL_NOTIFY": "Connexion, destinataires",
    "HTTP_REQUEST": "URL, méthode",
    "CONDITION": "Expression",
    "GATEWAY_PARALLEL": "aucun",
    "GATEWAY_JOIN": "Mode de jonction (ET/OU)",
    "EXTRACT_VARIABLES": "Colonnes à extraire",
    "SET_VARIABLE": "Variables et expressions",
}


def step_connection_label(step_type: str) -> str:
    return _CONNECTION_LABEL.get(step_type, "aucune")


def step_fields_to_fill(step_type: str) -> str:
    return _FIELDS_TO_FILL.get(step_type, "—")


def step_receives_label(step_type: str) -> str:
    requires, _ = get_step_requirements(step_type)
    return "un fichier de l'étape amont" if "output_file" in requires else "aucune donnée requise"


def step_produces_label(step_type: str) -> str:
    return "output_file" if step_produces_output_file(step_type, {}) else "aucun"


class StepPreviewPanel(QWidget):
    """Aperçu + bouton d'insertion. `set_step(step_type, config)` (config=None hors "Mes
    modèles") met à jour l'affichage ; `insert_requested` est émis au clic du bouton, l'hôte
    (`PipelineGraphEditorWidget`) décide seul où et comment insérer (voir sa docstring)."""

    insert_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._step_type: str | None = None
        self._build_ui()
        self.set_step(None)

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(16)

        self._eyebrow = QLabel()
        self._eyebrow.setStyleSheet(
            f"font-family: {FONT_MONO_STACK}; font-size: 10px; letter-spacing: 0.06em; "
            f"background: transparent; border: none;"
        )
        root.addWidget(self._eyebrow)

        self._title = QLabel()
        self._title.setStyleSheet(
            f"color: {COLORS['text_main']}; font-size: 17px; font-weight: 600; "
            f"background: transparent; border: none;"
        )
        root.addWidget(self._title)

        self._desc = QLabel()
        self._desc.setWordWrap(True)
        self._desc.setStyleSheet(f"color: {COLORS['text_dim']}; background: transparent; border: none;")
        root.addWidget(self._desc)

        box = QFrame()
        box.setStyleSheet(
            f"QFrame {{ background: {COLORS['bg_card']}; border-radius: 8px; }}"
        )
        box_l = QVBoxLayout(box)
        box_l.setContentsMargins(12, 12, 12, 12)
        box_l.setSpacing(8)
        self._row_receives = self._info_row(box_l, "Reçoit")
        self._row_produces = self._info_row(box_l, "Produit", mono=True)
        self._row_connection = self._info_row(box_l, "Connexion")
        self._row_error = self._info_row(box_l, "Port d'erreur", value_color=COLORS["warning"])
        root.addWidget(box)

        fields_col = QVBoxLayout(); fields_col.setSpacing(4)
        fields_hdr = QLabel("À REMPLIR APRÈS L'INSERTION")
        fields_hdr.setStyleSheet(
            f"color: {COLORS['text_dim']}; font-size: 11px; font-weight: 600; "
            f"letter-spacing: 0.06em; background: transparent; border: none;"
        )
        fields_col.addWidget(fields_hdr)
        self._fields_value = QLabel()
        self._fields_value.setWordWrap(True)
        self._fields_value.setStyleSheet(f"color: {COLORS['text_main']}; background: transparent; border: none;")
        fields_col.addWidget(self._fields_value)
        root.addLayout(fields_col)

        root.addStretch()

        self.btn_insert = QPushButton("Insérer à l'emplacement marqué")
        self.btn_insert.setFixedHeight(36)
        self.btn_insert.setStyleSheet(
            f"QPushButton {{ background: transparent; border: 1px solid {COLORS['accent']}; "
            f"border-radius: 6px; color: {COLORS['accent_pale']}; font-weight: 600; }}"
            f"QPushButton:hover {{ background: {COLORS['bg_hover']}; }}"
            f"QPushButton:disabled {{ border-color: {COLORS['border']}; color: {COLORS['text_muted']}; }}"
        )
        self.btn_insert.clicked.connect(self.insert_requested.emit)
        root.addWidget(self.btn_insert)

    @staticmethod
    def _info_row(layout: QVBoxLayout, label: str, mono: bool = False, value_color: str | None = None) -> QLabel:
        row = QHBoxLayout()
        lbl = QLabel(label)
        lbl.setStyleSheet(f"color: {COLORS['text_dim']}; background: transparent; border: none;")
        row.addWidget(lbl)
        row.addStretch()
        value = QLabel()
        font = f"font-family: {FONT_MONO_STACK}; " if mono else ""
        color = value_color or COLORS["text_main"]
        value.setStyleSheet(f"color: {color}; {font}background: transparent; border: none;")
        row.addWidget(value)
        layout.addLayout(row)
        return value

    def set_step(self, step_type: str | None, config: dict | None = None):
        """config n'est utilisé nulle part dans cet aperçu (rien n'en dépend visuellement) — reçu
        quand même pour une signature symétrique avec StepLibraryPanel.selection_changed."""
        self._step_type = step_type
        if step_type is None:
            self._eyebrow.setText("APERÇU")
            self._eyebrow.setStyleSheet(
                f"color: {COLORS['text_muted']}; font-family: {FONT_MONO_STACK}; font-size: 10px; "
                f"letter-spacing: 0.06em; background: transparent; border: none;"
            )
            self._title.setText("Sélectionnez un type d'étape")
            self._desc.setText("")
            for row in (self._row_receives, self._row_produces, self._row_connection):
                row.setText("—")
            self._row_error.setText("oui, comme toutes les étapes")
            self._fields_value.setText("—")
            self.btn_insert.setEnabled(False)
            return

        meta = STEP_META[step_type]
        self._eyebrow.setText(f"APERÇU · {meta['category'].upper()}")
        self._eyebrow.setStyleSheet(
            f"color: {meta['color']}; font-family: {FONT_MONO_STACK}; font-size: 10px; "
            f"letter-spacing: 0.06em; background: transparent; border: none;"
        )
        self._title.setText(meta["label"])
        from ui.step_editor.step_type_chooser_dialog import step_type_description
        self._desc.setText(step_type_description(step_type))
        self._row_receives.setText(step_receives_label(step_type))
        self._row_produces.setText(step_produces_label(step_type))
        self._row_connection.setText(step_connection_label(step_type))
        self._row_error.setText(
            "oui, comme toutes les étapes" if "error" in get_step_output_ports(step_type) else "—"
        )
        self._fields_value.setText(step_fields_to_fill(step_type))
        self.btn_insert.setEnabled(True)

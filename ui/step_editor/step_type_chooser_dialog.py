"""
DataScheduler — ui/step_editor/step_type_chooser_dialog.py
Dialogue de choix du type d'une nouvelle étape.
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
)
from PySide6.QtCore import Qt
from ui.styles import COLORS, DIALOG_STYLE
from .common import STEP_META


class StepTypeChooserDialog(QDialog):
    """Dialogue de sélection du type d'étape à ajouter."""

    def __init__(self, parent=None, include_condition: bool = False):
        super().__init__(parent)
        self.chosen_type: str = ""
        self._include_condition = include_condition
        self.setWindowTitle("Ajouter une étape")
        self.setFixedWidth(420)
        self.setStyleSheet(DIALOG_STYLE)
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(10)

        title = QLabel("Choisir le type d'étape")
        title.setStyleSheet(
            f"font-size: 15px; font-weight: 700; color: {COLORS['text_main']};"
        )
        root.addWidget(title)

        sep = QFrame(); sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet(f"background: {COLORS['border']}; max-height: 1px;")
        root.addWidget(sep)

        descriptions = {
            "DB_EXTRACT":     "Connexion à une base (Oracle, MySQL, PostgreSQL, SQL Server), exécution SQL, export CSV vers fichier temporaire.",
            "FTP_UPLOAD":     "Upload du fichier produit vers un serveur FTP / FTPS / SFTP.",
            "LOCAL_COPY":     "Copie du fichier produit dans un dossier local (avec tokens datetime).",
            "PYTHON_SCRIPT":  "Exécution d'un script Python avec arguments (tokens datetime + contexte).",
            "DB_EXECUTE":     "Exécution d'une instruction SQL/PLSQL (DML, DDL, procédure) sans extraction, tout moteur.",
            "FTP_DOWNLOAD":   "Téléchargement d'un fichier distant (FTP / FTPS / SFTP) comme source du pipeline.",
            "DB_LOAD":        "Chargement du fichier produit (CSV) dans une table, tout moteur.",
            "EMAIL_NOTIFY":   "Envoi d'un email, avec le fichier produit en pièce jointe optionnelle.",
            "HTTP_REQUEST":   "Appel d'une API REST / webhook, avec le fichier produit en option.",
        }
        if self._include_condition:
            descriptions["CONDITION"] = (
                "Évalue une expression sur le contexte et route vers l'une de ses deux sorties "
                "(Vrai/Faux) — à connecter dans le canevas."
            )

        for step_type, desc in descriptions.items():
            meta = STEP_META[step_type]

            btn_row = QFrame()
            btn_row.setCursor(Qt.PointingHandCursor)
            btn_row.setStyleSheet(
                f"QFrame {{ background: {COLORS['bg_card']}; border: 1px solid {COLORS['border']}; "
                f"border-radius: 6px; }}"
                f"QFrame:hover {{ border-color: {meta['color']}; background: {meta['color']}11; }}"
            )
            hl = QHBoxLayout(btn_row)
            hl.setContentsMargins(14, 10, 14, 10)
            hl.setSpacing(14)

            dot = QLabel("●")
            dot.setStyleSheet(
                f"color: {meta['color']}; font-size: 18px; background: transparent; border: none;"
            )
            dot.setFixedWidth(20)

            info_col = QVBoxLayout(); info_col.setSpacing(2)
            lbl_type = QLabel(meta["label"])
            lbl_type.setStyleSheet(
                f"color: {COLORS['text_main']}; font-size: 13px; font-weight: 600; "
                f"background: transparent; border: none;"
            )
            lbl_desc = QLabel(desc)
            lbl_desc.setStyleSheet(
                f"color: {COLORS['text_dim']}; font-size: 11px; "
                f"background: transparent; border: none;"
            )
            lbl_desc.setWordWrap(True)
            info_col.addWidget(lbl_type); info_col.addWidget(lbl_desc)

            hl.addWidget(dot)
            hl.addLayout(info_col, stretch=1)

            # Rendre la card cliquable via mousePressEvent override
            btn_row.mouseReleaseEvent = lambda _, t=step_type: self._choose(t)
            root.addWidget(btn_row)

        root.addSpacing(6)
        btn_cancel = QPushButton("Annuler"); btn_cancel.setObjectName("secondary")
        btn_cancel.setFixedHeight(34); btn_cancel.clicked.connect(self.reject)
        root.addWidget(btn_cancel, alignment=Qt.AlignRight)

    def _choose(self, step_type: str):
        self.chosen_type = step_type
        self.accept()

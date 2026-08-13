"""
DataScheduler — ui/dialogs/pipeline_export_dialog.py
Dialogue d'export d'un pipeline vers un fichier .dspipeline.
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QLineEdit,
    QPushButton, QFrame, QMessageBox, QFileDialog,
)
from PySide6.QtCore import Qt
from ui.styles import COLORS, DIALOG_STYLE


# ──────────────────────────────────────────────
#  DIALOGUE : EXPORT DE PIPELINE
# ──────────────────────────────────────────────

class PipelineExportDialog(QDialog):
    """
    Exporte un pipeline vers un fichier .dspipeline (JSON versionné — voir
    database/export_import.py). Le mot de passe chiffre les identifiants des profils
    référencés ; laissé vide, ils sont omis du fichier plutôt que forcés.
    """

    def __init__(self, parent=None, pipeline=None):
        super().__init__(parent)
        self._pipeline = pipeline
        self.setWindowTitle(f"Exporter « {pipeline.name} »")
        self.setMinimumWidth(460)
        self.setStyleSheet(DIALOG_STYLE)
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(16)

        title = QLabel(f"Exporter « {self._pipeline.name} »")
        title.setStyleSheet(f"font-size: 16px; font-weight: 700; color: {COLORS['text_main']};")
        root.addWidget(title)
        root.addWidget(self._sep())

        form = QFormLayout()
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        form.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)

        self.inp_password = QLineEdit()
        self.inp_password.setEchoMode(QLineEdit.Password)
        self.inp_password.setPlaceholderText("Laisser vide pour exporter sans les identifiants")
        self.inp_password.setFixedHeight(34)
        self.inp_password.setStyleSheet(self._input_style())
        form.addRow(self._label("Mot de passe"), self.inp_password)
        root.addLayout(form)

        note = QLabel(
            "Ce mot de passe chiffre les identifiants des profils référencés "
            "(Oracle/FTP/SMTP/base de données/SSH/Kerberos/Élévation) dans le fichier exporté. "
            "Laissé vide, le fichier ne contiendra aucun mot de passe — à ressaisir manuellement "
            "après import."
        )
        note.setWordWrap(True)
        note.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 11px; font-style: italic;")
        root.addWidget(note)

        root.addWidget(self._sep())
        btn_row = QHBoxLayout(); btn_row.setSpacing(10); btn_row.addStretch()
        btn_cancel = QPushButton("Annuler"); btn_cancel.setObjectName("secondary")
        btn_cancel.setFixedHeight(36); btn_cancel.clicked.connect(self.reject)
        btn_export = QPushButton("Exporter…")
        btn_export.setFixedHeight(36); btn_export.clicked.connect(self._on_export)
        btn_row.addWidget(btn_cancel); btn_row.addWidget(btn_export)
        root.addLayout(btn_row)

    def _on_export(self):
        password = self.inp_password.text() or None

        default_name = f"{self._pipeline.name}.dspipeline"
        path, _ = QFileDialog.getSaveFileName(
            self, "Exporter le pipeline", default_name,
            "Pipeline DataScheduler (*.dspipeline)",
        )
        if not path:
            return

        from database.export_import import export_pipeline_to_file
        result = export_pipeline_to_file(self._pipeline.id, path, password=password)

        if not result.success:
            QMessageBox.critical(self, "Échec de l'export", result.error or "Erreur inconnue.")
            return

        if result.warnings:
            QMessageBox.warning(
                self, "Export terminé avec avertissements",
                "Le pipeline a été exporté, mais :\n\n"
                + "\n".join(f"• {w}" for w in result.warnings),
            )
        else:
            QMessageBox.information(self, "Export réussi", f"Pipeline exporté vers :\n{path}")

        self.accept()

    def _input_style(self, error=False) -> str:
        border = COLORS["danger"] if error else COLORS["border"]
        return (f"QLineEdit {{ background: {COLORS['bg_card']}; border: 1px solid {border}; "
                f"border-radius: 4px; padding: 6px 10px; color: {COLORS['text_main']}; font-size: 13px; }}"
                f"QLineEdit:focus {{ border-color: {COLORS['accent']}; }}")

    def _label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(f"color: {COLORS['text_dim']}; font-size: 12px; font-weight: 500;")
        return lbl

    def _sep(self) -> QFrame:
        f = QFrame(); f.setFrameShape(QFrame.HLine)
        f.setStyleSheet(f"background: {COLORS['border']}; max-height: 1px;")
        return f

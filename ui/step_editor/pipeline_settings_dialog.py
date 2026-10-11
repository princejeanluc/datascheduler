"""
DataScheduler — ui/step_editor/pipeline_settings_dialog.py
Dialogue modal historique "Paramètres du pipeline" — depuis le chantier Atelier Pipelines, son
contenu (①-④, tous les _on_*/_build_*) a été extrait vers PipelineSettingsPanel
(pipeline_settings_panel.py). Ce QDialog n'est plus qu'une fine enveloppe de compatibilité : AUCUN
point d'appel en production ne l'instancie plus directement (PipelineGraphEditorWidget et
PipelinesView ouvrent désormais AtelierPipelinesView) — il n'est conservé que parce que
tests/test_pipeline_settings_dialog.py l'instancie directement et accède à des attributs/méthodes
internes (`dlg.inp_name`, `dlg.tbl_variables`, `dlg._on_save()`, etc.). Un `__getattr__` délègue
tout ce que ce dialogue ne définit pas lui-même à son panneau interne (`self._panel`), pour que
ces tests continuent de passer sans aucune modification.

Extrait à l'origine de l'ancien PipelineEditorDialog (liste linéaire + métadonnées combinées,
retiré — un pipeline construit avec des branches dans l'éditeur graphique, rouvert et enregistré
depuis cet ancien dialogue, pouvait voir ses arêtes silencieusement cassées, save_steps() ne les
touchant jamais mais réassignant step_order/supprimant des PipelineStep référencés par une
PipelineEdge). Toujours invoqué sur un pipeline déjà existant — pas de mode "création", la
création reste exclusivement le flux "nom seul -> éditeur graphique" de
PipelinesView._on_new_pipeline().
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
    # QMessageBox n'est plus utilisé directement ici (voir PipelineSettingsPanel.save()/
    # _validate()) — réimporté quand même pour que
    # tests/test_pipeline_settings_dialog.py::`monkeypatch.setattr(module.QMessageBox, ...)`
    # continue de résoudre `module.QMessageBox` (patche la même classe partagée, peu importe le
    # module qui la référence — mais `module.QMessageBox` doit exister pour ne pas lever
    # AttributeError avant même d'atteindre monkeypatch).
    QMessageBox,
)
from ui.styles import COLORS, DIALOG_STYLE
from .pipeline_settings_panel import PipelineSettingsPanel


class PipelineSettingsDialog(QDialog):
    """Enveloppe modale de PipelineSettingsPanel — voir docstring du module."""

    def __init__(self, parent=None, pipeline=None):
        super().__init__(parent)
        self.setWindowTitle("Paramètres du pipeline")
        self.setMinimumSize(560, 640)
        self.setStyleSheet(DIALOG_STYLE)
        self._build_ui(pipeline)

    def __getattr__(self, name):
        # N'est appelé que si l'attribut est absent du dialogue lui-même — délègue au panneau
        # interne (compatibilité rétroactive des tests existants, voir docstring du module).
        # Garde explicite sur "_panel" : évite une récursion infinie si ce hook est atteint avant
        # que self._panel n'existe encore (ex. pendant super().__init__()).
        if name == "_panel":
            raise AttributeError(name)
        return getattr(self._panel, name)

    def _build_ui(self, pipeline):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        hdr = QLabel("  Paramètres du pipeline")
        hdr.setFixedHeight(48)
        hdr.setStyleSheet(
            f"font-size: 16px; font-weight: 700; color: {COLORS['text_main']};"
            f"padding-left: 28px; border-bottom: 1px solid {COLORS['border']};"
            f"background: {COLORS['bg_panel']};"
        )
        root.addWidget(hdr)

        from PySide6.QtWidgets import QScrollArea
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        self._panel = PipelineSettingsPanel(parent=scroll, pipeline=pipeline)
        scroll.setWidget(self._panel)
        root.addWidget(scroll, stretch=1)

        sep_btn = QFrame(); sep_btn.setFrameShape(QFrame.HLine)
        sep_btn.setStyleSheet(f"background: {COLORS['border']}; max-height: 1px;")
        root.addWidget(sep_btn)

        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(28, 10, 28, 14)
        btn_row.setSpacing(10)
        btn_row.addStretch()
        btn_cancel = QPushButton("Annuler"); btn_cancel.setObjectName("secondary")
        btn_cancel.setFixedHeight(36); btn_cancel.clicked.connect(self.reject)
        btn_save = QPushButton("Enregistrer")
        btn_save.setFixedHeight(36); btn_save.setMinimumWidth(140)
        btn_save.clicked.connect(self._on_save)
        btn_row.addWidget(btn_cancel); btn_row.addWidget(btn_save)
        root.addLayout(btn_row)

    def _on_save(self):
        if self._panel.save():
            self.accept()

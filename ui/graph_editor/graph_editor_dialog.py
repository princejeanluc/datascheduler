"""
DataScheduler — ui/graph_editor/graph_editor_dialog.py
Dialogue modal historique de l'éditeur graphique — depuis le chantier Atelier Pipelines, son
contenu (toolbar/canevas/scène/vue/minimap/rail/zoom, tous les _on_*) a été extrait vers
PipelineGraphEditorWidget (graph_editor_widget.py). Ce QDialog n'est plus qu'une fine enveloppe de
compatibilité : AUCUN point d'appel en production ne l'instancie plus (PipelinesView/HistoryView
ouvrent désormais AtelierPipelinesView, la vue non-modale intégrée à la fenêtre principale) — il
n'est conservé que parce que ~13 fichiers de tests existants l'instancient directement et
accèdent à des attributs/méthodes internes (`dlg._scene`, `dlg._rail`, `dlg._on_save()`, etc.).
Un `__getattr__` délègue tout ce que ce dialogue ne définit pas lui-même à son widget interne
(`self._editor`), pour que ces tests continuent de passer sans aucune modification.
"""

from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame

from ui.styles import COLORS, DIALOG_STYLE
from .graph_editor_widget import (
    PipelineGraphEditorWidget,
    # Ré-exportées pour compatibilité (chantier Atelier Pipelines — ces constantes vivent
    # désormais dans graph_editor_widget.py) : tests/test_graph_tool_rail.py les importe
    # directement depuis ce module.
    _START_X, _START_Y, _NODE_SPACING_X, _ROW_HEIGHT, _ROWS_PER_COLUMN,
)


class PipelineGraphEditorDialog(QDialog):
    """Enveloppe modale de PipelineGraphEditorWidget — voir docstring du module."""

    def __init__(self, parent=None, pipeline=None, highlight_step_key: str | None = None):
        super().__init__(parent)
        self.setWindowTitle(f"Éditeur graphique — {pipeline.name}" if pipeline else "Éditeur graphique")
        self.setMinimumSize(900, 640)
        self.setStyleSheet(DIALOG_STYLE)
        self._build_ui(pipeline, highlight_step_key)

        if not highlight_step_key:
            # Traçage lumineux (chantier identité visuelle) : actif en permanence dès
            # l'ouverture, pas de bascule de mode. Jamais démarré dans le cas highlight_step_key
            # (lien "Voir dans le graphe" sur un run FAILED) — get_running_step_keys_multi()/
            # get_running_step_keys() ne trouvent structurellement jamais un run FAILED (filtrés
            # sur RUNNING), le sondage serait du travail perdu.
            self._editor.start_polling()

    def __getattr__(self, name):
        # N'est appelé que si l'attribut est absent du dialogue lui-même — délègue au widget
        # interne (compatibilité rétroactive des tests existants, voir docstring du module).
        # Garde explicite sur "_editor" : évite une récursion infinie si ce hook est atteint
        # avant que self._editor n'existe encore (ex. pendant super().__init__()).
        if name == "_editor":
            raise AttributeError(name)
        return getattr(self._editor, name)

    def _build_ui(self, pipeline, highlight_step_key):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        hdr = QLabel("  Éditeur graphique du pipeline")
        hdr.setFixedHeight(44)
        hdr.setStyleSheet(
            f"font-size: 15px; font-weight: 700; color: {COLORS['text_main']};"
            f"padding-left: 20px; border-bottom: 1px solid {COLORS['border']};"
            f"background: {COLORS['bg_panel']};"
        )
        root.addWidget(hdr)

        self._editor = PipelineGraphEditorWidget(
            parent=self, pipeline=pipeline, highlight_step_key=highlight_step_key,
            show_settings_shortcut_button=True,
        )
        # Le widget n'a pas de fenêtre à lui — c'est à nous de refléter un renommage fait via
        # "Paramètres du pipeline" dans le titre de CE dialogue (voir
        # tests/test_graph_editor_dialog.py::test_settings_button_opens_settings_dialog_and_refreshes_title).
        self._editor.pipeline_renamed.connect(
            lambda name: self.setWindowTitle(f"Éditeur graphique — {name}")
        )
        root.addWidget(self._editor, stretch=1)

        sep2 = QFrame(); sep2.setFrameShape(QFrame.HLine)
        sep2.setStyleSheet(f"background: {COLORS['border']}; max-height: 1px;")
        root.addWidget(sep2)

        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(20, 10, 20, 14)
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
        if self._editor.save():
            self.accept()

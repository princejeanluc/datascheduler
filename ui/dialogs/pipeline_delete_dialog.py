"""
DataScheduler — ui/dialogs/pipeline_delete_dialog.py
Confirmation de suppression d'un pipeline (lot A-Pipelines, A13) — remplace le QMessageBox.question
inline de PipelinesView._on_delete_pipeline. Liste les dépendants (déclenchés après ce pipeline)
et leur planification propre ; « Exporter d'abord » ouvre PipelineExportDialog sans fermer ni
supprimer.
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame, QWidget,
)
from ui.styles import COLORS, DIALOG_STYLE


class PipelineDeleteDialog(QDialog):
    """`pipeline` : l'objet Pipeline à supprimer. `dependents` : liste de Pipeline déclenchés
    après lui (db.get_pipelines_triggered_by(pipeline.id)). `run_count` : db.count_runs(pipeline.id)
    — affiché dans le texte corrigé par DECISIONS.md::P4 (« seront supprimées », pas « sont
    conservées » : Pipeline.runs a cascade="all, delete-orphan", le comportement n'est pas changé,
    seul le texte est corrigé pour refléter ce qu'il fait réellement)."""

    def __init__(self, parent, pipeline, dependents: list, run_count: int):
        super().__init__(parent)
        self._pipeline = pipeline
        self.setWindowTitle(f"Supprimer {pipeline.name}")
        self.setMinimumWidth(480)
        self.setStyleSheet(DIALOG_STYLE)
        self._build_ui(dependents, run_count)

    def _build_ui(self, dependents: list, run_count: int):
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(16)

        surtitle = QLabel("SUPPRIMER")
        surtitle.setStyleSheet(
            f"color: {COLORS['danger']}; font-size: 10px; font-weight: 700; letter-spacing: 0.06em;"
        )
        root.addWidget(surtitle)

        title = QLabel(f"Supprimer {self._pipeline.name} ?")
        title.setStyleSheet(f"font-size: 16px; font-weight: 700; color: {COLORS['text_main']};")
        root.addWidget(title)

        if dependents:
            n = len(dependents)
            intro = QLabel(
                f"{n} pipeline{'s' if n > 1 else ''} se lance{'nt' if n > 1 else ''} après "
                f"celui-ci. Ils resteront, mais ne partiront plus que sur leur propre "
                f"planification :"
            )
            intro.setWordWrap(True)
            intro.setStyleSheet(f"color: {COLORS['text_main']}; font-size: 12.5px;")
            root.addWidget(intro)

            from core.scheduler import describe_schedule

            deps_frame = QFrame()
            deps_frame.setStyleSheet(
                f"QFrame {{ background: {COLORS['bg_main']}; border: 1px solid {COLORS['border']}; "
                f"border-radius: 8px; }}"
            )
            deps_layout = QVBoxLayout(deps_frame)
            deps_layout.setContentsMargins(12, 10, 12, 10)
            deps_layout.setSpacing(6)
            for dep in dependents:
                row = QHBoxLayout()
                name_lbl = QLabel(f'<span style="color:{COLORS["relation"]}">↳</span> <b>{dep.name}</b>')
                name_lbl.setStyleSheet(f"color: {COLORS['text_main']}; font-size: 12.5px; background: transparent; border: none;")
                row.addWidget(name_lbl)
                row.addStretch()
                # Sans B3 (Lot B, hors périmètre), tout pipeline a toujours sa propre
                # planification réelle — jamais le texte "n'a pas d'autre planification" de la
                # maquette, qui dépend d'une colonne qui n'existe pas encore.
                schedule_lbl = QLabel(f"garde {describe_schedule(dep)}")
                schedule_lbl.setStyleSheet(f"color: {COLORS['text_dim']}; font-size: 12px; background: transparent; border: none;")
                row.addWidget(schedule_lbl)
                deps_layout.addLayout(row)
            root.addWidget(deps_frame)

        history_note = QLabel(
            f"Les {run_count} exécutions de l'historique seront supprimées. Pense à exporter "
            f"le pipeline si tu veux pouvoir le recréer."
        )
        history_note.setWordWrap(True)
        history_note.setStyleSheet(f"color: {COLORS['text_dim']}; font-size: 11.5px;")
        root.addWidget(history_note)

        root.addWidget(self._sep())
        btn_row = QHBoxLayout(); btn_row.setSpacing(8); btn_row.addStretch()
        btn_export = QPushButton("Exporter d'abord"); btn_export.setObjectName("secondary")
        btn_export.setFixedHeight(36)
        btn_export.clicked.connect(self._on_export_first)
        btn_row.addWidget(btn_export)
        btn_cancel = QPushButton("Annuler"); btn_cancel.setObjectName("secondary")
        btn_cancel.setFixedHeight(36); btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(btn_cancel)
        self.btn_delete = QPushButton("Supprimer"); self.btn_delete.setObjectName("danger")
        self.btn_delete.setFixedHeight(36); self.btn_delete.clicked.connect(self.accept)
        btn_row.addWidget(self.btn_delete)
        root.addLayout(btn_row)

    def _on_export_first(self):
        from ui.dialogs.pipeline_export_dialog import PipelineExportDialog
        PipelineExportDialog(self, pipeline=self._pipeline).exec()

    def _sep(self) -> QFrame:
        f = QFrame(); f.setFrameShape(QFrame.HLine)
        f.setStyleSheet(f"background: {COLORS['border']}; max-height: 1px;")
        return f

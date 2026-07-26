"""
DataScheduler — ui/main_window/pipelines_view.py
Vue Pipelines : liste + création + export/import.
"""

from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton, QFrame,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QMessageBox, QFileDialog,
)
from PySide6.QtCore import Qt, QSize, QTimer
from PySide6.QtGui import QColor, QShortcut, QKeySequence
from ui.styles import COLORS
from .widgets import _icon, _action_btn, _configure_columns, _filter_table_rows, _make_search_input, _make_empty_label, _make_title, _make_subtitle, _STATUS_BADGE, _status_str


class PipelinesView(QWidget):
    def __init__(self):
        super().__init__()
        self._build_ui()
        self._timer = QTimer(self)
        self._timer.setInterval(30_000)
        self._timer.timeout.connect(self.refresh)
        self._timer.start()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(24)

        header = QHBoxLayout()
        title_col = QVBoxLayout(); title_col.setSpacing(2)
        title_col.addWidget(_make_title("Pipelines"))
        title_col.addWidget(_make_subtitle("Orchestration flexible par étapes"))
        header.addLayout(title_col); header.addStretch()
        self.inp_search = _make_search_input("Rechercher un pipeline…  (Ctrl+N : nouveau)")
        self.inp_search.textChanged.connect(self._on_search_changed)
        header.addWidget(self.inp_search)
        btn_import = QPushButton("  Importer"); btn_import.setObjectName("secondary")
        btn_import.setFixedHeight(36)
        btn_import.setIcon(_icon("fa5s.file-import", COLORS["text_main"]))
        btn_import.setIconSize(QSize(13, 13))
        btn_import.clicked.connect(self._on_import_pipeline)
        header.addWidget(btn_import)
        btn_new = QPushButton("  Nouveau pipeline"); btn_new.setFixedHeight(36)
        btn_new.setIcon(_icon("fa5s.plus", "#000000")); btn_new.setIconSize(QSize(13, 13))
        btn_new.clicked.connect(self._on_new_pipeline)
        header.addWidget(btn_new)
        layout.addLayout(header)

        sep = QFrame(); sep.setObjectName("separator"); sep.setFrameShape(QFrame.HLine)
        layout.addWidget(sep)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            ["Nom", "Statut", "Étapes", "Planification", "Prochaine exéc.", "Actions"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setShowGrid(False)
        _configure_columns(self.table, stretch_cols={0, 2})
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Fixed)
        self.table.setColumnWidth(1, 130)
        self.table.setColumnWidth(5, 222)
        layout.addWidget(self.table)

        self._empty_label = _make_empty_label(
            "Aucun pipeline configuré — cliquez sur « Nouveau pipeline » pour créer le premier."
        )
        self._empty_label.setVisible(False)
        layout.addWidget(self._empty_label)

        QShortcut(QKeySequence("Ctrl+N"), self, activated=self._on_new_pipeline)

        self.refresh()

    def _on_search_changed(self, text: str):
        _filter_table_rows(self.table, text, columns=[0, 1, 2, 3, 4])

    def refresh(self):
        from database import db_manager as db
        from ui.step_editor import STEP_META
        pipelines = db.get_pipelines()
        self.table.setVisible(bool(pipelines))
        self._empty_label.setVisible(not pipelines)
        self.table.setRowCount(len(pipelines))
        for r_idx, p in enumerate(pipelines):
            st       = _status_str(p.last_status)
            freq     = _status_str(p.frequency)
            plan     = f"{freq} {p.scheduled_time or ''}".strip()
            next_run = p.next_run_at.strftime("%d/%m/%Y %H:%M") if p.next_run_at else "—"

            # Résumé des étapes
            step_types = [str(s.step_type).replace("StepType.", "") for s in (p.steps or [])]
            steps_str  = " → ".join(
                STEP_META.get(t, {}).get("label", t) for t in step_types
            ) or "—"

            text_color = COLORS["text_dim"] if not p.is_active else COLORS["text_main"]
            cells = [p.name, st, steps_str, plan, next_run]
            for c_idx, cell in enumerate(cells):
                if c_idx == 1:
                    badge_st   = "INACTIF" if not p.is_active else st
                    badge_name = "badge_idle" if not p.is_active else _STATUS_BADGE.get(st, "badge_idle")
                    badge = QLabel(badge_st); badge.setObjectName(badge_name)
                    badge.setAlignment(Qt.AlignCenter)
                    self.table.setCellWidget(r_idx, c_idx, badge)
                else:
                    item = QTableWidgetItem(cell)
                    item.setForeground(QColor(text_color))
                    if c_idx == 2:
                        item.setToolTip(steps_str)
                    self.table.setItem(r_idx, c_idx, item)

            pid       = p.id
            is_active = p.is_active
            aw  = QWidget(); al = QHBoxLayout(aw); al.setContentsMargins(4, 4, 4, 4); al.setSpacing(4)
            btn_run = _action_btn("fa5s.play", tooltip="Exécuter maintenant",
                                  icon_color="#000000")
            btn_toggle = _action_btn(
                "fa5s.pause" if is_active else "fa5s.play",
                object_name="secondary",
                tooltip="Désactiver" if is_active else "Activer",
                icon_color=COLORS["text_main"] if is_active else COLORS["success"],
            )
            if not is_active:
                btn_toggle.setStyleSheet(
                    f"QPushButton {{ color: {COLORS['success']}; border: 1px solid {COLORS['success']}; "
                    f"border-radius: 4px; background: transparent; }}"
                    f"QPushButton:hover {{ background: {COLORS['success']}; color: #000; }}"
                )
            btn_edit   = _action_btn("fa5s.pencil-alt", object_name="secondary", tooltip="Modifier")
            btn_graph  = _action_btn("fa5s.project-diagram", object_name="secondary",
                                     tooltip="Éditeur graphique")
            btn_export = _action_btn("fa5s.file-export", object_name="secondary", tooltip="Exporter")
            btn_del    = _action_btn("fa5s.trash-alt",  object_name="danger",    tooltip="Supprimer")
            btn_run.clicked.connect(lambda _, i=pid: self._on_run_pipeline(i))
            btn_toggle.clicked.connect(lambda _, i=pid, a=is_active: self._on_toggle_pipeline(i, a))
            btn_edit.clicked.connect(lambda _, i=pid: self._on_edit_pipeline(i))
            btn_graph.clicked.connect(lambda _, i=pid: self._on_edit_pipeline_graph(i))
            btn_export.clicked.connect(lambda _, i=pid: self._on_export_pipeline(i))
            btn_del.clicked.connect(lambda _, i=pid: self._on_delete_pipeline(i))
            al.addWidget(btn_run); al.addWidget(btn_toggle)
            al.addWidget(btn_edit); al.addWidget(btn_graph)
            al.addWidget(btn_export); al.addWidget(btn_del); al.addStretch()
            self.table.setCellWidget(r_idx, 5, aw)
            self.table.setRowHeight(r_idx, 52)

        self._on_search_changed(self.inp_search.text())

    def _on_new_pipeline(self):
        from ui.step_editor import PipelineEditorDialog
        if PipelineEditorDialog(self).exec():
            self.refresh()

    def _on_import_pipeline(self):
        from database.export_import import plan_import_from_file, apply_import
        from ui.dialogs import PipelineImportPasswordDialog, PipelineImportReviewDialog

        path, _ = QFileDialog.getOpenFileName(
            self, "Importer un pipeline", "", "Pipeline DataScheduler (*.dspipeline)",
        )
        if not path:
            return

        plan = plan_import_from_file(path)

        if plan.needs_password:
            pwd_dlg = PipelineImportPasswordDialog(self)
            if not pwd_dlg.exec():
                return
            plan = plan_import_from_file(path, password=pwd_dlg.password())

        if not plan.success:
            QMessageBox.critical(self, "Échec de l'import", plan.error or "Erreur inconnue.")
            return

        review_dlg = PipelineImportReviewDialog(self, plan=plan)
        if not review_dlg.exec():
            return

        result = apply_import(plan)
        if not result.success:
            QMessageBox.critical(self, "Échec de l'import", result.error or "Erreur inconnue.")
            return

        if result.warnings:
            QMessageBox.warning(
                self, "Import terminé avec avertissements",
                "Le pipeline a été importé, mais :\n\n"
                + "\n".join(f"• {w}" for w in result.warnings),
            )
        else:
            QMessageBox.information(self, "Import réussi", "Le pipeline a été importé avec succès.")

        self.refresh()

    def _on_edit_pipeline(self, pipeline_id: int):
        from database import db_manager as db
        from ui.step_editor import PipelineEditorDialog
        p = db.get_pipeline(pipeline_id)
        if p and PipelineEditorDialog(self, pipeline=p).exec():
            self.refresh()

    def _on_edit_pipeline_graph(self, pipeline_id: int):
        from database import db_manager as db
        from ui.graph_editor import PipelineGraphEditorDialog
        p = db.get_pipeline(pipeline_id)
        if p and PipelineGraphEditorDialog(self, pipeline=p).exec():
            self.refresh()

    def _on_export_pipeline(self, pipeline_id: int):
        from database import db_manager as db
        from ui.dialogs import PipelineExportDialog
        p = db.get_pipeline(pipeline_id)
        if p:
            PipelineExportDialog(self, pipeline=p).exec()

    def _on_run_pipeline(self, pipeline_id: int):
        from database import db_manager as db
        from ui.dialogs import RunProgressDialog
        from core.pipeline import is_pipeline_running, request_cancel
        p = db.get_pipeline(pipeline_id)
        if not p:
            return

        if p.prevent_overlap and is_pipeline_running(pipeline_id):
            box = QMessageBox(self)
            box.setWindowTitle("Pipeline déjà en cours")
            box.setText(
                f"« {p.name} » est déjà en cours d'exécution.\n\n"
                "L'interruption est coopérative : elle prend effet à la fin de l'étape en "
                "cours, pas instantanément si celle-ci est longue (ex: une extraction Oracle "
                "de plusieurs minutes). Relancez manuellement une fois le run arrêté."
            )
            btn_interrupt = box.addButton("Interrompre l'exécution en cours", QMessageBox.DestructiveRole)
            box.addButton("Annuler", QMessageBox.RejectRole)
            box.setDefaultButton(box.buttons()[-1])
            box.exec()
            if box.clickedButton() == btn_interrupt:
                request_cancel(pipeline_id)
                QMessageBox.information(
                    self, "Demande envoyée",
                    "L'arrêt a été demandé — relancez le pipeline une fois qu'il se sera arrêté."
                )
            return

        RunProgressDialog(pipeline_id, p.name, self).exec()
        self.refresh()

    def _on_delete_pipeline(self, pipeline_id: int):
        from database import db_manager as db
        reply = QMessageBox.question(self, "Supprimer", "Supprimer ce pipeline ?",
                                     QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            db.delete_pipeline(pipeline_id)
            self.refresh()

    def _on_toggle_pipeline(self, pipeline_id: int, currently_active: bool):
        from database import db_manager as db
        new_active = not currently_active
        db.set_pipeline_active(pipeline_id, new_active)
        try:
            from core.scheduler import get_scheduler
            sched = get_scheduler()
            if new_active:
                sched.schedule_pipeline(pipeline_id)
            else:
                sched.remove_pipeline(pipeline_id)
        except RuntimeError:
            pass
        self.refresh()

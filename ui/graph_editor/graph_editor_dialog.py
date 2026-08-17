"""
DataScheduler — ui/graph_editor/graph_editor_dialog.py
Dialogue principal de l'éditeur graphique (chantier 6b) : édite uniquement les étapes + leurs
connexions d'un pipeline déjà existant. Nom/description/planification restent gérés par
PipelineEditorDialog ("Modifier"), inchangé — les deux dialogues restent interopérables sur le
même pipeline (voir docs/ARCHITECTURE.md).
"""

from PySide6.QtCore import QPointF, QTimer
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame, QMessageBox,
)

from ui.styles import COLORS, DIALOG_STYLE
from ui.step_editor.step_type_chooser_dialog import StepTypeChooserDialog
from core.pipeline import validate_pipeline_graph

from .graph_scene import PipelineGraphScene
from .graph_view import PipelineGraphView
from .node_item import StepNodeItem
from .edge_item import EdgeItem

_NODE_SPACING_X = 240
_ROW_HEIGHT = 120
_ROWS_PER_COLUMN = 3
_START_X, _START_Y = 60, 60


class PipelineGraphEditorDialog(QDialog):
    """Éditeur graphique des étapes d'un pipeline déjà existant."""

    def __init__(self, parent=None, pipeline=None):
        super().__init__(parent)
        self._pipeline = pipeline
        self._load_profiles()

        self.setWindowTitle(f"Éditeur graphique — {pipeline.name}" if pipeline else "Éditeur graphique")
        self.setMinimumSize(900, 640)
        self.setStyleSheet(DIALOG_STYLE)
        self._build_ui()
        self._load_graph()

        # Traçage lumineux (chantier identité visuelle) : actif en permanence dès l'ouverture,
        # pas de bascule de mode — éditer un pipeline qui se trouve être en cours d'exécution
        # ailleurs affiche simplement le surlignage par-dessus, sans bloquer l'édition.
        from database import db_manager as db
        self._executing_timer = QTimer(self)
        self._executing_timer.setInterval(db.get_app_settings().trace_glow_refresh_s * 1000)
        self._executing_timer.timeout.connect(self._poll_executing_step)
        self._executing_timer.start()

    def _poll_executing_step(self):
        if not self._pipeline:
            return
        from database import db_manager as db
        step_key = db.get_running_step_keys().get(self._pipeline.id)
        self._scene.set_executing_step_key(step_key)

    # ── Données ──────────────────────────────

    def _load_profiles(self):
        from database import db_manager as db
        self._oracle_profiles = db.get_oracle_profiles()
        self._ftp_profiles    = db.get_ftp_profiles()
        self._sql_queries     = db.get_sql_queries()
        self._smtp_profiles   = db.get_smtp_profiles()
        self._db_profiles     = db.list_all_db_profiles()

    # ── Construction UI ──────────────────────

    def _build_ui(self):
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

        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(16, 8, 16, 8)
        toolbar.setSpacing(8)

        btn_add = QPushButton("  + Ajouter une étape")
        btn_add.setObjectName("secondary")
        btn_add.setFixedHeight(32)
        btn_add.clicked.connect(self._on_add_step)
        toolbar.addWidget(btn_add)

        btn_delete = QPushButton("  Supprimer la sélection")
        btn_delete.setObjectName("secondary")
        btn_delete.setFixedHeight(32)
        btn_delete.clicked.connect(self._on_delete_selected)
        toolbar.addWidget(btn_delete)

        btn_schedule = QPushButton("  Planification & déclenchement…")
        btn_schedule.setObjectName("secondary")
        btn_schedule.setFixedHeight(32)
        btn_schedule.setToolTip(
            "Ouvre l'éditeur classique pour le nom, la planification et le déclenchement "
            "conditionnel — enregistrez d'abord vos modifications du graphe si besoin, les deux "
            "éditeurs ne partagent pas leurs changements non enregistrés."
        )
        btn_schedule.clicked.connect(self._on_open_schedule_dialog)
        toolbar.addWidget(btn_schedule)

        hint = QLabel(
            "Glisser depuis un point de sortie (droite) vers un point d'entrée (gauche) pour "
            "connecter deux étapes.  Suppr/Retour arrière pour supprimer la sélection."
        )
        hint.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 11px; font-style: italic;")
        toolbar.addWidget(hint, stretch=1)

        root.addLayout(toolbar)

        sep = QFrame(); sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet(f"background: {COLORS['border']}; max-height: 1px;")
        root.addWidget(sep)

        self._scene = PipelineGraphScene()
        self._scene.node_double_clicked.connect(self._on_node_double_clicked)
        self._view = PipelineGraphView(self._scene)
        root.addWidget(self._view, stretch=1)

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

    # ── Chargement ────────────────────────────

    def _load_graph(self):
        if not self._pipeline:
            return
        from database import db_manager as db
        import json

        steps = db.get_steps(self._pipeline.id)
        edges = db.get_edges(self._pipeline.id)

        all_at_origin = all(s.pos_x == 0 and s.pos_y == 0 for s in steps) if steps else True

        for i, s in enumerate(steps):
            step = {
                "step_type":   str(s.step_type).replace("StepType.", ""),
                "label":       s.label or "",
                "config":      json.loads(s.config_json or "{}"),
                "retry_count": s.retry_count or 0,
                "run_always":  bool(s.run_always),
            }
            if all_at_origin:
                col, row = divmod(i, _ROWS_PER_COLUMN)
                pos = QPointF(_START_X + col * _NODE_SPACING_X, _START_Y + row * _ROW_HEIGHT)
            else:
                pos = QPointF(s.pos_x, s.pos_y)
            self._scene.add_node(step, pos)

        for e in edges:
            self._scene.add_edge(e.from_step_key, e.from_port, e.to_step_key)

    # ── Ajout / édition / suppression ─────────

    def _next_new_node_pos(self) -> QPointF:
        if not self._scene.nodes:
            return QPointF(_START_X, _START_Y)
        max_x = max(n.pos().x() for n in self._scene.nodes.values())
        return QPointF(max_x + _NODE_SPACING_X, _START_Y)

    def _on_add_step(self):
        from ui.step_editor import _open_config_dialog

        dlg = StepTypeChooserDialog(self, include_condition=True)
        if not dlg.exec():
            return
        config_dlg = _open_config_dialog(
            dlg.chosen_type, {}, self,
            self._oracle_profiles, self._ftp_profiles, self._sql_queries,
            self._smtp_profiles, self._db_profiles,
            prior_steps=[],
        )
        if config_dlg and config_dlg.exec():
            step = config_dlg.result_step()
            self._scene.add_node(step, self._next_new_node_pos())

    def _on_node_double_clicked(self, node: StepNodeItem):
        from ui.step_editor import _open_config_dialog

        step = node.step
        config_dlg = _open_config_dialog(
            step["step_type"], step.get("config", {}), self,
            self._oracle_profiles, self._ftp_profiles, self._sql_queries,
            self._smtp_profiles, self._db_profiles,
            label=step.get("label", ""),
            retry_count=step.get("retry_count", 0),
            run_always=step.get("run_always", False),
            timeout_s=step.get("timeout_s", 0),
            prior_steps=[],
        )
        if config_dlg and config_dlg.exec():
            node.step = config_dlg.result_step()
            node.update()

    def _on_delete_selected(self):
        for item in list(self._scene.selectedItems()):
            if isinstance(item, StepNodeItem):
                self._scene.remove_node(item)
            elif isinstance(item, EdgeItem):
                self._scene.remove_edge(item)

    def _on_open_schedule_dialog(self):
        """Raccourci vers l'éditeur classique pour le nom/planification/déclenchement
        conditionnel (chantier P) — ce dialogue ne les gère pas lui-même (voir docstring du
        module) ; évite l'aller-retour "fermer, retrouver la ligne, cliquer Modifier"."""
        from database import db_manager as db
        from ui.step_editor import PipelineEditorDialog

        if PipelineEditorDialog(self, pipeline=self._pipeline).exec():
            refreshed = db.get_pipeline(self._pipeline.id)
            if refreshed:
                self._pipeline = refreshed
                self.setWindowTitle(f"Éditeur graphique — {refreshed.name}")

    # ── Sauvegarde ───────────────────────────

    def _collect_graph(self):
        steps = []
        for node in self._scene.nodes.values():
            step = dict(node.step)
            step["pos_x"] = int(node.pos().x())
            step["pos_y"] = int(node.pos().y())
            steps.append(step)

        edges = [
            {
                "from_step_key": e.from_node.step_key,
                "from_port":     e.from_port,
                "to_step_key":   e.to_node.step_key,
                "to_port":       "input",
            }
            for e in self._scene.edges
        ]
        return steps, edges

    def _on_save(self):
        steps, edges = self._collect_graph()

        if not steps:
            QMessageBox.warning(
                self, "Étapes manquantes",
                "Ajoutez au moins une étape avant d'enregistrer.",
            )
            return

        errors, warnings = validate_pipeline_graph(steps, edges)
        if errors:
            QMessageBox.warning(
                self, "Graphe invalide",
                "Ce graphe d'étapes ne peut pas fonctionner :\n\n"
                + "\n".join(f"• {e}" for e in errors),
            )
            return
        if warnings:
            reply = QMessageBox.question(
                self, "Avertissement",
                "Certaines étapes pourraient tourner sans les données attendues :\n\n"
                + "\n".join(f"• {w}" for w in warnings)
                + "\n\nContinuer quand même ?",
                QMessageBox.Yes | QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return

        from database import db_manager as db
        db.save_pipeline_graph(self._pipeline.id, steps, edges)
        self.accept()

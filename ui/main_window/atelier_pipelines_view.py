"""
DataScheduler — ui/main_window/atelier_pipelines_view.py
Atelier Pipelines (chantier Atelier Pipelines, écran 2) : fusion non-modale de
PipelineGraphEditorDialog + PipelineSettingsDialog en une vue intégrée à la fenêtre principale —
sidebar de pipelines repliable (AtelierSidebar) à gauche, canevas (PipelineGraphEditorWidget) au
centre, panneau de paramètres (PipelineSettingsPanel) à droite. Pas un QSplitter — même patron de
layout que l'Atelier SQL (ui/main_window/queries_view.py) : colonnes à largeur fixe/stretch,
QHBoxLayout zéro marge.

Jamais une entrée de la nav rail à 8 items fixes (ui/main_window/window.py) — reconnu comme vue
9 (indice 8) du même QStackedWidget, hors des indices connus de NavRail (set_active_index(8) ne
surligne simplement aucun bouton, sans aucune modification de NavRail) ; atteint uniquement par
une action depuis une ligne de PipelinesView ou HistoryView (signal open_atelier_requested →
MainWindow.open_atelier()), jamais directement. back_requested ramène à l'écran 1 (gestion
rapide) — même idiome que les signaux navigate_to_history/navigate_to_settings du Dashboard, déjà
câblés en dur dans MainWindow.

Sauvegarde : deux boutons explicites et indépendants (graphe / paramètres), jamais fusionnés —
ce sont deux opérations DB réellement différentes (save_pipeline_graph vs update_pipeline+
set_pipeline_active+save_pipeline_variables+set_pipeline_trigger), chacune avec sa propre
validation. Aucune sauvegarde automatique ; changer de pipeline sélectionné dans la sidebar
recharge le canevas/panneau sans confirmation — même principe assumé que l'Atelier SQL
(queries_view.py : « changer de sélection écrase silencieusement l'éditeur sans confirmation »).
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame, QScrollArea,
)
from PySide6.QtCore import Qt, QSize, QTimer, Signal
from ui.styles import COLORS
from .widgets import _icon, HEADER_H, _status_str
from .atelier_sidebar import AtelierSidebar


def _vline() -> QFrame:
    f = QFrame(); f.setFrameShape(QFrame.VLine)
    f.setStyleSheet(f"background: {COLORS['border']}; max-width: 1px;")
    return f


class AtelierPipelinesView(QWidget):
    """Voir docstring du module."""

    back_requested = Signal()

    SETTINGS_PANEL_WIDTH = 360

    def __init__(self):
        super().__init__()
        self._pipeline_id: int | None = None
        self._is_new_pipeline = False
        self._canvas = None
        self._settings_panel = None
        self._build_ui()

        from database import db_manager as db
        self._timer = QTimer(self)
        self._timer.setInterval(db.get_app_settings().pipelines_refresh_s * 1000)
        self._timer.timeout.connect(self.refresh)
        self._timer.start()

    # ── Construction UI ──────────────────────

    def _build_ui(self):
        from database import db_manager as db

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header = QWidget()
        header.setFixedHeight(HEADER_H)
        header.setStyleSheet(
            f"background: {COLORS['bg_panel']}; border-bottom: 1px solid {COLORS['border']};"
        )
        hl = QHBoxLayout(header)
        hl.setContentsMargins(16, 0, 16, 0)
        hl.setSpacing(14)
        btn_back = QPushButton("  Retour aux pipelines")
        btn_back.setObjectName("secondary")
        btn_back.setFixedHeight(32)
        btn_back.setIcon(_icon("fa5s.arrow-left", COLORS["text_main"]))
        btn_back.setIconSize(QSize(13, 13))
        btn_back.clicked.connect(self._on_back_clicked)
        hl.addWidget(btn_back)
        self._title_lbl = QLabel("")
        self._title_lbl.setStyleSheet(
            f"color: {COLORS['text_main']}; font-size: 14px; font-weight: 700; "
            f"background: transparent; border: none;"
        )
        hl.addWidget(self._title_lbl)
        hl.addStretch()
        root.addWidget(header)

        body = QWidget()
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)

        self._sidebar = AtelierSidebar(initial_collapsed=db.get_app_settings().atelier_sidebar_collapsed)
        self._sidebar.collapsed_changed.connect(
            lambda c: db.update_app_settings(atelier_sidebar_collapsed=c)
        )
        self._sidebar.pipeline_selected.connect(self.open_pipeline)
        body_layout.addWidget(self._sidebar)
        body_layout.addWidget(_vline())

        self._canvas_container = QWidget()
        self._canvas_container_layout = QVBoxLayout(self._canvas_container)
        self._canvas_container_layout.setContentsMargins(0, 0, 0, 0)
        self._canvas_container_layout.setSpacing(0)
        body_layout.addWidget(self._canvas_container, stretch=1)
        body_layout.addWidget(_vline())

        self._settings_container = QWidget()
        self._settings_container.setFixedWidth(self.SETTINGS_PANEL_WIDTH)
        self._settings_container_layout = QVBoxLayout(self._settings_container)
        self._settings_container_layout.setContentsMargins(0, 0, 0, 0)
        self._settings_container_layout.setSpacing(0)
        body_layout.addWidget(self._settings_container)

        root.addWidget(body, stretch=1)

    @staticmethod
    def _clear_container(layout) -> None:
        """Vide récursivement `layout` — widgets ET sous-layouts (la rangée de boutons
        "Enregistrer" ajoutée via addLayout()). deleteLater() plutôt qu'une destruction
        immédiate : cohérent avec le reste de l'appli (ex. PipelinesView.refresh() reconstruit sa
        colonne Actions à chaque appel sans jamais appeler deleteWidget() de force)."""
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
                continue
            sub = item.layout()
            if sub is not None:
                AtelierPipelinesView._clear_container(sub)

    # ── Ouverture d'un pipeline ────────────────

    def open_pipeline(self, pipeline_id: int, highlight_step_key: str | None = None,
                       is_new_pipeline: bool = False):
        """`is_new_pipeline` (chantier Atelier Pipelines) : True uniquement depuis le flux
        "+ Nouveau pipeline" de PipelinesView — reproduit à l'identique les deux comportements de
        l'ancien PipelineGraphEditorDialog().exec() de ce flux précis : (1) planifie
        immédiatement une fois le graphe enregistré pour la première fois (voir le câblage de
        `saved` plus bas — avant, `_schedule_if_possible` suivait la fermeture modale réussie du
        dialogue) ; (2) sur retour sans avoir ajouté d'étape, supprime le pipeline coquille (voir
        _on_back_clicked). Jamais vrai pour une simple édition (_on_edit_pipeline_graph/
        _on_edit_pipeline_settings/HistoryView._open_graph) ni pour le flux "modèle de
        démarrage" (_on_start_from_template, qui planifie déjà de façon synchrone à la création,
        avant même d'ouvrir l'Atelier — le pipeline a déjà de vraies étapes, ce n'est jamais une
        coquille à protéger)."""
        from database import db_manager as db
        from ui.graph_editor import PipelineGraphEditorWidget

        if self._canvas is not None:
            self._canvas.stop_polling()
        self._clear_container(self._canvas_container_layout)
        self._clear_container(self._settings_container_layout)
        self._canvas = None
        self._settings_panel = None

        pipeline = db.get_pipeline(pipeline_id)
        if not pipeline:
            self._pipeline_id = None
            self._is_new_pipeline = False
            self._title_lbl.setText("")
            placeholder = QLabel("Pipeline introuvable — retournez à la liste.")
            placeholder.setAlignment(Qt.AlignCenter)
            placeholder.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 13px;")
            self._canvas_container_layout.addWidget(placeholder, stretch=1)
            return

        self._pipeline_id = pipeline_id
        self._is_new_pipeline = is_new_pipeline
        self._title_lbl.setText(pipeline.name)

        self._canvas = PipelineGraphEditorWidget(
            parent=self._canvas_container, pipeline=pipeline,
            highlight_step_key=highlight_step_key, show_settings_shortcut_button=False,
        )
        self._canvas_container_layout.addWidget(self._canvas, stretch=1)

        if is_new_pipeline:
            self._canvas.saved.connect(self._on_new_pipeline_graph_first_saved)

        graph_btn_row = QHBoxLayout()
        graph_btn_row.setContentsMargins(16, 8, 16, 10)
        graph_btn_row.addStretch()
        btn_save_graph = QPushButton("Enregistrer le graphe")
        btn_save_graph.setFixedHeight(34); btn_save_graph.setMinimumWidth(150)
        btn_save_graph.clicked.connect(self._canvas.save)
        graph_btn_row.addWidget(btn_save_graph)
        self._canvas_container_layout.addLayout(graph_btn_row)

        if not highlight_step_key:
            self._canvas.start_polling()

        from ui.step_editor.pipeline_settings_panel import PipelineSettingsPanel

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        self._settings_panel = PipelineSettingsPanel(parent=scroll, pipeline=pipeline)
        scroll.setWidget(self._settings_panel)
        self._settings_container_layout.addWidget(scroll, stretch=1)

        settings_sep = QFrame(); settings_sep.setFrameShape(QFrame.HLine)
        settings_sep.setStyleSheet(f"background: {COLORS['border']}; max-height: 1px;")
        self._settings_container_layout.addWidget(settings_sep)

        settings_btn_row = QHBoxLayout()
        settings_btn_row.setContentsMargins(16, 10, 16, 14)
        settings_btn_row.addStretch()
        btn_save_settings = QPushButton("Enregistrer les paramètres")
        btn_save_settings.setFixedHeight(34); btn_save_settings.setMinimumWidth(150)
        btn_save_settings.clicked.connect(self._settings_panel.save)
        settings_btn_row.addWidget(btn_save_settings)
        self._settings_container_layout.addLayout(settings_btn_row)

        self._sidebar.select_pipeline(pipeline_id)

    def _on_new_pipeline_graph_first_saved(self):
        """(Re)planifie une seule fois le premier enregistrement réussi d'un pipeline neuf —
        voir la docstring de `is_new_pipeline` dans open_pipeline(). Le signal `saved` du canevas
        reste connecté après ce premier appel (pas de déconnexion) : un second enregistrement du
        même graphe replanifie simplement de nouveau, ce qui est inoffensif (même garde
        défensive que _schedule_if_possible lui-même)."""
        from .pipelines_view import PipelinesView
        if self._pipeline_id is not None:
            PipelinesView._schedule_if_possible(self._pipeline_id)

    def _on_back_clicked(self):
        if self._is_new_pipeline and self._pipeline_id is not None:
            from database import db_manager as db
            # get_steps(), pas pipeline.steps : get_pipeline() n'eager-charge pas la relation
            # steps (seulement trigger_after_pipeline) — y accéder après la fermeture de la
            # session lèverait DetachedInstanceError (même piège documenté pour
            # trigger_after_pipeline dans get_pipeline() lui-même).
            if not db.get_steps(self._pipeline_id):
                # Retour sans avoir ajouté d'étape — un pipeline coquille à 0 étape ne servirait
                # qu'à encombrer la liste (même règle que l'ancien _on_new_pipeline()).
                db.delete_pipeline(self._pipeline_id)
        if self._canvas is not None:
            self._canvas.stop_polling()
        self.back_requested.emit()

    # ── Rafraîchissement ───────────────────────

    def refresh(self):
        """Ne touche QUE la sidebar (liste/statuts) — jamais le canevas/panneau déjà ouverts :
        ni F5 (MainWindow._refresh_current_view) ni ce timer périodique ne doivent jamais
        écraser silencieusement une édition en cours."""
        from database import db_manager as db
        pipelines = db.get_pipelines()
        rows = [
            {"id": p.id, "name": p.name, "status": _status_str(p.last_status), "is_active": p.is_active}
            for p in pipelines
        ]
        self._sidebar.set_pipelines(rows)
        self._sidebar.select_pipeline(self._pipeline_id)

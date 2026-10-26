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
from .widgets import _icon, HEADER_H, _status_str, _make_status_badge
from .atelier_sidebar import AtelierSidebar
from .pipeline_actions import run_pipeline_now


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
        self._run_id: int | None = None
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
        # Sélecteur d'ID (objectName) + WA_StyledBackground, pas une règle nue — une règle nue se
        # propage à tous les descendants et écrasait silencieusement le fond orange plein par
        # défaut de tout QPushButton sans objectName à l'intérieur (ex. "Exécuter" — bug réel
        # constaté en capture, même piège que side_panel.py, REGLES.md section 3).
        header.setObjectName("atelierHeader")
        header.setAttribute(Qt.WA_StyledBackground, True)
        header.setStyleSheet(
            f"QWidget#atelierHeader {{ background: {COLORS['bg_panel']}; "
            f"border-bottom: 1px solid {COLORS['border']}; }}"
        )
        hl = QHBoxLayout(header)
        hl.setContentsMargins(16, 0, 16, 0)
        hl.setSpacing(10)

        # A6 (lot A-Atelier-main) : fil d'Ariane « Pipelines / <nom> » — remplace l'ancien bouton
        # "Retour aux pipelines". _on_back_clicked garde son nom public et son comportement
        # (suppression d'un pipeline neuf sans étape, stop_polling, back_requested).
        btn_crumb_pipelines = QPushButton("Pipelines")
        btn_crumb_pipelines.setObjectName("atelierBreadcrumb")
        btn_crumb_pipelines.setCursor(Qt.PointingHandCursor)
        btn_crumb_pipelines.setStyleSheet(
            f"QPushButton#atelierBreadcrumb {{ color: {COLORS['text_dim']}; background: transparent; "
            f"border: none; font-size: 13px; padding: 0; }}"
            f"QPushButton#atelierBreadcrumb:hover {{ color: {COLORS['text_main']}; }}"
        )
        btn_crumb_pipelines.clicked.connect(self._on_back_clicked)
        hl.addWidget(btn_crumb_pipelines)

        crumb_sep = QLabel("/")
        crumb_sep.setStyleSheet(f"color: {COLORS['text_muted']}; background: transparent; border: none;")
        hl.addWidget(crumb_sep)

        self._title_lbl = QLabel("")
        self._title_lbl.setStyleSheet(
            f"color: {COLORS['text_main']}; font-size: 14px; font-weight: 700; "
            f"background: transparent; border: none;"
        )
        hl.addWidget(self._title_lbl)

        # C9 : badge « Échec à HH:MM · <étape> » — inséré/retiré par _apply_run_header(), à cet
        # index fixe (juste après le titre) ; absent en édition normale. self._header_layout/
        # self._run_badge gardés pour ça, _make_status_badge réutilise le style déjà existant de
        # PipelinesView/Historique (#badge_failed) plutôt qu'en inventer un nouveau.
        self._header_layout = hl
        self._run_badge = None
        hl.addStretch()

        # A7 : réutilise PipelineDryRunDialog (modal), orphelin depuis que PipelinesView valide
        # dans un panneau latéral — la fiche Atelier demande explicitement ce dialogue ici.
        self._btn_validate = QPushButton("Valider à blanc")
        self._btn_validate.setObjectName("secondary")
        self._btn_validate.setFixedHeight(32)
        self._btn_validate.clicked.connect(self._on_validate_pipeline)
        hl.addWidget(self._btn_validate)

        # A8 : même chemin que la liste (pipeline_actions.run_pipeline_now).
        self._btn_run = QPushButton("  Exécuter")
        self._btn_run.setFixedHeight(32)
        self._btn_run.setIcon(_icon("fa5s.play", "#000000"))
        self._btn_run.setIconSize(QSize(11, 11))
        self._btn_run.clicked.connect(self._on_run_pipeline)
        hl.addWidget(self._btn_run)

        # A9 : « Relancer tout »/« Reprendre depuis l'échec » — seulement en vue d'un run
        # reprenable (_apply_run_header() bascule la visibilité avec les deux boutons
        # ci-dessus ; sans run reprenable, Valider à blanc/Exécuter restent affichés même en
        # vue d'un run, le pipeline reste utilisable normalement).
        self._btn_relancer_tout = QPushButton("Relancer tout")
        self._btn_relancer_tout.setObjectName("secondary")
        self._btn_relancer_tout.setFixedHeight(32)
        self._btn_relancer_tout.setVisible(False)
        self._btn_relancer_tout.clicked.connect(self._on_run_pipeline)
        hl.addWidget(self._btn_relancer_tout)

        self._btn_reprendre = QPushButton("  Reprendre depuis l'échec")
        self._btn_reprendre.setFixedHeight(32)
        self._btn_reprendre.setIcon(_icon("fa5s.redo", "#000000"))
        self._btn_reprendre.setIconSize(QSize(11, 11))
        self._btn_reprendre.setVisible(False)
        self._btn_reprendre.clicked.connect(self._on_resume_pipeline)
        hl.addWidget(self._btn_reprendre)

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
                       is_new_pipeline: bool = False, run_id: int | None = None):
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
        coquille à protéger).
        `run_id` (C9) : vue en lecture seule d'un run passé — voir MainWindow.open_atelier_run()."""
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
            self._run_id = None
            self._title_lbl.setText("")
            self._apply_run_header(None)
            placeholder = QLabel("Pipeline introuvable — retournez à la liste.")
            placeholder.setAlignment(Qt.AlignCenter)
            placeholder.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 13px;")
            self._canvas_container_layout.addWidget(placeholder, stretch=1)
            return

        self._pipeline_id = pipeline_id
        self._is_new_pipeline = is_new_pipeline
        self._run_id = run_id
        self._title_lbl.setText(pipeline.name)

        self._canvas = PipelineGraphEditorWidget(
            parent=self._canvas_container, pipeline=pipeline,
            highlight_step_key=highlight_step_key, show_settings_shortcut_button=False,
            run_id=run_id,
        )
        self._canvas.run_view_exit_requested.connect(lambda: self.open_pipeline(self._pipeline_id))
        self._canvas_container_layout.addWidget(self._canvas, stretch=1)

        if is_new_pipeline:
            self._canvas.saved.connect(self._on_new_pipeline_graph_first_saved)

        if run_id is None:
            # C9 : un run passé ne se modifie pas — ni bouton Enregistrer, ni compartiment bas
            # (celui-ci réapparaît, rempli par le run consulté, uniquement via run_id).
            graph_btn_row = QHBoxLayout()
            graph_btn_row.setContentsMargins(16, 8, 16, 10)
            graph_btn_row.addStretch()
            btn_save_graph = QPushButton("Enregistrer le graphe")
            btn_save_graph.setFixedHeight(34); btn_save_graph.setMinimumWidth(150)
            btn_save_graph.clicked.connect(self._canvas.save)
            graph_btn_row.addWidget(btn_save_graph)
            self._canvas_container_layout.addLayout(graph_btn_row)
        else:
            self._canvas_container_layout.addWidget(self._canvas.timeline_panel)

        if not highlight_step_key and run_id is None:
            self._canvas.start_polling()

        from ui.step_editor.pipeline_settings_panel import PipelineSettingsPanel

        # C7/C9 : tout le contenu "normal" (paramètres + bouton Enregistrer) vit dans un seul
        # conteneur, pour pouvoir le masquer d'un coup pendant que le panneau "Ajouter" ou le
        # diagnostic d'un run est affiché (canvas.preview_panel/canvas.failure_panel prennent sa
        # place dans ce même _settings_container_layout) — jamais détruit entre les deux, juste
        # masqué (aucune perte de saisie en cours).
        self._settings_normal_container = QWidget()
        normal_layout = QVBoxLayout(self._settings_normal_container)
        normal_layout.setContentsMargins(0, 0, 0, 0)
        normal_layout.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        self._settings_panel = PipelineSettingsPanel(parent=scroll, pipeline=pipeline)
        scroll.setWidget(self._settings_panel)
        normal_layout.addWidget(scroll, stretch=1)

        settings_sep = QFrame(); settings_sep.setFrameShape(QFrame.HLine)
        settings_sep.setStyleSheet(f"background: {COLORS['border']}; max-height: 1px;")
        normal_layout.addWidget(settings_sep)

        settings_btn_row = QHBoxLayout()
        settings_btn_row.setContentsMargins(16, 10, 16, 14)
        settings_btn_row.addStretch()
        btn_save_settings = QPushButton("Enregistrer les paramètres")
        btn_save_settings.setFixedHeight(34); btn_save_settings.setMinimumWidth(150)
        btn_save_settings.clicked.connect(self._settings_panel.save)
        settings_btn_row.addWidget(btn_save_settings)
        normal_layout.addLayout(settings_btn_row)

        self._settings_container_layout.addWidget(self._settings_normal_container, stretch=1)
        self._settings_container_layout.addWidget(self._canvas.preview_panel, stretch=1)
        self._settings_container_layout.addWidget(self._canvas.failure_panel, stretch=1)
        self._canvas.preview_panel.setVisible(False)
        self._canvas.failure_panel.setVisible(False)
        self._canvas.step_library_toggled.connect(self._on_step_library_toggled)

        self._apply_run_header(run_id)
        if run_id is not None:
            self._settings_normal_container.setVisible(False)
            self._canvas.failure_panel.setVisible(True)

        self._sidebar.select_pipeline(pipeline_id)

    def _on_step_library_toggled(self, open_: bool):
        """C7 : bascule le panneau de droite entre paramètres et aperçu de type d'étape — jamais
        appelé en mode dialogue de compatibilité (step_library_toggled n'y est jamais émis)."""
        self._settings_normal_container.setVisible(not open_)
        self._canvas.preview_panel.setVisible(open_)

    def _apply_run_header(self, run_id: int | None):
        """A9 : bascule l'en-tête entre édition normale (Valider à blanc/Exécuter) et vue d'un
        run (badge + Relancer tout/Reprendre depuis l'échec — seulement si CE run précis est le
        run reprenable du pipeline ; sinon l'en-tête retombe sur Valider à blanc/Exécuter même en
        vue d'un run, le pipeline restant utilisable normalement — acceptance criterion A9)."""
        if self._run_badge is not None:
            self._header_layout.removeWidget(self._run_badge)
            self._run_badge.deleteLater()
            self._run_badge = None

        if run_id is None:
            self._btn_relancer_tout.setVisible(False)
            self._btn_reprendre.setVisible(False)
            self._btn_validate.setVisible(True)
            self._btn_run.setVisible(True)
            return

        from database import db_manager as db
        from ui.time_display import fmt_time

        run = db.get_run(run_id)
        last_resumable = db.get_last_resumable_run(self._pipeline_id)
        resumable = last_resumable is not None and last_resumable.id == run_id

        self._btn_relancer_tout.setVisible(resumable)
        self._btn_reprendre.setVisible(resumable)
        self._btn_validate.setVisible(not resumable)
        self._btn_run.setVisible(not resumable)

        if run is not None:
            is_failure = run.status == "FAILED"
            failed_row = (
                self._canvas._run_steps_by_key.get(run.failed_step_key)
                if run.failed_step_key else None
            )
            step_label = failed_row.step_label if failed_row else None
            text = f"{'Échec' if is_failure else 'Terminé'} à {fmt_time(run.finished_at or run.started_at, '%H:%M')}"
            if step_label:
                text += f" · {step_label}"
            self._run_badge = _make_status_badge(text, "badge_failed" if is_failure else "badge_success")
            self._header_layout.insertWidget(3, self._run_badge)

    def _on_resume_pipeline(self):
        if self._pipeline_id is None or self._run_id is None:
            return
        from ui.dialogs import RunProgressDialog
        RunProgressDialog(
            self._pipeline_id, self._title_lbl.text(), self, resume_from_run_id=self._run_id,
        ).exec()

    def _on_new_pipeline_graph_first_saved(self):
        """(Re)planifie une seule fois le premier enregistrement réussi d'un pipeline neuf —
        voir la docstring de `is_new_pipeline` dans open_pipeline(). Le signal `saved` du canevas
        reste connecté après ce premier appel (pas de déconnexion) : un second enregistrement du
        même graphe replanifie simplement de nouveau, ce qui est inoffensif (même garde
        défensive que _schedule_if_possible lui-même)."""
        from .pipelines_view import PipelinesView
        if self._pipeline_id is not None:
            PipelinesView._schedule_if_possible(self._pipeline_id)

    def _on_validate_pipeline(self):
        """A7 : réutilise le dialogue modal PipelineDryRunDialog, orphelin côté PipelinesView
        (qui valide désormais dans un panneau latéral) mais explicitement demandé ici par la
        fiche Atelier."""
        if self._pipeline_id is None:
            return
        from ui.dialogs import PipelineDryRunDialog
        PipelineDryRunDialog(self._pipeline_id, self._title_lbl.text(), self).exec()

    def _on_run_pipeline(self):
        """A8 : même chemin que depuis la liste des pipelines (pipeline_actions.run_pipeline_now)."""
        if self._pipeline_id is None:
            return
        run_pipeline_now(self, self._pipeline_id)

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

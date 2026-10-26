"""
DataScheduler — ui/graph_editor/graph_editor_widget.py
Contenu réutilisable de l'éditeur graphique (chantier Atelier Pipelines, écran 2) — extrait de
PipelineGraphEditorDialog (dont tout le contenu vivait jusqu'ici directement dans ce QDialog) pour
pouvoir être hébergé soit dans ce dialogue (conservé comme enveloppe de compatibilité, voir son
docstring), soit directement dans AtelierPipelinesView (vue non-modale intégrée à la fenêtre
principale). Ce widget ne construit ni l'en-tête ni la rangée Annuler/Enregistrer — c'est la
responsabilité de l'hôte (dialogue ou vue). Le polling du traçage lumineux
(start_polling()/stop_polling()) est également laissé à la charge de l'hôte : contrairement à
l'ancien QDialog, ce widget peut rester en vie indéfiniment (vue résidente dans un
QStackedWidget), donc il n'y a plus de point de destruction Qt garanti pour arrêter le QTimer.
"""

from PySide6.QtCore import QPointF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QMessageBox, QInputDialog,
)

from ui.styles import COLORS
from ui.step_editor.step_type_chooser_dialog import StepTypeChooserDialog
from ui.step_editor.common import _icon
from ui.main_window.widgets import _make_search_input
from core.pipeline import validate_pipeline_graph, topological_ranks
from core.steps import get_step_output_ports

from .graph_scene import PipelineGraphScene
from .graph_view import PipelineGraphView
from .node_item import StepNodeItem
from .edge_item import EdgeItem
from .zone_item import ZoneItem
from .node_context_menu import build_node_context_menu
from .minimap_widget import GraphMinimapWidget
from .tool_rail import EditorToolRail
from .zoom_widget import ZoomWidget
from .help_popup import GraphHelpDialog
from .node_search_overlay import NodeSearchOverlay
from .step_library_panel import StepLibraryPanel
from .step_preview_panel import StepPreviewPanel
from .run_failure_panel import RunFailurePanel
from .run_timeline_panel import RunTimelinePanel
from ui.help.content import get_topic

# C9 (Atelier-echec) : type -> (clé config du profil, fonction db_manager pour le résoudre) —
# seulement les types à un seul champ de profil simple (voir note d'impact, "PISTE" bornée).
_PISTE_PROFILE_LOOKUP = {
    "FTP_UPLOAD":    ("ftp_profile_id", "get_ftp_profile"),
    "FTP_DOWNLOAD":  ("ftp_profile_id", "get_ftp_profile"),
    "EMAIL_NOTIFY":  ("smtp_profile_id", "get_smtp_profile"),
    "SPARK_SQL":     ("edge_profile_id", "get_ssh_profile"),
    "SQOOP_EXPORT":  ("edge_profile_id", "get_ssh_profile"),
    "SQOOP_IMPORT":  ("edge_profile_id", "get_ssh_profile"),
}

_NODE_SPACING_X = 240
_ROW_HEIGHT = 120
_ROWS_PER_COLUMN = 3
# Décalage de départ (chantier chrome de l'éditeur) — dégage le rail d'icônes flottant ancré en
# haut à gauche du canevas (tool_rail.py), qui recouvrirait sinon tout nœud placé par défaut à
# 60,60 (pipeline neuf ou legacy jamais repositionné). Heuristique, pas une garantie parfaite (la
# correspondance scène↔écran dépend du zoom/défilement courants), mais dégage le cas courant à
# zoom par défaut sans changer _NODE_SPACING_X/_ROW_HEIGHT/_ROWS_PER_COLUMN (espacement entre
# nœuds, pas décalage de départ).
_START_X, _START_Y = 110, 90


class PipelineGraphEditorWidget(QWidget):
    """Toolbar + canevas (scène/vue/minimap/rail/zoom) de l'éditeur graphique d'un pipeline déjà
    existant — tout le comportement de l'ancien PipelineGraphEditorDialog, sauf l'en-tête et les
    boutons Annuler/Enregistrer (responsabilité de l'hôte). `save()` remplace l'ancien `_on_save`
    (plus de `self.accept()` — un QWidget n'a pas cette notion) et émet `saved` en cas de succès."""

    saved = Signal()
    # Émis après un enregistrement réussi depuis PipelineSettingsDialog ouvert via le raccourci
    # toolbar (_on_open_settings_dialog) — ce widget n'a pas de fenêtre à lui ; l'hôte (dialogue
    # de compatibilité, voir graph_editor_dialog.py) s'en sert pour rafraîchir SON titre.
    pipeline_renamed = Signal(str)
    # C7 : True à l'ouverture du panneau "Ajouter", False à sa fermeture — l'hôte
    # (AtelierPipelinesView) écoute pour basculer son panneau de droite entre PipelineSettingsPanel
    # et self.preview_panel. Jamais émis en mode dialogue de compatibilité (le panneau n'existe
    # pas dans ce mode, voir _on_add_step).
    step_library_toggled = Signal(bool)
    # C9 : « revenir à l'édition » cliqué dans la vue d'un run — l'hôte rouvre le même pipeline
    # sans run_id (jamais géré ici, ce widget ne sait pas comment se reconstruire lui-même).
    run_view_exit_requested = Signal()

    def __init__(self, parent=None, pipeline=None, highlight_step_key: str | None = None,
                 show_settings_shortcut_button: bool = True, run_id: int | None = None):
        super().__init__(parent)
        self._pipeline = pipeline
        self._show_settings_shortcut_button = show_settings_shortcut_button
        self._library_panel: StepLibraryPanel | None = None
        self._preview_panel: StepPreviewPanel | None = None
        # C9 (Atelier-echec) : vue en lecture seule d'un run passé. _run_steps reste {} tant que
        # _apply_run_view() n'a rien trouvé (aucune ligne B1 — ancien worker, voir note d'impact)
        # : le reste du code se comporte alors exactement comme avant ce lot (highlight_step_key
        # seul, un unique nœud rouge).
        self._run_id = run_id
        self._run_steps_by_key: dict[str, object] = {}
        self._failure_panel = None
        self._timeline_panel = None
        # Instantané des positions juste avant le dernier "Ranger automatiquement" (chantier UX
        # éditeur, Lot 1) — aucun QUndoStack n'existe nulle part dans cette app, annulation à un
        # seul niveau volontairement minimale plutôt qu'une abstraction prématurée. Écrase le
        # précédent à chaque nouveau rangement, effacé par _on_undo_layout().
        self._layout_snapshot: dict[str, QPointF] | None = None
        # Résultats de la recherche textuelle courante (chantier UX éditeur, Lot 2, B3) —
        # reconstruits à chaque frappe dans _on_search_changed(), cyclés par _on_search_jump().
        self._search_matches: list[StepNodeItem] = []
        self._search_match_idx: int = -1
        # Traçage lumineux (chantier identité visuelle) — self._executing_timer n'existe comme
        # attribut QUE si start_polling() a été appelé (même convention que l'ancien QDialog, où
        # cet attribut n'était tout simplement jamais créé dans le cas highlight_step_key — voir
        # tests/test_graph_editor_dialog.py::test_highlight_step_key_skips_the_live_polling_timer)
        # — jamais automatiquement ici : l'hôte (dialogue ou AtelierPipelinesView) décide quand
        # le polling doit tourner, et doit pouvoir l'arrêter explicitement puisque ce widget peut
        # survivre indéfiniment (pas de destruction Qt garantie).
        self._load_profiles()

        self._build_ui()
        self._load_graph()

        applied_run_view = False
        if run_id is not None:
            applied_run_view = self._apply_run_view(run_id)
        if not applied_run_view and highlight_step_key:
            # Lien "Voir dans le graphe" depuis une ligne d'historique en échec (chantier UX
            # éditeur, Lot 1, B1) — surlignage ponctuel à l'ouverture. Repli de _apply_run_view()
            # quand pipeline_run_steps est vide pour ce run (ancien worker qui n'écrit pas
            # encore cette table — acceptance criterion B1 : Main et Atelier-echec s'affichent
            # sans erreur ni place vide).
            self._highlight_failed_step(highlight_step_key)

    # ── Polling d'exécution (traçage lumineux) ─

    def start_polling(self):
        """Démarre le sondage périodique des étapes en cours d'exécution. Idempotent (un second
        appel sans stop_polling() entre les deux ne crée pas un second QTimer)."""
        if getattr(self, "_executing_timer", None) is not None:
            return
        from database import db_manager as db
        self._executing_timer = QTimer(self)
        self._executing_timer.setInterval(db.get_app_settings().trace_glow_refresh_s * 1000)
        self._executing_timer.timeout.connect(self._poll_executing_step)
        self._executing_timer.start()

    def stop_polling(self):
        """Arrête le sondage — à appeler explicitement par l'hôte avant de masquer/remplacer ce
        widget (voir docstring du module : plus de destruction Qt garantie à ce moment-là)."""
        timer = getattr(self, "_executing_timer", None)
        if timer is not None:
            timer.stop()
            self._executing_timer = None

    def _highlight_failed_step(self, step_key: str) -> None:
        node = self._scene.nodes.get(step_key)
        if not node:
            return
        node.set_failed(True)
        for e in self._scene.edges:
            if e.to_node is node:
                e.set_failed(True)
        self._view.centerOn(node)

    # ── C9 (Atelier-echec) : vue en lecture seule d'un run passé ──

    def _apply_run_view(self, run_id: int) -> bool:
        """Retourne False (et ne touche à rien) si pipeline_run_steps est vide pour ce run —
        l'appelant retombe alors sur l'ancien comportement highlight_step_key (voir __init__)."""
        from database import db_manager as db
        from .run_status import (
            node_status_text, node_card_state, edge_run_state, summarize_run_steps,
            parse_attempts, what_happened_next,
        )

        run_steps = db.get_run_steps(run_id)
        if not run_steps:
            return False

        self._run_steps_by_key = {r.step_key: r for r in run_steps if r.step_key}
        steps_by_key = self._run_steps_by_key

        error_incoming_keys = {
            e.to_node.step_key for e in self._scene.edges if e.from_port == "error"
        }

        failed_node = None
        for key, node in self._scene.nodes.items():
            row = steps_by_key.get(key)
            via_error = key in error_incoming_keys and row is not None and row.status == "SUCCESS"
            result = node_status_text(row, via_error)
            text, color_key = result if result else (None, None)
            node.set_run_status(text, color_key, node_card_state(row, via_error))
            node.set_movable(False)
            if row is not None and row.status == "FAILED":
                node.set_failed(True)
                if failed_node is None:
                    failed_node = node

        for edge in self._scene.edges:
            from_row = steps_by_key.get(edge.from_node.step_key)
            to_row = steps_by_key.get(edge.to_node.step_key)
            edge.set_run_state(edge_run_state(edge.from_port, from_row, to_row))
            if to_row is not None and to_row.status == "FAILED":
                edge.set_failed(True)

        self._rail.setEnabled(False)

        run = db.get_run(run_id)
        failed_step_key = (run.failed_step_key if run else None) or (
            failed_node.step_key if failed_node else None
        )
        target_node = self._scene.nodes.get(failed_step_key) if failed_step_key else None
        if target_node is None and self._scene.nodes:
            target_node = next(iter(self._scene.nodes.values()))
        if target_node is not None:
            self._view.centerOn(target_node)

        self._build_run_view_label(run)
        if failed_step_key:
            self._build_failure_panel(run, failed_step_key, steps_by_key)
        self._build_timeline_panel(run, run_steps)
        return True

    def _build_run_view_label(self, run) -> None:
        """« Vue de l'exécution du … · revenir à l'édition » — même emplacement que l'aide de
        glisser-déposer en mode édition (A10), jamais les deux en même temps (lecture seule)."""
        from ui.time_display import fmt_datetime

        when = f"du {fmt_datetime(run.started_at)} " if run else ""
        text = (
            f"Vue de l'exécution {when}· "
            f"<a href='#' style='color:{COLORS['accent_pale']}; text-decoration:none;'>revenir à l'édition</a>"
        )
        self._run_view_label = QLabel(text, self._view.viewport())
        self._run_view_label.setTextFormat(Qt.RichText)
        self._run_view_label.setStyleSheet(
            f"color: {COLORS['text_dim']}; font-size: 12px; background: transparent; border: none;"
        )
        self._run_view_label.linkActivated.connect(lambda _: self.run_view_exit_requested.emit())
        self._run_view_label.move(64, 12)
        self._run_view_label.show()

    def _resolve_piste(self, step_type: str, config: dict) -> str | None:
        from database import db_manager as db

        lookup = _PISTE_PROFILE_LOOKUP.get(step_type)
        if not lookup:
            return None
        config_key, getter_name = lookup
        profile_id = (config or {}).get(config_key)
        if not profile_id:
            return None
        profile = getattr(db, getter_name)(profile_id)
        if profile is None or profile.last_tested_at is not None:
            return None
        return f"La connexion {profile.name} n'a jamais été testée."

    def _build_failure_panel(self, run, failed_step_key: str, steps_by_key: dict) -> None:
        from datetime import datetime
        from ui.step_editor import STEP_META
        from ui.time_display import fmt_time
        from .run_status import parse_attempts, what_happened_next

        node = self._scene.nodes.get(failed_step_key)
        failed_row = steps_by_key.get(failed_step_key)
        if node is None or failed_row is None:
            return
        meta = STEP_META.get(node.step.get("step_type", ""), {"label": "", "category": ""})
        label = node.step.get("label") or meta.get("label", "")

        attempts = [
            (fmt_time(datetime.fromisoformat(a["started_at"])), "échouée")
            for a in parse_attempts(failed_row) if a.get("started_at")
        ]

        successors = [
            (e.to_node.step_key, e.from_port)
            for e in self._scene.edges if e.from_node.step_key == failed_step_key
        ]
        what_happened = what_happened_next(failed_step_key, successors, steps_by_key)

        piste = self._resolve_piste(node.step.get("step_type", ""), node.step.get("config") or {})

        resume_hint = None
        if run and run.resumable_state_json:
            success_count = sum(1 for r in steps_by_key.values() if r.status == "SUCCESS")
            resume_hint = (
                f"Rejoue {label} puis la suite. Les {success_count} étapes réussies ne sont pas "
                f"rejouées : leurs fichiers sont réutilisés."
            )

        self.failure_panel.set_data(
            eyebrow=f"ÉCHEC · {meta.get('category', '').upper()}",
            title=label,
            error_text=(failed_row.error_message or run.error_message or "").strip() or "Erreur inconnue.",
            attempts=attempts,
            what_happened=what_happened,
            piste=piste,
            resume_hint=resume_hint,
        )

    def _build_timeline_panel(self, run, run_steps) -> None:
        from datetime import datetime
        from ui.step_editor import STEP_META
        from ui.time_display import fmt_datetime
        from .run_status import format_step_duration, parse_attempts

        total_seconds = (run.duration_seconds if run else None) or 1.0
        rows = []
        for step_row in run_steps:
            if step_row.status not in ("SUCCESS", "FAILED"):
                continue
            node = self._scene.nodes.get(step_row.step_key)
            if node is None or node.is_routing_node:
                continue
            meta = STEP_META.get(node.step.get("step_type", ""), {"color": COLORS["text_dim"]})
            label = node.step.get("label") or meta.get("label", "")

            attempts = parse_attempts(step_row)
            bars = []
            connectors = []
            if attempts and step_row.status == "FAILED" and run and run.started_at:
                starts = [datetime.fromisoformat(a["started_at"]) for a in attempts if a.get("started_at")]
                ends = [datetime.fromisoformat(a["finished_at"]) for a in attempts if a.get("finished_at")]
                for s, e in zip(starts, ends):
                    start_pct = max(0.0, (s - run.started_at).total_seconds() / total_seconds)
                    width_pct = max(0.004, (e - s).total_seconds() / total_seconds)
                    bars.append((start_pct, width_pct, COLORS["danger"]))
                for i in range(len(ends) - 1):
                    gap_start = (ends[i] - run.started_at).total_seconds() / total_seconds
                    gap_end = (starts[i + 1] - run.started_at).total_seconds() / total_seconds
                    connectors.append((gap_start, max(0.0, gap_end - gap_start)))
                duration_text = f"{len(attempts)} × refus"
                duration_color = COLORS["danger"]
                label_color = COLORS["danger"]
            elif run and run.started_at and step_row.started_at and step_row.finished_at:
                start_pct = max(0.0, (step_row.started_at - run.started_at).total_seconds() / total_seconds)
                width_pct = max(0.004, (step_row.finished_at - step_row.started_at).total_seconds() / total_seconds)
                via_error = any(
                    e.from_port == "error" and e.to_node is node for e in self._scene.edges
                )
                bars.append((start_pct, width_pct, COLORS["warning"] if via_error else meta["color"]))
                duration_text = format_step_duration((step_row.finished_at - step_row.started_at).total_seconds())
                duration_color = COLORS["text_dim"]
                label_color = COLORS["warning"] if via_error else COLORS["text_main"]
            else:
                continue

            rows.append({
                "label": label, "label_color": label_color, "bars": bars, "connectors": connectors,
                "duration_text": duration_text, "duration_color": duration_color,
            })

        axis_labels = [format_step_duration(total_seconds * f) for f in (0, 0.25, 0.5, 0.75, 1.0)]
        status_color = COLORS["danger"] if (run and run.status == "FAILED") else COLORS["success"]
        status_word = "Échec" if (run and run.status == "FAILED") else "Réussie"
        status_text = f"{status_word} · {fmt_datetime(run.started_at)} · {format_step_duration(total_seconds)}" if run else ""

        has_retries = any(r["connectors"] for r in rows)
        self.timeline_panel.set_data(
            status_color=status_color, status_text=status_text,
            time_axis_labels=axis_labels, rows=rows,
            journal_text=(run.log_text if run else "") or "",
            footnote=("Les traits fins entre les tentatives sont les délais d'attente avant chaque réessai."
                      if has_retries else None),
        )


    def _poll_executing_step(self):
        if not self._pipeline:
            return
        from database import db_manager as db
        # Priorité au suivi multi-étapes (chantier parallélisme intra-pipeline) — non vide
        # uniquement pour un run ayant réellement emprunté le moteur concurrent
        # (PipelineRun.active_steps_json) ; sinon repli sur le suivi historique à une seule
        # étape (get_running_step_keys()), utilisé par tout run linéaire/graphe séquentiel,
        # inchangé.
        multi = db.get_running_step_keys_multi().get(self._pipeline.id)
        if multi:
            self._scene.set_executing_step_keys(multi)
            return
        step_key = db.get_running_step_keys().get(self._pipeline.id)
        self._scene.set_executing_step_keys({step_key} if step_key else set())

    # ── Données ──────────────────────────────

    def _load_profiles(self):
        from database import db_manager as db
        self._oracle_profiles    = db.get_oracle_profiles()
        self._ftp_profiles       = db.get_ftp_profiles()
        self._sql_queries        = db.get_sql_queries()
        self._smtp_profiles      = db.get_smtp_profiles()
        self._db_profiles        = db.list_all_db_profiles()
        # Chantier relooking des nœuds — nécessaires pour résoudre edge_profile_id/
        # kerberos_profile_id/elevation_profile_id (SPARK_SQL/SQOOP_*) sans requête DB depuis le
        # rendu d'un nœud ; absentes ici jusqu'à ce chantier (seuls leurs combos de dialogue les
        # chargeaient à la demande).
        self._ssh_profiles       = db.get_ssh_profiles()
        self._kerberos_profiles  = db.get_kerberos_profiles()
        self._elevation_profiles = db.get_elevation_profiles()
        self._profile_names = self._build_profile_names()

    def _build_profile_names(self) -> dict:
        """Dict de résolution ID -> nom pour le contenu déplié des nœuds (node_facts.py) —
        construit UNE FOIS ici à partir des listes déjà chargées, jamais recalculé depuis le
        rendu d'un nœud. "db" est keyé par (db_type, id) : list_all_db_profiles() fusionne
        OracleProfile et DatabaseProfile, dont les id PEUVENT se chevaucher entre les deux
        tables — une simple clé "id" résoudrait parfois le mauvais profil."""
        return {
            "db":        {(p["db_type"], p["id"]): p["name"] for p in self._db_profiles},
            "oracle":    {p.id: p.name for p in self._oracle_profiles},
            "ftp":       {p.id: p.name for p in self._ftp_profiles},
            # Moteur affiché au surtitre de carte (A1, node_facts.py::engine_label) — le
            # protocole n'est pas dans la config de l'étape (seul ftp_profile_id l'est).
            "ftp_protocol": {p.id: p.protocol.value for p in self._ftp_profiles},
            "smtp":      {p.id: p.name for p in self._smtp_profiles},
            "ssh":       {p.id: p.name for p in self._ssh_profiles},
            "kerberos":  {p.id: p.name for p in self._kerberos_profiles},
            "elevation": {p.id: p.name for p in self._elevation_profiles},
            "sql_query": {q.id: q.name for q in self._sql_queries},
        }

    # ── Construction UI ──────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # A10 (lot A-Atelier-main) : seul `PipelineGraphEditorDialog` (enveloppe de compatibilité
        # sans panneau de paramètres intégré) garde encore une barre de contexte classique, pour
        # son bouton "Paramètres du pipeline" — la vue Atelier réelle (show_settings_shortcut_
        # button=False) n'en a plus besoin : recherche et aide de glisser-déposer deviennent des
        # éléments flottants du canevas, voir plus bas.
        if self._show_settings_shortcut_button:
            toolbar = QHBoxLayout()
            toolbar.setContentsMargins(16, 8, 16, 8)
            toolbar.setSpacing(8)

            hint = QLabel(
                "Glisser depuis un point de sortie vers un point d'entrée pour connecter deux "
                "étapes."
            )
            hint.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 11px; font-style: italic;")
            toolbar.addWidget(hint)
            toolbar.addStretch(1)

            self.inp_search = _make_search_input("Rechercher un nœud…")
            self.inp_search.setToolTip(
                "Filtre les étapes par type ou libellé. Entrée pour centrer la vue sur le résultat "
                "suivant."
            )
            self.inp_search.textChanged.connect(self._on_search_changed)
            self.inp_search.returnPressed.connect(self._on_search_jump)
            toolbar.addWidget(self.inp_search)

            btn_settings = QPushButton("  Paramètres du pipeline")
            btn_settings.setObjectName("secondary")
            btn_settings.setFixedHeight(32)
            btn_settings.setIcon(_icon("fa5s.cog", COLORS["text_main"]))
            btn_settings.setIconSize(QSize(14, 14))
            btn_settings.setToolTip(
                "Nom, description, planification, déclenchement conditionnel et actif/inactif — "
                "n'affecte jamais les étapes ni les connexions de ce graphe."
            )
            btn_settings.clicked.connect(self._on_open_settings_dialog)
            toolbar.addWidget(btn_settings)

            root.addLayout(toolbar)

        self._scene = PipelineGraphScene()
        self._scene.node_double_clicked.connect(self._on_node_double_clicked)
        self._scene.zone_double_clicked.connect(self._on_zone_double_clicked)
        self._scene.node_context_menu_requested.connect(self._on_node_context_menu)
        self._view = PipelineGraphView(self._scene)
        self._view._owner = self   # C7 : voir PipelineGraphView.dropEvent
        root.addWidget(self._view, stretch=1)

        # Raccourci clavier — même idiome que Ctrl+N (pipelines_view.py)/F5 (window.py). Même
        # point d'appel que le bouton du rail et le menu contextuel — _on_duplicate_selected()
        # reste le seul endroit où duplicate_node() est réellement invoqué.
        QShortcut(QKeySequence("Ctrl+D"), self, activated=self._on_duplicate_selected)

        # Mini-carte de navigation (chantier UX éditeur, Lot 2, A3) — parentée au viewport, pas
        # à la vue elle-même, pour éviter tout décalage de coordonnées dû au cadre par défaut de
        # QGraphicsView (jamais retiré ici). Visible par défaut.
        self._minimap = GraphMinimapWidget(self._scene, self._view, parent=self._view.viewport())
        self._view._minimap = self._minimap
        self._minimap.reposition()
        self._scene.changed.connect(lambda *_: self._minimap.request_repaint())
        self._view.horizontalScrollBar().valueChanged.connect(
            lambda *_: self._minimap.request_repaint())
        self._view.verticalScrollBar().valueChanged.connect(
            lambda *_: self._minimap.request_repaint())

        # Rail d'icônes flottant (chantier chrome de l'éditeur) — mêmes parenté/mécanique que la
        # mini-carte ci-dessus, ancré près du bord opposé (haut-gauche) du canevas.
        self._rail = EditorToolRail(self, parent=self._view.viewport())
        self._view._rail = self._rail
        self._rail.reposition()
        self._btn_undo_layout = self._rail.btn_undo_layout
        self._rail.refresh_minimap_button_style(not self._minimap.isHidden())

        # Widget de zoom flottant (chantier identité visuelle) — coin bas-gauche, opposé à la
        # mini-carte (bas-droite).
        self._zoom_widget = ZoomWidget(self._view, parent=self._view.viewport())
        self._view._zoom_widget = self._zoom_widget
        self._zoom_widget.reposition()

        # A10 (lot A-Atelier-main) : recherche de nœud en surimpression, haut-droite du canevas —
        # uniquement pour la vue Atelier réelle (le dialogue de compatibilité garde sa barre
        # classique construite plus haut, avec son propre self.inp_search).
        if not self._show_settings_shortcut_button:
            self._drag_hint = QLabel(
                "Tirer d'un port de sortie vers un port d'entrée pour relier deux nœuds",
                self._view.viewport(),
            )
            self._drag_hint.setStyleSheet(
                f"color: {COLORS['text_muted']}; font-size: 11px; font-style: italic; "
                f"background: transparent;"
            )
            self._drag_hint.move(64, 12)
            self._drag_hint.show()

            self._search_overlay = NodeSearchOverlay(parent=self._view.viewport())
            self.inp_search = self._search_overlay.inp_search
            self.inp_search.setToolTip(
                "Filtre les étapes par type ou libellé. Entrée pour centrer la vue sur le "
                "résultat suivant."
            )
            self.inp_search.textChanged.connect(self._on_search_changed)
            self.inp_search.returnPressed.connect(self._on_search_jump)
            self._view._search_overlay = self._search_overlay
            self._search_overlay.reposition()

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
                "retry_interval_s": s.retry_interval_s or 5,
                "run_always":  bool(s.run_always),
                "timeout_s":   s.timeout_s or 0,
            }
            if all_at_origin:
                col, row = divmod(i, _ROWS_PER_COLUMN)
                pos = QPointF(_START_X + col * _NODE_SPACING_X, _START_Y + row * _ROW_HEIGHT)
            else:
                pos = QPointF(s.pos_x, s.pos_y)
            node = self._scene.add_node(step, pos)
            if node is not None:   # add_node() renvoie None si _step_key manque (jamais censé
                node.set_profile_names(self._profile_names)   # arriver sur un pipeline sauvegardé)

        for e in edges:
            self._scene.add_edge(e.from_step_key, e.from_port, e.to_step_key)

        for z in db.get_zones(self._pipeline.id):
            self._scene.add_zone(z.name, QPointF(z.pos_x, z.pos_y), z.width, z.height)

    # ── Ajout / édition / suppression ─────────

    def _next_new_node_pos(self) -> QPointF:
        if not self._scene.nodes:
            return QPointF(_START_X, _START_Y)
        max_x = max(n.pos().x() for n in self._scene.nodes.values())
        return QPointF(max_x + _NODE_SPACING_X, _START_Y)

    # ── Rangement automatique (chantier UX éditeur, Lot 1) ────

    def _compute_auto_layout_positions(self, node_subset=None) -> dict | None:
        """Calcule une nouvelle position pour chaque nœud du canevas (ou du sous-ensemble
        `node_subset`) : colonne = rang topologique, ligne = ordre par barycentre des
        prédécesseurs déjà positionnés au sein du même rang. Retourne None si le graphe contient
        un cycle (rangement impossible)."""
        _, edges, _ = self._collect_graph()
        ranks = topological_ranks(self._scene.nodes.keys(), edges)
        if ranks is None:
            return None

        incoming: dict[str, list[str]] = {k: [] for k in self._scene.nodes}
        for e in edges:
            frm, to = e["from_step_key"], e["to_step_key"]
            if to in incoming:
                incoming[to].append(frm)

        keys = set(self._scene.nodes) if node_subset is None else set(node_subset) & set(self._scene.nodes)
        by_rank: dict[int, list[str]] = {}
        for key in keys:
            by_rank.setdefault(ranks.get(key, 0), []).append(key)

        placed_y: dict[str, float] = {k: n.pos().y() for k, n in self._scene.nodes.items()}

        positions: dict[str, QPointF] = {}
        for rank in sorted(by_rank):
            rank_keys = by_rank[rank]
            if rank == 0:
                rank_keys.sort(key=lambda k: self._scene.nodes[k].pos().y())
            else:
                def _barycenter(k, _incoming=incoming, _placed_y=placed_y):
                    preds_y = [_placed_y[p] for p in _incoming.get(k, []) if p in _placed_y]
                    return sum(preds_y) / len(preds_y) if preds_y else _placed_y.get(k, 0.0)
                rank_keys.sort(key=_barycenter)
            for i, key in enumerate(rank_keys):
                x = _START_X + rank * _NODE_SPACING_X
                y = _START_Y + i * _ROW_HEIGHT
                positions[key] = QPointF(x, y)
                placed_y[key] = y
        return positions

    def _on_auto_layout(self):
        positions = self._compute_auto_layout_positions()
        if positions is None:
            QMessageBox.warning(
                self, "Rangement impossible",
                "Le graphe contient un cycle — impossible de déterminer un ordre de rangement.",
            )
            return
        self._layout_snapshot = {k: n.pos() for k, n in self._scene.nodes.items()}
        for key, pos in positions.items():
            self._scene.nodes[key].setPos(pos)
        self._btn_undo_layout.setEnabled(True)

    def _on_undo_layout(self):
        if not self._layout_snapshot:
            return
        for key, pos in self._layout_snapshot.items():
            node = self._scene.nodes.get(key)
            if node:
                node.setPos(pos)
        self._layout_snapshot = None
        self._btn_undo_layout.setEnabled(False)

    def _on_arrange_selection(self):
        """Version ciblée de _on_auto_layout (chantier UX éditeur, Lot 3, A6) : ne repositionne
        que les étapes actuellement sélectionnées. Réutilise le même snapshot/bouton
        d'annulation que le rangement complet."""
        keys = {n.step_key for n in self._scene.selectedItems() if isinstance(n, StepNodeItem)}
        if not keys:
            return
        positions = self._compute_auto_layout_positions(node_subset=keys)
        if positions is None:
            QMessageBox.warning(
                self, "Rangement impossible",
                "Le graphe contient un cycle — impossible de déterminer un ordre de rangement.",
            )
            return
        self._layout_snapshot = {k: n.pos() for k, n in self._scene.nodes.items()}
        for key, pos in positions.items():
            self._scene.nodes[key].setPos(pos)
        self._btn_undo_layout.setEnabled(True)

    # ── Zones de regroupement visuel (chantier UX éditeur, Lot 2, A4) ────

    def _on_add_zone(self):
        pos = self._view.mapToScene(self._view.viewport().rect().center())
        self._scene.add_zone("Nouvelle zone", pos)

    def _on_zone_double_clicked(self, zone: ZoneItem):
        new_name, ok = QInputDialog.getText(
            self, "Renommer la zone", "Nom :", text=zone.name,
        )
        new_name = new_name.strip()
        if ok and new_name:
            zone.name = new_name
            zone.update()

    # ── Mini-carte (chantier UX éditeur, Lot 2, A3) ────

    def _on_toggle_minimap(self):
        # isHidden() plutôt que isVisible() : ce dernier dépend aussi de la visibilité des
        # parents (donc toujours False tant que le widget n'a jamais été réellement affiché),
        # alors qu'isHidden() ne reflète que l'état explicitement demandé sur ce widget.
        self._minimap.setVisible(self._minimap.isHidden())
        self._rail.refresh_minimap_button_style(not self._minimap.isHidden())

    def _on_toggle_all_expanded(self):
        """"Tout déplier/replier" (chantier relooking des nœuds) — recalcule la cible à CHAQUE
        clic à partir de l'état réel des nœuds (pas d'état supplémentaire à maintenir sur ce
        widget) : au moins un nœud replié -> déplie tout ; sinon -> replie tout. Robuste même
        après des bascules individuelles (chevron par chevron) entre deux clics du bouton."""
        nodes = list(self._scene.nodes.values())
        if not nodes:
            return
        target = any(not n.is_expanded for n in nodes)
        for n in nodes:
            n.set_expanded(target)

    def _on_show_help(self):
        """Aide contextuelle (chantier UX éditeur, Lot 3, C2) — réutilise le même rendu Markdown
        que l'onglet "Aide" global, seule la rubrique "graph-editor" est affichée ici."""
        topic = get_topic("graph-editor")
        if topic is None:
            return
        GraphHelpDialog(topic, parent=self).exec()

    # ── Recherche textuelle (chantier UX éditeur, Lot 2, B3) ────

    def _on_search_changed(self, text: str):
        needle = text.strip().lower()
        matches = []
        for node in self._scene.nodes.values():
            matched = bool(needle) and needle in node.search_text()
            node.set_search_hit(matched)
            if matched:
                matches.append(node)
            protected = node.is_executing or node.is_failed
            node.setOpacity(1.0 if (not needle or matched or protected) else 0.35)

        for edge in self._scene.edges:
            protected = edge.from_node.is_executing or edge.from_node.is_failed \
                or edge.to_node.is_executing or edge.to_node.is_failed
            relevant = edge.from_node.is_search_hit or edge.to_node.is_search_hit
            edge.setOpacity(1.0 if (not needle or relevant or protected) else 0.35)

        self._search_matches = matches
        self._search_match_idx = -1

    def _on_search_jump(self):
        if not self._search_matches:
            return
        self._search_match_idx = (self._search_match_idx + 1) % len(self._search_matches)
        self._view.centerOn(self._search_matches[self._search_match_idx])

    def _incoming_prior_steps(self, node: StepNodeItem) -> list:
        """Étapes amont réellement connectées à `node` par une arête — ce que le sélecteur
        "Source"/bouton "+ Artefact" doivent voir pour lister les producteurs par nom."""
        return [e.from_node.step for e in self._scene.edges if e.to_node is node]

    def _on_add_step(self):
        """Mode dialogue de compatibilité : flux modal inchangé (StepTypeChooserDialog puis
        dialogue de config). Mode Atelier réel (C7) : ouvre le panneau "Ajouter" à la place —
        même bascule déjà établie pour A10 (recherche de nœud)."""
        if self._show_settings_shortcut_button:
            from ui.step_editor import _open_config_dialog
            from database import db_manager as db

            dlg = StepTypeChooserDialog(self, include_routing_nodes=True)
            if not dlg.exec():
                return
            # dlg.chosen_config (chantier bibliothèque d'étapes réutilisables) : {} pour un choix
            # de type normal, préremplie si le choix vient de "Mes modèles" — même chemin que
            # _on_node_double_clicked() ci-dessous (config déjà non vide pour une étape
            # existante), aucune modification des dialogues individuels n'est nécessaire.
            config_dlg = _open_config_dialog(
                dlg.chosen_type, dlg.chosen_config, self,
                self._oracle_profiles, self._ftp_profiles, self._sql_queries,
                self._smtp_profiles, self._db_profiles,
                prior_steps=[n.step for n in self._scene.nodes.values()],
                pipeline_variable_names=[v.name for v in db.get_pipeline_variables(self._pipeline.id)],
            )
            if config_dlg and config_dlg.exec():
                step = config_dlg.result_step()
                node = self._scene.add_node(step, self._next_new_node_pos())
                if node is not None:
                    node.set_profile_names(self._profile_names)
            return

        self.open_step_library()

    # ── C7 : panneau "Ajouter" (bibliothèque + aperçu) ────

    @property
    def preview_panel(self) -> StepPreviewPanel:
        """Construit à la demande — l'hôte (AtelierPipelinesView) le réclame une seule fois pour
        le reparenter dans son propre conteneur de droite (jamais placé dans le layout de ce
        widget lui-même, voir docstring du module de PipelineSettingsPanel pour le même
        principe)."""
        if self._preview_panel is None:
            self._preview_panel = StepPreviewPanel()
            self._preview_panel.insert_requested.connect(self._on_library_insert_requested)
        return self._preview_panel

    @property
    def failure_panel(self) -> RunFailurePanel:
        """C9 : même principe que preview_panel — l'hôte le reparente dans son propre conteneur
        de droite quand une vue d'exécution est ouverte."""
        if self._failure_panel is None:
            self._failure_panel = RunFailurePanel()
        return self._failure_panel

    @property
    def timeline_panel(self) -> RunTimelinePanel:
        """C9 : même principe — l'hôte le place sous le canevas (compartiment bas) quand une vue
        d'exécution est ouverte."""
        if self._timeline_panel is None:
            self._timeline_panel = RunTimelinePanel()
        return self._timeline_panel

    def open_step_library(self):
        if self._library_panel is None:
            self._library_panel = StepLibraryPanel(parent=self._view.viewport())
            self._library_panel.selection_changed.connect(self._on_library_selection_changed)
            self._library_panel.close_requested.connect(self.close_step_library)
            self._library_panel.insert_requested.connect(self._on_library_insert_requested)
            self._view._library_panel = self._library_panel
        _ = self.preview_panel   # construit si besoin, avant que l'hôte n'aille le chercher
        self._library_panel.reposition()
        self._library_panel.show()
        self._library_panel.raise_()
        self._library_panel.inp_search.setFocus()
        self.step_library_toggled.emit(True)

    def close_step_library(self):
        if self._library_panel is not None:
            self._library_panel.hide()
        self.step_library_toggled.emit(False)

    def _on_library_selection_changed(self, step_type: str, config: dict):
        self.preview_panel.set_step(step_type, config)

    def _on_library_insert_requested(self):
        panel = self._library_panel
        if panel is None or panel._selected_type is None:
            return
        self._perform_insertion(panel._selected_type, panel._selected_config)

    def handle_library_drop(self, step_type: str, config: dict, scene_pos: QPointF, hovered_edge):
        """Appelé par PipelineGraphView.dropEvent — un dépôt sur une arête greffe dedans (même
        logique que le bouton/Entrée sur une arête sélectionnée), un dépôt sur du vide ajoute un
        nœud flottant exactement à la position du dépôt (pas _next_new_node_pos, qui n'a de sens
        que pour un ajout sans position explicite de l'utilisateur)."""
        target = ("splice", hovered_edge) if hovered_edge is not None else ("floating_at", scene_pos)
        self._perform_insertion(step_type, config, target_override=target)

    def _resolve_insertion_target(self):
        """Point de greffe (C7, voir note d'impact) : une arête sélectionnée seule prime, sinon
        un nœud sélectionné seul, sinon flottant — jamais d'ambiguïté avec plusieurs éléments
        sélectionnés à la fois (repli sur flottant, le plus sûr)."""
        selected = self._scene.selectedItems()
        edges = [i for i in selected if isinstance(i, EdgeItem)]
        if len(edges) == 1:
            return ("splice", edges[0])
        nodes = [i for i in selected if isinstance(i, StepNodeItem)]
        if len(nodes) == 1:
            return ("after", nodes[0])
        return ("floating", None)

    @staticmethod
    def _first_non_error_port(step_type: str) -> str:
        ports = [p for p in get_step_output_ports(step_type) if p != "error"]
        return ports[0] if ports else "output_file"

    def _perform_insertion(self, step_type: str, config: dict, target_override=None):
        from ui.step_editor import _open_config_dialog
        from database import db_manager as db

        kind, ref = target_override if target_override is not None else self._resolve_insertion_target()

        config_dlg = _open_config_dialog(
            step_type, config, self,
            self._oracle_profiles, self._ftp_profiles, self._sql_queries,
            self._smtp_profiles, self._db_profiles,
            prior_steps=[n.step for n in self._scene.nodes.values()],
            pipeline_variable_names=[v.name for v in db.get_pipeline_variables(self._pipeline.id)],
        )
        if not (config_dlg and config_dlg.exec()):
            return
        step = config_dlg.result_step()

        if kind == "splice":
            edge = ref
            p1, p2 = edge.from_node.pos(), edge.to_node.pos()
            pos = QPointF((p1.x() + p2.x()) / 2, (p1.y() + p2.y()) / 2)
            node = self._scene.add_node(step, pos)
            if node is None:
                return
            node.set_profile_names(self._profile_names)
            from_key, from_port, to_key = edge.from_node.step_key, edge.from_port, edge.to_node.step_key
            self._scene.remove_edge(edge)
            self._scene.add_edge(from_key, from_port, node.step_key)
            self._scene.add_edge(node.step_key, self._first_non_error_port(step_type), to_key)
        elif kind == "after":
            prev = ref
            pos = QPointF(prev.pos().x() + _NODE_SPACING_X, prev.pos().y())
            node = self._scene.add_node(step, pos)
            if node is None:
                return
            node.set_profile_names(self._profile_names)
            prev_type = prev.step.get("step_type", "")
            self._scene.add_edge(prev.step_key, self._first_non_error_port(prev_type), node.step_key)
        elif kind == "floating_at":
            node = self._scene.add_node(step, ref)   # ref = QPointF (position du dépôt)
            if node is not None:
                node.set_profile_names(self._profile_names)
        else:
            node = self._scene.add_node(step, self._next_new_node_pos())
            if node is not None:
                node.set_profile_names(self._profile_names)

        self.close_step_library()

    def _on_node_double_clicked(self, node: StepNodeItem):
        from ui.step_editor import _open_config_dialog
        from database import db_manager as db

        step = node.step
        config_dlg = _open_config_dialog(
            step["step_type"], step.get("config", {}), self,
            self._oracle_profiles, self._ftp_profiles, self._sql_queries,
            self._smtp_profiles, self._db_profiles,
            label=step.get("label", ""),
            retry_count=step.get("retry_count", 0),
            retry_interval_s=step.get("retry_interval_s", 5),
            run_always=step.get("run_always", False),
            timeout_s=step.get("timeout_s", 0),
            prior_steps=self._incoming_prior_steps(node),
            pipeline_variable_names=[v.name for v in db.get_pipeline_variables(self._pipeline.id)],
        )
        if config_dlg and config_dlg.exec():
            # prepareGeometryChange() avant de réassigner step : le nombre de faits affichés
            # (si ce nœud est déplié) peut changer avec la nouvelle config (chantier relooking
            # des nœuds) — sans danger de l'appeler même quand la géométrie ne change pas
            # réellement (nœud replié, ou même nombre de faits).
            node.prepareGeometryChange()
            node.step = config_dlg.result_step()
            node.set_profile_names(self._profile_names)   # update() déjà inclus

    def _on_delete_selected(self):
        for item in list(self._scene.selectedItems()):
            if isinstance(item, StepNodeItem):
                self._scene.remove_node(item)
            elif isinstance(item, EdgeItem):
                self._scene.remove_edge(item)
            elif isinstance(item, ZoneItem):
                self._scene.remove_zone(item)

    def _on_node_context_menu(self, node: StepNodeItem, screen_pos):
        """Clic-droit sur un nœud : le sélectionne d'abord s'il ne fait pas déjà partie de la
        sélection courante, puis ouvre le menu construit par build_node_context_menu() — jamais
        de logique de nœud dupliquée ici, le menu appelle les mêmes gestionnaires que le
        rail/le raccourci."""
        if node not in self._scene.selectedItems():
            self._scene.clearSelection()
            node.setSelected(True)
        build_node_context_menu(node, self).exec(screen_pos)

    def _on_duplicate_selected(self):
        """Seul point d'appel réel des trois déclencheurs (bouton du rail, Ctrl+D, action
        "Dupliquer" du menu contextuel)."""
        originals = [n for n in self._scene.selectedItems() if isinstance(n, StepNodeItem)]
        if not originals:
            return
        copies = [self._scene.duplicate_node(n) for n in originals]
        self._scene.clearSelection()
        for c in copies:
            if c:
                c.setSelected(True)
                # Sans ça, le doublon afficherait des IDs de profil bruts dans son contenu
                # déplié jusqu'à ce qu'on le double-clique (chantier relooking des nœuds).
                c.set_profile_names(self._profile_names)

    def _on_save_as_template(self):
        """"Enregistrer comme modèle..." du menu contextuel (chantier bibliothèque d'étapes
        réutilisables) — n'agit que si EXACTEMENT un nœud est sélectionné : la portée validée
        avec l'utilisateur est une seule étape, jamais un groupe (voir docstring StepTemplate,
        database/models.py)."""
        from PySide6.QtWidgets import QInputDialog
        from database import db_manager as db
        from ui.step_editor.common import STEP_META
        import copy as _copy

        selected = [n for n in self._scene.selectedItems() if isinstance(n, StepNodeItem)]
        if len(selected) != 1:
            return
        node = selected[0]
        step = node.step
        default_name = step.get("label") or STEP_META[step["step_type"]]["label"]

        name, ok = QInputDialog.getText(
            self, "Enregistrer comme modèle", "Nom du modèle :", text=default_name,
        )
        name = name.strip()
        if not ok or not name:
            return

        # config nettoyée de _step_key ICI, au seul point d'écriture — voir docstring
        # StepTemplate (database/models.py) : aucun config_json stocké ne doit jamais en
        # contenir, pour qu'un futur consommateur (insertion, duplication de modèle...) n'ait
        # jamais à s'en souvenir lui-même.
        config = _copy.deepcopy(step.get("config") or {})
        config.pop("_step_key", None)

        unique_name = db.unique_step_template_name(name)
        db.create_step_template(
            name=unique_name, step_type=step["step_type"], config=config,
            label=step.get("label") or None,
        )

    def _on_open_settings_dialog(self):
        """Raccourci vers les métadonnées du pipeline (nom/planification/déclenchement/actif) —
        ce widget ne les gère pas lui-même ; évite l'aller-retour "fermer, retrouver la ligne,
        cliquer Paramètres". N'existe que si show_settings_shortcut_button=True (toolbar) — voir
        AtelierPipelinesView qui passe False, le panneau de droite étant toujours visible."""
        from database import db_manager as db
        from ui.step_editor import PipelineSettingsDialog

        if PipelineSettingsDialog(self, pipeline=self._pipeline).exec():
            refreshed = db.get_pipeline(self._pipeline.id)
            if refreshed:
                self._pipeline = refreshed
                self.pipeline_renamed.emit(refreshed.name)

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

        zones = [
            {
                "name":   z.name,
                "pos_x":  int(z.pos().x()),
                "pos_y":  int(z.pos().y()),
                "width":  int(z._width),
                "height": int(z._height),
            }
            for z in self._scene.zones
        ]
        return steps, edges, zones

    def save(self) -> bool:
        """Valide puis persiste le graphe — ex-_on_save(), sans self.accept() (un QWidget n'a pas
        cette notion). Émet `saved` en cas de succès ; l'hôte (dialogue : self.accept() ; Atelier :
        rien de spécial, le bouton "Enregistrer le graphe" reste local au canevas) réagit à la
        valeur de retour ou au signal selon son propre besoin."""
        steps, edges, zones = self._collect_graph()

        if not steps:
            QMessageBox.warning(
                self, "Étapes manquantes",
                "Ajoutez au moins une étape avant d'enregistrer.",
            )
            return False

        errors, warnings = validate_pipeline_graph(steps, edges)
        if errors:
            QMessageBox.warning(
                self, "Graphe invalide",
                "Ce graphe d'étapes ne peut pas fonctionner :\n\n"
                + "\n".join(f"• {e}" for e in errors),
            )
            return False
        if warnings:
            reply = QMessageBox.question(
                self, "Avertissement",
                "Certaines étapes pourraient tourner sans les données attendues :\n\n"
                + "\n".join(f"• {w}" for w in warnings)
                + "\n\nContinuer quand même ?",
                QMessageBox.Yes | QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return False

        from database import db_manager as db
        db.save_pipeline_graph(self._pipeline.id, steps, edges, zones=zones)
        self.saved.emit()
        return True

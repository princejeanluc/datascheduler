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

from PySide6.QtCore import QPointF, QSize, QTimer, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QMessageBox, QInputDialog,
)

from ui.styles import COLORS
from ui.step_editor.step_type_chooser_dialog import StepTypeChooserDialog
from ui.step_editor.common import _icon
from ui.main_window.widgets import _make_search_input
from core.pipeline import validate_pipeline_graph, topological_ranks

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
from ui.help.content import get_topic

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

    def __init__(self, parent=None, pipeline=None, highlight_step_key: str | None = None,
                 show_settings_shortcut_button: bool = True):
        super().__init__(parent)
        self._pipeline = pipeline
        self._show_settings_shortcut_button = show_settings_shortcut_button
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

        if highlight_step_key:
            # Lien "Voir dans le graphe" depuis une ligne d'historique en échec (chantier UX
            # éditeur, Lot 1, B1) — surlignage ponctuel à l'ouverture.
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

        # Barre de contexte (chantier chrome de l'éditeur) — ne garde que ce qui n'est pas de
        # l'édition du graphe : les 6 actions du canevas (ajouter/supprimer/ranger/zones/
        # mini-carte) vivent désormais dans le rail d'icônes flottant (tool_rail.py), pas ici.
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

        if self._show_settings_shortcut_button:
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
        from ui.step_editor import _open_config_dialog
        from database import db_manager as db

        dlg = StepTypeChooserDialog(self, include_routing_nodes=True)
        if not dlg.exec():
            return
        config_dlg = _open_config_dialog(
            dlg.chosen_type, {}, self,
            self._oracle_profiles, self._ftp_profiles, self._sql_queries,
            self._smtp_profiles, self._db_profiles,
            prior_steps=[n.step for n in self._scene.nodes.values()],
            # Lecture fraîche à chaque ouverture (jamais mise en cache) — une variable ajoutée
            # dans les Paramètres doit apparaître immédiatement dans "+ Variable".
            pipeline_variable_names=[v.name for v in db.get_pipeline_variables(self._pipeline.id)],
        )
        if config_dlg and config_dlg.exec():
            step = config_dlg.result_step()
            node = self._scene.add_node(step, self._next_new_node_pos())
            if node is not None:
                node.set_profile_names(self._profile_names)

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

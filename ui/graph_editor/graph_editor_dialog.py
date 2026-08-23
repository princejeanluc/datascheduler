"""
DataScheduler — ui/graph_editor/graph_editor_dialog.py
Dialogue principal de l'éditeur graphique (chantier 6b) : édite uniquement les étapes + leurs
connexions d'un pipeline déjà existant. Nom/description/planification restent gérés par
PipelineEditorDialog ("Modifier"), inchangé — les deux dialogues restent interopérables sur le
même pipeline (voir docs/ARCHITECTURE.md).
"""

from PySide6.QtCore import QPointF, QTimer
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame, QMessageBox, QInputDialog,
)

from ui.styles import COLORS, DIALOG_STYLE
from ui.step_editor.step_type_chooser_dialog import StepTypeChooserDialog
from ui.main_window.widgets import _make_search_input
from core.pipeline import validate_pipeline_graph, topological_ranks

from .graph_scene import PipelineGraphScene
from .graph_view import PipelineGraphView
from .node_item import StepNodeItem
from .edge_item import EdgeItem
from .zone_item import ZoneItem
from .minimap_widget import GraphMinimapWidget

_NODE_SPACING_X = 240
_ROW_HEIGHT = 120
_ROWS_PER_COLUMN = 3
_START_X, _START_Y = 60, 60


class PipelineGraphEditorDialog(QDialog):
    """Éditeur graphique des étapes d'un pipeline déjà existant."""

    def __init__(self, parent=None, pipeline=None, highlight_step_key: str | None = None):
        super().__init__(parent)
        self._pipeline = pipeline
        # Instantané des positions juste avant le dernier "Ranger automatiquement" (chantier UX
        # éditeur, Lot 1) — aucun QUndoStack n'existe nulle part dans cette app, annulation à un
        # seul niveau volontairement minimale plutôt qu'une abstraction prématurée. Écrase le
        # précédent à chaque nouveau rangement, effacé par _on_undo_layout().
        self._layout_snapshot: dict[str, QPointF] | None = None
        # Résultats de la recherche textuelle courante (chantier UX éditeur, Lot 2, B3) —
        # reconstruits à chaque frappe dans _on_search_changed(), cyclés par _on_search_jump().
        self._search_matches: list[StepNodeItem] = []
        self._search_match_idx: int = -1
        self._load_profiles()

        self.setWindowTitle(f"Éditeur graphique — {pipeline.name}" if pipeline else "Éditeur graphique")
        self.setMinimumSize(900, 640)
        self.setStyleSheet(DIALOG_STYLE)
        self._build_ui()
        self._load_graph()

        if highlight_step_key:
            # Lien "Voir dans le graphe" depuis une ligne d'historique en échec (chantier UX
            # éditeur, Lot 1, B1) — surlignage ponctuel à l'ouverture, jamais le sondage live
            # ci-dessous : get_running_step_keys_multi()/get_running_step_keys() ne trouvent
            # structurellement jamais un run FAILED (filtrés sur RUNNING), le lancer serait donc
            # pur travail perdu. Limite acceptée et documentée : un run concurrent réellement en
            # cours sur ce même pipeline, dans une autre fenêtre, n'est pas pris en compte ici.
            self._highlight_failed_step(highlight_step_key)
            return

        # Traçage lumineux (chantier identité visuelle) : actif en permanence dès l'ouverture,
        # pas de bascule de mode — éditer un pipeline qui se trouve être en cours d'exécution
        # ailleurs affiche simplement le surlignage par-dessus, sans bloquer l'édition.
        from database import db_manager as db
        self._executing_timer = QTimer(self)
        self._executing_timer.setInterval(db.get_app_settings().trace_glow_refresh_s * 1000)
        self._executing_timer.timeout.connect(self._poll_executing_step)
        self._executing_timer.start()

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

        btn_auto_layout = QPushButton("  Ranger automatiquement")
        btn_auto_layout.setObjectName("secondary")
        btn_auto_layout.setFixedHeight(32)
        btn_auto_layout.setToolTip(
            "Repositionne toutes les étapes par rang (colonnes de gauche à droite selon "
            "l'ordre du graphe), sans changer les connexions."
        )
        btn_auto_layout.clicked.connect(self._on_auto_layout)
        toolbar.addWidget(btn_auto_layout)

        self._btn_undo_layout = QPushButton("  Annuler le rangement")
        self._btn_undo_layout.setObjectName("secondary")
        self._btn_undo_layout.setFixedHeight(32)
        self._btn_undo_layout.setEnabled(False)
        self._btn_undo_layout.clicked.connect(self._on_undo_layout)
        toolbar.addWidget(self._btn_undo_layout)

        btn_add_zone = QPushButton("  + Ajouter une zone")
        btn_add_zone.setObjectName("secondary")
        btn_add_zone.setFixedHeight(32)
        btn_add_zone.setToolTip(
            "Dessine un rectangle nommé pour regrouper visuellement des étapes — purement "
            "décoratif, sans effet sur l'exécution. Glisser l'en-tête pour déplacer, le coin "
            "bas-droit pour redimensionner, double-clic pour renommer."
        )
        btn_add_zone.clicked.connect(self._on_add_zone)
        toolbar.addWidget(btn_add_zone)

        btn_toggle_minimap = QPushButton("  Mini-carte")
        btn_toggle_minimap.setObjectName("secondary")
        btn_toggle_minimap.setFixedHeight(32)
        btn_toggle_minimap.setToolTip("Afficher/masquer la mini-carte de navigation.")
        btn_toggle_minimap.clicked.connect(self._on_toggle_minimap)
        toolbar.addWidget(btn_toggle_minimap)

        hint = QLabel(
            "Glisser depuis un point de sortie (droite) vers un point d'entrée (gauche) pour "
            "connecter deux étapes.  Suppr/Retour arrière pour supprimer la sélection."
        )
        hint.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 11px; font-style: italic;")
        toolbar.addWidget(hint, stretch=1)

        self.inp_search = _make_search_input("Rechercher un nœud…")
        self.inp_search.setToolTip(
            "Filtre les étapes par type ou libellé. Entrée pour centrer la vue sur le résultat "
            "suivant."
        )
        self.inp_search.textChanged.connect(self._on_search_changed)
        self.inp_search.returnPressed.connect(self._on_search_jump)
        toolbar.addWidget(self.inp_search)

        root.addLayout(toolbar)

        sep = QFrame(); sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet(f"background: {COLORS['border']}; max-height: 1px;")
        root.addWidget(sep)

        self._scene = PipelineGraphScene()
        self._scene.node_double_clicked.connect(self._on_node_double_clicked)
        self._scene.zone_double_clicked.connect(self._on_zone_double_clicked)
        self._view = PipelineGraphView(self._scene)
        root.addWidget(self._view, stretch=1)

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
        `node_subset`, en prévision d'un futur "Ranger la sélection" — pas encore branché dans
        ce lot, mais le coût de le supporter ici est quasi nul) : colonne = rang topologique,
        ligne = ordre par barycentre des prédécesseurs déjà positionnés au sein du même rang
        (minimise les croisements d'arêtes grossiers — un simple rang→colonne sans ce tri
        laisserait un pipeline à plusieurs branches enchevêtré même "rangé"). Retourne None si
        le graphe contient un cycle (rangement impossible)."""
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

        # Amorcé aux positions Y actuelles — sert de repère de barycentre pour tout prédécesseur
        # hors sous-ensemble (jamais repositionné) ou pas encore traité à ce stade de la boucle.
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
        # parents (donc toujours False tant que le dialogue n'a jamais été réellement affiché),
        # alors qu'isHidden() ne reflète que l'état explicitement demandé sur ce widget.
        self._minimap.setVisible(self._minimap.isHidden())

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
        "Source"/bouton "+ Artefact" (chantier 3, ui/step_editor/base_config_dialog.py) doivent
        voir pour lister les producteurs par nom, au lieu de toujours retomber sur "étape
        précédente (par défaut)" faute de savoir à qui ce nœud est relié."""
        return [e.from_node.step for e in self._scene.edges if e.to_node is node]

    def _on_add_step(self):
        from ui.step_editor import _open_config_dialog

        dlg = StepTypeChooserDialog(self, include_condition=True)
        if not dlg.exec():
            return
        config_dlg = _open_config_dialog(
            dlg.chosen_type, {}, self,
            self._oracle_profiles, self._ftp_profiles, self._sql_queries,
            self._smtp_profiles, self._db_profiles,
            # Le nœud n'existe pas encore, donc aucune arête entrante réelle — même souplesse
            # que l'éditeur linéaire à l'ajout (prior_steps=self._steps_data, la liste complète
            # à ce stade) : tous les nœuds déjà sur le canevas sont proposés comme sources
            # possibles, à connecter ensuite par un glisser-déposer.
            prior_steps=[n.step for n in self._scene.nodes.values()],
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
            prior_steps=self._incoming_prior_steps(node),
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
            elif isinstance(item, ZoneItem):
                self._scene.remove_zone(item)

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

    def _on_save(self):
        steps, edges, zones = self._collect_graph()

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
        db.save_pipeline_graph(self._pipeline.id, steps, edges, zones=zones)
        self.accept()

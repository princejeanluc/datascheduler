"""
DataScheduler — ui/main_window/pipelines_view.py
Vue Pipelines : liste + création + export/import.
"""

from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton, QFrame,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QMessageBox, QFileDialog, QMenu, QInputDialog, QApplication,
)
from PySide6.QtCore import Qt, QSize, QTimer
from PySide6.QtGui import QColor, QShortcut, QKeySequence
from ui.styles import COLORS
from .widgets import (
    _icon, _action_btn, _configure_columns, _filter_table_rows, _make_search_input,
    _make_empty_label, _make_title, _make_subtitle, _STATUS_BADGE, _status_str,
    _make_status_badge, _ordered_with_chains, PipelineFlowThumbnail,
)


class PipelinesView(QWidget):
    def __init__(self):
        super().__init__()
        self._build_ui()
        from database import db_manager as db
        self._timer = QTimer(self)
        self._timer.setInterval(db.get_app_settings().pipelines_refresh_s * 1000)
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
        btn_new_graph = QPushButton("  Nouveau (graphique)"); btn_new_graph.setObjectName("secondary")
        btn_new_graph.setFixedHeight(36)
        btn_new_graph.setIcon(_icon("fa5s.project-diagram", COLORS["text_main"]))
        btn_new_graph.setIconSize(QSize(13, 13))
        btn_new_graph.setToolTip(
            "Créer un pipeline directement dans l'éditeur graphique — sans passer par "
            "l'éditeur classique (nom + planification restent modifiables ensuite via "
            "« Modifier »)."
        )
        btn_new_graph.clicked.connect(self._on_new_pipeline_graph)
        header.addWidget(btn_new_graph)
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
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.Fixed)
        self.table.setColumnWidth(5, 118)
        self.table.doubleClicked.connect(self._on_row_dbl_click)
        layout.addWidget(self.table)

        # Modèle de démarrage (chantier UX éditeur, Lot 1, C1) — dupliquer/adapter un squelette
        # réaliste plutôt que partir d'une toile blanche, visible uniquement tant qu'aucun
        # pipeline n'existe (même condition que le label lui-même, voir refresh() ci-dessous).
        btn_template = QPushButton("  Commencer avec un modèle")
        btn_template.setObjectName("secondary")
        btn_template.setFixedHeight(34)
        btn_template.setIcon(_icon("fa5s.magic", COLORS["text_main"]))
        btn_template.setIconSize(QSize(13, 13))
        btn_template.clicked.connect(self._on_start_from_template)

        self._empty_label = _make_empty_label(
            "Aucun pipeline configuré — assurez-vous d'abord d'avoir vos connexions et requêtes "
            "SQL (voir Connexions / Requêtes SQL), puis cliquez sur « Nouveau pipeline ».",
            button=btn_template,
        )
        self._empty_label.setVisible(False)
        layout.addWidget(self._empty_label)

        QShortcut(QKeySequence("Ctrl+N"), self, activated=self._on_new_pipeline)

        self.refresh()

    def _on_search_changed(self, text: str):
        _filter_table_rows(self.table, text, columns=[0, 1, 2, 3, 4])

    def refresh(self):
        # Reconstruit toute la colonne Actions à chaque appel (y compris chaque QMenu "⋯") — si
        # un de ces menus est actuellement ouvert (l'utilisateur est en train de choisir une
        # action), le détruire sous lui plante l'app (QMenu gère sa propre boucle d'événements
        # imbriquée pendant qu'il est affiché). Reporté au prochain appel (30s, timer périodique)
        # plutôt que de risquer ça — l'utilisateur aura fermé le menu bien avant.
        if QApplication.activePopupWidget() is not None:
            return

        from database import db_manager as db
        from ui.step_editor import STEP_META
        from core.pipeline import is_cancel_requested, is_pipeline_running
        from core.scheduler import describe_schedule
        pipelines = db.get_pipelines()
        ordered = _ordered_with_chains(pipelines)
        step_labels = db.get_running_step_labels()
        self._pipeline_ids = [p.id for p, _depth in ordered]
        self.table.setVisible(bool(pipelines))
        self._empty_label.setVisible(not pipelines)
        self.table.setRowCount(len(ordered))
        for r_idx, (p, depth) in enumerate(ordered):
            st       = _status_str(p.last_status)
            plan     = describe_schedule(p)
            next_run = p.next_run_at.strftime("%d/%m/%Y %H:%M") if p.next_run_at else "—"

            # Résumé des étapes
            step_types = [str(s.step_type).replace("StepType.", "") for s in (p.steps or [])]
            steps_str  = " → ".join(
                STEP_META.get(t, {}).get("label", t) for t in step_types
            ) or "—"
            step_colors = [STEP_META.get(t, {}).get("color", COLORS["border"]) for t in step_types]

            trigger_tooltip = ""
            if p.trigger_after_pipeline_id:
                parent_name = p.trigger_after_pipeline.name if p.trigger_after_pipeline else "?"
                cond_label = {"SUCCESS": "Succès", "FAILURE": "Échec", "ALWAYS": "Toujours"}.get(
                    _status_str(p.trigger_condition), "—"
                )
                trigger_tooltip = f"Se lance aussi après « {parent_name} » ({cond_label})"

            text_color = COLORS["text_dim"] if not p.is_active else COLORS["text_main"]
            name_indent = "    " * (depth - 1) if depth else ""
            name_display = f"{name_indent}{'↳ ' if depth else ''}{p.name}"
            name_color = COLORS["text_dim"] if (depth or not p.is_active) else COLORS["text_main"]
            cells = [name_display, st, steps_str, plan, next_run]
            for c_idx, cell in enumerate(cells):
                if c_idx == 1:
                    badge_st   = "INACTIF" if not p.is_active else st
                    if p.is_active and st == "RUNNING" and is_cancel_requested(p.id):
                        badge_st = "ARRÊT EN COURS"
                    badge_name = "badge_idle" if not p.is_active else _STATUS_BADGE.get(st, "badge_idle")
                    badge = _make_status_badge(badge_st, badge_name)
                    if p.is_active and st == "RUNNING":
                        badge.setToolTip(step_labels.get(p.id, ""))
                    self.table.setCellWidget(r_idx, c_idx, badge)
                elif c_idx == 2:
                    # Vignette de flux + résumé texte (chantier identité, vague 3, idée 8) — la
                    # vignette donne une reconnaissance visuelle immédiate, le texte reste
                    # inchangé (déjà utile en lecture).
                    steps_w = QWidget()
                    steps_hl = QHBoxLayout(steps_w)
                    steps_hl.setContentsMargins(4, 0, 4, 0)
                    steps_hl.setSpacing(8)
                    steps_hl.addWidget(PipelineFlowThumbnail(step_colors))
                    # QLabel ne s'élide pas tout seul selon la largeur disponible (contrairement
                    # à un QTableWidgetItem) — troncature statique + "…" plutôt qu'une coupe en
                    # plein mot sans indication visuelle (repéré sur une capture réelle) ; le
                    # texte complet reste dans l'infobulle de toute la cellule, juste en dessous.
                    display_steps = steps_str if len(steps_str) <= 45 else steps_str[:44] + "…"
                    steps_lbl = QLabel(display_steps)
                    steps_lbl.setStyleSheet(
                        f"color: {text_color}; background: transparent; border: none;"
                    )
                    steps_hl.addWidget(steps_lbl)
                    steps_hl.addStretch()
                    steps_w.setToolTip(steps_str)
                    self.table.setCellWidget(r_idx, c_idx, steps_w)
                else:
                    item = QTableWidgetItem(cell)
                    item.setForeground(QColor(name_color if c_idx == 0 else text_color))
                    if c_idx == 3 and trigger_tooltip:
                        item.setToolTip(trigger_tooltip)
                    self.table.setItem(r_idx, c_idx, item)

            pid       = p.id
            is_active = p.is_active
            pname     = p.name
            aw  = QWidget(); al = QHBoxLayout(aw); al.setContentsMargins(4, 4, 4, 4); al.setSpacing(4)
            btn_run = _action_btn("fa5s.play", tooltip="Exécuter maintenant",
                                  icon_color="#000000")
            btn_edit   = _action_btn(
                "fa5s.pencil-alt", object_name="secondary",
                tooltip="Modifier — nom, planification, liste des étapes",
            )
            btn_more = _action_btn("fa5s.ellipsis-h", object_name="secondary", tooltip="Plus d'actions")
            btn_run.clicked.connect(lambda _, i=pid: self._on_run_pipeline(i))
            btn_edit.clicked.connect(lambda _, i=pid: self._on_edit_pipeline(i))

            # Actions secondaires (moins fréquentes) regroupées dans un menu — même patron que
            # le bouton "+ Artefact" de ui/step_editor/base_config_dialog.py, pour ne pas garder
            # 8 boutons pleine largeur par ligne dans une colonne "Actions".
            menu = QMenu(btn_more)
            if is_pipeline_running(pid):
                # Accessible même quand la fenêtre d'exécution a été fermée entre-temps (elle
                # continue en arrière-plan) — sans ça, aucun moyen direct d'interrompre un run
                # dont on a fermé le dialogue de suivi.
                act_interrupt = menu.addAction("Interrompre l'exécution en cours")
                act_interrupt.triggered.connect(
                    lambda _, i=pid, n=pname: self._on_interrupt_pipeline(i, n)
                )
            act_toggle = menu.addAction("Désactiver" if is_active else "Activer")
            act_toggle.triggered.connect(lambda _, i=pid, a=is_active: self._on_toggle_pipeline(i, a))
            act_graph = menu.addAction("Éditeur graphique")
            act_graph.triggered.connect(lambda _, i=pid: self._on_edit_pipeline_graph(i))
            act_validate = menu.addAction("Valider (à blanc)")
            act_validate.triggered.connect(lambda _, i=pid, n=pname: self._on_validate_pipeline(i, n))
            resumable_run = db.get_last_resumable_run(pid)
            if resumable_run:
                act_resume = menu.addAction("Reprendre depuis l'échec")
                act_resume.triggered.connect(
                    lambda _, i=pid, n=pname, r=resumable_run.id: self._on_resume_pipeline(i, n, r)
                )
            act_dup = menu.addAction("Dupliquer")
            act_dup.triggered.connect(lambda _, i=pid: self._on_duplicate_pipeline(i))
            act_export = menu.addAction("Exporter")
            act_export.triggered.connect(lambda _, i=pid: self._on_export_pipeline(i))
            menu.addSeparator()
            act_del = menu.addAction("Supprimer")
            act_del.triggered.connect(lambda _, i=pid: self._on_delete_pipeline(i))
            btn_more.setMenu(menu)

            al.addWidget(btn_run); al.addWidget(btn_edit); al.addWidget(btn_more); al.addStretch()
            self.table.setCellWidget(r_idx, 5, aw)
            self.table.setRowHeight(r_idx, 52)

        self._on_search_changed(self.inp_search.text())

    def _on_new_pipeline(self):
        from ui.step_editor import PipelineEditorDialog
        if PipelineEditorDialog(self).exec():
            self.refresh()

    def _on_new_pipeline_graph(self):
        """Créer un pipeline sans passer par l'éditeur classique — celui-ci imposait au moins
        une étape avant d'enregistrer, ce qui forçait un aller-retour même pour qui ne veut
        travailler qu'en graphe. Ici : juste un nom, puis directement l'éditeur graphique
        (nom/planification restent modifiables ensuite via « Modifier »)."""
        name, ok = QInputDialog.getText(self, "Nouveau pipeline (éditeur graphique)", "Nom du pipeline :")
        name = (name or "").strip()
        if not ok or not name:
            return

        from database import db_manager as db
        from ui.graph_editor import PipelineGraphEditorDialog

        p = db.create_pipeline(name=name)
        if PipelineGraphEditorDialog(self, pipeline=p).exec():
            self._schedule_if_possible(p.id)
            self.refresh()
        else:
            # Rien enregistré (annulé sans ajouter d'étape) — un pipeline coquille à 0 étape
            # ne servirait qu'à encombrer la liste.
            db.delete_pipeline(p.id)

    def _on_start_from_template(self):
        """Modèle de démarrage (chantier UX éditeur, Lot 1, C1) — même mécanisme que l'import
        d'un vrai fichier .dspipeline (plan_import()/apply_import() n'exigent pas qu'un bundle
        vienne d'un vrai export), mais sans dialogue de revue : le modèle n'a ni profil ni
        collision à arbitrer (aucune référence de profil dans son bundle, nom toujours unique
        via _unique_name côté apply_import). Ouvre directement l'éditeur graphique sur le
        résultat pour que l'utilisateur atterrisse droit sur les champs à compléter."""
        from database.export_import import plan_import, apply_import
        from database.pipeline_templates import build_starter_template_bundle
        from database import db_manager as db
        from ui.graph_editor import PipelineGraphEditorDialog

        plan = plan_import(build_starter_template_bundle())
        if not plan.success:
            QMessageBox.critical(self, "Échec du modèle", plan.error or "Erreur inconnue.")
            return
        result = apply_import(plan)
        if not result.success:
            QMessageBox.critical(self, "Échec du modèle", result.error or "Erreur inconnue.")
            return

        self.refresh()
        pipeline = db.get_pipeline(result.pipeline_id) if result.pipeline_id else None
        if pipeline:
            PipelineGraphEditorDialog(self, pipeline=pipeline).exec()
            self._schedule_if_possible(pipeline.id)
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
            # Le dialogue valide lui-même (verify=...) et reste ouvert en cas de mot de passe
            # incorrect — évite d'avoir à ressélectionner le fichier pour une simple faute de
            # frappe (voir PipelineImportPasswordDialog._on_validate). plan.success est déjà
            # vrai ici si le dialogue a été accepté.
            pwd_dlg = PipelineImportPasswordDialog(
                self, verify=lambda pwd: plan_import_from_file(path, password=pwd),
            )
            if not pwd_dlg.exec():
                return
            plan = pwd_dlg.plan

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

        if result.pipeline_id is not None:
            self._schedule_if_possible(result.pipeline_id)
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

    def _on_row_dbl_click(self, index):
        row = index.row()
        if row >= len(self._pipeline_ids):
            return
        from database import db_manager as db
        from ui.dialogs import PipelineDetailDialog
        p = db.get_pipeline(self._pipeline_ids[row])
        if p:
            PipelineDetailDialog(self, pipeline=p).exec()

    def _on_validate_pipeline(self, pipeline_id: int, pipeline_name: str):
        from ui.dialogs import PipelineDryRunDialog
        PipelineDryRunDialog(pipeline_id, pipeline_name, self).exec()

    def _on_duplicate_pipeline(self, pipeline_id: int):
        from database.export_import import duplicate_pipeline
        result = duplicate_pipeline(pipeline_id)
        if not result.success:
            QMessageBox.critical(self, "Échec de la duplication", result.error or "Erreur inconnue.")
            return
        QMessageBox.information(
            self, "Pipeline dupliqué",
            "Le pipeline a été dupliqué avec succès — la copie est désactivée par défaut."
        )
        self.refresh()

    def _on_run_pipeline(self, pipeline_id: int):
        from database import db_manager as db
        from ui.dialogs import RunProgressDialog
        from core.pipeline import is_pipeline_running, request_cancel
        from core.execution_mode import (
            is_background_mode_active, is_pipeline_running_anywhere,
            request_run_now, request_cancel_run,
        )
        p = db.get_pipeline(pipeline_id)
        if not p:
            return

        # En mode arrière-plan, l'exécution réelle vit dans le process worker, pas ici —
        # is_pipeline_running()/request_cancel() (core.pipeline) ne lisent/n'écrivent qu'un état
        # en mémoire propre au process courant, donc toujours "pas en cours" côté appli desktop
        # même si le worker l'exécute réellement. is_pipeline_running_anywhere() lit le statut en
        # base (écrit par n'importe quel process qui exécute), fiable dans les deux modes.
        background = is_background_mode_active()
        currently_running = (
            is_pipeline_running_anywhere(pipeline_id) if background
            else is_pipeline_running(pipeline_id)
        )

        if p.prevent_overlap and currently_running:
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
                if not request_cancel_run(pipeline_id):
                    request_cancel(pipeline_id)
                # Reflète l'état "Arrêt en cours" tout de suite dans le tableau (colonne Statut)
                # plutôt que d'attendre le prochain rafraîchissement automatique (30s) — sans ça,
                # rien n'indique visuellement que la demande a bien été prise en compte.
                self.refresh()
                QMessageBox.information(
                    self, "Demande envoyée",
                    "L'arrêt a été demandé — le statut affichera « Arrêt en cours » jusqu'à ce "
                    "que l'étape en cours se termine."
                )
            return

        # Validation structurelle avant tout lancement (chantier UX éditeur, Lot 1) — nœuds
        # orphelins, ports requis non connectés, cycles, références de profil disparues.
        # test_connections=False : jamais de test réseau réel ici, cette phase reste rapide et
        # synchrone (0 accès réseau, quelques lectures DB) — les tests de connexion réels restent
        # le domaine exclusif de "Valider (à blanc)" (menu "⋯"), plus lent, jamais déclenché
        # automatiquement. Validé à CHAQUE clic, pas seulement le premier : dry_run_pipeline sans
        # test_connections est trop rapide pour justifier un cache invalidé sur chaque point
        # d'édition (un chemin d'édition oublié réutiliserait silencieusement une passe périmée).
        from core.pipeline import dry_run_pipeline
        dry_run = dry_run_pipeline(pipeline_id, test_connections=False)
        if dry_run.errors:
            QMessageBox.warning(
                self, "Pipeline invalide",
                f"« {p.name} » ne peut pas s'exécuter tel quel :\n\n"
                + "\n".join(f"• {e}" for e in dry_run.errors),
            )
            return
        if dry_run.warnings:
            reply = QMessageBox.question(
                self, "Avertissement",
                f"« {p.name} » pourrait tourner sans les données attendues :\n\n"
                + "\n".join(f"• {w}" for w in dry_run.warnings)
                + "\n\nContinuer quand même ?",
                QMessageBox.Yes | QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return

        if request_run_now(pipeline_id):
            from .remote_run_dialog import open_remote_run_dialog
            open_remote_run_dialog(self, pipeline_id, p.name)
        else:
            RunProgressDialog(pipeline_id, p.name, self).exec()
        self.refresh()

    def _on_resume_pipeline(self, pipeline_id: int, pipeline_name: str, resume_from_run_id: int):
        from ui.dialogs import RunProgressDialog
        RunProgressDialog(pipeline_id, pipeline_name, self, resume_from_run_id=resume_from_run_id).exec()
        self.refresh()

    def _on_delete_pipeline(self, pipeline_id: int):
        from database import db_manager as db
        dependents = db.get_pipelines_triggered_by(pipeline_id)
        if dependents:
            names = ", ".join(p.name for p in dependents)
            msg = (
                f"{len(dependents)} pipeline(s) se lance(nt) après celui-ci : {names}.\n\n"
                f"Le supprimer quand même ? Ces pipelines repasseront en planification seule."
            )
        else:
            msg = "Supprimer ce pipeline ?"
        reply = QMessageBox.question(self, "Supprimer", msg, QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            db.delete_pipeline(pipeline_id)
            self.refresh()

    @staticmethod
    def _schedule_if_possible(pipeline_id: int):
        """(Re)planifie immédiatement auprès d'APScheduler — même patron défensif que
        _on_toggle_pipeline() ci-dessous (RuntimeError silencieuse : scheduler non initialisé
        dans les tests qui construisent une vue directement). Utilisé partout où un pipeline
        actif est créé/modifié en dehors de PipelineEditorDialog._on_save() (qui gère déjà son
        propre cas), pour ne jamais dépendre d'un redémarrage de l'app pour prendre effet. En
        mode exécution en arrière-plan, délègue au worker (core/execution_mode.py) plutôt que de
        toucher un scheduler local qui n'existe pas dans ce mode."""
        from core.execution_mode import request_reload
        if request_reload():
            return
        try:
            from core.scheduler import get_scheduler
            get_scheduler().schedule_pipeline(pipeline_id)
        except RuntimeError:
            pass

    def _on_interrupt_pipeline(self, pipeline_id: int, pipeline_name: str):
        """Interrompre un run en cours indépendamment de la fenêtre d'exécution — accessible
        même après avoir fermé RunProgressDialog (qui laisse désormais le pipeline continuer en
        arrière-plan, voir ui/dialogs/run_progress_dialog.py)."""
        from core.pipeline import request_cancel
        reply = QMessageBox.question(
            self, "Interrompre l'exécution",
            f"Interrompre l'exécution en cours de « {pipeline_name} » ?\n\n"
            "L'interruption est coopérative : elle prend effet à la fin de l'étape en cours, "
            "pas instantanément si celle-ci est longue (ex: une extraction Oracle de plusieurs "
            "minutes).",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        request_cancel(pipeline_id)
        self.refresh()
        QMessageBox.information(
            self, "Demande envoyée",
            "L'arrêt a été demandé — le statut affichera « Arrêt en cours » jusqu'à ce que "
            "l'étape en cours se termine."
        )

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

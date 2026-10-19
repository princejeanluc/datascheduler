"""
DataScheduler — ui/main_window/pipelines_view.py
Vue Pipelines : liste + création + export/import.
"""

import re
from datetime import datetime

from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton, QFrame,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QMessageBox, QFileDialog, QMenu, QInputDialog, QApplication,
)
from PySide6.QtCore import Qt, QSize, QTimer, Signal
from PySide6.QtGui import QColor, QShortcut, QKeySequence
from ui.styles import COLORS
from ui.time_display import fmt_time, fmt_time_local, fmt_relative, to_display
from ui.components import make_page_header, SidePanel
from .widgets import (
    _icon, _action_btn, _configure_columns, _filter_table_rows, _make_search_input,
    _make_empty_label, _make_button_with_hint, _STATUS_BADGE, _status_str,
    _make_status_badge, _ordered_with_chains, PipelineStepDagThumbnail, RunHistoryDots,
    FONT_MONO_STACK,
)

# A3 : "Étape i/n : ..." déjà le format renvoyé par get_running_step_labels() (core/pipeline.py)
# — la ligne de détail de l'état n'en garde que "i/n", sans le libellé de l'étape.
_RUNNING_STEP_RE = re.compile(r"Étape (\d+)/(\d+)")


def _format_elapsed_mmss(started_at) -> str:
    """Écoulé d'un run en cours, en MM:SS — jamais converti (c'est une durée), même principe que
    le rail d'Aujourd'hui (dashboard_view.py), dupliqué ici plutôt que partagé (REGLES.md : trois
    lignes semblables plutôt qu'une abstraction prématurée)."""
    if not started_at:
        return "00:00"
    seconds = max(0, int((datetime.utcnow() - started_at).total_seconds()))
    m, s = divmod(seconds, 60)
    return f"{m:02d}:{s:02d}"


def _format_duration_short(seconds) -> str:
    """« 2 min 04 » / « 38 s » — même format que la colonne Durée d'Aujourd'hui, dupliqué ici."""
    if not seconds:
        return "0 s"
    m, s = divmod(int(seconds), 60)
    return f"{m} min {s:02d}" if m else f"{s} s"


def _format_next_run(next_run_at) -> str:
    """A6 : « demain HH:MM » / « HH:MM » nu le même jour / « JJ/MM HH:MM » plus loin — jamais
    converti (déjà dans le fuseau réglé, comme next_run_at partout ailleurs). Comparé au jour
    local courant, lui aussi déjà dans le fuseau réglé (to_display(utcnow()))."""
    if not next_run_at:
        return "—"
    today = to_display(datetime.utcnow()).date()
    delta_days = (next_run_at.date() - today).days
    if delta_days == 0:
        return next_run_at.strftime("%H:%M")
    if delta_days == 1:
        return f"demain {next_run_at.strftime('%H:%M')}"
    return next_run_at.strftime("%d/%m %H:%M")


_TRIGGER_CONDITION_PHRASE = {"SUCCESS": "si réussite", "FAILURE": "si échec", "ALWAYS": "toujours"}


def _pipeline_state_detail(p, status: str, last_run, running_label: str, missed) -> tuple:
    """Texte + couleur de la ligne de détail sous la pastille d'état (A3). Priorité, comme le
    badge existant : inactif > en cours > manqué > échec > réussi > rien (jamais exécuté, pas de
    changement). Pas d'état "En attente" (C4, gated) : un enfant bloqué par son parent montre son
    propre dernier état réel, jamais le texte synthétique de la maquette."""
    if not p.is_active:
        return "Inactif", COLORS["text_dim"]
    if status == "RUNNING":
        match = _RUNNING_STEP_RE.search(running_label or "")
        if match and last_run is not None:
            elapsed = _format_elapsed_mmss(last_run.started_at)
            return f"étape {match.group(1)}/{match.group(2)} · {elapsed}", COLORS["text_dim"]
        return running_label or "", COLORS["text_dim"]
    if missed:
        return f"prévue {fmt_time_local(missed['expected_at'])}", COLORS["warning"]
    if status == "FAILED" and last_run is not None:
        err = (last_run.error_message or "").strip().splitlines()[0] if last_run.error_message else ""
        err = err if len(err) <= 40 else err[:39] + "…"
        detail = fmt_time(last_run.started_at)
        return (f"{detail} · {err}" if err else detail), COLORS["danger"]
    if status == "SUCCESS" and last_run is not None:
        duration = _format_duration_short(last_run.duration_seconds)
        return f"{fmt_time(last_run.started_at)} · {duration}", COLORS["text_dim"]
    return "", COLORS["text_dim"]


class PipelinesView(QWidget):
    # Chantier Atelier Pipelines (écran 2) : remplace l'ouverture directe de
    # PipelineGraphEditorDialog/PipelineSettingsDialog — MainWindow écoute ce signal et bascule
    # vers l'Atelier (AtelierPipelinesView, 9e vue du QStackedWidget), jamais une entrée de la
    # nav rail. Args : pipeline_id, highlight_step_key (toujours None depuis cette vue — voir
    # HistoryView pour l'autre émetteur), is_new_pipeline (voir AtelierPipelinesView.open_pipeline
    # — True uniquement depuis _on_new_pipeline, pour reproduire à l'identique son comportement
    # "coquille vide supprimée au retour" / "planifié dès le premier enregistrement du graphe").
    open_atelier_requested = Signal(int, object, bool)

    def __init__(self):
        super().__init__()
        self._last_refresh_at = None
        self._build_ui()
        from database import db_manager as db
        self._timer = QTimer(self)
        self._timer.setInterval(db.get_app_settings().pipelines_refresh_s * 1000)
        self._timer.timeout.connect(self.refresh)
        self._timer.start()

        # A9 : "actualisé il y a N s" doit avancer en continu, pas seulement au rythme du
        # rafraîchissement complet (souvent 15-30s) — timer séparé, ne touche que ce label.
        self._footer_timer = QTimer(self)
        self._footer_timer.setInterval(1000)
        self._footer_timer.timeout.connect(self._refresh_footer_label)
        self._footer_timer.start()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(24)

        # A1 : en-tête via make_page_header (cohérence avec Paramètres/Ressources/Aujourd'hui) —
        # surtitre dynamique "N PIPELINES · M ACTIFS" tenu à jour dans refresh() (make_page_header
        # ne renvoie pas de référence à son surtitre, cherché une fois ici par objectName — même
        # patron que dashboard_view.py).
        btn_import = QPushButton("  Importer"); btn_import.setObjectName("secondary")
        btn_import.setFixedHeight(36)
        btn_import.setIcon(_icon("fa5s.file-import", COLORS["text_main"]))
        btn_import.setIconSize(QSize(13, 13))
        btn_import.clicked.connect(self._on_import_pipeline)

        # Le raccourci "Ctrl N" quitte le placeholder de la recherche (A1) pour s'afficher
        # directement sur le bouton — QPushButton ne pouvant pas mélanger deux styles de texte
        # dans un seul widget, voir _make_button_with_hint (widgets.py).
        btn_new = _make_button_with_hint(
            "+ Nouveau pipeline", "Ctrl N", on_click=self._on_new_pipeline,
        )
        btn_new.setToolTip(
            "Juste un nom, puis directement l'éditeur graphique — planification/déclenchement/"
            "actif restent modifiables ensuite via « Paramètres »."
        )

        header = make_page_header("", "Pipelines", actions=[btn_import, btn_new])
        self._eyebrow_lbl = header.findChild(QLabel, "page_eyebrow")
        layout.addWidget(header)

        self.inp_search = _make_search_input("Rechercher un pipeline…")
        self.inp_search.textChanged.connect(self._on_search_changed)
        search_row = QHBoxLayout()
        search_row.addWidget(self.inp_search)
        search_row.addStretch()
        layout.addLayout(search_row)

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
        self.table.setColumnWidth(1, 150)   # A3 : la ligne de détail a besoin d'un peu plus de place
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.Fixed)
        self.table.setColumnWidth(5, 156)
        self.table.doubleClicked.connect(self._on_row_dbl_click)
        layout.addWidget(self.table)

        # A9 : pied de liste — seule la ligne de légende vraie est gardée ("↳ se lance après…") ;
        # ni "clic sur la forme : ouvre l'Atelier" (C7, gated) ni "double-clic... ouvre l'Atelier"
        # (faux avec P10 — le code garde PipelineDetailDialog) ne sont reproduits.
        footer = QHBoxLayout()
        footer_legend = QLabel("↳ se lance après un autre pipeline (déclenchement)")
        footer_legend.setStyleSheet(f"color: {COLORS['text_dim']}; font-size: 11px;")
        footer.addWidget(footer_legend)
        footer.addStretch()
        self._footer_refreshed_lbl = QLabel("")
        self._footer_refreshed_lbl.setStyleSheet(f"color: {COLORS['text_dim']}; font-size: 11px;")
        footer.addWidget(self._footer_refreshed_lbl)
        layout.addLayout(footer)

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

        # A10 : panneau latéral partagé (déjà construit pour Aujourd'hui), réutilisé ici pour la
        # validation à blanc — remplace PipelineDryRunDialog (qui reste dans le code, orpheline).
        self._side_panel = SidePanel(self)

        self.refresh()

    def _on_search_changed(self, text: str):
        _filter_table_rows(self.table, text, columns=[0, 1, 2, 3, 4])

    def _refresh_footer_label(self):
        self._footer_refreshed_lbl.setText(f"actualisé {fmt_relative(self._last_refresh_at)}")

    def refresh(self):
        # Reconstruit toute la colonne Actions à chaque appel (y compris chaque QMenu "⋯") — si
        # un de ces menus est actuellement ouvert (l'utilisateur est en train de choisir une
        # action), le détruire sous lui plante l'app (QMenu gère sa propre boucle d'événements
        # imbriquée pendant qu'il est affiché). Reporté au prochain appel (30s, timer périodique)
        # plutôt que de risquer ça — l'utilisateur aura fermé le menu bien avant.
        if QApplication.activePopupWidget() is not None:
            return

        import json
        from database import db_manager as db
        from ui.step_editor import STEP_META
        from core.pipeline import is_cancel_requested, is_pipeline_running
        from core.scheduler import describe_schedule
        from core.steps import is_routing_node
        from core.missed_runs import get_pending
        pipelines = db.get_pipelines()
        ordered = _ordered_with_chains(pipelines)
        step_labels = db.get_running_step_labels()
        missed_map = {m["pipeline_id"]: m for m in get_pending()}
        self._pipeline_ids = [p.id for p, _depth in ordered]

        n_total = len(pipelines)
        n_active = sum(1 for p in pipelines if p.is_active)
        self._eyebrow_lbl.setText(
            f"{n_total} PIPELINE{'S' if n_total != 1 else ''} · "
            f"{n_active} ACTIF{'S' if n_active != 1 else ''}"
        )
        self.table.setVisible(bool(pipelines))
        self._empty_label.setVisible(not pipelines)
        self.table.setRowCount(len(ordered))
        for r_idx, (p, depth) in enumerate(ordered):
            st       = _status_str(p.last_status)
            plan     = describe_schedule(p)
            next_run = _format_next_run(p.next_run_at)

            # Résumé des étapes
            step_types = [str(s.step_type).replace("StepType.", "") for s in (p.steps or [])]
            steps_str  = " → ".join(
                STEP_META.get(t, {}).get("label", t) for t in step_types
            ) or "—"
            # Vignette mini-DAG (chantier Atelier Pipelines, écran 1) : step_key lu depuis
            # config_json (pas de colonne ORM dédiée — voir save_pipeline_graph()/
            # log_pipeline_edit() dans database/db_manager.py) ; repli synthétique "__step_<id>"
            # purement d'affichage si absent (jamais censé arriver, jamais écrit en base).
            step_nodes = [
                {
                    "step_key": (
                        json.loads(s.config_json or "{}").get("_step_key") or f"__step_{s.id}"
                    ),
                    "color": STEP_META.get(t, {}).get("color", COLORS["border"]),
                    "is_routing": is_routing_node(t),
                }
                for s, t in zip(p.steps or [], step_types)
            ]
            edge_rows = [
                {"from_step_key": e.from_step_key, "to_step_key": e.to_step_key}
                for e in (p.edges or [])
            ]

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

            # A3/A4 : une seule requête des 8 derniers runs par ligne, réutilisée pour le détail
            # d'état (le plus récent) et pour les pastilles RunHistoryDots de la colonne Étapes.
            runs8 = db.get_runs(p.id, 8)
            last_run = runs8[0] if runs8 else None
            detail_text, detail_color = _pipeline_state_detail(
                p, st, last_run, step_labels.get(p.id, ""), missed_map.get(p.id),
            )

            cells = [name_display, st, steps_str, plan, next_run]
            for c_idx, cell in enumerate(cells):
                if c_idx == 0:
                    # A2 : nom + description en dessous (cell-widget, même patron que la colonne
                    # Étapes déjà en cell-widget) — le connecteur d'arbre existant (indentation +
                    # "↳ ") est gardé tel quel, pas de ligne dessinée façon maquette.
                    name_w = QWidget()
                    name_vl = QVBoxLayout(name_w)
                    name_vl.setContentsMargins(4, 0, 4, 0)
                    name_vl.setSpacing(2)
                    name_lbl = QLabel(name_display)
                    name_lbl.setStyleSheet(
                        f"color: {name_color}; font-weight: 600; font-size: 13.5px; "
                        f"background: transparent; border: none;"
                    )
                    name_vl.addWidget(name_lbl)
                    if p.description:
                        desc_lbl = QLabel(p.description)
                        desc_lbl.setStyleSheet(
                            f"color: {COLORS['text_dim']}; font-size: 11.5px; "
                            f"background: transparent; border: none;"
                        )
                        name_vl.addWidget(desc_lbl)
                    self.table.setCellWidget(r_idx, c_idx, name_w)
                elif c_idx == 1:
                    # A3 : pastille existante (inchangée) + une ligne de détail selon l'état.
                    state_w = QWidget()
                    state_vl = QVBoxLayout(state_w)
                    state_vl.setContentsMargins(4, 0, 4, 0)
                    state_vl.setSpacing(3)
                    is_missed = p.is_active and st != "RUNNING" and p.id in missed_map
                    badge_st   = "INACTIF" if not p.is_active else st
                    if p.is_active and st == "RUNNING" and is_cancel_requested(p.id):
                        badge_st = "ARRÊT EN COURS"
                    elif is_missed:
                        badge_st = "MANQUÉ"
                    badge_name = "badge_idle" if not p.is_active else _STATUS_BADGE.get(st, "badge_idle")
                    if is_missed:
                        badge_name = "badge_missed"
                    badge = _make_status_badge(badge_st, badge_name)
                    if p.is_active and st == "RUNNING":
                        badge.setToolTip(step_labels.get(p.id, ""))
                    state_vl.addWidget(badge, 0, Qt.AlignLeft)
                    if detail_text:
                        detail_lbl = QLabel(detail_text)
                        detail_lbl.setStyleSheet(
                            f"color: {detail_color}; font-size: 11px; "
                            f"background: transparent; border: none;"
                        )
                        state_vl.addWidget(detail_lbl)
                    self.table.setCellWidget(r_idx, c_idx, state_w)
                elif c_idx == 2:
                    # Vignette de flux + résumé texte (chantier identité, vague 3, idée 8) — la
                    # vignette donne une reconnaissance visuelle immédiate, le texte reste
                    # inchangé (déjà utile en lecture).
                    steps_w = QWidget()
                    steps_hl = QHBoxLayout(steps_w)
                    steps_hl.setContentsMargins(4, 0, 4, 0)
                    steps_hl.setSpacing(8)
                    steps_hl.addWidget(PipelineStepDagThumbnail(step_nodes, edge_rows))
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
                    # A4 : pastilles des 8 derniers runs, réutilise RunHistoryDots (déjà un
                    # composant partagé de widgets.py, utilisé par Aujourd'hui).
                    dots = RunHistoryDots([_status_str(r.status) for r in reversed(runs8)])
                    steps_hl.addWidget(dots)
                    steps_hl.addStretch()
                    steps_w.setToolTip(steps_str)
                    self.table.setCellWidget(r_idx, c_idx, steps_w)
                elif c_idx == 3 and p.trigger_after_pipeline_id:
                    # A5 : la relation de déclenchement, jusqu'ici seulement en infobulle,
                    # devient une 2e ligne visible — garde aussi l'infobulle existante (inchangée)
                    # sur le widget entier. Reste un QTableWidgetItem quand il n'y a pas de
                    # déclenchement (cas très majoritaire, test_pipelines_view_schedule_display.py
                    # compare .item(0, 3).text() directement).
                    plan_w = QWidget()
                    plan_vl = QVBoxLayout(plan_w)
                    plan_vl.setContentsMargins(4, 0, 4, 0)
                    plan_vl.setSpacing(2)
                    plan_lbl = QLabel(cell)
                    plan_lbl.setStyleSheet(
                        f"color: {text_color}; background: transparent; border: none;"
                    )
                    plan_vl.addWidget(plan_lbl)
                    parent_name = p.trigger_after_pipeline.name if p.trigger_after_pipeline else "?"
                    cond_phrase = _TRIGGER_CONDITION_PHRASE.get(_status_str(p.trigger_condition), "—")
                    relation_lbl = QLabel(
                        f'<span style="color:{COLORS["relation"]}">↳ après {parent_name}</span> '
                        f"· {cond_phrase}"
                    )
                    relation_lbl.setStyleSheet(
                        f"color: {COLORS['text_dim']}; font-size: 11px; "
                        f"background: transparent; border: none;"
                    )
                    plan_vl.addWidget(relation_lbl)
                    plan_w.setToolTip(trigger_tooltip)
                    self.table.setCellWidget(r_idx, c_idx, plan_w)
                else:
                    item = QTableWidgetItem(cell)
                    item.setForeground(QColor(text_color))
                    if c_idx == 3 and trigger_tooltip:
                        item.setToolTip(trigger_tooltip)
                    self.table.setItem(r_idx, c_idx, item)

            pid       = p.id
            is_active = p.is_active
            pname     = p.name
            running = is_pipeline_running(pid)
            resumable_run = db.get_last_resumable_run(pid)

            aw  = QWidget(); al = QHBoxLayout(aw); al.setContentsMargins(4, 4, 4, 4); al.setSpacing(4)

            # A7 (DECISIONS.md::P8) : le premier bouton change selon l'état — reprendre si
            # reprenable, arrêter si en cours, lancer sinon. Un second run reste possible depuis
            # le menu "⋯" ("Exécuter depuis le début", A8) même quand une reprise est proposée ici.
            if not is_active:
                btn_run = _action_btn("fa5s.play", object_name="secondary", tooltip="Exécuter maintenant")
                btn_run.clicked.connect(lambda _, i=pid: self._on_run_pipeline(i))
            elif running:
                btn_run = _action_btn("fa5s.stop", object_name="secondary", tooltip="Interrompre")
                btn_run.clicked.connect(lambda _, i=pid, n=pname: self._on_interrupt_pipeline(i, n))
            elif resumable_run:
                btn_run = _action_btn(
                    "fa5s.history", object_name="accent_action", tooltip="Reprendre depuis l'échec",
                )
                btn_run.clicked.connect(
                    lambda _, i=pid, n=pname, r=resumable_run.id: self._on_resume_pipeline(i, n, r)
                )
            else:
                btn_run = _action_btn("fa5s.play", object_name="accent_action", tooltip="Exécuter maintenant")
                btn_run.clicked.connect(lambda _, i=pid: self._on_run_pipeline(i))

            btn_open = _action_btn(
                "fa5s.project-diagram", object_name="secondary",
                tooltip="Ouvrir l'éditeur — étapes et connexions",
            )
            btn_settings = _action_btn(
                "fa5s.cog", object_name="secondary",
                tooltip="Paramètres du pipeline — nom, planification, déclenchement, actif",
            )
            btn_more = _action_btn("fa5s.ellipsis-h", object_name="secondary", tooltip="Plus d'actions")
            btn_open.clicked.connect(lambda _, i=pid: self._on_edit_pipeline_graph(i))
            btn_settings.clicked.connect(lambda _, i=pid: self._on_edit_pipeline_settings(i))

            # A8 : menu restylé — réordonné (Interrompre/Reprendre toujours en tête si
            # applicables, puis Exécuter depuis le début/Valider, puis Dupliquer/Exporter/
            # Désactiver, puis Supprimer en dernier) et complété d'un item permanent "Exécuter
            # depuis le début" (compense A7 : le premier bouton de ligne ne lance plus un run
            # frais quand une reprise est proposée). Même patron que le bouton "+ Artefact" de
            # ui/step_editor/base_config_dialog.py, pour ne pas garder 8 boutons pleine largeur
            # par ligne dans une colonne "Actions".
            menu = QMenu(btn_more)
            if running:
                # Accessible même quand la fenêtre d'exécution a été fermée entre-temps (elle
                # continue en arrière-plan) — sans ça, aucun moyen direct d'interrompre un run
                # dont on a fermé le dialogue de suivi.
                act_interrupt = menu.addAction("Interrompre l'exécution en cours")
                act_interrupt.triggered.connect(
                    lambda _, i=pid, n=pname: self._on_interrupt_pipeline(i, n)
                )
            if resumable_run:
                act_resume = menu.addAction("Reprendre depuis l'échec")
                act_resume.triggered.connect(
                    lambda _, i=pid, n=pname, r=resumable_run.id: self._on_resume_pipeline(i, n, r)
                )
            act_run_fresh = menu.addAction("Exécuter depuis le début")
            act_run_fresh.triggered.connect(lambda _, i=pid: self._on_run_pipeline(i))
            act_validate = menu.addAction("Valider à blanc")
            act_validate.triggered.connect(lambda _, i=pid, n=pname: self._on_validate_pipeline(i, n))
            menu.addSeparator()
            act_dup = menu.addAction("Dupliquer")
            act_dup.triggered.connect(lambda _, i=pid: self._on_duplicate_pipeline(i))
            act_export = menu.addAction("Exporter…")
            act_export.triggered.connect(lambda _, i=pid: self._on_export_pipeline(i))
            if is_active:
                toggle_text = "Désactiver"
                if p.next_run_at:
                    toggle_text += f" — ne partira plus à {fmt_time_local(p.next_run_at)}"
            else:
                toggle_text = "Activer"
            act_toggle = menu.addAction(toggle_text)
            act_toggle.triggered.connect(lambda _, i=pid, a=is_active: self._on_toggle_pipeline(i, a))
            menu.addSeparator()
            act_del = menu.addAction("Supprimer…")
            act_del.triggered.connect(lambda _, i=pid: self._on_delete_pipeline(i))
            btn_more.setMenu(menu)

            al.addWidget(btn_run); al.addWidget(btn_open); al.addWidget(btn_settings)
            al.addWidget(btn_more); al.addStretch()
            self.table.setCellWidget(r_idx, 5, aw)
            self.table.setRowHeight(r_idx, 52)

        self._on_search_changed(self.inp_search.text())
        self._last_refresh_at = datetime.utcnow()
        self._refresh_footer_label()

    def _on_new_pipeline(self):
        """Un seul point d'entrée de création (chantier fusion des éditeurs — l'ancien dialogue
        lourd imposait au moins une étape avant d'enregistrer, ET toute la planification d'un
        coup, avant même d'avoir pu tester le pipeline). Juste un nom, puis directement l'Atelier
        (chantier Atelier Pipelines) — planification/déclenchement/actif restent modifiables
        ensuite via « Paramètres ». is_new_pipeline=True : voir
        AtelierPipelinesView.open_pipeline() pour la règle de suppression de la coquille vide et
        la planification au premier enregistrement, qui reproduisent à l'identique le
        if/else ci-dessous tel qu'il existait avant la fusion dans l'Atelier (git blame)."""
        name, ok = QInputDialog.getText(self, "Nouveau pipeline", "Nom du pipeline :")
        name = (name or "").strip()
        if not ok or not name:
            return

        from database import db_manager as db

        p = db.create_pipeline(name=name)
        self.open_atelier_requested.emit(p.id, None, True)

    def _on_start_from_template(self):
        """Modèle de démarrage (chantier UX éditeur, Lot 1, C1) — même mécanisme que l'import
        d'un vrai fichier .dspipeline (plan_import()/apply_import() n'exigent pas qu'un bundle
        vienne d'un vrai export), mais sans dialogue de revue : le modèle n'a ni profil ni
        collision à arbitrer (aucune référence de profil dans son bundle, nom toujours unique
        via _unique_name côté apply_import). Ouvre directement l'Atelier sur le résultat pour que
        l'utilisateur atterrisse droit sur les champs à compléter. _schedule_if_possible()
        s'exécute ICI, de façon synchrone, pas dans l'Atelier (contrairement à _on_new_pipeline
        ci-dessus) : le pipeline importé a déjà de vraies étapes (jamais une coquille à
        protéger), donc rien n'empêche de planifier tout de suite, comme avant la fusion dans
        l'Atelier — is_new_pipeline=False (défaut)."""
        from database.export_import import plan_import, apply_import
        from database.pipeline_templates import build_starter_template_bundle
        from database import db_manager as db

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
            self._schedule_if_possible(pipeline.id)
            self.open_atelier_requested.emit(pipeline.id, None, False)

    def _on_import_pipeline(self):
        from database.export_import import plan_import_from_file, apply_import
        from ui.dialogs import PipelineImportPasswordDialog, PipelineImportReviewDialog

        path, _ = QFileDialog.getOpenFileName(
            self, "Importer un pipeline", "", "Pipeline KULU (*.dspipeline)",
        )
        if not path:
            return

        plan = plan_import_from_file(path)
        password_used = False

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
            password_used = True

        if not plan.success:
            QMessageBox.critical(self, "Échec de l'import", plan.error or "Erreur inconnue.")
            return

        review_dlg = PipelineImportReviewDialog(self, plan=plan, password_used=password_used)
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

    def _on_edit_pipeline_settings(self, pipeline_id: int):
        # Chantier Atelier Pipelines : ouvre désormais l'Atelier (panneau de droite déjà
        # visible) plutôt que PipelineSettingsDialog seul — is_new_pipeline=False (défaut),
        # simple édition, jamais la règle "coquille vide"/planification au premier
        # enregistrement, qui ne concerne que _on_new_pipeline.
        self.open_atelier_requested.emit(pipeline_id, None, False)

    def _on_edit_pipeline_graph(self, pipeline_id: int):
        self.open_atelier_requested.emit(pipeline_id, None, False)

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
        """A10 : panneau latéral (remplace l'ancien PipelineDryRunDialog modal, qui reste dans
        le code — son propre test reste vert — mais devient orpheline, plus appelée d'ici)."""
        self._validation_pipeline_id = pipeline_id
        content = self._build_validation_panel_content(pipeline_name)
        self._side_panel.set_content(content)
        self._side_panel.open()
        self._run_validation(pipeline_id)

    def _build_validation_panel_content(self, pipeline_name: str) -> QWidget:
        content = QWidget()
        content.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(24, 4, 24, 20)
        layout.setSpacing(12)

        surtitle = QLabel("VALIDATION À BLANC · RIEN N'EST EXÉCUTÉ")
        surtitle.setStyleSheet(
            f"color: {COLORS['text_dim']}; font-family: {FONT_MONO_STACK}; font-size: 10px; "
            f"letter-spacing: 0.06em; background: transparent; border: none;"
        )
        layout.addWidget(surtitle)

        title = QLabel(pipeline_name)
        title.setStyleSheet(
            f"color: {COLORS['text_main']}; font-size: 17px; font-weight: 600; "
            f"background: transparent; border: none;"
        )
        layout.addWidget(title)

        intro = QLabel("Kulu vérifie la forme du graphe, les références et chaque connexion réelle.")
        intro.setWordWrap(True)
        intro.setStyleSheet(f"color: {COLORS['text_dim']}; background: transparent; border: none;")
        layout.addWidget(intro)

        self._lbl_validation_status = QLabel("Validation en cours…")
        self._lbl_validation_status.setWordWrap(True)
        self._lbl_validation_status.setStyleSheet(
            f"color: {COLORS['text_dim']}; font-size: 13px; font-weight: 600; "
            f"background: transparent; border: none;"
        )
        layout.addWidget(self._lbl_validation_status)

        counters_row = QHBoxLayout()
        counters_row.setSpacing(20)
        err_col = QVBoxLayout(); err_col.setSpacing(2)
        self._lbl_validation_errors = QLabel("—")
        self._lbl_validation_errors.setStyleSheet(
            f"color: {COLORS['text_main']}; font-size: 22px; font-weight: 700; "
            f"background: transparent; border: none;"
        )
        err_col.addWidget(self._lbl_validation_errors)
        err_label = QLabel("erreur(s)")
        err_label.setStyleSheet(f"color: {COLORS['text_dim']}; font-size: 11px; background: transparent; border: none;")
        err_col.addWidget(err_label)
        counters_row.addLayout(err_col)

        warn_col = QVBoxLayout(); warn_col.setSpacing(2)
        self._lbl_validation_warnings = QLabel("—")
        self._lbl_validation_warnings.setStyleSheet(
            f"color: {COLORS['text_main']}; font-size: 22px; font-weight: 700; "
            f"background: transparent; border: none;"
        )
        warn_col.addWidget(self._lbl_validation_warnings)
        warn_label = QLabel("avertissement(s)")
        warn_label.setStyleSheet(f"color: {COLORS['text_dim']}; font-size: 11px; background: transparent; border: none;")
        warn_col.addWidget(warn_label)
        counters_row.addLayout(warn_col)
        counters_row.addStretch()
        layout.addLayout(counters_row)

        # Liste plate des messages existants (DryRunResult.errors/.warnings) — pas de sections
        # GRAPHE/RÉFÉRENCES/CONNEXIONS RÉELLES structurées (C9, gated).
        findings_host = QWidget()
        findings_host.setStyleSheet("background: transparent;")
        self._validation_findings_layout = QVBoxLayout(findings_host)
        self._validation_findings_layout.setContentsMargins(0, 0, 0, 0)
        self._validation_findings_layout.setSpacing(8)
        self._validation_findings_layout.addStretch()
        layout.addWidget(findings_host, 1)

        footer = QHBoxLayout()
        self._btn_validation_rerun = QPushButton("Relancer la validation")
        self._btn_validation_rerun.setObjectName("secondary")
        self._btn_validation_rerun.setFixedHeight(36)
        self._btn_validation_rerun.clicked.connect(
            lambda: self._run_validation(self._validation_pipeline_id)
        )
        footer.addWidget(self._btn_validation_rerun)
        footer.addStretch()
        layout.addLayout(footer)

        return content

    def _run_validation(self, pipeline_id: int):
        from ui.dialogs.pipeline_dry_run_dialog import _DryRunThread

        self._lbl_validation_status.setText("Validation en cours…")
        self._lbl_validation_status.setStyleSheet(
            f"color: {COLORS['text_dim']}; font-size: 13px; font-weight: 600; "
            f"background: transparent; border: none;"
        )
        self._lbl_validation_errors.setText("—")
        self._lbl_validation_warnings.setText("—")
        self._clear_layout(self._validation_findings_layout)
        self._btn_validation_rerun.setEnabled(False)

        # Référence forte sur self — un objet QThread sans référence Python restante peut être
        # garbage-collecté avant la fin de son exécution, même si Qt le garde vivant côté C++
        # (même gotcha déjà documenté ailleurs dans le projet : GC Python vs parent Qt).
        self._validation_thread = _DryRunThread(pipeline_id)
        self._validation_thread.result_ready.connect(self._on_validation_result)
        # Fermeture bloquée tant que ça tourne — même garantie que l'ancien
        # PipelineDryRunDialog.closeEvent() (À garder tel quel).
        self._side_panel.set_close_guard(lambda: self._validation_thread.isRunning())
        self._validation_thread.start()

    def _on_validation_result(self, result):
        self._btn_validation_rerun.setEnabled(True)
        self._side_panel.set_close_guard(None)
        self._clear_layout(self._validation_findings_layout)

        n_errors = len(result.errors)
        n_warnings = len(result.warnings)
        self._lbl_validation_errors.setText(str(n_errors))
        self._lbl_validation_errors.setStyleSheet(
            f"color: {COLORS['danger'] if n_errors else COLORS['success']}; font-size: 22px; "
            f"font-weight: 700; background: transparent; border: none;"
        )
        self._lbl_validation_warnings.setText(str(n_warnings))
        self._lbl_validation_warnings.setStyleSheet(
            f"color: {COLORS['warning'] if n_warnings else COLORS['text_main']}; font-size: 22px; "
            f"font-weight: 700; background: transparent; border: none;"
        )

        if n_errors:
            status_text = "Validation échouée — corrigez les erreurs avant d'activer la planification."
            status_color = COLORS["danger"]
        elif n_warnings:
            status_text = (
                f"Validé avec {n_warnings} avertissement(s) "
                f"({result.checked_connections} connexion(s) vérifiée(s))."
            )
            status_color = COLORS["warning"]
        else:
            status_text = f"Aucun problème détecté ({result.checked_connections} connexion(s) vérifiée(s))."
            status_color = COLORS["success"]
        self._lbl_validation_status.setText(status_text)
        self._lbl_validation_status.setStyleSheet(
            f"color: {status_color}; font-size: 13px; font-weight: 600; "
            f"background: transparent; border: none;"
        )

        for msg in result.errors:
            lbl = QLabel(f"❌  {msg}"); lbl.setWordWrap(True)
            lbl.setStyleSheet(f"color: {COLORS['danger']}; font-size: 12px; background: transparent; border: none;")
            self._validation_findings_layout.insertWidget(self._validation_findings_layout.count() - 1, lbl)
        for msg in result.warnings:
            lbl = QLabel(f"⚠  {msg}"); lbl.setWordWrap(True)
            lbl.setStyleSheet(f"color: {COLORS['warning']}; font-size: 12px; background: transparent; border: none;")
            self._validation_findings_layout.insertWidget(self._validation_findings_layout.count() - 1, lbl)

    @staticmethod
    def _clear_layout(layout):
        while layout.count() > 1:   # garde le stretch final en dernière position
            item = layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

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
        actif est créé/modifié en dehors de PipelineSettingsDialog._on_save() (qui gère déjà son
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
        from core.execution_mode import request_cancel_run
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
        # En mode arrière-plan, request_cancel() local (core.pipeline._active_runs, en mémoire)
        # n'a aucun effet : c'est le worker détaché qui exécute réellement le pipeline, jamais
        # l'appli desktop (correctif K5, docs/refonte/LOTS.md — même idiome que _on_run_pipeline
        # ci-dessus pour l'arrêt avant relance).
        if not request_cancel_run(pipeline_id):
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

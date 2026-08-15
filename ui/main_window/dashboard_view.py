"""
DataScheduler — ui/main_window/dashboard_view.py
Vue Dashboard : état des pipelines + dernières exécutions.
"""

from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QGridLayout, QLabel, QPushButton, QFrame,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QMessageBox, QSizePolicy, QScrollArea,
)
from PySide6.QtCore import Qt, QSize, QTimer, Signal
from PySide6.QtGui import QFont, QColor
from ui.styles import COLORS
from .widgets import (
    _icon, _configure_columns, _make_empty_label, StatCard, _status_str,
    FONT_MONO, FONT_MONO_STACK, _apply_pulse, HealthRingWidget,
    _make_motif_separator, PipelineTopologyWidget, _ordered_with_chains, RunHistoryDots,
)


def _cap_topology_preview(ordered: list, max_chains: int = 6) -> list:
    """Plafonne l'aperçu du Dashboard à `max_chains` chaînes racines — chaque chaîne (racine +
    descendants) reste groupée, jamais coupée en plein milieu. Fonction pure, testable sans Qt."""
    capped = []
    chains_seen = 0
    for p, depth in ordered:
        if depth == 0:
            chains_seen += 1
            if chains_seen > max_chains:
                break
        capped.append((p, depth))
    return capped


class DashboardView(QWidget):
    navigate_to_history = Signal(str)

    def __init__(self):
        super().__init__()
        self._build_ui()
        self._timer = QTimer(self)
        self._timer.setInterval(30_000)   # 30 secondes
        self._timer.timeout.connect(self.refresh)
        self._timer.start()

    def _build_ui(self):
        # Le contenu du Dashboard a grandi (rail + bloc santé plus haut que les 4 cartes qu'il
        # remplace, chantier identité vague 2) au point de ne plus tenir dans la fenêtre sur tous
        # les écrans — sans zone de défilement, Qt compresse tout en dessous du minimum plutôt
        # que de laisser dépasser, provoquant un chevauchement visuel (repéré sur une capture
        # réelle). Le contenu passe donc dans une QScrollArea ; `layout` reste le layout du
        # contenu interne, tout le reste de cette méthode est inchangé.
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("background: transparent;")
        content = QWidget()
        scroll.setWidget(content)
        outer.addWidget(scroll)

        layout = QVBoxLayout(content)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(24)

        header = QWidget()
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(0, 0, 0, 0)
        title = QLabel("Dashboard"); title.setObjectName("section_title")
        sub   = QLabel("Vue d'ensemble des pipelines"); sub.setObjectName("subtitle")
        title_col = QVBoxLayout(); title_col.setSpacing(2)
        title_col.addWidget(title); title_col.addWidget(sub)
        h_layout.addLayout(title_col); h_layout.addStretch()
        btn_notifications = QPushButton("  Notifications"); btn_notifications.setObjectName("secondary")
        btn_notifications.setFixedHeight(36)
        btn_notifications.setIcon(_icon("fa5s.bell", COLORS["text_main"]))
        btn_notifications.setIconSize(QSize(13, 13))
        btn_notifications.clicked.connect(self._on_notifications)
        h_layout.addWidget(btn_notifications)
        btn_run_all = QPushButton("  Tout exécuter"); btn_run_all.setObjectName("secondary")
        btn_run_all.setFixedHeight(36)
        btn_run_all.setIcon(_icon("fa5s.bolt", COLORS["text_main"])); btn_run_all.setIconSize(QSize(14, 14))
        btn_run_all.clicked.connect(self._on_run_all)
        h_layout.addWidget(btn_run_all)
        layout.addWidget(header)

        self._onboarding_banner = QLabel(
            "Bienvenue — commencez par créer vos connexions (Connexions), puis vos requêtes SQL "
            "si besoin (Requêtes SQL), avant de créer votre premier pipeline (Pipelines). "
            "Consultez la section Aide pour un guide pas à pas."
        )
        self._onboarding_banner.setWordWrap(True)
        self._onboarding_banner.setStyleSheet(
            f"color: {COLORS['text_main']}; font-size: 12px; background: {COLORS['bg_panel']}; "
            f"border: 1px solid {COLORS['border']}; border-left: 3px solid {COLORS['accent']}; "
            f"border-radius: 6px; padding: 12px 16px;"
        )
        self._onboarding_banner.setVisible(False)
        layout.addWidget(self._onboarding_banner)

        # Rail "Prochaines & en cours" — remplace la carte isolée "Prochaine exéc." : les
        # pipelines sont planifiés, ce qui tourne/va tourner mérite d'être vu en premier plutôt
        # que noyé dans une case au même rang que les autres (chantier identité, vague 1).
        self._rail = QWidget()
        self._rail_layout = QHBoxLayout(self._rail)
        self._rail_layout.setContentsMargins(0, 0, 0, 0)
        self._rail_layout.setSpacing(10)
        layout.addWidget(self._rail)

        # Bloc santé asymétrique — casse la grille de cartes identiques (chantier identité,
        # vague 2, idée 4) : un anneau de santé (hero) + une grille compacte de stats
        # secondaires, au lieu de N rectangles de même poids visuel.
        health_row = QHBoxLayout(); health_row.setSpacing(16)

        hero = QFrame(); hero.setObjectName("card")
        hero.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        hero_layout = QHBoxLayout(hero)
        hero_layout.setContentsMargins(20, 16, 26, 16)
        hero_layout.setSpacing(18)
        self._health_ring = HealthRingWidget()
        hero_layout.addWidget(self._health_ring)

        hero_text_col = QVBoxLayout(); hero_text_col.setSpacing(6)
        hero_title = QLabel("Santé des pipelines")
        hero_title.setStyleSheet(
            f"color: {COLORS['text_main']}; font-size: 13px; font-weight: 700; "
            f"background: transparent; border: none;"
        )
        hero_text_col.addWidget(hero_title)
        self._lbl_health_success = self._make_legend_line(COLORS["success"])
        self._lbl_health_danger = self._make_legend_line(COLORS["danger"])
        self._lbl_health_idle = self._make_legend_line(COLORS["text_muted"])
        hero_text_col.addWidget(self._lbl_health_success)
        hero_text_col.addWidget(self._lbl_health_danger)
        hero_text_col.addWidget(self._lbl_health_idle)
        hero_layout.addLayout(hero_text_col)
        # Centre le bloc de texte verticalement à côté de l'anneau (taille fixe, donc déjà
        # centré par défaut par le QHBoxLayout) — sans ça, `hero_text_col` s'accroche en haut et
        # laisse un vide en bas, désalignant visuellement les deux colonnes (repéré sur une
        # capture réelle une fois la carte agrandie pour s'aligner sur la grille secondaire).
        hero_layout.setAlignment(hero_text_col, Qt.AlignVCenter)
        health_row.addWidget(hero)

        secondary_grid = QGridLayout()
        secondary_grid.setContentsMargins(0, 0, 0, 0)
        secondary_grid.setSpacing(10)
        self._card_success = StatCard("Succès (30j)", "—", "exécutions", COLORS["success"],
                                       clickable=True, border_accent=COLORS["success"])
        self._card_failed  = StatCard("Échecs (30j)", "—", "exécutions", COLORS["danger"],
                                       clickable=True, border_accent=COLORS["danger"])
        self._card_active  = StatCard("Pipelines actifs", "—", "configurés")
        self._card_avg_duration = StatCard("Durée moy.", "—", "30 derniers jours")
        self._card_success.setToolTip("Voir les exécutions réussies dans l'Historique")
        self._card_failed.setToolTip("Voir les échecs dans l'Historique")
        self._card_success.clicked.connect(lambda: self.navigate_to_history.emit("SUCCESS"))
        self._card_failed.clicked.connect(lambda: self.navigate_to_history.emit("FAILED"))
        secondary_grid.addWidget(self._card_success, 0, 0)
        secondary_grid.addWidget(self._card_failed, 0, 1)
        secondary_grid.addWidget(self._card_active, 1, 0)
        secondary_grid.addWidget(self._card_avg_duration, 1, 1)
        secondary_wrap = QWidget(); secondary_wrap.setLayout(secondary_grid)
        health_row.addWidget(secondary_wrap, stretch=1)

        layout.addLayout(health_row)

        layout.addWidget(_make_motif_separator())

        # Mini-topologie — remplace le graphique d'activité en barres sur cette vue (décision
        # confirmée avec l'utilisateur, suit la maquette validée ; le graphique lui-même reste
        # utilisé tel quel dans PipelineDetailDialog, chantier identité, vague 3, idée 5).
        topo_hd = QWidget()
        topo_hd_layout = QHBoxLayout(topo_hd)
        topo_hd_layout.setContentsMargins(0, 0, 0, 0)
        lbl_topo = QLabel("Vue d'ensemble des pipelines")
        lbl_topo.setStyleSheet(f"font-size: 15px; font-weight: 600; color: {COLORS['text_main']};")
        topo_hd_layout.addWidget(lbl_topo)
        topo_hd_layout.addStretch()
        # Lien "voir plus" — l'aperçu du Dashboard est plafonné (voir refresh()), ce lien ouvre
        # le dialogue dédié qui montre tous les pipelines, sans plafond, dans le même style.
        self._btn_see_all_topology = QPushButton("Voir tous les pipelines →")
        self._btn_see_all_topology.setObjectName("secondary")
        self._btn_see_all_topology.setFixedHeight(28)
        self._btn_see_all_topology.setVisible(False)
        self._btn_see_all_topology.clicked.connect(self._on_open_topology_dialog)
        topo_hd_layout.addWidget(self._btn_see_all_topology)
        layout.addWidget(topo_hd)

        # Carte englobante (fond + bordure fine) — la zone de la mini-topologie doit être
        # délimitée comme la maquette, les nœuds ressortant nettement plus sombres à l'intérieur
        # (voir PipelineTopologyWidget.paintEvent, fond bg_main) plutôt que de flotter sur le
        # fond de la page. Fond bg_panel en dur plutôt que la classe globale "card" (bg_card) :
        # bg_card/bg_main étaient trop proches pour un contraste net une fois rendus (repéré en
        # comparant à la maquette validée).
        topo_card = QFrame()
        topo_card.setStyleSheet(
            f"QFrame {{ background-color: {COLORS['bg_panel']}; "
            f"border: 1px solid {COLORS['border']}; border-radius: 6px; }}"
        )
        topo_card_layout = QVBoxLayout(topo_card)
        topo_card_layout.setContentsMargins(20, 18, 20, 18)
        self._topology = PipelineTopologyWidget()
        topo_card_layout.addWidget(self._topology)
        layout.addWidget(topo_card)

        layout.addWidget(_make_motif_separator())

        lbl_recent = QLabel("Dernières exécutions")
        lbl_recent.setStyleSheet(f"font-size: 15px; font-weight: 600; color: {COLORS['text_main']};")
        layout.addWidget(lbl_recent)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["Pipeline", "Historique", "Lignes", "Durée", "Date", "Fichier déposé"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        _configure_columns(self.table, stretch_cols={0, 5})
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Fixed)
        self.table.setColumnWidth(1, 130)
        self.table.setAlternatingRowColors(False)
        self.table.setShowGrid(False)
        self.table.setFixedHeight(200)
        layout.addWidget(self.table)

        self._empty_label = _make_empty_label(
            "Aucune exécution pour l'instant — les runs planifiés ou manuels apparaîtront ici."
        )
        self._empty_label.setFixedHeight(200)
        self._empty_label.setVisible(False)
        layout.addWidget(self._empty_label)

        self.refresh()

    def _make_legend_line(self, color: str) -> QLabel:
        lbl = QLabel()
        lbl.setStyleSheet(
            f"font-size: 11.5px; color: {COLORS['text_dim']}; background: transparent; border: none;"
        )
        lbl.setProperty("_dot_color", color)
        return lbl

    def _set_legend_text(self, lbl: QLabel, text: str):
        color = lbl.property("_dot_color")
        lbl.setText(f'<span style="color:{color};">●</span>&nbsp;{text}')

    def refresh(self):
        from database import db_manager as db
        from datetime import datetime, timedelta, timezone

        pipelines = db.get_pipelines()
        self._card_active.set_value(str(len(pipelines)))
        self._onboarding_banner.setVisible(not pipelines)

        cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=30)
        all_runs = db.get_recent_runs(limit=500)
        recent = [r for r in all_runs if r.started_at and r.started_at >= cutoff]
        self._card_success.set_value(str(sum(1 for r in recent if _status_str(r.status) == "SUCCESS")))
        self._card_failed.set_value(str(sum(1 for r in recent if _status_str(r.status) == "FAILED")))

        durations = [r.duration_seconds for r in recent if r.duration_seconds is not None]
        if durations:
            avg_s = sum(durations) / len(durations)
            m, s = divmod(int(avg_s), 60)
            self._card_avg_duration.set_value(f"{m}m {s:02d}s")
        else:
            self._card_avg_duration.set_value("—")

        # Anneau de santé — dernier statut connu par pipeline actif, pas un agrégat de runs
        # (voir HealthRingWidget : un pipeline jamais exécuté n'est ni sain ni en échec).
        active_pipelines = [p for p in pipelines if p.is_active]
        healthy = [p for p in active_pipelines if _status_str(p.last_status) == "SUCCESS"]
        unhealthy = [p for p in active_pipelines if _status_str(p.last_status) == "FAILED"]
        self._health_ring.set_data(len(healthy), len(unhealthy))
        self._set_legend_text(
            self._lbl_health_success,
            f"{len(healthy)} en succès sur leur dernière exécution",
        )
        if len(unhealthy) == 1:
            danger_text = f"1 en échec — {unhealthy[0].name}"
        else:
            danger_text = f"{len(unhealthy)} en échec" + ("s" if len(unhealthy) > 1 else "")
        self._set_legend_text(self._lbl_health_danger, danger_text)

        # Complète l'anneau (qui ne compte volontairement que succès/échec) plutôt que de laisser
        # ces pipelines invisibles — remplit aussi l'espace du bloc santé avec une information
        # réelle plutôt qu'un vide décoratif.
        never_run = len(active_pipelines) - len(healthy) - len(unhealthy)
        idle_text = (
            f"{never_run} jamais exécuté{'s' if never_run > 1 else ''}"
            if never_run else "Tous les pipelines actifs ont déjà été exécutés"
        )
        self._set_legend_text(self._lbl_health_idle, idle_text)

        # Aperçu plafonné (voir _cap_topology_preview) — sans plafond, le widget grandirait sans
        # limite avec beaucoup de pipelines. Le lien "voir plus" ouvre le dialogue dédié, non
        # plafonné, pour la liste complète.
        topo_ordered = _ordered_with_chains(pipelines)
        topo_capped = _cap_topology_preview(topo_ordered, max_chains=6)
        self._topology.set_data(topo_capped)
        hidden_count = len(topo_ordered) - len(topo_capped)
        if hidden_count > 0:
            self._btn_see_all_topology.setText(f"Voir tous les pipelines ({len(topo_ordered)}) →")
            self._btn_see_all_topology.setVisible(True)
        else:
            self._btn_see_all_topology.setVisible(False)

        self._refresh_rail(pipelines, all_runs)

        recent_runs = db.get_recent_runs(limit=100)
        runs_by_pipeline = {}
        for run in recent_runs:
            runs_by_pipeline.setdefault(run.pipeline_id, []).append(run)
        pipeline_order = list(runs_by_pipeline.keys())

        self.table.setVisible(bool(pipeline_order))
        self._empty_label.setVisible(not pipeline_order)
        self.table.setRowCount(len(pipeline_order))
        for r_idx, pid in enumerate(pipeline_order):
            runs = runs_by_pipeline[pid]
            run = runs[0]
            history = [_status_str(r.status) for r in runs[:8]][::-1]
            pname = run.pipeline.name if run.pipeline else str(run.pipeline_id)
            st    = _status_str(run.status)
            dur   = "—"
            if run.duration_seconds is not None:
                m, s = divmod(int(run.duration_seconds), 60)
                dur  = f"{m}m {s:02d}s"
            date_s = run.started_at.strftime("%d/%m/%Y %H:%M") if run.started_at else "—"
            rows_s = f"{run.rows_exported:,}".replace(",", " ") if run.rows_exported else "—"
            cells  = [pname, None, rows_s, dur, date_s, run.remote_path or "—"]
            for c_idx, cell in enumerate(cells):
                if c_idx == 1:
                    dots = RunHistoryDots(history)
                    dots.setToolTip(f"{len(runs)} dernière(s) exécution(s)")
                    self.table.setCellWidget(r_idx, c_idx, dots)
                else:
                    item = QTableWidgetItem(cell)
                    # Le nom du pipeline ressort en rouge sur un échec de la derniere execution
                    # -- pas seulement la pastille -- pour reperer un echec en un coup d'oeil en
                    # parcourant la liste, avec le message d'erreur en infobulle pour un premier
                    # diagnostic sans ouvrir l'historique complet.
                    if c_idx == 0 and st == "FAILED":
                        item.setForeground(QColor(COLORS["danger"]))
                        font = item.font(); font.setBold(True); item.setFont(font)
                        if run.error_message:
                            item.setToolTip(run.error_message)
                    else:
                        item.setForeground(QColor(COLORS["text_dim"] if c_idx == 5 else COLORS["text_main"]))
                        if c_idx == 5:
                            item.setFont(QFont(FONT_MONO, 11))
                    self.table.setItem(r_idx, c_idx, item)
            self.table.setRowHeight(r_idx, 44)

    def _refresh_rail(self, pipelines, all_runs):
        """Rail "Prochaines & en cours" — voir _build_ui(). Reconstruit à chaque refresh() (comme
        le tableau des dernières exécutions), le nombre/type de chips changeant dynamiquement."""
        from datetime import datetime, timezone

        from core.pipeline import is_pipeline_running

        while self._rail_layout.count():
            item = self._rail_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        running_ids = {p.id for p in pipelines if p.is_active and is_pipeline_running(p.id)}
        chips = []
        for p in pipelines:
            if p.id not in running_ids:
                continue
            started_at = next(
                (r.started_at for r in all_runs if r.pipeline_id == p.id and r.started_at), None
            )
            elapsed = ""
            if started_at:
                secs = int((datetime.now(timezone.utc).replace(tzinfo=None) - started_at).total_seconds())
                m, s = divmod(max(secs, 0), 60)
                elapsed = f" · {m}m {s:02d}s"
            chips.append(self._make_rail_chip(
                running=True, dot_color=COLORS["signal"],
                main_text=p.name, main_mono=False, sub_text=f"en cours{elapsed}",
            ))

        upcoming = sorted(
            (p for p in pipelines if p.is_active and p.next_run_at and p.id not in running_ids),
            key=lambda p: p.next_run_at,
        )[:3]
        for p in upcoming:
            chips.append(self._make_rail_chip(
                running=False, dot_color=COLORS["text_muted"],
                main_text=p.next_run_at.strftime("%d/%m %H:%M"), main_mono=True, sub_text=p.name,
            ))

        if not chips:
            placeholder = QLabel("Aucune exécution en cours ni planifiée pour l'instant.")
            placeholder.setStyleSheet(
                f"color: {COLORS['text_muted']}; font-size: 11.5px; font-style: italic;"
            )
            self._rail_layout.addWidget(placeholder)
        else:
            for chip in chips:
                self._rail_layout.addWidget(chip)
            self._rail_layout.addStretch()

    def _make_rail_chip(self, *, running: bool, dot_color: str, main_text: str,
                         main_mono: bool, sub_text: str) -> QFrame:
        chip = QFrame()
        chip.setFixedHeight(30)   # hauteur fixe indispensable : border-radius ne forme une
                                  # vraie pilule que si le rayon (15px) vaut la moitié exacte
                                  # d'une hauteur connue à l'avance — sinon Qt rend des coins à
                                  # peine arrondis plutôt qu'un contour pleinement incurvé.
        border = COLORS["signal_dim"] if running else COLORS["border"]
        bg = "rgba(62,143,176,0.08)" if running else COLORS["bg_card"]
        chip.setStyleSheet(
            f"QFrame {{ background: {bg}; border: 1px solid {border}; border-radius: 15px; }}"
        )
        hl = QHBoxLayout(chip)
        hl.setContentsMargins(12, 0, 14, 0)
        hl.setSpacing(8)

        dot = QLabel("●")
        dot.setStyleSheet(f"color: {dot_color}; font-size: 9px; background: transparent; border: none;")
        hl.addWidget(dot)
        if running:
            _apply_pulse(dot)

        font_css = f"font-family: {FONT_MONO_STACK};" if main_mono else ""
        color = COLORS["signal_pale"] if running else COLORS["text_dim"]
        weight = 700 if running else 600
        main_lbl = QLabel(main_text)
        main_lbl.setStyleSheet(
            f"color: {color}; font-size: 12px; font-weight: {weight}; {font_css} "
            f"background: transparent; border: none;"
        )
        hl.addWidget(main_lbl)

        sub_lbl = QLabel(sub_text)
        sub_lbl.setStyleSheet(
            f"color: {COLORS['text_muted']}; font-size: 10.5px; background: transparent; border: none;"
        )
        hl.addWidget(sub_lbl)
        return chip

    def _on_notifications(self):
        from ui.dialogs import NotificationSettingsDialog
        NotificationSettingsDialog(self).exec()

    def _on_open_topology_dialog(self):
        from database import db_manager as db
        from ui.dialogs import PipelineTopologyDialog
        PipelineTopologyDialog(self, db.get_pipelines()).exec()

    def _on_run_all(self):
        try:
            from core.scheduler import get_scheduler
            from database import db_manager as db
            pipelines = db.get_pipelines(active_only=True)
            if not pipelines:
                QMessageBox.information(self, "Tout exécuter", "Aucun pipeline actif à lancer.")
                return
            reply = QMessageBox.question(
                self, "Tout exécuter",
                f"Lancer {len(pipelines)} pipeline(s) actif(s) maintenant ?",
                QMessageBox.Yes | QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return
            sched = get_scheduler()
            for p in pipelines:
                sched.trigger_now(p.id)
            QMessageBox.information(
                self, "Tout exécuter",
                f"{len(pipelines)} pipeline(s) lancé(s) en arrière-plan."
            )
        except RuntimeError:
            QMessageBox.warning(self, "Scheduler", "Le scheduler n'est pas encore démarré.")

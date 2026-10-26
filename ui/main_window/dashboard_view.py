"""
DataScheduler — ui/main_window/dashboard_view.py
Vue Dashboard : état des pipelines + dernières exécutions.
"""

from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QGridLayout, QLabel, QPushButton, QFrame,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QMessageBox, QSizePolicy, QScrollArea, QStackedLayout, QProgressBar, QPlainTextEdit,
)
from PySide6.QtCore import Qt, QSize, QTimer, Signal
from PySide6.QtGui import QFont, QColor
from ui.styles import COLORS
from ui.time_display import fmt_datetime, fmt_datetime_local, fmt_time, fmt_time_local, to_display
from ui.components import make_page_header, SidePanel
from .widgets import (
    _icon, _configure_columns, _make_empty_label, StatCard, _status_str,
    FONT_MONO, FONT_MONO_STACK, _apply_pulse, HealthRingWidget,
    _make_motif_separator, PipelineTopologyWidget, _ordered_with_chains, RunHistoryDots,
)

# Jours/mois en français écrits en dur (A1) : pas de dépendance à la locale système, qui peut
# rester en anglais sur un poste Windows même francophone, surtout une fois packagé (PyInstaller).
_DAYS_FR = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
_MONTHS_FR = [
    "janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août",
    "septembre", "octobre", "novembre", "décembre",
]


def _today_eyebrow() -> str:
    """« DIMANCHE 18 OCTOBRE · 14:05 » — heure courante dans le fuseau réglé (A1)."""
    from datetime import datetime
    now_local = to_display(datetime.utcnow())
    day = _DAYS_FR[now_local.weekday()].upper()
    month = _MONTHS_FR[now_local.month - 1].upper()
    return f"{day} {now_local.day} {month} · {now_local.strftime('%H:%M')}"


def _step_key_of(step) -> str | None:
    """`_step_key` stable assigné par l'Atelier, stocké dans `config_json` (pas une colonne de
    `PipelineStep`) — même lecture que core/pipeline.py (`config.get("_step_key")`)."""
    import json
    try:
        config = json.loads(step.config_json or "{}")
    except (TypeError, ValueError):
        return None
    return config.get("_step_key")


def _resolve_step_label(pipeline, step_key: str | None) -> str | None:
    """Étape fautive -> libellé lisible (A4) : `failed_step_key` ne correspond à aucune colonne
    affichable directement, seulement au `_step_key` interne d'une étape — même repli que
    core/pipeline.py (`step.label or step_type`) si l'étape n'a pas de libellé personnalisé."""
    if not step_key:
        return None
    for step in pipeline.steps:
        if _step_key_of(step) == step_key:
            step_type = str(step.step_type).replace("StepType.", "")
            return step.label or step_type
    return None


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
    navigate_to_settings = Signal(str)
    # A1 : "+ Nouveau pipeline" — même patron que PipelinesView.open_atelier_requested, câblé
    # dans window.py vers PipelinesView._on_new_pipeline (seul point d'entrée de création).
    new_pipeline_requested = Signal()
    # A9 : "Ouvrir dans l'Atelier" depuis le panneau latéral d'une exécution en échec — même
    # signature que PipelinesView.open_atelier_requested, câblé dans window.py vers
    # MainWindow.open_atelier (point d'entrée unique déjà utilisé par Pipelines/Historique).
    open_atelier_requested = Signal(int, object, bool)
    # A12 (Aujourdhui-premier) : les 3 cartes/2 liens de l'accueil "premier pipeline" ne
    # dupliquent aucune logique — ils naviguent vers une vue existante ou appellent une méthode
    # déjà publique-par-l'usage de PipelinesView (même patron que new_pipeline_requested
    # ci-dessus, déjà câblé vers une méthode privée de PipelinesView).
    open_connections_requested = Signal()
    open_sql_editor_requested = Signal()
    start_from_template_requested = Signal()
    import_pipeline_requested = Signal()
    open_help_requested = Signal()

    def __init__(self):
        super().__init__()
        self._build_ui()
        from database import db_manager as db
        self._timer = QTimer(self)
        self._timer.setInterval(db.get_app_settings().dashboard_refresh_s * 1000)
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
        # Scopé à QScrollArea (pas une règle nue) : une règle nue se propage à tous les
        # descendants et écrasait silencieusement le fond orange plein par défaut de tout
        # QPushButton sans objectName à l'intérieur (ex. "+ Nouveau pipeline" — bug réel
        # constaté en capture, REGLES.md section 3).
        scroll.setStyleSheet("QScrollArea { background: transparent; }")
        content = QWidget()
        scroll.setWidget(content)
        outer.addWidget(scroll)

        layout = QVBoxLayout(content)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(24)

        # A1 : cloche icône seule (la pastille de notifications non lues est hors périmètre —
        # aucun centre de notifications n'existe), "Tout exécuter" en secondaire, "+ Nouveau
        # pipeline" en principal (nouveau signal, voir new_pipeline_requested).
        btn_notifications = QPushButton(); btn_notifications.setObjectName("secondary")
        btn_notifications.setFixedSize(36, 36)
        btn_notifications.setIcon(_icon("fa5s.bell", COLORS["text_main"]))
        btn_notifications.setIconSize(QSize(14, 14))
        btn_notifications.setToolTip("Notifications")
        btn_notifications.clicked.connect(self._on_notifications)

        btn_run_all = QPushButton("  Tout exécuter"); btn_run_all.setObjectName("secondary")
        btn_run_all.setFixedHeight(36)
        btn_run_all.setIcon(_icon("fa5s.bolt", COLORS["text_main"])); btn_run_all.setIconSize(QSize(14, 14))
        btn_run_all.clicked.connect(self._on_run_all)

        self._btn_new_pipeline = btn_new_pipeline = QPushButton("  Nouveau pipeline")
        btn_new_pipeline.setFixedHeight(36)
        btn_new_pipeline.setIcon(_icon("fa5s.plus", "#000000")); btn_new_pipeline.setIconSize(QSize(13, 13))
        btn_new_pipeline.clicked.connect(self.new_pipeline_requested.emit)

        header = make_page_header(
            _today_eyebrow(), "Aujourd'hui",
            actions=[btn_notifications, btn_run_all, btn_new_pipeline],
        )
        # make_page_header() ne renvoie pas de référence à son surtitre — recherché une fois ici
        # par objectName (fiable : un seul en-tête de page dans cette vue) pour le tenir à jour
        # dans refresh() (sinon l'heure affichée resterait figée à la construction de la vue).
        self._eyebrow_lbl = header.findChild(QLabel, "page_eyebrow")
        layout.addWidget(header)

        # A12 (Aujourdhui-premier, maquette html/Aujourdhui-premier.html) : remplace l'ancienne
        # phrase unique par 3 cartes de parcours + 2 liens. Garde le nom d'attribut
        # `_onboarding_banner` (À garder tel quel, test_onboarding_empty_states.py) même si son
        # contenu change entièrement — refresh() continue de faire .setVisible(not pipelines)
        # sans aucun changement.
        self._onboarding_banner = self._build_onboarding_block()
        layout.addWidget(self._onboarding_banner)

        # Rail "Prochaines & en cours" — remplace la carte isolée "Prochaine exéc." : les
        # pipelines sont planifiés, ce qui tourne/va tourner mérite d'être vu en premier plutôt
        # que noyé dans une case au même rang que les autres (chantier identité, vague 1).
        self._rail = QWidget()
        self._rail_layout = QHBoxLayout(self._rail)
        self._rail_layout.setContentsMargins(0, 0, 0, 0)
        self._rail_layout.setSpacing(10)
        layout.addWidget(self._rail)

        # Corps en 2 colonnes (A3-A8) : une colonne étroite à gauche ("À traiter" + santé), une
        # large à droite (bloc à onglets) — pas un simple empilement comme avant ce lot
        # (Aujourdhui.html). La ligne du temps "journée des pipelines" qui s'intercalerait en
        # haut de la colonne de droite est C4, gated : la colonne de droite démarre directement
        # sur le bloc à onglets, sans réserver de place vide pour elle (REGLES.md section 2).
        body = QHBoxLayout(); body.setSpacing(20)

        left_col = QVBoxLayout(); left_col.setSpacing(20)
        left_wrap = QWidget(); left_wrap.setLayout(left_col)
        left_wrap.setFixedWidth(370)
        left_col.addWidget(self._build_treat_column())
        left_col.addWidget(self._build_health_block())
        body.addWidget(left_wrap)

        body.addWidget(self._build_tabs_block(), stretch=1)

        layout.addLayout(body, stretch=1)

        # Panneau latéral (A9/A10) : un seul SidePanel réutilisé, son contenu remplacé selon ce
        # qui l'a ouvert (carte ÉCHEC -> A9, puce MAINTENANT -> A10) — voir _open_failure_panel/
        # _open_running_panel. Attaché à `self` (toute la vue), pas à une sous-colonne, pour
        # glisser sur toute la hauteur/largeur disponible.
        self._side_panel = SidePanel(self)

        self.refresh()

    # ── A3 + A4 : colonne "À traiter" ──────────────

    def _build_treat_column(self) -> QWidget:
        col = QWidget()
        col_layout = QVBoxLayout(col)
        col_layout.setContentsMargins(0, 0, 0, 0)
        col_layout.setSpacing(10)

        head = QHBoxLayout(); head.setSpacing(8)
        title = QLabel("À traiter")
        title.setStyleSheet(f"font-size: 15px; font-weight: 600; color: {COLORS['text_main']};")
        head.addWidget(title)
        subtitle = QLabel("du plus urgent au moins urgent")
        subtitle.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 11px;")
        head.addWidget(subtitle)
        head.addStretch()
        col_layout.addLayout(head)

        # Mini-barre groupée (décision utilisateur, question ouverte 6 de la fiche — pas de
        # recommandation écrite) : visible seulement si ≥ 2 cartes MANQUÉE, réutilise les
        # actions groupées existantes telles quelles.
        self._missed_bulk_bar = QWidget()
        bulk_layout = QHBoxLayout(self._missed_bulk_bar)
        bulk_layout.setContentsMargins(0, 0, 0, 0)
        bulk_layout.setSpacing(6)
        self._lbl_missed_bulk = QLabel("")
        self._lbl_missed_bulk.setStyleSheet(
            f"color: {COLORS['text_muted']}; font-size: 11px; background: transparent; border: none;"
        )
        bulk_layout.addWidget(self._lbl_missed_bulk)
        bulk_layout.addStretch()
        btn_bulk_launch = self._link_button("Lancer tout", COLORS["accent"])
        btn_bulk_launch.clicked.connect(self._on_missed_launch_all)
        bulk_layout.addWidget(btn_bulk_launch)
        btn_bulk_ignore = self._link_button("Ignorer tout", COLORS["text_muted"])
        btn_bulk_ignore.clicked.connect(self._on_missed_ignore_all)
        bulk_layout.addWidget(btn_bulk_ignore)
        self._missed_bulk_bar.setVisible(False)
        col_layout.addWidget(self._missed_bulk_bar)

        self._treat_cards = QWidget()
        self._treat_cards_layout = QVBoxLayout(self._treat_cards)
        self._treat_cards_layout.setContentsMargins(0, 0, 0, 0)
        self._treat_cards_layout.setSpacing(10)
        col_layout.addWidget(self._treat_cards)

        self._treat_empty = QLabel("Rien à traiter pour l'instant.")
        self._treat_empty.setStyleSheet(
            f"color: {COLORS['text_muted']}; font-size: 12px; font-style: italic; "
            f"background: transparent; border: none;"
        )
        self._treat_empty.setVisible(False)
        col_layout.addWidget(self._treat_empty)

        return col

    # ── A5 + A6 : bloc santé ────────────────────────

    def _build_health_block(self) -> QWidget:
        """Anneau + légende au-dessus d'une rangée de 4 StatCard — empilés, pas côte à côte
        comme l'ancienne disposition (Aujourdhui.html : les deux blocs partagent la colonne
        étroite de gauche avec "À traiter", pas toute la largeur de la page)."""
        wrap = QWidget()
        wrap_layout = QVBoxLayout(wrap)
        wrap_layout.setContentsMargins(0, 0, 0, 0)
        wrap_layout.setSpacing(12)

        hero = QFrame(); hero.setObjectName("card")
        hero_layout = QHBoxLayout(hero)
        hero_layout.setContentsMargins(20, 16, 20, 16)
        hero_layout.setSpacing(16)
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
        hero_layout.addLayout(hero_text_col, stretch=1)
        hero_layout.setAlignment(hero_text_col, Qt.AlignVCenter)
        wrap_layout.addWidget(hero)

        # padding_h réduit (20px par défaut -> 10px) : 4 cartes sur une seule rangée dans la
        # colonne étroite de gauche (360px) laissent trop peu de place pour "SUCCÈS (30J)" avec
        # les marges par défaut (texte rogné, constaté à l'écran) — StatCard garde son padding
        # par défaut partout ailleurs, ce lot ne change que ces 4 instances.
        stats_row = QHBoxLayout(); stats_row.setSpacing(8)
        self._card_success = StatCard("Succès (30j)", "—", "exécutions", COLORS["success"],
                                       clickable=True, border_accent=COLORS["success"],
                                       value_font_size=20, padding_h=10)
        self._card_failed  = StatCard("Échecs (30j)", "—", "exécutions", COLORS["danger"],
                                       clickable=True, border_accent=COLORS["danger"],
                                       value_font_size=20, padding_h=10)
        self._card_active  = StatCard("Pipelines actifs", "—", "configurés",
                                       value_font_size=20, padding_h=10)
        self._card_avg_duration = StatCard("Durée moy.", "—", "30 derniers jours",
                                            value_font_size=20, padding_h=10)
        self._card_success.setToolTip("Voir les exécutions réussies dans l'Historique")
        self._card_failed.setToolTip("Voir les échecs dans l'Historique")
        self._card_success.clicked.connect(lambda: self.navigate_to_history.emit("SUCCESS"))
        self._card_failed.clicked.connect(lambda: self.navigate_to_history.emit("FAILED"))
        for card in (self._card_success, self._card_failed, self._card_active, self._card_avg_duration):
            stats_row.addWidget(card)
        wrap_layout.addLayout(stats_row)

        return wrap

    # ── A7 + A8 : bloc à onglets ────────────────────

    def _build_tabs_block(self) -> QWidget:
        wrap = QWidget()
        wrap_layout = QVBoxLayout(wrap)
        wrap_layout.setContentsMargins(0, 0, 0, 0)
        wrap_layout.setSpacing(10)

        tabs_head = QHBoxLayout(); tabs_head.setSpacing(18)
        self._tab_btn_runs = self._make_tab_button("Dernières exécutions")
        self._tab_btn_runs.clicked.connect(lambda: self._set_active_tab(0))
        tabs_head.addWidget(self._tab_btn_runs)
        self._tab_btn_deps = self._make_tab_button("Dépendances entre pipelines")
        self._tab_btn_deps.clicked.connect(lambda: self._set_active_tab(1))
        tabs_head.addWidget(self._tab_btn_deps)
        tabs_head.addStretch()
        btn_all_history = self._link_button("Tout l'historique →", COLORS["accent"])
        btn_all_history.clicked.connect(lambda: self.navigate_to_history.emit(""))
        tabs_head.addWidget(btn_all_history)
        wrap_layout.addLayout(tabs_head)

        self._tabs_stack = QStackedLayout()
        stack_host = QWidget()
        stack_host.setLayout(self._tabs_stack)

        runs_page = QWidget()
        runs_layout = QVBoxLayout(runs_page)
        runs_layout.setContentsMargins(0, 0, 0, 0)
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["Pipeline", "8 dernières", "Lignes", "Durée", "Date", "Fichier déposé"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        _configure_columns(self.table, stretch_cols={0, 5})
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Fixed)
        self.table.setColumnWidth(1, 130)
        self.table.setAlternatingRowColors(False)
        self.table.setShowGrid(False)
        runs_layout.addWidget(self.table)
        self._empty_label = _make_empty_label(
            "Aucune exécution pour l'instant — les runs planifiés ou manuels apparaîtront ici."
        )
        self._empty_label.setVisible(False)
        runs_layout.addWidget(self._empty_label)
        self._tabs_stack.addWidget(runs_page)

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
        self._btn_see_all_topology = QPushButton("Voir tous les pipelines →")
        self._btn_see_all_topology.setObjectName("secondary")
        self._btn_see_all_topology.setFixedHeight(28)
        self._btn_see_all_topology.setVisible(False)
        self._btn_see_all_topology.clicked.connect(self._on_open_topology_dialog)
        topo_card_layout.addWidget(self._btn_see_all_topology, alignment=Qt.AlignRight)
        self._tabs_stack.addWidget(topo_card)

        wrap_layout.addWidget(stack_host, stretch=1)
        self._set_active_tab(0)
        return wrap

    def _make_tab_button(self, text: str) -> QPushButton:
        btn = QPushButton(text)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setFlat(True)
        return btn

    def _set_active_tab(self, index: int) -> None:
        self._tabs_stack.setCurrentIndex(index)
        for i, btn in enumerate((self._tab_btn_runs, self._tab_btn_deps)):
            active = i == index
            btn.setStyleSheet(
                f"QPushButton {{ background: transparent; border: none; border-bottom: 2px solid "
                f"{COLORS['accent'] if active else 'transparent'}; border-radius: 0; "
                f"padding: 0 0 8px 0; color: {COLORS['text_main'] if active else COLORS['text_dim']}; "
                f"font-size: 14px; font-weight: {600 if active else 500}; }}"
            )

    def _make_legend_line(self, color: str) -> QLabel:
        lbl = QLabel()
        lbl.setWordWrap(True)   # la carte santé vit désormais dans la colonne étroite de gauche
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

        if self._eyebrow_lbl is not None:
            self._eyebrow_lbl.setText(_today_eyebrow())

        pipelines = db.get_pipelines()
        # Correctif K6 (docs/refonte/LOTS.md) : la carte "Pipelines actifs" comptait tous les
        # pipelines, actifs et inactifs confondus, malgré son libellé.
        active_pipelines = [p for p in pipelines if p.is_active]
        self._card_active.set_value(str(len(active_pipelines)))
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
            self._card_avg_duration.set_value(f"{m}:{s:02d}")   # A5 : "3:08", pas "3m 08s"
        else:
            self._card_avg_duration.set_value("—")

        # Anneau de santé — dernier statut connu par pipeline actif, pas un agrégat de runs
        # (voir HealthRingWidget : un pipeline jamais exécuté n'est ni sain ni en échec).
        healthy = [p for p in active_pipelines if _status_str(p.last_status) == "SUCCESS"]
        unhealthy = [p for p in active_pipelines if _status_str(p.last_status) == "FAILED"]
        self._refresh_treat_column(unhealthy)
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
                # A8 : "2 min 04" si des minutes, "38 s" sinon (Aujourdhui.html).
                dur = f"{m} min {s:02d}" if m else f"{s} s"
            date_s = fmt_datetime(run.started_at)
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
        """Rail en 2 groupes MAINTENANT / ENSUITE (A2) — voir _build_ui(). Reconstruit à chaque
        refresh() (comme le tableau des dernières exécutions), le nombre/type de chips changeant
        dynamiquement."""
        from datetime import datetime, timezone

        from core.pipeline import is_pipeline_running
        from database import db_manager as db

        while self._rail_layout.count():
            item = self._rail_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        running_ids = {p.id for p in pipelines if p.is_active and is_pipeline_running(p.id)}
        step_labels = db.get_running_step_labels()
        now_chips = []
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
                elapsed = f" · {m:02d}:{s:02d}"
            step = step_labels.get(p.id, "Étape en cours…")
            now_chips.append(self._make_rail_chip(
                running=True, dot_color=COLORS["signal"],
                main_text=p.name, main_mono=False, sub_text=f"{step}{elapsed}",
                on_click=lambda pid=p.id: self._open_running_panel(pid),
            ))

        upcoming = sorted(
            (p for p in pipelines if p.is_active and p.next_run_at and p.id not in running_ids),
            key=lambda p: p.next_run_at,
        )[:3]
        next_chips = [
            self._make_rail_chip(
                running=False, dot_color=COLORS["text_muted"],
                main_text=fmt_datetime_local(p.next_run_at, fmt="%d/%m %H:%M"), main_mono=True, sub_text=p.name,
            )
            for p in upcoming
        ]

        if not now_chips and not next_chips:
            placeholder = QLabel("Aucune exécution en cours ni planifiée pour l'instant.")
            placeholder.setStyleSheet(
                f"color: {COLORS['text_muted']}; font-size: 11.5px; font-style: italic;"
            )
            self._rail_layout.addWidget(placeholder)
            return

        if now_chips:
            self._rail_layout.addWidget(self._make_rail_group_label("MAINTENANT"))
            for chip in now_chips:
                self._rail_layout.addWidget(chip)
        if next_chips:
            self._rail_layout.addWidget(self._make_rail_group_label("ENSUITE"))
            for chip in next_chips:
                self._rail_layout.addWidget(chip)
        self._rail_layout.addStretch()

    @staticmethod
    def _make_rail_group_label(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(
            f"color: {COLORS['text_muted']}; font-family: {FONT_MONO_STACK}; font-size: 10px; "
            f"font-weight: 700; letter-spacing: 0.06em; background: transparent; border: none;"
        )
        return lbl

    def _make_rail_chip(self, *, running: bool, dot_color: str, main_text: str,
                         main_mono: bool, sub_text: str, on_click=None) -> QFrame:
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
        # A10 : la puce MAINTENANT ouvre le panneau latéral "en cours" — même patron que les
        # cartes cliquables ailleurs dans la refonte (QFrame + mouseReleaseEvent assigné, pas de
        # QPushButton : la puce a déjà sa propre mise en forme interne).
        if on_click is not None:
            chip.setCursor(Qt.PointingHandCursor)
            chip.mouseReleaseEvent = lambda event, cb=on_click: cb()
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

    def _link_button(self, text: str, color: str) -> QPushButton:
        """Petit bouton "lien" plat (pas de bordure/fond) utilisé par le bandeau des pipelines
        manqués — aucun objectName dédié n'existe dans ui/styles.py pour ce style, seulement
        "secondary"/"danger" (boutons pleins)."""
        btn = QPushButton(text)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setStyleSheet(
            f"QPushButton {{ background: transparent; border: none; color: {color}; "
            f"font-size: 11px; font-weight: 600; padding: 2px 4px; }}"
            f"QPushButton:hover {{ color: {COLORS['text_main']}; }}"
        )
        return btn

    # ── A12 : accueil "premier pipeline" ────────────────────────────────────

    def _build_onboarding_block(self) -> QWidget:
        block = QWidget()
        col = QVBoxLayout(block)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(14)

        subtitle = QLabel(
            "Trois pas suffisent pour qu'un premier pipeline tourne tout seul chaque matin."
        )
        subtitle.setStyleSheet(
            f"color: {COLORS['text_dim']}; font-size: 13px; background: transparent; border: none;"
        )
        col.addWidget(subtitle)

        cards = QHBoxLayout(); cards.setSpacing(14)
        cards.addWidget(self._make_onboarding_card(
            step="1", active=True, title="Brancher une source", badge=None,
            text="Oracle, Postgres, Hive, SFTP, SMTP… Kulu teste la connexion avant de "
                 "l'enregistrer.",
            button_text="Créer une connexion", primary=True,
            on_click=self.open_connections_requested.emit,
        ))
        cards.addWidget(self._make_onboarding_card(
            step="2", active=False, title="Écrire la requête", badge="facultatif",
            text="Garde tes requêtes SQL en bibliothèque pour les réutiliser dans plusieurs "
                 "pipelines.",
            button_text="Ouvrir l'éditeur SQL", primary=False,
            on_click=self.open_sql_editor_requested.emit,
        ))
        cards.addWidget(self._make_onboarding_card(
            step="3", active=False, title="Assembler le pipeline", badge=None,
            text="Pars du modèle « extraction puis dépôt local » : il ne reste que le profil, "
                 "la requête et le dossier à remplir.",
            button_text="Partir du modèle", primary=False,
            on_click=self.start_from_template_requested.emit,
        ))
        col.addLayout(cards)

        links = QHBoxLayout(); links.setSpacing(10)
        lbl_has = QLabel("Tu as déjà un pipeline Kulu ?")
        lbl_has.setStyleSheet(
            f"color: {COLORS['text_dim']}; font-size: 13px; background: transparent; border: none;"
        )
        links.addWidget(lbl_has)
        btn_import = self._link_button("Importer un fichier .dspipeline", COLORS["accent"])
        btn_import.clicked.connect(self.import_pipeline_requested.emit)
        links.addWidget(btn_import)
        sep = QLabel("·")
        sep.setStyleSheet(f"color: {COLORS['text_muted']}; background: transparent; border: none;")
        links.addWidget(sep)
        btn_guide = self._link_button("Lire le guide pas à pas", COLORS["accent"])
        btn_guide.clicked.connect(self.open_help_requested.emit)
        links.addWidget(btn_guide)
        links.addStretch()
        col.addLayout(links)

        return block

    @staticmethod
    def _make_onboarding_card(*, step: str, active: bool, title: str, badge: str | None,
                               text: str, button_text: str, primary: bool, on_click) -> QFrame:
        # Sélecteur d'ID par carte (pas une règle nue sur QFrame) : QLabel hérite de QFrame en
        # Qt, voir REGLES.md section 3 — déjà vu deux fois dans ce lot sur des conteneurs
        # similaires (cartes "À traiter", lignes de rattrapage).
        card = QFrame()
        card.setObjectName(f"onboarding_card_{step}")
        border = COLORS["accent"] if active else COLORS["border"]
        card.setStyleSheet(
            f"QFrame#onboarding_card_{step} {{ background: {COLORS['bg_panel']}; "
            f"border: 1px solid {border}; border-radius: 10px; }}"
        )
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(10)

        head = QHBoxLayout(); head.setSpacing(10)
        badge_lbl = QLabel(step)
        badge_lbl.setFixedSize(26, 26)
        badge_lbl.setAlignment(Qt.AlignCenter)
        if active:
            badge_lbl.setStyleSheet(
                f"background: {COLORS['accent']}; color: #000000; border-radius: 13px; "
                f"font-weight: 700; font-size: 12px;"
            )
        else:
            badge_lbl.setStyleSheet(
                f"background: transparent; border: 1.5px solid {COLORS['text_muted']}; "
                f"color: {COLORS['text_dim']}; border-radius: 13px; font-weight: 700; "
                f"font-size: 12px;"
            )
        head.addWidget(badge_lbl)
        title_lbl = QLabel(title)
        title_lbl.setStyleSheet(
            f"font-size: 15px; font-weight: 600; color: {COLORS['text_main']}; "
            f"background: transparent; border: none;"
        )
        head.addWidget(title_lbl)
        if badge:
            badge_pill = QLabel(badge)
            badge_pill.setStyleSheet(
                f"color: {COLORS['text_dim']}; font-size: 11px; border: 1px solid "
                f"{COLORS['border']}; border-radius: 999px; padding: 1px 8px; "
                f"background: transparent;"
            )
            head.addWidget(badge_pill)
        head.addStretch()
        layout.addLayout(head)

        desc = QLabel(text)
        desc.setWordWrap(True)
        desc.setStyleSheet(
            f"color: {COLORS['text_dim']}; font-size: 12.5px; background: transparent; "
            f"border: none;"
        )
        layout.addWidget(desc, stretch=1)

        btn = QPushButton(button_text) if primary else DashboardView._treat_action_button(button_text)
        btn.setFixedHeight(34)
        btn.clicked.connect(on_click)
        btn_row = QHBoxLayout(); btn_row.addWidget(btn); btn_row.addStretch()
        layout.addLayout(btn_row)

        return card

    def _refresh_treat_column(self, unhealthy_pipelines):
        """Colonne "À traiter" (A3 + A4) : une carte ÉCHEC par pipeline actif dont le dernier
        statut est FAILED, puis une carte MANQUÉE par pipeline en attente de rattrapage — triées
        ÉCHEC avant MANQUÉE ("du plus urgent au moins urgent"). Reconstruite à chaque refresh()
        (même réflexe que _refresh_rail/HistoryView._refresh_frequency : vider puis repeupler
        plutôt que de tenter un diff)."""
        from core.missed_runs import get_pending
        from database import db_manager as db

        while self._treat_cards_layout.count():
            item = self._treat_cards_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        cards = []
        for p in unhealthy_pipelines:
            runs = db.get_runs(p.id, 1)
            if runs:
                cards.append(self._make_failure_card(p, runs[0]))

        pending = get_pending()
        for m in pending:
            cards.append(self._make_missed_card(m))

        self._treat_empty.setVisible(not cards)
        for card in cards:
            self._treat_cards_layout.addWidget(card)

        # Mini-barre groupée (décision utilisateur, question ouverte 6 de la fiche) : seulement
        # à partir de 2 cartes MANQUÉE — avec une seule, son propre "Lancer maintenant"/"Ignorer"
        # suffit, rien à grouper.
        self._missed_bulk_bar.setVisible(len(pending) >= 2)
        if len(pending) >= 2:
            self._lbl_missed_bulk.setText(f"{len(pending)} manquées")

    @staticmethod
    def _treat_card_frame() -> tuple[QFrame, QVBoxLayout]:
        card = QFrame()
        # Sélecteur d'ID, pas une règle nue sur le type QFrame : QLabel hérite de QFrame en Qt,
        # une règle nue se serait propagée à chaque QLabel enfant sans bordure propre (bug
        # constaté sur le patron jumeau de missed_pipelines_dialog.py::_make_row — même défaut,
        # corrigé ici avant qu'il ne se manifeste à l'écran, REGLES.md section 3).
        card.setObjectName("treat_card")
        card.setStyleSheet(
            f"QFrame#treat_card {{ background: {COLORS['bg_panel']}; "
            f"border: 1px solid {COLORS['border']}; border-radius: 10px; }}"
        )
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(14, 12, 14, 12)
        card_layout.setSpacing(6)
        return card, card_layout

    @staticmethod
    def _treat_card_header(dot_style: str, label_text: str, label_color: str) -> QHBoxLayout:
        head = QHBoxLayout(); head.setSpacing(8)
        dot = QLabel()
        dot.setFixedSize(8, 8)
        dot.setStyleSheet(dot_style)
        head.addWidget(dot)
        head_lbl = QLabel(label_text)
        head_lbl.setStyleSheet(
            f"color: {label_color}; font-size: 11px; font-weight: 700; letter-spacing: 0.06em; "
            f"background: transparent; border: none;"
        )
        head.addWidget(head_lbl)
        head.addStretch()
        return head

    def _make_missed_card(self, missed: dict) -> QFrame:
        from ui.dialogs.missed_pipelines_dialog import _format_late

        card, card_layout = self._treat_card_frame()
        card_layout.addLayout(self._treat_card_header(
            f"background: transparent; border: 2px dashed {COLORS['warning']}; border-radius: 4px;",
            f"MANQUÉE · {fmt_time_local(missed['expected_at'])}", COLORS["warning"],
        ))

        name_lbl = QLabel(missed["name"])
        name_lbl.setStyleSheet(
            f"color: {COLORS['text_main']}; font-size: 14px; font-weight: 600; "
            f"background: transparent; border: none;"
        )
        card_layout.addWidget(name_lbl)

        desc_lbl = QLabel(
            "Le poste était éteint à l'heure prévue. En retard de "
            f"{_format_late(missed['late_minutes'])}."
        )
        desc_lbl.setWordWrap(True)
        desc_lbl.setStyleSheet(f"color: {COLORS['text_dim']}; background: transparent; border: none;")
        card_layout.addWidget(desc_lbl)

        actions = QHBoxLayout(); actions.setSpacing(8)
        btn_launch = self._treat_action_button(
            "Lancer maintenant", outline=COLORS["accent"], text_color=COLORS["accent_pale"])
        btn_launch.clicked.connect(
            lambda checked=False, pid=missed["pipeline_id"]: self._on_missed_launch_one(pid))
        actions.addWidget(btn_launch)
        btn_ignore = self._treat_action_button("Ignorer")
        btn_ignore.clicked.connect(
            lambda checked=False, pid=missed["pipeline_id"]: self._on_missed_ignore_one(pid))
        actions.addWidget(btn_ignore)
        actions.addStretch()
        card_layout.addLayout(actions)

        return card

    def _make_failure_card(self, pipeline, run) -> QFrame:
        card, card_layout = self._treat_card_frame()
        card_layout.addLayout(self._treat_card_header(
            f"background: {COLORS['danger']}; border-radius: 4px;",
            f"ÉCHEC · {fmt_time(run.started_at)}", COLORS["danger"],
        ))

        name_lbl = QLabel(pipeline.name)
        name_lbl.setStyleSheet(
            f"color: {COLORS['text_main']}; font-size: 14px; font-weight: 600; "
            f"background: transparent; border: none;"
        )
        card_layout.addWidget(name_lbl)

        step_label = _resolve_step_label(pipeline, run.failed_step_key)
        retries = 0
        if run.failed_step_key:
            retries = next(
                (s.retry_count for s in pipeline.steps
                 if _step_key_of(s) == run.failed_step_key), 0
            )
        if step_label:
            desc_lbl = QLabel(f"Arrêté à l'étape <b>{step_label}</b> après {retries} réessais.")
        else:
            desc_lbl = QLabel(f"Arrêté après {retries} réessais.")
        desc_lbl.setTextFormat(Qt.RichText)
        desc_lbl.setWordWrap(True)
        desc_lbl.setStyleSheet(f"color: {COLORS['text_dim']}; background: transparent; border: none;")
        card_layout.addWidget(desc_lbl)

        if run.error_message:
            err_lbl = QLabel(run.error_message)
            err_lbl.setWordWrap(True)
            err_lbl.setStyleSheet(
                f"color: {COLORS['text_main']}; font-family: {FONT_MONO}; font-size: 11px; "
                f"background: {COLORS['bg_main']}; border: 1px solid {COLORS['bg_hover']}; "
                f"border-radius: 4px; padding: 6px 8px;"
            )
            card_layout.addWidget(err_lbl)

        actions = QHBoxLayout(); actions.setSpacing(8)
        from database import db_manager as db
        if db.get_last_resumable_run(pipeline.id) is not None:
            btn_resume = self._treat_action_button(
                "Reprendre depuis l'échec", outline=COLORS["accent"], text_color=COLORS["accent_pale"])
            btn_resume.clicked.connect(lambda checked=False, pid=pipeline.id: self._on_resume_run(pid))
            actions.addWidget(btn_resume)
        btn_details = self._treat_action_button("Détails")
        btn_details.clicked.connect(lambda checked=False, pid=pipeline.id: self._open_failure_panel(pid))
        actions.addWidget(btn_details)
        actions.addStretch()
        card_layout.addLayout(actions)

        return card

    @staticmethod
    def _treat_action_button(text: str, outline: str = None, text_color: str = None) -> QPushButton:
        btn = QPushButton(text)
        btn.setFixedHeight(30)
        border = outline or COLORS["border"]
        color = text_color or COLORS["text_main"]
        btn.setStyleSheet(
            f"QPushButton {{ background: transparent; border: 1px solid {border}; "
            f"border-radius: 6px; color: {color}; font-weight: 600; padding: 0 12px; }}"
            f"QPushButton:hover {{ background: {COLORS['bg_hover']}; }}"
        )
        return btn

    def _on_resume_run(self, pipeline_id: int):
        from database import db_manager as db
        from ui.dialogs.run_progress_dialog import RunProgressDialog
        resumable = db.get_last_resumable_run(pipeline_id)
        if resumable is None:
            return
        pipeline = db.get_pipeline(pipeline_id)
        name = pipeline.name if pipeline else str(pipeline_id)
        RunProgressDialog(pipeline_id, name, self, resume_from_run_id=resumable.id).exec()
        self.refresh()

    def _on_missed_launch_one(self, pipeline_id: int):
        from core.missed_runs import resolve
        try:
            from core.scheduler import get_scheduler
            get_scheduler().trigger_now(pipeline_id)
        except RuntimeError:
            pass
        resolve(pipeline_id)
        self.refresh()

    def _on_missed_ignore_one(self, pipeline_id: int):
        from core.missed_runs import resolve
        resolve(pipeline_id)
        self.refresh()

    def _on_missed_launch_all(self):
        from core.missed_runs import get_pending, resolve
        try:
            from core.scheduler import get_scheduler
            scheduler = get_scheduler()
        except RuntimeError:
            scheduler = None
        for m in get_pending():
            if scheduler is not None:
                scheduler.trigger_now(m["pipeline_id"])
            resolve(m["pipeline_id"])
        self.refresh()

    def _on_missed_ignore_all(self):
        from core.missed_runs import get_pending, resolve
        for m in get_pending():
            resolve(m["pipeline_id"])
        self.refresh()

    def _on_notifications(self):
        self.navigate_to_settings.emit("notifications")

    def _on_open_topology_dialog(self):
        from database import db_manager as db
        from ui.dialogs import PipelineTopologyDialog
        PipelineTopologyDialog(self, db.get_pipelines()).exec()

    # ── A9 : panneau latéral d'une exécution en échec ──

    def _open_failure_panel(self, pipeline_id: int):
        from database import db_manager as db
        pipeline = db.get_pipeline(pipeline_id)
        runs = db.get_runs(pipeline_id, 8)
        if not pipeline or not runs:
            return
        self._side_panel.set_content(self._build_failure_panel_content(pipeline, runs[0], runs))
        self._side_panel.open()

    def _build_failure_panel_content(self, pipeline, run, runs) -> QWidget:
        content = QWidget()
        content.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(24, 4, 24, 20)
        layout.setSpacing(12)

        eyebrow = QLabel(f"EXÉCUTION #{run.id} · ÉCHEC")
        eyebrow.setStyleSheet(
            f"color: {COLORS['danger']}; font-family: {FONT_MONO_STACK}; font-size: 11px; "
            f"font-weight: 700; letter-spacing: 0.06em; background: transparent; border: none;"
        )
        layout.addWidget(eyebrow)

        title = QLabel(pipeline.name)
        title.setWordWrap(True)
        title.setStyleSheet(
            f"color: {COLORS['text_main']}; font-size: 20px; font-weight: 700; "
            f"background: transparent; border: none;"
        )
        layout.addWidget(title)

        dur = "—"
        if run.duration_seconds is not None:
            m, s = divmod(int(run.duration_seconds), 60)
            dur = f"{m} min {s:02d}" if m else f"{s} s"
        info_bits = [f"Partie à {fmt_time(run.started_at)}"]
        if run.finished_at:
            info_bits.append(f"Arrêtée à {fmt_time(run.finished_at)}")
        info_bits.append(dur)
        info = QLabel(" · ".join(info_bits))
        info.setStyleSheet(f"color: {COLORS['text_dim']}; font-size: 12px; background: transparent; border: none;")
        layout.addWidget(info)

        history = [_status_str(r.status) for r in runs[:8]][::-1]
        layout.addWidget(RunHistoryDots(history), alignment=Qt.AlignLeft)

        if run.error_message:
            err = QLabel(run.error_message)
            err.setWordWrap(True)
            err.setStyleSheet(
                f"color: {COLORS['text_main']}; font-family: {FONT_MONO}; font-size: 11.5px; "
                f"background: {COLORS['bg_main']}; border: 1px solid {COLORS['bg_hover']}; "
                f"border-radius: 6px; padding: 10px;"
            )
            layout.addWidget(err)

        layout.addStretch()

        from database import db_manager as db
        footer = QHBoxLayout(); footer.setSpacing(8)
        if db.get_last_resumable_run(pipeline.id) is not None:
            btn_resume = self._treat_action_button(
                "Reprendre depuis l'échec", outline=COLORS["accent"], text_color=COLORS["accent_pale"])
            btn_resume.clicked.connect(lambda: self._on_resume_from_panel(pipeline.id))
            footer.addWidget(btn_resume)
        btn_atelier = self._treat_action_button("Ouvrir dans l'Atelier")
        btn_atelier.clicked.connect(
            lambda: self.open_atelier_requested.emit(pipeline.id, run.failed_step_key, False))
        footer.addWidget(btn_atelier)
        btn_journal = self._treat_action_button("Journal")
        btn_journal.clicked.connect(lambda: self._on_open_run_log(run.id))
        footer.addWidget(btn_journal)
        footer.addStretch()
        layout.addLayout(footer)

        return content

    def _on_resume_from_panel(self, pipeline_id: int):
        self._side_panel.close()
        self._on_resume_run(pipeline_id)

    def _on_open_run_log(self, run_id: int):
        from ui.main_window.run_log_dialog import open_run_log_dialog
        open_run_log_dialog(self, run_id)

    # ── A10 : panneau latéral d'une exécution en cours ──

    def _open_running_panel(self, pipeline_id: int):
        from database import db_manager as db
        pipeline = db.get_pipeline(pipeline_id)
        runs = db.get_runs(pipeline_id, 1)
        if not pipeline or not runs:
            return
        self._side_panel.set_content(self._build_running_panel_content(pipeline, runs[0]))
        self._side_panel.open()

    def _build_running_panel_content(self, pipeline, run) -> QWidget:
        from database import db_manager as db
        from database.models import PipelineRun

        content = QWidget()
        content.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(24, 4, 24, 20)
        layout.setSpacing(12)

        eyebrow = QLabel(f"EN COURS · DÉPART {fmt_time(run.started_at)}")
        eyebrow.setStyleSheet(
            f"color: {COLORS['signal_pale']}; font-family: {FONT_MONO_STACK}; font-size: 11px; "
            f"font-weight: 700; letter-spacing: 0.06em; background: transparent; border: none;"
        )
        layout.addWidget(eyebrow)

        title = QLabel(pipeline.name)
        title.setWordWrap(True)
        title.setStyleSheet(
            f"color: {COLORS['text_main']}; font-size: 20px; font-weight: 700; "
            f"background: transparent; border: none;"
        )
        layout.addWidget(title)

        # Indéterminée (0, 0), pas un pourcentage : PipelineRun ne stocke pas d'avancement
        # numérique (seulement current_step_label/log_text, voir update_run_progress) — un run en
        # arrière-plan n'a d'ailleurs aucune notion fiable de "pourcentage" à relire depuis la
        # base, contrairement à RunProgressDialog qui reçoit pct en direct du thread qu'il lance.
        progress = QProgressBar()
        progress.setRange(0, 0)
        progress.setTextVisible(False)
        progress.setFixedHeight(6)
        layout.addWidget(progress)

        lbl_step = QLabel(run.current_step_label or "Étape en cours…")
        lbl_step.setWordWrap(True)
        lbl_step.setStyleSheet(
            f"color: {COLORS['text_dim']}; font-size: 12px; background: transparent; border: none;")
        layout.addWidget(lbl_step)

        lbl_journal = QLabel("JOURNAL EN DIRECT")
        lbl_journal.setStyleSheet(
            f"color: {COLORS['text_muted']}; font-size: 10px; font-weight: 700; "
            f"letter-spacing: 0.06em; background: transparent; border: none;"
        )
        layout.addWidget(lbl_journal)

        log_box = QPlainTextEdit()
        log_box.setReadOnly(True)
        log_box.setFont(QFont(FONT_MONO, 10))
        log_box.setStyleSheet(
            f"background: {COLORS['bg_main']}; color: {COLORS['text_main']}; "
            f"border: 1px solid {COLORS['border']}; border-radius: 6px;"
        )
        log_box.setPlainText(run.log_text or "")
        layout.addWidget(log_box, stretch=1)

        footer = QHBoxLayout(); footer.setSpacing(8)
        btn_stop = QPushButton("Arrêter")
        btn_stop.setObjectName("danger")
        btn_stop.setFixedHeight(34)
        btn_stop.clicked.connect(lambda: self._on_stop_running(pipeline.id))
        footer.addWidget(btn_stop)
        btn_atelier = self._treat_action_button("Ouvrir dans l'Atelier")
        btn_atelier.clicked.connect(
            lambda: self.open_atelier_requested.emit(pipeline.id, None, False))
        footer.addWidget(btn_atelier)
        footer.addStretch()
        layout.addLayout(footer)

        # Rafraîchissement en direct (même patron que run_log_dialog.py::_refresh_live) —
        # s'arrête de lui-même dès que le run quitte RUNNING, ou si le panneau se ferme.
        run_id = run.id
        timer = QTimer(content)

        def _poll():
            with db.get_session() as s:
                fresh = s.get(PipelineRun, run_id)
                if not fresh or _status_str(fresh.status) != "RUNNING":
                    timer.stop()
                    return
                new_log = fresh.log_text or ""
                if new_log != log_box.toPlainText():
                    bar = log_box.verticalScrollBar()
                    at_bottom = bar.value() >= bar.maximum() - 4
                    log_box.setPlainText(new_log)
                    if at_bottom:
                        bar.setValue(bar.maximum())
                lbl_step.setText(fresh.current_step_label or "Étape en cours…")

        timer.setInterval(db.get_app_settings().live_log_refresh_s * 1000)
        timer.timeout.connect(_poll)
        timer.start()
        self._side_panel.closed.connect(timer.stop)

        return content

    def _on_stop_running(self, pipeline_id: int):
        # En mode arrière-plan, request_cancel() local (core.pipeline._active_runs, en mémoire)
        # n'a aucun effet : c'est le worker détaché qui exécute réellement le pipeline, jamais
        # l'appli desktop (correctif K5, même idiome que pipelines_view.py::_on_interrupt_pipeline).
        from core.pipeline import request_cancel
        from core.execution_mode import request_cancel_run
        if not request_cancel_run(pipeline_id):
            request_cancel(pipeline_id)

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

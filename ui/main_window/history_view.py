"""
DataScheduler — ui/main_window/history_view.py
Vue Historique : journal complet des exécutions.
"""

import re

from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton, QFrame, QScrollArea,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView, QStackedLayout,
    QPlainTextEdit,
)
from PySide6.QtCore import Qt, QSize, Signal
from PySide6.QtGui import QFont, QColor
from ui.styles import COLORS
from ui.time_display import fmt_time, fmt_datetime, fmt_relative, to_display
from ui.components import make_page_header, Bubble, SidePanel
from .widgets import (
    _icon, _action_btn, _configure_columns, _make_search_input, _make_empty_label,
    _make_subtitle, _STATUS_BADGE, _status_str, FONT_MONO, _make_status_badge,
    RunFrequencyHeatmap, HeatmapMonthMarkers, make_heatmap_legend,
)

_HEATMAP_DAYS = 90
# Plafond par défaut de la section "Fréquence d'exécution" (passage à l'échelle — au-delà, une
# requête d'agrégation par pipeline devenait sensible au nombre total de pipelines actifs, pas
# seulement à l'activité réelle). Désactivé (aucun plafond) dès qu'une recherche est en cours,
# pour qu'un pipeline peu actif reste trouvable — voir _refresh_frequency().
_MAX_FREQUENCY_ROWS = 10

_STATUS_FILTER_OPTIONS = [
    ("Tous les statuts", None),
    ("Succès", "SUCCESS"),
    ("Échec", "FAILED"),
    ("En cours", "RUNNING"),
    ("Annulé", "CANCELLED"),
]

# Jours/mois en français écrits en dur (A5/A9) — même raison que dashboard_view.py : pas de
# dépendance à la locale système.
_DAYS_FR = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
_MONTHS_FR = [
    "janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août",
    "septembre", "octobre", "novembre", "décembre",
]

# A7 (refonte, lot A-Historique) : mapping purement d'affichage, local à cet écran — ne touche
# pas _make_status_badge/_STATUS_BADGE (partagés avec Pipelines/Dashboard, qui continuent
# d'afficher les codes anglais). CANCELLED garde le style badge_idle (fiche : "tombe sur
# badge_idle"), seul le mot affiché change.
_STATUS_LABEL_FR = {
    "SUCCESS": "Réussi", "FAILED": "Échec", "RUNNING": "En cours",
    "CANCELLED": "Annulé", "IDLE": "—",
}


def _status_label_fr(status_code: str) -> str:
    return _STATUS_LABEL_FR.get(status_code, status_code)


def _format_duration_short(seconds) -> str:
    """« 2 min 04 » / « 38 s » (A6) — même format que Pipelines/Aujourd'hui/Dashboard, dupliqué
    ici (convention déjà suivie par dashboard_view.py plutôt qu'un import inter-vues)."""
    if seconds is None:
        return "—"
    m, s = divmod(int(seconds), 60)
    return f"{m} min {s:02d}" if m else f"{s} s"


def _day_group_label(day, today) -> str:
    """Intitulé d'une ligne d'en-tête de groupe du tableau principal (A5) — jour calculé dans le
    fuseau réglé (même conversion que la colonne Heure), pas le fuseau UTC de stockage (le
    calendrier de fréquence, lui, reste en UTC — B7, hors périmètre de ce lot)."""
    from datetime import timedelta
    if day == today:
        return "AUJOURD'HUI"
    if day == today - timedelta(days=1):
        return "HIER"
    return f"{_DAYS_FR[day.weekday()].upper()} {day.day} {_MONTHS_FR[day.month - 1].upper()}"


# A10 : eyebrow du panneau latéral de run, couleur selon le statut.
_PANEL_EYEBROW_COLOR = {
    "SUCCESS": "success", "FAILED": "danger", "RUNNING": "signal_pale", "CANCELLED": "text_dim",
}


def _step_key_of(step) -> str | None:
    """Dupliqué de dashboard_view.py (A10) — même raison que _format_duration_short : convention
    déjà suivie par ce module plutôt qu'un import inter-vues."""
    import json
    try:
        config = json.loads(step.config_json or "{}")
    except (TypeError, ValueError):
        return None
    return config.get("_step_key")


def _resolve_step_label(pipeline, step_key: str | None) -> str | None:
    """Étape fautive -> libellé lisible (A10), dupliqué de dashboard_view.py."""
    if not step_key:
        return None
    for step in pipeline.steps:
        if _step_key_of(step) == step_key:
            step_type = str(step.step_type).replace("StepType.", "")
            return step.label or step_type
    return None


_LOG_LINE_RE = re.compile(r"^\[(\d{2}):(\d{2}):(\d{2})\] (.*)$")


def _convert_log_text_times(log_text: str, started_at) -> str:
    """Reconstruit l'horodatage complet de chaque ligne de log (A10/T3, DECISIONS.md) —
    PipelineResult.log() (core/pipeline.py) écrit chaque ligne en UTC avec seulement l'heure
    (`[HH:MM:SS]`, pas la date). Algorithme décrit par la fiche elle-même (section B3) comme
    repli tant que B3 (journal à niveaux avec date complète stockée) n'existe pas — c'est donc le
    seul disponible pour ce lot : reconstruit la date complète à partir de `started_at.date()`, en
    la faisant avancer d'un jour à chaque fois que l'heure analysée est plus tôt que celle de la
    ligne précédente (passage de minuit)."""
    if not log_text or not started_at:
        return log_text or ""
    from datetime import datetime, timedelta

    current_date = started_at.date()
    prev_time = None
    out_lines = []
    for line in log_text.splitlines():
        m = _LOG_LINE_RE.match(line)
        if not m:
            out_lines.append(line)
            continue
        h, mi, s, rest = m.groups()
        t = (int(h), int(mi), int(s))
        if prev_time is not None and t < prev_time:
            current_date += timedelta(days=1)
        prev_time = t
        utc_dt = datetime(current_date.year, current_date.month, current_date.day, *t)
        local_dt = to_display(utc_dt)
        out_lines.append(f"[{local_dt.strftime('%H:%M:%S')}] {rest}")
    return "\n".join(out_lines)


# A11 (refonte, lot A-Historique) : traduction/couleur du journal des modifications, locale à cet
# écran — AuditEvent.event_type reste stocké tel quel en base (jamais réécrit), seul l'affichage
# change. Seuls les types explicitement listés par la fiche ont une couleur dédiée
# (succès/danger/signal_pale) ; un type connu mais non cité (duplication/export) reste text_main ;
# un type futur inconnu (B6 : connexion/requête/réglage) retombe sur le texte brut + text_main,
# jamais un crash.
_EVENT_TYPE_FR = {
    "pipeline_created": ("Création", "success"),
    "pipeline_edited": ("Modification", "text_main"),
    "pipeline_deleted": ("Suppression", "danger"),
    "pipeline_duplicated": ("Duplication", "text_main"),
    "pipeline_exported": ("Export", "text_main"),
    "pipeline_imported": ("Import", "signal_pale"),
}


def _event_type_label_and_color(event_type: str) -> tuple[str, str]:
    return _EVENT_TYPE_FR.get(event_type, (event_type, "text_main"))


# pipeline_imported est le seul event_type dont le detail stocké (database/export_import.py,
# apply_import()) est un motif technique brut ("action=create|collision|rename|overwrite"), pas
# déjà une phrase lisible comme les autres (save_steps/save_pipeline_graph/export_pipeline_to_file
# écrivent déjà des phrases en français) — décision utilisateur (AskUserQuestion) : reformuler ce
# seul cas à l'affichage, jamais inventer une donnée non stockée pour un detail vide/sparse.
_IMPORT_ACTION_FR = {
    "create": "Nouveau pipeline",
    "collision": "Collision non résolue",
    "rename": "Copie renommée",
    "overwrite": "Pipeline existant écrasé",
}


def _translate_audit_detail(event) -> str:
    detail = event.detail or ""
    if event.event_type == "pipeline_imported" and detail.startswith("action="):
        action = detail[len("action="):]
        return _IMPORT_ACTION_FR.get(action, detail)
    return detail or "—"


class HistoryView(QWidget):
    # Chantier Atelier Pipelines (écran 2) — même signal/contrat que PipelinesView
    # (pipeline_id, highlight_step_key, is_new_pipeline) ; ici is_new_pipeline est toujours
    # False (un lien "Voir dans le graphe" depuis l'historique n'édite jamais une création) et
    # highlight_step_key est toujours renseigné (voir _open_graph).
    open_atelier_requested = Signal(int, object, bool)
    # C9 (Atelier-echec) : vue en lecture seule d'un run passé — additif, jamais une modification
    # du signal ci-dessus (PipelinesView/Dashboard l'utilisent aussi, sans run à transmettre).
    # (pipeline_id, run_id, failed_step_key).
    open_atelier_run_requested = Signal(int, int, object)

    def __init__(self):
        super().__init__()
        self._build_ui()

    def _build_ui(self):
        # Le calendrier de fréquence (une ligne par pipeline actif) grandit avec le nombre de
        # pipelines, même risque de dépassement de fenêtre déjà rencontré et corrigé sur le
        # Dashboard (chantier identité vague 2) — appliqué ici préventivement. `layout` reste le
        # layout du contenu interne, tout le reste de cette méthode est inchangé.
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

        self._tab_exec_btn = self._make_tab_button("Exécutions")
        self._tab_exec_btn.clicked.connect(lambda: self._set_active_tab(0))
        self._tab_mod_btn = self._make_tab_button("Journal des modifications")
        self._tab_mod_btn.clicked.connect(lambda: self._set_active_tab(1))

        header = make_page_header("", "Historique", actions=[self._tab_exec_btn, self._tab_mod_btn])
        # make_page_header() ne renvoie pas de référence à son surtitre — recherché une fois ici
        # par objectName (même patron que dashboard_view.py/pipelines_view.py), tenu à jour dans
        # refresh() (A1 : "N EXÉCUTIONS SUR 7 JOURS · N ÉCHECS").
        self._eyebrow_lbl = header.findChild(QLabel, "page_eyebrow")
        layout.addWidget(header)

        sep = QFrame(); sep.setObjectName("separator"); sep.setFrameShape(QFrame.HLine)
        layout.addWidget(sep)

        self._tabs_stack = QStackedLayout()
        stack_host = QWidget()
        stack_host.setLayout(self._tabs_stack)

        exec_page = QWidget()
        exec_layout = QVBoxLayout(exec_page)
        exec_layout.setContentsMargins(0, 0, 0, 0)
        exec_layout.setSpacing(24)

        self._status_filter = None
        self._status_buttons = {}
        filters_row = QHBoxLayout()
        filters_row.setSpacing(8)
        for label, value in _STATUS_FILTER_OPTIONS:
            btn = QPushButton(label)
            btn.setFixedHeight(30)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda _, v=value: self._set_active_status(v))
            self._status_buttons[value] = btn
            filters_row.addWidget(btn)
        filters_row.addStretch()
        self.inp_search = _make_search_input("Rechercher…")
        self.inp_search.textChanged.connect(self._on_search_changed)
        filters_row.addWidget(self.inp_search)
        exec_layout.addLayout(filters_row)

        freq_frame = QFrame(); freq_frame.setObjectName("card")
        freq_layout = QVBoxLayout(freq_frame)
        freq_layout.setContentsMargins(20, 16, 20, 16)
        freq_layout.setSpacing(10)
        freq_title = QLabel("Fréquence d'exécution")
        freq_title.setStyleSheet(
            f"font-size: 13px; font-weight: 700; color: {COLORS['text_main']}; border: none;")
        freq_layout.addWidget(freq_title)
        freq_layout.addWidget(_make_subtitle("90 derniers jours · clic sur un jour pour ses exécutions."))
        freq_layout.addWidget(make_heatmap_legend())

        # Repères de mois alignés sur la grille des calendriers ci-dessous — décalage de
        # (largeur du nom de pipeline 160px + espacement de la ligne 12px), même valeurs que
        # dans _refresh_frequency().
        markers_row = QHBoxLayout()
        markers_row.setContentsMargins(0, 0, 0, 0)
        markers_spacer = QWidget(); markers_spacer.setFixedWidth(172)
        markers_row.addWidget(markers_spacer)
        markers_row.addWidget(HeatmapMonthMarkers(_HEATMAP_DAYS))
        markers_row.addStretch()
        freq_layout.addLayout(markers_row)

        self._freq_rows_layout = QVBoxLayout()
        self._freq_rows_layout.setSpacing(8)
        freq_layout.addLayout(self._freq_rows_layout)
        self._freq_empty_label = _make_empty_label("Aucun pipeline actif pour l'instant.")
        self._freq_empty_label.setVisible(False)
        freq_layout.addWidget(self._freq_empty_label)
        exec_layout.addWidget(freq_frame)

        self._run_ids = []   # index ligne → run_id
        self._bubble = None   # Bulle du jour (A9) — référence gardée pour qu'elle ne soit pas GC
        # A10 : panneau latéral d'un run, réutilisé pour chaque ouverture (même patron que
        # Dashboard/Pipelines) — `self` (cette vue) est déjà intégrée à la fenêtre principale, pas
        # une fenêtre top-level, donc parent.rect() reflète la bonne zone à couvrir.
        self._side_panel = SidePanel(self)

        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(
            ["Heure", "Pipeline", "Durée", "Lignes", "Statut", "Fichier déposé", ""])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setShowGrid(False)
        _configure_columns(self.table, stretch_cols={1, 5})
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
        self.table.setColumnWidth(0, 76)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Fixed)
        self.table.setColumnWidth(4, 130)
        self.table.horizontalHeader().setSectionResizeMode(6, QHeaderView.Fixed)
        # 60px suffisait pour le seul bouton "Voir le log complet" — élargi pour accueillir le
        # second bouton "Voir dans le graphe" (chantier UX éditeur, Lot 1, B1) sans chevauchement
        # ni débordement hors du tableau (2×26px + espacement + marges).
        self.table.setColumnWidth(6, 96)
        self.table.doubleClicked.connect(self._on_row_dbl_click)
        exec_layout.addWidget(self.table)

        self._empty_label = _make_empty_label(
            "Aucune exécution enregistrée pour l'instant."
        )
        self._empty_label.setVisible(False)
        exec_layout.addWidget(self._empty_label)
        exec_layout.addStretch()

        self._tabs_stack.addWidget(exec_page)

        # Page "Journal des modifications" (A11/A12) — remplace l'ancien bouton + QDialog
        # (_on_audit_log, supprimé) : même table (_build_audit_table, signature inchangée), types
        # traduits/colorés, note de bas de page verbatim de la maquette. self.audit_table est
        # remplacée à chaque refresh() (_refresh_audit_log) — même patron que _refresh_frequency,
        # pas de méthode d'update ligne à ligne pour une table reconstruite à chaque fois.
        mod_page = QWidget()
        self._mod_layout = QVBoxLayout(mod_page)
        self._mod_layout.setContentsMargins(0, 0, 0, 0)
        self._mod_layout.setSpacing(16)

        self.audit_table = self._build_audit_table([])
        self._mod_layout.addWidget(self.audit_table)

        self._audit_empty_label = _make_empty_label("Aucun événement enregistré pour l'instant.")
        self._audit_empty_label.setVisible(False)
        self._mod_layout.addWidget(self._audit_empty_label)

        audit_footnote = _make_subtitle(
            "Aujourd'hui, le journal ne suit que les pipelines (création, modification, "
            "suppression, import). Les lignes « proposé » étendent le suivi aux connexions, aux "
            "requêtes et au détail des réglages modifiés."
        )
        audit_footnote.setWordWrap(True)
        self._mod_layout.addWidget(audit_footnote)

        self._tabs_stack.addWidget(mod_page)

        layout.addWidget(stack_host)
        self._set_active_tab(0)
        self._set_active_status(None)

        self.refresh()

    def _make_tab_button(self, text: str) -> QPushButton:
        btn = QPushButton(text)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setFlat(True)
        return btn

    def _set_active_tab(self, index: int) -> None:
        self._tabs_stack.setCurrentIndex(index)
        for i, btn in enumerate((self._tab_exec_btn, self._tab_mod_btn)):
            active = i == index
            btn.setStyleSheet(
                f"QPushButton {{ background: transparent; border: none; border-bottom: 2px solid "
                f"{COLORS['accent'] if active else 'transparent'}; border-radius: 0; "
                f"padding: 0 0 8px 0; color: {COLORS['text_main'] if active else COLORS['text_dim']}; "
                f"font-size: 14px; font-weight: {600 if active else 500}; }}"
            )

    def _set_active_status(self, value) -> None:
        """Filtre de statut en boutons segmentés (A3) — même patron visuel que
        ResourcesView._set_active_range (pilule active : fond bg_active + bordure accent + texte
        gras ; inactive : transparent + bordure border + texte dim ; survol : bordure accent)."""
        self._status_filter = value
        for v, btn in self._status_buttons.items():
            active = v == value
            btn.setStyleSheet(
                f"QPushButton {{ border-radius: 15px; padding: 0 14px; font-size: 12px; "
                f"font-weight: {'700' if active else '500'}; "
                f"background: {COLORS['bg_active'] if active else 'transparent'}; "
                f"color: {COLORS['text_main'] if active else COLORS['text_dim']}; "
                f"border: 1px solid {COLORS['accent'] if active else COLORS['border']}; }}"
                f"QPushButton:hover {{ border-color: {COLORS['accent']}; color: {COLORS['text_main']}; }}"
            )
        self._apply_filters()

    def _apply_filters(self, *_args):
        """Combine le filtre de statut (propriété `status_code` posée sur le badge à la
        construction — pas badge.text(), qui affiche désormais un libellé français, A7) et la
        recherche libre (sous-chaîne insensible à la casse, colonnes Heure/Pipeline/Durée/Lignes/
        Statut/Fichier déposé + message d'erreur — A2) — une ligne doit satisfaire les deux pour
        rester visible. `self._run_ids[row] is None` identifie une ligne d'en-tête de groupe de
        jour (A5) : jamais filtrée directement, sa visibilité suit celle des runs qu'elle
        introduit (calculé après coup ci-dessous, une ligne d'en-tête ne connaît pas son groupe)."""
        status = self._status_filter
        needle = self.inp_search.text().strip().lower()
        search_cols = [0, 1, 2, 3, 4, 5]
        group_header_rows = []
        for row in range(self.table.rowCount()):
            if row >= len(self._run_ids) or self._run_ids[row] is None:
                group_header_rows.append(row)
                continue
            badge = self.table.cellWidget(row, 4)
            status_code = badge.property("status_code") if badge is not None else None
            if status is not None and status_code != status:
                self.table.setRowHidden(row, True)
                continue
            error_s = (self._run_errors.get(row) or "").lower()
            if not needle:
                self.table.setRowHidden(row, False)
                continue
            haystack = []
            for col in search_cols:
                item = self.table.item(row, col)
                if item:
                    haystack.append(item.text().lower())
                elif col == 4 and badge is not None:
                    haystack.append(badge.text().lower())
            haystack.append(error_s)
            self.table.setRowHidden(row, needle not in " ".join(haystack))

        n = self.table.rowCount()
        for row in group_header_rows:
            has_visible = False
            for r2 in range(row + 1, n):
                if r2 >= len(self._run_ids) or self._run_ids[r2] is None:
                    break
                if not self.table.isRowHidden(r2):
                    has_visible = True
                    break
            self.table.setRowHidden(row, not has_visible)

    def _on_search_changed(self, text: str):
        """La recherche filtre à la fois le tableau des exécutions (déjà couvert par
        _apply_filters) et la section "Fréquence d'exécution", qui ne montre par défaut que les
        pipelines les plus actifs — une recherche doit pouvoir en révéler un moins actif, exclu
        de ce plafond par défaut."""
        self._apply_filters()
        self._refresh_frequency(search=text.strip())

    def set_status_filter(self, status: str):
        # "" (chaîne vide) -> None : "Tous les statuts" est la valeur None dans
        # _STATUS_FILTER_OPTIONS/_status_buttons, pas "" — nécessaire pour le lien "Tout
        # l'historique" d'Aujourd'hui (A7, chantier antérieur), qui émet navigate_to_history("")
        # via un signal typé str (pas object).
        value = status or None
        if value in self._status_buttons:
            self._set_active_status(value)
        else:
            self._apply_filters()

    def _refresh_frequency(self, search: str = ""):
        """Une ligne (nom + calendrier de fréquence) par pipeline actif — pipelines désactivés
        exclus, leur historique n'étant plus d'actualité opérationnelle. Sans recherche, plafonné
        aux `_MAX_FREQUENCY_ROWS` pipelines les plus actifs (get_most_active_pipelines fait le tri
        et le plafond en une seule requête d'agrégation — jamais un chargement de tous les
        pipelines suivi d'un tri en Python, qui redeviendrait sensible à leur nombre total).
        Recherche active -> plafond levé, filtré par nom au niveau SQL."""
        from database import db_manager as db

        while self._freq_rows_layout.count():
            item = self._freq_rows_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        if search:
            pipelines = db.get_most_active_pipelines(limit=None, name_filter=search)
        else:
            pipelines = db.get_most_active_pipelines(limit=_MAX_FREQUENCY_ROWS)
        self._freq_empty_label.setVisible(not pipelines)
        for p in pipelines:
            counts = db.get_run_counts_by_day(days=_HEATMAP_DAYS, pipeline_id=p.id)
            row_widget = QWidget()
            row = QHBoxLayout(row_widget)
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(12)
            name = p.name if len(p.name) <= 22 else p.name[:21] + "…"
            name_lbl = QLabel(name)
            name_lbl.setFixedWidth(160)
            name_lbl.setToolTip(p.name)
            name_lbl.setStyleSheet(f"color: {COLORS['text_main']}; font-size: 12px; border: none;")
            row.addWidget(name_lbl)
            heatmap = RunFrequencyHeatmap(counts)
            heatmap.day_clicked.connect(
                lambda day, pl=p, hm=heatmap: self._on_frequency_day_clicked(pl, day, hm))
            row.addWidget(heatmap)
            row.addStretch()
            self._freq_rows_layout.addWidget(row_widget)

    def _on_frequency_day_clicked(self, pipeline, day, anchor=None):
        """Case du calendrier de fréquence cliquée (chantier identité, vague 4, idée 13 ; refonte,
        lot A-Historique, A9) — bulle ancrée au calendrier de CE pipeline (composant partagé
        Bubble, FONDATIONS.md section 3), détail des exécutions de CE jour. Remplace l'ancien
        QDialog. `anchor` (le widget RunFrequencyHeatmap cliqué) est optionnel — retombe sur
        `self` pour un appel direct en test ; une seule case déclenche le clic quel que soit le
        pipeline affiché, la bulle s'ancre donc au calendrier de LA ligne cliquée, pas à un point
        précis de la case (REGLES.md section 1 : le placement exact au pixel n'est pas exigé)."""
        from database import db_manager as db
        runs = db.get_runs_for_pipeline_on_day(pipeline.id, day)
        if not runs:
            return

        content = QWidget()
        vl = QVBoxLayout(content)
        vl.setContentsMargins(16, 14, 16, 14)
        vl.setSpacing(4)

        title = QLabel(pipeline.name)
        title.setWordWrap(True)
        title.setStyleSheet(
            f"font-size: 13px; font-weight: 700; color: {COLORS['text_main']}; border: none;")
        vl.addWidget(title)

        date_s = f"{_DAYS_FR[day.weekday()]} {day.day} {_MONTHS_FR[day.month - 1]}"
        n = len(runs)
        sub = QLabel(f"{date_s} · {n} exécution{'s' if n != 1 else ''}")
        sub.setStyleSheet(f"font-size: 11px; color: {COLORS['text_dim']}; border: none;")
        vl.addWidget(sub)

        sep = QFrame(); sep.setObjectName("separator"); sep.setFrameShape(QFrame.HLine)
        vl.addWidget(sep)

        for r in runs:
            vl.addWidget(self._build_bubble_run_row(r))

        bubble_anchor = anchor if anchor is not None else self
        self._bubble = Bubble(bubble_anchor.window())
        self._bubble.set_content(content)
        self._bubble.open_at(bubble_anchor)

    def _build_bubble_run_row(self, run) -> QPushButton:
        """Une ligne de la bulle du jour (A9) : heure | statut · durée (+ 1ʳᵉ ligne du message
        d'erreur si échec) | flèche — toute la ligne cliquable, ouvre le détail de ce run et
        ferme la bulle. Enfants en WA_TransparentForMouseEvents : sans ça, un QLabel capte le
        clic avant qu'il n'atteigne le QPushButton qui l'englobe (même gotcha déjà rencontré avec
        des widgets Qt empilés, voir feedback_pyside_gotchas)."""
        st = _status_str(run.status)
        row_btn = QPushButton()
        row_btn.setFlat(True)
        row_btn.setCursor(Qt.PointingHandCursor)
        row_btn.setStyleSheet(
            "QPushButton { background: transparent; border: none; border-radius: 6px; text-align: left; }"
            f"QPushButton:hover {{ background: {COLORS['bg_hover']}; }}"
        )
        row_l = QHBoxLayout(row_btn)
        row_l.setContentsMargins(6, 6, 6, 6)
        row_l.setSpacing(8)

        time_lbl = QLabel(fmt_time(run.started_at))
        time_lbl.setFixedWidth(52)
        time_lbl.setAttribute(Qt.WA_TransparentForMouseEvents)
        time_lbl.setStyleSheet(
            f"font-family: {FONT_MONO}; font-size: 11.5px; color: {COLORS['text_dim']}; border: none;")
        row_l.addWidget(time_lbl)

        detail_text = f"{_status_label_fr(st)} · {_format_duration_short(run.duration_seconds)}"
        if st == "FAILED" and run.error_message:
            detail_text += f" — {run.error_message.splitlines()[0]}"
        detail_lbl = QLabel(detail_text)
        detail_lbl.setWordWrap(True)
        detail_lbl.setAttribute(Qt.WA_TransparentForMouseEvents)
        detail_lbl.setStyleSheet(
            f"font-size: 12px; "
            f"color: {COLORS['danger'] if st == 'FAILED' else COLORS['text_main']}; border: none;"
        )
        row_l.addWidget(detail_lbl, stretch=1)

        arrow = QLabel("→")
        arrow.setAttribute(Qt.WA_TransparentForMouseEvents)
        arrow.setStyleSheet(f"font-size: 13px; color: {COLORS['text_dim']}; border: none;")
        row_l.addWidget(arrow)

        row_btn.clicked.connect(lambda _, rid=run.id: self._on_bubble_run_clicked(rid))
        return row_btn

    def _on_bubble_run_clicked(self, run_id: int):
        """Ligne de la bulle du jour cliquée (A9) — ferme la bulle, ouvre le panneau latéral du
        run (A10) ; jamais run_log_dialog.py directement depuis cet écran (lui-même inchangé,
        toujours utilisé par PipelineDetailDialog — un chemin séparé, pas remplacé ici)."""
        if self._bubble is not None:
            self._bubble.hide()
        self._open_run_panel(run_id)

    def _open_run_panel(self, run_id: int):
        from database import db_manager as db
        run = db.get_run(run_id)
        if not run:
            return
        # get_pipelines() (pas get_pipeline(), singulier) : seul le premier joinedload déjà
        # pipeline.steps — nécessaire à _resolve_step_label() ci-dessous, sans quoi .steps lèverait
        # DetachedInstanceError une fois la session de get_pipeline() refermée (même piège que
        # _open_graph ci-dessus, déjà commenté).
        pipeline = next((p for p in db.get_pipelines() if p.id == run.pipeline_id), None)
        if not pipeline:
            return
        self._side_panel.set_content(self._build_run_panel_content(pipeline, run))
        self._side_panel.open()

    def _build_run_panel_content(self, pipeline, run) -> QWidget:
        """Panneau latéral d'un run (A10) — même patron que le panneau d'échec de Dashboard
        (surtitre/titre/ligne d'info/encadré d'erreur/journal/pied d'actions), sans les
        précisions gated (C3 : mot "planifiée" ; C4 : "de travail, le reste en attente de
        réessai" ; C5/C6 : recherche/filtre/couleurs par ligne dans le journal ; C7 : exporter)."""
        from datetime import datetime

        st = _status_str(run.status)

        content = QWidget()
        content.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(24, 4, 24, 20)
        layout.setSpacing(12)

        eyebrow_color = _PANEL_EYEBROW_COLOR.get(st, "text_dim")
        eyebrow = QLabel(f"EXÉCUTION #{run.id} · {_status_label_fr(st).upper()}")
        eyebrow.setStyleSheet(
            f"color: {COLORS[eyebrow_color]}; font-family: {FONT_MONO}; font-size: 11px; "
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

        today = to_display(datetime.utcnow()).date()
        day = to_display(run.started_at).date() if run.started_at else today
        end_s = fmt_time(run.finished_at) if run.finished_at else "en cours"
        info = QLabel(
            f"{_day_group_label(day, today).lower()} {fmt_time(run.started_at)} → {end_s} · "
            f"{_format_duration_short(run.duration_seconds)}"
        )
        info.setStyleSheet(
            f"color: {COLORS['text_dim']}; font-size: 12px; background: transparent; border: none;")
        layout.addWidget(info)

        if run.error_message:
            step_label = _resolve_step_label(pipeline, run.failed_step_key)
            err_text = f"{step_label} — {run.error_message}" if step_label else run.error_message
            err = QLabel(err_text)
            err.setWordWrap(True)
            err.setStyleSheet(
                f"color: {COLORS['text_main']}; font-family: {FONT_MONO}; font-size: 11.5px; "
                f"background: {COLORS['bg_main']}; border: 1px solid {COLORS['bg_hover']}; "
                f"border-radius: 6px; padding: 10px;"
            )
            layout.addWidget(err)

        log_lbl = QLabel("JOURNAL")
        log_lbl.setStyleSheet(
            f"color: {COLORS['text_muted']}; font-size: 10px; font-weight: 700; "
            f"letter-spacing: 0.06em; background: transparent; border: none;"
        )
        layout.addWidget(log_lbl)

        log_box = QPlainTextEdit()
        log_box.setReadOnly(True)
        log_box.setFont(QFont(FONT_MONO, 10))
        log_box.setStyleSheet(
            f"background: {COLORS['bg_main']}; color: {COLORS['text_main']}; "
            f"border: 1px solid {COLORS['border']}; border-radius: 6px;"
        )
        log_box.setPlainText(_convert_log_text_times(run.log_text, run.started_at))
        layout.addWidget(log_box, stretch=1)

        footer = QHBoxLayout(); footer.setSpacing(8)
        if run.resumable_state_json:
            btn_resume = self._panel_action_button(
                "Reprendre depuis l'échec", outline=COLORS["accent"], text_color=COLORS["accent_pale"])
            btn_resume.clicked.connect(lambda: self._on_resume_from_panel(run.id))
            footer.addWidget(btn_resume)
        if st == "FAILED" and run.failed_step_key:
            btn_graph = self._panel_action_button("Voir dans le graphe")
            btn_graph.clicked.connect(
                lambda: self._on_open_graph_from_panel(pipeline.id, run.id, run.failed_step_key)
            )
            footer.addWidget(btn_graph)
        footer.addStretch()
        layout.addLayout(footer)

        return content

    @staticmethod
    def _panel_action_button(text: str, outline: str = None, text_color: str = None) -> QPushButton:
        """Dupliqué de dashboard_view.py::_treat_action_button (A10) — même raison que
        _format_duration_short : convention déjà suivie par ce module plutôt qu'un import
        inter-vues."""
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

    def _on_resume_from_panel(self, run_id: int):
        """Reprise depuis le panneau (A10) — passe par l'id directement (db.get_run), pas par un
        index de ligne du tableau principal contrairement à _on_resume (bouton de ligne, qui
        connaît déjà sa ligne) : le run ouvert dans le panneau peut provenir de la bulle du jour
        (A9), pas forcément des 100 lignes récentes de self._run_ids."""
        self._side_panel.close()
        from database import db_manager as db
        run = db.get_run(run_id)
        if not run or not run.resumable_state_json:
            return
        pipeline = db.get_pipeline(run.pipeline_id)
        if not pipeline:
            return
        from ui.dialogs import RunProgressDialog
        RunProgressDialog(pipeline.id, pipeline.name, self, resume_from_run_id=run.id).exec()
        self.refresh()

    def _on_open_graph_from_panel(self, pipeline_id: int, run_id: int, failed_step_key: str):
        self._side_panel.close()
        self.open_atelier_run_requested.emit(pipeline_id, run_id, failed_step_key)

    def refresh(self):
        from datetime import datetime

        from database import db_manager as db

        if self._eyebrow_lbl is not None:
            counts_7d = db.get_run_counts_by_day(days=7)
            n_total = sum(c["success"] + c["failed"] + c["cancelled"] for c in counts_7d)
            n_fail = sum(c["failed"] for c in counts_7d)
            self._eyebrow_lbl.setText(
                f"{n_total} EXÉCUTION{'S' if n_total != 1 else ''} SUR 7 JOURS · "
                f"{n_fail} ÉCHEC{'S' if n_fail != 1 else ''}"
            )

        self._refresh_frequency(search=self.inp_search.text().strip())
        self._refresh_audit_log()
        runs = db.get_recent_runs(limit=100)
        self.table.setVisible(bool(runs))
        self._empty_label.setVisible(not runs)

        # A5 : groupes de jours (AUJOURD'HUI/HIER/date) — jour calculé dans le fuseau réglé, même
        # conversion que la colonne Heure (pas le fuseau UTC de stockage). `display_rows` entrelace
        # des lignes d'en-tête (non sélectionnables, `setSpan` sur toute la largeur) et des lignes
        # de run dans le même QTableWidget — un seul tableau, jamais plusieurs (question 6 du
        # plan).
        today = to_display(datetime.utcnow()).date()
        display_rows: list = []
        last_day = None
        for run in runs:
            day = to_display(run.started_at).date() if run.started_at else None
            if day != last_day:
                display_rows.append((None, _day_group_label(day, today) if day else "—"))
                last_day = day
            display_rows.append((run, None))

        self._run_ids = []       # index ligne → run_id (None pour une ligne d'en-tête de groupe)
        self._run_errors = {}    # index ligne → run.error_message (A2, recherche étendue)
        self.table.setRowCount(len(display_rows))
        for r_idx, (run, header_label) in enumerate(display_rows):
            if run is None:
                self._run_ids.append(None)
                self.table.setSpan(r_idx, 0, 1, 7)
                header_item = QTableWidgetItem(header_label)
                header_item.setFlags(Qt.ItemIsEnabled)
                header_item.setForeground(QColor(COLORS["text_dim"]))
                header_item.setFont(QFont(FONT_MONO, 10))
                self.table.setItem(r_idx, 0, header_item)
                self.table.setRowHeight(r_idx, 28)
                continue

            self._run_ids.append(run.id)
            self._run_errors[r_idx] = run.error_message or ""
            pname  = run.pipeline.name if run.pipeline else str(run.pipeline_id)
            st     = _status_str(run.status)
            time_s = fmt_time(run.started_at)
            dur    = _format_duration_short(run.duration_seconds)
            rows_s = (
                f"{run.rows_exported:,}".replace(",", " ")
                if run.rows_exported is not None else "—"
            )
            cells  = [time_s, pname, dur, rows_s, st, run.remote_path or "—"]
            for c_idx, cell in enumerate(cells):
                if c_idx == 4:
                    badge = _make_status_badge(_status_label_fr(st), _STATUS_BADGE.get(st, "badge_idle"))
                    badge.setProperty("status_code", st)
                    self.table.setCellWidget(r_idx, c_idx, badge)
                else:
                    item = QTableWidgetItem(cell)
                    item.setForeground(QColor(COLORS["text_dim"] if c_idx == 5 else COLORS["text_main"]))
                    if c_idx == 5:
                        item.setFont(QFont(FONT_MONO, 11))
                    self.table.setItem(r_idx, c_idx, item)

            w = QWidget(); hl = QHBoxLayout(w); hl.setContentsMargins(4, 4, 4, 4)
            hl.setSpacing(4)

            # A8 : la loupe "Voir le log complet" disparaît (ouverture désormais par double-clic
            # sur la ligne, T6 — _on_row_dbl_click, inchangé) ; une icône "Reprendre depuis
            # l'échec" apparaît à la place quand un état de reprise est persisté sur CE run (même
            # icône/style que Pipelines : fa5s.history, accent_action).
            if run.resumable_state_json:
                btn_resume = _action_btn("fa5s.history", object_name="accent_action",
                                         tooltip="Reprendre depuis l'échec", size=(26, 26))
                btn_resume.clicked.connect(lambda _, i=r_idx: self._on_resume(i))
                hl.addWidget(btn_resume)

            # "Voir dans le graphe" (chantier UX éditeur, Lot 1, B1) — pas seulement st ==
            # "FAILED" : certains échecs n'ont jamais traversé la boucle d'étapes (pipeline
            # introuvable, plafond de concurrence, reprise invalide, exception générique) et
            # n'ont donc jamais de failed_step_key, y compris toute ligne antérieure à cette
            # colonne — le bouton ne doit apparaître que quand il y a réellement un nœud à
            # montrer.
            if st == "FAILED" and run.failed_step_key:
                btn_graph = _action_btn("fa5s.project-diagram", object_name="secondary",
                                        tooltip="Voir dans le graphe", size=(26, 26))
                btn_graph.clicked.connect(lambda _, i=r_idx: self._open_graph(i))
                hl.addWidget(btn_graph)

            self.table.setCellWidget(r_idx, 6, w)

            self.table.setRowHeight(r_idx, 44)

        self._apply_filters()

    def _on_row_dbl_click(self, index):
        self._open_log(index.row())

    def _open_log(self, row: int):
        if row >= len(self._run_ids) or self._run_ids[row] is None:
            return
        from .run_log_dialog import open_run_log_dialog
        open_run_log_dialog(self, self._run_ids[row])

    def _on_resume(self, row: int):
        """"Reprendre depuis l'échec" (A8) — même dialogue que Pipelines (ui/dialogs,
        RunProgressDialog(resume_from_run_id=...)), pas une réimplémentation locale."""
        if row >= len(self._run_ids) or self._run_ids[row] is None:
            return
        from database import db_manager as db

        run = db.get_run(self._run_ids[row])
        if not run or not run.resumable_state_json:
            return
        pipeline = db.get_pipeline(run.pipeline_id)
        if not pipeline:
            return
        from ui.dialogs import RunProgressDialog
        RunProgressDialog(pipeline.id, pipeline.name, self, resume_from_run_id=run.id).exec()
        self.refresh()

    def _open_graph(self, row: int):
        """Lien "Voir dans le graphe" (chantier UX éditeur, Lot 1, B1). db.get_run() ne
        joinedload pas Pipeline — accéder à run.pipeline après la fermeture de sa session
        lèverait DetachedInstanceError ; db.get_pipeline(run.pipeline_id) refait une requête
        dédiée plutôt que de suivre cette relation (même prudence que PipelineDetailDialog).

        Chantier Atelier Pipelines : ouvre désormais l'Atelier plutôt qu'un dialogue modal —
        changement de comportement assumé, pas une régression cachée (voir CHANGELOG) : quitter
        l'Atelier ramène à l'écran "Pipelines" (gestion rapide), pas à l'Historique, puisque
        l'Atelier n'a qu'une seule sortie (back_requested → MainWindow._navigate(1))."""
        if row >= len(self._run_ids) or self._run_ids[row] is None:
            return
        from database import db_manager as db

        run = db.get_run(self._run_ids[row])
        if not run or not run.failed_step_key:
            return
        pipeline = db.get_pipeline(run.pipeline_id)
        if not pipeline:
            return
        self.open_atelier_run_requested.emit(pipeline.id, run.id, run.failed_step_key)

    @staticmethod
    def _build_audit_table(events) -> QTableWidget:
        """A11 : types traduits/colorés (_event_type_label_and_color), détail reformulé à
        l'affichage pour l'import (_translate_audit_detail) — jamais une donnée inventée pour un
        detail vide/sparse (ex. "Création" sans détail reste "—")."""
        table = QTableWidget(0, 5)
        table.setHorizontalHeaderLabels(["Quand", "Type", "Élément", "Auteur", "Ce qui a changé"])
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setShowGrid(False)
        _configure_columns(table, stretch_cols={4})

        table.setRowCount(len(events))
        for r_idx, event in enumerate(events):
            date_s = fmt_datetime(event.timestamp, fmt="%d/%m/%Y %H:%M:%S")
            type_label, type_color_key = _event_type_label_and_color(event.event_type)
            cells = [
                (date_s, "text_main"),
                (type_label, type_color_key),
                (event.pipeline_name or "—", "text_main"),
                (event.actor or "—", "text_main"),
                (_translate_audit_detail(event), "text_dim"),
            ]
            for c_idx, (text, color_key) in enumerate(cells):
                item = QTableWidgetItem(text)
                item.setForeground(QColor(COLORS[color_key]))
                table.setItem(r_idx, c_idx, item)
            table.setRowHeight(r_idx, 36)
        return table

    def _refresh_audit_log(self):
        """Onglet "Journal des modifications" (A11) — même patron que _refresh_frequency : la
        table est reconstruite (pas mise à jour ligne à ligne) et remplacée dans son layout à
        chaque refresh()."""
        from database import db_manager as db

        events = db.get_audit_events(limit=200)
        new_table = self._build_audit_table(events)
        idx = self._mod_layout.indexOf(self.audit_table)
        self._mod_layout.removeWidget(self.audit_table)
        self.audit_table.deleteLater()
        self._mod_layout.insertWidget(idx, new_table)
        self.audit_table = new_table
        self._audit_empty_label.setVisible(not events)

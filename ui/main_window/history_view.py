"""
DataScheduler — ui/main_window/history_view.py
Vue Historique : journal complet des exécutions.
"""

import re

from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton, QFrame, QScrollArea,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView, QStackedLayout,
    QTextEdit, QLineEdit, QFileDialog, QMessageBox, QApplication,
)
from PySide6.QtCore import Qt, QSize, QTimer, Signal
from PySide6.QtGui import QFont, QColor
from ui.styles import COLORS
from ui.time_display import fmt_time, fmt_datetime, fmt_relative, to_display
from ui.components import make_page_header, Bubble, SidePanel
from ui.graph_editor.run_status import node_status_text, format_step_duration
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


# C3 (refonte, lot C-Historique-1, DONNEES.md::D2) : traduction de PipelineRun.trigger_origin —
# None couvre un run d'avant ce lot, ou écrit par un ancien worker (DONNEES.md).
def _origin_label(trigger_origin: str | None, triggered_by_run_id: int | None) -> str:
    if trigger_origin == "SCHEDULED":
        return "Planifié"
    if trigger_origin == "MANUAL":
        return "Manuel"
    if trigger_origin == "TRIGGERED":
        return f"Déclenché ↳ #{triggered_by_run_id}" if triggered_by_run_id else "Déclenché"
    if trigger_origin == "CATCHUP":
        return "Rattrapé"
    if trigger_origin == "RESUME":
        return "Reprise"
    return "—"


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


def _build_steps_section(step_rows) -> QWidget | None:
    """Section « ÉTAPES » du panneau (C4, lot C-Historique-1) — None si `step_rows` est vide (run
    d'avant B1/D1, ou écrit par un ancien worker : la section reste absente, pas d'erreur, comme
    avant ce lot). Traductions statut/durée reprises telles quelles de `run_status.py` (déjà
    écrites pour l'Atelier, C9/atelier-suivi-execution) — aucune nouvelle logique de statut.
    Ordre : celui de `get_run_steps` (ordre d'insertion), pas recalculé ici."""
    if not step_rows:
        return None

    box = QWidget()
    box.setStyleSheet("background: transparent;")
    v = QVBoxLayout(box)
    v.setContentsMargins(0, 0, 0, 0)
    v.setSpacing(8)

    lbl = QLabel("ÉTAPES")
    lbl.setStyleSheet(
        f"color: {COLORS['text_muted']}; font-size: 10px; font-weight: 700; "
        f"letter-spacing: 0.06em; background: transparent; border: none;"
    )
    v.addWidget(lbl)

    # Somme des durées réellement écoulées (SUCCESS/FAILED) — une étape SKIPPED/SKIPPED_RESUME/
    # CANCELLED n'a pas tourné, donc rien à additionner pour elle (started_at/finished_at restent
    # souvent None sur ces lignes).
    total_s = sum(
        (r.finished_at - r.started_at).total_seconds()
        for r in step_rows if r.started_at and r.finished_at
    )
    summary = QLabel(f"{format_step_duration(total_s)} de travail")
    summary.setStyleSheet(
        f"color: {COLORS['text_dim']}; font-size: 11px; background: transparent; border: none;")
    v.addWidget(summary)

    for r in step_rows:
        row = QHBoxLayout(); row.setSpacing(8)
        name = QLabel(r.step_label or r.step_type)
        name.setStyleSheet(
            f"color: {COLORS['text_main']}; font-size: 12px; background: transparent; border: none;")
        row.addWidget(name, stretch=1)
        status_text, color_key = node_status_text(r)
        status_lbl = QLabel(status_text)
        status_lbl.setStyleSheet(
            f"color: {COLORS[color_key]}; font-size: 11px; font-family: {FONT_MONO}; "
            f"background: transparent; border: none;"
        )
        row.addWidget(status_lbl)
        v.addLayout(row)

    return box


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


def _parse_log_text_entries(log_text: str, started_at) -> list[dict]:
    """Analyse ligne à ligne de `log_text` — reconstruit l'heure locale complète (passage de
    minuit géré) et déduit un niveau (« ERROR » si la ligne contient « ERREUR : », sinon
    « INFO ») — repli du journal filtrable (C5, lot C-Historique-1, fiche section B3) pour un run
    d'avant D3 ou écrit par un ancien worker (`log_json` absent). Factorisé hors de
    `_convert_log_text_times` (A10/T3, inchangée en comportement) pour que les deux partagent le
    même algorithme de reconstruction de date. Chaque entrée : `{"time_s": "HH:MM:SS" local, ou
    "" si la ligne ne correspond pas au motif, "lvl": str, "msg": str (sans l'horodatage)}`."""
    if not log_text or not started_at:
        return []
    from datetime import datetime, timedelta

    current_date = started_at.date()
    prev_time = None
    out = []
    for line in log_text.splitlines():
        m = _LOG_LINE_RE.match(line)
        if not m:
            out.append({"time_s": "", "lvl": "INFO", "msg": line})
            continue
        h, mi, s, rest = m.groups()
        t = (int(h), int(mi), int(s))
        if prev_time is not None and t < prev_time:
            current_date += timedelta(days=1)
        prev_time = t
        utc_dt = datetime(current_date.year, current_date.month, current_date.day, *t)
        local_dt = to_display(utc_dt)
        lvl = "ERROR" if "ERREUR : " in rest else "INFO"
        out.append({"time_s": local_dt.strftime("%H:%M:%S"), "lvl": lvl, "msg": rest})
    return out


def _convert_log_text_times(log_text: str, started_at) -> str:
    """Reconstruit l'horodatage complet de chaque ligne de log (A10/T3, DECISIONS.md) —
    PipelineResult.log() (core/pipeline.py) écrit chaque ligne en UTC avec seulement l'heure
    (`[HH:MM:SS]`, pas la date). Comportement inchangé par le lot C-Historique-1 ; ne fait plus
    que mettre en texte le résultat de `_parse_log_text_entries` (même algorithme, partagé avec
    le repli du journal filtrable, C5)."""
    if not log_text or not started_at:
        return log_text or ""
    out_lines = []
    for e in _parse_log_text_entries(log_text, started_at):
        out_lines.append(f"[{e['time_s']}] {e['msg']}" if e["time_s"] else e["msg"])
    return "\n".join(out_lines)


def _log_entries_for_render(run) -> list[dict]:
    """Entrées affichables du journal du panneau (C5) — depuis `log_json` (D3) si renseigné et
    valide, sinon repli sur `log_text` via `_parse_log_text_entries` (fiche, section B3). Chaque
    entrée : `{"time_s", "lvl", "msg"}`, `time_s` déjà en heure locale (`to_display`)."""
    if run.log_json:
        import json
        try:
            raw = json.loads(run.log_json)
        except (TypeError, ValueError):
            raw = None
        if raw:
            from datetime import datetime
            out = []
            for e in raw:
                try:
                    local_dt = to_display(datetime.fromisoformat(e["t"]))
                except (KeyError, ValueError, TypeError):
                    continue
                out.append({
                    "time_s": local_dt.strftime("%H:%M:%S"),
                    "lvl": e.get("lvl") or "INFO",
                    "msg": e.get("msg", ""),
                })
            return out
    return _parse_log_text_entries(run.log_text, run.started_at)


# C5 (lot C-Historique-1) : couleur par niveau — mêmes clés que les badges de statut existants,
# aucune nouvelle clé COLORS. INFO garde la couleur par défaut du journal (text_main).
_LOG_LEVEL_COLOR = {"ERROR": "danger", "WARN": "warning", "OK": "success", "INFO": "text_main"}


def _log_entry_text(entry: dict) -> str:
    prefix = f"[{entry['time_s']}] " if entry["time_s"] else ""
    return prefix + entry["msg"]


def _log_entries_to_text(entries: list[dict]) -> str:
    """Texte brut d'une liste d'entrées déjà filtrée — utilisé par Copier et Exporter (C6/C7)
    pour agir sur exactement ce que `_render_log_entries` vient d'afficher."""
    return "\n".join(_log_entry_text(e) for e in entries)


def _render_log_entries(log_box: QTextEdit, entries: list[dict], errors_only: bool,
                         query: str = "") -> list[dict]:
    """Rendu HTML du journal, une ligne colorée par entrée (C5) — `QTextEdit` plutôt que
    `QPlainTextEdit` (A10, avant ce lot) : seul moyen Qt simple de colorer certaines lignes sans
    widget personnalisé. `query` (C6, lot C-Historique-2) filtre par sous-chaîne sur le message,
    insensible à la casse, appliqué après le filtre de niveau. Retourne les entrées effectivement
    affichées (texte vide si aucune) pour que Copier/Exporter (C6/C7) agissent sur ce qui est
    visible sans dupliquer la logique de filtre."""
    import html as _html
    if not entries:
        log_box.setHtml(f'<div style="color:{COLORS["text_dim"]};">(aucun log enregistré)</div>')
        return []
    by_level = [e for e in entries if not errors_only or e["lvl"] == "ERROR"]
    if not by_level:
        log_box.setHtml(f'<div style="color:{COLORS["text_dim"]};">Aucune erreur dans ce journal.</div>')
        return []
    q = query.strip().lower()
    shown = [e for e in by_level if q in e["msg"].lower()] if q else by_level
    if not shown:
        log_box.setHtml(
            f'<div style="color:{COLORS["text_dim"]};">Aucune ligne ne correspond à la recherche.</div>'
        )
        return []
    lines = []
    for e in shown:
        color = COLORS[_LOG_LEVEL_COLOR.get(e["lvl"], "text_main")]
        lines.append(f'<div style="color:{color};">{_html.escape(_log_entry_text(e))}</div>')
    log_box.setHtml("".join(lines))
    return shown


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

        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels(
            ["Heure", "Pipeline", "Durée", "Lignes", "Statut", "Déclenchement", "Fichier déposé", ""])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setShowGrid(False)
        _configure_columns(self.table, stretch_cols={1, 6})
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
        self.table.setColumnWidth(0, 76)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Fixed)
        self.table.setColumnWidth(4, 130)
        # C3 (lot C-Historique-1) : colonne Déclenchement, entre Statut et Fichier déposé.
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.Fixed)
        self.table.setColumnWidth(5, 130)
        self.table.horizontalHeader().setSectionResizeMode(7, QHeaderView.Fixed)
        # 60px suffisait pour le seul bouton "Voir le log complet" — élargi pour accueillir le
        # second bouton "Voir dans le graphe" (chantier UX éditeur, Lot 1, B1) sans chevauchement
        # ni débordement hors du tableau (2×26px + espacement + marges).
        self.table.setColumnWidth(7, 96)
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
        # Déclenchement (colonne 5, C3) volontairement absent : A2 ne liste que Heure/Pipeline/
        # Durée/Lignes/Statut/Fichier déposé + erreur comme cherchés par la recherche libre.
        search_cols = [0, 1, 2, 3, 4, 6]
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
        run (A10), même panneau que le double-clic sur le tableau principal (_open_log, lot
        C-Historique-1). run_log_dialog.py reste utilisé ailleurs par PipelineDetailDialog — un
        chemin séparé, pas remplacé ici (fiche, question ouverte 3 : hors périmètre tant que le
        bandeau pipeline de C9 n'existe pas)."""
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
        """Panneau latéral d'un run (A10, étendu lot C-Historique-1) — même patron que le
        panneau d'échec de Dashboard (surtitre/titre/ligne d'info/encadré d'erreur/journal/pied
        d'actions). C3 : mot d'origine dans le surtitre. C4 : section ÉTAPES (statique à
        l'ouverture — pas réévaluée par le rafraîchissement en direct ci-dessous, la fiche ne
        l'exige pas). C5 : filtre Tout/Erreurs + couleurs par niveau dans le journal. Pied
        d'actions, "Étape en cours" et rafraîchissement en direct d'un run RUNNING inchangés en
        comportement par rapport à l'ancien run_log_dialog.py (point 7 de "À garder tel quel"),
        désormais portés ici car ce panneau est le seul chemin vers "Historique-run" (_open_log,
        _on_bubble_run_clicked)."""
        from datetime import datetime
        from database import db_manager as db

        content = QWidget()
        content.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(24, 4, 24, 20)
        layout.setSpacing(12)

        eyebrow = QLabel()
        eyebrow.setStyleSheet(
            f"font-family: {FONT_MONO}; font-size: 11px; font-weight: 700; "
            f"letter-spacing: 0.06em; background: transparent; border: none;"
        )
        layout.addWidget(eyebrow)

        def _update_eyebrow(status_code: str, trigger_origin, triggered_by_run_id):
            color = COLORS[_PANEL_EYEBROW_COLOR.get(status_code, "text_dim")]
            origin_s = _origin_label(trigger_origin, triggered_by_run_id)
            eyebrow.setText(f"EXÉCUTION #{run.id} · {_status_label_fr(status_code).upper()} · {origin_s.upper()}")
            eyebrow.setStyleSheet(
                f"color: {color}; font-family: {FONT_MONO}; font-size: 11px; font-weight: 700; "
                f"letter-spacing: 0.06em; background: transparent; border: none;"
            )

        title = QLabel(pipeline.name)
        title.setWordWrap(True)
        title.setStyleSheet(
            f"color: {COLORS['text_main']}; font-size: 20px; font-weight: 700; "
            f"background: transparent; border: none;"
        )
        layout.addWidget(title)

        today = to_display(datetime.utcnow()).date()
        day = to_display(run.started_at).date() if run.started_at else today
        info = QLabel()
        info.setStyleSheet(
            f"color: {COLORS['text_dim']}; font-size: 12px; background: transparent; border: none;")
        layout.addWidget(info)

        def _update_info(finished_at, duration_seconds):
            end_s = fmt_time(finished_at) if finished_at else "en cours"
            info.setText(
                f"{_day_group_label(day, today).lower()} {fmt_time(run.started_at)} → {end_s} · "
                f"{_format_duration_short(duration_seconds)}"
            )

        # "Étape en cours" (point 7 de "À garder tel quel", porté de run_log_dialog.py) —
        # toujours créé, visible seulement tant que le run est RUNNING.
        step_lbl = QLabel()
        step_lbl.setStyleSheet(
            f"color: {COLORS['text_dim']}; font-size: 12px; background: transparent; border: none;")
        step_lbl.setVisible(False)
        layout.addWidget(step_lbl)

        def _update_step_label(current_step_label):
            if current_step_label:
                step_lbl.setText(f"Étape en cours : {current_step_label}")
                step_lbl.setVisible(True)
            else:
                step_lbl.setVisible(False)

        # Encadré d'erreur — toujours créé (comme step_lbl) pour pouvoir apparaître si le run
        # passe de RUNNING à FAILED pendant que le panneau est ouvert.
        err = QLabel()
        err.setWordWrap(True)
        err.setStyleSheet(
            f"color: {COLORS['text_main']}; font-family: {FONT_MONO}; font-size: 11.5px; "
            f"background: {COLORS['bg_main']}; border: 1px solid {COLORS['bg_hover']}; "
            f"border-radius: 6px; padding: 10px;"
        )
        err.setVisible(False)
        layout.addWidget(err)

        def _update_error(error_message, failed_step_key):
            if error_message:
                step_label = _resolve_step_label(pipeline, failed_step_key)
                err.setText(f"{step_label} — {error_message}" if step_label else error_message)
                err.setVisible(True)
            else:
                err.setVisible(False)

        # C4 : section ÉTAPES, statique à l'ouverture (voir docstring).
        steps_section = _build_steps_section(db.get_run_steps(run.id))
        if steps_section is not None:
            layout.addWidget(steps_section)

        log_lbl = QLabel("JOURNAL")
        log_lbl.setStyleSheet(
            f"color: {COLORS['text_muted']}; font-size: 10px; font-weight: 700; "
            f"letter-spacing: 0.06em; background: transparent; border: none;"
        )
        layout.addWidget(log_lbl)

        # C5 : filtre Tout/Erreurs — mêmes couleurs de bascule que les segments de statut
        # (_set_active_status), état purement local à ce panneau (log_filter_state).
        # C6 (lot C-Historique-2) : recherche par sous-chaîne, même ligne, avant le bascule —
        # placement de la maquette (Historique-run.html).
        log_filter_row = QHBoxLayout(); log_filter_row.setSpacing(6)
        log_filter_state = {"errors_only": False, "query": ""}

        inp_log_search = QLineEdit()
        inp_log_search.setPlaceholderText("Chercher dans le journal")
        inp_log_search.setFixedHeight(30)
        inp_log_search.setClearButtonEnabled(True)
        log_filter_row.addWidget(inp_log_search, stretch=1)

        btn_log_all = QPushButton("Tout")
        btn_log_errors = QPushButton("Erreurs")

        def _style_log_filter_btn(btn, active):
            btn.setStyleSheet(
                f"QPushButton {{ padding: 2px 10px; border-radius: 5px; font-size: 11px; "
                f"background: {COLORS['bg_active'] if active else 'transparent'}; "
                f"color: {COLORS['text_main'] if active else COLORS['text_dim']}; "
                f"border: 1px solid {COLORS['accent'] if active else COLORS['border']}; }}"
            )

        def _apply_log_filter():
            _style_log_filter_btn(btn_log_all, not log_filter_state["errors_only"])
            _style_log_filter_btn(btn_log_errors, log_filter_state["errors_only"])
            log_entries_box["shown"] = _render_log_entries(
                log_box, log_entries_box["entries"],
                log_filter_state["errors_only"], log_filter_state["query"],
            )

        def _set_log_filter(errors_only):
            log_filter_state["errors_only"] = errors_only
            _apply_log_filter()

        def _set_log_search(text):
            log_filter_state["query"] = text
            _apply_log_filter()

        inp_log_search.textChanged.connect(_set_log_search)

        for btn, errors_only in ((btn_log_all, False), (btn_log_errors, True)):
            btn.setFixedHeight(24)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda _, v=errors_only: _set_log_filter(v))
            log_filter_row.addWidget(btn)

        btn_log_copy = self._panel_action_button("Copier")

        def _on_copy_log():
            QApplication.clipboard().setText(_log_entries_to_text(log_entries_box["shown"]))

        btn_log_copy.clicked.connect(_on_copy_log)
        log_filter_row.addWidget(btn_log_copy)
        layout.addLayout(log_filter_row)

        log_box = QTextEdit()
        log_box.setReadOnly(True)
        log_box.setFont(QFont(FONT_MONO, 10))
        log_box.setStyleSheet(
            f"background: {COLORS['bg_main']}; color: {COLORS['text_main']}; "
            f"border: 1px solid {COLORS['border']}; border-radius: 6px;"
        )
        layout.addWidget(log_box, stretch=1)

        # Boîte mutable (pas une variable locale simple) pour que _apply_log_filter() voie les
        # entrées rafraîchies par le polling ci-dessous sans dépendre de l'ordre de définition.
        # "shown" (C6/C7) : dernières entrées effectivement affichées, lues par Copier/Exporter.
        log_entries_box = {"entries": _log_entries_for_render(run), "shown": []}
        _apply_log_filter()

        footer = QHBoxLayout(); footer.setSpacing(8)
        if run.resumable_state_json:
            btn_resume = self._panel_action_button(
                "Reprendre depuis l'échec", outline=COLORS["accent"], text_color=COLORS["accent_pale"])
            btn_resume.clicked.connect(lambda: self._on_resume_from_panel(run.id))
            footer.addWidget(btn_resume)
        # Lot atelier-suivi-execution : disponible pour tout run, pas seulement l'échec — voir le
        # commentaire équivalent sur le bouton de ligne ci-dessous (_build_table, colonne 6).
        btn_graph = self._panel_action_button("Voir dans le graphe")
        btn_graph.clicked.connect(
            lambda: self._on_open_graph_from_panel(pipeline.id, run.id, run.failed_step_key)
        )
        footer.addWidget(btn_graph)
        footer.addStretch()

        # C7 (lot C-Historique-2) : exporte le texte actuellement affiché (déjà filtré par niveau
        # et par recherche) — même patron que queries_view.py::_on_export_sql.
        btn_log_export = self._panel_action_button("Exporter le journal")

        def _on_export_log():
            path, _ = QFileDialog.getSaveFileName(
                self, "Exporter le journal", f"run-{run.id}-journal.txt",
                "Fichiers texte (*.txt);;Tous les fichiers (*)",
            )
            if not path:
                return
            try:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(_log_entries_to_text(log_entries_box["shown"]))
            except OSError as e:
                QMessageBox.warning(self, "Export impossible", f"Impossible d'écrire ce fichier : {e}")

        btn_log_export.clicked.connect(_on_export_log)
        footer.addWidget(btn_log_export)
        layout.addLayout(footer)

        _update_eyebrow(_status_str(run.status), run.trigger_origin, run.triggered_by_run_id)
        _update_info(run.finished_at, run.duration_seconds)
        _update_step_label(run.current_step_label)
        _update_error(run.error_message, run.failed_step_key)

        # Rafraîchissement en direct (point 7 de "À garder tel quel", porté de
        # run_log_dialog.py::_refresh_live — même patron que dashboard_view.py l.1213-1236) :
        # s'arrête de lui-même dès que le run quitte RUNNING, ou si le panneau se ferme.
        if _status_str(run.status) == "RUNNING":
            run_id = run.id
            timer = QTimer(content)

            def _poll():
                from database.models import PipelineRun
                with db.get_session() as s:
                    fresh = s.get(PipelineRun, run_id)
                    if not fresh:
                        timer.stop()
                        return
                    new_status = _status_str(fresh.status)
                    _update_eyebrow(new_status, fresh.trigger_origin, fresh.triggered_by_run_id)
                    _update_info(fresh.finished_at, fresh.duration_seconds)
                    _update_step_label(fresh.current_step_label)
                    _update_error(fresh.error_message, fresh.failed_step_key)
                    new_entries = _log_entries_for_render(fresh)
                    if new_entries != log_entries_box["entries"]:
                        log_entries_box["entries"] = new_entries
                        _apply_log_filter()
                    if new_status != "RUNNING":
                        timer.stop()

            timer.setInterval(db.get_app_settings().live_log_refresh_s * 1000)
            timer.timeout.connect(_poll)
            timer.start()
            self._side_panel.closed.connect(timer.stop)

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
                self.table.setSpan(r_idx, 0, 1, 8)
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
            origin_s = _origin_label(run.trigger_origin, run.triggered_by_run_id)
            cells  = [time_s, pname, dur, rows_s, st, origin_s, run.remote_path or "—"]
            for c_idx, cell in enumerate(cells):
                if c_idx == 4:
                    badge = _make_status_badge(_status_label_fr(st), _STATUS_BADGE.get(st, "badge_idle"))
                    badge.setProperty("status_code", st)
                    self.table.setCellWidget(r_idx, c_idx, badge)
                else:
                    item = QTableWidgetItem(cell)
                    item.setForeground(QColor(COLORS["text_dim"] if c_idx in (5, 6) else COLORS["text_main"]))
                    if c_idx == 6:
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

            # "Voir dans le graphe" (chantier UX éditeur, Lot 1, B1 ; lot atelier-suivi-execution :
            # plus seulement pour un échec — la vue d'un run (graph_editor_widget.py::
            # _apply_run_view) montre l'état réel de chaque étape quel que soit le statut du run,
            # réussi compris). run.failed_step_key reste None pour un run réussi (ou un échec
            # survenu hors de la boucle d'étapes — pipeline introuvable, plafond de concurrence,
            # reprise invalide) : accepté par MainWindow.open_atelier_run, aucun nœud surligné
            # dans ce cas, juste le graphe annoté.
            btn_graph = _action_btn("fa5s.project-diagram", object_name="secondary",
                                    tooltip="Voir dans le graphe", size=(26, 26))
            btn_graph.clicked.connect(lambda _, i=r_idx: self._open_graph(i))
            hl.addWidget(btn_graph)

            self.table.setCellWidget(r_idx, 7, w)

            self.table.setRowHeight(r_idx, 44)

        self._apply_filters()

    def _on_row_dbl_click(self, index):
        self._open_log(index.row())

    def _open_log(self, row: int):
        """Double-clic sur une ligne du tableau (T6) — ouvre le panneau latéral A10
        (_open_run_panel), comme la bulle du jour (lot C-Historique-1 : avant ce lot, seule la
        bulle y menait, le tableau ouvrait encore l'ancien run_log_dialog.py — écart avec la
        fiche, qui décrit un seul frame "Historique-run" peu importe le point d'entrée)."""
        if row >= len(self._run_ids) or self._run_ids[row] is None:
            return
        self._open_run_panel(self._run_ids[row])

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
        l'Atelier n'a qu'une seule sortie (back_requested → MainWindow._navigate(1)).

        Lot atelier-suivi-execution : disponible pour tout run, pas seulement FAILED — voir le
        commentaire au-dessus du bouton. run.failed_step_key (souvent None hors échec) est
        transmis tel quel."""
        if row >= len(self._run_ids) or self._run_ids[row] is None:
            return
        from database import db_manager as db

        run = db.get_run(self._run_ids[row])
        if not run:
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

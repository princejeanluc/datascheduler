"""
DataScheduler — ui/main_window/history_view.py
Vue Historique : journal complet des exécutions.
"""

from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton, QFrame, QScrollArea,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView, QComboBox,
)
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QFont, QColor
from ui.styles import COLORS
from .widgets import (
    _icon, _action_btn, _configure_columns, _make_search_input, _make_empty_label,
    _make_title, _make_subtitle, _STATUS_BADGE, _status_str, FONT_MONO, _make_status_badge,
    RunFrequencyHeatmap,
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


class HistoryView(QWidget):
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

        header = QHBoxLayout()
        title_col = QVBoxLayout(); title_col.setSpacing(2)
        title_col.addWidget(_make_title("Historique"))
        title_col.addWidget(_make_subtitle("Journal complet de toutes les exécutions"))
        header.addLayout(title_col); header.addStretch()
        btn_audit = QPushButton("  Journal des modifications"); btn_audit.setObjectName("secondary")
        btn_audit.setFixedHeight(36)
        btn_audit.setIcon(_icon("fa5s.history", COLORS["text_main"]))
        btn_audit.setIconSize(QSize(13, 13))
        btn_audit.clicked.connect(self._on_audit_log)
        header.addWidget(btn_audit)
        self.cb_status = QComboBox()
        self.cb_status.setFixedHeight(34)
        for label, value in _STATUS_FILTER_OPTIONS:
            self.cb_status.addItem(label, value)
        self.cb_status.currentIndexChanged.connect(self._apply_filters)
        header.addWidget(self.cb_status)
        self.inp_search = _make_search_input("Rechercher…")
        self.inp_search.textChanged.connect(self._on_search_changed)
        header.addWidget(self.inp_search)
        layout.addLayout(header)

        sep = QFrame(); sep.setObjectName("separator"); sep.setFrameShape(QFrame.HLine)
        layout.addWidget(sep)

        freq_frame = QFrame(); freq_frame.setObjectName("card")
        freq_layout = QVBoxLayout(freq_frame)
        freq_layout.setContentsMargins(20, 16, 20, 16)
        freq_layout.setSpacing(10)
        freq_title = QLabel("Fréquence d'exécution")
        freq_title.setStyleSheet(
            f"font-size: 13px; font-weight: 700; color: {COLORS['text_main']}; border: none;")
        freq_layout.addWidget(freq_title)
        self._freq_rows_layout = QVBoxLayout()
        self._freq_rows_layout.setSpacing(8)
        freq_layout.addLayout(self._freq_rows_layout)
        self._freq_empty_label = _make_empty_label("Aucun pipeline actif pour l'instant.")
        self._freq_empty_label.setVisible(False)
        freq_layout.addWidget(self._freq_empty_label)
        layout.addWidget(freq_frame)

        self._run_ids = []   # index ligne → run_id

        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(
            ["Pipeline", "Démarré le", "Durée", "Lignes", "Statut", "Fichier déposé", ""])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setShowGrid(False)
        _configure_columns(self.table, stretch_cols={0, 5})
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Fixed)
        self.table.setColumnWidth(4, 130)
        self.table.horizontalHeader().setSectionResizeMode(6, QHeaderView.Fixed)
        # 60px suffisait pour le seul bouton "Voir le log complet" — élargi pour accueillir le
        # second bouton "Voir dans le graphe" (chantier UX éditeur, Lot 1, B1) sans chevauchement
        # ni débordement hors du tableau (2×26px + espacement + marges).
        self.table.setColumnWidth(6, 96)
        self.table.doubleClicked.connect(self._on_row_dbl_click)
        layout.addWidget(self.table)

        self._empty_label = _make_empty_label(
            "Aucune exécution enregistrée pour l'instant."
        )
        self._empty_label.setVisible(False)
        layout.addWidget(self._empty_label)
        layout.addStretch()

        self.refresh()

    def _apply_filters(self, *_args):
        """Combine le filtre de statut (colonne badge, égalité exacte) et la recherche libre
        (sous-chaîne insensible à la casse) — une ligne doit satisfaire les deux pour rester
        visible."""
        status = self.cb_status.currentData()
        needle = self.inp_search.text().strip().lower()
        search_cols = [0, 1, 2, 3, 4, 5]
        for row in range(self.table.rowCount()):
            badge = self.table.cellWidget(row, 4)
            if status is not None and (badge is None or badge.text() != status):
                self.table.setRowHidden(row, True)
                continue
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
            self.table.setRowHidden(row, needle not in " ".join(haystack))

    def _on_search_changed(self, text: str):
        """La recherche filtre à la fois le tableau des exécutions (déjà couvert par
        _apply_filters) et la section "Fréquence d'exécution", qui ne montre par défaut que les
        pipelines les plus actifs — une recherche doit pouvoir en révéler un moins actif, exclu
        de ce plafond par défaut."""
        self._apply_filters()
        self._refresh_frequency(search=text.strip())

    def set_status_filter(self, status: str):
        idx = self.cb_status.findData(status)
        if idx >= 0:
            self.cb_status.setCurrentIndex(idx)
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
            heatmap.day_clicked.connect(lambda day, pl=p: self._on_frequency_day_clicked(pl, day))
            row.addWidget(heatmap)
            row.addStretch()
            self._freq_rows_layout.addWidget(row_widget)

    @staticmethod
    def _build_day_runs_table(runs) -> QTableWidget:
        """Même patron que _build_audit_table() ci-dessous — extrait en méthode statique pour
        être testable sans ouvrir le QDialog qui l'englobe."""
        table = QTableWidget(0, 4)
        table.setHorizontalHeaderLabels(["Heure", "Durée", "Lignes", "Statut"])
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setShowGrid(False)
        _configure_columns(table, stretch_cols={0})
        # Colonne à cellule-widget (badge, pas un QTableWidgetItem) — ResizeToContents la
        # comprime sous la pression de la colonne étirée (même bug déjà rencontré et corrigé
        # sur la colonne "Statut" du tableau principal de cette vue, voir _build_ui() ci-dessus).
        table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Fixed)
        table.setColumnWidth(3, 130)
        table.setRowCount(len(runs))
        for i, r in enumerate(runs):
            time_s = r.started_at.strftime("%H:%M:%S") if r.started_at else "—"
            dur = "—"
            if r.duration_seconds is not None:
                m, s = divmod(int(r.duration_seconds), 60)
                dur = f"{m}m {s:02d}s"
            rows_s = f"{r.rows_exported:,}".replace(",", " ") if r.rows_exported else "—"
            st = _status_str(r.status)
            table.setItem(i, 0, QTableWidgetItem(time_s))
            table.setItem(i, 1, QTableWidgetItem(dur))
            table.setItem(i, 2, QTableWidgetItem(rows_s))
            table.setCellWidget(i, 3, _make_status_badge(st, _STATUS_BADGE.get(st, "badge_idle")))
            table.setRowHeight(i, 40)
        return table

    def _on_frequency_day_clicked(self, pipeline, day):
        """Case du calendrier de fréquence cliquée (chantier identité, vague 4, idée 13) —
        détail des exécutions de CE jour pour CE pipeline, pas juste sa couleur agrégée. Même
        patron que _on_audit_log() ci-dessous : petit QDialog construit à la volée, tableau en
        lecture seule, double-clic sur une ligne ouvre le log complet de ce run."""
        from database import db_manager as db
        runs = db.get_runs_for_pipeline_on_day(pipeline.id, day)
        if not runs:
            return

        from PySide6.QtWidgets import QDialog
        date_s = day.strftime("%d/%m/%Y")
        dlg = QDialog(self)
        dlg.setWindowTitle(f"Exécutions du {date_s} — {pipeline.name}")
        dlg.setMinimumSize(560, 360)
        from ui.styles import DIALOG_STYLE
        dlg.setStyleSheet(DIALOG_STYLE)

        vl = QVBoxLayout(dlg)
        vl.setContentsMargins(20, 16, 20, 16)
        vl.setSpacing(12)

        lbl_title = QLabel(f"Exécutions du {date_s}")
        lbl_title.setStyleSheet(f"font-size: 15px; font-weight: 700; color: {COLORS['text_main']};")
        vl.addWidget(lbl_title)

        table = self._build_day_runs_table(runs)
        run_ids = [r.id for r in runs]

        def _open_full_log(index):
            from .run_log_dialog import open_run_log_dialog
            open_run_log_dialog(dlg, run_ids[index.row()])

        table.doubleClicked.connect(_open_full_log)
        vl.addWidget(table)

        hint = _make_subtitle("Double-cliquer une ligne pour voir le log complet.")
        vl.addWidget(hint)

        btn_close = QPushButton("Fermer")
        btn_close.setFixedHeight(34)
        btn_close.clicked.connect(dlg.accept)
        vl.addWidget(btn_close, alignment=Qt.AlignRight)

        dlg.exec()

    def refresh(self):
        from database import db_manager as db
        self._refresh_frequency(search=self.inp_search.text().strip())
        runs = db.get_recent_runs(limit=100)
        self._run_ids = [r.id for r in runs]
        self.table.setVisible(bool(runs))
        self._empty_label.setVisible(not runs)
        self.table.setRowCount(len(runs))
        for r_idx, run in enumerate(runs):
            pname  = run.pipeline.name if run.pipeline else str(run.pipeline_id)
            st     = _status_str(run.status)
            dur    = "—"
            if run.duration_seconds is not None:
                m, s = divmod(int(run.duration_seconds), 60)
                dur  = f"{m}m {s:02d}s"
            date_s = run.started_at.strftime("%d/%m/%Y %H:%M:%S") if run.started_at else "—"
            rows_s = f"{run.rows_exported:,}".replace(",", " ") if run.rows_exported else "—"
            cells  = [pname, date_s, dur, rows_s, st, run.remote_path or "—"]
            for c_idx, cell in enumerate(cells):
                if c_idx == 4:
                    badge = _make_status_badge(st, _STATUS_BADGE.get(st, "badge_idle"))
                    self.table.setCellWidget(r_idx, c_idx, badge)
                else:
                    item = QTableWidgetItem(cell)
                    item.setForeground(QColor(COLORS["text_dim"] if c_idx == 5 else COLORS["text_main"]))
                    if c_idx == 5:
                        item.setFont(QFont(FONT_MONO, 11))
                    self.table.setItem(r_idx, c_idx, item)

            btn_view = _action_btn("fa5s.search", object_name="secondary",
                                   tooltip="Voir le log complet", size=(26, 26))
            btn_view.clicked.connect(lambda _, i=r_idx: self._open_log(i))
            w = QWidget(); hl = QHBoxLayout(w); hl.setContentsMargins(4, 4, 4, 4)
            hl.setSpacing(4)
            hl.addWidget(btn_view)

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
        if row >= len(self._run_ids):
            return
        from .run_log_dialog import open_run_log_dialog
        open_run_log_dialog(self, self._run_ids[row])

    def _open_graph(self, row: int):
        """Lien "Voir dans le graphe" (chantier UX éditeur, Lot 1, B1). db.get_run() ne
        joinedload pas Pipeline — accéder à run.pipeline après la fermeture de sa session
        lèverait DetachedInstanceError ; db.get_pipeline(run.pipeline_id) refait une requête
        dédiée plutôt que de suivre cette relation (même prudence que PipelineDetailDialog)."""
        if row >= len(self._run_ids):
            return
        from database import db_manager as db
        from ui.graph_editor import PipelineGraphEditorDialog

        run = db.get_run(self._run_ids[row])
        if not run or not run.failed_step_key:
            return
        pipeline = db.get_pipeline(run.pipeline_id)
        if not pipeline:
            return
        PipelineGraphEditorDialog(self, pipeline=pipeline, highlight_step_key=run.failed_step_key).exec()

    @staticmethod
    def _build_audit_table(events) -> QTableWidget:
        table = QTableWidget(0, 5)
        table.setHorizontalHeaderLabels(["Date", "Type", "Pipeline", "Auteur", "Détail"])
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setShowGrid(False)
        _configure_columns(table, stretch_cols={4})

        table.setRowCount(len(events))
        for r_idx, event in enumerate(events):
            date_s = event.timestamp.strftime("%d/%m/%Y %H:%M:%S") if event.timestamp else "—"
            cells = [
                date_s, event.event_type, event.pipeline_name or "—",
                event.actor or "—", event.detail or "—",
            ]
            for c_idx, cell in enumerate(cells):
                item = QTableWidgetItem(cell)
                item.setForeground(QColor(COLORS["text_dim"] if c_idx == 4 else COLORS["text_main"]))
                table.setItem(r_idx, c_idx, item)
            table.setRowHeight(r_idx, 36)
        return table

    def _on_audit_log(self):
        from database import db_manager as db
        events = db.get_audit_events(limit=200)

        from PySide6.QtWidgets import QDialog, QVBoxLayout, QPushButton
        dlg = QDialog(self)
        dlg.setWindowTitle("Journal des modifications")
        dlg.setMinimumSize(760, 480)
        from ui.styles import DIALOG_STYLE
        dlg.setStyleSheet(DIALOG_STYLE)

        vl = QVBoxLayout(dlg)
        vl.setContentsMargins(20, 16, 20, 16)
        vl.setSpacing(12)

        lbl_title = QLabel("Journal des modifications")
        lbl_title.setStyleSheet(f"font-size: 15px; font-weight: 700; color: {COLORS['text_main']};")
        vl.addWidget(lbl_title)

        table = self._build_audit_table(events)
        vl.addWidget(table)

        if not events:
            vl.addWidget(_make_empty_label("Aucun événement enregistré pour l'instant."))

        btn_close = QPushButton("Fermer")
        btn_close.setFixedHeight(34)
        btn_close.clicked.connect(dlg.accept)
        vl.addWidget(btn_close, alignment=Qt.AlignRight)

        dlg.exec()

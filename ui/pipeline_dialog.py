"""
DataScheduler — ui/dialogs/pipeline_dialog.py
Dialogue de création / édition d'un pipeline complet.

Étapes :
  1. Nom + description
  2. Source  : profil Oracle + requête SQL
  3. Export  : séparateur, encodage, chunk size
  4. Destination : profil FTP + templates de nommage
  5. Planification : DAILY / WEEKLY / MONTHLY / CUSTOM
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QLineEdit, QSpinBox, QComboBox, QTextEdit,
    QPushButton, QFrame, QWidget, QStackedWidget,
    QRadioButton, QButtonGroup, QSizePolicy, QTabWidget,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

from ui.styles import COLORS, DIALOG_STYLE


class PipelineDialog(QDialog):
    """
    Dialogue de création ou d'édition d'un pipeline.

    En création : PipelineDialog(parent)
    En édition  : PipelineDialog(parent, pipeline=<Pipeline>)
    """

    DAYS_OF_WEEK = ["Lundi", "Mardi", "Mercredi", "Jeudi",
                    "Vendredi", "Samedi", "Dimanche"]

    def __init__(self, parent=None, pipeline=None):
        super().__init__(parent)
        self._pipeline = pipeline
        self.setWindowTitle("Nouveau pipeline" if pipeline is None else "Modifier le pipeline")
        self.setMinimumWidth(580)
        self.setMinimumHeight(560)
        self.setStyleSheet(DIALOG_STYLE)
        self._load_profiles()
        self._build_ui()
        if pipeline:
            self._fill_fields(pipeline)

    # ── Chargement des données ────────────────

    def _load_profiles(self):
        from database import db_manager as db
        self._oracle_profiles = db.get_oracle_profiles()
        self._ftp_profiles    = db.get_ftp_profiles()
        self._sql_queries     = db.get_sql_queries()

    # ── Construction UI ──────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 20)
        root.setSpacing(16)

        # Titre
        title = QLabel("Configuration du pipeline")
        title.setStyleSheet(f"font-size: 16px; font-weight: 700; color: {COLORS['text_main']};")
        root.addWidget(title)
        root.addWidget(self._sep())

        # Onglets
        tabs = QTabWidget()
        tabs.setStyleSheet(f"""
            QTabWidget::pane {{
                border: 1px solid {COLORS['border']};
                border-radius: 6px;
                background: {COLORS['bg_panel']};
            }}
            QTabBar::tab {{
                background: {COLORS['bg_card']};
                color: {COLORS['text_dim']};
                padding: 8px 20px;
                border: 1px solid {COLORS['border']};
                border-bottom: none;
                border-radius: 5px 5px 0 0;
                font-size: 12px;
                font-weight: 500;
            }}
            QTabBar::tab:selected {{
                background: {COLORS['bg_panel']};
                color: {COLORS['text_main']};
                font-weight: 600;
                border-bottom-color: {COLORS['bg_panel']};
            }}
            QTabBar::tab:hover:!selected {{
                background: {COLORS['bg_hover']};
                color: {COLORS['text_main']};
            }}
        """)

        tabs.addTab(self._build_tab_general(),      "① Général")
        tabs.addTab(self._build_tab_source(),       "② Source")
        tabs.addTab(self._build_tab_export(),       "③ Export CSV")
        tabs.addTab(self._build_tab_destination(),  "④ Destination")
        tabs.addTab(self._build_tab_schedule(),     "⑤ Planification")
        root.addWidget(tabs, stretch=1)

        # Boutons bas
        root.addWidget(self._sep())
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        btn_row.addStretch()

        self.btn_cancel = QPushButton("Annuler")
        self.btn_cancel.setObjectName("secondary")
        self.btn_cancel.setFixedHeight(36)
        self.btn_cancel.clicked.connect(self.reject)

        self.btn_save = QPushButton("Enregistrer le pipeline")
        self.btn_save.setFixedHeight(36)
        self.btn_save.setMinimumWidth(180)
        self.btn_save.clicked.connect(self._on_save)

        btn_row.addWidget(self.btn_cancel)
        btn_row.addWidget(self.btn_save)
        root.addLayout(btn_row)

    # ── Onglet 1 : Général ───────────────────

    def _build_tab_general(self) -> QWidget:
        w = self._tab_widget()
        form = self._form()

        self.inp_name = self._input("ex : EXPORT_VENTES_QUOTIDIEN")
        self.inp_desc = QTextEdit()
        self.inp_desc.setPlaceholderText("Description optionnelle…")
        self.inp_desc.setFixedHeight(80)
        self.inp_desc.setStyleSheet(self._textedit_style())

        form.addRow(self._label("Nom *"),        self.inp_name)
        form.addRow(self._label("Description"),  self.inp_desc)
        w.layout().addLayout(form)
        w.layout().addStretch()
        return w

    # ── Onglet 2 : Source ────────────────────

    def _build_tab_source(self) -> QWidget:
        w = self._tab_widget()
        form = self._form()

        self.cb_oracle = self._combo(
            [(p.name, p.id) for p in self._oracle_profiles],
            empty_label="— Sélectionner un profil Oracle —"
        )
        self.cb_query = self._combo(
            [(q.name, q.id) for q in self._sql_queries],
            empty_label="— Sélectionner une requête SQL —"
        )

        # Aperçu de la requête sélectionnée
        self.lbl_sql_preview = QLabel("Sélectionne une requête pour voir son SQL.")
        self.lbl_sql_preview.setStyleSheet(
            f"color: {COLORS['text_muted']}; font-size: 11px; "
            f"font-family: Consolas; background: {COLORS['bg_card']}; "
            f"border: 1px solid {COLORS['border']}; border-radius: 5px; "
            f"padding: 8px 10px;"
        )
        self.lbl_sql_preview.setWordWrap(True)
        self.lbl_sql_preview.setFixedHeight(80)
        self.cb_query.currentIndexChanged.connect(self._on_query_changed)

        form.addRow(self._label("Profil Oracle *"), self.cb_oracle)
        form.addRow(self._label("Requête SQL *"),   self.cb_query)
        form.addRow(self._label("Aperçu SQL"),      self.lbl_sql_preview)

        w.layout().addLayout(form)
        w.layout().addStretch()
        return w

    # ── Onglet 3 : Export CSV ────────────────

    def _build_tab_export(self) -> QWidget:
        w = self._tab_widget()
        form = self._form()

        self.cb_separator = QComboBox()
        for label, val in [("Virgule (,)", ","), ("Point-virgule (;)", ";"),
                            ("Tabulation (\\t)", "\t"), ("Pipe (|)", "|")]:
            self.cb_separator.addItem(label, val)
        self.cb_separator.setCurrentIndex(1)   # ; par défaut
        self.cb_separator.setStyleSheet(self._combo_style())

        self.cb_encoding = QComboBox()
        for enc in ["utf-8-sig", "utf-8", "latin-1", "cp1252"]:
            self.cb_encoding.addItem(enc)
        self.cb_encoding.setStyleSheet(self._combo_style())

        self.inp_chunk = QSpinBox()
        self.inp_chunk.setRange(1000, 1_000_000)
        self.inp_chunk.setValue(50_000)
        self.inp_chunk.setSingleStep(10_000)
        self.inp_chunk.setSuffix(" lignes")
        self.inp_chunk.setFixedWidth(160)
        self.inp_chunk.setStyleSheet(self._spinbox_style())

        self.cb_quoting = QComboBox()
        for label, val in [
            ("Chaines & dates seulement (défaut)", "QUOTE_NONNUMERIC"),
            ("Minimal — uniquement si nécessaire",  "QUOTE_MINIMAL"),
            ("Tout entre guillemets",               "QUOTE_ALL"),
            ("Aucun guillemet",                     "QUOTE_NONE"),
        ]:
            self.cb_quoting.addItem(label, val)
        self.cb_quoting.setStyleSheet(self._combo_style())

        lbl_hint = QLabel(
            "utf-8-sig recommandé : le BOM permet à Excel d'ouvrir le fichier "
            "sans problème d'accents."
        )
        lbl_hint.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 11px; font-style: italic;")
        lbl_hint.setWordWrap(True)

        lbl_quoting_hint = QLabel(
            "«Minimal» supprime les guillemets autour des chaines et dates. "
            "«Aucun» est risqué si le séparateur peut apparaître dans les données."
        )
        lbl_quoting_hint.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 11px; font-style: italic;")
        lbl_quoting_hint.setWordWrap(True)

        form.addRow(self._label("Séparateur"),    self.cb_separator)
        form.addRow(self._label("Encodage"),      self.cb_encoding)
        form.addRow(self._label("Taille chunk"),  self.inp_chunk)
        form.addRow("",                           lbl_hint)
        form.addRow(self._label("Guillemets CSV"), self.cb_quoting)
        form.addRow("",                            lbl_quoting_hint)

        w.layout().addLayout(form)
        w.layout().addStretch()
        return w

    # ── Onglet 4 : Destination ───────────────

    def _build_tab_destination(self) -> QWidget:
        w = self._tab_widget()
        form = self._form()

        self.cb_ftp = self._combo(
            [(p.name, p.id) for p in self._ftp_profiles],
            empty_label="— Sélectionner un profil FTP —"
        )

        self.inp_remote_path = self._input("ex : /export/{yyyy}/{MM}/")
        self.inp_filename    = self._input("ex : ventes_{yyyyMMdd}.csv")

        # Tokens d'aide
        tokens_lbl = QLabel(
            "Tokens disponibles :  {yyyy}  {yy}  {MM}  {dd}  {HH}  {mm}  "
            "{yyyyMMdd}  {yyyyMMddHHmm}"
        )
        tokens_lbl.setStyleSheet(
            f"color: {COLORS['text_muted']}; font-size: 11px; "
            f"font-family: Consolas; font-style: italic;"
        )
        tokens_lbl.setWordWrap(True)

        # Aperçu résolu
        self.lbl_path_preview = QLabel()
        self._refresh_path_preview()
        self.lbl_path_preview.setStyleSheet(
            f"color: {COLORS['accent']}; font-size: 12px; font-family: Consolas; "
            f"background: {COLORS['bg_card']}; border: 1px solid {COLORS['border']}; "
            f"border-radius: 5px; padding: 7px 10px;"
        )
        self.inp_remote_path.textChanged.connect(self._refresh_path_preview)
        self.inp_filename.textChanged.connect(self._refresh_path_preview)

        form.addRow(self._label("Profil FTP *"),      self.cb_ftp)
        form.addRow(self._label("Chemin distant *"),  self.inp_remote_path)
        form.addRow(self._label("Nom du fichier *"),  self.inp_filename)
        form.addRow("",                               tokens_lbl)
        form.addRow(self._label("Aperçu"),            self.lbl_path_preview)

        w.layout().addLayout(form)
        w.layout().addStretch()
        return w

    # ── Onglet 5 : Planification ─────────────

    def _build_tab_schedule(self) -> QWidget:
        w = self._tab_widget()

        # Sélecteur de fréquence
        freq_row = QHBoxLayout()
        freq_row.setSpacing(10)
        self._freq_group = QButtonGroup()
        self._freq_buttons = {}

        for label, key in [("Quotidien", "DAILY"), ("Hebdomadaire", "WEEKLY"),
                            ("Mensuel", "MONTHLY"), ("Personnalisé", "CUSTOM")]:
            rb = QRadioButton(label)
            rb.setStyleSheet(f"color: {COLORS['text_main']}; font-size: 13px;")
            self._freq_group.addButton(rb)
            self._freq_buttons[key] = rb
            freq_row.addWidget(rb)
        freq_row.addStretch()
        self._freq_buttons["DAILY"].setChecked(True)
        self._freq_group.buttonClicked.connect(self._on_freq_changed)

        # Stack des options selon fréquence
        self._sched_stack = QStackedWidget()
        self._sched_stack.addWidget(self._build_sched_daily())    # 0
        self._sched_stack.addWidget(self._build_sched_weekly())   # 1
        self._sched_stack.addWidget(self._build_sched_monthly())  # 2
        self._sched_stack.addWidget(self._build_sched_custom())   # 3

        # Aperçu cron
        self.lbl_cron_preview = QLabel()
        self.lbl_cron_preview.setStyleSheet(
            f"color: {COLORS['accent']}; font-size: 12px; font-family: Consolas; "
            f"background: {COLORS['bg_card']}; border: 1px solid {COLORS['border']}; "
            f"border-radius: 5px; padding: 7px 12px;"
        )
        self._refresh_cron_preview()

        w.layout().addLayout(freq_row)
        w.layout().addSpacing(12)
        w.layout().addWidget(self._sched_stack)
        w.layout().addSpacing(10)
        w.layout().addWidget(QLabel("Expression cron générée :"))
        w.layout().addWidget(self.lbl_cron_preview)
        w.layout().addStretch()
        return w

    def _build_sched_daily(self) -> QWidget:
        w = QWidget()
        hl = QHBoxLayout(w); hl.setContentsMargins(0,0,0,0); hl.setSpacing(10)
        hl.addWidget(QLabel("Heure :"))
        self.inp_daily_time = self._time_input("06:00")
        self.inp_daily_time.textChanged.connect(self._refresh_cron_preview)
        hl.addWidget(self.inp_daily_time)
        hl.addStretch()
        return w

    def _build_sched_weekly(self) -> QWidget:
        w = QWidget()
        hl = QHBoxLayout(w); hl.setContentsMargins(0,0,0,0); hl.setSpacing(10)
        self.cb_weekly_day = QComboBox()
        for i, d in enumerate(self.DAYS_OF_WEEK):
            self.cb_weekly_day.addItem(d, i)
        self.cb_weekly_day.setStyleSheet(self._combo_style())
        self.cb_weekly_day.setFixedWidth(130)
        self.inp_weekly_time = self._time_input("08:00")
        self.cb_weekly_day.currentIndexChanged.connect(self._refresh_cron_preview)
        self.inp_weekly_time.textChanged.connect(self._refresh_cron_preview)
        hl.addWidget(QLabel("Jour :"))
        hl.addWidget(self.cb_weekly_day)
        hl.addWidget(QLabel("Heure :"))
        hl.addWidget(self.inp_weekly_time)
        hl.addStretch()
        return w

    def _build_sched_monthly(self) -> QWidget:
        w = QWidget()
        hl = QHBoxLayout(w); hl.setContentsMargins(0,0,0,0); hl.setSpacing(10)
        self.inp_monthly_day = QSpinBox()
        self.inp_monthly_day.setRange(1, 31)
        self.inp_monthly_day.setValue(1)
        self.inp_monthly_day.setFixedWidth(70)
        self.inp_monthly_day.setStyleSheet(self._spinbox_style())
        self.inp_monthly_time = self._time_input("06:00")
        self.inp_monthly_day.valueChanged.connect(self._refresh_cron_preview)
        self.inp_monthly_time.textChanged.connect(self._refresh_cron_preview)
        hl.addWidget(QLabel("Jour du mois :"))
        hl.addWidget(self.inp_monthly_day)
        hl.addWidget(QLabel("Heure :"))
        hl.addWidget(self.inp_monthly_time)
        hl.addStretch()
        return w

    def _build_sched_custom(self) -> QWidget:
        w = QWidget()
        vl = QVBoxLayout(w); vl.setContentsMargins(0,0,0,0); vl.setSpacing(6)
        self.inp_custom_cron = self._input("ex : 0 6 * * 1-5")
        self.inp_custom_cron.textChanged.connect(self._refresh_cron_preview)
        hint = QLabel("Format :  minute  heure  jour  mois  jour_semaine")
        hint.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 11px; font-family: Consolas;")
        vl.addWidget(self.inp_custom_cron)
        vl.addWidget(hint)
        return w

    # ── Logique planification ────────────────

    def _on_freq_changed(self):
        mapping = {"DAILY": 0, "WEEKLY": 1, "MONTHLY": 2, "CUSTOM": 3}
        for key, btn in self._freq_buttons.items():
            if btn.isChecked():
                self._sched_stack.setCurrentIndex(mapping[key])
                break
        self._refresh_cron_preview()

    def _current_freq(self) -> str:
        for key, btn in self._freq_buttons.items():
            if btn.isChecked():
                return key
        return "DAILY"

    def _refresh_cron_preview(self):
        try:
            freq = self._current_freq()
            if freq == "DAILY":
                t = self.inp_daily_time.text()
                h, m = self._parse_time(t)
                expr = f"{m} {h} * * *"
            elif freq == "WEEKLY":
                dow = self.cb_weekly_day.currentData()
                t   = self.inp_weekly_time.text()
                h, m = self._parse_time(t)
                expr = f"{m} {h} * * {dow}"
            elif freq == "MONTHLY":
                day = self.inp_monthly_day.value()
                t   = self.inp_monthly_time.text()
                h, m = self._parse_time(t)
                expr = f"{m} {h} {day} * *"
            else:
                expr = self.inp_custom_cron.text().strip() or "—"

            self.lbl_cron_preview.setText(f"  {expr}")
            self.lbl_cron_preview.setStyleSheet(
                f"color: {COLORS['accent']}; font-size: 13px; font-family: Consolas; "
                f"background: {COLORS['bg_card']}; border: 1px solid {COLORS['border']}; "
                f"border-radius: 5px; padding: 7px 12px;"
            )
        except Exception:
            self.lbl_cron_preview.setText("  Expression invalide")

    def _parse_time(self, time_str: str):
        parts = time_str.split(":")
        h = int(parts[0]) if parts else 6
        m = int(parts[1]) if len(parts) > 1 else 0
        return h, m

    # ── Aperçu chemin FTP ────────────────────

    def _refresh_path_preview(self):
        from core.ftp import resolve_remote_path
        try:
            path_tpl = self.inp_remote_path.text().strip() or "/export/"
            file_tpl = self.inp_filename.text().strip()    or "fichier_{yyyyMMdd}.csv"
            preview  = resolve_remote_path(path_tpl, file_tpl)
            self.lbl_path_preview.setText(f"  {preview}")
        except Exception:
            self.lbl_path_preview.setText("  —")

    # ── Aperçu SQL ───────────────────────────

    def _on_query_changed(self, index: int):
        if index <= 0 or not self._sql_queries:
            self.lbl_sql_preview.setText("Sélectionne une requête pour voir son SQL.")
            return
        qid = self.cb_query.itemData(index)
        for q in self._sql_queries:
            if q.id == qid:
                preview = q.sql_text[:200] + ("…" if len(q.sql_text) > 200 else "")
                self.lbl_sql_preview.setText(preview)
                return

    # ── Sauvegarde ───────────────────────────

    def _on_save(self):
        if not self._validate():
            return
        from database import db_manager as db

        name       = self.inp_name.text().strip()
        desc       = self.inp_desc.toPlainText().strip()
        oracle_id  = self.cb_oracle.currentData()
        query_id   = self.cb_query.currentData()
        ftp_id     = self.cb_ftp.currentData()
        sep        = self.cb_separator.currentData()
        enc        = self.cb_encoding.currentText()
        chunk      = self.inp_chunk.value()
        quoting    = self.cb_quoting.currentData()
        path_tpl   = self.inp_remote_path.text().strip()
        file_tpl   = self.inp_filename.text().strip()
        freq       = self._current_freq()

        # Heure planifiée
        sched_time = "06:00"
        sched_day  = None
        cron_expr  = None

        if freq == "DAILY":
            sched_time = self.inp_daily_time.text()
        elif freq == "WEEKLY":
            sched_day  = self.cb_weekly_day.currentData()
            sched_time = self.inp_weekly_time.text()
        elif freq == "MONTHLY":
            sched_day  = self.inp_monthly_day.value()
            sched_time = self.inp_monthly_time.text()
        elif freq == "CUSTOM":
            cron_expr  = self.inp_custom_cron.text().strip()

        if self._pipeline:
            with db.get_session() as s:
                from database.models import Pipeline
                p = s.get(Pipeline, self._pipeline.id)
                p.name              = name
                p.description       = desc
                p.oracle_profile_id = oracle_id
                p.sql_query_id      = query_id
                p.ftp_profile_id    = ftp_id
                p.csv_separator     = sep
                p.csv_encoding      = enc
                p.csv_chunk_size    = chunk
                p.csv_quoting       = quoting
                p.remote_path_tpl   = path_tpl
                p.filename_tpl      = file_tpl
                p.frequency         = freq
                p.cron_expression   = cron_expr
                p.scheduled_time    = sched_time
                p.scheduled_day     = sched_day
        else:
            db.create_pipeline(
                name=name, description=desc,
                oracle_profile_id=oracle_id,
                sql_query_id=query_id,
                ftp_profile_id=ftp_id,
                csv_separator=sep, csv_encoding=enc,
                csv_chunk_size=chunk, csv_quoting=quoting,
                remote_path_tpl=path_tpl,
                filename_tpl=file_tpl,
                frequency=freq,
                cron_expression=cron_expr,
                scheduled_time=sched_time,
                scheduled_day=sched_day,
            )
        self.accept()

    def _validate(self) -> bool:
        if not self.inp_name.text().strip():
            self._flash(self.inp_name, "Nom requis"); return False
        if self.cb_oracle.currentData() is None:
            return False
        if self.cb_query.currentData() is None:
            return False
        if self.cb_ftp.currentData() is None:
            return False
        if not self.inp_remote_path.text().strip():
            self._flash(self.inp_remote_path, "Chemin requis"); return False
        if not self.inp_filename.text().strip():
            self._flash(self.inp_filename, "Nom de fichier requis"); return False
        return True

    def _fill_fields(self, p):
        self.inp_name.setText(p.name)
        if p.description:
            self.inp_desc.setPlainText(p.description)
        self._set_combo_by_data(self.cb_oracle, p.oracle_profile_id)
        self._set_combo_by_data(self.cb_query,  p.sql_query_id)
        self._set_combo_by_data(self.cb_ftp,    p.ftp_profile_id)

        sep_idx = self.cb_separator.findData(p.csv_separator)
        if sep_idx >= 0: self.cb_separator.setCurrentIndex(sep_idx)
        enc_idx = self.cb_encoding.findText(p.csv_encoding)
        if enc_idx >= 0: self.cb_encoding.setCurrentIndex(enc_idx)
        self.inp_chunk.setValue(p.csv_chunk_size)
        quoting_val = getattr(p, "csv_quoting", "QUOTE_NONNUMERIC") or "QUOTE_NONNUMERIC"
        q_idx = self.cb_quoting.findData(quoting_val)
        if q_idx >= 0: self.cb_quoting.setCurrentIndex(q_idx)
        self.inp_remote_path.setText(p.remote_path_tpl)
        self.inp_filename.setText(p.filename_tpl)

        freq = str(p.frequency).replace("CronFrequency.", "")
        if freq in self._freq_buttons:
            self._freq_buttons[freq].setChecked(True)
            self._on_freq_changed()

        if p.scheduled_time:
            if freq == "DAILY":   self.inp_daily_time.setText(p.scheduled_time)
            if freq == "WEEKLY":  self.inp_weekly_time.setText(p.scheduled_time)
            if freq == "MONTHLY": self.inp_monthly_time.setText(p.scheduled_time)
        if p.scheduled_day is not None:
            if freq == "WEEKLY":
                idx = self.cb_weekly_day.findData(p.scheduled_day)
                if idx >= 0: self.cb_weekly_day.setCurrentIndex(idx)
            if freq == "MONTHLY":
                self.inp_monthly_day.setValue(int(p.scheduled_day))
        if p.cron_expression:
            self.inp_custom_cron.setText(p.cron_expression)

    # ── Helpers visuels ──────────────────────

    def _tab_widget(self) -> QWidget:
        w = QWidget()
        vl = QVBoxLayout(w)
        vl.setContentsMargins(18, 16, 18, 16)
        vl.setSpacing(14)
        return w

    def _form(self) -> QFormLayout:
        f = QFormLayout()
        f.setSpacing(12)
        f.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        f.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)
        return f

    def _combo(self, items: list, empty_label: str = "—") -> QComboBox:
        cb = QComboBox()
        cb.setStyleSheet(self._combo_style())
        cb.addItem(empty_label, None)
        for label, data in items:
            cb.addItem(label, data)
        return cb

    def _set_combo_by_data(self, cb: QComboBox, data):
        for i in range(cb.count()):
            if cb.itemData(i) == data:
                cb.setCurrentIndex(i)
                return

    def _input(self, placeholder="") -> QLineEdit:
        w = QLineEdit()
        w.setPlaceholderText(placeholder)
        w.setFixedHeight(34)
        w.setStyleSheet(self._input_style())
        return w

    def _time_input(self, default="06:00") -> QLineEdit:
        w = QLineEdit(default)
        w.setFixedWidth(80)
        w.setFixedHeight(32)
        w.setStyleSheet(self._input_style())
        return w

    def _flash(self, widget, msg):
        widget.setStyleSheet(self._input_style(error=True))
        widget.setPlaceholderText(msg)
        widget.setFocus()

    def _input_style(self, error=False) -> str:
        border = COLORS["danger"] if error else COLORS["border"]
        return (
            f"QLineEdit {{ background: {COLORS['bg_card']}; border: 1px solid {border}; "
            f"border-radius: 5px; padding: 6px 10px; color: {COLORS['text_main']}; font-size: 13px; }}"
            f"QLineEdit:focus {{ border-color: {COLORS['accent']}; }}"
        )

    def _spinbox_style(self) -> str:
        return (
            f"QSpinBox {{ background: {COLORS['bg_card']}; border: 1px solid {COLORS['border']}; "
            f"border-radius: 5px; padding: 6px 8px; color: {COLORS['text_main']}; font-size: 13px; }}"
            f"QSpinBox:focus {{ border-color: {COLORS['accent']}; }}"
        )

    def _combo_style(self) -> str:
        return (
            f"QComboBox {{ background: {COLORS['bg_card']}; border: 1px solid {COLORS['border']}; "
            f"border-radius: 5px; padding: 6px 10px; color: {COLORS['text_main']}; font-size: 13px; }}"
            f"QComboBox:focus {{ border-color: {COLORS['accent']}; }}"
            f"QComboBox::drop-down {{ border: none; padding-right: 8px; }}"
            f"QComboBox QAbstractItemView {{ background: {COLORS['bg_card']}; "
            f"border: 1px solid {COLORS['border']}; "
            f"selection-background-color: {COLORS['bg_active']}; }}"
        )

    def _textedit_style(self) -> str:
        return (
            f"QTextEdit {{ background: {COLORS['bg_card']}; border: 1px solid {COLORS['border']}; "
            f"border-radius: 5px; padding: 6px 10px; color: {COLORS['text_main']}; font-size: 13px; }}"
            f"QTextEdit:focus {{ border-color: {COLORS['accent']}; }}"
        )

    def _label(self, text: str) -> QLabel:
        l = QLabel(text)
        l.setStyleSheet(f"color: {COLORS['text_dim']}; font-size: 12px; font-weight: 500;")
        return l

    def _sep(self) -> QFrame:
        f = QFrame(); f.setFrameShape(QFrame.HLine)
        f.setStyleSheet(f"background: {COLORS['border']}; max-height: 1px;")
        return f
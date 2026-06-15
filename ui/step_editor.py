"""
DataScheduler — ui/step_editor.py
Éditeur de pipeline flexible : liste d'étapes ordonnées + planification.
"""

import json

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QScrollArea,
    QLabel, QLineEdit, QSpinBox, QComboBox, QTextEdit, QPlainTextEdit,
    QPushButton, QFrame, QWidget, QRadioButton, QButtonGroup,
    QFileDialog, QMessageBox, QSizePolicy, QStackedWidget,
)
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QFont

from ui.styles import COLORS, DIALOG_STYLE

try:
    import qtawesome as qta
    def _icon(name, color=None): return qta.icon(name, color=color or COLORS["text_dim"])
except ImportError:
    def _icon(name, color=None): return None


# ──────────────────────────────────────────────
#  MÉTADONNÉES PAR TYPE D'ÉTAPE
# ──────────────────────────────────────────────

STEP_META = {
    "ORACLE_EXTRACT": {"label": "Extraction Oracle", "color": "#4fc3f7"},
    "FTP_UPLOAD":     {"label": "Envoi FTP",          "color": "#FF7900"},
    "LOCAL_COPY":     {"label": "Copie locale",       "color": "#66bb6a"},
    "PYTHON_SCRIPT":  {"label": "Script Python",      "color": "#ce93d8"},
}

DAYS_OF_WEEK = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]

TOKENS_HINT = "{yyyy}  {yy}  {MM}  {dd}  {HH}  {mm}  {yyyyMMdd}  {yyyyMMddHHmm}  {output_file}"


# ──────────────────────────────────────────────
#  DIALOGUE PRINCIPAL : ÉDITEUR DE PIPELINE
# ──────────────────────────────────────────────

class PipelineEditorDialog(QDialog):
    """Création / édition d'un pipeline avec une liste d'étapes ordonnées."""

    def __init__(self, parent=None, pipeline=None):
        super().__init__(parent)
        self._pipeline   = pipeline
        self._steps_data: list[dict] = []
        self._load_profiles()

        self.setWindowTitle("Nouveau pipeline" if pipeline is None else "Modifier le pipeline")
        self.setMinimumSize(660, 740)
        self.setStyleSheet(DIALOG_STYLE)
        self._build_ui()

        if pipeline:
            self._fill_fields(pipeline)
        else:
            self._rebuild_step_list()

    # ── Données ──────────────────────────────

    def _load_profiles(self):
        from database import db_manager as db
        self._oracle_profiles = db.get_oracle_profiles()
        self._ftp_profiles    = db.get_ftp_profiles()
        self._sql_queries     = db.get_sql_queries()

    # ── Construction UI ──────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Titre fixe
        hdr = QLabel("  Configuration du pipeline")
        hdr.setFixedHeight(48)
        hdr.setStyleSheet(
            f"font-size: 16px; font-weight: 700; color: {COLORS['text_main']};"
            f"padding-left: 28px; border-bottom: 1px solid {COLORS['border']};"
            f"background: {COLORS['bg_panel']};"
        )
        root.addWidget(hdr)

        # Zone scrollable
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        inner = QWidget()
        scroll.setWidget(inner)
        root.addWidget(scroll, stretch=1)

        fr = QVBoxLayout(inner)
        fr.setContentsMargins(28, 20, 28, 12)
        fr.setSpacing(18)

        # ① Général
        fr.addWidget(self._section_label("① Informations générales"))
        f1 = self._form()
        self.inp_name = self._input("ex : EXPORT_VENTES_QUOTIDIEN")
        self.inp_desc = self._input("Description optionnelle")
        f1.addRow(self._label("Nom *"),       self.inp_name)
        f1.addRow(self._label("Description"), self.inp_desc)
        fr.addLayout(f1)
        fr.addWidget(self._sep())

        # ② Étapes
        fr.addWidget(self._section_label("② Étapes du pipeline"))
        hint = QLabel(
            "Les étapes s'exécutent dans l'ordre. "
            "Le fichier produit par une étape est transmis automatiquement à la suivante via {output_file}."
        )
        hint.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 11px; font-style: italic;")
        hint.setWordWrap(True)
        fr.addWidget(hint)

        self._steps_container = QWidget()
        self._steps_layout    = QVBoxLayout(self._steps_container)
        self._steps_layout.setContentsMargins(0, 0, 0, 0)
        self._steps_layout.setSpacing(6)
        fr.addWidget(self._steps_container)

        btn_add = QPushButton("  + Ajouter une étape")
        btn_add.setObjectName("secondary")
        btn_add.setFixedHeight(34)
        btn_add.clicked.connect(self._on_add_step)
        fr.addWidget(btn_add)
        fr.addWidget(self._sep())

        # ③ Planification
        fr.addWidget(self._section_label("③ Planification"))
        fr.addLayout(self._build_schedule_ui())
        fr.addStretch()

        # Boutons bas (fixes)
        sep_btn = QFrame(); sep_btn.setFrameShape(QFrame.HLine)
        sep_btn.setStyleSheet(f"background: {COLORS['border']}; max-height: 1px;")
        root.addWidget(sep_btn)

        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(28, 10, 28, 14)
        btn_row.setSpacing(10)
        btn_row.addStretch()
        btn_cancel = QPushButton("Annuler"); btn_cancel.setObjectName("secondary")
        btn_cancel.setFixedHeight(36); btn_cancel.clicked.connect(self.reject)
        btn_save = QPushButton("Enregistrer le pipeline")
        btn_save.setFixedHeight(36); btn_save.setMinimumWidth(180)
        btn_save.clicked.connect(self._on_save)
        btn_row.addWidget(btn_cancel); btn_row.addWidget(btn_save)
        root.addLayout(btn_row)

    def _build_schedule_ui(self) -> QVBoxLayout:
        vl = QVBoxLayout(); vl.setSpacing(10)

        # Sélecteur fréquence
        freq_row = QHBoxLayout(); freq_row.setSpacing(14)
        self._freq_group   = QButtonGroup()
        self._freq_buttons = {}
        for lbl, key in [("Quotidien","DAILY"), ("Hebdomadaire","WEEKLY"),
                         ("Mensuel","MONTHLY"), ("Personnalisé","CUSTOM")]:
            rb = QRadioButton(lbl)
            rb.setStyleSheet(f"color: {COLORS['text_main']}; font-size: 13px;")
            self._freq_group.addButton(rb)
            self._freq_buttons[key] = rb
            freq_row.addWidget(rb)
        freq_row.addStretch()
        self._freq_buttons["DAILY"].setChecked(True)
        self._freq_group.buttonClicked.connect(self._on_freq_changed)
        vl.addLayout(freq_row)

        # Options par fréquence
        self._w_daily = QWidget()
        hl = QHBoxLayout(self._w_daily); hl.setContentsMargins(0,0,0,0); hl.setSpacing(8)
        self.inp_daily_h = self._time_input("06:00")
        self.inp_daily_h.textChanged.connect(self._refresh_cron)
        hl.addWidget(QLabel("Heure :")); hl.addWidget(self.inp_daily_h); hl.addStretch()

        self._w_weekly = QWidget()
        hl2 = QHBoxLayout(self._w_weekly); hl2.setContentsMargins(0,0,0,0); hl2.setSpacing(8)
        self.cb_week_day = QComboBox()
        self.cb_week_day.setStyleSheet(self._combo_style()); self.cb_week_day.setFixedWidth(130)
        for i, d in enumerate(DAYS_OF_WEEK): self.cb_week_day.addItem(d, i)
        self.inp_weekly_h = self._time_input("08:00")
        self.cb_week_day.currentIndexChanged.connect(self._refresh_cron)
        self.inp_weekly_h.textChanged.connect(self._refresh_cron)
        hl2.addWidget(QLabel("Jour :")); hl2.addWidget(self.cb_week_day)
        hl2.addWidget(QLabel("Heure :")); hl2.addWidget(self.inp_weekly_h); hl2.addStretch()

        self._w_monthly = QWidget()
        hl3 = QHBoxLayout(self._w_monthly); hl3.setContentsMargins(0,0,0,0); hl3.setSpacing(8)
        self.inp_month_day = QSpinBox()
        self.inp_month_day.setRange(1, 28); self.inp_month_day.setValue(1)
        self.inp_month_day.setFixedWidth(70); self.inp_month_day.setStyleSheet(self._spinbox_style())
        self.inp_monthly_h = self._time_input("06:00")
        self.inp_month_day.valueChanged.connect(self._refresh_cron)
        self.inp_monthly_h.textChanged.connect(self._refresh_cron)
        hl3.addWidget(QLabel("Jour du mois :")); hl3.addWidget(self.inp_month_day)
        hl3.addWidget(QLabel("Heure :")); hl3.addWidget(self.inp_monthly_h); hl3.addStretch()

        self._w_custom = QWidget()
        hl4 = QVBoxLayout(self._w_custom); hl4.setContentsMargins(0,0,0,0); hl4.setSpacing(4)
        self.inp_cron = self._input("ex : 0 6 * * 1-5")
        self.inp_cron.textChanged.connect(self._refresh_cron)
        cron_hint = QLabel("Format :  minute  heure  jour  mois  jour_semaine")
        cron_hint.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 11px; font-family: Consolas;")
        hl4.addWidget(self.inp_cron); hl4.addWidget(cron_hint)

        for w in (self._w_daily, self._w_weekly, self._w_monthly, self._w_custom):
            vl.addWidget(w)

        self.lbl_cron = QLabel()
        self.lbl_cron.setStyleSheet(
            f"color: {COLORS['accent']}; font-size: 12px; font-family: Consolas; "
            f"background: {COLORS['bg_card']}; border: 1px solid {COLORS['border']}; "
            f"border-radius: 5px; padding: 7px 12px;"
        )
        vl.addWidget(QLabel("Expression cron générée :"))
        vl.addWidget(self.lbl_cron)

        self._on_freq_changed()
        return vl

    # ── Gestion des étapes ────────────────────

    def _rebuild_step_list(self):
        while self._steps_layout.count():
            item = self._steps_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not self._steps_data:
            lbl = QLabel("Aucune étape — cliquer « + Ajouter une étape »")
            lbl.setStyleSheet(
                f"color: {COLORS['text_muted']}; font-size: 12px; "
                f"font-style: italic; padding: 8px 0;"
            )
            self._steps_layout.addWidget(lbl)
            return

        for i, step in enumerate(self._steps_data):
            self._steps_layout.addWidget(self._make_step_card(i, step))

    def _make_step_card(self, idx: int, step: dict) -> QFrame:
        step_type = step["step_type"]
        meta      = STEP_META.get(step_type, {"label": step_type, "color": COLORS["accent"]})

        card = QFrame()
        card.setStyleSheet(
            f"QFrame {{ background: {COLORS['bg_card']}; "
            f"border: 1px solid {COLORS['border']}; border-radius: 6px; }}"
        )
        hl = QHBoxLayout(card)
        hl.setContentsMargins(12, 8, 8, 8)
        hl.setSpacing(10)

        # Numéro + badge type
        num = QLabel(str(idx + 1))
        num.setStyleSheet(
            f"color: {COLORS['text_muted']}; font-size: 11px; font-weight: 700; "
            f"min-width: 16px; background: transparent; border: none;"
        )
        badge = QLabel(meta["label"])
        badge.setStyleSheet(
            f"background: {meta['color']}22; color: {meta['color']}; "
            f"border: 1px solid {meta['color']}66; border-radius: 4px; "
            f"padding: 2px 8px; font-size: 11px; font-weight: 700; "
            f"background-color: {meta['color']}22;"
        )
        badge.setFixedHeight(22)

        user_label = step.get("label") or ""
        summary    = self._step_summary(step_type, step.get("config", {}))

        info_col = QVBoxLayout(); info_col.setSpacing(2); info_col.setContentsMargins(0,0,0,0)
        top_row  = QHBoxLayout(); top_row.setSpacing(8); top_row.setContentsMargins(0,0,0,0)
        top_row.addWidget(badge)
        if user_label:
            lbl_name = QLabel(user_label)
            lbl_name.setStyleSheet(
                f"color: {COLORS['text_main']}; font-size: 12px; "
                f"font-weight: 600; background: transparent; border: none;"
            )
            top_row.addWidget(lbl_name)
        top_row.addStretch()

        lbl_summary = QLabel(summary)
        lbl_summary.setStyleSheet(
            f"color: {COLORS['text_dim']}; font-size: 11px; "
            f"background: transparent; border: none;"
        )
        lbl_summary.setWordWrap(False)

        info_col.addLayout(top_row)
        info_col.addWidget(lbl_summary)

        hl.addWidget(num)
        hl.addLayout(info_col, stretch=1)

        # Boutons
        def _abtn(icon_name: str, tip: str) -> QPushButton:
            b = QPushButton()
            b.setObjectName("secondary")
            b.setFixedSize(26, 26)
            b.setToolTip(tip)
            ico = _icon(icon_name)
            if ico:
                b.setIcon(ico); b.setIconSize(QSize(12, 12))
            return b

        btn_up   = _abtn("fa5s.chevron-up",   "Monter")
        btn_down = _abtn("fa5s.chevron-down", "Descendre")
        btn_edit = _abtn("fa5s.pencil-alt",   "Modifier")
        btn_del  = _abtn("fa5s.trash-alt",    "Supprimer")

        btn_up.setEnabled(idx > 0)
        btn_down.setEnabled(idx < len(self._steps_data) - 1)

        btn_up.clicked.connect(lambda _, i=idx: self._move_step(i, -1))
        btn_down.clicked.connect(lambda _, i=idx: self._move_step(i, +1))
        btn_edit.clicked.connect(lambda _, i=idx: self._edit_step(i))
        btn_del.clicked.connect(lambda _, i=idx: self._delete_step(i))

        for b in (btn_up, btn_down, btn_edit, btn_del):
            hl.addWidget(b)

        return card

    def _step_summary(self, step_type: str, config: dict) -> str:
        if step_type == "ORACLE_EXTRACT":
            oracle = next((p for p in self._oracle_profiles if p.id == config.get("oracle_profile_id")), None)
            query  = next((q for q in self._sql_queries     if q.id == config.get("sql_query_id")), None)
            parts  = []
            if oracle: parts.append(f"Oracle: {oracle.name}")
            if query:  parts.append(f"Requête: {query.name}")
            return " · ".join(parts) or "(non configuré)"
        elif step_type == "FTP_UPLOAD":
            ftp  = next((p for p in self._ftp_profiles if p.id == config.get("ftp_profile_id")), None)
            path = (config.get("remote_path_tpl", "") + config.get("filename_tpl", ""))[:60]
            parts = []
            if ftp:  parts.append(f"FTP: {ftp.name}")
            if path: parts.append(path)
            return " · ".join(parts) or "(non configuré)"
        elif step_type == "LOCAL_COPY":
            d = config.get("dest_dir", "")
            f = config.get("filename_tpl", "")
            return (f"{d}/{f}" if f else d)[:80] or "(non configuré)"
        elif step_type == "PYTHON_SCRIPT":
            return config.get("script_path", "(non configuré)")[:80]
        return ""

    def _on_add_step(self):
        dlg = StepTypeChooserDialog(self)
        if not dlg.exec():
            return
        step_type  = dlg.chosen_type
        config_dlg = _open_config_dialog(
            step_type, {}, self,
            self._oracle_profiles, self._ftp_profiles, self._sql_queries,
        )
        if config_dlg and config_dlg.exec():
            self._steps_data.append(config_dlg.result_step())
            self._load_profiles()   # re-sync au cas où un profil a été créé inline
            self._rebuild_step_list()

    def _edit_step(self, idx: int):
        step = self._steps_data[idx]
        config_dlg = _open_config_dialog(
            step["step_type"], step.get("config", {}), self,
            self._oracle_profiles, self._ftp_profiles, self._sql_queries,
            label=step.get("label", ""),
        )
        if config_dlg and config_dlg.exec():
            self._steps_data[idx] = config_dlg.result_step()
            self._load_profiles()
            self._rebuild_step_list()

    def _move_step(self, idx: int, direction: int):
        new_idx = idx + direction
        if 0 <= new_idx < len(self._steps_data):
            self._steps_data[idx], self._steps_data[new_idx] = \
                self._steps_data[new_idx], self._steps_data[idx]
            self._rebuild_step_list()

    def _delete_step(self, idx: int):
        self._steps_data.pop(idx)
        self._rebuild_step_list()

    # ── Planification ─────────────────────────

    def _on_freq_changed(self):
        freq = self._current_freq()
        self._w_daily.setVisible(freq == "DAILY")
        self._w_weekly.setVisible(freq == "WEEKLY")
        self._w_monthly.setVisible(freq == "MONTHLY")
        self._w_custom.setVisible(freq == "CUSTOM")
        self._refresh_cron()

    def _current_freq(self) -> str:
        for key, btn in self._freq_buttons.items():
            if btn.isChecked():
                return key
        return "DAILY"

    def _refresh_cron(self):
        try:
            freq = self._current_freq()
            if freq == "DAILY":
                h, m = self._parse_time(self.inp_daily_h.text())
                expr = f"{m} {h} * * *"
            elif freq == "WEEKLY":
                dow  = self.cb_week_day.currentData()
                h, m = self._parse_time(self.inp_weekly_h.text())
                expr = f"{m} {h} * * {dow}"
            elif freq == "MONTHLY":
                day  = self.inp_month_day.value()
                h, m = self._parse_time(self.inp_monthly_h.text())
                expr = f"{m} {h} {day} * *"
            else:
                expr = self.inp_cron.text().strip() or "—"
            self.lbl_cron.setText(f"  {expr}")
        except Exception:
            self.lbl_cron.setText("  Expression invalide")

    @staticmethod
    def _parse_time(s: str):
        parts = s.split(":")
        return int(parts[0]) if parts else 6, int(parts[1]) if len(parts) > 1 else 0

    # ── Sauvegarde ───────────────────────────

    def _on_save(self):
        if not self._validate():
            return

        from database import db_manager as db

        name = self.inp_name.text().strip()
        desc = self.inp_desc.text().strip() or None
        freq = self._current_freq()
        sched_time = "06:00"; sched_day = None; cron_expr = None

        if freq == "DAILY":
            sched_time = self.inp_daily_h.text()
        elif freq == "WEEKLY":
            sched_day  = self.cb_week_day.currentData()
            sched_time = self.inp_weekly_h.text()
        elif freq == "MONTHLY":
            sched_day  = self.inp_month_day.value()
            sched_time = self.inp_monthly_h.text()
        elif freq == "CUSTOM":
            cron_expr  = self.inp_cron.text().strip()

        if self._pipeline:
            with db.get_session() as s:
                from database.models import Pipeline
                p = s.get(Pipeline, self._pipeline.id)
                p.name            = name
                p.description     = desc
                p.frequency       = freq
                p.scheduled_time  = sched_time
                p.scheduled_day   = sched_day
                p.cron_expression = cron_expr
            pipeline_id = self._pipeline.id
        else:
            p = db.create_pipeline(
                name=name, description=desc,
                frequency=freq, scheduled_time=sched_time,
                scheduled_day=sched_day, cron_expression=cron_expr,
            )
            pipeline_id = p.id

        db.save_steps(pipeline_id, self._steps_data)
        self.accept()

    def _validate(self) -> bool:
        if not self.inp_name.text().strip():
            self.inp_name.setStyleSheet(self._input_style(error=True))
            self.inp_name.setFocus()
            return False
        if not self._steps_data:
            QMessageBox.warning(
                self, "Étapes manquantes",
                "Ajoutez au moins une étape avant d'enregistrer.",
            )
            return False
        return True

    # ── Remplissage en édition ────────────────

    def _fill_fields(self, p):
        self.inp_name.setText(p.name)
        self.inp_desc.setText(p.description or "")

        from database import db_manager as db
        for s in db.get_steps(p.id):
            self._steps_data.append({
                "step_type": str(s.step_type).replace("StepType.", ""),
                "label":     s.label or "",
                "config":    json.loads(s.config_json or "{}"),
            })
        self._rebuild_step_list()

        freq = str(p.frequency).replace("CronFrequency.", "") if p.frequency else "DAILY"
        if freq in self._freq_buttons:
            self._freq_buttons[freq].setChecked(True)
            self._on_freq_changed()

        t = p.scheduled_time or "06:00"
        if freq == "DAILY":   self.inp_daily_h.setText(t)
        if freq == "WEEKLY":  self.inp_weekly_h.setText(t)
        if freq == "MONTHLY": self.inp_monthly_h.setText(t)

        if p.scheduled_day is not None:
            if freq == "WEEKLY":
                idx = self.cb_week_day.findData(p.scheduled_day)
                if idx >= 0: self.cb_week_day.setCurrentIndex(idx)
            if freq == "MONTHLY":
                self.inp_month_day.setValue(int(p.scheduled_day))
        if p.cron_expression:
            self.inp_cron.setText(p.cron_expression)

    # ── Helpers visuels ──────────────────────

    def _section_label(self, text: str) -> QLabel:
        l = QLabel(text)
        l.setStyleSheet(
            f"color: {COLORS['accent']}; font-size: 12px; font-weight: 700; letter-spacing: 0.5px;"
        )
        return l

    def _label(self, text: str) -> QLabel:
        l = QLabel(text)
        l.setStyleSheet(f"color: {COLORS['text_dim']}; font-size: 12px; font-weight: 500;")
        return l

    def _input(self, placeholder="") -> QLineEdit:
        w = QLineEdit(); w.setPlaceholderText(placeholder); w.setFixedHeight(34)
        w.setStyleSheet(self._input_style()); return w

    def _time_input(self, default="06:00") -> QLineEdit:
        w = QLineEdit(default); w.setFixedWidth(80); w.setFixedHeight(32)
        w.setStyleSheet(self._input_style()); return w

    def _input_style(self, error=False) -> str:
        border = COLORS["danger"] if error else COLORS["border"]
        return (
            f"QLineEdit {{ background: {COLORS['bg_card']}; border: 1px solid {border}; "
            f"border-radius: 4px; padding: 6px 10px; color: {COLORS['text_main']}; font-size: 13px; }}"
            f"QLineEdit:focus {{ border-color: {COLORS['accent']}; }}"
        )

    def _spinbox_style(self) -> str:
        return (
            f"QSpinBox {{ background: {COLORS['bg_card']}; border: 1px solid {COLORS['border']}; "
            f"border-radius: 4px; padding: 6px 8px; color: {COLORS['text_main']}; font-size: 13px; }}"
            f"QSpinBox:focus {{ border-color: {COLORS['accent']}; }}"
        )

    def _combo_style(self) -> str:
        return (
            f"QComboBox {{ background: {COLORS['bg_card']}; border: 1px solid {COLORS['border']}; "
            f"border-radius: 4px; padding: 6px 10px; color: {COLORS['text_main']}; font-size: 13px; }}"
            f"QComboBox:focus {{ border-color: {COLORS['accent']}; }}"
            f"QComboBox::drop-down {{ border: none; padding-right: 8px; }}"
            f"QComboBox QAbstractItemView {{ background: {COLORS['bg_card']}; "
            f"border: 1px solid {COLORS['border']}; "
            f"selection-background-color: {COLORS['bg_active']}; color: {COLORS['text_main']}; }}"
        )

    def _form(self) -> QFormLayout:
        f = QFormLayout(); f.setSpacing(10)
        f.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        f.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)
        return f

    def _sep(self) -> QFrame:
        f = QFrame(); f.setFrameShape(QFrame.HLine)
        f.setStyleSheet(f"background: {COLORS['border']}; max-height: 1px;")
        return f


# ──────────────────────────────────────────────
#  CHOIX DU TYPE D'ÉTAPE
# ──────────────────────────────────────────────

class StepTypeChooserDialog(QDialog):
    """Dialogue de sélection du type d'étape à ajouter."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.chosen_type: str = ""
        self.setWindowTitle("Ajouter une étape")
        self.setFixedWidth(420)
        self.setStyleSheet(DIALOG_STYLE)
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(10)

        title = QLabel("Choisir le type d'étape")
        title.setStyleSheet(
            f"font-size: 15px; font-weight: 700; color: {COLORS['text_main']};"
        )
        root.addWidget(title)

        sep = QFrame(); sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet(f"background: {COLORS['border']}; max-height: 1px;")
        root.addWidget(sep)

        descriptions = {
            "ORACLE_EXTRACT": "Connexion Oracle, exécution SQL, export CSV vers fichier temporaire.",
            "FTP_UPLOAD":     "Upload du fichier produit vers un serveur FTP / FTPS / SFTP.",
            "LOCAL_COPY":     "Copie du fichier produit dans un dossier local (avec tokens datetime).",
            "PYTHON_SCRIPT":  "Exécution d'un script Python avec arguments (tokens datetime + contexte).",
        }

        for step_type, desc in descriptions.items():
            meta = STEP_META[step_type]

            btn_row = QFrame()
            btn_row.setCursor(Qt.PointingHandCursor)
            btn_row.setStyleSheet(
                f"QFrame {{ background: {COLORS['bg_card']}; border: 1px solid {COLORS['border']}; "
                f"border-radius: 6px; }}"
                f"QFrame:hover {{ border-color: {meta['color']}; background: {meta['color']}11; }}"
            )
            hl = QHBoxLayout(btn_row)
            hl.setContentsMargins(14, 10, 14, 10)
            hl.setSpacing(14)

            dot = QLabel("●")
            dot.setStyleSheet(
                f"color: {meta['color']}; font-size: 18px; background: transparent; border: none;"
            )
            dot.setFixedWidth(20)

            info_col = QVBoxLayout(); info_col.setSpacing(2)
            lbl_type = QLabel(meta["label"])
            lbl_type.setStyleSheet(
                f"color: {COLORS['text_main']}; font-size: 13px; font-weight: 600; "
                f"background: transparent; border: none;"
            )
            lbl_desc = QLabel(desc)
            lbl_desc.setStyleSheet(
                f"color: {COLORS['text_dim']}; font-size: 11px; "
                f"background: transparent; border: none;"
            )
            lbl_desc.setWordWrap(True)
            info_col.addWidget(lbl_type); info_col.addWidget(lbl_desc)

            hl.addWidget(dot)
            hl.addLayout(info_col, stretch=1)

            # Rendre la card cliquable via mousePressEvent override
            btn_row.mouseReleaseEvent = lambda _, t=step_type: self._choose(t)
            root.addWidget(btn_row)

        root.addSpacing(6)
        btn_cancel = QPushButton("Annuler"); btn_cancel.setObjectName("secondary")
        btn_cancel.setFixedHeight(34); btn_cancel.clicked.connect(self.reject)
        root.addWidget(btn_cancel, alignment=Qt.AlignRight)

    def _choose(self, step_type: str):
        self.chosen_type = step_type
        self.accept()


# ──────────────────────────────────────────────
#  BASE DES DIALOGUES DE CONFIGURATION
# ──────────────────────────────────────────────

class _BaseStepConfigDialog(QDialog):
    """Dialogue de configuration d'une étape (base commune)."""

    STEP_TYPE = ""

    def __init__(self, config: dict, parent=None, label: str = ""):
        super().__init__(parent)
        self._config = config
        self._init_label = label
        self.setMinimumWidth(500)
        self.setStyleSheet(DIALOG_STYLE)

    def result_step(self) -> dict:
        return {
            "step_type": self.STEP_TYPE,
            "label":     self._get_label(),
            "config":    self._collect_config(),
        }

    def _get_label(self) -> str:
        return getattr(self, "inp_label", None) and self.inp_label.text().strip() or ""

    def _collect_config(self) -> dict:
        raise NotImplementedError

    # ── Widgets communs ───────────────────────

    def _add_label_row(self, form: QFormLayout):
        self.inp_label = QLineEdit()
        self.inp_label.setPlaceholderText("ex : Export Ventes (optionnel)")
        self.inp_label.setText(self._init_label)
        self.inp_label.setFixedHeight(34)
        self.inp_label.setStyleSheet(self._input_style())
        form.addRow(self._lbl("Libellé"), self.inp_label)

    def _profile_row(self, form: QFormLayout, label: str, items: list,
                     empty_label: str, new_fn) -> QComboBox:
        cb = QComboBox(); cb.setStyleSheet(self._combo_style())
        cb.addItem(empty_label, None)
        for item in items:
            cb.addItem(item.name, item.id)
        row = QHBoxLayout(); row.setSpacing(6)
        row.addWidget(cb, stretch=1)
        btn_new = QPushButton("+ Nouveau")
        btn_new.setObjectName("secondary"); btn_new.setFixedHeight(30)
        btn_new.setFixedWidth(90)
        btn_new.clicked.connect(lambda: new_fn(cb))
        row.addWidget(btn_new)
        w = QWidget(); w.setLayout(row)
        form.addRow(self._lbl(label), w)
        return cb

    def _tokens_hint(self) -> QLabel:
        lbl = QLabel("Tokens : " + TOKENS_HINT)
        lbl.setStyleSheet(
            f"color: {COLORS['text_muted']}; font-size: 10px; font-family: Consolas; font-style: italic;"
        )
        lbl.setWordWrap(True)
        return lbl

    def _input(self, placeholder="") -> QLineEdit:
        w = QLineEdit(); w.setPlaceholderText(placeholder); w.setFixedHeight(34)
        w.setStyleSheet(self._input_style()); return w

    def _input_style(self, error=False) -> str:
        border = COLORS["danger"] if error else COLORS["border"]
        return (
            f"QLineEdit {{ background: {COLORS['bg_card']}; border: 1px solid {border}; "
            f"border-radius: 4px; padding: 6px 10px; color: {COLORS['text_main']}; font-size: 13px; }}"
            f"QLineEdit:focus {{ border-color: {COLORS['accent']}; }}"
        )

    def _spinbox_style(self) -> str:
        return (
            f"QSpinBox {{ background: {COLORS['bg_card']}; border: 1px solid {COLORS['border']}; "
            f"border-radius: 4px; padding: 6px 8px; color: {COLORS['text_main']}; font-size: 13px; }}"
            f"QSpinBox:focus {{ border-color: {COLORS['accent']}; }}"
        )

    def _combo_style(self) -> str:
        return (
            f"QComboBox {{ background: {COLORS['bg_card']}; border: 1px solid {COLORS['border']}; "
            f"border-radius: 4px; padding: 6px 10px; color: {COLORS['text_main']}; font-size: 13px; }}"
            f"QComboBox:focus {{ border-color: {COLORS['accent']}; }}"
            f"QComboBox::drop-down {{ border: none; padding-right: 8px; }}"
            f"QComboBox QAbstractItemView {{ background: {COLORS['bg_card']}; "
            f"border: 1px solid {COLORS['border']}; "
            f"selection-background-color: {COLORS['bg_active']}; color: {COLORS['text_main']}; }}"
        )

    def _lbl(self, text: str) -> QLabel:
        l = QLabel(text)
        l.setStyleSheet(f"color: {COLORS['text_dim']}; font-size: 12px; font-weight: 500;")
        return l

    def _form(self) -> QFormLayout:
        f = QFormLayout(); f.setSpacing(12)
        f.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        f.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)
        return f

    def _sep(self) -> QFrame:
        f = QFrame(); f.setFrameShape(QFrame.HLine)
        f.setStyleSheet(f"background: {COLORS['border']}; max-height: 1px;")
        return f

    def _buttons(self, root: QVBoxLayout):
        root.addWidget(self._sep())
        btn_row = QHBoxLayout(); btn_row.setSpacing(10); btn_row.addStretch()
        btn_cancel = QPushButton("Annuler"); btn_cancel.setObjectName("secondary")
        btn_cancel.setFixedHeight(36); btn_cancel.clicked.connect(self.reject)
        btn_ok = QPushButton("Valider l'étape")
        btn_ok.setFixedHeight(36); btn_ok.clicked.connect(self._on_ok)
        btn_row.addWidget(btn_cancel); btn_row.addWidget(btn_ok)
        root.addLayout(btn_row)

    def _on_ok(self):
        self.accept()

    @staticmethod
    def _set_combo(cb: QComboBox, value):
        for i in range(cb.count()):
            if cb.itemData(i) == value:
                cb.setCurrentIndex(i); return


# ──────────────────────────────────────────────
#  CONFIG : ORACLE_EXTRACT
# ──────────────────────────────────────────────

class _OracleExtractConfigDialog(_BaseStepConfigDialog):
    STEP_TYPE = "ORACLE_EXTRACT"

    SEPARATORS = [("Point-virgule  ;", ";"), ("Virgule  ,", ","),
                  ("Pipe  |", "|"), ("Tabulation  \\t", "\t")]
    ENCODINGS  = [("UTF-8 BOM (Excel)", "utf-8-sig"), ("UTF-8", "utf-8"),
                  ("Latin-1", "latin-1"), ("CP1252", "cp1252")]
    QUOTINGS   = [
        ("Chaînes & dates seulement", "QUOTE_NONNUMERIC"),
        ("Minimal — si nécessaire",   "QUOTE_MINIMAL"),
        ("Tout entre guillemets",     "QUOTE_ALL"),
        ("Aucun guillemet",           "QUOTE_NONE"),
    ]

    def __init__(self, config: dict, parent=None, label: str = "",
                 oracle_profiles=None, sql_queries=None, ftp_profiles=None):
        super().__init__(config, parent, label)
        self._oracle_profiles = oracle_profiles or []
        self._sql_queries     = sql_queries     or []
        self.setWindowTitle("Étape — Extraction Oracle")
        self.setMinimumSize(540, 500)
        self._build_ui()
        self._prefill()

    def _build_ui(self):
        root = QVBoxLayout(self); root.setContentsMargins(28, 24, 28, 20); root.setSpacing(16)
        title = QLabel("Extraction Oracle → CSV")
        title.setStyleSheet(f"font-size: 15px; font-weight: 700; color: {COLORS['text_main']};")
        root.addWidget(title); root.addWidget(self._sep())

        form = self._form()
        self._add_label_row(form)
        self.cb_oracle = self._profile_row(
            form, "Profil Oracle *",
            self._oracle_profiles, "— Sélectionner un profil Oracle —",
            self._new_oracle_profile,
        )
        self.cb_query = self._profile_row(
            form, "Requête SQL *",
            self._sql_queries, "— Sélectionner une requête SQL —",
            self._new_sql_query,
        )
        self.cb_oracle.currentIndexChanged.connect(self._filter_queries)

        # CSV
        self.cb_sep = QComboBox(); self.cb_sep.setStyleSheet(self._combo_style())
        for lbl, val in self.SEPARATORS: self.cb_sep.addItem(lbl, val)

        self.cb_enc = QComboBox(); self.cb_enc.setStyleSheet(self._combo_style())
        for lbl, val in self.ENCODINGS: self.cb_enc.addItem(lbl, val)

        self.inp_chunk = QSpinBox()
        self.inp_chunk.setRange(1_000, 1_000_000); self.inp_chunk.setValue(50_000)
        self.inp_chunk.setSingleStep(10_000); self.inp_chunk.setSuffix(" lignes")
        self.inp_chunk.setStyleSheet(self._spinbox_style())

        self.cb_quoting = QComboBox(); self.cb_quoting.setStyleSheet(self._combo_style())
        for lbl, val in self.QUOTINGS: self.cb_quoting.addItem(lbl, val)

        form.addRow(self._lbl("Séparateur CSV"),  self.cb_sep)
        form.addRow(self._lbl("Encodage"),        self.cb_enc)
        form.addRow(self._lbl("Taille chunk"),    self.inp_chunk)
        form.addRow(self._lbl("Guillemets CSV"),  self.cb_quoting)
        root.addLayout(form)
        root.addStretch()
        self._buttons(root)

    def _prefill(self):
        c = self._config
        self._set_combo(self.cb_oracle, c.get("oracle_profile_id"))
        self._filter_queries()
        self._set_combo(self.cb_query, c.get("sql_query_id"))
        self._set_combo_by_data(self.cb_sep,     c.get("csv_separator", ";"))
        self._set_combo_by_data(self.cb_enc,     c.get("csv_encoding",  "utf-8-sig"))
        self._set_combo_by_data(self.cb_quoting, c.get("csv_quoting",   "QUOTE_NONNUMERIC"))
        self.inp_chunk.setValue(c.get("csv_chunk_size", 50_000))

    def _filter_queries(self):
        oracle_id = self.cb_oracle.currentData()
        cur_qid   = self.cb_query.currentData()
        self.cb_query.blockSignals(True)
        self.cb_query.clear()
        self.cb_query.addItem("— Sélectionner une requête SQL —", None)
        for q in self._sql_queries:
            if oracle_id is None or q.oracle_profile_id == oracle_id or q.oracle_profile_id is None:
                self.cb_query.addItem(q.name, q.id)
        self._set_combo(self.cb_query, cur_qid)
        self.cb_query.blockSignals(False)

    def _new_oracle_profile(self, cb: QComboBox):
        from ui.dialogs import OracleDialog
        from database import db_manager as db
        if OracleDialog(self).exec():
            self._oracle_profiles = db.get_oracle_profiles()
            cb.clear(); cb.addItem("— Sélectionner un profil Oracle —", None)
            for p in self._oracle_profiles: cb.addItem(p.name, p.id)
            cb.setCurrentIndex(cb.count() - 1)

    def _new_sql_query(self, cb: QComboBox):
        from ui.dialogs import SqlQueryDialog
        from database import db_manager as db
        if SqlQueryDialog(self).exec():
            self._sql_queries = db.get_sql_queries()
            self._filter_queries()
            self._set_combo(cb, self._sql_queries[-1].id if self._sql_queries else None)

    def _collect_config(self) -> dict:
        return {
            "oracle_profile_id": self.cb_oracle.currentData(),
            "sql_query_id":      self.cb_query.currentData(),
            "csv_separator":     self.cb_sep.currentData(),
            "csv_encoding":      self.cb_enc.currentData(),
            "csv_chunk_size":    self.inp_chunk.value(),
            "csv_quoting":       self.cb_quoting.currentData(),
        }

    def _on_ok(self):
        if not self.cb_oracle.currentData():
            QMessageBox.warning(self, "Champ requis", "Sélectionner un profil Oracle.")
            return
        if not self.cb_query.currentData():
            QMessageBox.warning(self, "Champ requis", "Sélectionner une requête SQL.")
            return
        self.accept()

    @staticmethod
    def _set_combo_by_data(cb: QComboBox, value):
        for i in range(cb.count()):
            if cb.itemData(i) == value:
                cb.setCurrentIndex(i); return


# ──────────────────────────────────────────────
#  CONFIG : FTP_UPLOAD
# ──────────────────────────────────────────────

class _FtpUploadConfigDialog(_BaseStepConfigDialog):
    STEP_TYPE = "FTP_UPLOAD"

    def __init__(self, config: dict, parent=None, label: str = "",
                 oracle_profiles=None, sql_queries=None, ftp_profiles=None):
        super().__init__(config, parent, label)
        self._ftp_profiles = ftp_profiles or []
        self.setWindowTitle("Étape — Envoi FTP")
        self._build_ui()
        self._prefill()

    def _build_ui(self):
        root = QVBoxLayout(self); root.setContentsMargins(28, 24, 28, 20); root.setSpacing(16)
        title = QLabel("Envoi FTP / FTPS / SFTP")
        title.setStyleSheet(f"font-size: 15px; font-weight: 700; color: {COLORS['text_main']};")
        root.addWidget(title); root.addWidget(self._sep())

        form = self._form()
        self._add_label_row(form)
        self.cb_ftp = self._profile_row(
            form, "Profil FTP *",
            self._ftp_profiles, "— Sélectionner un profil FTP —",
            self._new_ftp_profile,
        )
        self.inp_path = self._input("ex : /export/{yyyy}/{MM}/")
        self.inp_file = self._input("ex : ventes_{yyyyMMdd}.csv")
        form.addRow(self._lbl("Dossier distant *"), self.inp_path)
        form.addRow(self._lbl("Nom du fichier *"),  self.inp_file)
        form.addRow("", self._tokens_hint())

        # Aperçu
        self.lbl_preview = QLabel()
        self.lbl_preview.setStyleSheet(
            f"color: {COLORS['accent']}; font-size: 12px; font-family: Consolas; "
            f"background: {COLORS['bg_card']}; border: 1px solid {COLORS['border']}; "
            f"border-radius: 5px; padding: 6px 10px;"
        )
        self.inp_path.textChanged.connect(self._refresh_preview)
        self.inp_file.textChanged.connect(self._refresh_preview)
        form.addRow(self._lbl("Aperçu"), self.lbl_preview)
        root.addLayout(form)
        root.addStretch()
        self._buttons(root)

    def _refresh_preview(self):
        from core.ftp import resolve_remote_path
        try:
            preview = resolve_remote_path(
                self.inp_path.text().strip() or "/export/",
                self.inp_file.text().strip() or "fichier_{yyyyMMdd}.csv",
            )
            self.lbl_preview.setText(f"  {preview}")
        except Exception:
            self.lbl_preview.setText("  —")

    def _prefill(self):
        c = self._config
        self._set_combo(self.cb_ftp, c.get("ftp_profile_id"))
        self.inp_path.setText(c.get("remote_path_tpl", ""))
        self.inp_file.setText(c.get("filename_tpl", ""))
        self._refresh_preview()

    def _new_ftp_profile(self, cb: QComboBox):
        from ui.dialogs import FtpDialog
        from database import db_manager as db
        if FtpDialog(self).exec():
            self._ftp_profiles = db.get_ftp_profiles()
            cb.clear(); cb.addItem("— Sélectionner un profil FTP —", None)
            for p in self._ftp_profiles: cb.addItem(p.name, p.id)
            cb.setCurrentIndex(cb.count() - 1)

    def _collect_config(self) -> dict:
        return {
            "ftp_profile_id":  self.cb_ftp.currentData(),
            "remote_path_tpl": self.inp_path.text().strip(),
            "filename_tpl":    self.inp_file.text().strip(),
        }

    def _on_ok(self):
        if not self.cb_ftp.currentData():
            QMessageBox.warning(self, "Champ requis", "Sélectionner un profil FTP.")
            return
        if not self.inp_path.text().strip():
            QMessageBox.warning(self, "Champ requis", "Saisir le dossier distant.")
            return
        if not self.inp_file.text().strip():
            QMessageBox.warning(self, "Champ requis", "Saisir le nom du fichier.")
            return
        self.accept()


# ──────────────────────────────────────────────
#  CONFIG : LOCAL_COPY
# ──────────────────────────────────────────────

class _LocalCopyConfigDialog(_BaseStepConfigDialog):
    STEP_TYPE = "LOCAL_COPY"

    def __init__(self, config: dict, parent=None, label: str = "", **_):
        super().__init__(config, parent, label)
        self.setWindowTitle("Étape — Copie locale")
        self._build_ui()
        self._prefill()

    def _build_ui(self):
        root = QVBoxLayout(self); root.setContentsMargins(28, 24, 28, 20); root.setSpacing(16)
        title = QLabel("Copie locale")
        title.setStyleSheet(f"font-size: 15px; font-weight: 700; color: {COLORS['text_main']};")
        root.addWidget(title); root.addWidget(self._sep())

        form = self._form()
        self._add_label_row(form)

        # Dossier destination
        self.inp_dest = self._input("ex : C:/backup/{yyyy}/{MM}/")
        dir_row = QHBoxLayout(); dir_row.setSpacing(6)
        dir_row.addWidget(self.inp_dest, stretch=1)
        btn_browse = QPushButton("Parcourir…"); btn_browse.setObjectName("secondary")
        btn_browse.setFixedHeight(34); btn_browse.setFixedWidth(100)
        btn_browse.clicked.connect(self._browse_dir)
        dir_row.addWidget(btn_browse)
        dir_widget = QWidget(); dir_widget.setLayout(dir_row)
        form.addRow(self._lbl("Dossier dest. *"), dir_widget)

        self.inp_file = self._input("ex : ventes_{yyyyMMdd}.csv  (vide = même nom)")
        form.addRow(self._lbl("Nom du fichier"),  self.inp_file)
        form.addRow("", self._tokens_hint())

        # Aperçu
        self.lbl_preview = QLabel()
        self.lbl_preview.setStyleSheet(
            f"color: {COLORS['accent']}; font-size: 12px; font-family: Consolas; "
            f"background: {COLORS['bg_card']}; border: 1px solid {COLORS['border']}; "
            f"border-radius: 5px; padding: 6px 10px;"
        )
        self.inp_dest.textChanged.connect(self._refresh_preview)
        self.inp_file.textChanged.connect(self._refresh_preview)
        form.addRow(self._lbl("Aperçu"), self.lbl_preview)
        root.addLayout(form)
        root.addStretch()
        self._buttons(root)

    def _browse_dir(self):
        path = QFileDialog.getExistingDirectory(self, "Choisir le dossier de destination")
        if path:
            self.inp_dest.setText(path)

    def _refresh_preview(self):
        from core.steps.base import StepContext
        ctx  = StepContext()
        dest = ctx.resolve_tokens(self.inp_dest.text().strip() or "C:/backup/")
        fil  = ctx.resolve_tokens(self.inp_file.text().strip() or "fichier.csv")
        self.lbl_preview.setText(f"  {dest}/{fil}")

    def _prefill(self):
        c = self._config
        self.inp_dest.setText(c.get("dest_dir", ""))
        self.inp_file.setText(c.get("filename_tpl", ""))
        self._refresh_preview()

    def _collect_config(self) -> dict:
        return {
            "dest_dir":     self.inp_dest.text().strip(),
            "filename_tpl": self.inp_file.text().strip(),
        }

    def _on_ok(self):
        if not self.inp_dest.text().strip():
            QMessageBox.warning(self, "Champ requis", "Saisir le dossier de destination.")
            return
        self.accept()


# ──────────────────────────────────────────────
#  CONFIG : PYTHON_SCRIPT
# ──────────────────────────────────────────────

class _PythonScriptConfigDialog(_BaseStepConfigDialog):
    STEP_TYPE = "PYTHON_SCRIPT"

    def __init__(self, config: dict, parent=None, label: str = "", **_):
        super().__init__(config, parent, label)
        self.setWindowTitle("Étape — Script Python")
        self.setMinimumSize(540, 520)
        self._build_ui()
        self._prefill()

    def _build_ui(self):
        root = QVBoxLayout(self); root.setContentsMargins(28, 24, 28, 20); root.setSpacing(16)
        title = QLabel("Exécution d'un script Python")
        title.setStyleSheet(f"font-size: 15px; font-weight: 700; color: {COLORS['text_main']};")
        root.addWidget(title); root.addWidget(self._sep())

        form = self._form()
        self._add_label_row(form)

        # Script
        self.inp_script = self._input("ex : C:/scripts/traitement.py")
        script_row = QHBoxLayout(); script_row.setSpacing(6)
        script_row.addWidget(self.inp_script, stretch=1)
        btn_browse = QPushButton("Parcourir…"); btn_browse.setObjectName("secondary")
        btn_browse.setFixedHeight(34); btn_browse.setFixedWidth(100)
        btn_browse.clicked.connect(self._browse_script)
        script_row.addWidget(btn_browse)
        sw = QWidget(); sw.setLayout(script_row)
        form.addRow(self._lbl("Script * (.py)"), sw)

        # Python exe
        self.inp_py_exe = self._input("ex : python  ou  C:/Python311/python.exe")
        form.addRow(self._lbl("Exécutable Python"), self.inp_py_exe)

        # Arguments (un par ligne)
        args_lbl = QLabel("Arguments (un par ligne) :")
        args_lbl.setStyleSheet(f"color: {COLORS['text_dim']}; font-size: 12px; font-weight: 500;")
        root.addLayout(form)
        root.addWidget(args_lbl)

        self.txt_args = QPlainTextEdit()
        self.txt_args.setFont(QFont("Consolas", 11))
        self.txt_args.setPlaceholderText(
            "--date {yyyyMMdd}\n--input {output_file}\n--mode production"
        )
        self.txt_args.setFixedHeight(110)
        self.txt_args.setStyleSheet(
            f"background: {COLORS['bg_main']}; color: {COLORS['text_main']}; "
            f"border: 1px solid {COLORS['border']}; border-radius: 4px; padding: 6px;"
        )
        root.addWidget(self.txt_args)

        hint = QLabel("Tokens disponibles : " + TOKENS_HINT)
        hint.setStyleSheet(
            f"color: {COLORS['text_muted']}; font-size: 10px; font-family: Consolas; font-style: italic;"
        )
        hint.setWordWrap(True)
        root.addWidget(hint)

        form2 = self._form()
        self.inp_workdir = self._input("Dossier de travail (optionnel)")
        workdir_row = QHBoxLayout(); workdir_row.setSpacing(6)
        workdir_row.addWidget(self.inp_workdir, stretch=1)
        btn_wdir = QPushButton("Parcourir…"); btn_wdir.setObjectName("secondary")
        btn_wdir.setFixedHeight(34); btn_wdir.setFixedWidth(100)
        btn_wdir.clicked.connect(self._browse_workdir)
        workdir_row.addWidget(btn_wdir)
        ww = QWidget(); ww.setLayout(workdir_row)
        form2.addRow(self._lbl("Répertoire travail"), ww)

        self.inp_timeout = QSpinBox()
        self.inp_timeout.setRange(10, 86400); self.inp_timeout.setValue(300)
        self.inp_timeout.setSuffix(" s"); self.inp_timeout.setFixedWidth(110)
        self.inp_timeout.setStyleSheet(self._spinbox_style())
        form2.addRow(self._lbl("Timeout"), self.inp_timeout)
        root.addLayout(form2)

        root.addStretch()
        self._buttons(root)

    def _browse_script(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Choisir le script Python", "", "Scripts Python (*.py)"
        )
        if path:
            self.inp_script.setText(path)

    def _browse_workdir(self):
        path = QFileDialog.getExistingDirectory(self, "Répertoire de travail")
        if path:
            self.inp_workdir.setText(path)

    def _prefill(self):
        import sys as _sys
        c = self._config
        self.inp_script.setText(c.get("script_path", ""))
        self.inp_py_exe.setText(c.get("python_executable", _sys.executable))
        args = c.get("args", [])
        self.txt_args.setPlainText("\n".join(args))
        self.inp_workdir.setText(c.get("working_dir", ""))
        self.inp_timeout.setValue(int(c.get("timeout", 300)))

    def _collect_config(self) -> dict:
        import sys as _sys
        raw  = self.txt_args.toPlainText()
        args = [a.strip() for a in raw.splitlines() if a.strip()]
        exe  = self.inp_py_exe.text().strip() or _sys.executable
        return {
            "script_path":        self.inp_script.text().strip(),
            "python_executable":  exe,
            "args":               args,
            "working_dir":        self.inp_workdir.text().strip() or None,
            "timeout":            self.inp_timeout.value(),
        }

    def _on_ok(self):
        if not self.inp_script.text().strip():
            QMessageBox.warning(self, "Champ requis", "Saisir le chemin du script Python.")
            return
        self.accept()


# ──────────────────────────────────────────────
#  FACTORY
# ──────────────────────────────────────────────

def _open_config_dialog(step_type: str, config: dict, parent,
                        oracle_profiles, ftp_profiles, sql_queries,
                        label: str = "") -> _BaseStepConfigDialog | None:
    kwargs = dict(
        config=config, parent=parent, label=label,
        oracle_profiles=oracle_profiles,
        ftp_profiles=ftp_profiles,
        sql_queries=sql_queries,
    )
    mapping = {
        "ORACLE_EXTRACT": _OracleExtractConfigDialog,
        "FTP_UPLOAD":     _FtpUploadConfigDialog,
        "LOCAL_COPY":     _LocalCopyConfigDialog,
        "PYTHON_SCRIPT":  _PythonScriptConfigDialog,
    }
    cls = mapping.get(step_type)
    return cls(**kwargs) if cls else None

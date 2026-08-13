"""
DataScheduler — ui/step_editor/pipeline_editor_dialog.py
Dialogue principal : éditeur de pipeline (liste d'étapes + planification).
"""

import json

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QScrollArea, QLabel,
    QLineEdit, QSpinBox, QComboBox, QPushButton, QFrame, QWidget, QRadioButton,
    QButtonGroup, QCheckBox, QMessageBox,
)
from PySide6.QtCore import Qt, QSize
from ui.styles import COLORS, DIALOG_STYLE
from .common import STEP_META, DAYS_OF_WEEK, _icon
from .step_type_chooser_dialog import StepTypeChooserDialog


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
        self._smtp_profiles   = db.get_smtp_profiles()
        self._db_profiles     = db.list_all_db_profiles()
        self._other_pipelines = [
            p for p in db.get_pipelines()
            if self._pipeline is None or p.id != self._pipeline.id
        ]

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
        fr.addWidget(self._sep())

        # ④ Déclenchement conditionnel
        fr.addWidget(self._section_label("④ Déclenchement conditionnel"))
        fr.addLayout(self._build_trigger_ui())
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

        self.chk_prevent_overlap = QCheckBox("Empêcher les exécutions simultanées de ce pipeline")
        self.chk_prevent_overlap.setStyleSheet(f"color: {COLORS['text_main']};")
        self.chk_prevent_overlap.setToolTip(
            "Si activé, un déclenchement (manuel ou planifié) qui trouve ce pipeline déjà en "
            "cours d'exécution est ignoré (planifié) ou vous propose de l'interrompre (manuel)."
        )
        vl.addWidget(self.chk_prevent_overlap)

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

    def _build_trigger_ui(self) -> QVBoxLayout:
        """Additif à la planification cron ci-dessus, ne la remplace jamais : un pipeline peut
        avoir les deux (un planning ET un déclenchement après un autre pipeline). Hors
        export/import — voir database/db_manager.py::set_pipeline_trigger()."""
        vl = QVBoxLayout(); vl.setSpacing(10)

        hint = QLabel(
            "En plus de sa planification, ce pipeline peut se lancer automatiquement quand un "
            "autre pipeline se termine."
        )
        hint.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 11px; font-style: italic;")
        hint.setWordWrap(True)
        vl.addWidget(hint)

        row = QHBoxLayout(); row.setSpacing(10)
        self.cb_trigger_parent = QComboBox()
        self.cb_trigger_parent.setStyleSheet(self._combo_style())
        self.cb_trigger_parent.addItem("— Aucun (planification seule) —", None)
        for p in self._other_pipelines:
            self.cb_trigger_parent.addItem(p.name, p.id)
        self.cb_trigger_parent.currentIndexChanged.connect(self._on_trigger_parent_changed)

        self.cb_trigger_condition = QComboBox()
        self.cb_trigger_condition.setStyleSheet(self._combo_style())
        self.cb_trigger_condition.addItem("Succès", "SUCCESS")
        self.cb_trigger_condition.addItem("Échec", "FAILURE")
        self.cb_trigger_condition.addItem("Toujours", "ALWAYS")

        row.addWidget(QLabel("Après :")); row.addWidget(self.cb_trigger_parent, stretch=1)
        row.addWidget(QLabel("Si :")); row.addWidget(self.cb_trigger_condition)
        vl.addLayout(row)

        self._on_trigger_parent_changed()
        return vl

    def _on_trigger_parent_changed(self):
        self.cb_trigger_condition.setEnabled(self.cb_trigger_parent.currentData() is not None)

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
        extras = []
        if step.get("retry_count"):
            extras.append(f"retry×{step['retry_count']}")
        if step.get("run_always"):
            extras.append("toujours exécuté")
        if step.get("timeout_s"):
            extras.append(f"délai {step['timeout_s']}s")
        if extras:
            summary = (summary + "  ·  " if summary else "") + " · ".join(extras)

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

    def _db_profile_summary_name(self, config: dict) -> str | None:
        db_type, profile_id = config.get("db_type"), config.get("profile_id")
        p = next((p for p in self._db_profiles
                  if p["db_type"] == db_type and p["id"] == profile_id), None)
        if not p:
            return None
        from ui.dialogs import DB_TYPE_META
        type_label = DB_TYPE_META.get(db_type, {}).get("label", db_type)
        return f"{type_label}: {p['name']}"

    def _step_summary(self, step_type: str, config: dict) -> str:
        if step_type == "DB_EXTRACT":
            profile_s = self._db_profile_summary_name(config)
            query  = next((q for q in self._sql_queries if q.id == config.get("sql_query_id")), None)
            parts  = []
            if profile_s: parts.append(profile_s)
            if query:     parts.append(f"Requête: {query.name}")
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
        elif step_type == "DB_EXECUTE":
            profile_s = self._db_profile_summary_name(config)
            query  = next((q for q in self._sql_queries if q.id == config.get("sql_query_id")), None)
            parts  = []
            if profile_s: parts.append(profile_s)
            if query:     parts.append(f"Requête: {query.name}")
            return " · ".join(parts) or "(non configuré)"
        elif step_type == "FTP_DOWNLOAD":
            ftp  = next((p for p in self._ftp_profiles if p.id == config.get("ftp_profile_id")), None)
            path = config.get("remote_path_tpl", "")[:60]
            parts = []
            if ftp:  parts.append(f"FTP: {ftp.name}")
            if path: parts.append(path)
            return " · ".join(parts) or "(non configuré)"
        elif step_type == "DB_LOAD":
            profile_s = self._db_profile_summary_name(config)
            table  = config.get("table_name", "")
            parts  = []
            if profile_s: parts.append(profile_s)
            if table:     parts.append(f"Table: {table}")
            return " · ".join(parts) or "(non configuré)"
        elif step_type == "EMAIL_NOTIFY":
            smtp = next((p for p in self._smtp_profiles if p.id == config.get("smtp_profile_id")), None)
            to   = config.get("to", "")
            parts = []
            if smtp: parts.append(f"SMTP: {smtp.name}")
            if to:   parts.append(f"→ {to}")
            return " · ".join(parts) or "(non configuré)"
        elif step_type == "HTTP_REQUEST":
            method = config.get("method", "GET")
            url    = config.get("url_tpl", "")
            return f"{method} {url}"[:80] or "(non configuré)"
        elif step_type == "SPARK_SQL":
            query = next((q for q in self._sql_queries if q.id == config.get("sql_query_id")), None)
            parts = []
            if query: parts.append(f"Requête: {query.name}")
            parts.append("avec résultat" if config.get("fetch_result") else "sans résultat")
            return " · ".join(parts) or "(non configuré)"
        elif step_type == "COMPRESS":
            name = config.get("archive_name_tpl", "")
            return name[:80] if name else "(nom auto)"
        elif step_type == "SQOOP_EXPORT":
            hcat = config.get("hcatalog_table", "")
            ora  = config.get("oracle_table", "")
            return f"{hcat} → {ora}"[:80] if (hcat or ora) else "(non configuré)"
        return ""

    def _on_add_step(self):
        from ui.step_editor import _open_config_dialog
        dlg = StepTypeChooserDialog(self)
        if not dlg.exec():
            return
        step_type  = dlg.chosen_type
        config_dlg = _open_config_dialog(
            step_type, {}, self,
            self._oracle_profiles, self._ftp_profiles, self._sql_queries,
            self._smtp_profiles, self._db_profiles,
            prior_steps=self._steps_data,
        )
        if config_dlg and config_dlg.exec():
            self._steps_data.append(config_dlg.result_step())
            self._load_profiles()   # re-sync au cas où un profil a été créé inline
            self._rebuild_step_list()

    def _edit_step(self, idx: int):
        from ui.step_editor import _open_config_dialog
        step = self._steps_data[idx]
        config_dlg = _open_config_dialog(
            step["step_type"], step.get("config", {}), self,
            self._oracle_profiles, self._ftp_profiles, self._sql_queries,
            self._smtp_profiles, self._db_profiles,
            label=step.get("label", ""),
            retry_count=step.get("retry_count", 0),
            run_always=step.get("run_always", False),
            timeout_s=step.get("timeout_s", 0),
            prior_steps=self._steps_data[:idx],
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
        step = self._steps_data[idx]
        name = step.get("label") or STEP_META.get(step["step_type"], {}).get("label", step["step_type"])
        reply = QMessageBox.question(
            self, "Supprimer l'étape",
            f"Supprimer l'étape « {name} » ? Cette action est immédiate et ne peut pas être annulée.",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
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

        prevent_overlap = self.chk_prevent_overlap.isChecked()

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
                p.prevent_overlap = prevent_overlap
            pipeline_id = self._pipeline.id
        else:
            p = db.create_pipeline(
                name=name, description=desc,
                frequency=freq, scheduled_time=sched_time,
                scheduled_day=sched_day, cron_expression=cron_expr,
                prevent_overlap=prevent_overlap,
            )
            pipeline_id = p.id

        db.save_steps(pipeline_id, self._steps_data)

        trigger_parent_id = self.cb_trigger_parent.currentData()
        trigger_condition = self.cb_trigger_condition.currentData() if trigger_parent_id else None
        try:
            db.set_pipeline_trigger(pipeline_id, trigger_parent_id, trigger_condition)
        except ValueError as e:
            QMessageBox.warning(
                self, "Déclenchement non enregistré",
                f"Le pipeline a bien été enregistré, mais le déclenchement conditionnel n'a pas "
                f"pu être appliqué : {e}",
            )

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

        from core.pipeline import validate_step_sequence
        errors, warnings = validate_step_sequence(self._steps_data)
        if errors:
            QMessageBox.warning(
                self, "Séquence d'étapes invalide",
                "Cette séquence d'étapes ne peut pas fonctionner :\n\n"
                + "\n".join(f"• {e}" for e in errors),
            )
            return False
        if warnings:
            reply = QMessageBox.question(
                self, "Avertissement",
                "Certaines étapes \"toujours exécutées\" pourraient tourner sans les données "
                "attendues (par ex. après un échec précoce) :\n\n"
                + "\n".join(f"• {w}" for w in warnings)
                + "\n\nContinuer quand même ?",
                QMessageBox.Yes | QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return False
        return True

    # ── Remplissage en édition ────────────────

    def _fill_fields(self, p):
        self.inp_name.setText(p.name)
        self.inp_desc.setText(p.description or "")

        from database import db_manager as db
        for s in db.get_steps(p.id):
            self._steps_data.append({
                "step_type":   str(s.step_type).replace("StepType.", ""),
                "label":       s.label or "",
                "config":      json.loads(s.config_json or "{}"),
                "retry_count": s.retry_count or 0,
                "run_always":  bool(s.run_always),
                "timeout_s":   s.timeout_s or 0,
            })
        self._rebuild_step_list()

        self.chk_prevent_overlap.setChecked(bool(p.prevent_overlap))

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

        if p.trigger_after_pipeline_id:
            idx = self.cb_trigger_parent.findData(p.trigger_after_pipeline_id)
            if idx >= 0:
                self.cb_trigger_parent.setCurrentIndex(idx)
            cond = str(p.trigger_condition).replace("TriggerCondition.", "") if p.trigger_condition else None
            idx_cond = self.cb_trigger_condition.findData(cond)
            if idx_cond >= 0:
                self.cb_trigger_condition.setCurrentIndex(idx_cond)
        self._on_trigger_parent_changed()

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

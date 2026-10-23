"""
DataScheduler — ui/step_editor/pipeline_settings_panel.py
Contenu réutilisable du panneau "Paramètres du pipeline" (chantier Atelier Pipelines, écran 2) —
extrait de PipelineSettingsDialog (dont tout le contenu vivait jusqu'ici directement dans ce
QDialog) pour pouvoir être hébergé soit dans ce dialogue (conservé comme enveloppe de
compatibilité, voir son docstring), soit directement dans AtelierPipelinesView (panneau de droite
de la vue non-modale intégrée à la fenêtre principale). Ce widget ne construit ni l'en-tête ni la
rangée Annuler/Enregistrer — responsabilité de l'hôte.

Nom, description, actif, planification, déclenchement conditionnel, variables — jamais les
étapes/arêtes, qui restent la responsabilité exclusive de l'éditeur graphique
(ui/graph_editor/graph_editor_widget.py).
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QSpinBox, QComboBox, QPushButton, QFrame,
    QButtonGroup, QCheckBox, QMessageBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QColor
from ui.styles import COLORS, FONT_MONO_STACK, FONT_MONO, FONT_UI
from .common import DAYS_OF_WEEK
from core.expr_lang import compile_expression

_COL_VAR_NAME, _COL_VAR_EXPR = range(2)


def _compute_written_variable_sources(pipeline_id: int) -> dict[str, str]:
    """A15 : une variable par étape du canevas qui l'écrit (SET_VARIABLE/EXTRACT_VARIABLES) —
    import différé de ui.graph_editor.node_facts pour éviter le cycle d'import décrit dans
    graph_editor_widget.py (qui importe ui.step_editor au niveau module)."""
    import json
    from database import db_manager as db
    from ui.graph_editor.node_facts import compute_written_variables

    sources: dict[str, str] = {}
    for s in db.get_steps(pipeline_id):
        step_type = str(s.step_type).replace("StepType.", "")
        config = json.loads(s.config_json or "{}")
        label = s.label or step_type.replace("_", " ").title()
        for var_name in compute_written_variables(step_type, config):
            sources.setdefault(var_name, label)
    return sources


class PipelineSettingsPanel(QWidget):
    """Métadonnées d'un pipeline déjà existant — jamais ses étapes. `save()` remplace l'ancien
    `_on_save` (plus de `self.accept()` — un QWidget n'a pas cette notion) et émet `saved` en cas
    de succès."""

    saved = Signal()

    def __init__(self, parent=None, pipeline=None):
        super().__init__(parent)
        self._pipeline = pipeline

        from database import db_manager as db
        self._other_pipelines = [p for p in db.get_pipelines() if p.id != pipeline.id]

        self._build_ui()
        self._fill_fields(pipeline)

    # ── Construction UI ──────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # A11 : surtitre PIPELINE + case Actif sur la même ligne, nom en titre éditable,
        # description — bloc d'en-tête du panneau (maquette Main.html).
        header = QVBoxLayout()
        header.setContentsMargins(18, 16, 18, 12)
        header.setSpacing(8)

        top_row = QHBoxLayout()
        surtitle = QLabel("PIPELINE")
        surtitle.setStyleSheet(
            f"color: {COLORS['accent_pale']}; font-family: {FONT_MONO_STACK}; font-size: 10px; "
            f"letter-spacing: 0.06em; background: transparent; border: none;"
        )
        top_row.addWidget(surtitle)
        top_row.addStretch()
        self.chk_active = QCheckBox("Actif")
        self.chk_active.setStyleSheet(f"color: {COLORS['text_dim']}; font-size: 12px;")
        self.chk_active.setToolTip(
            "Un pipeline désactivé reste utilisable manuellement (bouton Exécuter), mais ne se "
            "déclenche jamais tout seul — planification et déclenchement conditionnel ignorés."
        )
        top_row.addWidget(self.chk_active)
        header.addLayout(top_row)

        self.inp_name = QLineEdit()
        self.inp_name.setPlaceholderText("ex : EXPORT_VENTES_QUOTIDIEN")
        self.inp_name.setStyleSheet(
            f"QLineEdit {{ background: transparent; border: none; "
            f"border-bottom: 1px solid {COLORS['border']}; color: {COLORS['text_main']}; "
            f"font-size: 17px; font-weight: 600; padding: 2px 0 6px 0; }}"
            f"QLineEdit:focus {{ border-bottom-color: {COLORS['accent']}; }}"
        )
        header.addWidget(self.inp_name)

        self.inp_desc = QLineEdit()
        self.inp_desc.setPlaceholderText("Description optionnelle")
        self.inp_desc.setStyleSheet(
            f"QLineEdit {{ background: transparent; border: none; color: {COLORS['text_dim']}; "
            f"font-size: 12px; padding: 0; }}"
        )
        header.addWidget(self.inp_desc)

        root.addLayout(header)
        root.addWidget(self._sep())

        content = QVBoxLayout()
        content.setContentsMargins(18, 14, 18, 12)
        content.setSpacing(18)

        content.addWidget(self._section_label("PLANIFICATION"))
        content.addLayout(self._build_schedule_ui())

        content.addWidget(self._section_label("DÉCLENCHEMENT EN CHAÎNE"))
        content.addLayout(self._build_trigger_ui())

        content.addWidget(self._section_label("EXÉCUTION"))
        content.addLayout(self._build_execution_ui())

        content.addLayout(self._build_variables_ui())
        content.addStretch()

        root.addLayout(content)

    def _build_schedule_ui(self) -> QVBoxLayout:
        vl = QVBoxLayout(); vl.setSpacing(10)

        # A12 : boutons segmentés (Jour/Semaine/Mois/Cron) remplaçant les anciens QRadioButton —
        # même groupe exclusif, mêmes clés DAILY/WEEKLY/MONTHLY/CUSTOM, même connexion.
        freq_bar = QWidget()
        freq_bar.setStyleSheet(
            f"QWidget {{ background: {COLORS['bg_main']}; border: 1px solid {COLORS['border']}; "
            f"border-radius: 6px; }}"
        )
        freq_row = QHBoxLayout(freq_bar)
        freq_row.setContentsMargins(2, 2, 2, 2); freq_row.setSpacing(2)
        self._freq_group   = QButtonGroup(self)
        self._freq_buttons = {}
        for lbl, key in [("Jour","DAILY"), ("Semaine","WEEKLY"),
                         ("Mois","MONTHLY"), ("Cron","CUSTOM")]:
            btn = QPushButton(lbl)
            btn.setCheckable(True)
            btn.setFixedHeight(28)
            btn.setStyleSheet(self._segment_button_style())
            self._freq_group.addButton(btn)
            self._freq_buttons[key] = btn
            freq_row.addWidget(btn, stretch=1)
        self._freq_buttons["DAILY"].setChecked(True)
        self._freq_group.buttonClicked.connect(self._on_freq_changed)
        vl.addWidget(freq_bar)

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
        cron_hint.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 11px; font-family: {FONT_MONO_STACK};")
        hl4.addWidget(self.inp_cron); hl4.addWidget(cron_hint)

        for w in (self._w_daily, self._w_weekly, self._w_monthly, self._w_custom):
            vl.addWidget(w)

        self.lbl_cron = QLabel()
        self.lbl_cron.setStyleSheet(
            f"color: {COLORS['accent']}; font-size: 12px; font-family: {FONT_MONO_STACK}; "
            f"background: {COLORS['bg_card']}; border: 1px solid {COLORS['border']}; "
            f"border-radius: 5px; padding: 7px 12px;"
        )
        vl.addWidget(QLabel("Expression cron générée :"))
        vl.addWidget(self.lbl_cron)

        self._on_freq_changed()
        return vl

    def _build_execution_ui(self) -> QVBoxLayout:
        """A14 : section EXÉCUTION séparée de la planification — mêmes deux cases et le même
        plafond que l'ancien bloc (déplacés hors de _build_schedule_ui, comportement inchangé)."""
        vl = QVBoxLayout(); vl.setSpacing(10)

        self.chk_prevent_overlap = QCheckBox("Empêcher les exécutions simultanées de ce pipeline")
        self.chk_prevent_overlap.setStyleSheet(f"color: {COLORS['text_main']};")
        self.chk_prevent_overlap.setToolTip(
            "Si activé, un déclenchement (manuel ou planifié) qui trouve ce pipeline déjà en "
            "cours d'exécution est ignoré (planifié) ou vous propose de l'interrompre (manuel)."
        )
        vl.addWidget(self.chk_prevent_overlap)

        self.chk_parallel_execution = QCheckBox("Exécuter les branches indépendantes en parallèle")
        self.chk_parallel_execution.setStyleSheet(f"color: {COLORS['text_main']};")
        self.chk_parallel_execution.setToolTip(
            "Si activé, les étapes de ce pipeline dont toutes les dépendances sont déjà résolues "
            "s'exécutent en même temps (jusqu'au plafond ci-dessous) au lieu de s'enchaîner une "
            "par une — un vrai gain de temps sur un pipeline à branches indépendantes. Sans effet "
            "sur un pipeline linéaire (aucune branche à paralléliser)."
        )
        self.chk_parallel_execution.toggled.connect(self._on_parallel_execution_toggled)
        vl.addWidget(self.chk_parallel_execution)

        self._w_parallel_branches = QWidget()
        pb_row = QHBoxLayout(self._w_parallel_branches)
        pb_row.setContentsMargins(20, 0, 0, 0); pb_row.setSpacing(8)
        self.spin_max_parallel_branches = QSpinBox()
        self.spin_max_parallel_branches.setRange(1, 16)
        self.spin_max_parallel_branches.setValue(4)
        self.spin_max_parallel_branches.setFixedWidth(70)
        self.spin_max_parallel_branches.setStyleSheet(self._spinbox_style())
        pb_row.addWidget(QLabel("Branches en parallèle max :"))
        pb_row.addWidget(self.spin_max_parallel_branches)
        pb_row.addStretch()
        vl.addWidget(self._w_parallel_branches)
        self._w_parallel_branches.setVisible(False)

        return vl

    def _on_parallel_execution_toggled(self, checked: bool):
        self._w_parallel_branches.setVisible(checked)

    def _build_trigger_ui(self) -> QVBoxLayout:
        """Additif à la planification cron ci-dessus, ne la remplace jamais : un pipeline peut
        avoir les deux (un planning ET un déclenchement après un autre pipeline). Hors
        export/import — voir database/db_manager.py::set_pipeline_trigger().
        A13 : phrase « Lancer aussi après [pipeline] si elle [réussit/échoue/se termine] »
        remplaçant les labels « Après : »/« Si : » — mêmes combos, mêmes valeurs SUCCESS/
        FAILURE/ALWAYS (seuls les libellés affichés changent, en verbe plutôt qu'en nom).
        Sur deux lignes plutôt qu'une seule (la maquette laisse le navigateur passer "si elle
        [...]" à la ligne quand ça ne tient pas — un QHBoxLayout ne le fait jamais tout seul et
        forcerait sinon toute la largeur du panneau à s'élargir pour tout faire tenir)."""
        vl = QVBoxLayout(); vl.setSpacing(8)

        row1 = QHBoxLayout(); row1.setSpacing(6)
        row1.addWidget(QLabel("Lancer aussi après"))
        self.cb_trigger_parent = QComboBox()
        self.cb_trigger_parent.setStyleSheet(self._combo_style())
        self.cb_trigger_parent.addItem("— Aucun (planification seule) —", None)
        for p in self._other_pipelines:
            self.cb_trigger_parent.addItem(p.name, p.id)
        self.cb_trigger_parent.currentIndexChanged.connect(self._on_trigger_parent_changed)
        row1.addWidget(self.cb_trigger_parent, stretch=1)
        vl.addLayout(row1)

        row2 = QHBoxLayout(); row2.setSpacing(6)
        row2.addWidget(QLabel("si elle"))
        self.cb_trigger_condition = QComboBox()
        self.cb_trigger_condition.setStyleSheet(self._combo_style())
        self.cb_trigger_condition.addItem("réussit", "SUCCESS")
        self.cb_trigger_condition.addItem("échoue", "FAILURE")
        self.cb_trigger_condition.addItem("se termine", "ALWAYS")
        row2.addWidget(self.cb_trigger_condition)
        row2.addStretch()
        vl.addLayout(row2)

        caption = QLabel("Choix possibles : réussit, échoue, se termine.")
        caption.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 11px;")
        vl.addWidget(caption)

        self._on_trigger_parent_changed()
        return vl

    def _on_trigger_parent_changed(self):
        self.cb_trigger_condition.setEnabled(self.cb_trigger_parent.currentData() is not None)

    def _build_variables_ui(self) -> QVBoxLayout:
        """Variables nommées amorçant ctx.variables avant la première étape (chantier variables
        de pipeline) — même patron de liste dynamique que _SetVariableConfigDialog
        (ui/step_editor/set_variable_config_dialog.py), 2 colonnes seulement : evaluate() renvoie
        déjà une valeur typée, pas de colonne Type/Format. L'ORDRE des lignes compte : la valeur
        par défaut d'une variable peut référencer var:nom d'une variable déclarée plus haut
        (core/pipeline.py les évalue une par une, dans l'ordre déclaré).
        A15 : surtitre VARIABLES et lien « + Ajouter » sur la même ligne, table en police Mono,
        variables écrites par une étape du canevas (compute_written_variables) affichées en
        lecture seule « écrite par <étape> » si elles ne sont pas déjà déclarées ici."""
        vl = QVBoxLayout(); vl.setSpacing(10)

        header_row = QHBoxLayout()
        header_row.addWidget(self._section_label("VARIABLES"))
        header_row.addStretch()
        btn_add = QPushButton("+ Ajouter")
        btn_add.setFlat(True)
        btn_add.setCursor(Qt.PointingHandCursor)
        btn_add.setStyleSheet(
            f"QPushButton {{ background: transparent; border: none; color: {COLORS['accent_pale']}; "
            f"font-size: 12px; font-weight: 600; padding: 0; }}"
            f"QPushButton:hover {{ color: {COLORS['accent']}; }}"
        )
        btn_add.clicked.connect(lambda: self._add_variable_row())
        header_row.addWidget(btn_add)
        vl.addLayout(header_row)

        hint = QLabel(
            "Amorce ctx.variables avant la première étape — une ligne par variable (var:nom). "
            "Une valeur par défaut peut référencer une variable déclarée plus haut dans la "
            "liste, ex : date_add(var:base_date, -7)."
        )
        hint.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 11px; font-style: italic;")
        hint.setWordWrap(True)
        vl.addWidget(hint)

        self.tbl_variables = QTableWidget(0, 2)
        self.tbl_variables.setHorizontalHeaderLabels(["Nom", "Valeur par défaut (expression)"])
        self.tbl_variables.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tbl_variables.verticalHeader().setVisible(False)
        self.tbl_variables.verticalHeader().setDefaultSectionSize(52)
        self.tbl_variables.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tbl_variables.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tbl_variables.setMinimumHeight(120)
        self.tbl_variables.setStyleSheet(
            f"QTableWidget {{ background: {COLORS['bg_card']}; border: 1px solid {COLORS['border']}; "
            f"border-radius: 4px; color: {COLORS['text_main']}; gridline-color: {COLORS['border']}; "
            f"font-family: {FONT_MONO_STACK}; font-size: 11.5px; }}"
            f"QHeaderView::section {{ background: {COLORS['bg_active']}; color: {COLORS['text_dim']}; "
            f"padding: 4px; border: none; font-size: 11px; font-family: inherit; }}"
            f"QTableWidget::item:selected {{ background-color: {COLORS['bg_hover']}; "
            f"color: {COLORS['text_main']}; border-left: 2px solid {COLORS['accent']}; }}"
        )
        vl.addWidget(self.tbl_variables)

        btn_row = QHBoxLayout(); btn_row.setSpacing(8)
        btn_remove = QPushButton("− Retirer"); btn_remove.setObjectName("secondary")
        btn_remove.setFixedHeight(30); btn_remove.clicked.connect(self._remove_selected_variable_row)
        btn_row.addWidget(btn_remove); btn_row.addStretch()
        vl.addLayout(btn_row)

        return vl

    def _add_variable_row(self, name: str = "", default_expression: str = ""):
        row = self.tbl_variables.rowCount()
        self.tbl_variables.insertRow(row)
        self.tbl_variables.setItem(row, _COL_VAR_NAME, QTableWidgetItem(name))
        self.tbl_variables.setItem(row, _COL_VAR_EXPR, QTableWidgetItem(default_expression))

    def _add_written_only_variable_row(self, name: str, source_label: str):
        """A15 : ligne informative pour une variable écrite par une étape du canevas (
        compute_written_variables) mais jamais déclarée dans cette table — non éditable, non
        sélectionnable (pas de vraie ligne à enregistrer), exclue de _collect_variables()."""
        row = self.tbl_variables.rowCount()
        self.tbl_variables.insertRow(row)
        name_item = QTableWidgetItem(name)
        name_item.setFlags(name_item.flags() & ~Qt.ItemIsEditable & ~Qt.ItemIsSelectable)
        name_item.setData(Qt.UserRole, True)
        self.tbl_variables.setItem(row, _COL_VAR_NAME, name_item)

        expr_item = QTableWidgetItem(f"écrite par {source_label}")
        expr_item.setFlags(expr_item.flags() & ~Qt.ItemIsEditable & ~Qt.ItemIsSelectable)
        expr_item.setForeground(QColor(COLORS["text_muted"]))
        expr_item.setFont(QFont(FONT_UI))
        self.tbl_variables.setItem(row, _COL_VAR_EXPR, expr_item)

    def _remove_selected_variable_row(self):
        rows = {i.row() for i in self.tbl_variables.selectedIndexes()}
        for row in sorted(rows, reverse=True):
            self.tbl_variables.removeRow(row)

    def _collect_variables(self) -> list[dict]:
        variables = []
        for row in range(self.tbl_variables.rowCount()):
            name_item = self.tbl_variables.item(row, _COL_VAR_NAME)
            if name_item is not None and name_item.data(Qt.UserRole):
                continue   # ligne "écrite par X" (A15) — informative seulement
            expr_item = self.tbl_variables.item(row, _COL_VAR_EXPR)
            name = name_item.text().strip() if name_item else ""
            expr = expr_item.text().strip() if expr_item else ""
            if not name and not expr:
                continue
            variables.append({"name": name, "default_expression": expr})
        return variables

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

    def save(self) -> bool:
        """Valide puis persiste les métadonnées — ex-_on_save(), sans self.accept() (un QWidget
        n'a pas cette notion). Émet `saved` en cas de succès."""
        if not self._validate():
            return False

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

        pipeline_id = self._pipeline.id
        db.update_pipeline(
            pipeline_id, name=name, description=desc,
            frequency=freq, cron_expression=cron_expr,
            scheduled_time=sched_time, scheduled_day=sched_day,
            prevent_overlap=self.chk_prevent_overlap.isChecked(),
            parallel_execution_enabled=self.chk_parallel_execution.isChecked(),
            max_parallel_branches=self.spin_max_parallel_branches.value(),
        )
        db.set_pipeline_active(pipeline_id, self.chk_active.isChecked())
        db.save_pipeline_variables(pipeline_id, self._collect_variables())

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

        # (Re)planifie immédiatement — même patron que l'ancien PipelineEditorDialog._on_save().
        from core.execution_mode import request_reload
        if not request_reload():
            try:
                from core.scheduler import get_scheduler
                get_scheduler().schedule_pipeline(pipeline_id)
            except RuntimeError:
                pass

        self.saved.emit()
        return True

    def _validate(self) -> bool:
        if not self.inp_name.text().strip():
            self.inp_name.setStyleSheet(self._input_style(error=True))
            self.inp_name.setFocus()
            return False

        seen_names = set()
        for v in self._collect_variables():
            if not v["name"] or not v["default_expression"]:
                QMessageBox.warning(
                    self, "Variable incomplète",
                    "Chaque variable de pipeline doit avoir un nom et une expression."
                )
                return False
            try:
                compile_expression(v["default_expression"])
            except ValueError as e:
                QMessageBox.warning(
                    self, "Expression invalide", f"« {v['name']} » : {e}"
                )
                return False
            if v["name"] in seen_names:
                QMessageBox.warning(
                    self, "Variable en double",
                    f"Le nom de variable « {v['name']} » est utilisé plusieurs fois."
                )
                return False
            seen_names.add(v["name"])
        return True

    # ── Remplissage ────────────────────────────

    def _fill_fields(self, p):
        self.inp_name.setText(p.name)
        self.inp_desc.setText(p.description or "")
        self.chk_active.setChecked(bool(p.is_active))

        self.chk_prevent_overlap.setChecked(bool(p.prevent_overlap))
        self.chk_parallel_execution.setChecked(bool(p.parallel_execution_enabled))
        self.spin_max_parallel_branches.setValue(p.max_parallel_branches or 4)

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

        from database import db_manager as db
        declared_names = set()
        for v in db.get_pipeline_variables(p.id):
            self._add_variable_row(v.name, v.default_expression)
            declared_names.add(v.name)

        # A15 : variables écrites par une étape du canevas (SET_VARIABLE/EXTRACT_VARIABLES),
        # affichées en lecture seule si elles ne sont pas déjà une variable déclarée ci-dessus.
        for name, source_label in _compute_written_variable_sources(p.id).items():
            if name not in declared_names:
                self._add_written_only_variable_row(name, source_label)

    # ── Helpers visuels ──────────────────────

    def _section_label(self, text: str) -> QLabel:
        l = QLabel(text)
        l.setStyleSheet(
            f"color: {COLORS['text_dim']}; font-size: 11px; font-weight: 600; "
            f"letter-spacing: 0.06em; background: transparent; border: none;"
        )
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

    def _segment_button_style(self) -> str:
        """A12 : boutons segmentés de fréquence — fond plein `bg_hover` + texte plein quand
        coché, transparent/atténué sinon, sans bordure individuelle (la bordure vit sur le
        conteneur `freq_bar`)."""
        return (
            f"QPushButton {{ background: transparent; border: none; border-radius: 4px; "
            f"color: {COLORS['text_dim']}; font-size: 12px; font-weight: 600; padding: 0; }}"
            f"QPushButton:checked {{ background: {COLORS['bg_hover']}; color: {COLORS['text_main']}; }}"
            f"QPushButton:hover:!checked {{ color: {COLORS['text_main']}; }}"
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

    def _sep(self) -> QFrame:
        f = QFrame(); f.setFrameShape(QFrame.HLine)
        f.setStyleSheet(f"background: {COLORS['border']}; max-height: 1px;")
        return f

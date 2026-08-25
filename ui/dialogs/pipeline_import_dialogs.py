"""
DataScheduler — ui/dialogs/pipeline_import_dialogs.py
Dialogues du flux d'import : prompt du mot de passe et écran de revue.
"""

from types import SimpleNamespace

from PySide6.QtWidgets import (
    QComboBox, QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel,
    QLineEdit, QRadioButton, QButtonGroup, QPushButton, QFrame, QTableWidget,
    QTableWidgetItem,
)
from PySide6.QtCore import Qt
from ui.styles import COLORS, DIALOG_STYLE, FONT_MONO_STACK


# ──────────────────────────────────────────────
#  DIALOGUE : MOT DE PASSE D'IMPORT
# ──────────────────────────────────────────────

class PipelineImportPasswordDialog(QDialog):
    """Prompt du mot de passe nécessaire pour déchiffrer un bundle .dspipeline importé.

    `verify` (facultatif) : Callable[[str], ImportPlan] appelé au clic sur "Valider" — un échec
    (`plan.success is False`) affiche l'erreur sur place et laisse le dialogue ouvert pour une
    nouvelle tentative, au lieu de forcer l'appelant à tout redémarrer (resélection du fichier
    comprise). `self.plan` porte le résultat réussi, prêt à être lu par l'appelant après
    `exec()`. `verify=None` (défaut) préserve le comportement historique — accepter
    inconditionnellement — pour tout appelant qui n'en a pas besoin."""

    def __init__(self, parent=None, verify=None):
        super().__init__(parent)
        self._verify = verify
        self.plan = None
        self.setWindowTitle("Mot de passe requis")
        self.setMinimumWidth(420)
        self.setStyleSheet(DIALOG_STYLE)
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(16)

        title = QLabel("Mot de passe requis")
        title.setStyleSheet(f"font-size: 16px; font-weight: 700; color: {COLORS['text_main']};")
        root.addWidget(title)
        root.addWidget(self._sep())

        note = QLabel(
            "Ce fichier contient des identifiants chiffrés. Saisissez le mot de passe utilisé "
            "au moment de l'export pour les déchiffrer."
        )
        note.setWordWrap(True)
        note.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 11px; font-style: italic;")
        root.addWidget(note)

        form = QFormLayout()
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        form.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)
        self.inp_password = QLineEdit()
        self.inp_password.setEchoMode(QLineEdit.Password)
        self.inp_password.setFixedHeight(34)
        self.inp_password.setStyleSheet(self._input_style())
        self.inp_password.textChanged.connect(self._clear_error)
        form.addRow(self._label("Mot de passe"), self.inp_password)
        root.addLayout(form)

        self.lbl_error = QLabel("")
        self.lbl_error.setStyleSheet(f"color: {COLORS['danger']}; font-size: 11px;")
        self.lbl_error.setWordWrap(True)
        self.lbl_error.setVisible(False)
        root.addWidget(self.lbl_error)

        root.addWidget(self._sep())
        btn_row = QHBoxLayout(); btn_row.setSpacing(10); btn_row.addStretch()
        btn_cancel = QPushButton("Annuler"); btn_cancel.setObjectName("secondary")
        btn_cancel.setFixedHeight(36); btn_cancel.clicked.connect(self.reject)
        btn_ok = QPushButton("Valider")
        btn_ok.setFixedHeight(36); btn_ok.clicked.connect(self._on_validate)
        btn_row.addWidget(btn_cancel); btn_row.addWidget(btn_ok)
        root.addLayout(btn_row)

    def _clear_error(self):
        # isHidden() plutôt qu'isVisible() : ce dernier dépend aussi de la visibilité des
        # parents (donc toujours False tant que le dialogue n'a jamais été réellement affiché,
        # comme dans les tests), alors qu'isHidden() ne reflète que l'état explicitement demandé
        # sur ce widget précis (même piège déjà rencontré sur PipelinesView._on_toggle_minimap).
        if not self.lbl_error.isHidden():
            self.lbl_error.setVisible(False)
            self.inp_password.setStyleSheet(self._input_style())

    def _on_validate(self):
        if self._verify is None:
            self.accept()
            return
        plan = self._verify(self.inp_password.text())
        if not plan.success:
            self.inp_password.setStyleSheet(self._input_style(error=True))
            self.lbl_error.setText(plan.error or "Mot de passe incorrect.")
            self.lbl_error.setVisible(True)
            return
        self.plan = plan
        self.accept()

    def password(self) -> str:
        return self.inp_password.text()

    def _input_style(self, error=False) -> str:
        border = COLORS["danger"] if error else COLORS["border"]
        return (f"QLineEdit {{ background: {COLORS['bg_card']}; border: 1px solid {border}; "
                f"border-radius: 4px; padding: 6px 10px; color: {COLORS['text_main']}; font-size: 13px; }}"
                f"QLineEdit:focus {{ border-color: {COLORS['accent']}; }}")

    def _label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(f"color: {COLORS['text_dim']}; font-size: 12px; font-weight: 500;")
        return lbl

    def _sep(self) -> QFrame:
        f = QFrame(); f.setFrameShape(QFrame.HLine)
        f.setStyleSheet(f"background: {COLORS['border']}; max-height: 1px;")
        return f


# ──────────────────────────────────────────────
#  DIALOGUE : REVUE DE L'IMPORT (chantier 5c)
# ──────────────────────────────────────────────

class PipelineImportReviewDialog(QDialog):
    """
    Écran de revue avant apply_import() : montre les décisions par défaut de plan_import()
    (réutiliser/créer, copie renommée en cas de collision de pipeline) et permet de les changer
    — écraser le pipeline existant, remapper un profil vers un existant local. Mute `plan` en
    place à la confirmation ; ne fait elle-même aucune écriture en base.
    """

    _CATEGORY_LABELS = {
        "oracle": "Oracle", "ftp": "FTP", "smtp": "SMTP",
        "database": "Base de données", "sql_query": "Requête SQL",
        "ssh": "SSH (nœud edge)", "kerberos": "Kerberos", "elevation": "Élévation (sudo su)",
    }

    def __init__(self, parent=None, plan=None):
        super().__init__(parent)
        self.plan = plan
        self._combo_by_decision = []   # [(EntityDecision, QComboBox)]
        self.rb_rename = None
        self.rb_overwrite = None
        self.setWindowTitle("Revue de l'import")
        self.setMinimumSize(620, 480)
        self.setStyleSheet(DIALOG_STYLE)
        self._build_ui()

    def _build_ui(self):
        from database import db_manager as db

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(14)

        title = QLabel("Revue de l'import")
        title.setStyleSheet(f"font-size: 16px; font-weight: 700; color: {COLORS['text_main']};")
        root.addWidget(title)
        root.addWidget(self._sep())

        pipeline_data = self.plan.bundle["pipeline"]
        pipeline_lbl = QLabel(f"Pipeline : « {pipeline_data['name']} »")
        pipeline_lbl.setStyleSheet(f"color: {COLORS['text_main']}; font-size: 13px; font-weight: 600;")
        root.addWidget(pipeline_lbl)

        existing = (db.get_pipeline(self.plan.pipeline_existing_id)
                    if self.plan.pipeline_action == "collision" else None)
        root.addWidget(self._build_settings_preview(pipeline_data, existing))

        if self.plan.pipeline_action == "collision":
            existing_name = existing.name if existing else "?"
            self.rb_rename = QRadioButton("Importer comme copie renommée")
            self.rb_rename.setChecked(True)
            self.rb_overwrite = QRadioButton(f"Écraser le pipeline existant « {existing_name} »")
            group = QButtonGroup(self)
            group.addButton(self.rb_rename); group.addButton(self.rb_overwrite)
            for rb in (self.rb_rename, self.rb_overwrite):
                rb.setStyleSheet(f"color: {COLORS['text_main']};")
                root.addWidget(rb)
            warn = QLabel("Écraser remplace définitivement les étapes du pipeline existant.")
            warn.setStyleSheet(f"color: {COLORS['warning']}; font-size: 10.5px; font-style: italic;")
            root.addWidget(warn)
        else:
            info = QLabel("Nouveau pipeline — aucune collision détectée.")
            info.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 11px; font-style: italic;")
            root.addWidget(info)

        root.addWidget(self._sep())

        entities_lbl = QLabel("Profils et requêtes référencés :")
        entities_lbl.setStyleSheet(f"color: {COLORS['text_dim']}; font-size: 12px; font-weight: 500;")
        root.addWidget(entities_lbl)

        all_decisions = list(self.plan.profile_decisions) + list(self.plan.sql_query_decisions)
        table = QTableWidget(len(all_decisions), 4)
        table.setHorizontalHeaderLabels(["Catégorie", "Nom", "Statut", "Action"])
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.horizontalHeader().setStretchLastSection(True)
        table.setStyleSheet(
            f"QTableWidget {{ background: {COLORS['bg_card']}; color: {COLORS['text_main']}; "
            f"border: 1px solid {COLORS['border']}; gridline-color: {COLORS['border']}; }}"
            f"QHeaderView::section {{ background: {COLORS['bg_panel']}; color: {COLORS['text_dim']}; "
            f"border: none; padding: 4px; }}"
        )

        for row, decision in enumerate(all_decisions):
            table.setItem(row, 0, QTableWidgetItem(
                self._CATEGORY_LABELS.get(decision.category, decision.category)))

            if decision.action == "create":
                name = (decision.data or {}).get("name", "?")
                status = "Nouveau"
            else:
                existing = self._get_existing(decision.category, decision.existing_id)
                name = existing.name if existing else "?"
                status = "Réutilisé"
            table.setItem(row, 1, QTableWidgetItem(name))
            table.setItem(row, 2, QTableWidgetItem(status))

            if decision.action == "create":
                combo = QComboBox()
                combo.addItem("Créer un nouveau profil", None)
                for existing in self._list_existing(decision.category):
                    combo.addItem(f"Remapper vers « {existing.name} »", existing.id)
                table.setCellWidget(row, 3, combo)
                self._combo_by_decision.append((decision, combo))
            else:
                table.setItem(row, 3, QTableWidgetItem("—"))

        table.resizeColumnsToContents()
        root.addWidget(table, stretch=1)

        root.addWidget(self._sep())
        btn_row = QHBoxLayout(); btn_row.setSpacing(10); btn_row.addStretch()
        btn_cancel = QPushButton("Annuler"); btn_cancel.setObjectName("secondary")
        btn_cancel.setFixedHeight(36); btn_cancel.clicked.connect(self.reject)
        btn_ok = QPushButton("Continuer")
        btn_ok.setFixedHeight(36); btn_ok.clicked.connect(self._on_confirm)
        btn_row.addWidget(btn_cancel); btn_row.addWidget(btn_ok)
        root.addLayout(btn_row)

    def _build_settings_preview(self, pipeline_data: dict, existing) -> QFrame:
        """Aperçu actif/planification du pipeline entrant (correctif friction d'import) —
        invisible avant que is_active soit réellement restauré par apply_import() (voir
        database/export_import.py), puisqu'un import réactivait jusque-là toujours le pipeline
        sans que rien ne le montre. `existing` (le pipeline local en collision, ou None pour un
        import sans collision) sert uniquement à détecter un changement d'état actif à
        l'écrasement — jamais utilisé pour la planification, qui affiche toujours celle du
        bundle entrant, pas celle de l'existant."""
        from core.scheduler import describe_schedule

        frame = QFrame()
        frame.setStyleSheet(
            f"QFrame {{ background: {COLORS['bg_main']}; border: 1px solid {COLORS['border']}; "
            f"border-radius: 8px; }}"
        )
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(8)

        heading = QLabel("RÉGLAGES DU PIPELINE IMPORTÉ")
        heading.setStyleSheet(
            f"color: {COLORS['text_muted']}; font-size: 10.5px; font-weight: 700; "
            f"letter-spacing: 0.5px;"
        )
        layout.addWidget(heading)

        is_active = pipeline_data.get("is_active", True)
        row = QHBoxLayout(); row.setSpacing(14)

        self.lbl_active_pill = QLabel("Actif" if is_active else "Inactif")
        pill_color = COLORS["success"] if is_active else COLORS["text_dim"]
        self.lbl_active_pill.setStyleSheet(
            f"background: {pill_color}26; color: {pill_color}; border-radius: 999px; "
            f"padding: 3px 10px; font-size: 11px; font-weight: 700;"
        )
        row.addWidget(self.lbl_active_pill)

        self.lbl_schedule_preview = QLabel(describe_schedule(SimpleNamespace(**pipeline_data)))
        self.lbl_schedule_preview.setStyleSheet(
            f"color: {COLORS['text_dim']}; font-size: 12px; font-family: {FONT_MONO_STACK};"
        )
        row.addWidget(self.lbl_schedule_preview)
        row.addStretch()
        layout.addLayout(row)

        self.lbl_transition_warning = QLabel("")
        self.lbl_transition_warning.setStyleSheet(
            f"color: {COLORS['warning']}; font-size: 10.5px; font-style: italic;"
        )
        self.lbl_transition_warning.setVisible(False)
        if existing is not None and bool(existing.is_active) != is_active:
            state_from = "Actif" if existing.is_active else "Inactif"
            state_to = "Actif" if is_active else "Inactif"
            self.lbl_transition_warning.setText(
                f"En écrasant, l'état actif changera : {state_from} → {state_to}"
            )
            self.lbl_transition_warning.setVisible(True)
        layout.addWidget(self.lbl_transition_warning)

        return frame

    def _on_confirm(self):
        if self.rb_overwrite is not None and self.rb_overwrite.isChecked():
            self.plan.pipeline_action = "overwrite"
        elif self.plan.pipeline_action == "collision":
            self.plan.pipeline_action = "rename"

        for decision, combo in self._combo_by_decision:
            chosen_id = combo.currentData()
            if chosen_id is not None:
                decision.action = "reuse"
                decision.existing_id = chosen_id

        self.accept()

    @staticmethod
    def _get_existing(category, existing_id):
        from database import db_manager as db
        getters = {
            "oracle": db.get_oracle_profile, "ftp": db.get_ftp_profile,
            "smtp": db.get_smtp_profile, "database": db.get_database_profile,
            "sql_query": db.get_sql_query,
            "ssh": db.get_ssh_profile, "kerberos": db.get_kerberos_profile,
            "elevation": db.get_elevation_profile,
        }
        getter = getters.get(category)
        return getter(existing_id) if getter else None

    @staticmethod
    def _list_existing(category):
        from database import db_manager as db
        getters = {
            "oracle": db.get_oracle_profiles, "ftp": db.get_ftp_profiles,
            "smtp": db.get_smtp_profiles, "database": db.get_database_profiles,
            "sql_query": db.get_sql_queries,
            "ssh": db.get_ssh_profiles, "kerberos": db.get_kerberos_profiles,
            "elevation": db.get_elevation_profiles,
        }
        getter = getters.get(category)
        return getter() if getter else []

    def _sep(self) -> QFrame:
        f = QFrame(); f.setFrameShape(QFrame.HLine)
        f.setStyleSheet(f"background: {COLORS['border']}; max-height: 1px;")
        return f

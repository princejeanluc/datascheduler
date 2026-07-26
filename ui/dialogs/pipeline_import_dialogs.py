"""
DataScheduler — ui/dialogs/pipeline_import_dialogs.py
Dialogues du flux d'import : prompt du mot de passe et écran de revue.
"""

from PySide6.QtWidgets import (
    QComboBox, QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel,
    QLineEdit, QRadioButton, QButtonGroup, QPushButton, QFrame, QTableWidget,
    QTableWidgetItem,
)
from PySide6.QtCore import Qt
from ui.styles import COLORS, DIALOG_STYLE


# ──────────────────────────────────────────────
#  DIALOGUE : MOT DE PASSE D'IMPORT
# ──────────────────────────────────────────────

class PipelineImportPasswordDialog(QDialog):
    """Prompt du mot de passe nécessaire pour déchiffrer un bundle .dspipeline importé."""

    def __init__(self, parent=None):
        super().__init__(parent)
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
        form.addRow(self._label("Mot de passe"), self.inp_password)
        root.addLayout(form)

        root.addWidget(self._sep())
        btn_row = QHBoxLayout(); btn_row.setSpacing(10); btn_row.addStretch()
        btn_cancel = QPushButton("Annuler"); btn_cancel.setObjectName("secondary")
        btn_cancel.setFixedHeight(36); btn_cancel.clicked.connect(self.reject)
        btn_ok = QPushButton("Valider")
        btn_ok.setFixedHeight(36); btn_ok.clicked.connect(self.accept)
        btn_row.addWidget(btn_cancel); btn_row.addWidget(btn_ok)
        root.addLayout(btn_row)

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

        if self.plan.pipeline_action == "collision":
            existing = db.get_pipeline(self.plan.pipeline_existing_id)
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
        }
        getter = getters.get(category)
        return getter() if getter else []

    def _sep(self) -> QFrame:
        f = QFrame(); f.setFrameShape(QFrame.HLine)
        f.setStyleSheet(f"background: {COLORS['border']}; max-height: 1px;")
        return f

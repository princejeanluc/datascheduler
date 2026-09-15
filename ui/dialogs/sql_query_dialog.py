"""
DataScheduler — ui/dialogs/sql_query_dialog.py
Dialogue de création / édition rapide d'une requête SQL réutilisable — ouvert depuis un dialogue
de configuration d'étape ("+ Nouvelle requête SQL" sur DB_EXTRACT/DB_EXECUTE/SPARK_SQL) quand
l'utilisateur n'a pas besoin de quitter son étape en cours pour en créer une. L'atelier dédié
(chantier atelier SQL, ui/main_window/queries_view.py) reste l'endroit pour un travail plus
approfondi sur une bibliothèque de requêtes existante — les deux partagent le même éditeur
(ui/sql_editor.py::SqlEditorWidget), jamais deux implémentations divergentes.
"""

from PySide6.QtWidgets import (
    QComboBox, QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QLineEdit,
    QPushButton, QFrame,
)
from PySide6.QtCore import Qt
from ui.styles import COLORS, DIALOG_STYLE
from ui.sql_editor import SqlEditorWidget


# ──────────────────────────────────────────────
#  DIALOGUE : REQUÊTE SQL
# ──────────────────────────────────────────────

class SqlQueryDialog(QDialog):
    """Création / édition d'une requête SQL réutilisable."""

    def __init__(self, parent=None, query=None):
        super().__init__(parent)
        self._query = query
        self.setWindowTitle("Requête SQL" if query is None else "Modifier la requête")
        self.setMinimumSize(680, 520)
        self.setStyleSheet(DIALOG_STYLE)
        self._build_ui()
        if query:
            self._fill_fields(query)

    # ── Construction UI ──────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(16)

        title = QLabel("Requête SQL")
        title.setStyleSheet(f"font-size: 16px; font-weight: 700; color: {COLORS['text_main']};")
        root.addWidget(title)
        root.addWidget(self._sep())

        form = QFormLayout()
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        form.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)

        self.inp_name = self._input("ex : REQUETE_VENTES_JOUR")
        self.inp_desc = self._input("Description courte (optionnel)")

        self.cb_oracle = QComboBox()
        self.cb_oracle.setStyleSheet(self._combo_style())
        self._load_oracle_profiles()

        form.addRow(self._label("Nom *"),              self.inp_name)
        form.addRow(self._label("Description"),        self.inp_desc)
        form.addRow(self._label("Profil Oracle"),      self.cb_oracle)
        root.addLayout(form)

        lbl_sql = QLabel("Requête SELECT *")
        lbl_sql.setStyleSheet(f"color: {COLORS['text_dim']}; font-size: 12px; font-weight: 500;")
        root.addWidget(lbl_sql)

        self.editor = SqlEditorWidget()
        self.editor.set_placeholder(
            "SELECT col1, col2\nFROM ma_table\nWHERE condition = :param\nORDER BY col1"
        )
        root.addWidget(self.editor, stretch=1)

        root.addWidget(self._sep())

        btn_row = QHBoxLayout(); btn_row.setSpacing(10)
        btn_format = QPushButton("Formater"); btn_format.setObjectName("secondary")
        btn_format.setFixedHeight(36); btn_format.clicked.connect(self.editor.format_sql)
        btn_row.addWidget(btn_format)
        btn_row.addStretch()
        btn_cancel = QPushButton("Annuler"); btn_cancel.setObjectName("secondary")
        btn_cancel.setFixedHeight(36); btn_cancel.clicked.connect(self.reject)
        btn_save = QPushButton("Enregistrer")
        btn_save.setFixedHeight(36); btn_save.clicked.connect(self._on_save)
        btn_row.addWidget(btn_cancel); btn_row.addWidget(btn_save)
        root.addLayout(btn_row)

    # ── Logique ──────────────────────────────

    def _load_oracle_profiles(self):
        from database import db_manager as db
        self.cb_oracle.clear()
        self.cb_oracle.addItem("(aucun)", None)
        for p in db.get_oracle_profiles():
            self.cb_oracle.addItem(p.name, p.id)

    def _on_save(self):
        name = self.inp_name.text().strip()
        sql  = self.editor.text().strip()
        if not name:
            self.inp_name.setStyleSheet(self._input_style(error=True))
            self.inp_name.setFocus()
            return
        if not sql:
            self.editor.editor.setStyleSheet(
                f"QPlainTextEdit {{ background: {COLORS['bg_main']}; color: {COLORS['text_main']}; "
                f"border: 2px solid {COLORS['danger']}; border-radius: 4px; padding: 8px; }}"
            )
            self.editor.editor.setFocus()
            return

        from database import db_manager as db
        desc       = self.inp_desc.text().strip() or None
        oracle_id  = self.cb_oracle.currentData()

        if self._query:
            db.update_sql_query(self._query.id, name=name, sql_text=sql,
                                description=desc, oracle_profile_id=oracle_id)
        else:
            db.create_sql_query(name=name, sql_text=sql,
                                description=desc, oracle_profile_id=oracle_id)
        self.accept()

    def _fill_fields(self, query):
        self.inp_name.setText(query.name)
        self.inp_desc.setText(query.description or "")
        self.editor.set_text(query.sql_text or "")
        if query.oracle_profile_id:
            idx = self.cb_oracle.findData(query.oracle_profile_id)
            if idx >= 0:
                self.cb_oracle.setCurrentIndex(idx)

    # ── Helpers visuels ──────────────────────

    def _input(self, placeholder="") -> QLineEdit:
        w = QLineEdit(); w.setPlaceholderText(placeholder); w.setFixedHeight(34)
        w.setStyleSheet(self._input_style())
        return w

    def _input_style(self, error=False) -> str:
        border = COLORS["danger"] if error else COLORS["border"]
        return (f"QLineEdit {{ background: {COLORS['bg_card']}; border: 1px solid {border}; "
                f"border-radius: 4px; padding: 6px 10px; color: {COLORS['text_main']}; font-size: 13px; }}"
                f"QLineEdit:focus {{ border-color: {COLORS['accent']}; }}")

    def _combo_style(self) -> str:
        return (f"QComboBox {{ background: {COLORS['bg_card']}; border: 1px solid {COLORS['border']}; "
                f"border-radius: 4px; padding: 6px 10px; color: {COLORS['text_main']}; font-size: 13px; }}"
                f"QComboBox:focus {{ border-color: {COLORS['accent']}; }}"
                f"QComboBox::drop-down {{ border: none; padding-right: 8px; }}"
                f"QComboBox QAbstractItemView {{ background: {COLORS['bg_card']}; "
                f"border: 1px solid {COLORS['border']}; "
                f"selection-background-color: {COLORS['bg_active']}; color: {COLORS['text_main']}; }}")

    def _label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(f"color: {COLORS['text_dim']}; font-size: 12px; font-weight: 500;")
        return lbl

    def _sep(self) -> QFrame:
        f = QFrame(); f.setFrameShape(QFrame.HLine)
        f.setStyleSheet(f"background: {COLORS['border']}; max-height: 1px;")
        return f

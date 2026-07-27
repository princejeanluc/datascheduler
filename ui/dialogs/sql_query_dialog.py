"""
DataScheduler — ui/dialogs/sql_query_dialog.py
Dialogue de création / édition d'une requête SQL réutilisable.
"""

from PySide6.QtWidgets import (
    QComboBox, QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel,
    QLineEdit, QPushButton, QFrame, QPlainTextEdit,
)
from PySide6.QtCore import Qt, QRegularExpression
from PySide6.QtGui import QFont, QSyntaxHighlighter, QTextCharFormat, QColor
from ui.styles import COLORS, DIALOG_STYLE


# ──────────────────────────────────────────────
#  COLORATION SYNTAXIQUE SQL (simple)
# ──────────────────────────────────────────────

class _SqlHighlighter(QSyntaxHighlighter):
    _KEYWORDS = (
        "SELECT", "FROM", "WHERE", "AND", "OR", "NOT", "IN", "IS", "NULL",
        "LIKE", "BETWEEN", "EXISTS", "JOIN", "LEFT", "RIGHT", "INNER", "OUTER",
        "ON", "AS", "GROUP", "BY", "ORDER", "HAVING", "DISTINCT", "UNION",
        "ALL", "INSERT", "INTO", "VALUES", "UPDATE", "SET", "DELETE",
        "CREATE", "ALTER", "DROP", "TABLE", "VIEW", "INDEX", "WITH",
        "CASE", "WHEN", "THEN", "ELSE", "END", "OVER", "PARTITION",
        "ROWNUM", "ROWID", "CONNECT", "START", "PRIOR", "LEVEL",
    )

    def __init__(self, document):
        super().__init__(document)

        kw_fmt = QTextCharFormat()
        kw_fmt.setForeground(QColor("#FF7900"))
        kw_fmt.setFontWeight(700)

        str_fmt = QTextCharFormat()
        str_fmt.setForeground(QColor("#7ec8a4"))

        cmt_fmt = QTextCharFormat()
        cmt_fmt.setForeground(QColor("#666666"))
        cmt_fmt.setFontItalic(True)

        num_fmt = QTextCharFormat()
        num_fmt.setForeground(QColor("#b5cea8"))

        self._rules = []
        for kw in self._KEYWORDS:
            pat = QRegularExpression(rf"\b{kw}\b", QRegularExpression.CaseInsensitiveOption)
            self._rules.append((pat, kw_fmt))
        self._rules.append((QRegularExpression(r"'[^']*'"), str_fmt))
        self._rules.append((QRegularExpression(r"--[^\n]*"),  cmt_fmt))
        self._rules.append((QRegularExpression(r"\b\d+(\.\d+)?\b"), num_fmt))

    def highlightBlock(self, text: str):
        for pattern, fmt in self._rules:
            it = pattern.globalMatch(text)
            while it.hasNext():
                m = it.next()
                self.setFormat(m.capturedStart(), m.capturedLength(), fmt)


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

        self.editor = QPlainTextEdit()
        self.editor.setFont(QFont("Consolas", 12))
        self.editor.setStyleSheet(
            f"background: {COLORS['bg_main']}; color: {COLORS['text_main']}; "
            f"border: 1px solid {COLORS['border']}; border-radius: 4px; padding: 8px;"
        )
        self.editor.setPlaceholderText(
            "SELECT col1, col2\nFROM ma_table\nWHERE condition = :param\nORDER BY col1"
        )
        self._highlighter = _SqlHighlighter(self.editor.document())
        root.addWidget(self.editor, stretch=1)

        root.addWidget(self._sep())

        btn_row = QHBoxLayout(); btn_row.setSpacing(10); btn_row.addStretch()
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
        sql  = self.editor.toPlainText().strip()
        if not name:
            self.inp_name.setStyleSheet(self._input_style(error=True))
            self.inp_name.setFocus()
            return
        if not sql:
            self.editor.setStyleSheet(
                f"background: {COLORS['bg_main']}; color: {COLORS['text_main']}; "
                f"border: 2px solid {COLORS['danger']}; border-radius: 4px; padding: 8px;"
            )
            self.editor.setFocus()
            return

        from database import db_manager as db
        desc       = self.inp_desc.text().strip() or None
        oracle_id  = self.cb_oracle.currentData()

        if self._query:
            with db.get_session() as s:
                from database.models import SqlQuery
                q = s.get(SqlQuery, self._query.id)
                q.name              = name
                q.description       = desc
                q.sql_text          = sql
                q.oracle_profile_id = oracle_id
        else:
            db.create_sql_query(name=name, sql_text=sql,
                                description=desc, oracle_profile_id=oracle_id)
        self.accept()

    def _fill_fields(self, query):
        self.inp_name.setText(query.name)
        self.inp_desc.setText(query.description or "")
        self.editor.setPlainText(query.sql_text or "")
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

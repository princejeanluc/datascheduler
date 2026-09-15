"""
DataScheduler — ui/sql_editor.py
Éditeur SQL réutilisable (chantier atelier SQL) : numéros de ligne, coloration syntaxique,
recherche/remplacement, formatage — construit sur des widgets Qt natifs (`QPlainTextEdit` +
gouttière peinte à la main, pattern "Code Editor Example" documenté par Qt depuis des années),
jamais QScintilla (bindings Python officiels réservés à PyQt5/PyQt6, aucun support PySide6 —
vérifié avant d'écarter l'idée, voir CHANGELOG). Partagé entre `ui/dialogs/sql_query_dialog.py`
(modale rapide "+ Nouvelle requête" ouverte depuis un dialogue de step) et
`ui/main_window/queries_view.py` (atelier maître-détail) — un seul endroit à faire évoluer.
"""

import sqlparse

from PySide6.QtCore import Qt, QRect, QSize, QRegularExpression
from PySide6.QtGui import (
    QColor, QFont, QPainter, QSyntaxHighlighter, QTextCharFormat, QTextCursor,
    QKeySequence, QShortcut,
)
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPlainTextEdit, QTextEdit, QLineEdit, QLabel,
    QPushButton, QFrame,
)
from ui.styles import COLORS, FONT_MONO


# ──────────────────────────────────────────────
#  COLORATION SYNTAXIQUE SQL (simple, non-eval — un blob éditable à la main, jamais interprété)
# ──────────────────────────────────────────────

class SqlHighlighter(QSyntaxHighlighter):
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
#  ÉDITEUR AVEC GOUTTIÈRE DE NUMÉROS DE LIGNE
# ──────────────────────────────────────────────

class _LineNumberArea(QWidget):
    def __init__(self, editor: "_CodeEditor"):
        super().__init__(editor)
        self._editor = editor

    def sizeHint(self) -> QSize:
        return QSize(self._editor.line_number_area_width(), 0)

    def paintEvent(self, event):
        self._editor.line_number_area_paint_event(event)


class _CodeEditor(QPlainTextEdit):
    """`QPlainTextEdit` + gouttière — pattern Qt standard : la gouttière est un widget enfant
    peint à la main, sa largeur réserve une marge sur le viewport (`setViewportMargins`), et elle
    se resynchronise sur `updateRequest` (défilement/frappe) et `blockCountChanged` (nombre de
    chiffres qui grandit)."""

    def __init__(self):
        super().__init__()
        self.setFont(QFont(FONT_MONO, 12))
        self.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.setTabStopDistance(4 * self.fontMetrics().horizontalAdvance(" "))
        self.setStyleSheet(
            f"QPlainTextEdit {{ background: {COLORS['bg_main']}; color: {COLORS['text_main']}; "
            f"border: 1px solid {COLORS['border']}; border-radius: 4px; padding: 8px; }}"
        )
        self._line_area = _LineNumberArea(self)
        self.blockCountChanged.connect(self._update_area_width)
        self.updateRequest.connect(self._update_area)
        self.cursorPositionChanged.connect(self._highlight_current_line)
        self._update_area_width(0)
        self._highlight_current_line()

    def line_number_area_width(self) -> int:
        digits = max(2, len(str(max(1, self.blockCount()))))
        return 10 + self.fontMetrics().horizontalAdvance("9") * digits

    def _update_area_width(self, _new_block_count: int):
        self.setViewportMargins(self.line_number_area_width(), 0, 0, 0)

    def _update_area(self, rect, dy: int):
        if dy:
            self._line_area.scroll(0, dy)
        else:
            self._line_area.update(0, rect.y(), self._line_area.width(), rect.height())
        if rect.contains(self.viewport().rect()):
            self._update_area_width(0)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        cr = self.contentsRect()
        self._line_area.setGeometry(QRect(cr.left(), cr.top(), self.line_number_area_width(), cr.height()))

    def line_number_area_paint_event(self, event):
        painter = QPainter(self._line_area)
        painter.fillRect(event.rect(), QColor(COLORS["bg_main"]))
        block = self.firstVisibleBlock()
        block_number = block.blockNumber()
        top = self.blockBoundingGeometry(block).translated(self.contentOffset()).top()
        bottom = top + self.blockBoundingRect(block).height()
        painter.setPen(QColor(COLORS["text_muted"]))
        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                painter.drawText(
                    0, int(top), self._line_area.width() - 6, self.fontMetrics().height(),
                    Qt.AlignRight, str(block_number + 1),
                )
            block = block.next()
            top = bottom
            bottom = top + self.blockBoundingRect(block).height()
            block_number += 1

    def _highlight_current_line(self):
        selection = QTextEdit.ExtraSelection()
        selection.format.setBackground(QColor(COLORS["bg_hover"]))
        selection.format.setProperty(QTextCharFormat.Property.FullWidthSelection, True)
        selection.cursor = self.textCursor()
        selection.cursor.clearSelection()
        self.setExtraSelections([selection])


# ──────────────────────────────────────────────
#  BARRE DE RECHERCHE / REMPLACEMENT
# ──────────────────────────────────────────────

class _FindBar(QFrame):
    def __init__(self, editor: _CodeEditor):
        super().__init__(editor)
        self._editor = editor
        self.setStyleSheet(
            f"QFrame {{ background: {COLORS['bg_card']}; border: 1px solid {COLORS['border']}; "
            f"border-radius: 7px; }}"
        )
        self.hide()

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        row1 = QHBoxLayout(); row1.setSpacing(6)
        self.inp_find = QLineEdit(); self.inp_find.setPlaceholderText("Rechercher…")
        self.inp_find.setFixedHeight(26)
        self.inp_find.setStyleSheet(self._input_style())
        self.lbl_count = QLabel("0/0")
        self.lbl_count.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 10.5px;")
        self.lbl_count.setFixedWidth(40)
        self.lbl_count.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        btn_prev = self._icon_btn("↑", "Précédent")
        btn_next = self._icon_btn("↓", "Suivant")
        btn_close = self._icon_btn("✕", "Fermer (Échap)")
        row1.addWidget(self.inp_find, stretch=1)
        row1.addWidget(self.lbl_count)
        row1.addWidget(btn_prev); row1.addWidget(btn_next); row1.addWidget(btn_close)
        root.addLayout(row1)

        row2 = QHBoxLayout(); row2.setSpacing(6)
        self.inp_replace = QLineEdit(); self.inp_replace.setPlaceholderText("Remplacer par…")
        self.inp_replace.setFixedHeight(26)
        self.inp_replace.setStyleSheet(self._input_style())
        row2.addWidget(self.inp_replace, stretch=1)
        root.addLayout(row2)

        row3 = QHBoxLayout(); row3.setSpacing(6)
        btn_one = QPushButton("Remplacer"); btn_all = QPushButton("Tout remplacer")
        for b in (btn_one, btn_all):
            b.setFixedHeight(24)
            b.setStyleSheet(
                f"QPushButton {{ background: transparent; border: 1px solid {COLORS['border']}; "
                f"border-radius: 4px; color: {COLORS['text_dim']}; font-size: 10.5px; font-weight: 600; }}"
                f"QPushButton:hover {{ border-color: {COLORS['accent']}; color: {COLORS['accent']}; }}"
            )
        row3.addWidget(btn_one); row3.addWidget(btn_all)
        root.addLayout(row3)

        self.setFixedWidth(300)

        self.inp_find.textChanged.connect(self._update_matches)
        self.inp_find.returnPressed.connect(lambda: self.step(1))
        btn_next.clicked.connect(lambda: self.step(1))
        btn_prev.clicked.connect(lambda: self.step(-1))
        btn_close.clicked.connect(self.close_bar)
        btn_one.clicked.connect(self._replace_one)
        btn_all.clicked.connect(self._replace_all)

        self._matches: list[int] = []
        self._current = -1

    def _input_style(self) -> str:
        return (
            f"QLineEdit {{ background: {COLORS['bg_main']}; border: 1px solid {COLORS['border']}; "
            f"border-radius: 4px; padding: 0 8px; color: {COLORS['text_main']}; font-size: 12px; "
            f"font-family: {FONT_MONO}; }}"
            f"QLineEdit:focus {{ border-color: {COLORS['accent']}; }}"
        )

    def _icon_btn(self, text: str, tooltip: str) -> QPushButton:
        b = QPushButton(text); b.setToolTip(tooltip); b.setFixedSize(24, 24)
        b.setStyleSheet(
            f"QPushButton {{ background: transparent; border: 1px solid {COLORS['border']}; "
            f"border-radius: 4px; color: {COLORS['text_dim']}; }}"
            f"QPushButton:hover {{ border-color: {COLORS['accent']}; color: {COLORS['accent']}; }}"
        )
        return b

    # ── Logique ──────────────────────────────

    def open(self):
        self.show()
        self.raise_()
        selected = self._editor.textCursor().selectedText()
        if selected:
            self.inp_find.setText(selected)
        self.inp_find.setFocus()
        self.inp_find.selectAll()
        self._update_matches()

    def close_bar(self):
        self.hide()
        self._matches = []
        self._current = -1
        self._editor.setFocus()

    def _all_match_positions(self, needle: str) -> list[int]:
        if not needle:
            return []
        text = self._editor.toPlainText()
        positions, start = [], 0
        low_text, low_needle = text.lower(), needle.lower()
        while True:
            idx = low_text.find(low_needle, start)
            if idx == -1:
                break
            positions.append(idx)
            start = idx + len(needle)
        return positions

    def _update_matches(self):
        needle = self.inp_find.text()
        self._matches = self._all_match_positions(needle)
        self._current = 0 if self._matches else -1
        self._refresh_count()
        if self._current >= 0:
            self._select_match(self._current)

    def _refresh_count(self):
        total = len(self._matches)
        shown = (self._current + 1) if total else 0
        self.lbl_count.setText(f"{shown}/{total}")

    def _select_match(self, index: int):
        needle = self.inp_find.text()
        start = self._matches[index]
        cursor = self._editor.textCursor()
        cursor.setPosition(start)
        cursor.setPosition(start + len(needle), QTextCursor.KeepAnchor)
        self._editor.setTextCursor(cursor)
        self._editor.ensureCursorVisible()

    def step(self, direction: int):
        if not self._matches:
            return
        self._current = (self._current + direction) % len(self._matches)
        self._refresh_count()
        self._select_match(self._current)

    def _replace_one(self):
        if self._current < 0:
            return
        cursor = self._editor.textCursor()
        cursor.insertText(self.inp_replace.text())
        self._update_matches()

    def _replace_all(self):
        needle = self.inp_find.text()
        if not needle:
            return
        text = self._editor.toPlainText()
        count = text.lower().count(needle.lower())
        if count == 0:
            return
        import re
        pattern = re.compile(re.escape(needle), re.IGNORECASE)
        new_text = pattern.sub(lambda _m: self.inp_replace.text(), text)
        cursor = self._editor.textCursor()
        cursor.beginEditBlock()
        cursor.select(QTextCursor.Document)
        cursor.insertText(new_text)
        cursor.endEditBlock()
        self._update_matches()


# ──────────────────────────────────────────────
#  WIDGET COMPOSITE PUBLIC
# ──────────────────────────────────────────────

class SqlEditorWidget(QWidget):
    """Éditeur SQL complet : numéros de ligne, coloration, Ctrl+F/Ctrl+H, formatage. `.editor`
    expose le `QPlainTextEdit` sous-jacent pour un appelant qui a besoin d'un accès direct
    (placeholder, focus...)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        self.editor = _CodeEditor()
        self._highlighter = SqlHighlighter(self.editor.document())
        root.addWidget(self.editor)

        self._find_bar = _FindBar(self.editor)
        self._position_find_bar()

        QShortcut(QKeySequence.Find, self.editor, activated=self.show_find_bar)
        QShortcut(QKeySequence.Replace, self.editor, activated=self.show_find_bar)
        QShortcut(QKeySequence(Qt.Key_Escape), self.editor, activated=self._find_bar.close_bar)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._position_find_bar()

    def _position_find_bar(self):
        margin = 10
        self._find_bar.move(self.width() - self._find_bar.width() - margin, margin)

    def show_find_bar(self):
        self._position_find_bar()
        self._find_bar.open()

    def text(self) -> str:
        return self.editor.toPlainText()

    def set_text(self, text: str) -> None:
        self.editor.setPlainText(text or "")

    def set_placeholder(self, text: str) -> None:
        self.editor.setPlaceholderText(text)

    def format_sql(self) -> None:
        """Reformate la requête (indentation par clause) via `sqlparse` — bibliothèque pure
        Python, aucune extension C, sans rapport avec le binding Qt (contrairement à QScintilla,
        écarté — voir docstring du module)."""
        formatted = sqlparse.format(
            self.text(), reindent=True, keyword_case="upper", indent_width=2,
        )
        self.set_text(formatted.strip())

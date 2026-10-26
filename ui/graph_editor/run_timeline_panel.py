"""
DataScheduler — ui/graph_editor/run_timeline_panel.py
Compartiment bas d'une vue d'exécution (C9, frame Atelier-echec) : onglets Chronogramme/Journal —
même patron d'onglets que HistoryView._make_tab_button/_set_active_tab (bouton plat, soulignement
accent de l'onglet actif). Purement un afficheur, comme RunFailurePanel : toutes les données
viennent déjà calculées de l'appelant.
"""

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QFont
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QStackedLayout, QPlainTextEdit,
)

from ui.styles import COLORS, FONT_MONO_STACK, FONT_MONO


class _TimelineTrack(QWidget):
    """Piste d'une étape : fond arrondi + segments colorés (une étape normale n'en a qu'un, une
    étape en échec avec plusieurs tentatives en a plusieurs, reliés par de fins connecteurs — le
    délai d'attente entre tentatives). Couleurs reçues en hex déjà résolu (pas une clé COLORS) :
    l'appelant peut avoir besoin d'une couleur de famille (STEP_META, hors de COLORS), autant
    accepter du hex partout plutôt que deux conventions différentes."""

    def __init__(self, bars: list[tuple[float, float, str]],
                 connectors: list[tuple[float, float]] | None = None, parent=None):
        super().__init__(parent)
        self._bars = bars
        self._connectors = connectors or []
        self.setFixedHeight(11)
        self.setMinimumWidth(80)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(COLORS["bg_card"]))
        painter.drawRoundedRect(0, 0, w, h, 3, 3)

        painter.setPen(QColor(COLORS["border"]))
        for start, width, in self._connectors:
            y = h / 2
            painter.drawLine(int(start * w), int(y), int((start + width) * w), int(y))

        painter.setPen(Qt.NoPen)
        for start, width, color_hex in self._bars:
            painter.setBrush(QColor(color_hex))
            painter.drawRoundedRect(int(start * w), 0, max(2, int(width * w)), h, 3, 3)
        painter.end()


class RunTimelinePanel(QWidget):
    HEIGHT = 188

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(self.HEIGHT)
        self.setStyleSheet(f"background: {COLORS['bg_panel']}; border-top: 1px solid {COLORS['border']};")
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        tab_row = QHBoxLayout()
        tab_row.setContentsMargins(20, 10, 20, 8)
        tab_row.setSpacing(16)
        self._tab_chrono = self._make_tab_button("Chronogramme")
        self._tab_chrono.clicked.connect(lambda: self._set_active_tab(0))
        self._tab_journal = self._make_tab_button("Journal")
        self._tab_journal.clicked.connect(lambda: self._set_active_tab(1))
        tab_row.addWidget(self._tab_chrono)
        tab_row.addWidget(self._tab_journal)
        tab_row.addStretch()

        self._status_dot = QLabel()
        self._status_dot.setFixedSize(7, 7)
        self._status_text = QLabel()
        self._status_text.setStyleSheet(f"color: {COLORS['text_dim']}; font-size: 12px; background: transparent; border: none;")
        tab_row.addWidget(self._status_dot)
        tab_row.addWidget(self._status_text)
        root.addLayout(tab_row)

        sep = QWidget(); sep.setFixedHeight(1); sep.setStyleSheet(f"background: {COLORS['border']};")
        root.addWidget(sep)

        self._stack = QStackedLayout()
        stack_host = QWidget()
        stack_host.setLayout(self._stack)
        root.addWidget(stack_host, stretch=1)

        self._chrono_page = QWidget()
        self._chrono_layout = QVBoxLayout(self._chrono_page)
        self._chrono_layout.setContentsMargins(20, 8, 20, 10)
        self._chrono_layout.setSpacing(5)
        self._stack.addWidget(self._chrono_page)

        self._journal_text = QPlainTextEdit()
        self._journal_text.setReadOnly(True)
        self._journal_text.setFont(QFont(FONT_MONO, 10))
        self._journal_text.setStyleSheet(
            f"QPlainTextEdit {{ background: {COLORS['bg_main']}; color: {COLORS['text_main']}; "
            f"border: none; padding: 10px 20px; }}"
        )
        self._stack.addWidget(self._journal_text)

        self._set_active_tab(0)

    def _make_tab_button(self, text: str) -> QPushButton:
        btn = QPushButton(text)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setFlat(True)
        return btn

    def _set_active_tab(self, index: int) -> None:
        self._stack.setCurrentIndex(index)
        for i, btn in enumerate((self._tab_chrono, self._tab_journal)):
            active = i == index
            btn.setStyleSheet(
                f"QPushButton {{ background: transparent; border: none; border-bottom: 2px solid "
                f"{COLORS['accent'] if active else 'transparent'}; border-radius: 0; "
                f"padding: 0 0 4px 0; color: {COLORS['text_main'] if active else COLORS['text_dim']}; "
                f"font-size: 13px; font-weight: {600 if active else 500}; }}"
            )

    def set_data(self, *, status_color: str, status_text: str,
                 time_axis_labels: list[str], rows: list[dict], journal_text: str,
                 footnote: str | None = None):
        """`rows` : [{"label": str, "label_color": hex, "bars": [(start,width,hex)],
        "connectors": [(start,width)], "duration_text": str, "duration_color": hex}] — couleurs
        en hex déjà résolu, voir docstring de _TimelineTrack."""
        self._status_dot.setStyleSheet(f"background: {status_color}; border-radius: 3px;")
        self._status_text.setText(status_text)

        while self._chrono_layout.count():
            item = self._chrono_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

        axis_row = QHBoxLayout()
        axis_row.setSpacing(12)
        axis_row.addSpacing(170)
        axis_labels_row = QHBoxLayout()
        for label in time_axis_labels:
            lbl = QLabel(label)
            lbl.setStyleSheet(f"color: {COLORS['text_dim']}; font-family: {FONT_MONO_STACK}; font-size: 10px; background: transparent; border: none;")
            axis_labels_row.addWidget(lbl)
            axis_labels_row.addStretch()
        axis_row.addLayout(axis_labels_row, stretch=1)
        axis_row.addSpacing(90)
        self._chrono_layout.addLayout(axis_row)

        for row in rows:
            r = QHBoxLayout(); r.setSpacing(12)
            lbl = QLabel(row["label"])
            lbl.setFixedWidth(170)
            lbl.setStyleSheet(f"color: {row.get('label_color', COLORS['text_main'])}; background: transparent; border: none;")
            r.addWidget(lbl)
            track = _TimelineTrack(row["bars"], row.get("connectors"))
            r.addWidget(track, stretch=1)
            dur = QLabel(row["duration_text"])
            dur.setFixedWidth(90)
            dur.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            dur.setStyleSheet(f"color: {row.get('duration_color', COLORS['text_dim'])}; font-family: {FONT_MONO_STACK}; font-size: 12px; background: transparent; border: none;")
            r.addWidget(dur)
            self._chrono_layout.addLayout(r)

        if footnote:
            note = QLabel(footnote)
            note.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 11px; background: transparent; border: none; padding-left: 182px;")
            self._chrono_layout.addWidget(note)
        self._chrono_layout.addStretch()

        self._journal_text.setPlainText(journal_text or "")

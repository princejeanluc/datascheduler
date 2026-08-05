"""
DataScheduler — ui/help/help_view.py
Vue "Aide" : documentation pédagogique intégrée à l'application, pour que l'utilisateur final
reste autonome sans dépendre de quelqu'un d'autre pour comprendre l'outil.
"""

from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QListWidget, QListWidgetItem, QTextBrowser, QFrame,
)
from PySide6.QtCore import Qt
from ui.styles import COLORS
from ui.main_window.widgets import _icon, _make_search_input, _make_title, _make_subtitle
from .content import HELP_TOPICS


class HelpView(QWidget):
    def __init__(self):
        super().__init__()
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(24)

        header = QHBoxLayout()
        title_col = QVBoxLayout(); title_col.setSpacing(2)
        title_col.addWidget(_make_title("Aide"))
        title_col.addWidget(_make_subtitle("Guide d'utilisation de DataScheduler"))
        header.addLayout(title_col); header.addStretch()
        self.inp_search = _make_search_input("Rechercher une rubrique…")
        self.inp_search.textChanged.connect(self._on_search_changed)
        header.addWidget(self.inp_search)
        layout.addLayout(header)

        sep = QFrame(); sep.setObjectName("separator"); sep.setFrameShape(QFrame.HLine)
        layout.addWidget(sep)

        body = QHBoxLayout(); body.setSpacing(20)

        self.list_topics = QListWidget()
        self.list_topics.setObjectName("card")
        self.list_topics.setFixedWidth(240)
        self.list_topics.setStyleSheet(
            "QListWidget { padding: 6px; }"
            f"QListWidget::item {{ padding: 10px 12px; border-radius: 4px; color: {COLORS['text_main']}; }}"
            f"QListWidget::item:selected {{ background-color: {COLORS['bg_active']}; color: {COLORS['text_main']}; }}"
            f"QListWidget::item:hover:!selected {{ background-color: {COLORS['bg_hover']}; }}"
        )
        for topic in HELP_TOPICS:
            item = QListWidgetItem(_icon(topic.icon, COLORS["text_dim"]), topic.title)
            item.setData(Qt.UserRole, topic.key)
            self.list_topics.addItem(item)
        self.list_topics.currentRowChanged.connect(self._on_topic_selected)
        body.addWidget(self.list_topics)

        self.browser = QTextBrowser()
        self.browser.setObjectName("card")
        self.browser.setOpenExternalLinks(False)
        self.browser.setStyleSheet(
            f"QTextBrowser {{ padding: 20px; font-size: 13px; color: {COLORS['text_main']}; }}"
        )
        body.addWidget(self.browser, stretch=1)

        layout.addLayout(body, stretch=1)

        if HELP_TOPICS:
            self.list_topics.setCurrentRow(0)

    def _on_topic_selected(self, row: int):
        if row < 0 or row >= len(HELP_TOPICS):
            return
        self.browser.setMarkdown(HELP_TOPICS[row].markdown)

    def _on_search_changed(self, text: str):
        needle = text.strip().lower()
        for i in range(self.list_topics.count()):
            topic = HELP_TOPICS[i]
            item = self.list_topics.item(i)
            matches = not needle or needle in topic.title.lower() or needle in topic.markdown.lower()
            item.setHidden(not matches)

"""
DataScheduler — ui/graph_editor/help_popup.py
Fenêtre d'aide contextuelle de l'éditeur graphique (chantier UX éditeur, Lot 3, C2) : réutilise
le rendu Markdown déjà établi par ui/help/help_view.py (QTextBrowser.setMarkdown), sans son
panneau liste/recherche à deux volets — inutile pour un sujet fixe unique.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QPushButton, QTextBrowser

from ui.styles import COLORS, DIALOG_STYLE
from ui.help.content import HelpTopic


class GraphHelpDialog(QDialog):
    def __init__(self, topic: HelpTopic, parent=None):
        super().__init__(parent)
        self.setWindowTitle(topic.title)
        self.setMinimumSize(560, 480)
        self.setStyleSheet(DIALOG_STYLE)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        title = QLabel(topic.title)
        title.setStyleSheet(f"font-size: 15px; font-weight: 700; color: {COLORS['text_main']};")
        layout.addWidget(title)

        browser = QTextBrowser()
        browser.setObjectName("card")
        browser.setOpenExternalLinks(False)
        browser.setStyleSheet(
            f"QTextBrowser {{ padding: 16px; font-size: 13px; color: {COLORS['text_main']}; }}"
        )
        browser.setMarkdown(topic.markdown)
        layout.addWidget(browser, stretch=1)

        btn_close = QPushButton("Fermer")
        btn_close.setFixedHeight(34)
        btn_close.clicked.connect(self.accept)
        layout.addWidget(btn_close, alignment=Qt.AlignRight)

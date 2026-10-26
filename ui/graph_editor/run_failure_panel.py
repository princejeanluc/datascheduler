"""
DataScheduler — ui/graph_editor/run_failure_panel.py
Panneau de diagnostic d'un run en échec (C9, frame Atelier-echec) — remplace le panneau
"Paramètres du pipeline" tant qu'une vue d'exécution est ouverte (bascule faite par l'hôte,
AtelierPipelinesView, jamais par ce widget). Purement un afficheur : toutes les données
(message, tentatives, suite, piste) sont déjà calculées par l'appelant (graph_editor_widget.py,
via run_status.py) — ce widget ne lit jamais la DB lui-même.
"""

from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame

from ui.styles import COLORS, FONT_MONO_STACK


class RunFailurePanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header = QVBoxLayout()
        header.setContentsMargins(18, 16, 18, 12)
        header.setSpacing(6)
        self._eyebrow = QLabel()
        self._eyebrow.setStyleSheet(
            f"color: {COLORS['danger']}; font-family: {FONT_MONO_STACK}; font-size: 10px; "
            f"letter-spacing: 0.06em; background: transparent; border: none;"
        )
        header.addWidget(self._eyebrow)
        self._title = QLabel()
        self._title.setStyleSheet(
            f"color: {COLORS['text_main']}; font-size: 17px; font-weight: 600; "
            f"background: transparent; border: none;"
        )
        header.addWidget(self._title)
        root.addLayout(header)
        root.addWidget(self._sep())

        self._body = QVBoxLayout()
        self._body.setContentsMargins(18, 14, 18, 14)
        self._body.setSpacing(16)
        root.addLayout(self._body)
        root.addStretch()

    @staticmethod
    def _sep() -> QFrame:
        f = QFrame(); f.setFrameShape(QFrame.HLine)
        f.setStyleSheet(f"background: {COLORS['border']}; max-height: 1px;")
        return f

    @staticmethod
    def _section_label(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(
            f"color: {COLORS['text_dim']}; font-size: 11px; font-weight: 600; "
            f"letter-spacing: 0.06em; background: transparent; border: none;"
        )
        return lbl

    def _clear_body(self):
        while self._body.count():
            item = self._body.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
                continue
            sub = item.layout()
            if sub is not None:
                while sub.count():
                    sub.takeAt(0)

    def set_data(self, *, eyebrow: str, title: str, error_text: str,
                 attempts: list[tuple[str, str]], what_happened: list[str],
                 piste: str | None, resume_hint: str | None):
        """`attempts` : [(horodatage déjà formaté "HH:MM:SS", mot d'issue)]. `piste`/
        `resume_hint` : None masque entièrement leur section (voir note d'impact — piste bornée
        à certains types, resume_hint seulement si le run est repris possible)."""
        self._eyebrow.setText(eyebrow)
        self._title.setText(title)
        self._clear_body()

        box = QLabel(error_text)
        box.setWordWrap(True)
        box.setStyleSheet(
            f"QLabel {{ font-family: {FONT_MONO_STACK}; font-size: 11.5px; line-height: 1.5; "
            f"padding: 10px 12px; border-radius: 6px; background: {COLORS['bg_main']}; "
            f"border: 1px solid {COLORS['danger']}; color: {COLORS['text_main']}; }}"
        )
        self._body.addWidget(box)

        if attempts:
            col = QVBoxLayout(); col.setSpacing(6)
            col.addWidget(self._section_label("TENTATIVES"))
            for n, (time_str, outcome) in enumerate(attempts, start=1):
                row = QHBoxLayout()
                left = QLabel(f"{n} · {time_str}")
                left.setStyleSheet(f"font-family: {FONT_MONO_STACK}; font-size: 12px; color: {COLORS['text_main']}; background: transparent; border: none;")
                row.addWidget(left)
                row.addStretch()
                right = QLabel(outcome)
                right.setStyleSheet(f"font-family: {FONT_MONO_STACK}; font-size: 12px; color: {COLORS['danger']}; background: transparent; border: none;")
                row.addWidget(right)
                col.addLayout(row)
            self._body.addLayout(col)

        if what_happened:
            col = QVBoxLayout(); col.setSpacing(6)
            col.addWidget(self._section_label("CE QUI S'EST PASSÉ ENSUITE"))
            for line in what_happened:
                lbl = QLabel(line)
                lbl.setWordWrap(True)
                lbl.setStyleSheet(f"color: {COLORS['text_main']}; background: transparent; border: none;")
                col.addWidget(lbl)
            self._body.addLayout(col)

        if piste:
            col = QVBoxLayout(); col.setSpacing(8)
            col.addWidget(self._section_label("PISTE"))
            lbl = QLabel(piste)
            lbl.setWordWrap(True)
            lbl.setStyleSheet(f"color: {COLORS['text_dim']}; background: transparent; border: none;")
            col.addWidget(lbl)
            self._body.addLayout(col)

        if resume_hint:
            card = QFrame()
            card.setStyleSheet(
                f"QFrame {{ background: {COLORS['bg_card']}; border: 1px solid {COLORS['warning']}; "
                f"border-radius: 8px; }}"
            )
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(12, 10, 12, 10)
            card_layout.setSpacing(6)
            title_lbl = QLabel("Reprendre depuis l'échec")
            title_lbl.setStyleSheet(f"color: {COLORS['text_main']}; font-weight: 600; background: transparent; border: none;")
            card_layout.addWidget(title_lbl)
            hint_lbl = QLabel(resume_hint)
            hint_lbl.setWordWrap(True)
            hint_lbl.setStyleSheet(f"color: {COLORS['text_dim']}; background: transparent; border: none;")
            card_layout.addWidget(hint_lbl)
            self._body.addWidget(card)

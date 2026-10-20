"""
DataScheduler — ui/components/bubble.py
Bulle partagée (refonte, lot A-Historique — FONDATIONS.md section 3 : « ancrée à un élément, avec
une flèche »). Premier écran à en avoir besoin (Historique, jour de la carte de fréquence).

Contrairement à SidePanel (glisse dans la vue, ferme par Échap/bouton « ✕ » uniquement), une bulle
est une vraie fenêtre popup (`Qt.Popup`) : Qt la ferme déjà tout seul sur un clic en dehors ou la
perte de focus, sans qu'on ait à installer un filtre d'événements sur l'application entière pour
ça — comportement natif, même famille que QMenu. Échap est géré explicitement en plus, par
cohérence avec les autres composants de la refonte.

Ne gère que le chrome (position ancrée, flèche, fermeture) : la composition du contenu reste à la
charge de l'appelant via `set_content()`, même contrat que `SidePanel`.
"""

from PySide6.QtCore import Qt, QPoint, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QBrush
from PySide6.QtWidgets import QFrame, QVBoxLayout, QGraphicsDropShadowEffect

from ui.styles import COLORS

_DEFAULT_WIDTH = 330
_ARROW_SIZE = 7
_ARROW_Y = 40   # distance verticale entre le haut de la bulle et la pointe de la flèche


class Bubble(QFrame):
    """`parent` sert uniquement à l'ancrage Qt (ownership) — la bulle est un vrai popup, jamais
    repositionnée par un redimensionnement du parent (contrairement à SidePanel) : elle se ferme
    plutôt que de suivre, un jour cliqué sur la carte ne bouge pas pendant qu'elle est ouverte."""

    closed = Signal()

    def __init__(self, parent, width: int = _DEFAULT_WIDTH):
        super().__init__(parent, Qt.Popup)
        self._width = width
        self._content = None

        self.setObjectName("bubble")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(
            f"QFrame#bubble {{ background: {COLORS['bg_panel']}; "
            f"border: 1px solid {COLORS['border_strong']}; border-radius: 10px; }}"
        )

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(28)
        shadow.setYOffset(10)
        shadow.setColor(QColor(0, 0, 0, 160))
        self.setGraphicsEffect(shadow)

        # Marge gauche réservée à la flèche (peinte dans paintEvent, à l'intérieur des bornes du
        # widget — jamais en x négatif, qui serait rogné par le composited window system).
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(_ARROW_SIZE + 3, 0, 0, 0)
        self._layout.setSpacing(0)

        self.hide()

    def set_content(self, widget) -> None:
        if self._content is not None:
            self._layout.removeWidget(self._content)
            self._content.deleteLater()
        self._content = widget
        self._layout.addWidget(widget)

    def open_at(self, anchor) -> None:
        """Positionne la bulle à droite de `anchor` (widget déjà visible, coordonnées globales via
        mapToGlobal), flèche pointant vers lui — ajuste la taille au contenu avant de positionner,
        comme un menu natif."""
        self.setFixedWidth(self._width)
        self.adjustSize()
        global_point = anchor.mapToGlobal(QPoint(anchor.width() + 8, -_ARROW_Y + self.height() // 2))
        self.move(global_point)
        self.show()
        self.raise_()

    def hideEvent(self, event):
        # Qt.Popup masque tout seul sur un clic en dehors/perte de focus (hide(), pas close()) —
        # hideEvent() est donc le seul endroit fiable pour émettre `closed` dans tous les cas.
        super().hideEvent(event)
        self.closed.emit()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.hide()
            return
        super().keyPressEvent(event)

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        path = QPainterPath()
        path.moveTo(_ARROW_SIZE + 1, _ARROW_Y - _ARROW_SIZE)
        path.lineTo(1, _ARROW_Y)
        path.lineTo(_ARROW_SIZE + 1, _ARROW_Y + _ARROW_SIZE)
        path.closeSubpath()
        painter.setBrush(QBrush(QColor(COLORS["bg_panel"])))
        painter.setPen(QPen(QColor(COLORS["border_strong"]), 1))
        painter.drawPath(path)

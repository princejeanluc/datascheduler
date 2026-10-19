"""
DataScheduler — ui/components/switch.py
Interrupteur partagé (refonte, lot A-Paramètres — FONDATIONS.md section 3 : « 38 x 22 px, accent
quand activé »). Structure confirmée sur les maquettes Parametres*.html (role="switch" — fond
plein, pastille blanche qui glisse). QAbstractButton checkable plutôt que QCheckBox : un
QCheckBox stylé en QSS ne sait pas dessiner une pastille qui se déplace sans image externe, et ce
projet embarque ses icônes en qtawesome, pas en fichiers image séparés (voir KULU.spec). Fournit
isChecked()/setChecked()/toggled, remplacement direct d'un QCheckBox pour un réglage booléen de
premier plan (pas une case dans un tableau, qui reste QCheckBox standard ailleurs dans l'app).
"""

from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QPainter, QColor
from PySide6.QtWidgets import QAbstractButton

from ui.styles import COLORS

_WIDTH, _HEIGHT = 38, 22
_THUMB = 18
_MARGIN = 2


class Switch(QAbstractButton):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(_WIDTH, _HEIGHT)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)

        track_color = COLORS["accent"] if self.isChecked() else COLORS["border"]
        painter.setBrush(QColor(track_color))
        painter.drawRoundedRect(QRectF(0, 0, _WIDTH, _HEIGHT), _HEIGHT / 2, _HEIGHT / 2)

        thumb_x = _WIDTH - _THUMB - _MARGIN if self.isChecked() else _MARGIN
        painter.setBrush(QColor(COLORS["text_main"]))
        painter.drawEllipse(QRectF(thumb_x, _MARGIN, _THUMB, _THUMB))


def make_switch() -> Switch:
    return Switch()

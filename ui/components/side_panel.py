"""
DataScheduler — ui/components/side_panel.py
Panneau latéral partagé (refonte, lot A-Aujourd'hui — FONDATIONS.md section 3 : « glisse depuis
la droite (560 px par défaut), ombre, se ferme par Échap »). Premier écran à en avoir besoin
(Aujourd'hui, détail d'une exécution) ; Historique et Connexions le réutiliseront dans un lot
ultérieur sans changement attendu ici.

Classe, pas une fonction comme les autres composants partagés (`make_banner`, `make_info_pill`) :
ce composant est intrinsèquement à état (ouvert/fermé, contenu remplaçable), pas un simple widget
stylé construit une fois — même raison que `Switch` (ui/components/switch.py).

Ne gère que le chrome (glissement, ombre, fermeture) : la composition du contenu (surtitre, titre,
corps, pied d'actions) reste entièrement à la charge de l'appelant via `set_content()`, pour ne
pas présumer d'une structure que de futurs consommateurs (Historique, Connexions) pourraient ne
pas partager.
"""

from PySide6.QtCore import Qt, QSize, QRect, QPropertyAnimation, QEasingCurve, QEvent, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QGraphicsDropShadowEffect, QSizePolicy,
)

from ui.styles import COLORS

_DEFAULT_WIDTH = 560


class SidePanel(QWidget):
    """S'attache à `parent` (la vue dans laquelle il doit glisser, pas la fenêtre entière) et se
    positionne lui-même en absolu par-dessus — `parent` doit donc être un widget déjà dans un
    layout réel (pas une fenêtre top-level), pour que `parent.rect()` reflète la zone à couvrir."""

    closed = Signal()

    def __init__(self, parent: QWidget, width: int = _DEFAULT_WIDTH):
        # Import différé : ui.main_window.widgets (via ui.main_window) importe lui-même des
        # modules qui importent ui.components — un import en tête de fichier ici créerait une
        # dépendance circulaire selon l'ordre d'import (même précaution que page_header.py).
        from ui.main_window.widgets import _icon

        super().__init__(parent)
        self._panel_width = width
        self._content: QWidget | None = None
        # Lot A-Pipelines (A10) : garde-fou optionnel, rétrocompatible — par défaut None, aucun
        # changement de comportement pour les appelants existants (Aujourd'hui). Même garantie que
        # l'ancien PipelineDryRunDialog.closeEvent() ("fermeture bloquée tant que ça tourne"), pour
        # un contenu qui lance un traitement en arrière-plan (validation à blanc) et ne doit pas
        # pouvoir être fermé pendant qu'il tourne.
        self._close_guard = None
        # Sélecteur d'ID (objectName), pas une règle nue — même précaution que partout ailleurs
        # dans la refonte (REGLES.md section 3) : une règle nue poserait les mêmes risques de
        # cascade vers les enfants qu'un `setStyleSheet("background: ...; border: ...;")` direct.
        self.setObjectName("side_panel")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(
            f"QWidget#side_panel {{ background: {COLORS['bg_panel']}; "
            f"border-left: 1px solid {COLORS['border_strong']}; }}"
        )
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        self.hide()

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(32)
        shadow.setXOffset(-4)
        shadow.setYOffset(0)
        shadow.setColor(QColor(0, 0, 0, 160))
        self.setGraphicsEffect(shadow)

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)

        close_row = QWidget()
        close_row.setStyleSheet("background: transparent;")
        close_row_layout = QHBoxLayout(close_row)
        close_row_layout.setContentsMargins(12, 10, 12, 0)
        close_row_layout.addStretch()
        # Icône qtawesome plutôt qu'un glyphe Unicode brut ("✕") : un glyphe texte dépend de sa
        # présence dans la police embarquée/ses polices de repli, qui peut rester vide sur
        # certaines machines (bug déjà rencontré et documenté, voir ui/sql_editor.py).
        self._btn_close = QPushButton()
        self._btn_close.setIcon(_icon("fa5s.times", COLORS["text_muted"]))
        self._btn_close.setIconSize(QSize(12, 12))
        self._btn_close.setFixedSize(26, 26)
        self._btn_close.setCursor(Qt.PointingHandCursor)
        self._btn_close.setStyleSheet(
            f"QPushButton {{ background: transparent; border: none; border-radius: 13px; }}"
            f"QPushButton:hover {{ background: {COLORS['bg_hover']}; }}"
        )
        self._btn_close.clicked.connect(self.close)
        close_row_layout.addWidget(self._btn_close)
        self._layout.addWidget(close_row)

        self._content_host = QWidget()
        self._content_host.setStyleSheet("background: transparent;")
        self._content_host_layout = QVBoxLayout(self._content_host)
        self._content_host_layout.setContentsMargins(0, 0, 0, 0)
        self._layout.addWidget(self._content_host, stretch=1)

        parent.installEventFilter(self)

        self._anim = QPropertyAnimation(self, b"geometry", self)
        self._anim.setDuration(220)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)

    # ── Contenu ────────────────────────────────────

    def set_content(self, widget: QWidget) -> None:
        if self._content is not None:
            self._content_host_layout.removeWidget(self._content)
            self._content.deleteLater()
        self._content = widget
        self._content_host_layout.addWidget(widget)

    def set_close_guard(self, fn) -> None:
        """`fn` : `Callable[[], bool] | None` — si `fn()` renvoie vrai, `close()` ne fait rien
        (ni Échap, ni le bouton « ✕ », ni un appel direct). Remis à None par défaut par chaque
        appel : à l'appelant de rappeler `set_close_guard(None)` une fois le traitement terminé."""
        self._close_guard = fn

    # ── Ouverture / fermeture ──────────────────────

    def _resting_geometry(self):
        p = self.parentWidget()
        return p.width() - self._panel_width, 0, self._panel_width, p.height()

    def _offscreen_geometry(self):
        p = self.parentWidget()
        return p.width(), 0, self._panel_width, p.height()

    def open(self) -> None:
        self.setGeometry(QRect(*self._offscreen_geometry()))
        self.show()
        self.raise_()
        self._anim.stop()
        self._anim.setStartValue(self.geometry())
        self._anim.setEndValue(QRect(*self._resting_geometry()))
        self._anim.start()

    def close(self) -> None:
        if not self.isVisible():
            return
        if self._close_guard is not None and self._close_guard():
            return
        self._anim.stop()
        self._anim.setStartValue(self.geometry())
        self._anim.setEndValue(QRect(*self._offscreen_geometry()))
        self._anim.finished.connect(self._on_close_animation_finished)
        self._anim.start()

    def _on_close_animation_finished(self) -> None:
        self._anim.finished.disconnect(self._on_close_animation_finished)
        self.hide()
        self.closed.emit()

    # ── Échap + suivi du redimensionnement du parent ──

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.close()
            return
        super().keyPressEvent(event)

    def eventFilter(self, watched, event):
        if watched is self.parentWidget() and event.type() == QEvent.Resize and self.isVisible():
            x, y, w, h = self._resting_geometry()
            self.setGeometry(x, y, w, h)
        return super().eventFilter(watched, event)

"""
DataScheduler — ui/graph_editor/zoom_widget.py
Widget de zoom flottant du canevas (chantier identité visuelle, maquette approuvée) : +/- et le
pourcentage courant, en plus du zoom à la molette déjà existant (PipelineGraphView.wheelEvent).
Même patron que EditorToolRail/GraphMinimapWidget — panneau flottant ancré au viewport, coin
bas-gauche (opposé à la mini-carte, bas-droite).
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel

from ui.styles import COLORS, FONT_MONO_STACK
from ui.main_window.widgets import _action_btn

_MARGIN_TO_PARENT = 16
_PANEL_PADDING = 4
_BUTTON_SIZE = (28, 28)
_ZOOM_FACTOR = 1.15


class ZoomWidget(QWidget):
    def __init__(self, view, parent=None):
        super().__init__(parent)
        self._view = view
        self.setObjectName("zoomWidgetPanel")
        self.setStyleSheet(f"""
            QWidget#zoomWidgetPanel {{
                background-color: rgba(28, 26, 23, 0.92);
                border: 1px solid {COLORS['border']};
                border-radius: 10px;
            }}
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(_PANEL_PADDING, _PANEL_PADDING, _PANEL_PADDING, _PANEL_PADDING)
        layout.setSpacing(2)

        self.btn_zoom_out = _action_btn(
            "fa5s.minus", object_name="secondary", tooltip="Zoom arrière", size=_BUTTON_SIZE,
        )
        self.btn_zoom_out.clicked.connect(self._on_zoom_out)
        layout.addWidget(self.btn_zoom_out)

        self.lbl_pct = QLabel("100 %")
        self.lbl_pct.setFixedWidth(44)
        self.lbl_pct.setAlignment(Qt.AlignCenter)
        self.lbl_pct.setStyleSheet(
            f"color: {COLORS['text_dim']}; font-size: 11.5px; font-weight: 600; "
            f"font-family: {FONT_MONO_STACK}; background: transparent; border: none;"
        )
        layout.addWidget(self.lbl_pct)

        self.btn_zoom_in = _action_btn(
            "fa5s.plus", object_name="secondary", tooltip="Zoom avant", size=_BUTTON_SIZE,
        )
        self.btn_zoom_in.clicked.connect(self._on_zoom_in)
        layout.addWidget(self.btn_zoom_in)

        self.refresh()

    def refresh(self) -> None:
        pct = round(self._view.transform().m11() * 100)
        self.lbl_pct.setText(f"{pct} %")

    def _on_zoom_out(self):
        self._view.scale(1 / _ZOOM_FACTOR, 1 / _ZOOM_FACTOR)
        self.refresh()
        if self._view._minimap is not None:
            self._view._minimap.request_repaint()

    def _on_zoom_in(self):
        self._view.scale(_ZOOM_FACTOR, _ZOOM_FACTOR)
        self.refresh()
        if self._view._minimap is not None:
            self._view._minimap.request_repaint()

    def reposition(self) -> None:
        parent = self.parentWidget()
        if parent is None:
            return
        self.adjustSize()
        y = parent.height() - self.height() - _MARGIN_TO_PARENT
        self.move(_MARGIN_TO_PARENT, max(0, y))

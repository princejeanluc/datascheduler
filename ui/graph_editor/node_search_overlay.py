"""
DataScheduler — ui/graph_editor/node_search_overlay.py
Recherche de nœud en surimpression du canevas (lot A-Atelier-main, A10) — remplace l'ancienne
barre horizontale au-dessus de la vue : même patron flottant que ZoomWidget/GraphMinimapWidget/
EditorToolRail, ancré en haut à droite du viewport. Le champ et sa logique de filtre
(`_on_search_changed`/`_on_search_jump`) restent dans PipelineGraphEditorWidget — ce widget n'est
qu'un conteneur de présentation.
"""

from PySide6.QtWidgets import QWidget, QHBoxLayout

from ui.styles import COLORS
from ui.main_window.widgets import _make_search_input

_MARGIN_TO_PARENT = 12
_PANEL_PADDING = 0


class NodeSearchOverlay(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("nodeSearchOverlayPanel")
        self.setStyleSheet(f"""
            QWidget#nodeSearchOverlayPanel {{
                background: transparent;
            }}
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(_PANEL_PADDING, _PANEL_PADDING, _PANEL_PADDING, _PANEL_PADDING)
        layout.setSpacing(0)

        self.inp_search = _make_search_input("Rechercher un nœud…")
        self.inp_search.setStyleSheet(
            f"QLineEdit {{ background: {COLORS['bg_panel']}; border: 1px solid {COLORS['border']}; "
            f"border-radius: 6px; padding: 0 10px; color: {COLORS['text_main']}; font-size: 12px; }}"
            f"QLineEdit:focus {{ border-color: {COLORS['accent']}; }}"
        )
        layout.addWidget(self.inp_search)

    def reposition(self) -> None:
        parent = self.parentWidget()
        if parent is None:
            return
        self.adjustSize()
        x = parent.width() - self.width() - _MARGIN_TO_PARENT
        self.move(max(0, x), _MARGIN_TO_PARENT)

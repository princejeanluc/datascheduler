"""
DataScheduler — ui/graph_editor/tool_rail.py
Rail d'icônes flottant du canevas (chantier chrome de l'éditeur, refonte visuelle — capture
utilisateur montrant la barre d'outils texte déborder/se tronquer, maquette approuvée). Regroupe
les actions d'édition du graphe (auparavant 6 boutons texte dans une QHBoxLayout unique) en un
panneau compact ancré près du bord du canevas — même esprit que la mini-carte
(minimap_widget.py), généralisé. Boutons via _action_btn() (ui/main_window/widgets.py), déjà le
patron établi et éprouvé ailleurs dans l'app (ui/main_window/history_view.py) pour un bouton
icône-seul — object_name="secondary" obligatoire sur chacun, sans quoi la règle QPushButton
globale de DIALOG_STYLE (fond orange plein) s'applique.
"""

from PySide6.QtWidgets import QWidget, QVBoxLayout, QFrame

from ui.styles import COLORS
from ui.main_window.widgets import _action_btn

_MARGIN_TO_PARENT = 18
_PANEL_PADDING = 6
_BUTTON_SIZE = (32, 32)


def _separator() -> QFrame:
    sep = QFrame()
    sep.setFrameShape(QFrame.HLine)
    sep.setStyleSheet(f"background: {COLORS['border']}; max-height: 1px; border: none;")
    return sep


class EditorToolRail(QWidget):
    def __init__(self, dialog, parent=None):
        super().__init__(parent)
        self._dialog = dialog
        self.setObjectName("toolRailPanel")
        self.setStyleSheet(f"""
            QWidget#toolRailPanel {{
                background-color: rgba(28, 26, 23, 0.92);
                border: 1px solid {COLORS['border']};
                border-radius: 12px;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(_PANEL_PADDING, _PANEL_PADDING, _PANEL_PADDING, _PANEL_PADDING)
        layout.setSpacing(4)

        # Groupe "Édition"
        self.btn_add_step = _action_btn(
            "fa5s.plus", object_name="secondary", tooltip="Ajouter une étape", size=_BUTTON_SIZE,
        )
        self.btn_add_step.clicked.connect(dialog._on_add_step)
        layout.addWidget(self.btn_add_step)

        self.btn_add_zone = _action_btn(
            "fa5s.object-group", object_name="secondary", size=_BUTTON_SIZE,
            tooltip="Ajouter une zone — regroupe visuellement des étapes, sans effet sur "
                    "l'exécution. Glisser l'en-tête pour déplacer, le coin bas-droit pour "
                    "redimensionner, double-clic pour renommer.",
        )
        self.btn_add_zone.clicked.connect(dialog._on_add_zone)
        layout.addWidget(self.btn_add_zone)

        self.btn_delete = _action_btn(
            "fa5s.trash-alt", object_name="secondary", tooltip="Supprimer la sélection",
            size=_BUTTON_SIZE,
        )
        self.btn_delete.clicked.connect(dialog._on_delete_selected)
        layout.addWidget(self.btn_delete)

        layout.addWidget(_separator())

        # Groupe "Mise en page"
        self.btn_auto_layout = _action_btn(
            "fa5s.sitemap", object_name="secondary", size=_BUTTON_SIZE,
            tooltip="Ranger automatiquement — repositionne les étapes par rang (colonnes de "
                    "gauche à droite selon l'ordre du graphe), sans changer les connexions.",
        )
        self.btn_auto_layout.clicked.connect(dialog._on_auto_layout)
        layout.addWidget(self.btn_auto_layout)

        self.btn_arrange_selection = _action_btn(
            "fa5s.object-ungroup", object_name="secondary", size=_BUTTON_SIZE,
            tooltip="Ranger la sélection — repositionne uniquement les étapes sélectionnées, "
                    "sans toucher au reste du graphe.",
        )
        self.btn_arrange_selection.clicked.connect(dialog._on_arrange_selection)
        layout.addWidget(self.btn_arrange_selection)

        self.btn_undo_layout = _action_btn(
            "fa5s.undo", object_name="secondary", tooltip="Annuler le rangement",
            size=_BUTTON_SIZE,
        )
        self.btn_undo_layout.setEnabled(False)
        self.btn_undo_layout.clicked.connect(dialog._on_undo_layout)
        layout.addWidget(self.btn_undo_layout)

        layout.addWidget(_separator())

        # Groupe "Vue"
        self.btn_toggle_minimap = _action_btn(
            "fa5s.map", object_name="secondary", tooltip="Mini-carte : afficher/masquer",
            size=_BUTTON_SIZE,
        )
        self.btn_toggle_minimap.clicked.connect(dialog._on_toggle_minimap)
        layout.addWidget(self.btn_toggle_minimap)

        layout.addWidget(_separator())

        # Groupe "Aide" (chantier UX éditeur, Lot 3, C2)
        self.btn_help = _action_btn(
            "fa5s.question-circle", object_name="secondary", size=_BUTTON_SIZE,
            tooltip="Aide sur l'éditeur graphique",
        )
        self.btn_help.clicked.connect(dialog._on_show_help)
        layout.addWidget(self.btn_help)

    def reposition(self) -> None:
        """Ancré en haut à gauche du viewport, marge fixe — contrairement à la mini-carte (coin
        bas-droit), cette position ne dépend pas de la taille du parent, mais reste appelée
        depuis PipelineGraphView.resizeEvent() par cohérence avec ce patron déjà établi."""
        self.adjustSize()
        self.move(_MARGIN_TO_PARENT, _MARGIN_TO_PARENT)

    def refresh_minimap_button_style(self, active: bool) -> None:
        """État "actif" du bouton mini-carte — échange direct de stylesheet en ligne, même
        patron que NavButton (ui/main_window/widgets.py) : aucun mécanisme dynamic-property/
        unpolish()/polish() n'existe ailleurs dans cette base. Un style défini directement sur
        l'instance du widget l'emporte toujours sur le style hérité (#secondary, DIALOG_STYLE),
        quelle que soit sa spécificité — setStyleSheet("") efface l'instance et retombe sur
        l'hérité."""
        if active:
            self.btn_toggle_minimap.setStyleSheet(f"""
                QPushButton {{
                    background-color: {COLORS['bg_active']};
                    border: 1px solid {COLORS['accent_dim']};
                    border-radius: 6px;
                }}
                QPushButton:hover {{
                    background-color: {COLORS['bg_active']};
                    border-color: {COLORS['accent']};
                }}
            """)
        else:
            self.btn_toggle_minimap.setStyleSheet("")

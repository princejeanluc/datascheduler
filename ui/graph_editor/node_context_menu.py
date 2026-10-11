"""
DataScheduler — ui/graph_editor/node_context_menu.py
Premier menu contextuel (clic-droit) de l'éditeur graphique (chantier duplication de nœud) —
conçu comme point d'extension réutilisable pour de futures actions ciblées sur un seul nœud,
pas un hack ponctuel. build_node_context_menu() construit et retourne le QMenu, ne l'exécute
jamais lui-même — c'est à l'appelant (PipelineGraphEditorDialog._on_node_context_menu) de
l'exécuter à la position voulue.
"""

from PySide6.QtWidgets import QMenu

from ui.styles import COLORS
from ui.step_editor.common import _icon


def build_node_context_menu(node, dialog) -> QMenu:
    menu = QMenu(dialog)

    act_dup = menu.addAction(_icon("fa5s.clone", COLORS["accent"]), "Dupliquer")
    act_dup.setShortcut("Ctrl+D")
    act_dup.triggered.connect(dialog._on_duplicate_selected)

    menu.addSeparator()
    act_future = menu.addAction("(futures actions ici)")
    act_future.setEnabled(False)

    menu.addSeparator()
    act_del = menu.addAction(_icon("fa5s.trash-alt", COLORS["danger"]), "Supprimer")
    act_del.triggered.connect(dialog._on_delete_selected)

    return menu

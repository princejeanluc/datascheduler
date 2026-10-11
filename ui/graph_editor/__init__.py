"""
DataScheduler — ui/graph_editor/__init__.py
Package de l'éditeur graphique de pipeline (chantier 6b) — voir docs/ARCHITECTURE.md.
"""

from .graph_editor_dialog import PipelineGraphEditorDialog
from .graph_editor_widget import PipelineGraphEditorWidget

__all__ = ["PipelineGraphEditorDialog", "PipelineGraphEditorWidget"]

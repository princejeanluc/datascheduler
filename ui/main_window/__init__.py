"""
DataScheduler — ui/main_window/__init__.py
Package de la fenêtre principale (éclaté depuis l'ancien ui/main_window.py — voir
docs/ARCHITECTURE.md). `run()` est le seul nom jamais importé de l'extérieur (main.py).
"""

from .window import run

__all__ = ["run"]

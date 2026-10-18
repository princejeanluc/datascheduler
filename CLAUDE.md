# Kulu : consignes pour Claude Code

Kulu est une application de bureau PySide6 (Windows d'abord) qui planifie et exécute des pipelines de données. Version de départ de la refonte : 0.45.0.

## Refonte de l'interface en cours

Toute tâche qui touche `ui/` dans le cadre de la refonte suit les règles de `docs/refonte/REGLES.md`. Lis-les avant de proposer un plan.

@docs/refonte/REGLES.md

## Commandes

- Tests : `python -m pytest tests -q` (chaque test d'interface fixe `QT_QPA_PLATFORM=offscreen` en tête de fichier, voir `tests/test_settings_view.py`)
- Lancer l'application : `python main.py`
- Build Windows : `build.bat` (PyInstaller, `KULU.spec`)

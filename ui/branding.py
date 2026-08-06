"""
DataScheduler — ui/branding.py
Icône de l'application, encodée en base64 plutôt que chargée depuis un fichier — évite toute
résolution de chemin sys._MEIPASS dans l'exe gelé, même convention que ui/help/content.py pour
les rubriques d'aide (embarquées comme chaînes Python, pas comme fichiers .md).

DataScheduler.spec (icon=...) couvre déjà l'icône de l'exécutable lui-même (Explorateur, tuile
avant lancement). Ça ne couvre PAS la fenêtre une fois affichée : Qt ne reprend pas
automatiquement l'icône de l'exe pour la barre de titre / le bouton de la barre des tâches
pendant l'exécution / Alt-Tab — il faut la poser explicitement via QApplication.setWindowIcon().
"""

import base64

from PySide6.QtCore import QByteArray
from PySide6.QtGui import QIcon, QPixmap

# PNG 128×128, fond transparent — dérivé de assets/icon.png (logo fourni par l'utilisateur).
_ICON_PNG_B64 = (
    "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"
)


def app_icon() -> QIcon:
    """Icône de l'application, à poser sur QApplication (voir docstring du module)."""
    data = QByteArray(base64.b64decode(_ICON_PNG_B64))
    pixmap = QPixmap()
    pixmap.loadFromData(data, "PNG")
    return QIcon(pixmap)

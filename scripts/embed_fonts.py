"""
DataScheduler — scripts/embed_fonts.py
Utilitaire dev (jamais exécuté par l'application) : lit les .ttf sources dans resources/fonts/
et régénère ui/fonts.py, où chaque police est embarquée en base64 — même convention que
ui/branding.py (icône) et ui/help/content.py (rubriques d'aide), pour éviter toute résolution
de chemin sys._MEIPASS dans l'exe gelé.

À relancer uniquement si les fichiers de police source changent (mise à jour de version,
ajout d'une graisse). Usage : python scripts/embed_fonts.py
"""

import base64
from pathlib import Path

FONTS_DIR = Path(__file__).resolve().parent.parent / "resources" / "fonts"
OUTPUT_FILE = Path(__file__).resolve().parent.parent / "ui" / "fonts.py"

# (nom de variable, fichier source, famille Qt attendue après enregistrement)
FONT_FILES = [
    ("IBM_PLEX_SANS_REGULAR", "IBMPlexSans-Regular.ttf"),
    ("IBM_PLEX_SANS_MEDIUM", "IBMPlexSans-Medium.ttf"),
    ("IBM_PLEX_SANS_SEMIBOLD", "IBMPlexSans-SemiBold.ttf"),
    ("IBM_PLEX_SANS_BOLD", "IBMPlexSans-Bold.ttf"),
    ("JETBRAINS_MONO_REGULAR", "JetBrainsMono-Regular.ttf"),
    ("JETBRAINS_MONO_MEDIUM", "JetBrainsMono-Medium.ttf"),
    ("JETBRAINS_MONO_BOLD", "JetBrainsMono-Bold.ttf"),
]


def _wrap_b64(data: bytes, indent: str = "    ") -> str:
    encoded = base64.b64encode(data).decode("ascii")
    chunk = 96
    lines = [encoded[i : i + chunk] for i in range(0, len(encoded), chunk)]
    quoted = "\n".join(f'{indent}"{line}"' for line in lines)
    return quoted


def main() -> None:
    constants = []
    var_names = []
    for var_name, filename in FONT_FILES:
        path = FONTS_DIR / filename
        data = path.read_bytes()
        var_names.append(var_name)
        constants.append(f"_{var_name}_B64 = (\n{_wrap_b64(data)}\n)")

    body = "\n\n".join(constants)
    font_list = ",\n    ".join(f"_{name}_B64" for name in var_names)

    source = f'''"""
DataScheduler — ui/fonts.py
GÉNÉRÉ par scripts/embed_fonts.py — ne pas éditer à la main.

Polices IBM Plex Sans et JetBrains Mono (SIL Open Font License 1.1), embarquées en base64
plutôt que chargées depuis des fichiers — même convention que ui/branding.py (icône), pour
éviter toute résolution de chemin sys._MEIPASS dans l'exe gelé.
"""

import base64
import logging

from PySide6.QtCore import QByteArray
from PySide6.QtGui import QFontDatabase

logger = logging.getLogger(__name__)

{body}

_ALL_FONTS_B64 = [
    {font_list},
]


def register_app_fonts() -> None:
    """Enregistre les polices embarquées auprès de Qt. Ne lève jamais : un échec individuel
    (police corrompue, etc.) est journalisé et ignoré — l'application retombe alors sur les
    polices système via les chaînes de repli définies dans ui/styles.py."""
    for encoded in _ALL_FONTS_B64:
        try:
            data = QByteArray(base64.b64decode(encoded))
            font_id = QFontDatabase.addApplicationFontFromData(data)
            if font_id == -1:
                logger.warning("Échec de l'enregistrement d'une police embarquée (ignoré).")
        except Exception:
            logger.warning("Erreur lors de l'enregistrement d'une police embarquée (ignoré).")
'''

    OUTPUT_FILE.write_text(source, encoding="utf-8")
    print(f"ui/fonts.py régénéré ({len(FONT_FILES)} polices embarquées).")


if __name__ == "__main__":
    main()

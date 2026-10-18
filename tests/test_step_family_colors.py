"""
DataScheduler — tests/test_step_family_colors.py
Refonte, lot 0a : la couleur par type d'étape (STEP_META[...]["color"]) est désormais dérivée
d'une des 7 familles (maquette Grammaire), pas écrite à la main par type. "family" est distincte
de "category" (qui pilote les sections de StepTypeChooserDialog, inchangées par ce lot).
"""

from ui.step_editor.common import STEP_META, _FAMILY_COLORS

EXPECTED_FAMILY_OF = {
    "DB_EXTRACT": "Extraction et chargement",
    "FTP_DOWNLOAD": "Extraction et chargement",
    "DB_LOAD": "Extraction et chargement",
    "FTP_UPLOAD": "Transfert et diffusion",
    "LOCAL_COPY": "Transfert et diffusion",
    "COMPRESS": "Transfert et diffusion",
    "DB_EXECUTE": "Exécution et scripts",
    "PYTHON_SCRIPT": "Exécution et scripts",
    "SPARK_SQL": "Big Data",
    "SQOOP_EXPORT": "Big Data",
    "SQOOP_IMPORT": "Big Data",
    "EMAIL_NOTIFY": "Notification",
    "HTTP_REQUEST": "Notification",
    "CONDITION": "Passerelles",
    "GATEWAY_PARALLEL": "Passerelles",
    "GATEWAY_JOIN": "Passerelles",
    "EXTRACT_VARIABLES": "Variables",
    "SET_VARIABLE": "Variables",
}


def test_seven_families_declared_with_their_documented_hex():
    expected = {
        "Extraction et chargement": "#6BB4CF",
        "Transfert et diffusion": "#b5c96a",
        "Exécution et scripts": "#d68fb8",
        "Big Data": "#4fb3a0",
        "Notification": "#c9a37a",
        "Variables": "#b8b2a8",
        "Passerelles": "#a58cf0",
    }
    assert _FAMILY_COLORS == expected


def test_every_step_type_has_the_documented_family():
    assert set(STEP_META) == set(EXPECTED_FAMILY_OF)
    for step_type, family in EXPECTED_FAMILY_OF.items():
        assert STEP_META[step_type]["family"] == family, step_type


def test_every_step_type_color_matches_its_family_color():
    for step_type, meta in STEP_META.items():
        assert meta["color"] == _FAMILY_COLORS[meta["family"]], step_type


def test_big_data_family_is_not_a_chooser_category():
    """La famille de couleur et la section du sélecteur sont deux choses distinctes (FONDATIONS.md,
    lot 0a) : Big Data n'a pas sa propre section, Spark SQL/Sqoop restent dans "Exécution &
    scripts" (_CATEGORY_ORDER inchangé)."""
    from ui.step_editor.step_type_chooser_dialog import _CATEGORY_ORDER
    assert "Big Data" not in _CATEGORY_ORDER
    for step_type in ("SPARK_SQL", "SQOOP_EXPORT", "SQOOP_IMPORT"):
        assert STEP_META[step_type]["category"] == "Exécution & scripts"
        assert STEP_META[step_type]["family"] == "Big Data"


def test_gateway_and_condition_share_the_passerelles_family():
    for step_type in ("CONDITION", "GATEWAY_PARALLEL", "GATEWAY_JOIN"):
        assert STEP_META[step_type]["family"] == "Passerelles"

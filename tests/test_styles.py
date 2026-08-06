"""
DataScheduler — tests/test_styles.py
Vérifie ui/styles.py (chantier design, audit visuel) : la couleur "warning" est bien distincte de
l'accent (elle en était une copie exacte avant correctif, rendant un avertissement indissociable
d'un bouton actif/survolé) et l'échelle typographique FONT_SIZES est bien déclarée.
"""

from ui.styles import COLORS, FONT_SIZES


def test_warning_color_is_distinct_from_accent():
    assert COLORS["warning"] != COLORS["accent"]


def test_warning_color_is_distinct_from_success_and_danger():
    assert COLORS["warning"] not in (COLORS["success"], COLORS["danger"])


def test_font_sizes_declares_all_expected_tiers():
    expected_keys = {"display", "title", "subtitle_dialog", "body", "label", "caption"}
    assert set(FONT_SIZES) == expected_keys


def test_font_sizes_are_in_descending_order():
    order = ["display", "title", "subtitle_dialog", "body", "label", "caption"]
    values = [FONT_SIZES[k] for k in order]
    assert values == sorted(values, reverse=True)

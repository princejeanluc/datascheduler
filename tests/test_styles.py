"""
DataScheduler — tests/test_styles.py
Vérifie ui/styles.py (chantier design, audit visuel) : la couleur "warning" est bien distincte de
l'accent (elle en était une copie exacte avant correctif, rendant un avertissement indissociable
d'un bouton actif/survolé), l'échelle typographique FONT_SIZES est bien déclarée, et le second
accent "signal" (chantier identité, 2026-08) ne se confond avec aucune couleur sémantique ou de
marque existante — sinon il perdrait sa raison d'être (désengorger l'orange, qui portait jusque-là
marque + action + statut "en cours" à la fois).
"""

from ui.styles import COLORS, FONT_SIZES, FONT_UI, FONT_MONO, FONT_UI_STACK, FONT_MONO_STACK, DIALOG_STYLE


def test_warning_color_is_distinct_from_accent():
    assert COLORS["warning"] != COLORS["accent"]


def test_warning_color_is_distinct_from_success_and_danger():
    assert COLORS["warning"] not in (COLORS["success"], COLORS["danger"])


def test_font_sizes_declares_all_expected_tiers():
    expected_keys = {
        "page_title", "display", "title", "panel_title", "subtitle_dialog", "row_label",
        "body", "label", "caption",
    }
    assert set(FONT_SIZES) == expected_keys


def test_font_sizes_are_in_descending_order():
    order = ["display", "title", "subtitle_dialog", "body", "label", "caption"]
    values = [FONT_SIZES[k] for k in order]
    assert values == sorted(values, reverse=True)


def test_signal_color_is_distinct_from_accent_and_semantic_colors():
    other_colors = (
        COLORS["accent"], COLORS["accent_dim"], COLORS["accent_pale"],
        COLORS["success"], COLORS["warning"], COLORS["danger"],
    )
    assert COLORS["signal"] not in other_colors


def test_font_constants_are_non_empty_strings():
    assert isinstance(FONT_UI, str) and FONT_UI
    assert isinstance(FONT_MONO, str) and FONT_MONO


def test_font_stacks_reference_the_custom_face_with_a_system_fallback():
    assert FONT_UI in FONT_UI_STACK and "Segoe UI" in FONT_UI_STACK
    assert FONT_MONO in FONT_MONO_STACK and "Consolas" in FONT_MONO_STACK


def test_dialog_style_uses_the_ui_font_stack_not_a_hardcoded_family():
    assert FONT_UI_STACK in DIALOG_STYLE


# ──────────────────────────────────────────────
#  Refonte, lot 0a — nouvelles clés COLORS relevées dans FONDATIONS.md (sections 1 et 6). Chaque
#  valeur est figée ici pour qu'une maquette future ne puisse pas glisser sans que ce test échoue.
# ──────────────────────────────────────────────

def test_lot_0a_colors_are_declared_with_their_documented_values():
    expected = {
        "border_strong": "#4a463f",
        "text_soft": "#c9c4bc",
        "success_dim": "#2f7d3c",
        "bg_info": "#16282f", "border_info": "#24414b",
        "bg_success": "#132116", "border_success": "#24502c",
        "bg_warning": "#241d10", "border_warning": "#5a4719",
        "bg_danger": "#2a1715", "border_danger": "#6e2b28",
        "bg_section": "#191714",
        "token_bg": "#2a1d10", "token_border": "#4a3520",
        "sql_string": "#7ec8a4",
        "editor_current_line": "#1f1c18",
        "relation": "#a58cf0",
    }
    assert len(expected) == 17
    for key, value in expected.items():
        assert COLORS[key] == value, key


def test_relation_color_matches_the_passerelles_step_family():
    """Même valeur que la famille d'étape Passerelles (lot 0a) — un lien vers un objet lié doit
    visuellement évoquer la même famille que CONDITION/GATEWAY_*."""
    from ui.step_editor.common import _FAMILY_COLORS
    assert COLORS["relation"] == _FAMILY_COLORS["Passerelles"]

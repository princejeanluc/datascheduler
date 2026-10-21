"""
DataScheduler — tests/test_sql_editor_widget.py
SqlEditorWidget (chantier atelier SQL) : gouttière de numéros de ligne, coloration syntaxique,
recherche/remplacement, formatage. Widget natif PySide6 (QPlainTextEdit + gouttière peinte à la
main) — QScintilla écarté (bindings Python réservés à PyQt5/PyQt6, aucun support PySide6).
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_text_round_trip(qapp):
    from ui.sql_editor import SqlEditorWidget

    w = SqlEditorWidget()
    w.set_text("SELECT 1 FROM dual")
    assert w.text() == "SELECT 1 FROM dual"


def test_set_text_accepts_none_without_raising(qapp):
    from ui.sql_editor import SqlEditorWidget

    w = SqlEditorWidget()
    w.set_text(None)
    assert w.text() == ""


def test_gutter_width_grows_with_line_count(qapp):
    from ui.sql_editor import SqlEditorWidget

    w = SqlEditorWidget()
    w.set_text("SELECT 1")
    narrow = w.editor.line_number_area_width()
    w.set_text("\n".join(f"line {i}" for i in range(200)))   # 3 chiffres au lieu de 1
    wide = w.editor.line_number_area_width()
    assert wide > narrow


def test_format_sql_reindents_by_clause(qapp):
    from ui.sql_editor import SqlEditorWidget

    w = SqlEditorWidget()
    w.set_text("select a, b from t where x = 1")
    w.format_sql()
    assert "SELECT" in w.text()
    assert "FROM" in w.text()
    assert "\n" in w.text()


def test_find_bar_hidden_by_default(qapp):
    from ui.sql_editor import SqlEditorWidget

    w = SqlEditorWidget()
    assert w._find_bar.isHidden()


def test_show_find_bar_opens_and_prefills_from_selection(qapp):
    from ui.sql_editor import SqlEditorWidget
    from PySide6.QtGui import QTextCursor

    w = SqlEditorWidget()
    w.set_text("SELECT nom FROM clients")
    cursor = w.editor.textCursor()
    cursor.setPosition(7); cursor.setPosition(10, QTextCursor.KeepAnchor)   # "nom"
    w.editor.setTextCursor(cursor)
    w.show_find_bar()
    assert not w._find_bar.isHidden()
    assert w._find_bar.inp_find.text() == "nom"


def test_find_counts_all_case_insensitive_matches(qapp):
    from ui.sql_editor import SqlEditorWidget

    w = SqlEditorWidget()
    w.set_text("x X x")   # 3 occurrences sans ambiguïté, casse mêlée
    w.show_find_bar()
    w._find_bar.inp_find.setText("x")
    assert len(w._find_bar._matches) == 3
    assert w._find_bar.lbl_count.text() == "1/3"


def test_find_next_wraps_around(qapp):
    from ui.sql_editor import SqlEditorWidget

    w = SqlEditorWidget()
    w.set_text("x x x")
    w.show_find_bar()
    w._find_bar.inp_find.setText("x")
    assert w._find_bar._current == 0
    w._find_bar.step(1); assert w._find_bar._current == 1
    w._find_bar.step(1); assert w._find_bar._current == 2
    w._find_bar.step(1); assert w._find_bar._current == 0   # boucle


def test_replace_one_replaces_only_current_match(qapp):
    from ui.sql_editor import SqlEditorWidget

    w = SqlEditorWidget()
    w.set_text("foo foo foo")
    w.show_find_bar()
    w._find_bar.inp_find.setText("foo")
    w._find_bar.inp_replace.setText("bar")
    w._find_bar._replace_one()
    assert w.text() == "bar foo foo"


def test_replace_all_replaces_every_occurrence_case_insensitively(qapp):
    from ui.sql_editor import SqlEditorWidget

    w = SqlEditorWidget()
    w.set_text("Foo foo FOO")
    w.show_find_bar()
    w._find_bar.inp_find.setText("foo")
    w._find_bar.inp_replace.setText("bar")
    w._find_bar._replace_all()
    assert w.text() == "bar bar bar"


def test_replace_all_with_empty_query_does_nothing(qapp):
    from ui.sql_editor import SqlEditorWidget

    w = SqlEditorWidget()
    w.set_text("SELECT 1")
    w.show_find_bar()
    w._find_bar.inp_find.setText("")
    w._find_bar._replace_all()
    assert w.text() == "SELECT 1"


def test_find_bar_nav_buttons_use_real_icons_not_text_glyphs(qapp):
    """Régression réelle (constatée à l'usage) : les boutons ↑/↓/✕ de la barre étaient construits
    avec un glyphe Unicode brut comme texte de bouton — resté vide sur la machine de l'utilisateur
    (dépend de la présence de ce caractère précis dans la police UI/ses polices de repli). Corrigé
    en passant à des icônes qtawesome (même patron que _action_btn ailleurs dans l'appli),
    garanties de se peindre quel que soit l'environnement de police."""
    from PySide6.QtWidgets import QPushButton
    from ui.sql_editor import SqlEditorWidget

    w = SqlEditorWidget()
    w.show_find_bar()
    nav_buttons = [b for b in w._find_bar.findChildren(QPushButton) if b.toolTip()]
    assert len(nav_buttons) == 3   # Précédent, Suivant, Fermer
    for btn in nav_buttons:
        assert not btn.icon().isNull(), f"bouton {btn.toolTip()!r} sans icône"


def test_find_bar_count_label_has_transparent_background(qapp):
    """Régression réelle (constatée à l'usage) : GLOBAL_STYLE peint tout QWidget non spécifié en
    bg_main (règle générique "QWidget { background-color: ... }") — sans "background: transparent"
    explicite, ce label peignait un rectangle opaque bg_main derrière "1/1", visiblement différent
    du fond réel de la barre (bg_card)."""
    from ui.sql_editor import SqlEditorWidget

    w = SqlEditorWidget()
    assert "transparent" in w._find_bar.lbl_count.styleSheet()


def test_no_hardcoded_hex_colors_in_sql_editor_module():
    """A6 (Requêtes SQL) : critère d'acceptation explicite de la fiche — aucune couleur en dur
    dans ui/sql_editor.py, tout passe par COLORS."""
    import re
    import ui.sql_editor as mod

    with open(mod.__file__, "r", encoding="utf-8") as f:
        source = f.read()
    assert not re.findall(r"#[0-9a-fA-F]{6}", source)


def _colors_at(widget, pos: int):
    """Renvoie (couleur de texte, couleur de fond) appliquées par le highlighter à la position
    `pos` (0-indexé, tout le texte tient sur un seul bloc dans ces tests) — extrait les couleurs
    immédiatement : le QTextCharFormat d'un QTextLayout.FormatRange ne survit pas à la portée de
    l'appel qui l'a produit (objet C++ libéré dès que le wrapper Python est collecté)."""
    block = widget.editor.document().findBlock(pos)
    offset = pos - block.position()
    fg = bg = None
    for rng in block.layout().formats():
        if rng.start <= offset < rng.start + rng.length:
            fg = rng.format.foreground().color().name().lower()
            bg = rng.format.background().color().name().lower()
    return fg, bg


def test_tokens_are_highlighted_with_accent_and_token_background(qapp):
    """A7 (Requêtes SQL) : un jeton {...} est surligné (texte accent_pale sur fond token_bg)."""
    from ui.sql_editor import SqlEditorWidget
    from ui.styles import COLORS

    w = SqlEditorWidget()
    w.set_text("SELECT {var:region}")
    pos = w.text().index("{")
    fg, bg = _colors_at(w, pos + 1)   # à l'intérieur du jeton
    assert fg == COLORS["accent_pale"].lower()
    assert bg == COLORS["token_bg"].lower()


def test_tokens_are_highlighted_even_inside_an_ordinary_string(qapp):
    """A7 : un jeton entre accolades à l'intérieur d'une chaîne SQL ordinaire suit la même règle
    (acceptance criterion explicite de la fiche) — le format de jeton doit gagner sur le format de
    chaîne pour ce fragment."""
    from ui.sql_editor import SqlEditorWidget
    from ui.styles import COLORS

    w = SqlEditorWidget()
    w.set_text("WHERE d = TO_DATE('{yyyy}-{MM}-{dd}', 'YYYY-MM-DD')")
    pos = w.text().index("{yyyy}") + 1
    fg, _bg = _colors_at(w, pos)
    assert fg == COLORS["accent_pale"].lower()


def test_close_bar_hides_and_clears_matches(qapp):
    from ui.sql_editor import SqlEditorWidget

    w = SqlEditorWidget()
    w.set_text("SELECT 1")
    w.show_find_bar()
    w._find_bar.inp_find.setText("SELECT")
    assert w._find_bar._matches
    w._find_bar.close_bar()
    assert w._find_bar.isHidden()
    assert w._find_bar._matches == []

"""
DataScheduler — tests/test_empty_state.py
Refonte, lot A-Ressources : extension de `_make_empty_label` (icon/title, FONDATIONS.md section
3 — "État vide" marqué « à étendre ») pour l'état vide de Ressources. Couvre la rétrocompatibilité
des appelants existants (aucun ne passe icon/title) et le rendu de la nouvelle variante.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QLabel, QPushButton, QFrame


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_plain_text_variant_unchanged_without_title(qapp):
    """Les 7 appelants existants (connections_view, dashboard_view, history_view,
    pipelines_view) ne passent ni icon ni title — doivent recevoir exactement le même QLabel nu
    qu'avant cette extension."""
    from ui.main_window.widgets import _make_empty_label

    widget = _make_empty_label("Aucun profil FTP — cliquez sur « Nouveau profil FTP ».")

    assert isinstance(widget, QLabel)
    assert widget.text() == "Aucun profil FTP — cliquez sur « Nouveau profil FTP »."


def test_button_variant_unchanged_without_title(qapp):
    from ui.main_window.widgets import _make_empty_label

    btn = QPushButton("Nouveau pipeline")
    widget = _make_empty_label("Aucun pipeline configuré.", button=btn)

    assert not isinstance(widget, QLabel)   # conteneur composite, comme avant
    assert btn.parent() is widget


def test_icon_title_variant_builds_a_left_aligned_card(qapp):
    from ui.main_window.widgets import _make_empty_label

    widget = _make_empty_label(
        "Kulu mesure son CPU et sa mémoire toutes les 60 secondes.",
        icon="fa5s.chart-line", title="Pas encore de mesure",
    )

    assert isinstance(widget, QFrame)
    labels_text = " ".join(lbl.text() for lbl in widget.findChildren(QLabel))
    assert "Pas encore de mesure" in labels_text
    assert "toutes les 60 secondes" in labels_text


def test_icon_title_variant_frame_style_is_id_scoped_not_a_bare_rule(qapp):
    """Régression : une première version posait le style du cadre (bordure + border-radius) via
    une règle QSS nue (setStyleSheet("border: ...") sans sélecteur), qui se propage à tout
    descendant qui ne fixe pas sa propre bordure — chaque QLabel enfant (icône, titre, texte) se
    retrouvait encadré (bug constaté à l'écran, reproduit isolément par pixel-sampling). Corrigé
    en scopant le cadre à un sélecteur d'ID, comme déjà pratiqué ailleurs dans l'appli pour le
    même type de bug (voir REGLES.md section 3)."""
    from ui.main_window.widgets import _make_empty_label

    widget = _make_empty_label("Texte.", icon="fa5s.chart-line", title="Titre")

    assert widget.objectName() == "empty_state"
    assert "QFrame#empty_state" in widget.styleSheet()

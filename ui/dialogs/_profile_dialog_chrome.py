"""
DataScheduler — ui/dialogs/_profile_dialog_chrome.py
Chrome partagé des 7 dialogues de profil de connexion (refonte, lot A-Connexions, A8/A9) :
en-tête (surtitre + icône de famille + titre), bandeau de résultat de test, pied de boutons.
Usage interne à ces dialogues (préfixe `_` du nom de fichier) — jamais importé ailleurs. Chaque
dialogue garde sa propre construction de champs, son thread de test et sa logique de sauvegarde,
inchangés : seul ce chrome visuel, identique sur les 7, est centralisé ici plutôt que dupliqué.
"""

from datetime import datetime

from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from ui.styles import COLORS, FONT_MONO
from ui.time_display import fmt_time

_FAMILY_LABELS = {
    "oracle": "BASES DE DONNÉES", "database": "BASES DE DONNÉES",
    "ftp": "FICHIERS", "smtp": "E-MAIL",
    "ssh": "BIG DATA", "kerberos": "BIG DATA", "elevation": "BIG DATA",
}

_VARIANT_ICON = {
    "success": "fa5s.check-circle", "danger": "fa5s.times-circle",
    "warning": "fa5s.exclamation-triangle", "info": "fa5s.info-circle",
}


def build_header(category: str, title: str, editing: bool) -> QWidget:
    """A8 : surtitre Mono (« MODIFIER · FICHIERS » / « NOUVEAU · FICHIERS ») + icône de famille
    (28px, même dictionnaire que les tableaux de ConnectionsView et le bilan de santé) + titre,
    séparateur. `category` : une clé de `ui.main_window.widgets._TYPE_ICON`."""
    # Import différé : ui.main_window (via ui.main_window.window) importe lui-même ui.dialogs —
    # un import en tête de fichier ici créerait une dépendance circulaire selon l'ordre d'import
    # (même précaution que ui/components/page_header.py et side_panel.py).
    from ui.main_window.widgets import _type_icon_badge

    container = QWidget()
    layout = QVBoxLayout(container)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(10)

    family = _FAMILY_LABELS.get(category, "")
    eyebrow = QLabel(f"{'MODIFIER' if editing else 'NOUVEAU'} · {family}")
    eyebrow.setStyleSheet(
        f"font-family: {FONT_MONO}; font-size: 10px; letter-spacing: 0.06em; "
        f"color: {COLORS['text_dim']};"
    )
    layout.addWidget(eyebrow)

    title_row = QHBoxLayout()
    title_row.setSpacing(10)
    title_row.addWidget(_type_icon_badge(category, size=28))
    title_lbl = QLabel(title)
    title_lbl.setStyleSheet(f"font-size: 17px; font-weight: 600; color: {COLORS['text_main']};")
    title_row.addWidget(title_lbl)
    title_row.addStretch()
    layout.addLayout(title_row)

    sep = QFrame(); sep.setFrameShape(QFrame.HLine)
    sep.setStyleSheet(f"background: {COLORS['border']}; max-height: 1px; border: none;")
    layout.addWidget(sep)

    return container


def make_test_banner_container() -> tuple:
    """A9 : conteneur vide + une fonction `set_banner(variant, title_text, message_text="")` qui
    reconstruit et remplace le bandeau à chaque appel — même patron « reconstruire et remplacer »
    que `HistoryView._refresh_audit_log`, jamais un widget mis à jour en place. `variant` une des
    4 clés de `ui.components.banner.make_banner` (info/success/warning/danger). `message_text`,
    s'il y en a un, est affiché en `FONT_MONO` (A9 : « le message brut en Mono »). Passer
    `variant=None` vide le conteneur (aucun bandeau — l'état initial, avant tout test)."""
    from ui.components import make_banner

    container = QWidget()
    layout = QVBoxLayout(container)
    layout.setContentsMargins(0, 0, 0, 0)
    state = {"current": None}

    def set_banner(variant, title_text: str = "", message_text: str = "") -> None:
        if state["current"] is not None:
            layout.removeWidget(state["current"])
            # setParent(None) avant deleteLater() : la détache immédiatement de l'arbre QObject
            # (deleteLater() seul ne la détruit qu'au prochain passage de la boucle d'événements —
            # un appelant qui inspecterait le conteneur entre-temps, via findChildren(), verrait
            # encore l'ancien bandeau).
            state["current"].setParent(None)
            state["current"].deleteLater()
            state["current"] = None
        if variant is None:
            return
        banner = make_banner(variant, _VARIANT_ICON.get(variant, "fa5s.info-circle"),
                              title_text, message_text)
        if message_text:
            for lbl in banner.findChildren(QLabel):
                if lbl.text() == message_text:
                    lbl.setStyleSheet(lbl.styleSheet() + f" font-family: {FONT_MONO};")
        layout.addWidget(banner)
        state["current"] = banner

    return container, set_banner


def test_result_title(success: bool) -> str:
    """A9 : titre du bandeau avec l'heure du test (« Le test a échoué à 15:42 » / « Connexion
    réussie à 15:42 »), absente avant ce lot."""
    now_s = fmt_time(datetime.utcnow())
    return f"Connexion réussie à {now_s}" if success else f"Le test a échoué à {now_s}"


def build_footer(test_label: str, on_test, on_cancel, on_save) -> tuple:
    """A9 : note + 3 boutons (Tester/Annuler/Enregistrer), mêmes `objectName`/connexions
    qu'aujourd'hui (seul le bouton Tester change de place, désormais ici plutôt que dans une
    carte à part au-dessus). Retourne (layout, btn_test, btn_cancel, btn_save) — chaque dialogue
    garde une référence à `btn_test` pour le désactiver pendant un test en cours, comme avant."""
    row = QHBoxLayout()
    row.setSpacing(10)

    note = QLabel("Le test utilise les valeurs saisies, pas celles enregistrées.")
    note.setStyleSheet(f"font-size: 12px; color: {COLORS['text_dim']};")
    row.addWidget(note, stretch=1)

    btn_test = QPushButton(test_label)
    btn_test.setObjectName("secondary")
    btn_test.setFixedHeight(36)
    btn_test.clicked.connect(on_test)
    row.addWidget(btn_test)

    btn_cancel = QPushButton("Annuler")
    btn_cancel.setObjectName("secondary")
    btn_cancel.setFixedHeight(36)
    btn_cancel.clicked.connect(on_cancel)
    row.addWidget(btn_cancel)

    btn_save = QPushButton("Enregistrer")
    btn_save.setFixedHeight(36)
    btn_save.clicked.connect(on_save)
    row.addWidget(btn_save)

    return row, btn_test, btn_cancel, btn_save

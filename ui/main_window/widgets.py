"""
DataScheduler — ui/main_window/widgets.py
Helpers, constantes et petits composants partagés par toutes les vues.
"""

import qtawesome as qta
from PySide6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame, QSizePolicy, QLineEdit,
    QTableWidget, QHeaderView, QGraphicsOpacityEffect, QWidget, QToolTip,
)
from PySide6.QtCore import Qt, QSize, Signal, QPropertyAnimation, QEasingCurve, QRectF, QPointF, QEvent
from PySide6.QtGui import QIcon, QPainter, QFont, QPen, QColor, QBrush, QPainterPath
from ui.styles import COLORS, FONT_MONO, FONT_UI, FONT_MONO_STACK, FONT_UI_STACK, FONT_SIZES


# ──────────────────────────────────────────────
#  HELPERS ICÔNES
# ──────────────────────────────────────────────

def _icon(name: str, color: str) -> QIcon:
    return qta.icon(name, color=color)

def _action_btn(icon_name: str, object_name: str = "", tooltip: str = "",
                size: tuple = (28, 26), icon_color: str = None) -> QPushButton:
    """Crée un bouton carré icône-seul pour les tableaux d'actions."""
    btn = QPushButton()
    if object_name:
        btn.setObjectName(object_name)
    if tooltip:
        btn.setToolTip(tooltip)
    btn.setFixedSize(*size)
    # "accent_action" (lot A-Pipelines, A7) : action mise en avant sur une ligne active
    # (reprendre/exécuter maintenant) — fond bg_active/bordure border_active posés par GLOBAL_STYLE,
    # seule l'icône se choisit ici, même principe que "danger" déjà existant.
    if icon_color:
        color = icon_color
    elif object_name == "danger":
        color = COLORS["danger"]
    elif object_name == "accent_action":
        color = COLORS["accent_pale"]
    else:
        color = COLORS["text_main"]
    btn.setIcon(_icon(icon_name, color))
    btn.setIconSize(QSize(14, 14))
    return btn


def _make_button_with_hint(text: str, hint: str, icon: str = "", primary: bool = True,
                            on_click=None) -> QFrame:
    """Bouton avec raccourci clavier affiché à sa droite en Mono atténué (FONDATIONS.md section 3,
    « Bouton avec raccourci affiché ») — ex. « + Nouveau pipeline   Ctrl N » de Pipelines.html.
    QPushButton ne peut pas mélanger deux styles de texte dans un seul widget (pas de rich text) :
    même patron qu'une puce de rail (QFrame stylé en bouton, clic câblé sur mouseReleaseEvent)
    plutôt qu'un vrai QPushButton, pour obtenir les deux styles de texte sans widget composite
    plus lourd (QToolButton personnalisé, QWidgetAction…). `clicked` n'est pas un signal Qt ici :
    l'appelant passe directement son callback via `on_click` (voir usage)."""
    btn = QFrame()
    btn.setCursor(Qt.PointingHandCursor)
    btn.setFixedHeight(36)
    if primary:
        bg, bg_hover, fg, border = COLORS["accent"], COLORS["accent_pale"], "#000000", "none"
    else:
        bg, bg_hover, fg, border = "transparent", COLORS["bg_hover"], COLORS["text_main"], f"1px solid {COLORS['border']}"
    btn.setObjectName("button_with_hint")
    btn.setStyleSheet(
        f"QFrame#button_with_hint {{ background: {bg}; border-radius: 6px; border: {border}; }}"
        f"QFrame#button_with_hint:hover {{ background: {bg_hover}; }}"
    )
    layout = QHBoxLayout(btn)
    layout.setContentsMargins(16, 0, 14, 0)
    layout.setSpacing(8)
    if icon:
        icon_lbl = QLabel()
        icon_lbl.setPixmap(_icon(icon, fg).pixmap(QSize(13, 13)))
        icon_lbl.setStyleSheet("background: transparent; border: none;")
        layout.addWidget(icon_lbl)
    text_lbl = QLabel(text)
    text_lbl.setStyleSheet(f"color: {fg}; font-weight: 700; font-size: 13px; background: transparent; border: none;")
    layout.addWidget(text_lbl)
    hint_lbl = QLabel(hint)
    hint_lbl.setStyleSheet(
        f"color: {fg}; font-family: {FONT_MONO_STACK}; font-size: 10.5px; font-weight: 500; "
        f"background: transparent; border: none;"
    )
    op_effect = QGraphicsOpacityEffect(hint_lbl)
    op_effect.setOpacity(0.7)
    hint_lbl.setGraphicsEffect(op_effect)
    layout.addWidget(hint_lbl)
    if on_click is not None:
        btn.mouseReleaseEvent = lambda event, cb=on_click: cb()
    return btn


def _configure_columns(table: QTableWidget, stretch_cols: set) -> None:
    """
    N'étire que les colonnes indiquées (celles qui ont besoin de place :
    noms, chemins…) ; les autres s'ajustent à leur contenu (port, statut,
    protocole…). Évite qu'une colonne de 4 chiffres reçoive la même largeur
    qu'un nom de pipeline.
    """
    header = table.horizontalHeader()
    for i in range(table.columnCount()):
        header.setSectionResizeMode(
            i, QHeaderView.Stretch if i in stretch_cols else QHeaderView.ResizeToContents
        )


def _filter_table_rows(table: QTableWidget, needle: str, columns: list) -> None:
    """Cache les lignes qui ne contiennent pas `needle` (insensible à la casse)
    dans les colonnes indiquées — fonctionne pour les cellules texte (QTableWidgetItem)
    et les badges (QLabel en cellWidget)."""
    needle = needle.strip().lower()
    for row in range(table.rowCount()):
        if not needle:
            table.setRowHidden(row, False)
            continue
        haystack = []
        for col in columns:
            item = table.item(row, col)
            if item:
                haystack.append(item.text().lower())
            else:
                w = table.cellWidget(row, col)
                if isinstance(w, QLabel):
                    haystack.append(w.text().lower())
        table.setRowHidden(row, needle not in " ".join(haystack))


def _make_search_input(placeholder: str) -> QLineEdit:
    inp = QLineEdit()
    inp.setPlaceholderText(placeholder)
    inp.setFixedHeight(34)
    inp.setFixedWidth(240)
    inp.setClearButtonEnabled(True)
    icon = _icon("fa5s.search", COLORS["text_dim"])
    if icon:
        inp.addAction(icon, QLineEdit.LeadingPosition)
    return inp


def _make_empty_label(text: str, button: QPushButton | None = None,
                       icon: str = "", title: str = "") -> QWidget:
    """Message d'état vide, cohérent avec celui de l'éditeur de pipeline. `button` (chantier UX
    éditeur, Lot 1 — ex: "Commencer avec un modèle" sur l'état vide de PipelinesView) est
    optionnel et rétrocompatible : par défaut (None), retourne le QLabel nu exactement comme
    avant — tous les appelants existants n'utilisent que des méthodes QWidget génériques
    (setVisible/setFixedHeight), jamais rien de spécifique à QLabel, donc le conteneur composite
    retourné quand un bouton est fourni reste un remplacement transparent.

    `icon`/`title` (refonte, lot A-Ressources — A9) : variante FONDATIONS.md "icône, titre,
    texte, action", pour un état vide plus riche qu'un seul message centré en italique
    (Ressources-vide.html : icône 44px, titre 17px/600, texte normal, tout aligné à gauche dans
    un bloc centré — pas le texte centré/italique des autres appelants). `title` seul déclenche
    cette variante ; sans lui, rendu strictement identique à avant (7 appelants existants
    vérifiés par grep : aucun ne passe ces 2 paramètres)."""
    if title:
        return _make_empty_state(icon, title, text, button)

    lbl = QLabel(text)
    lbl.setAlignment(Qt.AlignCenter)
    lbl.setWordWrap(True)
    lbl.setStyleSheet(
        f"color: {COLORS['text_muted']}; font-size: 12px; font-style: italic; "
        f"background: transparent; border: none;" if button is not None else
        f"color: {COLORS['text_muted']}; font-size: 12px; font-style: italic; "
        f"background: {COLORS['bg_panel']}; border: 1px solid {COLORS['border']}; "
        f"border-radius: 6px; padding: 28px 12px;"
    )
    if button is None:
        return lbl

    container = QWidget()
    container.setStyleSheet(
        f"background: {COLORS['bg_panel']}; border: 1px solid {COLORS['border']}; "
        f"border-radius: 6px;"
    )
    vl = QVBoxLayout(container)
    vl.setContentsMargins(12, 28, 12, 28)
    vl.setSpacing(14)
    vl.addWidget(lbl)
    vl.addWidget(button, alignment=Qt.AlignCenter)
    return container


def _make_empty_state(icon: str, title: str, text: str, button: QPushButton | None) -> QWidget:
    """Bloc icône/titre/texte aligné à gauche, lui-même centré dans la carte — structure propre à
    Ressources-vide.html, distincte du message centré/italique des autres états vides."""
    frame = QFrame()
    frame.setObjectName("empty_state")
    # Sélecteur d'ID, pas une règle nue : une règle nue ("background: ...; border: ...") posée
    # via setStyleSheet() sur un conteneur se propage à ses descendants pour les propriétés
    # qu'ils ne fixent pas eux-mêmes — ici le "border-radius: 10px" du cadre se retrouvait peint
    # autour de chaque QLabel enfant (icône, titre, texte), même avec leur propre
    # "background: transparent" (bug déjà rencontré et documenté, REGLES.md section 3).
    frame.setStyleSheet(
        f"QFrame#empty_state {{ background: {COLORS['bg_panel']}; "
        f"border: 1px solid {COLORS['border']}; border-radius: 10px; }}"
    )
    outer = QHBoxLayout(frame)
    outer.addStretch()

    column = QVBoxLayout(); column.setSpacing(10)
    column.addStretch()

    if icon:
        icon_lbl = QLabel()
        icon_lbl.setPixmap(_icon(icon, COLORS["text_muted"]).pixmap(QSize(40, 40)))
        icon_lbl.setStyleSheet("background: transparent;")
        column.addWidget(icon_lbl)

    title_lbl = QLabel(title)
    title_lbl.setStyleSheet(
        f"color: {COLORS['text_main']}; font-size: 17px; font-weight: 600; "
        f"background: transparent;")
    column.addWidget(title_lbl)

    text_lbl = QLabel(text)
    text_lbl.setWordWrap(True)
    text_lbl.setFixedWidth(480)
    text_lbl.setStyleSheet(f"color: {COLORS['text_dim']}; font-size: 13px; background: transparent;")
    column.addWidget(text_lbl)

    if button is not None:
        column.addWidget(button, alignment=Qt.AlignLeft)

    column.addStretch()
    outer.addLayout(column)
    outer.addStretch()
    return frame

# ──────────────────────────────────────────────
#  CONSTANTES
# ──────────────────────────────────────────────

NAV_WIDTH            = 220
NAV_WIDTH_COLLAPSED  = 56   # icône seule + tooltip (chantier ergonomie, repli du menu)
HEADER_H             = 52
# FONT_MONO / FONT_UI définies dans ui/styles.py (ré-exportées ici pour compat avec les imports
# existants `from .widgets import ..., FONT_MONO`) — voir ui/fonts.py pour l'enregistrement.


# ──────────────────────────────────────────────
#  STYLES CSS GLOBAUX
# ──────────────────────────────────────────────

GLOBAL_STYLE = f"""
QWidget {{
    background-color: {COLORS['bg_main']};
    color: {COLORS['text_main']};
    font-family: {FONT_UI_STACK};
    font-size: 13px;
}}

/* ── Infobulles ──
   Sans règle explicite, QToolTip peut être peint par le chrome natif de l'OS sur certaines
   machines (thème sombre/clair Windows, mise à l'échelle...) au lieu de suivre la palette de
   l'appli — texte et fond peuvent alors provenir de deux sources différentes et finir par se
   confondre (encadré visible mais texte invisible, signalé par un utilisateur sur certains
   postes bureau, jamais reproduit sur d'autres machines). Une règle QSS explicite fait peindre
   l'infobulle entièrement par Qt, de façon identique sur toutes les machines. */
QToolTip {{
    background-color: {COLORS['bg_card']};
    color: {COLORS['text_main']};
    border: 1px solid {COLORS['border']};
    border-radius: 4px;
    padding: 4px 8px;
}}

/* ── Menus contextuels ──
   Sans règle explicite, QMenu hérite uniquement du fond/texte de la règle QWidget générale
   ci-dessus (aucun arrondi, aucune bordure, aucun retour visuel au survol/désactivé) — tout
   QMenu de l'app (menu "⋯" de PipelinesView, bouton "+ Artefact", menu contextuel de l'éditeur
   graphique) en a toujours souffert en silence ; corrigé une seule fois ici plutôt que par
   endroit. */
QMenu {{
    background-color: {COLORS['bg_panel']};
    border: 1px solid {COLORS['border']};
    border-radius: 8px;
    padding: 4px;
}}
QMenu::item {{
    padding: 7px 14px;
    border-radius: 5px;
    color: {COLORS['text_main']};
}}
QMenu::item:selected {{
    background-color: {COLORS['bg_hover']};
}}
QMenu::item:disabled {{
    color: {COLORS['text_muted']};
}}
QMenu::separator {{
    height: 1px;
    background: {COLORS['border']};
    margin: 4px 6px;
}}

/* ── Scrollbar ── */
QScrollBar:vertical {{
    background: {COLORS['bg_panel']};
    width: 6px;
    border-radius: 3px;
}}
QScrollBar::handle:vertical {{
    background: {COLORS['border']};
    border-radius: 3px;
    min-height: 24px;
}}
QScrollBar::handle:vertical:hover {{
    background: {COLORS['accent']};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}

/* ── Tableau ── */
QTableWidget {{
    background-color: {COLORS['bg_panel']};
    border: 1px solid {COLORS['border']};
    border-radius: 6px;
    gridline-color: {COLORS['border']};
    selection-background-color: {COLORS['bg_active']};
}}
QTableWidget::item {{
    padding: 8px 12px;
    border: none;
    outline: none;
}}
QTableWidget::item:selected {{
    background-color: {COLORS['bg_active']};
    color: {COLORS['text_main']};
    border-left: 2px solid {COLORS['accent']};
}}
QTableWidget::item:focus {{
    border: none;
    outline: none;
}}
QHeaderView::section {{
    background-color: {COLORS['bg_card']};
    color: {COLORS['text_dim']};
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 1px;
    text-transform: uppercase;
    padding: 8px 12px;
    border: none;
    border-bottom: 2px solid {COLORS['accent']};
}}

/* ── Boutons ── */
QPushButton {{
    background-color: {COLORS['accent']};
    color: #000000;
    border: none;
    border-radius: 4px;
    padding: 8px 18px;
    font-weight: 700;
    font-size: 13px;
}}
QPushButton:hover {{
    background-color: {COLORS['accent_pale']};
}}
QPushButton:pressed {{
    background-color: {COLORS['accent_dim']};
    color: white;
}}
QPushButton#secondary {{
    background-color: transparent;
    color: {COLORS['text_main']};
    border: 1px solid {COLORS['border']};
}}
QPushButton#secondary:hover {{
    background-color: {COLORS['bg_hover']};
    border-color: {COLORS['accent']};
    color: {COLORS['accent']};
}}
QPushButton#danger {{
    background-color: transparent;
    color: {COLORS['danger']};
    border: 1px solid {COLORS['danger']};
}}
QPushButton#danger:hover {{
    background-color: {COLORS['danger']};
    color: white;
}}
/* "accent_action" (lot A-Pipelines, A7) : action mise en avant sur une ligne active (reprendre/
   exécuter maintenant) — distinct du bouton principal plein accent, plus proche d'un badge. */
QPushButton#accent_action {{
    background-color: {COLORS['bg_active']};
    border: 1px solid {COLORS['border_active']};
}}
QPushButton#accent_action:hover {{
    background-color: {COLORS['border_active']};
}}

/* ── Formulaires ── */
QLineEdit, QTextEdit, QComboBox, QSpinBox {{
    background-color: {COLORS['bg_card']};
    border: 1px solid {COLORS['border']};
    border-radius: 4px;
    padding: 7px 10px;
    color: {COLORS['text_main']};
    font-size: 13px;
}}
QLineEdit:focus, QTextEdit:focus, QComboBox:focus, QSpinBox:focus {{
    border-color: {COLORS['accent']};
    border-width: 2px;
}}
QComboBox::drop-down {{
    border: none;
    padding-right: 8px;
}}
QComboBox QAbstractItemView {{
    background-color: {COLORS['bg_card']};
    border: 1px solid {COLORS['border']};
    selection-background-color: {COLORS['bg_active']};
    color: {COLORS['text_main']};
}}

/* ── Étiquettes ── */
QLabel#section_title {{
    font-size: 20px;
    font-weight: 700;
    color: {COLORS['text_main']};
}}
QLabel#subtitle {{
    font-size: 13px;
    color: {COLORS['text_dim']};
}}

/* ── En-tête de page (refonte, lot 0a — FONDATIONS.md section 2/3) ── */
QLabel#page_eyebrow {{
    font-family: {FONT_MONO_STACK};
    font-size: 11px;
    letter-spacing: 0.08em;
    color: {COLORS['text_dim']};
}}
QLabel#page_title {{
    font-size: {FONT_SIZES['page_title']}px;
    font-weight: 600;
    color: {COLORS['text_main']};
}}

/* ── Badges statut ── */
QLabel#badge_success {{
    background-color: rgba(63,185,80,0.12);
    color: {COLORS['success']};
    border-radius: 3px;
    padding: 2px 10px;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.5px;
}}
QLabel#badge_failed {{
    background-color: rgba(248,81,73,0.12);
    color: {COLORS['danger']};
    border-radius: 3px;
    padding: 2px 10px;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.5px;
}}
QLabel#badge_running {{
    background-color: rgba(62,143,176,0.15);
    color: {COLORS['signal']};
    border-radius: 3px;
    padding: 2px 10px;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.5px;
}}
QLabel#badge_idle {{
    background-color: rgba(153,153,153,0.10);
    color: {COLORS['text_dim']};
    border-radius: 3px;
    padding: 2px 10px;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.5px;
}}

/* ── Cartes et séparateurs ── */
QFrame#card {{
    background-color: {COLORS['bg_card']};
    border: 1px solid {COLORS['border']};
    border-radius: 6px;
}}
QFrame#separator {{
    background-color: {COLORS['border']};
    max-height: 1px;
}}
"""

# ──────────────────────────────────────────────
#  COMPOSANT : BOUTON DE NAVIGATION
# ──────────────────────────────────────────────

class NavButton(QPushButton):
    """Bouton de la barre de navigation latérale."""

    def __init__(self, label: str, icon_name: str = ""):
        super().__init__()
        self._label     = label
        self._icon_name = icon_name
        self._active    = False
        self._collapsed = False
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(44)
        self.setIconSize(QSize(16, 16))
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._apply_style()

    def set_active(self, active: bool):
        self._active = active
        self._apply_style()

    def set_collapsed(self, collapsed: bool):
        """Rail replié (chantier ergonomie) — icône seule, libellé reporté en infobulle plutôt
        que perdu : sans lui, un rail icône-seule mal fait devient un jeu de mémoire."""
        self._collapsed = collapsed
        self._apply_style()

    def _apply_style(self):
        bg     = COLORS["bg_active"] if self._active else "transparent"
        color  = COLORS["text_main"] if self._active else COLORS["text_dim"]
        border = f"border-left: 3px solid {COLORS['accent']};" if self._active else "border-left: 3px solid transparent;"
        padding = "0px" if self._collapsed else "0px 16px 0px 12px"
        align   = "center" if self._collapsed else "left"
        self.setStyleSheet(f"""
            QPushButton {{
                background-color: {bg};
                color: {color};
                {border}
                border-radius: 0px;
                padding: {padding};
                text-align: {align};
                font-size: 13px;
                font-weight: {"600" if self._active else "400"};
            }}
            QPushButton:hover {{
                background-color: {COLORS['bg_hover']};
                color: {COLORS['text_main']};
            }}
        """)
        self.setText("" if self._collapsed else f"  {self._label}")
        self.setToolTip(self._label if self._collapsed else "")
        if self._icon_name:
            from ui.icons import nav_icon
            self.setIcon(nav_icon(self._icon_name, color))


# ──────────────────────────────────────────────
#  COMPOSANT : RAIL DE NAVIGATION (chantier ergonomie, repli du menu)
# ──────────────────────────────────────────────

class NavRail(QWidget):
    """
    Colonne de navigation latérale — extraite de MainWindow._build_nav() en composant autonome
    (chantier repli du menu) précisément pour rester testable seule : MainWindow instancie ses 8
    vues (Dashboard, Pipelines, Connexions, Requêtes SQL, Historique, Ressources, Paramètres,
    Aide) dans son constructeur, avec effets de bord réels (pont vers le scheduler, dialogue de
    rattrapage des pipelines manqués) — en construire plusieurs dans une même suite de tests a
    fait planter/bloquer la suite complète à deux reprises (voir CHANGELOG, chantier repli du
    menu), alors que NavRail seule, sans rien de tout ça, se construit et se teste en isolation
    sans aucun risque.

    N'importe rien de la logique de persistance (AppSettings) : `navigate_requested`/
    `collapsed_changed` laissent l'appelant (MainWindow) décider quoi en faire — ce composant ne
    connaît que sa propre présentation.
    """

    navigate_requested  = Signal(int)
    collapsed_changed   = Signal(bool)

    def __init__(self, nav_items: list[tuple[str, str, int]], initial_collapsed: bool = False):
        super().__init__()
        self._collapsed = initial_collapsed
        self._nav_buttons: list[NavButton] = []
        self.setStyleSheet(f"background-color: {COLORS['bg_panel']};")
        self._build_ui(nav_items)
        self._apply_collapsed_state()

    def _build_ui(self, nav_items):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Logo / titre
        self._logo_widget = QWidget()
        self._logo_widget.setFixedHeight(HEADER_H)
        self._logo_widget.setStyleSheet(f"background: {COLORS['bg_panel']}; border-bottom: 1px solid {COLORS['border']};")
        self._logo_layout = QHBoxLayout(self._logo_widget)
        self._logo_layout.setSpacing(10)
        from ui.icons import logo_icon as _logo_icon
        logo_icon = QLabel()
        logo_icon.setFixedSize(22, 22)
        logo_icon.setPixmap(_logo_icon(COLORS["accent"], size=22).pixmap(22, 22))
        logo_icon.setStyleSheet("background: transparent; border: none;")
        self._logo_lbl = QLabel("KULU")
        self._logo_lbl.setStyleSheet(
            f"color: {COLORS['accent']}; font-size: 14px; font-weight: 700; "
            f"background: transparent; border: none; letter-spacing: 0.5px;"
        )
        self._logo_layout.addWidget(logo_icon)
        self._logo_layout.addWidget(self._logo_lbl)
        layout.addWidget(self._logo_widget)

        # Boutons de navigation
        for label, icon, idx in nav_items:
            btn = NavButton(label, icon)
            btn.clicked.connect(lambda checked, i=idx: self.navigate_requested.emit(i))
            self._nav_buttons.append(btn)
            layout.addWidget(btn)

        layout.addStretch()

        # Repli/dépli — bascule explicite (jamais au survol, qui ajouterait un mouvement non
        # sollicité sur un outil où l'on reste concentré longtemps sur une vue). QPushButton nu
        # plutôt que NavButton : son icône (chevron réversible) vient de qtawesome (_icon()), pas
        # du jeu d'icônes SVG maison fermé de NavButton (ui/icons.py::nav_icon(), une clé par
        # item de nav).
        self._toggle_btn = QPushButton()
        self._toggle_btn.setCursor(Qt.PointingHandCursor)
        self._toggle_btn.setFixedHeight(36)
        self._toggle_btn.setIconSize(QSize(13, 13))
        self._toggle_btn.clicked.connect(self.toggle_collapsed)
        layout.addWidget(self._toggle_btn)

        # Version en bas
        from version import __version__
        self._version_lbl = QLabel(f"v{__version__}")
        self._version_lbl.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 11px; padding: 12px 18px; background: transparent;")
        layout.addWidget(self._version_lbl)

    # ── API publique ───────────────────────────

    def set_active_index(self, index: int):
        for i, btn in enumerate(self._nav_buttons):
            btn.set_active(i == index)

    def toggle_collapsed(self):
        self.set_collapsed(not self._collapsed)

    def set_collapsed(self, collapsed: bool):
        self._collapsed = collapsed
        self._apply_collapsed_state()
        self.collapsed_changed.emit(collapsed)

    @property
    def is_collapsed(self) -> bool:
        return self._collapsed

    # ── Présentation ───────────────────────────

    def _apply_collapsed_state(self):
        self.setFixedWidth(NAV_WIDTH_COLLAPSED if self._collapsed else NAV_WIDTH)
        for btn in self._nav_buttons:
            btn.set_collapsed(self._collapsed)

        self._logo_lbl.setVisible(not self._collapsed)
        margin = 8 if self._collapsed else 18
        self._logo_layout.setContentsMargins(margin, 0, margin, 0)

        self._version_lbl.setVisible(not self._collapsed)

        chevron = "fa5s.chevron-right" if self._collapsed else "fa5s.chevron-left"
        self._toggle_btn.setIcon(_icon(chevron, COLORS["text_dim"]))
        self._toggle_btn.setText("" if self._collapsed else "  Réduire le menu")
        self._toggle_btn.setToolTip("Agrandir le menu" if self._collapsed else "")
        padding = "0px" if self._collapsed else "0px 16px 0px 12px"
        self._toggle_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {COLORS['text_dim']};
                border: none;
                border-radius: 0px;
                padding: {padding};
                text-align: left;
                font-size: 12px;
            }}
            QPushButton:hover {{
                background-color: {COLORS['bg_hover']};
                color: {COLORS['text_main']};
            }}
        """)


# ──────────────────────────────────────────────
#  COMPOSANT : CARTE STAT (Dashboard)
# ──────────────────────────────────────────────

class StatCard(QFrame):
    clicked = Signal()

    def __init__(self, title: str, value: str = "—", subtitle: str = "",
                 color: str = None, clickable: bool = False, border_accent: str = None,
                 height: int = 100, value_font_size: int = 28, padding_h: int = 20):
        super().__init__()
        self.setObjectName("card")
        # setMinimumHeight, pas setFixedHeight : une hauteur figée plus petite que le contenu
        # réel (marges + 3 lignes de texte) le rogne silencieusement — repéré sur une capture
        # réelle des cartes compactes. Un minimum laisse Qt grandir si le contenu l'exige, sans
        # jamais rogner, tout en gardant les cartes visuellement compactes en pratique.
        self.setMinimumHeight(height)
        self._clickable = clickable
        if clickable:
            self.setCursor(Qt.PointingHandCursor)
        # Liseré de couleur (chantier identité visuelle, phase 2) — n'ajoute que border-left,
        # le reste de l'apparence de la carte reste géré par QFrame#card dans GLOBAL_STYLE.
        self.setStyleSheet(
            f"QFrame#card {{ border-left: 3px solid {border_accent or COLORS['signal']}; }}"
        )

        # Marges/tailles fixes, indépendantes de `height` — une tentative précédente de les
        # resserrer "en mode compact" en dessous de 100px avait fini par rogner le sous-titre
        # (mauvaise estimation des métriques réelles de police). `height` ne fait plus que fixer
        # un plancher (setMinimumHeight) ; le contenu garde toujours la même respiration.
        layout = QVBoxLayout(self)
        layout.setContentsMargins(padding_h, 14, padding_h, 14)
        layout.setSpacing(4)

        lbl_title = QLabel(title.upper())
        lbl_title.setStyleSheet(f"color: {COLORS['text_dim']}; font-size: 10px; font-weight: 700; letter-spacing: 1px; background: transparent; border: none;")
        # setWordWrap : un titre plus long que la carte n'est ni rogné ni débordant, il passe sur
        # 2 lignes — la carte peut déjà grandir pour s'adapter à son contenu (setMinimumHeight,
        # pas setFixedHeight, voir plus haut) ; sans wrap, Qt rognait silencieusement le texte au
        # lieu de laisser la carte grandir (constaté sur les 4 cartes compactes d'Aujourd'hui,
        # padding_h réduit). Sans effet sur les cartes plus larges, où le titre tient déjà sur
        # une ligne.
        lbl_title.setWordWrap(True)

        self._lbl_value = QLabel(value)
        c = color or COLORS["text_main"]
        self._lbl_value.setStyleSheet(
            f"color: {c}; font-size: {value_font_size}px; font-weight: 700; "
            f"background: transparent; border: none;")

        self._lbl_sub = QLabel(subtitle)
        self._lbl_sub.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 11px; background: transparent; border: none;")

        layout.addWidget(lbl_title)
        layout.addWidget(self._lbl_value)
        layout.addWidget(self._lbl_sub)

    def set_value(self, value: str):
        self._lbl_value.setText(value)

    def set_subtitle(self, text: str):
        self._lbl_sub.setText(text)

    def mousePressEvent(self, event):
        if self._clickable:
            self.clicked.emit()
        super().mousePressEvent(event)


# ──────────────────────────────────────────────
#  COMPOSANT : ANNEAU DE SANTÉ (Dashboard, chantier identité, vague 2, idée 4)
# ──────────────────────────────────────────────

def _ring_arcs(success: int, danger: int) -> list:
    """Géométrie pure de l'anneau segmenté — factorisée hors de paintEvent() pour rester
    testable sans Qt, même philosophie que ActivityChartWidget._bar_rect(). Angles en degrés,
    départ à midi (90°), sens horaire (valeurs négatives — convention QPainter.drawArc)."""
    total = success + danger
    if total == 0:
        return []
    success_span = 360.0 * success / total
    danger_span = 360.0 * danger / total
    arcs = []
    if success:
        arcs.append(("success", 90.0, -success_span))
    if danger:
        arcs.append(("danger", 90.0 - success_span, -danger_span))
    return arcs


class HealthRingWidget(QWidget):
    """Anneau de santé segmenté (succès/échec) — casse la grille de cartes stat identiques, LE
    tell le plus reconnaissable d'un dashboard générique. Ne compte que les pipelines actifs
    ayant déjà un dernier statut connu (SUCCESS/FAILED) : un pipeline jamais exécuté n'est ni
    sain ni en échec, l'inclure dans un dénominateur forcé aurait été trompeur — le nombre total
    de pipelines actifs reste visible séparément (carte "Pipelines actifs")."""

    SIZE = 108
    PEN_WIDTH = 10

    def __init__(self):
        super().__init__()
        self._success = 0
        self._danger = 0
        self.setFixedSize(self.SIZE, self.SIZE)

    def set_data(self, success: int, danger: int):
        self._success = success
        self._danger = danger
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(
            self.PEN_WIDTH / 2, self.PEN_WIDTH / 2,
            self.SIZE - self.PEN_WIDTH, self.SIZE - self.PEN_WIDTH,
        )

        bg_pen = QPen(QColor(COLORS["border"]), self.PEN_WIDTH)
        bg_pen.setCapStyle(Qt.RoundCap)
        painter.setPen(bg_pen)
        painter.drawArc(rect, 0, 360 * 16)

        for color_key, start, span in _ring_arcs(self._success, self._danger):
            pen = QPen(QColor(COLORS[color_key]), self.PEN_WIDTH)
            pen.setCapStyle(Qt.RoundCap)
            painter.setPen(pen)
            painter.drawArc(rect, int(start * 16), int(span * 16))

        total = self._success + self._danger
        center_text = f"{self._success}/{total}" if total else "—"

        painter.setPen(QColor(COLORS["text_main"]))
        value_font = QFont(FONT_MONO)
        value_font.setPointSize(17)
        value_font.setBold(True)
        painter.setFont(value_font)
        painter.drawText(self.rect().adjusted(0, -10, 0, -10), Qt.AlignCenter, center_text)

        painter.setPen(QColor(COLORS["text_muted"]))
        label_font = QFont(FONT_UI)
        label_font.setPointSize(8)
        label_font.setBold(True)
        painter.setFont(label_font)
        painter.drawText(self.rect().adjusted(0, 18, 0, 18), Qt.AlignCenter, "SAINS")


def _make_motif_separator() -> QWidget:
    """Séparateur de section reprenant le motif "flux" (3 points reliés) au lieu d'une simple
    ligne plate — cohérence de composition au-delà de la seule couleur (chantier identité,
    vague 2, idée 2). Le motif lui-même est un seul rendu SVG (ui.icons.motif_dots_icon) plutôt
    que des QLabel/QFrame juxtaposés : leurs ancrages verticaux (baseline de texte vs geometrie
    de cadre) ne s'alignaient pas — repéré sur une capture réelle où le trait paraissait décentré
    par rapport aux points. Un seul repère de coordonnées en SVG règle ça par construction."""
    from ui.icons import motif_dots_icon

    row = QWidget()
    hl = QHBoxLayout(row)
    hl.setContentsMargins(0, 8, 0, 8)
    hl.setSpacing(10)

    def _line() -> QFrame:
        f = QFrame()
        f.setFrameShape(QFrame.HLine)
        f.setStyleSheet(f"background: {COLORS['border']}; max-height: 1px; border: none;")
        return f

    dots_lbl = QLabel()
    dots_lbl.setPixmap(motif_dots_icon(COLORS["accent"]).pixmap(26, 14))
    dots_lbl.setStyleSheet("background: transparent; border: none;")

    hl.addWidget(_line(), stretch=1)
    hl.addWidget(dots_lbl)
    hl.addWidget(_line(), stretch=1)
    return row


_STATUS_BADGE = {
    "SUCCESS": "badge_success",
    "FAILED":  "badge_failed",
    "RUNNING": "badge_running",
    "IDLE":    "badge_idle",
}


def _apply_pulse(widget) -> None:
    """Anime l'opacité de `widget` en boucle infinie — signale un état "actif en ce moment"
    (badge RUNNING, pastille du rail "à venir / en cours" du Dashboard). Facteur commun pour que
    tout indicateur "ça tourne maintenant" pulse de la même façon dans toute l'application."""
    effect = QGraphicsOpacityEffect(widget)
    widget.setGraphicsEffect(effect)
    anim = QPropertyAnimation(effect, b"opacity", widget)
    anim.setDuration(1600)
    anim.setKeyValueAt(0.0, 1.0)
    anim.setKeyValueAt(0.5, 0.45)
    anim.setKeyValueAt(1.0, 1.0)
    anim.setEasingCurve(QEasingCurve.InOutSine)
    anim.setLoopCount(-1)
    anim.start()
    widget._pulse_anim = anim  # référence Python conservée par prudence (GC PySide6)


def _make_status_badge(text: str, object_name: str) -> QLabel:
    """Fabrique commune pour les badges de statut (Dashboard/Pipelines/Historique) — évite la
    triple duplication de `QLabel(...); setObjectName(...)` et centralise la pulsation du badge
    RUNNING (chantier identité, vague 1) pour qu'elle bénéficie aux 3 écrans d'un coup."""
    badge = QLabel(text)
    badge.setObjectName(object_name)
    badge.setAlignment(Qt.AlignCenter)
    if object_name == "badge_running":
        _apply_pulse(badge)
    return badge


def _status_str(val) -> str:
    return val.value if hasattr(val, "value") else str(val or "IDLE")


def _ordered_with_chains(pipelines) -> list:
    """Réordonne une liste de pipelines pour que chaque enfant (déclenché après un parent via
    trigger_after_pipeline_id, chantier P) apparaisse juste après son parent plutôt que noyé
    alphabétiquement — retourne une liste de tuples (pipeline, profondeur). Fonction pure, sans
    Qt, pour rester facilement testable (chantier identité, vague 1, idée 9 ; partagée avec la
    mini-topologie du Dashboard, vague 3, idée 5, qui a besoin du même ordre/profondeur)."""
    by_id = {p.id: p for p in pipelines}
    children = {}
    for p in pipelines:
        if p.trigger_after_pipeline_id in by_id:
            children.setdefault(p.trigger_after_pipeline_id, []).append(p)
    roots = [p for p in pipelines if p.trigger_after_pipeline_id not in by_id]

    ordered, seen = [], set()

    def visit(p, depth):
        if p.id in seen:   # garde-fou — la création empêche déjà les cycles, filet de sécurité
            return
        seen.add(p.id)
        ordered.append((p, depth))
        for c in children.get(p.id, []):
            visit(c, depth + 1)

    for r in roots:
        visit(r, 0)
    return ordered


def _make_title(text: str) -> QLabel:
    l = QLabel(text); l.setObjectName("section_title"); return l

def _make_subtitle(text: str) -> QLabel:
    l = QLabel(text); l.setObjectName("subtitle"); return l

def _make_page_eyebrow(text: str) -> QLabel:
    """Surtitre de page en majuscules (refonte, lot 0a — FONDATIONS.md section 2) : Mono, 11px,
    espacement 0,08em, text_dim. Distinct de _make_title (20px, section), réservé à l'en-tête de
    page via ui/components/page_header.py."""
    l = QLabel(text.upper()); l.setObjectName("page_eyebrow"); return l

def _make_page_title(text: str) -> QLabel:
    """Titre de page (refonte, lot 0a) : 26px/600, palier FONT_SIZES['page_title'] — distinct de
    _make_title (20px, titre de section), réservé à l'en-tête de page."""
    l = QLabel(text); l.setObjectName("page_title"); return l


# ──────────────────────────────────────────────
#  COMPOSANT : VIGNETTE DE FLUX (Pipelines, chantier identité, vague 3, idée 8)
# ──────────────────────────────────────────────

class PipelineFlowThumbnail(QWidget):
    """Points colorés reliés, un par étape (STEP_META[type]['color']) — signature de
    reconnaissance visuelle d'un pipeline dans la liste, pas une vraie disposition de graphe
    (pas de branches/edges réels, juste la séquence ordonnée de p.steps, déjà chargée en
    eager-load par get_pipelines() — aucune requête supplémentaire)."""

    DOT_R = 3
    GAP = 12

    def __init__(self, colors: list = None):
        super().__init__()
        self._colors = colors or []
        self.setFixedSize(self._width_for(len(self._colors)), 18)
        self.setStyleSheet("background: transparent; border: none;")

    def set_colors(self, colors: list):
        self._colors = colors
        self.setFixedWidth(self._width_for(len(colors)))
        self.update()

    def _width_for(self, n: int) -> int:
        return ((n - 1) * self.GAP + 2 * self.DOT_R) if n else 1

    def paintEvent(self, event):
        if not self._colors:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        y = self.height() / 2
        positions = [self.DOT_R + i * self.GAP for i in range(len(self._colors))]

        painter.setPen(QPen(QColor(COLORS["border"]), 1.4))
        for x1, x2 in zip(positions, positions[1:]):
            painter.drawLine(int(x1), int(y), int(x2), int(y))

        painter.setPen(Qt.NoPen)
        for x, color in zip(positions, self._colors):
            painter.setBrush(QBrush(QColor(color)))
            painter.drawEllipse(QPointF(x, y), self.DOT_R, self.DOT_R)


def _paint_dot_chain(painter: QPainter, colors: list, height: float) -> None:
    """Chaîne plate de points reliés — extrait de l'ancien PipelineFlowThumbnail.paintEvent
    (chantier Atelier Pipelines, écran 1) ; repli de PipelineStepDagThumbnail quand le graphe
    contient un cycle (_layout_step_dag_thumbnail renvoie alors None — jamais censé arriver sur
    un pipeline sauvegardé, validate_pipeline_graph() l'empêche à la sauvegarde, mais une base
    modifiée hors de l'appli reste possible)."""
    if not colors:
        return
    y = height / 2
    gap = PipelineFlowThumbnail.GAP
    r = PipelineFlowThumbnail.DOT_R
    positions = [r + i * gap for i in range(len(colors))]

    painter.setPen(QPen(QColor(COLORS["border"]), 1.4))
    for x1, x2 in zip(positions, positions[1:]):
        painter.drawLine(int(x1), int(y), int(x2), int(y))

    painter.setPen(Qt.NoPen)
    for x, color in zip(positions, colors):
        painter.setBrush(QBrush(QColor(color)))
        painter.drawEllipse(QPointF(x, y), r, r)


def _layout_step_dag_thumbnail(step_keys: list, edges: list) -> dict | None:
    """Position (colonne=rang, ligne=index dans le rang) de chaque étape pour la vignette
    mini-DAG de PipelinesView (chantier Atelier Pipelines, écran 1) — géométrie pure, pas de Qt,
    testable isolément (même philosophie que _layout_topology_nodes ci-dessous).
    topological_ranks() (core/pipeline.py) fait tout le travail de tri ; cette fonction ne fait
    que répartir les nœuds d'un même rang sur des lignes successives, dans l'ordre d'apparition
    de step_keys (= step_order, déjà l'ordre de p.steps). Retourne None si le graphe contient un
    cycle (même convention que topological_ranks/validate_pipeline_graph)."""
    from core.pipeline import topological_ranks
    ranks = topological_ranks(step_keys, edges)
    if ranks is None:
        return None
    by_rank: dict = {}
    for k in step_keys:
        by_rank.setdefault(ranks.get(k, 0), []).append(k)
    return {k: (rank, row) for rank, keys in by_rank.items() for row, k in enumerate(keys)}


class PipelineStepDagThumbnail(QWidget):
    """Mini-DAG par rang (chantier Atelier Pipelines, écran 1) — remplace PipelineFlowThumbnail
    dans la colonne Étapes de PipelinesView : points pour étapes normales, losanges pour nœuds
    de routage (is_routing_node, core/steps/__init__.py — CONDITION/GATEWAY_PARALLEL/
    GATEWAY_JOIN), colorés via STEP_META[type]['color']. Reflète les vraies branches (edges),
    contrairement à PipelineFlowThumbnail qui ne connaît que la séquence plate de p.steps.

    `nodes` : liste de dicts {"step_key", "color", "is_routing"} dans l'ordre step_order (=
    l'ordre de p.steps). `edges` : liste de dicts {"from_step_key", "to_step_key"} (même forme
    que core/pipeline.py::topological_ranks)."""

    DOT_R = 3
    DIAMOND_R = 4
    COL_GAP = 16
    ROW_GAP = 9
    MARGIN = DIAMOND_R
    MAX_VISIBLE_ROWS = 3   # la cellule du tableau a une hauteur fixe (table.setRowHeight(r_idx,
                           # 52), pipelines_view.py) — un rang à 4+ nœuds parallèles doit
                           # tronquer avec un repère "+N", pas déborder.
    HEIGHT = 2 * MARGIN + (MAX_VISIBLE_ROWS - 1) * ROW_GAP

    def __init__(self, nodes: list = None, edges: list = None):
        super().__init__()
        self._nodes = nodes or []
        self._edges = edges or []
        self.setFixedSize(self._width_for(self._nodes, self._edges), self.HEIGHT)
        self.setStyleSheet("background: transparent; border: none;")

    def set_data(self, nodes: list, edges: list):
        self._nodes = nodes or []
        self._edges = edges or []
        self.setFixedWidth(self._width_for(self._nodes, self._edges))
        self.update()

    def _width_for(self, nodes: list, edges: list) -> int:
        if not nodes:
            return 1
        positions = _layout_step_dag_thumbnail([n["step_key"] for n in nodes], edges)
        if positions is None:
            n = len(nodes)
            return ((n - 1) * PipelineFlowThumbnail.GAP + 2 * PipelineFlowThumbnail.DOT_R) if n else 1
        max_col = max(col for col, _row in positions.values())
        return 2 * self.MARGIN + max_col * self.COL_GAP

    def paintEvent(self, event):
        if not self._nodes:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        step_keys = [n["step_key"] for n in self._nodes]
        positions = _layout_step_dag_thumbnail(step_keys, self._edges)
        if positions is None:
            _paint_dot_chain(painter, [n["color"] for n in self._nodes], self.height())
            return

        by_key = {n["step_key"]: n for n in self._nodes}
        rows_per_col: dict = {}
        xy: dict = {}
        for key, (col, row) in positions.items():
            visible_row = min(row, self.MAX_VISIBLE_ROWS - 1)
            x = self.MARGIN + col * self.COL_GAP
            y = self.MARGIN + visible_row * self.ROW_GAP
            xy[key] = (x, y)
            rows_per_col[col] = max(rows_per_col.get(col, 0), row + 1)

        # Arêtes d'abord (sous les nœuds) — seulement entre deux nœuds tous deux visibles.
        painter.setPen(QPen(QColor(COLORS["border"]), 1.2))
        for e in self._edges:
            frm, to = e.get("from_step_key"), e.get("to_step_key")
            if frm in xy and to in xy:
                x1, y1 = xy[frm]
                x2, y2 = xy[to]
                painter.drawLine(int(x1), int(y1), int(x2), int(y2))

        painter.setPen(Qt.NoPen)
        for key, (x, y) in xy.items():
            node = by_key[key]
            painter.setBrush(QBrush(QColor(node["color"])))
            if node.get("is_routing"):
                r = self.DIAMOND_R
                path = QPainterPath()
                path.moveTo(x, y - r)
                path.lineTo(x + r, y)
                path.lineTo(x, y + r)
                path.lineTo(x - r, y)
                path.closeSubpath()
                painter.drawPath(path)
            else:
                painter.drawEllipse(QPointF(x, y), self.DOT_R, self.DOT_R)

        # Repère "+N" par colonne tronquée — aucun nœud supplémentaire dessiné au-delà de
        # MAX_VISIBLE_ROWS, juste un indicateur textuel (même esprit que la troncature
        # steps_str[:44] + "…" déjà utilisée dans PipelinesView.refresh()).
        painter.setPen(QColor(COLORS["text_muted"]))
        font = QFont(FONT_UI); font.setPointSize(7)
        painter.setFont(font)
        for col, count in rows_per_col.items():
            overflow = count - self.MAX_VISIBLE_ROWS
            if overflow > 0:
                x = self.MARGIN + col * self.COL_GAP
                y = self.MARGIN + (self.MAX_VISIBLE_ROWS - 1) * self.ROW_GAP
                painter.drawText(QRectF(x + self.DIAMOND_R, y - 6, 20, 12),
                                  Qt.AlignLeft | Qt.AlignVCenter, f"+{overflow}")


# ──────────────────────────────────────────────
#  COMPOSANT : MINI-TOPOLOGIE (Dashboard, chantier identité, vague 3, idée 5)
# ──────────────────────────────────────────────

_TOPOLOGY_STATUS_COLOR_KEY = {
    "SUCCESS": "success",
    "FAILED": "danger",
    "RUNNING": "signal",
}


def _layout_topology_nodes(ordered: list, max_width: int) -> list:
    """Géométrie pure (pas de Qt) — factorisée hors de paintEvent() pour rester testable, même
    philosophie que _ring_arcs()/ActivityChartWidget._bar_rect(). `ordered` est la sortie de
    _ordered_with_chains() : une chaîne (racine + descendants) est toujours consécutive et sur
    la même ligne (ils partagent la même lignée) ; layout "étagères" — si la chaîne suivante ne
    tient plus sur la ligne courante, passage à la ligne suivante. Retourne une liste de
    (pipeline, depth, x, y, parent_id_ou_None)."""
    node_w, node_h = PipelineTopologyWidget.NODE_W, PipelineTopologyWidget.NODE_H
    gap_x, gap_y, margin = (
        PipelineTopologyWidget.GAP_X, PipelineTopologyWidget.GAP_Y, PipelineTopologyWidget.MARGIN,
    )

    positions = []
    cursor_x, cursor_y = margin, margin
    chain: list = []

    def flush_chain():
        nonlocal cursor_x, cursor_y, chain
        if not chain:
            return
        max_depth = max(d for _, d in chain)
        chain_width = (max_depth + 1) * node_w + max_depth * gap_x
        if cursor_x != margin and cursor_x + chain_width > max_width - margin:
            cursor_x = margin
            cursor_y += node_h + gap_y
        last_at_depth = {}
        for p, depth in chain:
            x = cursor_x + depth * (node_w + gap_x)
            y = cursor_y
            parent_id = last_at_depth.get(depth - 1)
            positions.append((p, depth, x, y, parent_id))
            last_at_depth[depth] = p.id
        cursor_x += chain_width + gap_x * 2
        chain = []

    for p, depth in ordered:
        if depth == 0:
            flush_chain()
            chain = [(p, depth)]
        else:
            chain.append((p, depth))
    flush_chain()
    return positions


class PipelineTopologyWidget(QWidget):
    """Aperçu des pipelines en nœuds reliés par les chaînes de déclenchement (chantier P),
    colorés par leur dernier statut — remplace le graphique d'activité sur le Dashboard. Layout
    "étagères" (greedy row-wrap, voir _layout_topology_nodes) plutôt qu'un vrai moteur de
    bin-packing : la volumétrie réelle de ce projet reste petite (quelques pipelines)."""

    NODE_W, NODE_H = 150, 54
    GAP_X, GAP_Y = 30, 16
    MARGIN = 14

    def __init__(self):
        super().__init__()
        self._ordered = []
        self.setMinimumHeight(self.NODE_H + 2 * self.MARGIN)

    def set_data(self, ordered: list):
        self._ordered = ordered
        self.update()

    def paintEvent(self, event):
        from ui.step_editor.common import STEP_META

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        if not self._ordered:
            painter.setPen(QColor(COLORS["text_muted"]))
            painter.drawText(self.rect(), Qt.AlignCenter, "Aucun pipeline à afficher")
            return

        positions = _layout_topology_nodes(self._ordered, max(self.width(), self.NODE_W + 2 * self.MARGIN))
        by_id = {p.id: (x, y) for p, _depth, x, y, _parent in positions}

        needed_height = max((y for _, _, _, y, _ in positions), default=0) + self.NODE_H + self.MARGIN
        if needed_height != self.minimumHeight():
            self.setMinimumHeight(needed_height)

        # Arêtes d'abord (sous les nœuds).
        for p, _depth, x, y, parent_id in positions:
            if parent_id is None or parent_id not in by_id:
                continue
            px, py = by_id[parent_id]
            painter.setPen(QPen(QColor(COLORS["signal"]), 1.8))
            y1 = py + self.NODE_H / 2
            y2 = y + self.NODE_H / 2
            painter.drawLine(int(px + self.NODE_W), int(y1), int(x), int(y2))

        for p, _depth, x, y, _parent in positions:
            status = _status_str(p.last_status)
            if not p.is_active:
                border_color = COLORS["border"]
            else:
                border_color = COLORS[_TOPOLOGY_STATUS_COLOR_KEY.get(status, "border")]

            rect = QRectF(x, y, self.NODE_W, self.NODE_H)
            # bg_main (le plus sombre des 3 fonds) pour un contraste net avec le conteneur
            # (bg_panel — voir _build_ui() dans dashboard_view.py) : bg_panel/bg_card étaient
            # trop proches pour se distinguer clairement une fois rendus (repéré sur une capture
            # réelle — l'écart lisible en maquette web ne l'était pas ici).
            painter.setBrush(QBrush(QColor(COLORS["bg_main"])))
            pen = QPen(QColor(border_color), 1.5)
            if not p.is_active:
                pen.setStyle(Qt.DashLine)   # inactif : bordure interrompue, pas seulement grise
            painter.setPen(pen)
            painter.drawRoundedRect(rect, 8, 8)

            # Point en ligne avec le nom (même centre vertical), pas empilé au-dessus — repéré en
            # comparant à la maquette validée.
            name_rect = QRectF(x + 22, y + 12, self.NODE_W - 32, 18)
            dot_rect = QRectF(x + 10, name_rect.center().y() - 3, 6, 6)
            painter.setBrush(QBrush(QColor(border_color)))
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(dot_rect)

            painter.setPen(QColor(COLORS["text_main"]))
            font = QFont(FONT_UI); font.setBold(True); font.setPointSize(9)
            painter.setFont(font)
            name = p.name if len(p.name) <= 18 else p.name[:17] + "…"
            painter.drawText(name_rect, Qt.AlignLeft | Qt.AlignVCenter, name)

            # Résumé d'étapes plutôt que le simple mot de statut (déjà porté par le point/la
            # bordure colorée, redondant sinon) — repéré en comparant à la maquette validée.
            step_types = [str(s.step_type).replace("StepType.", "") for s in (p.steps or [])]
            step_summary = " → ".join(
                STEP_META.get(t, {}).get("label", t) for t in step_types
            ) or "—"
            if len(step_summary) > 22:
                step_summary = step_summary[:21] + "…"
            sub = f"{step_summary} · inactif" if not p.is_active else step_summary
            painter.setPen(QColor(COLORS["text_muted"]))
            font2 = QFont(FONT_UI); font2.setPointSize(8)
            painter.setFont(font2)
            # Aligné sur le nom (x+22), pas sur le point (x+10) — désalignement repéré sur une
            # capture réelle après le passage du point en ligne avec le nom.
            painter.drawText(QRectF(x + 22, y + 34, self.NODE_W - 32, 14),
                              Qt.AlignLeft | Qt.AlignVCenter, sub)


# ──────────────────────────────────────────────
#  COMPOSANT : PASTILLES D'HISTORIQUE (Dashboard, chantier identité, vague 3, idée 7)
# ──────────────────────────────────────────────

_RUN_DOT_COLOR_KEY = {
    "SUCCESS": "success",
    "FAILED": "danger",
    "CANCELLED": "text_muted",
    "RUNNING": "signal",
}


class RunHistoryDots(QWidget):
    """Bande de pastilles colorées représentant les N dernières exécutions d'un pipeline (façon
    graphe de contributions) — remplace le badge de statut unique dans le tableau "Dernières
    exécutions" du Dashboard, qui ne montrait que le tout dernier run."""

    DOT_R = 4
    GAP = 11

    def __init__(self, statuses: list = None):
        super().__init__()
        self._statuses = statuses or []
        self.setFixedSize(self._width_for(len(self._statuses)), 16)
        self.setStyleSheet("background: transparent; border: none;")

    def set_statuses(self, statuses: list):
        self._statuses = statuses
        self.setFixedWidth(self._width_for(len(statuses)))
        self.update()

    def _width_for(self, n: int) -> int:
        return ((n - 1) * self.GAP + 2 * self.DOT_R) if n else 1

    def paintEvent(self, event):
        if not self._statuses:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        y = self.height() / 2
        for i, status in enumerate(self._statuses):
            x = self.DOT_R + i * self.GAP
            color_key = _RUN_DOT_COLOR_KEY.get(status, "border")
            painter.setBrush(QBrush(QColor(COLORS[color_key])))
            painter.drawEllipse(QPointF(x, y), self.DOT_R, self.DOT_R)


# ──────────────────────────────────────────────
#  COMPOSANT : CALENDRIER DE FRÉQUENCE (Historique, chantier identité, vague 4, idée 13)
# ──────────────────────────────────────────────

def _heatmap_day_color_key(day_counts: dict) -> str:
    """Couleur d'une case du calendrier de fréquence pour un jour donné — pire résultat du jour
    l'emporte (un seul échec dans la journée suffit à colorer la case en danger), pour que
    "ce pipeline échoue tous les lundis" saute aux yeux d'un coup d'œil."""
    if day_counts.get("failed", 0) > 0:
        return "danger"
    if day_counts.get("success", 0) > 0:
        return "success"
    return "border"


def _heatmap_day_tooltip(day_counts: dict) -> str:
    """Texte d'infobulle d'UNE case précise (date + détail des exécutions ce jour-là) — un
    "90 derniers jours" identique sur toutes les cases n'apprend rien à l'utilisateur qui
    cherche justement à savoir QUAND et QUOI s'est produit."""
    d = day_counts.get("date")
    date_s = d.strftime("%d/%m/%Y") if d else "?"
    success, failed, cancelled = (
        day_counts.get("success", 0), day_counts.get("failed", 0), day_counts.get("cancelled", 0))
    if not (success or failed or cancelled):
        return f"{date_s} — aucune exécution"
    parts = []
    if success:
        parts.append(f"{success} succès")
    if failed:
        parts.append(f"{failed} échec" + ("s" if failed > 1 else ""))
    if cancelled:
        parts.append(f"{cancelled} annulé" + ("s" if cancelled > 1 else ""))
    return f"{date_s} — " + ", ".join(parts)


class RunFrequencyHeatmap(QWidget):
    """Bande de cases colorées, une par jour, façon graphe de contributions — vue d'ensemble de
    la fréquence/fiabilité d'exécution d'un pipeline sur les derniers mois. Alimentée par
    get_run_counts_by_day(days, pipeline_id) (chantier D.1), déjà zéro-rempli jour par jour.

    Survoler une case affiche le détail de CE jour (pas un texte générique identique partout) ;
    cliquer une case avec au moins une exécution émet day_clicked(date) — au widget appelant de
    décider quoi en faire (ici, HistoryView ouvre la liste des exécutions de ce jour)."""

    SQUARE = 8
    GAP = 3

    day_clicked = Signal(object)   # datetime.date

    def __init__(self, counts: list = None):
        super().__init__()
        self._counts = counts or []
        self.setFixedSize(self._width_for(len(self._counts)), self.SQUARE)
        self.setStyleSheet("background: transparent; border: none;")
        self.setMouseTracking(True)
        self.setCursor(Qt.PointingHandCursor)

    def set_counts(self, counts: list):
        self._counts = counts or []
        self.setFixedWidth(self._width_for(len(self._counts)))
        self.update()

    def _width_for(self, n: int) -> int:
        return (n * self.SQUARE + max(0, n - 1) * self.GAP) if n else 1

    def _index_at(self, x: float) -> int | None:
        if not self._counts:
            return None
        i = int(x // (self.SQUARE + self.GAP))
        return i if 0 <= i < len(self._counts) else None

    def event(self, ev):
        if ev.type() == QEvent.ToolTip:
            idx = self._index_at(ev.pos().x())
            if idx is not None:
                QToolTip.showText(ev.globalPos(), _heatmap_day_tooltip(self._counts[idx]), self)
            else:
                QToolTip.hideText()
            return True
        return super().event(ev)

    def mousePressEvent(self, event):
        idx = self._index_at(event.position().x())
        if idx is not None:
            day_counts = self._counts[idx]
            if day_counts.get("success") or day_counts.get("failed") or day_counts.get("cancelled"):
                self.day_clicked.emit(day_counts.get("date"))
        super().mousePressEvent(event)

    def paintEvent(self, event):
        if not self._counts:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, False)
        painter.setPen(Qt.NoPen)
        for i, day_counts in enumerate(self._counts):
            x = i * (self.SQUARE + self.GAP)
            color_key = _heatmap_day_color_key(day_counts)
            painter.setBrush(QBrush(QColor(COLORS[color_key])))
            painter.drawRoundedRect(QRectF(x, 0, self.SQUARE, self.SQUARE), 2, 2)

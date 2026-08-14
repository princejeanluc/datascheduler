"""
DataScheduler — ui/main_window/widgets.py
Helpers, constantes et petits composants partagés par toutes les vues.
"""

import qtawesome as qta
from PySide6.QtWidgets import (
    QVBoxLayout, QLabel, QPushButton, QFrame, QSizePolicy, QLineEdit,
    QTableWidget, QHeaderView, QGraphicsOpacityEffect,
)
from PySide6.QtCore import Qt, QSize, Signal, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QIcon
from ui.styles import COLORS, FONT_MONO, FONT_UI, FONT_MONO_STACK, FONT_UI_STACK


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
    color = icon_color or (COLORS["danger"] if object_name == "danger" else COLORS["text_main"])
    btn.setIcon(_icon(icon_name, color))
    btn.setIconSize(QSize(14, 14))
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


def _make_empty_label(text: str) -> QLabel:
    """Message d'état vide, cohérent avec celui de l'éditeur de pipeline."""
    lbl = QLabel(text)
    lbl.setAlignment(Qt.AlignCenter)
    lbl.setWordWrap(True)
    lbl.setStyleSheet(
        f"color: {COLORS['text_muted']}; font-size: 12px; font-style: italic; "
        f"background: {COLORS['bg_panel']}; border: 1px solid {COLORS['border']}; "
        f"border-radius: 6px; padding: 28px 12px;"
    )
    return lbl

# ──────────────────────────────────────────────
#  CONSTANTES
# ──────────────────────────────────────────────

NAV_WIDTH   = 220
HEADER_H    = 52
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
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(44)
        self.setIconSize(QSize(16, 16))
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._apply_style()

    def set_active(self, active: bool):
        self._active = active
        self._apply_style()

    def _apply_style(self):
        bg     = COLORS["bg_active"] if self._active else "transparent"
        color  = COLORS["text_main"] if self._active else COLORS["text_dim"]
        border = f"border-left: 3px solid {COLORS['accent']};" if self._active else "border-left: 3px solid transparent;"
        self.setStyleSheet(f"""
            QPushButton {{
                background-color: {bg};
                color: {color};
                {border}
                border-radius: 0px;
                padding: 0px 16px 0px 12px;
                text-align: left;
                font-size: 13px;
                font-weight: {"600" if self._active else "400"};
            }}
            QPushButton:hover {{
                background-color: {COLORS['bg_hover']};
                color: {COLORS['text_main']};
            }}
        """)
        self.setText(f"  {self._label}")
        if self._icon_name:
            from ui.icons import nav_icon
            self.setIcon(nav_icon(self._icon_name, color))


# ──────────────────────────────────────────────
#  COMPOSANT : CARTE STAT (Dashboard)
# ──────────────────────────────────────────────

class StatCard(QFrame):
    clicked = Signal()

    def __init__(self, title: str, value: str = "—", subtitle: str = "",
                 color: str = None, clickable: bool = False, border_accent: str = None):
        super().__init__()
        self.setObjectName("card")
        self.setFixedHeight(100)
        self._clickable = clickable
        if clickable:
            self.setCursor(Qt.PointingHandCursor)
        # Liseré de couleur (chantier identité visuelle, phase 2) — n'ajoute que border-left,
        # le reste de l'apparence de la carte reste géré par QFrame#card dans GLOBAL_STYLE.
        self.setStyleSheet(
            f"QFrame#card {{ border-left: 3px solid {border_accent or COLORS['signal']}; }}"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 14, 20, 14)
        layout.setSpacing(4)

        lbl_title = QLabel(title.upper())
        lbl_title.setStyleSheet(f"color: {COLORS['text_dim']}; font-size: 10px; font-weight: 700; letter-spacing: 1px; background: transparent; border: none;")

        self._lbl_value = QLabel(value)
        c = color or COLORS["text_main"]
        self._lbl_value.setStyleSheet(f"color: {c}; font-size: 28px; font-weight: 700; background: transparent; border: none;")

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

def _make_title(text: str) -> QLabel:
    l = QLabel(text); l.setObjectName("section_title"); return l

def _make_subtitle(text: str) -> QLabel:
    l = QLabel(text); l.setObjectName("subtitle"); return l

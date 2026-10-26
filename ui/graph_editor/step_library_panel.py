"""
DataScheduler — ui/graph_editor/step_library_panel.py
Panneau « Ajouter » flottant du canevas (C7, frame Atelier-ajout) — remplace le dialogue modal
StepTypeChooserDialog pour l'ajout d'étape en mode Atelier réel (StepTypeChooserDialog reste
intact, toujours utilisé par le dialogue de compatibilité, voir docs/refonte/impact/
c7-atelier-ajout.md). Réutilise son contenu (_DESCRIPTIONS/_CATEGORY_ORDER, Mes modèles) plutôt
que de le dupliquer.

Une carte ne s'insère jamais elle-même : un clic sélectionne (signal selection_changed, l'hôte
met à jour l'aperçu de droite) et active un glisser (QDrag) — c'est toujours
PipelineGraphEditorWidget qui décide où/comment insérer (bouton d'aperçu, Entrée, ou dépôt sur le
canevas), jamais ce panneau.
"""

import json

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QFrame,
    QScrollArea, QApplication, QInputDialog, QMessageBox,
)
from PySide6.QtCore import Qt, QSize, QPoint, QMimeData, Signal
from PySide6.QtGui import QDrag

from ui.styles import COLORS
from ui.step_editor.common import STEP_META, _icon
from ui.step_editor.step_type_chooser_dialog import (
    _DESCRIPTIONS, _CATEGORY_ORDER, step_type_description,
)
from core.steps import is_routing_node, known_step_types

# Marqueur de glisser interne — aucune interopérabilité externe attendue (glisser-déposer
# in-process seulement) ; la charge utile réelle (step_type, config) voyage hors bande via
# StepLibraryPanel._drag_payload, jamais encodée dans le QMimeData lui-même (un objet Python
# arbitraire n'y tient pas).
MIME_TYPE = "application/x-kulu-step-card"

_ROUTING_LABELS = [("Aiguillage", "CONDITION"), ("Parallèle", "GATEWAY_PARALLEL"),
                    ("Jonction", "GATEWAY_JOIN")]
_ROUTING_SYMBOLS = {"CONDITION": "?", "GATEWAY_PARALLEL": "+", "GATEWAY_JOIN": "ET"}


class _DraggableCard(QFrame):
    """Base commune carte de type / badge de passerelle : sélection au clic, glisser réel
    au-delà du seuil Qt standard. `panel` est le StepLibraryPanel parent — sert à déposer la
    charge utile du glisser avant drag.exec() (voir docstring du module)."""

    clicked = Signal()

    def __init__(self, panel: "StepLibraryPanel", step_type: str, config: dict | None, parent=None):
        super().__init__(parent)
        self._panel = panel
        self._step_type = step_type
        self._config = config or {}
        self._press_pos: QPoint | None = None
        self._dragging = False
        self._selected = False
        self.setCursor(Qt.PointingHandCursor)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._press_pos = event.position().toPoint()
            self._dragging = False
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._press_pos is None or not (event.buttons() & Qt.LeftButton):
            return
        moved = (event.position().toPoint() - self._press_pos).manhattanLength()
        if moved < QApplication.startDragDistance():
            return
        self._dragging = True
        self._panel._drag_payload = (self._step_type, self._config)
        drag = QDrag(self)
        mime = QMimeData()
        mime.setData(MIME_TYPE, b"1")
        drag.setMimeData(mime)
        drag.exec(Qt.CopyAction)
        self._panel._drag_payload = None

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and not self._dragging and self._press_pos is not None:
            self.clicked.emit()
        self._press_pos = None
        self._dragging = False
        super().mouseReleaseEvent(event)

    def set_selected(self, selected: bool):
        self._selected = selected
        self._apply_style()

    def _apply_style(self):
        raise NotImplementedError


class _StepCard(_DraggableCard):
    """Une ligne de la bibliothèque (type normal ou modèle) — point de couleur, libellé, légende.
    `extra_widgets` (boutons renommer/supprimer d'un modèle) vit à droite, inerte au glisser
    (un QPushButton enfant consomme son propre relâchement — même garantie que
    StepTypeChooserDialog._make_template_card, déjà vérifiée là-bas)."""

    def __init__(self, panel, step_type, title, subtitle, dot_color, config=None,
                 extra_widgets=None, parent=None):
        super().__init__(panel, step_type, config, parent)
        hl = QHBoxLayout(self)
        hl.setContentsMargins(8, 7, 8, 7)
        hl.setSpacing(10)

        dot = QLabel()
        dot.setFixedSize(10, 10)
        dot.setStyleSheet(f"background: {dot_color}; border-radius: 3px;")
        hl.addWidget(dot)

        title_lbl = QLabel(title)
        title_lbl.setStyleSheet(f"color: {COLORS['text_main']}; background: transparent; border: none;")
        hl.addWidget(title_lbl, stretch=1)

        if subtitle:
            sub_lbl = QLabel(subtitle)
            sub_lbl.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 11px; background: transparent; border: none;")
            hl.addWidget(sub_lbl)

        for w in (extra_widgets or []):
            hl.addWidget(w)

        self._apply_style()

    def _apply_style(self):
        if self._selected:
            self.setStyleSheet(
                f"QFrame {{ background: {COLORS['bg_active']}; border-radius: 6px; "
                f"border: 1px solid {COLORS['accent']}; }}"
            )
        else:
            self.setStyleSheet(
                f"QFrame {{ background: transparent; border-radius: 6px; border: 1px solid transparent; }}"
                f"QFrame:hover {{ background: {COLORS['bg_hover']}; }}"
            )


class _RoutingBadge(_DraggableCard):
    """Badge losange des 3 passerelles (Aiguillage/Parallèle/Jonction) — mêmes couleurs que le
    rendu réel du nœud sur le canevas (node_item.py : fond teinté _tinted_bg(bg_card, couleur de
    famille), symbole blanc), en miniature pour la grille 3 colonnes."""

    def __init__(self, panel, step_type, label, symbol, parent=None):
        super().__init__(panel, step_type, {}, parent)
        from PySide6.QtGui import QColor
        from .node_item import _tinted_bg
        family_color = STEP_META[step_type]["color"]
        fill = _tinted_bg(QColor(COLORS["bg_card"]), QColor(family_color)).name()

        vl = QVBoxLayout(self)
        vl.setContentsMargins(4, 10, 4, 10)
        vl.setSpacing(6)
        vl.setAlignment(Qt.AlignCenter)

        diamond = QLabel(symbol)
        diamond.setFixedSize(20, 20)
        diamond.setAlignment(Qt.AlignCenter)
        diamond.setStyleSheet(
            f"background: {fill}; border: 1.5px solid {family_color}; border-radius: 4px; "
            f"color: #ffffff; font-size: 10px; font-weight: 700;"
        )
        diamond_row = QHBoxLayout(); diamond_row.setAlignment(Qt.AlignCenter)
        diamond_row.addWidget(diamond)
        vl.addLayout(diamond_row)

        lbl = QLabel(label)
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setStyleSheet(f"color: {COLORS['text_main']}; font-size: 11.5px; background: transparent; border: none;")
        vl.addWidget(lbl)

        self._apply_style()

    def _apply_style(self):
        border = COLORS["accent"] if self._selected else COLORS["border"]
        bg = COLORS["bg_active"] if self._selected else COLORS["bg_card"]
        self.setStyleSheet(
            f"QFrame {{ background: {bg}; border: 1px solid {border}; border-radius: 8px; }}"
        )


class StepLibraryPanel(QWidget):
    """Voir docstring du module. `selection_changed(step_type, config)` à chaque sélection
    (clic ou premier résultat après une recherche validée) ; `close_requested` au bouton ×."""

    selection_changed = Signal(str, dict)
    close_requested = Signal()
    insert_requested = Signal()   # Entrée dans la recherche — même sélection courante, l'hôte décide où

    PANEL_WIDTH = 312

    def __init__(self, parent=None):
        super().__init__(parent)
        self._drag_payload = None   # (step_type, config) — posé juste avant QDrag.exec(), lu par
                                     # PipelineGraphView.dropEvent (voir _DraggableCard)
        self._selected_type: str | None = None
        self._selected_config: dict = {}
        self._cards: list[_DraggableCard] = []
        self._sections: list[tuple[QLabel, list]] = []
        self._templates_header: QLabel | None = None
        self.setFixedWidth(self.PANEL_WIDTH)
        self.setObjectName("stepLibraryPanel")
        # Gotcha Qt connu (voir REGLES.md) : un QWidget nu n'applique pas "background-color" de
        # son propre QSS sans ce flag — sans lui, le panneau reste transparent et laisse voir le
        # rail/l'aide de glisser derrière lui malgré un z-order pourtant correct (déjà vérifié).
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(
            f"QWidget#stepLibraryPanel {{ background: {COLORS['bg_panel']}; "
            f"border-right: 1px solid {COLORS['border']}; }}"
        )
        self._build_ui()
        # Échap ferme le panneau quel que soit l'enfant qui a le focus (recherche le plus
        # souvent) — WidgetWithChildrenShortcut, pas un simple keyPressEvent qui ne capterait
        # que les évènements adressés directement à ce QWidget, jamais à self.inp_search.
        from PySide6.QtGui import QKeySequence, QShortcut
        QShortcut(QKeySequence(Qt.Key_Escape), self, activated=self.close_requested.emit,
                  context=Qt.WidgetWithChildrenShortcut)

    def consume_drag_payload(self) -> tuple[str, dict] | None:
        """Appelé par PipelineGraphView.dropEvent — jamais par ce panneau lui-même."""
        return self._drag_payload

    def reposition(self) -> None:
        """Épinglé au bord gauche du viewport, pleine hauteur — même patron que ZoomWidget/
        GraphMinimapWidget/NodeSearchOverlay, appelé par PipelineGraphView.resizeEvent."""
        parent = self.parentWidget()
        if parent is None:
            return
        self.setGeometry(0, 0, self.PANEL_WIDTH, parent.height())

    # ── Construction ──────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header = QHBoxLayout()
        header.setContentsMargins(16, 14, 12, 10)
        title = QLabel("Ajouter")
        title.setStyleSheet(f"color: {COLORS['text_main']}; font-size: 15px; font-weight: 600; background: transparent; border: none;")
        header.addWidget(title)
        header.addStretch()
        # fa5s.times (qtawesome), pas un caractère "×" littéral — même patron que
        # SidePanel._btn_close/sql_editor._FindBar.btn_close, un glyphe texte n'est pas garanti
        # présent dans la police embarquée (IBM Plex Sans en base64, voir ui/fonts.py).
        btn_close = QPushButton()
        btn_close.setIcon(_icon("fa5s.times", COLORS["text_dim"]))
        btn_close.setFixedSize(24, 24)
        btn_close.setToolTip("Fermer (Échap)")
        btn_close.setStyleSheet(
            f"QPushButton {{ background: transparent; border: none; }}"
            f"QPushButton:hover {{ background: {COLORS['bg_hover']}; border-radius: 4px; }}"
        )
        btn_close.clicked.connect(self.close_requested.emit)
        header.addWidget(btn_close)
        root.addLayout(header)

        self.inp_search = QLineEdit()
        self.inp_search.setPlaceholderText("Étape, passerelle ou modèle…")
        self.inp_search.setFixedHeight(36)
        self.inp_search.setStyleSheet(
            f"QLineEdit {{ margin: 0 16px; background: {COLORS['bg_main']}; "
            f"border: 2px solid {COLORS['accent']}; border-radius: 6px; padding: 0 10px; "
            f"color: {COLORS['text_main']}; font-size: 13px; }}"
        )
        self.inp_search.textChanged.connect(self._on_search_changed)
        self.inp_search.returnPressed.connect(self._on_return_pressed)
        root.addWidget(self.inp_search)

        hint = QLabel("Glisser sur le canevas ou une liaison · Entrée insère après la sélection")
        hint.setWordWrap(True)
        hint.setStyleSheet(
            f"color: {COLORS['text_muted']}; font-size: 11px; background: transparent; "
            f"border: none; padding: 8px 16px 6px 16px;"
        )
        root.addWidget(hint)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        inner = QWidget()
        scroll.setWidget(inner)
        root.addWidget(scroll, stretch=1)

        self._list_layout = QVBoxLayout(inner)
        self._list_layout.setContentsMargins(8, 4, 8, 12)
        self._list_layout.setSpacing(1)

        self._templates_container = QWidget()
        self._templates_layout = QVBoxLayout(self._templates_container)
        self._templates_layout.setContentsMargins(0, 0, 0, 0)
        self._templates_layout.setSpacing(1)
        self._list_layout.addWidget(self._templates_container)
        self.refresh_templates()

        routing_header = self._section_header("PASSERELLES")
        self._list_layout.addWidget(routing_header)
        grid_host = QWidget()
        grid = QHBoxLayout(grid_host)
        grid.setContentsMargins(0, 2, 0, 6)
        grid.setSpacing(6)
        routing_cards = []
        for label, step_type in _ROUTING_LABELS:
            badge = _RoutingBadge(self, step_type, label, _ROUTING_SYMBOLS[step_type])
            badge._label_text = f"{label} {STEP_META[step_type]['label']}"
            badge.clicked.connect(lambda t=step_type: self._select(t, {}))
            grid.addWidget(badge)
            self._cards.append(badge)
            routing_cards.append(badge)
        self._list_layout.addWidget(grid_host)
        self._sections.append((routing_header, routing_cards))

        for category in _CATEGORY_ORDER:
            types_in_category = [
                t for t in _DESCRIPTIONS
                if STEP_META[t]["category"] == category and not is_routing_node(t)
            ]
            if not types_in_category:
                continue
            cat_header = self._section_header(category.upper())
            self._list_layout.addWidget(cat_header)
            cat_cards = []
            for step_type in types_in_category:
                meta = STEP_META[step_type]
                card = _StepCard(self, step_type, meta["label"], None, meta["color"])
                card._label_text = meta["label"]
                card.clicked.connect(lambda t=step_type: self._select(t, {}))
                self._list_layout.addWidget(card)
                self._cards.append(card)
                cat_cards.append(card)
            self._sections.append((cat_header, cat_cards))

        self._list_layout.addStretch()

    @staticmethod
    def _section_header(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(
            f"color: {COLORS['text_dim']}; font-size: 10.5px; font-weight: 600; "
            f"letter-spacing: 0.06em; background: transparent; border: none; padding: 8px 8px 4px 8px;"
        )
        return lbl

    # ── Mes modèles ────────────────────────────

    def refresh_templates(self):
        """(Re)construit "Mes modèles" — appelée à la construction puis après chaque renommage/
        suppression, même patron que StepTypeChooserDialog._refresh_templates_section()."""
        from database import db_manager as db
        from ui.main_window.widgets import _action_btn

        while self._templates_layout.count():
            item = self._templates_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        self._cards = [c for c in self._cards if getattr(c, "_is_template_card", False) is False]
        self._sections = [s for s in self._sections if s[0] is not self._templates_header]

        try:
            raw_templates = db.get_step_templates()
        except RuntimeError:
            raw_templates = []
        templates = [t for t in raw_templates if t.step_type in known_step_types()]
        if not templates:
            self._templates_header = None
            return

        self._templates_header = self._section_header("MES MODÈLES")
        self._templates_layout.addWidget(self._templates_header)
        template_cards = []
        for template in templates:
            meta = STEP_META[template.step_type]
            btn_rename = _action_btn("fa5s.pen", object_name="secondary", tooltip="Renommer", size=(20, 20))
            btn_rename.clicked.connect(
                lambda _, tid=template.id, cur=template.name: self._on_rename_template(tid, cur)
            )
            btn_delete = _action_btn("fa5s.trash-alt", object_name="danger", tooltip="Supprimer", size=(20, 20))
            btn_delete.clicked.connect(
                lambda _, tid=template.id, nm=template.name: self._on_delete_template(tid, nm)
            )
            config = json.loads(template.config_json or "{}")
            card = _StepCard(
                self, template.step_type, template.name, meta["label"], meta["color"],
                config=config, extra_widgets=[btn_rename, btn_delete],
            )
            card._is_template_card = True
            card._label_text = f"{template.name} {meta['label']} mes modèles"
            card.clicked.connect(lambda t=template.step_type, c=config: self._select(t, c))
            self._templates_layout.addWidget(card)
            self._cards.append(card)
            template_cards.append(card)
        self._sections.append((self._templates_header, template_cards))

    def _on_rename_template(self, template_id: int, current_name: str):
        from database import db_manager as db
        new_name, ok = QInputDialog.getText(self, "Renommer le modèle", "Nom :", text=current_name)
        new_name = new_name.strip()
        if not ok or not new_name:
            return
        new_name = db.unique_step_template_name(new_name, exclude_id=template_id)
        db.rename_step_template(template_id, new_name)
        self.refresh_templates()

    def _on_delete_template(self, template_id: int, name: str):
        from database import db_manager as db
        reply = QMessageBox.question(
            self, "Supprimer", f"Supprimer le modèle « {name} » ?", QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        db.delete_step_template(template_id)
        self.refresh_templates()

    # ── Sélection / recherche ──────────────────

    def _select(self, step_type: str, config: dict):
        self._selected_type = step_type
        self._selected_config = config
        for card in self._cards:
            card.set_selected(card._step_type == step_type and card._config == config)
        self.selection_changed.emit(step_type, config)

    def _on_search_changed(self, text: str):
        needle = text.strip().lower()
        for card in self._cards:
            label = getattr(card, "_label_text", "") or STEP_META.get(card._step_type, {}).get("label", "")
            search_text = f"{label} {step_type_description(card._step_type)}".lower()
            card.setVisible(not needle or needle in search_text)
        for header, cards in self._sections:
            header.setVisible(any(not c.isHidden() for c in cards))

    def _on_return_pressed(self):
        if self._selected_type is None:
            visible = [c for c in self._cards if c.isVisible()]
            if not visible:
                return
            self._select(visible[0]._step_type, visible[0]._config)
        self.insert_requested.emit()

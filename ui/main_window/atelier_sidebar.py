"""
DataScheduler — ui/main_window/atelier_sidebar.py
Colonne de gauche de l'Atelier Pipelines (chantier Atelier Pipelines, écran 2) : liste des
pipelines, repliable — même PATRON que NavRail (ui/main_window/widgets.py : largeurs fixes,
bascule explicite en bas avec chevron réversible, signal collapsed_changed SANS persistance
interne, laissée à la charge de l'appelant — voir AppSettings.atelier_sidebar_collapsed), mais PAS
une sous-classe : NavRail est fermement couplée à être LE rail de navigation de l'appli (branding
KULU, jeu d'icônes fermé ui/icons.py::nav_icon() par item de nav, indices entiers figés vers
MainWindow._stack). Les lignes réutilisent _make_status_badge/_STATUS_BADGE (déjà partagés par
Dashboard/Pipelines/Historique) plutôt qu'une carte riche façon _QueryCard
(ui/main_window/queries_view.py) — pas d'aperçu de contenu à montrer ici, juste une sélection.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame, QScrollArea,
)
from PySide6.QtCore import Qt, QSize, Signal
from ui.styles import COLORS
from .widgets import (
    _icon, HEADER_H, _STATUS_BADGE, _make_status_badge, _TOPOLOGY_STATUS_COLOR_KEY,
)

WIDTH            = 260
WIDTH_COLLAPSED  = 56   # même valeur que NAV_WIDTH_COLLAPSED (widgets.py) — icône/point seul.


class AtelierPipelineRow(QFrame):
    """Une ligne de la sidebar — patron de carte cliquable proche de _QueryCard
    (ui/main_window/queries_view.py), avec un set_collapsed() supplémentaire (jamais nécessaire
    pour l'Atelier SQL, toujours plein écran) : repli vers un simple point de statut coloré, nom
    reporté en infobulle — même convention que NavButton.set_collapsed()."""

    clicked_pipeline = Signal(int)

    def __init__(self, pipeline_id: int, name: str, status: str, is_active: bool):
        super().__init__()
        self.pipeline_id = pipeline_id
        self._name = name
        self.setCursor(Qt.PointingHandCursor)
        # objectName + sélecteur qualifié, même raison que _QueryCard (widgets.py) : un style non
        # qualifié sur un QFrame ancêtre coupe la cascade de GLOBAL_STYLE pour ses descendants.
        self.setObjectName("atelierPipelineRow")

        root = QHBoxLayout(self)
        root.setContentsMargins(10, 8, 10, 8)
        root.setSpacing(8)

        badge_status = "INACTIF" if not is_active else status
        badge_name   = "badge_idle" if not is_active else _STATUS_BADGE.get(status, "badge_idle")
        dot_color    = COLORS["border"] if not is_active else COLORS[_TOPOLOGY_STATUS_COLOR_KEY.get(status, "border")]

        # Repli (icône-seule) : un simple point coloré plutôt que le badge texte complet
        # ("SUCCESS"/"FAILED"...), bien trop large pour WIDTH_COLLAPSED (56px).
        self._dot = QLabel()
        self._dot.setFixedSize(10, 10)
        self._dot.setStyleSheet(f"background: {dot_color}; border-radius: 5px;")
        self._dot.setVisible(False)
        root.addWidget(self._dot)

        self._name_lbl = QLabel(name)
        self._name_lbl.setStyleSheet(
            f"background: transparent; font-size: 12.5px; font-weight: 600; color: {COLORS['text_main']};"
        )
        root.addWidget(self._name_lbl, stretch=1)

        self._badge = _make_status_badge(badge_status, badge_name)
        root.addWidget(self._badge)

        self.set_active(False)

    def set_collapsed(self, collapsed: bool):
        self._name_lbl.setVisible(not collapsed)
        self._badge.setVisible(not collapsed)
        self._dot.setVisible(collapsed)
        self.setToolTip(self._name if collapsed else "")

    def set_active(self, active: bool):
        border = f"2px solid {COLORS['accent']}" if active else "1px solid transparent"
        bg = COLORS["bg_active"] if active else "transparent"
        self.setStyleSheet(
            f"QFrame#atelierPipelineRow {{ background: {bg}; border-left: {border}; border-radius: 4px; }}"
        )

    def mouseReleaseEvent(self, event):
        self.clicked_pipeline.emit(self.pipeline_id)
        super().mouseReleaseEvent(event)


class AtelierSidebar(QWidget):
    """Liste des pipelines, repliable — voir docstring du module. N'importe rien de la
    persistance (AppSettings) : `collapsed_changed`/`pipeline_selected` laissent l'appelant
    (AtelierPipelinesView) décider quoi en faire — ce composant ne connaît que sa propre
    présentation, même séparation de responsabilité que NavRail."""

    collapsed_changed  = Signal(bool)
    pipeline_selected  = Signal(int)

    def __init__(self, initial_collapsed: bool = False):
        super().__init__()
        self._collapsed = initial_collapsed
        self._rows: list[AtelierPipelineRow] = []
        self._active_id: int | None = None
        self.setStyleSheet(f"background-color: {COLORS['bg_panel']};")
        self._build_ui()
        self._apply_collapsed_state()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._title_widget = QWidget()
        self._title_widget.setFixedHeight(HEADER_H)
        self._title_widget.setStyleSheet(
            f"background: {COLORS['bg_panel']}; border-bottom: 1px solid {COLORS['border']};"
        )
        title_layout = QHBoxLayout(self._title_widget)
        title_layout.setContentsMargins(18, 0, 18, 0)
        self._title_lbl = QLabel("Pipelines")
        self._title_lbl.setStyleSheet(
            f"color: {COLORS['text_main']}; font-size: 13px; font-weight: 700; "
            f"background: transparent; border: none;"
        )
        title_layout.addWidget(self._title_lbl)
        layout.addWidget(self._title_widget)

        self._rows_container = QWidget()
        self._rows_layout = QVBoxLayout(self._rows_container)
        self._rows_layout.setContentsMargins(6, 6, 6, 6)
        self._rows_layout.setSpacing(4)
        self._rows_layout.addStretch()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        scroll.setWidget(self._rows_container)
        layout.addWidget(scroll, stretch=1)

        # Repli/dépli — bascule explicite (jamais au survol), même raison que NavRail._toggle_btn
        # (widgets.py) : un mouvement non sollicité sur un outil où l'on reste concentré
        # longtemps sur une vue serait une gêne, pas un service.
        self._toggle_btn = QPushButton()
        self._toggle_btn.setCursor(Qt.PointingHandCursor)
        self._toggle_btn.setFixedHeight(36)
        self._toggle_btn.setIconSize(QSize(13, 13))
        self._toggle_btn.clicked.connect(self.toggle_collapsed)
        layout.addWidget(self._toggle_btn)

    # ── API publique ───────────────────────────

    def set_pipelines(self, pipelines: list):
        """`pipelines` : liste de dicts {"id", "name", "status", "is_active"} — forme simple et
        sans ORM, comme les autres set_data() de ce paquet (ex. PipelineTopologyWidget), pour
        rester trivialement testable."""
        for row in self._rows:
            row.setParent(None)
        self._rows = []
        for p in pipelines:
            row = AtelierPipelineRow(p["id"], p["name"], p["status"], p["is_active"])
            row.set_collapsed(self._collapsed)
            row.set_active(p["id"] == self._active_id)
            row.clicked_pipeline.connect(self.pipeline_selected.emit)
            self._rows_layout.insertWidget(self._rows_layout.count() - 1, row)
            self._rows.append(row)

    def select_pipeline(self, pipeline_id: int | None):
        self._active_id = pipeline_id
        for row in self._rows:
            row.set_active(row.pipeline_id == pipeline_id)

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
        self.setFixedWidth(WIDTH_COLLAPSED if self._collapsed else WIDTH)
        for row in self._rows:
            row.set_collapsed(self._collapsed)

        self._title_lbl.setVisible(not self._collapsed)

        chevron = "fa5s.chevron-right" if self._collapsed else "fa5s.chevron-left"
        self._toggle_btn.setIcon(_icon(chevron, COLORS["text_dim"]))
        self._toggle_btn.setText("" if self._collapsed else "  Réduire")
        self._toggle_btn.setToolTip("Agrandir" if self._collapsed else "")
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

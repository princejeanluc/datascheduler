"""
DataScheduler — ui/dialogs/pipeline_topology_dialog.py
Vue globale des pipelines : tous les pipelines en nœuds reliés par leurs chaînes de déclenchement
(chantier P), dans le même langage visuel que l'aperçu du Dashboard (PipelineTopologyWidget), mais
sans plafond, avec recherche/filtre de statut, zoom et clic-pour-détail. Ouverte depuis le lien
"Voir tous les pipelines" du Dashboard (l'aperçu y est plafonné, voir dashboard_view.py).

Rendu via QGraphicsScene/QGraphicsView plutôt qu'un QWidget peint à la main (comme l'aperçu du
Dashboard) : ce dialogue a besoin de zoom/pan/clic, que Qt offre nativement pour une scène de
QGraphicsItem — patron déjà établi et éprouvé par l'éditeur graphique (chantier 6b,
ui/graph_editor/), pas réinventé ici. La géométrie des nœuds réutilise _layout_topology_nodes()
telle quelle (fonction pure, indépendante de Qt) pour garder la même disposition et le même
mapping de couleurs que l'aperçu du Dashboard.
"""

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPainterPath, QPen, QPolygonF
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QComboBox, QGraphicsObject,
    QGraphicsPathItem, QGraphicsScene, QGraphicsView, QPushButton,
)

from ui.styles import COLORS, DIALOG_STYLE, FONT_UI
from ui.main_window.widgets import (
    PipelineTopologyWidget, _layout_topology_nodes, _TOPOLOGY_STATUS_COLOR_KEY, _status_str,
    _ordered_with_chains, _make_search_input, _make_title, _make_subtitle,
)

_STATUS_FILTER_OPTIONS = [
    ("Tous les statuts", None),
    ("En cours", "RUNNING"),
    ("Succès", "SUCCESS"),
    ("Échec", "FAILED"),
    ("Inactifs", "INACTIVE"),   # cas particulier : filtre sur is_active, pas last_status
]


class PipelineNodeItem(QGraphicsObject):
    """Même rendu visuel qu'un nœud de PipelineTopologyWidget.paintEvent() (rectangle arrondi,
    point en ligne avec le nom, sous-titre résumé d'étapes, bordure interrompue si inactif) mais
    en tant que QGraphicsItem réel — cliquable/sélectionnable nativement, zoomable avec la scène."""

    clicked = Signal(int)

    NODE_W = PipelineTopologyWidget.NODE_W
    NODE_H = PipelineTopologyWidget.NODE_H

    def __init__(self, pipeline, step_summary: str):
        super().__init__()
        self.pipeline = pipeline
        self._step_summary = step_summary
        self.setAcceptHoverEvents(True)
        self.setCursor(Qt.PointingHandCursor)

    def boundingRect(self) -> QRectF:
        return QRectF(0, 0, self.NODE_W, self.NODE_H)

    def _border_color(self) -> str:
        if not self.pipeline.is_active:
            return COLORS["border"]
        status = _status_str(self.pipeline.last_status)
        return COLORS[_TOPOLOGY_STATUS_COLOR_KEY.get(status, "border")]

    def paint(self, painter: QPainter, option, widget=None):
        painter.setRenderHint(QPainter.Antialiasing)
        border_color = self._border_color()

        rect = QRectF(0, 0, self.NODE_W, self.NODE_H)
        painter.setBrush(QBrush(QColor(COLORS["bg_main"])))
        pen = QPen(QColor(border_color), 1.5)
        if not self.pipeline.is_active:
            pen.setStyle(Qt.DashLine)
        if self.isSelected():
            pen.setWidthF(2.5)
        painter.setPen(pen)
        painter.drawRoundedRect(rect, 8, 8)

        name_rect = QRectF(22, 12, self.NODE_W - 32, 18)
        dot_rect = QRectF(10, name_rect.center().y() - 3, 6, 6)
        painter.setBrush(QBrush(QColor(border_color)))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(dot_rect)

        painter.setPen(QColor(COLORS["text_main"]))
        font = QFont(FONT_UI); font.setBold(True); font.setPointSize(9)
        painter.setFont(font)
        name = self.pipeline.name if len(self.pipeline.name) <= 18 else self.pipeline.name[:17] + "…"
        painter.drawText(name_rect, Qt.AlignLeft | Qt.AlignVCenter, name)

        sub = f"{self._step_summary} · inactif" if not self.pipeline.is_active else self._step_summary
        painter.setPen(QColor(COLORS["text_muted"]))
        font2 = QFont(FONT_UI); font2.setPointSize(8)
        painter.setFont(font2)
        painter.drawText(QRectF(22, 34, self.NODE_W - 32, 14), Qt.AlignLeft | Qt.AlignVCenter, sub)

    def mousePressEvent(self, event):
        self.clicked.emit(self.pipeline.id)
        super().mousePressEvent(event)


class PipelineEdgeItem(QGraphicsPathItem):
    """Trait entre le parent et l'enfant d'une même chaîne de déclenchement — même triangle de
    flèche que ui/graph_editor/edge_item.py::EdgeItem pour une direction toujours visible,
    cohérente avec l'autre canevas de l'application."""

    ARROW_LENGTH = 9
    ARROW_HALF_WIDTH = 4.5

    def __init__(self, from_item: PipelineNodeItem, to_item: PipelineNodeItem):
        super().__init__()
        self.setZValue(-1)
        p1 = from_item.pos() + QPointF(from_item.NODE_W, from_item.NODE_H / 2)
        p2 = to_item.pos() + QPointF(0, to_item.NODE_H / 2)
        path = QPainterPath(p1)
        path.lineTo(p2)
        self.setPath(path)
        self._p2 = p2

    def paint(self, painter: QPainter, option, widget=None):
        color = QColor(COLORS["signal"])
        painter.setPen(QPen(color, 1.8))
        painter.drawPath(self.path())

        tip = QPointF(self._p2.x() - 6, self._p2.y())
        base1 = QPointF(tip.x() - self.ARROW_LENGTH, tip.y() - self.ARROW_HALF_WIDTH)
        base2 = QPointF(tip.x() - self.ARROW_LENGTH, tip.y() + self.ARROW_HALF_WIDTH)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(color))
        painter.drawPolygon(QPolygonF([tip, base1, base2]))


class PipelineTopologyView(QGraphicsView):
    """Zoom à la molette — copie conforme de
    ui/graph_editor/graph_view.py::PipelineGraphView (patron déjà établi et éprouvé)."""

    def __init__(self, scene):
        super().__init__(scene)
        self.setRenderHint(QPainter.Antialiasing)
        self.setStyleSheet(f"background-color: {COLORS['bg_main']}; border: none;")

    def wheelEvent(self, event):
        factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        self.scale(factor, factor)


class PipelineTopologyDialog(QDialog):
    """Vue globale des pipelines — voir docstring du module."""

    def __init__(self, parent, pipelines: list):
        super().__init__(parent)
        self._all_pipelines = pipelines
        self.setWindowTitle("Vue globale des pipelines")
        self.setStyleSheet(DIALOG_STYLE)
        self.resize(900, 600)

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 18)
        root.setSpacing(14)

        header = QHBoxLayout()
        title_col = QVBoxLayout(); title_col.setSpacing(2)
        title_col.addWidget(_make_title("Vue globale des pipelines"))
        title_col.addWidget(_make_subtitle("Tous les pipelines et leurs chaînes de déclenchement"))
        header.addLayout(title_col)
        header.addStretch()
        self.cb_status = QComboBox()
        self.cb_status.setFixedHeight(34)
        for label, value in _STATUS_FILTER_OPTIONS:
            self.cb_status.addItem(label, value)
        self.cb_status.currentIndexChanged.connect(self._refresh_scene)
        header.addWidget(self.cb_status)
        self.inp_search = _make_search_input("Rechercher un pipeline…")
        self.inp_search.textChanged.connect(self._refresh_scene)
        header.addWidget(self.inp_search)
        root.addLayout(header)

        self._scene = QGraphicsScene(self)
        self._view = PipelineTopologyView(self._scene)
        root.addWidget(self._view, stretch=1)

        btn_close = QPushButton("Fermer")
        btn_close.setObjectName("secondary")
        btn_close.clicked.connect(self.accept)
        footer = QHBoxLayout()
        footer.addStretch()
        footer.addWidget(btn_close)
        root.addLayout(footer)

        self._refresh_scene()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Repasse à la ligne selon la largeur réelle disponible — redimensionner/maximiser la
        # fenêtre doit profiter de la place supplémentaire plutôt que de garder le layout figé
        # sur la largeur d'ouverture.
        self._refresh_scene()

    def _matching_pipelines(self) -> list:
        needle = self.inp_search.text().strip().lower()
        status_filter = self.cb_status.currentData()
        result = []
        for p in self._all_pipelines:
            if needle and needle not in p.name.lower():
                continue
            if status_filter == "INACTIVE":
                if p.is_active:
                    continue
            elif status_filter and (not p.is_active or _status_str(p.last_status) != status_filter):
                continue
            result.append(p)
        return result

    def _refresh_scene(self, *_args):
        from ui.step_editor.common import STEP_META

        self._scene.clear()
        ordered = _ordered_with_chains(self._matching_pipelines())
        # Largeur réelle de la vue (pas une valeur fixe généreuse) : sinon le layout "étagères"
        # de _layout_topology_nodes() ne retombe jamais à la ligne, et tout s'étale sur une seule
        # rangée qui s'allonge indéfiniment — fastidieux à parcourir avec beaucoup de pipelines
        # (repéré par l'utilisateur). Repasse à la ligne dès que la largeur visible est dépassée.
        max_width = self._view.viewport().width() or self.width() or 860
        positions = _layout_topology_nodes(ordered, max_width=max_width)

        items_by_id = {}
        for p, _depth, x, y, _parent_id in positions:
            step_types = [str(s.step_type).replace("StepType.", "") for s in (p.steps or [])]
            step_summary = " → ".join(
                STEP_META.get(t, {}).get("label", t) for t in step_types
            ) or "—"
            if len(step_summary) > 22:
                step_summary = step_summary[:21] + "…"
            node = PipelineNodeItem(p, step_summary)
            node.setPos(x, y)
            node.clicked.connect(self._on_node_clicked)
            self._scene.addItem(node)
            items_by_id[p.id] = node

        for p, _depth, _x, _y, parent_id in positions:
            if parent_id is None or parent_id not in items_by_id:
                continue
            edge = PipelineEdgeItem(items_by_id[parent_id], items_by_id[p.id])
            self._scene.addItem(edge)

        self._scene.setSceneRect(self._scene.itemsBoundingRect().adjusted(-20, -20, 20, 20))

    def _on_node_clicked(self, pipeline_id: int):
        from database import db_manager as db
        from ui.dialogs import PipelineDetailDialog

        p = db.get_pipeline(pipeline_id)
        if p:
            PipelineDetailDialog(self, pipeline=p).exec()

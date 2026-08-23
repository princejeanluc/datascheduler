"""
DataScheduler — ui/graph_editor/node_item.py
Nœud du canevas : représente une étape (dict complet step_type/label/config/retry_count/
run_always) — le même objet que celui retourné par _open_config_dialog(...).result_step().
"""

from PySide6.QtCore import QPointF, QRectF, Qt, QSize
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QGraphicsItem, QGraphicsObject

from ui.styles import COLORS
from ui.step_editor import STEP_META
from ui.step_editor.common import _icon
from core.steps import get_step_output_ports, is_routing_node

PORT_RADIUS = 6

# Port_name -> (clé de couleur COLORS, étiquette courte) — chantier port d'erreur générique.
# "error" utilise "warning" (ambre), jamais "danger" (déjà pris par "false" sur ConditionStep :
# les réutiliser toutes les deux rendrait 2 points adjacents sur un même nœud indiscernables
# sauf par position). Tout port inconnu (le port normal "output_file", ou tout futur port
# "normal" d'un type d'étape à venir) retombe sur le traitement neutre d'aujourd'hui : pas
# d'étiquette, couleur atténuée — c'est ce qui empêche le port normal d'une étape classique de
# s'afficher par erreur en rouge dès qu'elle gagne un 2e port (le port "error").
_PORT_STYLE = {
    "true":  ("success", "V"),
    "false": ("danger",  "F"),
    "error": ("warning", "!"),
}
_DEFAULT_PORT_STYLE = ("text_dim", "")


def _port_visual(port: str) -> tuple[str, str]:
    """Couleur (clé COLORS) + étiquette courte pour un port de sortie nommé — factoré hors de
    paint() pour être testable sans contexte Qt (même philosophie que EdgeItem._arrow_points())."""
    return _PORT_STYLE.get(port, _DEFAULT_PORT_STYLE)


def _diamond_port_local_pos(width: float, height: float, idx: int, count: int) -> tuple[float, float]:
    """Position LOCALE (avant mapToScene) du idx-ième port de sortie sur un nœud de routage en
    losange — chantier UX éditeur. Sur un rectangle, plusieurs ports se répartissent sur la
    ligne verticale x=WIDTH (le bord droit) ; sur un vrai losange inscrit dans WIDTH×HEIGHT,
    x=WIDTH n'est qu'un seul point (le sommet droit) — y placer plusieurs ports les
    superposerait exactement, les rendant impossibles à cliquer individuellement. Les ports sont
    donc répartis le long des deux arêtes obliques (sommet haut → sommet droit → sommet bas),
    symétriquement autour du sommet droit, exactement comme l'ancienne répartition verticale
    était symétrique autour de HEIGHT/2 — même formule `step * (idx+1)`, appliquée à une
    coordonnée curviligne le long du "V" du losange plutôt qu'à une ligne droite."""
    if count <= 1:
        return (width, height / 2)
    step = 1.0 / (count + 1)
    t = step * (idx + 1)   # 0 < t < 1, position le long du chemin sommet-haut→droit→bas
    if t <= 0.5:
        local_t = t / 0.5
        x = width / 2 + local_t * (width / 2)
        y = local_t * (height / 2)
    else:
        local_t = (t - 0.5) / 0.5
        x = width - local_t * (width / 2)
        y = height / 2 + local_t * (height / 2)
    return (x, y)


class StepNodeItem(QGraphicsObject):
    """
    Rectangle arrondi représentant une étape sur le canevas. Porte le dict `step` complet —
    aucune génération de `_step_key` ici, il vient gratuitement de
    `_open_config_dialog(...).result_step()` (chantier 3), réutilisé tel quel pour créer/éditer
    la configuration d'un nœud.
    """

    WIDTH, HEIGHT = 200, 64

    def __init__(self, step: dict):
        super().__init__()
        self.step = step
        self._is_executing = False
        self.setFlags(
            QGraphicsItem.ItemIsMovable
            | QGraphicsItem.ItemIsSelectable
            | QGraphicsItem.ItemSendsGeometryChanges
        )
        self.setZValue(1)

    def set_executing(self, executing: bool) -> None:
        """Traçage lumineux (chantier identité visuelle) : surligne ce nœud comme étant
        l'étape en cours d'une exécution réelle. Bordure signal statique — pas d'animation,
        distincte de la sélection (même épaisseur, couleur différente)."""
        if executing != self._is_executing:
            self._is_executing = executing
            self.update()

    # ── Identité ──────────────────────────────

    @property
    def step_key(self) -> str | None:
        return (self.step.get("config") or {}).get("_step_key")

    @property
    def output_ports(self) -> tuple[str, ...]:
        return get_step_output_ports(self.step.get("step_type", ""))

    # ── Géométrie des ports (coordonnées de scène) ──

    def input_port_pos(self) -> QPointF:
        return self.mapToScene(QPointF(0, self.HEIGHT / 2))

    @property
    def is_routing_node(self) -> bool:
        return is_routing_node(self.step.get("step_type", ""))

    def output_port_pos(self, port: str) -> QPointF:
        ports = self.output_ports
        idx = ports.index(port) if port in ports else 0
        if self.is_routing_node:
            x, y = _diamond_port_local_pos(self.WIDTH, self.HEIGHT, idx, len(ports))
        elif len(ports) <= 1:
            x, y = self.WIDTH, self.HEIGHT / 2
        else:
            step = self.HEIGHT / (len(ports) + 1)
            x, y = self.WIDTH, step * (idx + 1)
        return self.mapToScene(QPointF(x, y))

    # ── Qt ────────────────────────────────────

    def boundingRect(self) -> QRectF:
        return QRectF(-PORT_RADIUS, -PORT_RADIUS,
                      self.WIDTH + 2 * PORT_RADIUS, self.HEIGHT + 2 * PORT_RADIUS)

    def paint(self, painter, option, widget=None):
        step_type = self.step.get("step_type", "")
        meta = STEP_META.get(step_type, {"label": step_type, "color": COLORS["accent"]})
        routing = self.is_routing_node

        path = QPainterPath()
        if routing:
            # Losange inscrit dans WIDTH×HEIGHT (chantier UX éditeur) — distingue un nœud de
            # routage/jonction (CONDITION, futur GATEWAY) d'une étape normale au premier coup
            # d'œil, sans avoir à lire le texte. boundingRect() reste inchangé (le rectangle
            # englobant reste une boîte de collision valide, juste plus large que la forme
            # peinte).
            path.moveTo(self.WIDTH / 2, 0)
            path.lineTo(self.WIDTH, self.HEIGHT / 2)
            path.lineTo(self.WIDTH / 2, self.HEIGHT)
            path.lineTo(0, self.HEIGHT / 2)
            path.closeSubpath()
        else:
            rect = QRectF(0, 0, self.WIDTH, self.HEIGHT)
            path.addRoundedRect(rect, 8, 8)

        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(QBrush(QColor(COLORS["bg_card"])))
        border_color = QColor(COLORS["signal"]) if self._is_executing else QColor(meta["color"])
        pen = QPen(border_color, 3 if (self.isSelected() or self._is_executing) else 1.5)
        painter.setPen(pen)
        painter.drawPath(path)

        painter.setPen(QColor(meta["color"]))
        font = QFont(); font.setBold(True); font.setPointSize(9)
        painter.setFont(font)
        painter.drawText(QRectF(10, 6, self.WIDTH - 40, 18), Qt.AlignLeft | Qt.AlignVCenter,
                          meta["label"])

        type_icon = _icon(meta.get("icon", "fa5s.circle"), meta["color"])
        if type_icon:
            painter.drawPixmap(self.WIDTH - 24, 6, type_icon.pixmap(QSize(16, 16)))

        user_label = self.step.get("label") or ""
        if user_label:
            painter.setPen(QColor(COLORS["text_main"]))
            font.setBold(False); font.setPointSize(8)
            painter.setFont(font)
            painter.drawText(QRectF(10, 26, self.WIDTH - 20, 18), Qt.AlignLeft | Qt.AlignVCenter,
                              user_label)

        # Port d'entrée (toujours dessiné, connecté ou non).
        painter.setBrush(QBrush(QColor(COLORS["text_dim"])))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(QPointF(0, self.HEIGHT / 2), PORT_RADIUS, PORT_RADIUS)

        # Port(s) de sortie — même géométrie que output_port_pos() (coordonnées locales ici,
        # scène là-bas), pour que le point dessiné coïncide toujours avec la zone cliquable.
        ports = self.output_ports
        for i, port in enumerate(ports):
            if routing:
                x, y = _diamond_port_local_pos(self.WIDTH, self.HEIGHT, i, len(ports))
            elif len(ports) <= 1:
                x, y = self.WIDTH, self.HEIGHT / 2
            else:
                step = self.HEIGHT / (len(ports) + 1)
                x, y = self.WIDTH, step * (i + 1)
            color_key, label = _port_visual(port)
            color = COLORS[color_key]
            painter.setBrush(QBrush(QColor(color)))
            painter.drawEllipse(QPointF(x, y), PORT_RADIUS, PORT_RADIUS)
            if label:
                painter.setPen(QColor(color))
                painter.drawText(QRectF(x - 22, y - 9, 16, 18),
                                  Qt.AlignRight | Qt.AlignVCenter, label)

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionHasChanged and self.scene():
            self.scene().notify_node_moved(self)
        return super().itemChange(change, value)

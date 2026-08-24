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
# Marge supplémentaire sous le port "error" (au-delà de PORT_RADIUS) pour son étiquette "!",
# dessinée en dessous du point plutôt qu'à côté — voir boundingRect()/paint().
_ERROR_LABEL_MARGIN = 16

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
    """Position LOCALE (avant mapToScene) du idx-ième port de sortie NORMAL (jamais "error", voir
    _error_port_local_pos ci-dessous) sur un nœud de routage en losange — chantier UX éditeur.
    Sur un rectangle, plusieurs ports se répartissent sur la ligne verticale x=WIDTH (le bord
    droit) ; sur un vrai losange inscrit dans WIDTH×HEIGHT, x=WIDTH n'est qu'un seul point (le
    sommet droit) — y placer plusieurs ports les superposerait exactement, les rendant
    impossibles à cliquer individuellement. Les ports sont donc répartis le long des deux arêtes
    obliques (sommet haut → sommet droit → sommet bas), symétriquement autour du sommet droit,
    exactement comme l'ancienne répartition verticale était symétrique autour de HEIGHT/2 — même
    formule `step * (idx+1)`, appliquée à une coordonnée curviligne le long du "V" du losange
    plutôt qu'à une ligne droite."""
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


def _tinted_bg(base: QColor, accent: QColor, ratio: float = 0.13) -> QColor:
    """Interpole linéairement, canal par canal, de `base` vers `accent` — chantier identité
    visuelle : un fond de carte uniforme (bg_card) pour tout type de nœud se détachait à peine
    du fond du canevas (bg_main, un ton à peine plus sombre) et ne différenciait pas les types
    entre eux au premier coup d'œil. `ratio=0` retourne `base` inchangé, `ratio=1` retourne
    `accent` inchangé — QColor n'a pas d'équivalent CSS color-mix(), fonction pure testable sans
    contexte Qt (même philosophie que _port_visual)."""
    ratio = max(0.0, min(1.0, ratio))
    r = base.red()   + (accent.red()   - base.red())   * ratio
    g = base.green() + (accent.green() - base.green()) * ratio
    b = base.blue()  + (accent.blue()  - base.blue())  * ratio
    return QColor(round(r), round(g), round(b))


def _error_port_local_pos(width: float, height: float) -> tuple[float, float]:
    """Position LOCALE du port "error" — chantier placement du port d'erreur. Toujours au
    sommet/bord BAS (`width/2, height`), quelle que soit la forme (losange ou rectangle) et quel
    que soit le nombre d'autres ports : le sommet/bord DROIT reste exclusivement réservé au(x)
    port(s) normal(aux), celui qu'on suit des yeux dans le sens de lecture. Sans cette séparation,
    un nœud à seulement 2 ports (normal + error — le cas de la vaste majorité des types d'étape,
    et des deux passerelles GATEWAY_PARALLEL/GATEWAY_JOIN) plaçait les deux via la même
    répartition générique, les faisant atterrir l'un contre l'autre près du sommet droit d'un
    losange (bug constaté par capture d'écran) — jamais un problème sur un rectangle (l'axe X y
    est fixe), mais bien un sur un losange (l'axe X y varie avec Y). Aucun précédent BPMN/Dataiku
    à copier ici — la gestion d'erreur générique par port est propre à cette app."""
    return (width / 2, height)


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
        self._is_executing  = False
        self._is_failed     = False
        self._is_search_hit = False
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

    def set_failed(self, failed: bool) -> None:
        """Surlignage "échec" (chantier UX éditeur, Lot 1, B1 — lien "Voir dans le graphe" depuis
        une ligne d'historique en échec). État JUMEAU de set_executing(), jamais une
        réutilisation : celui-ci peint en rouge (COLORS["danger"]), pas en bleu "signal" — un
        nœud surligné ainsi est terminé/en échec, pas en train de tourner."""
        if failed != self._is_failed:
            self._is_failed = failed
            self.update()

    def set_search_hit(self, hit: bool) -> None:
        """Surlignage "résultat de recherche" (chantier UX éditeur, Lot 2, B3). État JUMEAU de
        set_executing()/set_failed(), jamais une réutilisation : couleur dédiée
        COLORS["signal_pale"], priorité la plus basse dans paint() — un nœud en cours
        d'exécution ou en échec garde toujours la priorité visuelle sur un simple résultat de
        recherche."""
        if hit != self._is_search_hit:
            self._is_search_hit = hit
            self.update()

    def search_text(self) -> str:
        """Texte de correspondance pour B3 — exactement les deux libellés déjà peints par
        paint() (type + libellé utilisateur), pour que "ce qu'on voit" soit "ce qui se
        cherche"."""
        meta = STEP_META.get(self.step.get("step_type", ""), {"label": self.step.get("step_type", "")})
        return f"{meta['label']} {self.step.get('label') or ''}".lower()

    @property
    def is_executing(self) -> bool:
        return self._is_executing

    @property
    def is_failed(self) -> bool:
        return self._is_failed

    @property
    def is_search_hit(self) -> bool:
        return self._is_search_hit

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
        if port == "error":
            x, y = _error_port_local_pos(self.WIDTH, self.HEIGHT)
            return self.mapToScene(QPointF(x, y))

        normal_ports = [p for p in self.output_ports if p != "error"]
        idx = normal_ports.index(port) if port in normal_ports else 0
        count = len(normal_ports)
        if self.is_routing_node:
            x, y = _diamond_port_local_pos(self.WIDTH, self.HEIGHT, idx, count)
        elif count <= 1:
            x, y = self.WIDTH, self.HEIGHT / 2
        else:
            step = self.HEIGHT / (count + 1)
            x, y = self.WIDTH, step * (idx + 1)
        return self.mapToScene(QPointF(x, y))

    # ── Qt ────────────────────────────────────

    def boundingRect(self) -> QRectF:
        # Marge basse élargie (au-delà du simple PORT_RADIUS des autres côtés) : le port "error"
        # est désormais toujours au bord/sommet bas (_error_port_local_pos), avec son étiquette
        # "!" dessinée EN DESSOUS du point plutôt qu'à côté (voir paint()) — sans cette marge
        # supplémentaire, l'étiquette déborderait de la zone repeinte par Qt.
        return QRectF(-PORT_RADIUS, -PORT_RADIUS,
                      self.WIDTH + 2 * PORT_RADIUS, self.HEIGHT + PORT_RADIUS + _ERROR_LABEL_MARGIN)

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
        # Fond teinté par la couleur du type (chantier identité visuelle) — une couche de fond
        # discrète en plus, jamais un remplacement de la bordure épaisse colorée qui reste le
        # signal prioritaire pour _is_failed/_is_executing/_is_search_hit (inchangés ci-dessous).
        painter.setBrush(QBrush(_tinted_bg(QColor(COLORS["bg_card"]), QColor(meta["color"]))))
        if self._is_failed:
            border_color = QColor(COLORS["danger"])
        elif self._is_executing:
            border_color = QColor(COLORS["signal"])
        elif self._is_search_hit:
            border_color = QColor(COLORS["signal_pale"])
        else:
            border_color = QColor(meta["color"])
        pen = QPen(border_color, 3 if (self.isSelected() or self._is_executing or self._is_failed
                                        or self._is_search_hit) else 1.5)
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
        # "error" est toujours à part, au bord/sommet bas (_error_port_local_pos) — jamais mêlé
        # à la répartition des ports normaux, voir son commentaire complet.
        normal_ports = [p for p in self.output_ports if p != "error"]
        for i, port in enumerate(normal_ports):
            if routing:
                x, y = _diamond_port_local_pos(self.WIDTH, self.HEIGHT, i, len(normal_ports))
            elif len(normal_ports) <= 1:
                x, y = self.WIDTH, self.HEIGHT / 2
            else:
                step = self.HEIGHT / (len(normal_ports) + 1)
                x, y = self.WIDTH, step * (i + 1)
            color_key, label = _port_visual(port)
            color = COLORS[color_key]
            painter.setBrush(QBrush(QColor(color)))
            painter.drawEllipse(QPointF(x, y), PORT_RADIUS, PORT_RADIUS)
            if label:
                painter.setPen(QColor(color))
                painter.drawText(QRectF(x - 22, y - 9, 16, 18),
                                  Qt.AlignRight | Qt.AlignVCenter, label)

        if "error" in self.output_ports:
            ex, ey = _error_port_local_pos(self.WIDTH, self.HEIGHT)
            color_key, label = _port_visual("error")
            color = COLORS[color_key]
            painter.setBrush(QBrush(QColor(color)))
            painter.drawEllipse(QPointF(ex, ey), PORT_RADIUS, PORT_RADIUS)
            if label:
                painter.setPen(QColor(color))
                painter.drawText(QRectF(ex - 8, ey + 4, 16, 14), Qt.AlignCenter, label)

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionHasChanged and self.scene():
            self.scene().notify_node_moved(self)
        return super().itemChange(change, value)

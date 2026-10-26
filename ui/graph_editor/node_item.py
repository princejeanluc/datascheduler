"""
DataScheduler — ui/graph_editor/node_item.py
Nœud du canevas : représente une étape (dict complet step_type/label/config/retry_count/
run_always) — le même objet que celui retourné par _open_config_dialog(...).result_step().
"""

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QGraphicsItem, QGraphicsObject

from ui.styles import COLORS
from ui.step_editor import STEP_META
from core.steps import get_step_output_ports, is_routing_node, get_join_mode
from .node_facts import (
    compute_node_facts, extract_var_references_from_config, compute_written_variables,
    engine_label,
)

PORT_RADIUS = 6
# Marge supplémentaire sous le port "error" (au-delà de PORT_RADIUS) pour son étiquette "!",
# dessinée en dessous du point plutôt qu'à côté — voir boundingRect()/paint().
_ERROR_LABEL_MARGIN = 16

# Chevron de dépli/repli (chantier relooking des nœuds) — carré cliquable, haut-droite de la
# carte pour un nœud normal, à côté de la légende sous le losange pour un nœud de routage.
_CHEVRON_SIZE = 14
# Tolérance de clic au-delà du carré nu — même confort que les ports (PORT_RADIUS=6 déjà
# généreux), un carré de 14px nu serait frustrant à viser précisément.
_CHEVRON_HIT_PADDING = 4


def _chevron_rect(width: float, height: float, routing: bool) -> tuple[float, float, float, float]:
    """Rectangle LOCAL (x, y, w, h) du chevron ▾/▸ — géométrie pure, testable sans Qt (même
    philosophie que _diamond_port_local_pos/_error_port_local_pos). Même coin haut-droite de la
    boîte englobante pour un nœud normal ET un nœud de routage (refonte, lot A-Atelier-grammaire,
    A3) : depuis que le nom d'un losange est peint AU-DESSUS de lui plutôt qu'en dessous, ce coin
    est un espace libre dans les deux cas — plus besoin d'une formule distincte accrochée à
    l'ancienne légende sous le losange."""
    size = _CHEVRON_SIZE
    return (width - 8 - size, 8, size, size)

# Port_name -> (clé de couleur COLORS, étiquette courte) — chantier port d'erreur générique.
# "error" utilise "warning" (ambre), jamais "danger" (déjà pris par "false" sur ConditionStep :
# les réutiliser toutes les deux rendrait 2 points adjacents sur un même nœud indiscernables
# sauf par position). Tout port inconnu (le port normal "output_file", ou tout futur port
# "normal" d'un type d'étape à venir) retombe sur le traitement neutre d'aujourd'hui : pas
# d'étiquette, couleur atténuée — c'est ce qui empêche le port normal d'une étape classique de
# s'afficher par erreur en rouge dès qu'elle gagne un 2e port (le port "error").
_PORT_STYLE = {
    # true/false n'ont plus d'étiquette au POINT depuis le lot A-Atelier-grammaire (A5) : le mot
    # entier ("vrai"/"faux") est désormais porté par la liaison elle-même (edge_item.py), pas
    # besoin de la répéter en lettre seule ici (les deux cerclaient le même point, redondant et
    # encombré sur un losange qui concentre déjà 2-3 ports proches de son sommet droit).
    "true":  ("success", ""),
    "false": ("danger",  ""),
    "error": ("warning", "!"),
}
_DEFAULT_PORT_STYLE = ("text_dim", "")


def _port_visual(port: str) -> tuple[str, str]:
    """Couleur (clé COLORS) + étiquette courte pour un port de sortie nommé — factoré hors de
    paint() pour être testable sans contexte Qt (même philosophie que EdgeItem._arrow_points())."""
    return _PORT_STYLE.get(port, _DEFAULT_PORT_STYLE)


# Symbole dessiné au centre du losange (refonte, lot A-Atelier-grammaire, A3) — remplace le badge
# d'icône qtawesome utilisé pour tout autre nœud : fonction pure, testable sans Qt (même
# philosophie que _port_visual/_tinted_bg).
def _routing_symbol(step_type: str, config: dict) -> str:
    if step_type == "CONDITION":
        return "?"
    if step_type == "GATEWAY_PARALLEL":
        return "+"
    if step_type == "GATEWAY_JOIN":
        return "ET" if get_join_mode(step_type, config) == "AND" else "OU"
    return "?"


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


# Coins arrondis du losange (correctif, relevé en comparant une capture à la maquette Grammaire
# — la maquette montre un losange aux coins nettement arrondis, jamais des pointes nettes comme
# le tracé d'origine moveTo/lineTo). Chaque sommet est remplacé par une courbe quadratique entre
# deux points reculés le long des arêtes adjacentes, plutôt qu'un angle vif.
_DIAMOND_CORNER_FRAC = 0.22


def _rounded_diamond_path(width: float, height: float, corner_frac: float = _DIAMOND_CORNER_FRAC) -> QPainterPath:
    top    = QPointF(width / 2, 0)
    right  = QPointF(width, height / 2)
    bottom = QPointF(width / 2, height)
    left   = QPointF(0, height / 2)
    verts = [top, right, bottom, left]

    def _lerp(a: QPointF, b: QPointF, t: float) -> QPointF:
        return QPointF(a.x() + (b.x() - a.x()) * t, a.y() + (b.y() - a.y()) * t)

    path = QPainterPath()
    n = len(verts)
    start = _lerp(verts[0], verts[-1], corner_frac)
    path.moveTo(start)
    for i in range(n):
        v = verts[i]
        nxt = verts[(i + 1) % n]
        prev = verts[(i - 1) % n]
        into = _lerp(v, prev, corner_frac)
        out = _lerp(v, nxt, corner_frac)
        path.lineTo(into)
        path.quadTo(v, out)
    path.closeSubpath()
    return path


# Opacité d'un nœud selon l'état de sélection du canevas (A4) — fonction pure, testable sans Qt
# (même philosophie que _port_visual/_tinted_bg). Un nœud ne s'atténue jamais lui-même, même
# sélectionné ; tout autre nœud s'atténue dès qu'une sélection existe quelque part.
_DIMMED_OPACITY = 0.4


def _node_opacity(is_self_selected: bool, any_selected: bool) -> float:
    return _DIMMED_OPACITY if (any_selected and not is_self_selected) else 1.0


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


# Nom du losange AU-DESSUS de lui (refonte, lot A-Atelier-grammaire, A3 — il était en dessous
# avant ce chantier). Une seule ligne (jamais de libellé de type en plus : la maquette Grammaire
# n'en montre qu'une, contrairement à la carte d'une étape normale qui en garde deux) — hauteur
# réservée au-dessus de la boîte englobante. Voir boundingRect()/paint().
_ROUTING_LABEL_ABOVE_H = 18


# Hiérarchie de texte (chantier relooking des nœuds) : le libellé UTILISATEUR devient le texte
# PRINCIPAL (gras, text_main) ; le libellé de TYPE (secondaire) sert de repli si l'utilisateur
# n'en a pas défini. Depuis le lot A-Atelier-grammaire (A1), paint() n'affiche plus `secondary`
# séparément : le surtitre "FAMILLE · MOTEUR" et le sous-titre "objet" portent désormais le
# contexte de type — la fonction garde sa forme (tuple) pour ne pas changer sa signature sans
# raison, `secondary` reste calculé mais ignoré par l'appelant non-routage.
def _node_text_hierarchy(step: dict, meta: dict) -> tuple[str, str | None]:
    """Fonction pure, testable sans Qt (même philosophie que _port_visual/_tinted_bg)."""
    user_label = step.get("label") or ""
    primary = user_label or meta["label"]
    secondary = meta["label"] if user_label else None
    return primary, secondary


# Contenu déplié (chantier relooking des nœuds) : hauteur additionnelle de boundingRect() selon
# le nombre de faits/puces de variable — fonction pure, testable sans Qt.
_FACT_LINE_H         = 16
_VAR_BULLET_LINE_H   = 15
_EXPANDED_TOP_PAD    = 8
_EXPANDED_BOTTOM_PAD = 6


def _expanded_content_height(num_facts: int, num_read_vars: int, num_written_vars: int) -> float:
    if num_facts == 0 and num_read_vars == 0 and num_written_vars == 0:
        return _EXPANDED_TOP_PAD + _FACT_LINE_H + _EXPANDED_BOTTOM_PAD   # placeholder "Aucun détail…"
    return (_EXPANDED_TOP_PAD
            + num_facts * _FACT_LINE_H
            + (num_read_vars + num_written_vars) * _VAR_BULLET_LINE_H
            + _EXPANDED_BOTTOM_PAD)


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
        self._dragging      = False
        # État déplié/replié (chantier relooking des nœuds) — purement ÉPHÉMÈRE, jamais persisté
        # (aucun précédent d'état UI par nœud ailleurs dans ce projet, vérifié) : réinitialisé à
        # replié à chaque chargement du graphe. _profile_names : voir set_profile_names() plus
        # bas — résolution des noms de profil pour le contenu déplié, jamais de requête DB ici.
        self._expanded = False
        self._profile_names: dict = {}
        # C9 (Atelier-echec) : ligne de statut du run affichée à la place de l'objet principal
        # habituel (sous-titre, 3e ligne) — jamais en plus, voir set_run_status(). card_state :
        # None (normal), "not_executed" (bordure pointillée, texte atténué), "error_triggered"
        # (bordure/fond ambre) — FAILED reste exclusivement couvert par set_failed(), jamais
        # dupliqué ici.
        self._run_status_text: str | None = None
        self._run_status_color_key: str | None = None
        self._run_card_state: str | None = None
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

    def set_run_status(self, text: str | None, color_key: str | None, card_state: str | None = None) -> None:
        """C9 (Atelier-echec) : affiche le résultat réel d'un run passé sur ce nœud. `text`/
        `color_key` remplacent la 3e ligne (objet principal) — jamais une ligne en plus, même
        hauteur de carte qu'en édition. `card_state` : voir docstring de __init__. `None, None,
        None` efface (retour à l'apparence d'édition normale, ex. en quittant la vue d'un run)."""
        new = (text, color_key, card_state)
        old = (self._run_status_text, self._run_status_color_key, self._run_card_state)
        if new != old:
            self._run_status_text, self._run_status_color_key, self._run_card_state = new
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

    def set_movable(self, movable: bool) -> None:
        """C9 (Atelier-echec) : un run passé ne se repositionne pas en le glissant — jamais
        appelé en édition normale."""
        self.setFlag(QGraphicsItem.ItemIsMovable, movable)

    def set_expanded(self, expanded: bool) -> None:
        """Déplie/replie le panneau de détail de ce nœud (chantier relooking des nœuds) — seul
        mutateur d'état de cette classe qui change la GÉOMÉTRIE (boundingRect() s'agrandit),
        d'où prepareGeometryChange() avant la mutation : même patron que le seul autre précédent
        de la base, ZoneItem.mouseMoveEvent() (ui/graph_editor/zone_item.py)."""
        if expanded != self._expanded:
            self.prepareGeometryChange()
            self._expanded = expanded
            self.update()

    def toggle_expanded(self) -> None:
        self.set_expanded(not self._expanded)

    def set_profile_names(self, profile_names: dict) -> None:
        """Noms de profil résolus (ftp/smtp/ssh/kerberos/elevation/oracle/sql_query/db) pour le
        contenu déplié — construits par l'appelant (PipelineGraphEditorWidget) à partir de
        listes déjà chargées en mémoire, jamais par une requête DB déclenchée ici. Ne change
        jamais le NOMBRE de faits affichés (un ID est juste remplacé par un nom dans le texte),
        donc pas de prepareGeometryChange() — update() suffit."""
        self._profile_names = profile_names or {}
        self.update()

    @property
    def is_expanded(self) -> bool:
        return self._expanded

    def _resolve_step_label(self, step_key: str | None) -> str | None:
        """Libellé lisible du nœud amont référencé par `step_key` (reads_from_step_key /
        artifact_source_step_key) — pour le fait "Source"/"Artefact propagé" du contenu déplié.
        Même règle de repli que search_text() : libellé utilisateur sinon libellé de type. None
        si introuvable (nœud supprimé entre-temps, ou pas encore attaché à une scène)."""
        if not step_key or not self.scene():
            return None
        node = self.scene().nodes.get(step_key)
        if not node:
            return None
        label = node.step.get("label") or ""
        if label:
            return label
        meta = STEP_META.get(node.step.get("step_type", ""), {})
        return meta.get("label", node.step.get("step_type", ""))

    def _facts_and_vars(self):
        """Faits clés + variables lues/écrites de CE nœud — helper commun à boundingRect() et
        paint() (jamais calculé deux fois différemment). Pas de cache : opérations pures bon
        marché (pas de DB, pas de Qt), même tolérance de volumétrie que _layout_topology_nodes
        ailleurs dans ce projet."""
        step_type = self.step.get("step_type", "")
        config = self.step.get("config") or {}
        source_key = config.get("reads_from_step_key") or config.get("artifact_source_step_key")
        source_label = self._resolve_step_label(source_key)
        facts = compute_node_facts(step_type, config, self._profile_names, source_label=source_label)
        read_vars = extract_var_references_from_config(config)
        written_vars = compute_written_variables(step_type, config)
        return facts, read_vars, written_vars

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
        # supplémentaire, l'étiquette déborderait de la zone repeinte par Qt. Même marge pour un
        # nœud de routage désormais (refonte, lot A-Atelier-grammaire, A3) : son nom vit
        # au-dessus du losange, pas en dessous — voir top_margin ci-dessous.
        bottom_margin = _ERROR_LABEL_MARGIN
        top_margin = PORT_RADIUS + (_ROUTING_LABEL_ABOVE_H if self.is_routing_node else 0)
        # Contenu déplié (chantier relooking des nœuds) : hauteur additionnelle sous la marge
        # basse déjà existante — jamais de cache, voir _facts_and_vars().
        extra = 0.0
        if self._expanded:
            facts, read_vars, written_vars = self._facts_and_vars()
            extra = _expanded_content_height(len(facts), len(read_vars), len(written_vars))
        return QRectF(-PORT_RADIUS, -top_margin,
                      self.WIDTH + 2 * PORT_RADIUS, top_margin + self.HEIGHT + bottom_margin + extra)

    def paint(self, painter, option, widget=None):
        step_type = self.step.get("step_type", "")
        meta = STEP_META.get(step_type, {"label": step_type, "color": COLORS["accent"]})
        routing = self.is_routing_node

        if routing:
            # Losange inscrit dans WIDTH×HEIGHT, coins arrondis (correctif — voir
            # _rounded_diamond_path) — distingue un nœud de routage/jonction d'une étape normale
            # au premier coup d'œil, sans avoir à lire le texte. boundingRect() reste inchangé
            # (le rectangle englobant reste une boîte de collision valide, juste plus large que
            # la forme peinte).
            path = _rounded_diamond_path(self.WIDTH, self.HEIGHT)
        else:
            path = QPainterPath()
            # Coins 12px (chantier relooking des nœuds, "carte plus aérée" — maquette
            # approuvée) : avant, 8px.
            rect = QRectF(0, 0, self.WIDTH, self.HEIGHT)
            path.addRoundedRect(rect, 12, 12)

        painter.setRenderHint(QPainter.Antialiasing)

        # Sélection (A4) : bordure accent, et tout AUTRE nœud atténué tant qu'une sélection
        # existe quelque part sur le canevas — jamais l'inverse (un nœud sélectionné ne s'atténue
        # jamais lui-même). Opacité globale du paint() le temps de ce nœud, remise à 1 en sortie.
        scene = self.scene()
        any_selected = bool(scene.selectedItems()) if scene else False
        painter.setOpacity(_node_opacity(self.isSelected(), any_selected))

        # C9 (Atelier-echec) : deux états supplémentaires qui ne sont ni une sélection ni un échec
        # (déjà couvert par set_failed(), inchangé). "not_executed" : carte jamais atteinte par ce
        # run — fond transparent (pas de teinte, contrairement à une étape normale), bordure
        # pointillée border_strong. "error_triggered" : étape atteinte PAR le port d'erreur et
        # réussie — bordure/fond teintés warning au lieu de la couleur de famille habituelle.
        not_executed = self._run_card_state == "not_executed"
        error_triggered = self._run_card_state == "error_triggered"

        # Fond teinté par la couleur du type (chantier identité visuelle) — une couche de fond
        # discrète en plus, jamais un remplacement de la bordure épaisse colorée qui reste le
        # signal prioritaire pour _is_failed/_is_executing/_is_search_hit (inchangés ci-dessous).
        if not_executed:
            painter.setBrush(Qt.NoBrush)
        elif error_triggered:
            painter.setBrush(QBrush(_tinted_bg(QColor(COLORS["bg_card"]), QColor(COLORS["warning"]))))
        else:
            painter.setBrush(QBrush(_tinted_bg(QColor(COLORS["bg_card"]), QColor(meta["color"]))))
        if self._is_failed:
            border_color = QColor(COLORS["danger"])
        elif error_triggered:
            border_color = QColor(COLORS["warning"])
        elif not_executed:
            border_color = QColor(COLORS["border_strong"])
        elif self._is_executing:
            border_color = QColor(COLORS["signal"])
        elif self.isSelected():
            border_color = QColor(COLORS["accent"])
        elif self._is_search_hit:
            border_color = QColor(COLORS["signal_pale"])
        else:
            border_color = QColor(meta["color"])
        pen = QPen(border_color, 3 if (self.isSelected() or self._is_executing or self._is_failed
                                        or self._is_search_hit or error_triggered) else 1.5)
        if not_executed:
            pen.setStyle(Qt.DashLine)
        painter.setPen(pen)
        painter.drawPath(path)

        primary_text, _ = _node_text_hierarchy(self.step, meta)

        if routing:
            # Symbole au centre du losange (refonte, lot A-Atelier-grammaire, A3) — remplace
            # l'icône qtawesome utilisée par tout autre nœud : "?" (Aiguillage), "+" (Parallèle),
            # "ET"/"OU" (Jonction, selon join_mode).
            # Taille proportionnelle à la forme (correctif — trop petit et non centré avant),
            # pas un point fixe arbitraire : un glyphe seul ("?", "+") plus grand qu'un sigle à
            # 2 lettres ("ET"/"OU"), pour que les deux occupent une place visuelle comparable.
            symbol = _routing_symbol(step_type, self.step.get("config") or {})
            painter.setPen(QColor("#ffffff"))
            font = QFont(); font.setBold(True); font.setPointSize(15 if len(symbol) == 1 else 12)
            painter.setFont(font)
            painter.drawText(QRectF(0, 0, self.WIDTH, self.HEIGHT), Qt.AlignCenter, symbol)

            # Nom AU-DESSUS du losange (A3 — il était en dessous avant ce chantier) : une seule
            # ligne, le libellé utilisateur s'il existe sinon le libellé de type. Atténué si
            # jamais atteint par le run consulté (C9) — même traitement que le titre d'une carte
            # normale ci-dessous.
            painter.setPen(QColor(COLORS["border_strong"] if not_executed else COLORS["text_main"]))
            font = QFont(); font.setBold(True); font.setPointSize(9)
            painter.setFont(font)
            painter.drawText(QRectF(-20, -_ROUTING_LABEL_ABOVE_H, self.WIDTH + 40, _ROUTING_LABEL_ABOVE_H),
                              Qt.AlignCenter, primary_text)
            self._paint_chevron(painter, routing)
        else:
            # Point de famille (refonte, lot A-Atelier-grammaire, A1) — remplace le badge
            # d'icône : une pastille pleine suffit, la couleur dit déjà la famille. Omis si
            # jamais atteint par le run consulté (C9) — la maquette ne montre aucun point sur une
            # carte "non exécutée", pas seulement une couleur atténuée.
            if not not_executed:
                dot_x, dot_y = 10, 11
                painter.setBrush(QBrush(QColor(meta["color"])))
                painter.setPen(Qt.NoPen)
                painter.drawEllipse(QPointF(dot_x, dot_y), 4, 4)

            # Surtitre Mono "FAMILLE · MOTEUR" (A1) — couleur de famille, comme le point ; gris
            # atténué si jamais atteint par le run consulté (C9).
            engine = engine_label(step_type, self.step.get("config") or {}, self._profile_names)
            eyebrow = f"{meta.get('family', '').upper()} · {engine}" if engine else meta.get("family", "").upper()
            painter.setPen(QColor(COLORS["text_dim"] if not_executed else meta["color"]))
            font = QFont("JetBrains Mono"); font.setPointSize(6); font.setBold(True)
            painter.setFont(font)
            painter.drawText(QRectF(18, 3, self.WIDTH - 28, 11),
                              Qt.AlignLeft | Qt.AlignVCenter, eyebrow)

            # Titre (A1) — libellé utilisateur, ou libellé de type à défaut ; atténué si jamais
            # atteint par le run consulté (C9).
            painter.setPen(QColor(COLORS["text_dim"] if not_executed else COLORS["text_main"]))
            font = QFont(); font.setBold(True); font.setPointSize(9)
            painter.setFont(font)
            painter.drawText(QRectF(10, 15, self.WIDTH - 20, 18),
                              Qt.AlignLeft | Qt.AlignVCenter, primary_text)

            # Sous-titre (A1) : objet principal (premier fait) en édition normale — REMPLACÉ par
            # le résultat du run consulté quand set_run_status() en a posé un (C9, jamais les
            # deux en même temps, même hauteur de carte).
            if self._run_status_text:
                painter.setPen(QColor(COLORS[self._run_status_color_key]))
                font = QFont("JetBrains Mono"); font.setPointSize(7)
                painter.setFont(font)
                painter.drawText(QRectF(10, 34, self.WIDTH - 20, 14),
                                  Qt.AlignLeft | Qt.AlignVCenter, self._run_status_text)
            else:
                facts, _rv, _wv = self._facts_and_vars()
                if facts:
                    painter.setPen(QColor(COLORS["text_dim"]))
                    font = QFont("JetBrains Mono"); font.setPointSize(7)
                    painter.setFont(font)
                    painter.drawText(QRectF(10, 34, self.WIDTH - 20, 14),
                                      Qt.AlignLeft | Qt.AlignVCenter, facts[0]["value"])

            # Chevron ▾/▸ en haut-droite.
            self._paint_chevron(painter, routing)

        if self._expanded:
            self._paint_expanded_content(painter, routing)

        # Port d'entrée (toujours dessiné, connecté ou non) — anneau, pas un disque plein
        # (correctif, relevé en comparant une capture à la maquette Grammaire : bordure colorée,
        # intérieur sombre, jamais un point plein).
        self._draw_port_ring(painter, QPointF(0, self.HEIGHT / 2), COLORS["text_dim"])

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
            self._draw_port_ring(painter, QPointF(x, y), color)
            if label:
                painter.setPen(QColor(color))
                painter.drawText(QRectF(x - 22, y - 9, 16, 18),
                                  Qt.AlignRight | Qt.AlignVCenter, label)

        if "error" in self.output_ports:
            ex, ey = _error_port_local_pos(self.WIDTH, self.HEIGHT)
            color_key, label = _port_visual("error")
            color = COLORS[color_key]
            self._draw_port_ring(painter, QPointF(ex, ey), color)
            if label:
                painter.setPen(QColor(color))
                painter.drawText(QRectF(ex - 8, ey + 4, 16, 14), Qt.AlignCenter, label)

    def _draw_port_ring(self, painter, pos: QPointF, color: str) -> None:
        """Anneau d'un point de port — bordure colorée, intérieur sombre (correctif, relevé en
        comparant une capture à la maquette Grammaire : les points étaient pleins avant ce
        correctif, la maquette les montre toujours creux)."""
        painter.setBrush(QBrush(QColor(COLORS["bg_main"])))
        painter.setPen(QPen(QColor(color), 2))
        painter.drawEllipse(pos, PORT_RADIUS, PORT_RADIUS)

    def _paint_chevron(self, painter, routing: bool) -> None:
        """▾ (déplié) / ▸ (replié) — même rectangle que le hit-test de mousePressEvent
        (_chevron_rect), discret (text_dim)."""
        cx, cy, cw, ch = _chevron_rect(self.WIDTH, self.HEIGHT, routing)
        painter.setBrush(QBrush(QColor(COLORS["text_dim"])))
        painter.setPen(Qt.NoPen)
        tri = QPainterPath()
        if self._expanded:
            tri.moveTo(cx + 2, cy + 3)
            tri.lineTo(cx + cw - 2, cy + 3)
            tri.lineTo(cx + cw / 2, cy + ch - 3)
        else:
            tri.moveTo(cx + 3, cy + 2)
            tri.lineTo(cx + cw - 3, cy + ch / 2)
            tri.lineTo(cx + 3, cy + ch - 2)
        tri.closeSubpath()
        painter.drawPath(tri)

    def _paint_expanded_content(self, painter, routing: bool) -> None:
        """Faits clés + puces de variables lues/écrites — sous la marge basse déjà existante
        (bottom_margin, voir boundingRect()). Placeholder générique si rien à montrer (ex.
        GATEWAY_PARALLEL, config toujours vide) plutôt que de masquer le chevron au cas par cas."""
        facts, read_vars, written_vars = self._facts_and_vars()
        # Même marge basse pour un nœud de routage depuis ce chantier (A3 — son nom est passé
        # au-dessus du losange), voir boundingRect().
        y = self.HEIGHT + _ERROR_LABEL_MARGIN + _EXPANDED_TOP_PAD

        if not facts and not read_vars and not written_vars:
            painter.setPen(QColor(COLORS["text_muted"]))
            font = QFont(); font.setPointSize(8); font.setItalic(True)
            painter.setFont(font)
            painter.drawText(QRectF(10, y, self.WIDTH - 20, _FACT_LINE_H),
                              Qt.AlignLeft | Qt.AlignVCenter, "Aucun détail de configuration.")
            return

        # Valeur tronquée avec "…" (correctif, relevé en comparant une capture à la maquette : un
        # chemin Windows complet débordait du contenu déplié, coupé net en plein milieu d'un
        # caractère, sans indication visuelle qu'il manque la fin — même principe d'ellipse déjà
        # utilisé ailleurs dans l'appli, ex. settings_view.py::_make_category_row).
        value_width = self.WIDTH - 20 - 86
        base_font = QFont(); base_font.setPointSize(8)
        value_fm = QFontMetrics(base_font)
        for fact in facts:
            painter.setFont(base_font)
            painter.setPen(QColor(COLORS["text_dim"]))
            painter.drawText(QRectF(10, y, 84, _FACT_LINE_H), Qt.AlignLeft | Qt.AlignVCenter,
                              f"{fact['label']} :")
            painter.setPen(QColor(COLORS["text_main"]))
            elided_value = value_fm.elidedText(fact["value"], Qt.ElideRight, int(value_width))
            painter.drawText(QRectF(96, y, value_width, _FACT_LINE_H), Qt.AlignLeft | Qt.AlignVCenter,
                              elided_value)
            y += _FACT_LINE_H

        # Couleurs des puces (refonte, lot A-Atelier-grammaire, A2) : lit var:x en signal_pale,
        # écrit y en accent_pale — avant ce chantier, respectivement text_dim/border et accent.
        for name in read_vars:
            painter.setPen(QPen(QColor(COLORS["signal_pale"]), 1))
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(QRectF(12, y + 4, 6, 6))   # pastille creuse — variable LUE
            painter.setPen(QColor(COLORS["signal_pale"]))
            painter.setFont(base_font)
            painter.drawText(QRectF(24, y, self.WIDTH - 34, _VAR_BULLET_LINE_H),
                              Qt.AlignLeft | Qt.AlignVCenter, f"↳ lit var:{name}")
            y += _VAR_BULLET_LINE_H

        written_font = QFont(base_font); written_font.setBold(True)
        for name in written_vars:
            painter.setBrush(QBrush(QColor(COLORS["accent_pale"])))
            painter.setPen(Qt.NoPen)
            painter.drawRect(QRectF(12, y + 4, 6, 6))   # pastille pleine accent — variable ÉCRITE
            painter.setPen(QColor(COLORS["accent_pale"]))
            painter.setFont(written_font)
            painter.drawText(QRectF(24, y, self.WIDTH - 34, _VAR_BULLET_LINE_H),
                              Qt.AlignLeft | Qt.AlignVCenter, f"↳ écrit {name}")
            y += _VAR_BULLET_LINE_H

    def mousePressEvent(self, event):
        # Hit-test du chevron ▾/▸ AVANT toute logique de drag — un clic dessus bascule l'état
        # déplié/replié et s'arrête là (ni drag, ni changement de sélection). LIMITATION ACCEPTÉE
        # et documentée, pas un bug à corriger : un double-clic précis sur le chevron replie/
        # déplie ET ouvre le dialogue de configuration, car PipelineGraphScene.mouseDoubleClickEvent
        # (graph_scene.py) détecte le double-clic par un hit-test indépendant sur toute la forme
        # du nœud, sans savoir ce que ce mousePressEvent a fait du premier clic — déjà le cas
        # aujourd'hui pour n'importe quel point du nœud, y compris un port, pas une régression
        # propre à ce chantier.
        cx, cy, cw, ch = _chevron_rect(self.WIDTH, self.HEIGHT, self.is_routing_node)
        pad = _CHEVRON_HIT_PADDING
        if QRectF(cx - pad, cy - pad, cw + 2 * pad, ch + 2 * pad).contains(event.pos()):
            self.toggle_expanded()
            event.accept()
            return
        # self._dragging distingue un glissé interactif réel d'un setPos() programmatique
        # (rangement automatique/de la sélection, annulation, placement initial d'un nouveau
        # nœud) — seul le premier doit déclencher l'accrochage aux guides d'alignement dans
        # itemChange() ci-dessous (chantier UX éditeur, Lot 3, A5).
        self._dragging = True
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        self._dragging = False
        if self.scene():
            self.scene().clear_alignment_guides()
        super().mouseReleaseEvent(event)

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionChange and self._dragging and self.scene():
            return self.scene().snap_node_position(self, value)
        if change == QGraphicsItem.ItemPositionHasChanged and self.scene():
            self.scene().notify_node_moved(self)
        return super().itemChange(change, value)

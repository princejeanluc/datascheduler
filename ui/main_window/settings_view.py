"""
DataScheduler — ui/main_window/settings_view.py
Vue Paramètres : réglages transverses à l'application, jusqu'ici câblés en dur dans le code sans
aucun endroit pour les consulter ou les modifier sans reconstruire l'exe (fuseau horaire du
scheduler, niveau de log, fréquences de rafraîchissement de l'UI…). Recherche + catégories à
gauche, détail à droite (patron "façon VSCode", maquette validée avec l'utilisateur) — intégré
dans la nav rail existante comme une vue de plus, pas une fenêtre à part.

Reprend aussi les champs du digest de notification (NotificationSettings, existant) dans la
catégorie "Notifications" — NotificationSettingsDialog est retiré au profit de cet écran unique.
"""

import re
from html import escape
from zoneinfo import available_timezones

from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton, QFrame, QScrollArea,
    QComboBox, QSpinBox, QLineEdit, QMessageBox, QCompleter, QGraphicsOpacityEffect,
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFontMetrics
from version import __version__
from ui.styles import COLORS, FONT_MONO_STACK, FONT_SIZES
from ui.time_display import fmt_relative
from ui.step_editor.common import DAYS_OF_WEEK
from ui.components import make_page_header, make_info_pill, make_banner, make_switch
from .widgets import _icon, _make_search_input

_CATEGORIES = [
    # "sub" (rail, court) et "desc" (panneau de détail, plus long) sont deux textes distincts sur
    # la maquette (Parametres.html : "Planification, rattrapages, exécution en arrière-plan" au
    # rail vs "Comportement du planificateur : fuseau, rattrapages, exécution en arrière-plan."
    # en détail) — une relecture avait fusionné les deux en un seul texte, repris tel quel aux
    # deux endroits. "desc" pour Journalisation/Interface/Ressources n'a pas d'équivalent sur une
    # maquette (seuls Ordonnanceur et Notifications ont leur panneau de détail capturé) : gardé
    # tel que déjà écrit, faute de référence à reprendre.
    {"key": "scheduler",     "label": "Ordonnanceur",    "icon": "fa5s.clock",
     "sub": "Planification, rattrapages, exécution en arrière-plan",
     "desc": "Comportement du planificateur : fuseau, rattrapages, exécution en arrière-plan."},
    {"key": "logging",       "label": "Journalisation",  "icon": "fa5s.file-alt",
     "sub": "Fichiers de logs et niveau de détail",
     "desc": "Fichier de logs (%APPDATA%/DataScheduler/logs)."},
    {"key": "interface",     "label": "Interface",       "icon": "fa5s.sync-alt",
     "sub": "Fréquences de rafraîchissement",
     "desc": "Fréquences de rafraîchissement automatique."},
    {"key": "notifications", "label": "Notifications",   "icon": "fa5s.bell",
     "sub": "Résumé périodique par email",
     "desc": "Résumé périodique des exécutions par email."},
    {"key": "resources",     "label": "Ressources",      "icon": "fa5s.chart-line",
     "sub": "Échantillonnage CPU et mémoire",
     "desc": "Échantillonnage CPU/mémoire de la vue Ressources."},
]

# Liste complète des fuseaux IANA réels (via tzdata, déjà une dépendance du projet pour
# core/missed_runs.py) plutôt qu'une poignée de choix câblés en dur — un décalage fixe
# ("GMT+3") ne gère jamais le changement d'heure été/hiver, contrairement à un vrai fuseau
# nommé par ville/région, qui reste correct toute l'année. "UTC" en tête (choix explicite le
# plus courant), le reste trié alphabétiquement.
_TIMEZONES = ["UTC"] + sorted(available_timezones() - {"UTC"})
_LOG_LEVELS = ["DEBUG", "INFO", "WARNING", "ERROR"]

_CATEGORY_SUB_WIDTH = 150   # px — largeur dispo connue d'avance (rail 240px, largeur fixe)

# Pastille de prise d'effet (A4, docs/refonte/ecrans/Parametres.md) : variante + infobulle par
# texte exact, pour que _add_row() n'ait qu'à recevoir le texte déjà écrit dans la fiche. Seule
# "au redémarrage" porte une icône sur la maquette (petite flèche de rechargement) ; les deux
# autres variantes n'en ont pas (confirmé sur Parametres.html et Parametres-recherche.html).
_BADGE_INFO = {
    "au redémarrage": ("neutral", "Prend effet au prochain démarrage de Kulu", "↻"),
    "à la prochaine ouverture": ("neutral", "Prend effet à la prochaine ouverture de l'écran", ""),
    "immédiat": ("success", "Prend effet immédiatement", ""),
}


def _hide_before_first_show(widget):
    """setVisible(False) sans danger sur un widget jamais encore affiché. Un widget masqué avant
    d'avoir jamais traversé une passe de mise en page garde la géométrie par défaut de Qt
    (0,0,640,480) — un layout n'y touche plus une fois masqué, il ne la corrigera jamais tout
    seul. QWidget.grab() a été constaté fuyant ce rectangle resté par défaut dans la capture
    malgré isVisible()==False (bug réel, reproduit et corrigé, pas une supposition). Un
    redimensionnement minimal avant le masquage suffit : une fois rendu visible plus tard, le
    layout reprend la main et lui donne sa vraie taille normalement."""
    widget.resize(1, 1)
    widget.setVisible(False)


def _highlight(text: str, query: str) -> str:
    """Rich text (A5, Parametres-recherche.html) : entoure chaque occurrence de `query` (recherche
    insensible à la casse, casse d'origine du texte préservée) d'un <mark>. Sans query, renvoie le
    texte échappé tel quel — toujours sûr à passer à QLabel.setText (QLabel détecte le HTML tout
    seul s'il y en a, et affiche du texte normal sinon)."""
    if not query:
        return escape(text)
    pattern = re.compile(re.escape(query), re.IGNORECASE)
    pieces = []
    last = 0
    for m in pattern.finditer(text):
        pieces.append(escape(text[last:m.start()]))
        # <span>, pas <mark> : le sous-ensemble HTML du rich text Qt ne connaît pas <mark>
        # (balise HTML5) et l'affiche tel quel au lieu de l'interpréter.
        pieces.append(
            f'<span style="background-color:{COLORS["search_highlight"]}; '
            f'color:{COLORS["text_main"]}; border-radius:2px;">{escape(m.group(0))}</span>'
        )
        last = m.end()
    pieces.append(escape(text[last:]))
    return "".join(pieces)


def _input_style(error: bool = False) -> str:
    border = COLORS["danger"] if error else COLORS["border"]
    return (
        f"QLineEdit {{ background: {COLORS['bg_card']}; border: 1px solid {border}; "
        f"border-radius: 4px; padding: 6px 10px; color: {COLORS['text_main']}; font-size: 13px; }}"
        f"QLineEdit:focus {{ border-color: {COLORS['accent']}; }}"
    )


def _combo_style() -> str:
    return (
        f"QComboBox {{ background: {COLORS['bg_card']}; border: 1px solid {COLORS['border']}; "
        f"border-radius: 4px; padding: 6px 10px; color: {COLORS['text_main']}; font-size: 13px; }}"
        f"QComboBox:focus {{ border-color: {COLORS['accent']}; }}"
        f"QComboBox::drop-down {{ border: none; padding-right: 8px; }}"
        f"QComboBox QAbstractItemView {{ background: {COLORS['bg_card']}; "
        f"border: 1px solid {COLORS['border']}; "
        f"selection-background-color: {COLORS['bg_active']}; color: {COLORS['text_main']}; }}"
    )


def _spinbox_style() -> str:
    return (
        f"QSpinBox {{ background: {COLORS['bg_card']}; border: 1px solid {COLORS['border']}; "
        f"border-radius: 4px; padding: 6px 8px; color: {COLORS['text_main']}; font-size: 13px; }}"
        f"QSpinBox:focus {{ border-color: {COLORS['accent']}; }}"
    )


class SettingsView(QWidget):
    def __init__(self):
        super().__init__()
        self._active_category = "scheduler"
        self._row_widgets: list[dict] = []   # {category, label, desc, widget, category_chip}
        self._build_ui()
        self._prefill()
        self._refresh_worker_status()
        self._worker_status_timer = QTimer(self)
        self._worker_status_timer.setInterval(5000)
        self._worker_status_timer.timeout.connect(self._refresh_worker_status)
        self._worker_status_timer.start()

    # ── Construction ──────────────────────────

    def _build_ui(self):
        # Pas de séparateur horizontal sous l'en-tête ni de ligne verticale entre rail et
        # panneau : la maquette (Parametres.html) n'en a aucun, juste un espacement (gap) entre
        # le rail et le panneau, lui-même bordé (voir _build_detail).
        outer = QVBoxLayout(self)
        outer.setContentsMargins(32, 24, 32, 20)
        outer.setSpacing(18)

        outer.addWidget(make_page_header(f"CE POSTE · KULU {__version__}", "Paramètres"))

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(24)

        body.addWidget(self._build_rail())
        body.addWidget(self._build_detail(), stretch=1)
        outer.addLayout(body, stretch=1)

    def _build_rail(self) -> QWidget:
        rail = QWidget()
        rail.setFixedWidth(240)
        rail_layout = QVBoxLayout(rail)
        rail_layout.setContentsMargins(16, 16, 16, 16)
        rail_layout.setSpacing(14)

        self.inp_search = _make_search_input("Rechercher un paramètre…")
        self.inp_search.setFixedWidth(208)
        self.inp_search.textChanged.connect(self._on_search_changed)
        rail_layout.addWidget(self.inp_search)

        self._category_rows: dict[str, dict] = {}
        for cat in _CATEGORIES:
            row = self._make_category_row(cat)
            rail_layout.addWidget(row["frame"])
            self._category_rows[cat["key"]] = row

        rail_layout.addStretch()

        rail_footer = QLabel(
            "Réglages enregistrés pour ce poste, dans la base locale de Kulu.")
        rail_footer.setWordWrap(True)
        rail_footer.setStyleSheet(
            f"color: {COLORS['text_muted']}; font-size: 11.5px; background: transparent;")
        rail_layout.addWidget(rail_footer)
        return rail

    def _make_category_row(self, cat: dict) -> dict:
        """Entrée de catégorie du rail (refonte, lot A-Paramètres — A1) : icône, nom, sous-titre
        tronqué, et un compteur de résultats de recherche masqué par défaut (A5). Même patron
        clickable que `_make_card` (step_type_chooser_dialog.py) : QFrame + mouseReleaseEvent
        assigné, pas un QPushButton — aucun test ne dépend du type exact (vérifié)."""
        frame = QFrame()
        frame.setObjectName("category_row")   # sélecteur d'ID — voir _build_detail pour pourquoi
        frame.setCursor(Qt.PointingHandCursor)
        frame.setFixedHeight(48)
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(10, 0, 10, 0)
        layout.setSpacing(10)

        # background: transparent sur chaque QLabel : sans lui, la règle globale `QWidget {
        # background-color: bg_main }` (widgets.py::GLOBAL_STYLE) peint un rectangle opaque
        # bg_main derrière le texte, visible comme un encart sombre dès que la ligne elle-même a
        # un fond différent (bg_active ici) — bug constaté à l'écran, reproduit isolément.
        icon_lbl = QLabel()
        icon_lbl.setFixedWidth(18)
        icon_lbl.setStyleSheet("background: transparent;")
        layout.addWidget(icon_lbl, alignment=Qt.AlignVCenter)

        text_col = QVBoxLayout(); text_col.setSpacing(1)
        name_lbl = QLabel(cat["label"])
        name_lbl.setStyleSheet(
            f"color: {COLORS['text_main']}; font-size: 13.5px; font-weight: 600; "
            f"background: transparent;")
        text_col.addWidget(name_lbl)
        sub_lbl = QLabel()
        sub_lbl.setStyleSheet(f"color: {COLORS['text_dim']}; background: transparent;")
        sub_font = sub_lbl.font(); sub_font.setPixelSize(12)
        sub_lbl.setFont(sub_font)
        sub_lbl.setFixedWidth(_CATEGORY_SUB_WIDTH)
        sub_lbl.setToolTip(cat["sub"])
        sub_lbl.setText(QFontMetrics(sub_font).elidedText(
            cat["sub"], Qt.ElideRight, _CATEGORY_SUB_WIDTH))
        text_col.addWidget(sub_lbl)
        layout.addLayout(text_col, 1)

        count_lbl = QLabel("")
        # Taille fixe explicite : un QLabel masqué via setVisible(False) avant d'avoir jamais été
        # affiché garde sa géométrie Qt par défaut (0,0,640,480) — un vrai bug de rendu Qt/
        # plateforme offscreen a été constaté avec QWidget.grab() : ce widget masqué "depuis sa
        # naissance" fuyait un rectangle visible dans la capture malgré isVisible()==False. Une
        # taille raisonnable fixée dès la construction élimine le problème (vérifié).
        count_lbl.setFixedSize(26, 16)
        count_lbl.setAlignment(Qt.AlignCenter)
        count_lbl.setStyleSheet(
            f"color: {COLORS['signal_pale']}; font-size: 11px; font-family: {FONT_MONO_STACK}; "
            f"background: transparent;"
        )
        count_lbl.setVisible(False)
        layout.addWidget(count_lbl, alignment=Qt.AlignVCenter)

        frame.mouseReleaseEvent = lambda _, k=cat["key"]: self._select_category(k)
        return {"frame": frame, "icon_name": cat["icon"], "icon_lbl": icon_lbl,
                "name_lbl": name_lbl, "sub_lbl": sub_lbl, "count_lbl": count_lbl}

    def _build_detail(self) -> QWidget:
        # Carte à bord arrondi (Parametres.html::section) : bg_panel, bordure, rayon 10px — pas
        # juste un fond plat séparé du rail par une ligne verticale (ancien rendu).
        panel = QFrame()
        panel.setObjectName("settings_panel")
        # Sélecteur d'ID, pas "QFrame" (type) : QLabel hérite de QFrame en Qt — un sélecteur de
        # type aurait fait hériter bordure/fond/rayon à CHAQUE QLabel descendant (libellés,
        # descriptions...), bug constaté à l'écran avant cette correction.
        panel.setStyleSheet(
            f"QFrame#settings_panel {{ background: {COLORS['bg_panel']}; "
            f"border: 1px solid {COLORS['border']}; border-radius: 10px; }}"
        )
        col = QVBoxLayout(panel)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(0)

        title_wrap = QWidget()
        title_wrap.setObjectName("settings_title_wrap")
        # Sélecteur d'ID, pas une règle nue : une règle `widget.setStyleSheet("...")` sans
        # sélecteur se propage à TOUS les descendants pour les propriétés qu'ils ne fixent pas
        # eux-mêmes (confirmé isolément) — ici "border-bottom" aurait pu déteindre, et ailleurs
        # (footer_wrap) une règle nue a bien écrasé le fond du bouton Enregistrer (bug constaté).
        title_wrap.setStyleSheet(
            f"QWidget#settings_title_wrap {{ border-bottom: 1px solid {COLORS['border']}; }}")
        self._detail_title = QLabel()
        self._detail_title.setStyleSheet(
            f"color: {COLORS['text_main']}; font-size: {FONT_SIZES['panel_title']}px; font-weight: 600; "
            f"border: none; background: transparent;")
        self._detail_sub = QLabel()
        self._detail_sub.setStyleSheet(
            f"color: {COLORS['text_dim']}; font-size: 12.5px; border: none; background: transparent;")
        self._detail_sub.setWordWrap(True)

        title_block = QVBoxLayout(title_wrap)
        title_block.setContentsMargins(20, 16, 20, 12)
        title_block.setSpacing(3)
        title_block.addWidget(self._detail_title)
        title_block.addWidget(self._detail_sub)
        col.addWidget(title_wrap)

        self._search_help_lbl = QLabel("")
        self._search_help_lbl.setTextFormat(Qt.RichText)
        self._search_help_lbl.setStyleSheet(
            f"color: {COLORS['text_dim']}; font-size: 12px; background: transparent;")
        self._search_help_lbl.setContentsMargins(20, 0, 20, 6)
        _hide_before_first_show(self._search_help_lbl)
        col.addWidget(self._search_help_lbl)

        self._failure_banner = self._build_failure_banner()
        banner_wrap = QHBoxLayout()
        banner_wrap.setContentsMargins(20, 10, 20, 0)
        banner_wrap.addWidget(self._failure_banner)
        col.addLayout(banner_wrap)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("background: transparent;")
        content = QWidget()
        scroll.setWidget(content)
        self._rows_layout = QVBoxLayout(content)
        self._rows_layout.setContentsMargins(20, 4, 20, 8)
        self._rows_layout.setSpacing(0)
        col.addWidget(scroll, stretch=1)

        self._build_rows()
        # Sans ce stretch final, QVBoxLayout redistribue l'espace vertical excédentaire de la
        # zone de défilement entre les lignes VISIBLES (flagrant en recherche, où seules 2-3
        # lignes restent affichées sur ~22) au lieu de le laisser en blanc sous la dernière ligne
        # — chaque ligne gagnait alors une hauteur variable selon le nombre de lignes visibles,
        # au lieu de garder sa hauteur naturelle (bug latent, révélé par les pastilles à fond
        # plein de ce lot, jamais visible avec le texte nu d'avant).
        self._rows_layout.addStretch()

        footer_wrap = QWidget()
        footer_wrap.setObjectName("settings_footer")
        # Sélecteur d'ID, pas une règle nue : confirmé isolément qu'une règle nue ("background: ...")
        # posée sur ce conteneur écrasait le fond accent du QPushButton#Enregistrer (règle globale
        # `QPushButton { background-color: accent }` de widgets.py) — le bouton rendait plat, sans
        # son fond orange, exactement le bug signalé à l'écran.
        footer_wrap.setStyleSheet(
            f"QWidget#settings_footer {{ background: {COLORS['bg_panel']}; "
            f"border-top: 1px solid {COLORS['border']}; border-radius: 0 0 10px 10px; }}"
        )
        footer = QHBoxLayout(footer_wrap)
        footer.setContentsMargins(20, 10, 20, 10)
        footer.setSpacing(12)
        # Texte par défaut "Aucune modification" repris de Parametres.html (pas de pastille
        # "proposé" dessus, contrairement au compteur dynamique "N réglages modifiés" de la même
        # zone sur Parametres-arriere-plan.html — celui-là est C1, gated par la décision P1).
        # Icône séparée du texte (correctif, écart maquette) : un glyphe Unicode de coche/alerte
        # inline dans le texte ("✓ Enregistré") n'a pas la même graisse que le reste de la chaîne
        # — la police embarquée n'a pas ce glyphe en gras, Qt retombe sur une police système plus
        # fine pour ce seul caractère (constaté en capturant). Icône qtawesome à la place, même
        # principe que les autres icônes de l'appli (voir le commentaire de ui/sql_editor.py sur
        # les glyphes texte).
        self._save_status_icon = QLabel()
        self._save_status_icon.setFixedSize(14, 14)
        self._save_status_icon.setVisible(False)
        footer.addWidget(self._save_status_icon)
        self._save_status_lbl = QLabel("")
        footer.addWidget(self._save_status_lbl)
        self._reset_save_status_lbl()
        footer.addStretch()
        ctrl_s_hint = QLabel("Ctrl S")
        ctrl_s_hint.setStyleSheet(
            f"color: {COLORS['text_muted']}; font-size: 11px; font-family: {FONT_MONO_STACK}; "
            f"border: none; background: transparent;")
        footer.addWidget(ctrl_s_hint)
        btn_save = QPushButton("Enregistrer")
        btn_save.setFixedHeight(34); btn_save.setMinimumWidth(140)
        btn_save.clicked.connect(self._on_save)
        footer.addWidget(btn_save)
        col.addWidget(footer_wrap)

        self._select_category("scheduler")
        return panel

    def _build_failure_banner(self) -> QWidget:
        """Bandeau d'échec d'activation du mode arrière-plan (A7) — persistant jusqu'à fermeture
        ou nouvel enregistrement, contrairement au texte du pied qui s'efface tout seul après
        10s (inchangé, voir _on_save). "Copier le détail" (maquette Parametres-refus.html) porte
        un badge "proposé" (C8, gated) : seul "Fermer" est construit ici."""
        btn_fermer = QPushButton("Fermer")
        btn_fermer.setObjectName("secondary")
        btn_fermer.clicked.connect(lambda: self._failure_banner.setVisible(False))
        banner = make_banner(
            "danger", "fa5s.exclamation-circle",
            "Windows a refusé la tâche d'arrière-plan (accès refusé)",
            "Le mode « Dans l'application seulement » reste actif, vos pipelines planifiés "
            "continuent de tourner tant que Kulu est ouvert. Les autres réglages ont bien été "
            "enregistrés. Contactez votre support informatique : Kulu a besoin du droit de "
            "créer une tâche planifiée à l'ouverture de session.",
            actions=btn_fermer,
        )
        _hide_before_first_show(banner)
        return banner

    def _add_row(self, category: str, label: str, desc: str, widget, badge: str | None = None):
        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 14, 0, 14)
        row_layout.setSpacing(20)

        text_col = QVBoxLayout(); text_col.setSpacing(3)
        chip = make_info_pill(next(c["label"] for c in _CATEGORIES if c["key"] == category),
                               variant="info")
        _hide_before_first_show(chip)
        # alignment=Qt.AlignLeft : sans lui, QVBoxLayout étire le QLabel (fond plein) sur toute
        # la largeur de la colonne — invisible avec l'ancien style (pas de fond), mais flagrant
        # avec le fond de make_info_pill (bug révélé, pas introduit, par ce changement).
        text_col.addWidget(chip, alignment=Qt.AlignLeft)

        label_row = QHBoxLayout(); label_row.setSpacing(8)
        lbl = QLabel(label)
        lbl.setTextFormat(Qt.RichText)
        lbl.setStyleSheet(
            f"color: {COLORS['text_main']}; font-size: {FONT_SIZES['row_label']}px; font-weight: 600; "
            f"background: transparent;")
        label_row.addWidget(lbl)
        if badge:
            variant, tooltip, icon = _BADGE_INFO[badge]
            pill = make_info_pill(badge, variant=variant, tooltip=tooltip, icon=icon)
            # alignment=AlignVCenter : sans lui, QHBoxLayout étire le QLabel sur toute la hauteur
            # de la ligne (son texte reste ancré en haut, la bordure/le fond de make_info_pill
            # peint tout le rectangle étiré — même bug que le chip ci-dessus, autre axe).
            label_row.addWidget(pill, alignment=Qt.AlignVCenter)
        label_row.addStretch()
        text_col.addLayout(label_row)

        desc_lbl = None
        if desc:
            desc_lbl = QLabel(desc)
            desc_lbl.setTextFormat(Qt.RichText)
            desc_lbl.setWordWrap(True)
            desc_lbl.setStyleSheet(
                f"color: {COLORS['text_dim']}; font-size: 12.5px; background: transparent;")
            text_col.addWidget(desc_lbl)

        row_layout.addLayout(text_col, stretch=1)
        # 280px, pas 200 : la maquette va jusqu'à 280px pour "Mode d'exécution" (sa valeur la
        # plus longue, "Avec exécution en arrière-plan") — un seul gabarit plus large pour
        # toutes les lignes plutôt qu'une largeur par ligne, plus simple, jamais trop étroit.
        control_box = QWidget(); control_box.setFixedWidth(280)
        control_layout = QHBoxLayout(control_box)
        control_layout.setContentsMargins(0, 0, 0, 0)
        control_layout.addWidget(widget)
        row_layout.addWidget(control_box)

        sep = QFrame(); sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet(f"background: {COLORS['bg_hover']}; max-height: 1px;")

        wrapper = QWidget()
        wrapper_layout = QVBoxLayout(wrapper)
        wrapper_layout.setContentsMargins(0, 0, 0, 0)
        wrapper_layout.setSpacing(0)
        wrapper_layout.addWidget(row)
        wrapper_layout.addWidget(sep)

        self._rows_layout.addWidget(wrapper)
        self._row_widgets.append({
            "category": category, "label": label.lower(), "desc": desc.lower(),
            "wrapper": wrapper, "chip": chip,
            "label_text": label, "desc_text": desc, "label_lbl": lbl, "desc_lbl": desc_lbl,
        })

    def _build_rows(self):
        # Ordonnanceur
        self.cb_timezone = QComboBox(); self.cb_timezone.setStyleSheet(_combo_style())
        self.cb_timezone.addItems(_TIMEZONES)
        # Éditable + complétion filtrée : ~600 fuseaux IANA, une liste déroulante brute serait
        # inutilisable. Tapez une ville/région ("Paris", "Nairobi") ou "Etc/GMT+3" pour un
        # décalage fixe explicite sans changement d'heure saisonnier.
        self.cb_timezone.setEditable(True)
        self.cb_timezone.setInsertPolicy(QComboBox.NoInsert)
        completer = QCompleter(_TIMEZONES, self.cb_timezone)
        completer.setCaseSensitivity(Qt.CaseInsensitive)
        completer.setFilterMode(Qt.MatchContains)
        completer.setCompletionMode(QCompleter.PopupCompletion)
        self.cb_timezone.setCompleter(completer)
        self._add_row("scheduler", "Fuseau horaire",
                       "Référence pour l'heure de toutes les planifications (Quotidien, Hebdo, "
                       "Cron).", self.cb_timezone, badge="au redémarrage")

        self.spin_misfire = QSpinBox(); self.spin_misfire.setStyleSheet(_spinbox_style())
        self.spin_misfire.setRange(1, 1440); self.spin_misfire.setSuffix(" min")
        self._add_row("scheduler", "Tolérance de rattrapage",
                       "Délai après lequel une exécution planifiée manquée (PC éteint) n'est "
                       "plus rattrapée.", self.spin_misfire, badge="immédiat")

        self.chk_coalesce = make_switch()
        self._add_row("scheduler", "Regrouper les rattrapages manqués",
                       "Si plusieurs déclenchements ont été manqués pendant la tolérance, n'en "
                       "rejouer qu'un seul plutôt que tous d'affilée.",
                       self.chk_coalesce, badge="immédiat")

        self.spin_max_concurrent = QSpinBox(); self.spin_max_concurrent.setStyleSheet(_spinbox_style())
        self.spin_max_concurrent.setRange(1, 100)
        self._add_row("scheduler", "Plafond d'exécutions simultanées",
                       "Au-delà, un nouveau lancement (manuel, planifié ou en chaîne) est "
                       "refusé, pas mis en file d'attente. Un run planifié refusé attend son "
                       "prochain déclenchement.",
                       self.spin_max_concurrent, badge="immédiat")

        # Exécution en arrière-plan (chantier worker) — un worker détaché devient le seul
        # exécuteur, l'appli desktop devient purement cliente. Jamais à chaud (voir _on_save) :
        # évite toute fenêtre avec deux planificateurs actifs en même temps.
        self.cb_execution_mode = QComboBox(); self.cb_execution_mode.setStyleSheet(_combo_style())
        self.cb_execution_mode.addItem("Dans l'application seulement", "IN_APP")
        self.cb_execution_mode.addItem("Avec exécution en arrière-plan", "BACKGROUND")
        self._add_row("scheduler", "Mode d'exécution",
                       "En arrière-plan, un worker détaché continue de planifier et d'exécuter "
                       "même l'appli fermée, tant que la session Windows est ouverte.",
                       self.cb_execution_mode, badge="au redémarrage")

        self.lbl_worker_status = QLabel("Sans objet en mode « Dans l'application seulement »")
        self.lbl_worker_status.setTextFormat(Qt.RichText)
        self.lbl_worker_status.setWordWrap(True)   # texte plus long que "—" : ne pas le tronquer
        self.lbl_worker_status.setStyleSheet(
            f"color: {COLORS['text_muted']}; font-size: 12px; background: transparent;")
        self._add_row("scheduler", "État du worker en arrière-plan",
                       "Déduit du dernier échantillon de ressources, que le worker écrit en "
                       "continu.", self.lbl_worker_status)

        # Réutilisation des tickets Kerberos (chantier dédié) — jusqu'ici, kinit était relancé
        # sans condition à chaque étape SPARK_SQL/SQOOP_EXPORT/SQOOP_IMPORT, même si un ticket
        # valide de 24h existait déjà.
        self.chk_kerberos_reuse = make_switch()
        self._add_row("scheduler", "Réutiliser un ticket Kerberos valide",
                       "Évite un kinit à chaque étape Spark SQL ou Sqoop si un ticket valide "
                       "existe déjà sur le nœud edge.",
                       self.chk_kerberos_reuse, badge="immédiat")

        self.spin_kerberos_grace = QSpinBox(); self.spin_kerberos_grace.setStyleSheet(_spinbox_style())
        self.spin_kerberos_grace.setRange(0, 86400); self.spin_kerberos_grace.setSuffix(" s")
        self.spin_kerberos_grace.setSpecialValueText("Aucune")
        self.chk_kerberos_reuse.toggled.connect(self.spin_kerberos_grace.setEnabled)
        self._add_row("scheduler", "Marge de grâce du ticket Kerberos",
                       "Un ticket n'est réutilisé que s'il lui reste plus que cette durée avant "
                       "expiration.",
                       self.spin_kerberos_grace, badge="immédiat")

        # Journalisation
        self.cb_log_level = QComboBox(); self.cb_log_level.setStyleSheet(_combo_style())
        self.cb_log_level.addItems(_LOG_LEVELS)
        self._add_row("logging", "Niveau de journalisation",
                       "INFO ne conserve pas le détail utile pour diagnostiquer un comportement "
                       "rare.", self.cb_log_level, badge="immédiat")

        self.spin_log_mb = QSpinBox(); self.spin_log_mb.setStyleSheet(_spinbox_style())
        self.spin_log_mb.setRange(1, 500); self.spin_log_mb.setSuffix(" Mo")
        self._add_row("logging", "Taille max par fichier",
                       "Au-delà, rotation vers un nouveau fichier.",
                       self.spin_log_mb, badge="au redémarrage")

        self.spin_log_backups = QSpinBox(); self.spin_log_backups.setStyleSheet(_spinbox_style())
        self.spin_log_backups.setRange(1, 50)
        self._add_row("logging", "Fichiers conservés",
                       "Nombre de fichiers de rotation gardés avant suppression du plus ancien.",
                       self.spin_log_backups, badge="au redémarrage")

        # Interface
        self.spin_dashboard_refresh = QSpinBox(); self.spin_dashboard_refresh.setStyleSheet(_spinbox_style())
        self.spin_dashboard_refresh.setRange(5, 600); self.spin_dashboard_refresh.setSuffix(" s")
        self._add_row("interface", "Rafraîchissement du Dashboard",
                       "Vue d'ensemble, badges d'état des pipelines.",
                       self.spin_dashboard_refresh, badge="au redémarrage")

        self.spin_pipelines_refresh = QSpinBox(); self.spin_pipelines_refresh.setStyleSheet(_spinbox_style())
        self.spin_pipelines_refresh.setRange(5, 600); self.spin_pipelines_refresh.setSuffix(" s")
        self._add_row("interface", "Rafraîchissement des Pipelines",
                       "Liste des pipelines et leur statut courant.",
                       self.spin_pipelines_refresh, badge="au redémarrage")

        self.spin_live_log_refresh = QSpinBox(); self.spin_live_log_refresh.setStyleSheet(_spinbox_style())
        self.spin_live_log_refresh.setRange(1, 60); self.spin_live_log_refresh.setSuffix(" s")
        self._add_row("interface", "Log d'exécution en direct",
                       "Fenêtre de suivi d'un run en cours, rafraîchie à cet intervalle.",
                       self.spin_live_log_refresh, badge="à la prochaine ouverture")

        self.spin_trace_glow_refresh = QSpinBox(); self.spin_trace_glow_refresh.setStyleSheet(_spinbox_style())
        self.spin_trace_glow_refresh.setRange(1, 60); self.spin_trace_glow_refresh.setSuffix(" s")
        self._add_row("interface", "Traçage lumineux (éditeur graphique)",
                       "Interrogation de l'étape en cours pour surligner le nœud actif, "
                       "rafraîchie à cet intervalle.", self.spin_trace_glow_refresh,
                       badge="à la prochaine ouverture")

        # Notifications
        self.chk_digest_enabled = make_switch()
        self._add_row("notifications", "Résumé périodique activé",
                       "Envoie un email récapitulatif des exécutions depuis le dernier envoi.",
                       self.chk_digest_enabled, badge="immédiat")

        self.cb_smtp = QComboBox(); self.cb_smtp.setStyleSheet(_combo_style())
        self._add_row("notifications", "Profil SMTP",
                       "Utilisé pour l'envoi du résumé. Les profils se gèrent dans Connexions.",
                       self.cb_smtp, badge="immédiat")

        self.inp_recipients = QLineEdit(); self.inp_recipients.setFixedHeight(34)
        self.inp_recipients.setStyleSheet(_input_style())
        self.inp_recipients.setPlaceholderText("ex : sophie@entreprise.com, karim@entreprise.com")
        self._add_row("notifications", "Destinataires",
                       "Adresses séparées par une virgule.", self.inp_recipients, badge="immédiat")

        self.cb_frequency = QComboBox(); self.cb_frequency.setStyleSheet(_combo_style())
        self.cb_frequency.addItem("Quotidien", "DAILY")
        self.cb_frequency.addItem("Hebdomadaire", "WEEKLY")
        self.cb_frequency.currentIndexChanged.connect(self._on_frequency_changed)
        self._add_row("notifications", "Fréquence", "", self.cb_frequency, badge="immédiat")

        self.cb_day = QComboBox(); self.cb_day.setStyleSheet(_combo_style())
        for i, d in enumerate(DAYS_OF_WEEK):
            self.cb_day.addItem(d, i)
        self._add_row("notifications", "Jour",
                       "Jour d'envoi du résumé hebdomadaire.", self.cb_day, badge="immédiat")

        self.inp_time = QLineEdit(); self.inp_time.setFixedHeight(34)
        self.inp_time.setStyleSheet(_input_style())
        self._add_row("notifications", "Heure d'envoi",
                       "Format HH:MM, dans le fuseau de l'ordonnanceur.", self.inp_time,
                       badge="immédiat")

        # Ressources (chantier suivi des ressources) — premier réglage né directement avec ce
        # socle, jamais en dur auparavant.
        self.spin_sample_interval = QSpinBox(); self.spin_sample_interval.setStyleSheet(_spinbox_style())
        self.spin_sample_interval.setRange(10, 3600); self.spin_sample_interval.setSuffix(" s")
        self._add_row("resources", "Intervalle d'échantillonnage",
                       "Fréquence de mesure du CPU/mémoire de l'application. Effet immédiat.",
                       self.spin_sample_interval, badge="immédiat")

        self.spin_sample_retention = QSpinBox(); self.spin_sample_retention.setStyleSheet(_spinbox_style())
        self.spin_sample_retention.setRange(1, 90); self.spin_sample_retention.setSuffix(" j")
        self._add_row("resources", "Rétention des échantillons",
                       "Au-delà, les échantillons les plus anciens sont supprimés automatiquement.",
                       self.spin_sample_retention, badge="immédiat")

    # ── Données ───────────────────────────────

    def _prefill(self):
        from database import db_manager as db
        settings = db.get_app_settings()

        idx = self.cb_timezone.findText(settings.timezone)
        self.cb_timezone.setCurrentIndex(idx if idx >= 0 else 0)
        self.spin_misfire.setValue(settings.misfire_grace_time_min)
        self.chk_coalesce.setChecked(settings.coalesce_missed_runs)
        self.spin_max_concurrent.setValue(settings.max_concurrent_runs)

        idx = self.cb_execution_mode.findData(settings.execution_mode)
        self.cb_execution_mode.setCurrentIndex(idx if idx >= 0 else 0)

        self.chk_kerberos_reuse.setChecked(settings.kerberos_reuse_valid_ticket)
        self.spin_kerberos_grace.setValue(settings.kerberos_ticket_grace_period_s)
        self.spin_kerberos_grace.setEnabled(settings.kerberos_reuse_valid_ticket)

        idx = self.cb_log_level.findText(settings.log_level)
        self.cb_log_level.setCurrentIndex(idx if idx >= 0 else 1)
        self.spin_log_mb.setValue(max(1, settings.log_max_bytes // 1_000_000))
        self.spin_log_backups.setValue(settings.log_backup_count)

        self.spin_dashboard_refresh.setValue(settings.dashboard_refresh_s)
        self.spin_pipelines_refresh.setValue(settings.pipelines_refresh_s)
        self.spin_live_log_refresh.setValue(settings.live_log_refresh_s)
        self.spin_trace_glow_refresh.setValue(settings.trace_glow_refresh_s)

        self.spin_sample_interval.setValue(settings.resource_sample_interval_s)
        self.spin_sample_retention.setValue(settings.resource_sample_retention_days)

        notif = db.get_notification_settings()
        self._smtp_profiles = db.get_smtp_profiles()
        self.cb_smtp.clear()
        self.cb_smtp.addItem("— Sélectionner un profil SMTP —", None)
        for p in self._smtp_profiles:
            self.cb_smtp.addItem(p.name, p.id)
        self.chk_digest_enabled.setChecked(bool(notif.digest_enabled))
        if notif.digest_smtp_profile_id:
            idx = self.cb_smtp.findData(notif.digest_smtp_profile_id)
            if idx >= 0:
                self.cb_smtp.setCurrentIndex(idx)
        self.inp_recipients.setText(notif.digest_recipients or "")
        idx = self.cb_frequency.findData(notif.digest_frequency or "DAILY")
        if idx >= 0:
            self.cb_frequency.setCurrentIndex(idx)
        self.inp_time.setText(notif.digest_time or "07:00")
        day_idx = self.cb_day.findData(notif.digest_day_of_week if notif.digest_day_of_week is not None else 0)
        if day_idx >= 0:
            self.cb_day.setCurrentIndex(day_idx)
        self._on_frequency_changed()

    def _refresh_worker_status(self):
        """État "en cours"/"arrêté" déduit du dernier échantillon de ressources — c'est le
        même battement de cœur déjà utilisé par la vue Ressources, pas une nouvelle mesure.
        Un échantillon plus vieux que 2x l'intervalle configuré est considéré périmé (le worker
        a probablement été arrêté ou n'a jamais démarré)."""
        from datetime import datetime
        from database import db_manager as db

        settings = db.get_app_settings()
        if settings.execution_mode != "BACKGROUND":
            self.lbl_worker_status.setText("Sans objet en mode « Dans l'application seulement »")
            self.lbl_worker_status.setStyleSheet(
                f"color: {COLORS['text_muted']}; font-size: 12px; background: transparent;")
            return

        sample = db.get_latest_resource_sample()
        if not sample:
            self._set_worker_status_dot("Arrêté (aucun signal reçu)", COLORS["danger"])
            return

        age_s = (datetime.utcnow() - sample.timestamp).total_seconds()
        if age_s <= 2 * settings.resource_sample_interval_s:
            self._set_worker_status_dot(
                f"Actif (dernier signal {fmt_relative(sample.timestamp)})", COLORS["success"])
        else:
            self._set_worker_status_dot(
                f"Arrêté (dernier signal {fmt_relative(sample.timestamp)})", COLORS["danger"])

    def _set_worker_status_dot(self, text: str, color: str):
        """Point coloré en rich text (A6) — même patron que
        dashboard_view.py::_set_legend_text, pas un nouveau composant."""
        self.lbl_worker_status.setText(f'<span style="color:{color};">●</span>&nbsp;{text}')
        self.lbl_worker_status.setStyleSheet(
            f"color: {COLORS['text_main']}; font-size: 12px; background: transparent;")

    # ── Navigation catégories / recherche ─────

    def select_category(self, key: str):
        """Point d'entrée public — utilisé par le raccourci 🔔 du Dashboard pour amener
        directement sur la catégorie Notifications."""
        self.inp_search.clear()
        self._select_category(key)

    def _select_category(self, key: str):
        self._active_category = key
        cat = next(c for c in _CATEGORIES if c["key"] == key)
        self._detail_title.setText(cat["label"])
        self._detail_sub.setText(cat["desc"])
        self._search_help_lbl.setVisible(False)
        for row in self._category_rows.values():
            row["count_lbl"].setVisible(False)
            row["frame"].setGraphicsEffect(None)
        for k, row in self._category_rows.items():
            active = k == key
            icon_color = COLORS["accent"] if active else COLORS["text_dim"]
            icon = _icon(row["icon_name"], icon_color)
            if icon:
                row["icon_lbl"].setPixmap(icon.pixmap(16, 16))
            row["frame"].setStyleSheet(
                f"QFrame#category_row {{ border: none; border-radius: 5px; "
                f"background: {COLORS['bg_active'] if active else 'transparent'}; "
                f"border-left: 2px solid {COLORS['accent'] if active else 'transparent'}; }}"
                f"QFrame#category_row:hover {{ background: "
                f"{COLORS['bg_active'] if active else COLORS['bg_hover']}; }}"
            )
        for row in self._row_widgets:
            row["chip"].setVisible(False)
            row["wrapper"].setVisible(row["category"] == key)
            row["label_lbl"].setText(_highlight(row["label_text"], ""))
            if row["desc_lbl"]:
                row["desc_lbl"].setText(_highlight(row["desc_text"], ""))
        self._on_frequency_changed()   # ré-applique le masquage conditionnel de "Jour"

    def _on_search_changed(self, text: str):
        query = text.strip().lower()
        if not query:
            self._select_category(self._active_category)
            return

        counts = {cat["key"]: 0 for cat in _CATEGORIES}
        for row in self._row_widgets:
            match = query in row["label"] or query in row["desc"]
            row["wrapper"].setVisible(match)
            row["chip"].setVisible(match)
            row["label_lbl"].setText(_highlight(row["label_text"], query if match else ""))
            if row["desc_lbl"]:
                row["desc_lbl"].setText(_highlight(row["desc_text"], query if match else ""))
            if match:
                counts[row["category"]] += 1

        for key, row in self._category_rows.items():
            count = counts[key]
            row["frame"].setStyleSheet(
                f"QFrame#category_row {{ border: none; border-radius: 5px; background: transparent; "
                f"border-left: 2px solid transparent; }}"
                f"QFrame#category_row:hover {{ background: {COLORS['bg_hover']}; }}"
            )
            if count:
                row["count_lbl"].setText(str(count))
                row["count_lbl"].setVisible(True)
                row["frame"].setGraphicsEffect(None)
            else:
                row["count_lbl"].setVisible(False)
                effect = QGraphicsOpacityEffect(row["frame"])
                effect.setOpacity(0.38)
                row["frame"].setGraphicsEffect(effect)

        total = sum(counts.values())
        n_categories = sum(1 for c in counts.values() if c)
        # background-color, pas border : le sous-ensemble de rich text de Qt (QLabel) n'applique
        # pas "border" sur un <span> inline (confirmé isolément, même famille de limite que <mark>
        # non supporté) — un fond discret rend la même intention de "touche" que la bordure de la
        # maquette, sans la garder invisible à l'écran.
        # Attribut style en quotes simples : FONT_MONO_STACK contient des guillemets doubles
        # ("JetBrains Mono", "Consolas", monospace) qui, dans un attribut style="..." en
        # guillemets doubles, terminaient l'attribut prématurément après `font-family:"` — tout le
        # reste (dont background-color) devenait du texte d'attribut invalide, jamais appliqué.
        # Confirmé en isolant le rendu (fond invisible malgré une balise correcte en apparence).
        escape_hint = (
            f"<span style='font-family:{FONT_MONO_STACK}; font-size:10.5px; "
            f"background-color:{COLORS['border']}; border-radius:4px; padding:1px 5px;'>Échap</span>"
        )
        self._search_help_lbl.setText(
            f"{total} réglage{'s' if total > 1 else ''} dans {n_categories} "
            f"catégorie{'s' if n_categories > 1 else ''} · la recherche porte sur les noms et "
            f"les descriptions · {escape_hint} pour revenir"
        )
        self._search_help_lbl.setVisible(True)

        self._detail_title.setText("Résultats")
        self._detail_sub.setText(f"Paramètres correspondant à « {text.strip()} »")

    def _on_frequency_changed(self):
        weekly = self.cb_frequency.currentData() == "WEEKLY"
        for row in self._row_widgets:
            if row["label"] == "jour":
                row["wrapper"].setVisible(weekly and self._active_category == "notifications"
                                           and not self.inp_search.text().strip())

    # ── Enregistrement ────────────────────────

    @staticmethod
    def _is_valid_time(value: str) -> bool:
        try:
            h, m = value.split(":")
            return 0 <= int(h) <= 23 and 0 <= int(m) <= 59
        except (ValueError, AttributeError):
            return False

    def _reset_save_status_lbl(self):
        """État de repos du texte à gauche du pied (A8) — "Aucune modification", maquette
        Parametres.html. Pas une vraie détection de modification (ce serait C1, gated) : affiché
        tant qu'aucun enregistrement n'est en cours de confirmation, qu'un champ ait été touché
        ou non."""
        self._save_status_icon.setVisible(False)
        self._save_status_lbl.setText("Aucune modification")
        self._save_status_lbl.setStyleSheet(
            f"color: {COLORS['text_muted']}; font-size: 12.5px; font-weight: 400; border: none; "
            f"background: transparent;")

    def _on_save(self):
        digest_enabled = self.chk_digest_enabled.isChecked()
        if digest_enabled:
            if not self.cb_smtp.currentData():
                QMessageBox.warning(self, "Champ requis", "Sélectionner un profil SMTP.")
                return
            if not self.inp_recipients.text().strip():
                QMessageBox.warning(self, "Champ requis", "Saisir au moins un destinataire.")
                return
        if not self._is_valid_time(self.inp_time.text().strip()):
            QMessageBox.warning(self, "Champ invalide", "Heure d'envoi invalide (format HH:MM).")
            return
        if self.cb_timezone.currentText().strip() not in _TIMEZONES:
            QMessageBox.warning(
                self, "Champ invalide",
                "Fuseau horaire non reconnu — choisissez-en un dans la liste proposée.",
            )
            return

        from database import db_manager as db

        previous_mode = db.get_app_settings().execution_mode
        new_mode = self.cb_execution_mode.currentData()

        db.update_app_settings(
            timezone=self.cb_timezone.currentText(),
            misfire_grace_time_min=self.spin_misfire.value(),
            coalesce_missed_runs=self.chk_coalesce.isChecked(),
            max_concurrent_runs=self.spin_max_concurrent.value(),
            execution_mode=new_mode,
            kerberos_reuse_valid_ticket=self.chk_kerberos_reuse.isChecked(),
            kerberos_ticket_grace_period_s=self.spin_kerberos_grace.value(),
            log_level=self.cb_log_level.currentText(),
            log_max_bytes=self.spin_log_mb.value() * 1_000_000,
            log_backup_count=self.spin_log_backups.value(),
            dashboard_refresh_s=self.spin_dashboard_refresh.value(),
            pipelines_refresh_s=self.spin_pipelines_refresh.value(),
            live_log_refresh_s=self.spin_live_log_refresh.value(),
            trace_glow_refresh_s=self.spin_trace_glow_refresh.value(),
            resource_sample_interval_s=self.spin_sample_interval.value(),
            resource_sample_retention_days=self.spin_sample_retention.value(),
        )
        db.update_notification_settings(
            digest_enabled=digest_enabled,
            digest_smtp_profile_id=self.cb_smtp.currentData(),
            digest_recipients=self.inp_recipients.text().strip(),
            digest_frequency=self.cb_frequency.currentData(),
            digest_time=self.inp_time.text().strip(),
            digest_day_of_week=self.cb_day.currentData(),
        )

        import logging
        logging.getLogger().setLevel(self.cb_log_level.currentText())

        # Mode d'exécution en arrière-plan (chantier worker) — jamais délégué ET local à la
        # fois pour une même sauvegarde (voir core/execution_mode.py) ; le comportement du
        # process desktop courant (son propre scheduler) ne change qu'au redémarrage, mais la
        # tâche planifiée Windows et le worker déjà lancé, eux, réagissent tout de suite.
        from core.execution_mode import request_reload
        if not request_reload():
            try:
                from core.scheduler import get_scheduler
                sched = get_scheduler()
                sched.apply_settings()
                sched.refresh_digest_job()
            except RuntimeError:
                pass   # scheduler pas encore démarré (ne devrait pas arriver depuis l'UI)

        background_activation_failed = False
        if new_mode != previous_mode:
            from core.task_scheduler import register_logon_task, unregister_logon_task
            if new_mode == "BACKGROUND":
                if not register_logon_task():
                    # Échec réel de terrain (compte standard bloqué par une politique IT,
                    # "Accès refusé") : sans ce filet, AppSettings.execution_mode restait quand
                    # même à BACKGROUND (déjà écrit par le db.update_app_settings() ci-dessus) —
                    # l'appli desktop cesse alors d'exécuter ses propres pipelines planifiés
                    # (comportement normal du mode BACKGROUND, "c'est le worker qui s'en
                    # charge"), mais le worker, lui, ne démarre jamais (aucune tâche Windows
                    # enregistrée) : plus aucun pipeline planifié ne tournait, silencieusement,
                    # avec pour seul indice une ligne de log. On revient donc explicitement en
                    # "Dans l'application seulement" plutôt que de laisser l'utilisateur dans cet
                    # état cassé.
                    db.update_app_settings(execution_mode=previous_mode)
                    background_activation_failed = True
            else:
                unregister_logon_task()
                db.enqueue_worker_command("SHUTDOWN")
            self._refresh_worker_status()

        # Bandeau persistant (A7) — reste visible jusqu'à "Fermer" ou un nouvel enregistrement
        # (recalculé ici à chaque appel), contrairement au texte du pied ci-dessous qui s'efface
        # tout seul.
        self._failure_banner.setVisible(background_activation_failed)

        # Confirmation non bloquante (pas de QMessageBox.information ici, volontairement) : un
        # "Enregistrer" qu'on peut cliquer plusieurs fois de suite sans devoir fermer une boîte
        # de dialogue à chaque fois est plus confortable sur un écran de paramètres — et ça évite
        # tout risque de blocage en environnement offscreen (tests) où rien ne clique le bouton.
        if background_activation_failed:
            self._save_status_icon.setPixmap(_icon("fa5s.exclamation-circle", COLORS["danger"]).pixmap(14, 14))
            self._save_status_icon.setVisible(True)
            self._save_status_lbl.setStyleSheet(
                f"color: {COLORS['danger']}; font-size: 12.5px; font-weight: 600; "
                f"border: none; background: transparent;")
            # Texte exact de Parametres-refus.html (footer) : la précision "contactez votre
            # support informatique" n'y figure pas — elle n'existe que dans le corps du bandeau
            # persistant ci-dessus (_build_failure_banner), pas dupliquée ici (écart corrigé).
            self._save_status_lbl.setText(
                "Échec de l'activation du mode arrière-plan (accès refusé). "
                "Le mode « Dans l'application seulement » reste actif."
            )
            # Le mode était resté sur BACKGROUND à l'écran (choix de l'utilisateur au moment du
            # clic) alors que la base est revenue à previous_mode ci-dessus : sans ce retour
            # explicite, le menu déroulant affichait un mode différent de celui réellement actif
            # (écart constaté en capturant, voir Parametres-refus.html qui montre bien le menu
            # revenu sur "Dans l'application seulement").
            idx = self.cb_execution_mode.findData(previous_mode)
            if idx >= 0:
                self.cb_execution_mode.setCurrentIndex(idx)
            QTimer.singleShot(10000, self._reset_save_status_lbl)
        else:
            self._save_status_icon.setPixmap(_icon("fa5s.check", COLORS["success"]).pixmap(14, 14))
            self._save_status_icon.setVisible(True)
            self._save_status_lbl.setStyleSheet(
                f"color: {COLORS['success']}; font-size: 12.5px; font-weight: 600; "
                f"border: none; background: transparent;")
            # Texte simplifié à "Enregistré" (Parametres-enregistre.html) : la mention de ce qui
            # attend un redémarrage appartient au bandeau de succès détaillé de C4 (gated, pas
            # construit dans ce lot) — pas un texte de repli inventé à sa place.
            self._save_status_lbl.setText("Enregistré")
            QTimer.singleShot(4000, self._reset_save_status_lbl)

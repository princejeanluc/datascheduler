"""
DataScheduler — ui/step_editor/step_type_chooser_dialog.py
Dialogue de choix du type d'une nouvelle étape : recherche en direct, regroupement par
catégorie, défilement — pensé pour rester utilisable avec beaucoup plus de types qu'aujourd'hui
(voir docs/ARCHITECTURE.md, section sélecteur de type d'étape).
"""

import json

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QFrame,
    QScrollArea, QWidget, QInputDialog, QMessageBox,
)
from PySide6.QtCore import Qt, QSize
from ui.styles import COLORS, DIALOG_STYLE
from core.steps import is_routing_node, known_step_types
from .common import STEP_META, _icon

# Ordre d'affichage des sections — indépendant de l'ordre d'insertion de STEP_META.
_CATEGORY_ORDER = [
    "Extraction & chargement",
    "Transfert & diffusion",
    "Exécution & scripts",
    "Notification & intégration",
    "Contrôle de flux",
]

_DESCRIPTIONS = {
    "DB_EXTRACT":     "Connexion à une base (Oracle, MySQL, PostgreSQL, SQL Server), exécution SQL, export CSV vers fichier temporaire.",
    "FTP_UPLOAD":     "Upload du fichier produit vers un serveur FTP / FTPS / SFTP.",
    "LOCAL_COPY":     "Copie du fichier produit dans un dossier local (avec tokens datetime).",
    "COMPRESS":       "Compression du fichier produit en archive ZIP (utile avant une diffusion limitée en taille).",
    "PYTHON_SCRIPT":  "Exécution d'un script Python avec arguments (tokens datetime + contexte).",
    "SPARK_SQL":      "Requête Spark SQL sur un cluster Hadoop via un nœud edge (SSH + Kerberos).",
    "SQOOP_EXPORT":   "Export d'une table Hive/HCatalog vers Oracle via Sqoop, sur un nœud edge (SSH + Kerberos).",
    "SQOOP_IMPORT":   "Import d'une table Oracle vers Hive/HCatalog via Sqoop, sur un nœud edge (SSH + Kerberos).",
    "DB_EXECUTE":     "Exécution d'une instruction SQL/PLSQL (DML, DDL, procédure) sans extraction, tout moteur.",
    "FTP_DOWNLOAD":   "Téléchargement d'un fichier distant (FTP / FTPS / SFTP) comme source du pipeline.",
    "DB_LOAD":        "Chargement du fichier produit (CSV) dans une table, tout moteur.",
    "EMAIL_NOTIFY":   "Envoi d'un email, avec le fichier produit en pièce jointe optionnelle.",
    "HTTP_REQUEST":   "Appel d'une API REST / webhook, avec le fichier produit en option.",
    "CONDITION":      "Évalue une expression sur le contexte et route vers l'une de ses deux "
                      "sorties (Vrai/Faux) — à connecter dans le canevas.",
    "GATEWAY_PARALLEL": "Marque explicitement un embranchement parallèle — le flux se divise en "
                      "plusieurs branches actives simultanément.",
    "GATEWAY_JOIN":   "Synchronise plusieurs branches convergentes — ET (toutes doivent réussir) "
                      "ou OU (une seule suffit), artefact désigné explicitement.",
    "EXTRACT_VARIABLES": "Extrait des colonnes d'un fichier source (une seule ligne) vers des "
                      "variables (var:nom), réutilisables dans une Condition ou un champ templaté.",
    "SET_VARIABLE":   "Calcule une ou plusieurs variables (var:nom) à partir d'une expression "
                      "(arithmétique, fonctions date/texte), sans fichier source requis.",
}


class StepTypeChooserDialog(QDialog):
    """Dialogue de sélection du type d'étape à ajouter."""

    def __init__(self, parent=None, include_routing_nodes: bool = False):
        super().__init__(parent)
        self.chosen_type: str = ""
        # Config préremplie si le choix vient de la section "Mes modèles" (chantier bibliothèque
        # d'étapes réutilisables) — {} sinon, comportement inchangé pour un choix de type normal.
        self.chosen_config: dict = {}
        self._include_routing_nodes = include_routing_nodes
        self._cards: list[tuple[QFrame, str]] = []          # (carte, texte de recherche)
        self._category_sections: dict[str, tuple[QLabel, list[QFrame]]] = {}
        self._template_card_set: set = set()   # cartes modèle actuelles, pour les retirer de
                                                # self._cards avant un _refresh_templates_section()
        self.setWindowTitle("Ajouter une étape")
        self.setStyleSheet(DIALOG_STYLE)
        self.resize(460, 560)
        self._build_ui()
        self.inp_search.setFocus()

    def _visible_types(self) -> dict:
        # Un nœud de routage (CONDITION, GATEWAY_PARALLEL, GATEWAY_JOIN — IS_ROUTING_NODE) n'a de
        # sens que connecté par arêtes dans le canevas ; jamais proposé dans l'éditeur linéaire
        # (chantier Gateway — généralisé depuis un littéral "CONDITION" codé en dur, qui n'aurait
        # exclu ni GATEWAY_PARALLEL ni GATEWAY_JOIN).
        if self._include_routing_nodes:
            return dict(_DESCRIPTIONS)
        return {k: v for k, v in _DESCRIPTIONS.items() if not is_routing_node(k)}

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 16)
        root.setSpacing(10)

        title = QLabel("Choisir le type d'étape")
        title.setStyleSheet(
            f"font-size: 15px; font-weight: 700; color: {COLORS['text_main']};"
        )
        root.addWidget(title)

        self.inp_search = QLineEdit()
        self.inp_search.setPlaceholderText("Rechercher un type d'étape…")
        self.inp_search.setFixedHeight(34)
        self.inp_search.setStyleSheet(
            f"QLineEdit {{ background: {COLORS['bg_card']}; border: 1px solid {COLORS['border']}; "
            f"border-radius: 4px; padding: 6px 10px; color: {COLORS['text_main']}; font-size: 13px; }}"
            f"QLineEdit:focus {{ border-color: {COLORS['accent']}; }}"
        )
        self.inp_search.textChanged.connect(self._on_search_changed)
        root.addWidget(self.inp_search)

        sep = QFrame(); sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet(f"background: {COLORS['border']}; max-height: 1px;")
        root.addWidget(sep)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        inner = QWidget()
        scroll.setWidget(inner)
        root.addWidget(scroll, stretch=1)

        list_layout = QVBoxLayout(inner)
        list_layout.setContentsMargins(0, 4, 4, 4)
        list_layout.setSpacing(8)

        # "Mes modèles" (chantier bibliothèque d'étapes réutilisables) — en tête, avant les
        # catégories de types. Conteneur propre reconstruit entièrement à chaque renommage/
        # suppression (_refresh_templates_section), sans toucher au reste de list_layout.
        self._templates_container = QWidget()
        self._templates_layout = QVBoxLayout(self._templates_container)
        self._templates_layout.setContentsMargins(0, 0, 0, 0)
        self._templates_layout.setSpacing(8)
        list_layout.addWidget(self._templates_container)
        self._refresh_templates_section()

        descriptions = self._visible_types()
        for category in _CATEGORY_ORDER:
            types_in_category = [t for t in descriptions if STEP_META[t]["category"] == category]
            if not types_in_category:
                continue

            header = QLabel(category.upper())
            header.setStyleSheet(
                f"color: {COLORS['text_muted']}; font-size: 10.5px; font-weight: 700; "
                f"letter-spacing: 0.6px; margin-top: 4px;"
            )
            list_layout.addWidget(header)

            frames = []
            for step_type in types_in_category:
                card = self._make_card(step_type, descriptions[step_type])
                list_layout.addWidget(card)
                search_text = f"{STEP_META[step_type]['label']} {descriptions[step_type]} {category}".lower()
                self._cards.append((card, search_text))
                frames.append(card)
            self._category_sections[category] = (header, frames)

        list_layout.addStretch()

        root.addSpacing(6)
        btn_cancel = QPushButton("Annuler"); btn_cancel.setObjectName("secondary")
        btn_cancel.setFixedHeight(34); btn_cancel.clicked.connect(self.reject)
        root.addWidget(btn_cancel, alignment=Qt.AlignRight)

    # ── "Mes modèles" (chantier bibliothèque d'étapes réutilisables) ────

    def _refresh_templates_section(self):
        """(Re)construit entièrement la section "Mes modèles" — appelée une fois à la
        construction du dialogue, puis après chaque renommage/suppression (jamais besoin de
        toucher aux catégories de types, construites séparément et une seule fois)."""
        from database import db_manager as db

        while self._templates_layout.count():
            item = self._templates_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

        # Retire les anciennes cartes modèle de self._cards (la recherche live itère cette
        # liste) avant de les reconstruire — les cartes de type normal n'y sont jamais touchées.
        self._cards = [(c, s) for c, s in self._cards if c not in self._template_card_set]
        self._template_card_set = set()

        try:
            raw_templates = db.get_step_templates()
        except RuntimeError:
            # Base non initialisée (ex. ce dialogue construit directement dans un test sans
            # fixture test_db) — "Mes modèles" est une section optionnelle, jamais un prérequis
            # pour ajouter une étape normalement ; même tolérance défensive que
            # PipelinesView._schedule_if_possible() pour un scheduler non initialisé.
            raw_templates = []
        templates = [t for t in raw_templates if t.step_type in known_step_types()]
        if not templates:
            # Modèle dont le type a disparu : exclu silencieusement de la liste (vue de
            # navigation passive, jamais une erreur bloquante — contrairement à plan_import()).
            self._category_sections.pop("Mes modèles", None)
            return

        header = QLabel("MES MODÈLES")
        header.setStyleSheet(
            f"color: {COLORS['text_muted']}; font-size: 10.5px; font-weight: 700; "
            f"letter-spacing: 0.6px; margin-top: 4px;"
        )
        self._templates_layout.addWidget(header)

        frames = []
        for template in templates:
            card = self._make_template_card(template)
            self._templates_layout.addWidget(card)
            meta = STEP_META[template.step_type]
            search_text = f"{template.name} {meta['label']} mes modèles".lower()
            self._cards.append((card, search_text))
            self._template_card_set.add(card)
            frames.append(card)
        self._category_sections["Mes modèles"] = (header, frames)

    def _make_template_card(self, template) -> QFrame:
        from ui.main_window.widgets import _action_btn
        meta = STEP_META[template.step_type]

        card = QFrame()
        card.setCursor(Qt.PointingHandCursor)
        card.setStyleSheet(
            f"QFrame {{ background: {COLORS['bg_card']}; border: 1px solid {COLORS['border']}; "
            f"border-radius: 6px; }}"
            f"QFrame:hover {{ border-color: {meta['color']}; background: {meta['color']}11; }}"
        )
        hl = QHBoxLayout(card)
        hl.setContentsMargins(14, 10, 14, 10)
        hl.setSpacing(10)

        dot = QLabel()
        icon = _icon(meta.get("icon", "fa5s.circle"), meta["color"])
        if icon:
            dot.setPixmap(icon.pixmap(QSize(18, 18)))
        dot.setStyleSheet("background: transparent; border: none;")
        dot.setFixedWidth(20)

        info_col = QVBoxLayout(); info_col.setSpacing(2)
        lbl_name = QLabel(template.name)
        lbl_name.setStyleSheet(
            f"color: {COLORS['text_main']}; font-size: 13px; font-weight: 600; "
            f"background: transparent; border: none;"
        )
        lbl_type = QLabel(meta["label"])
        lbl_type.setStyleSheet(
            f"color: {COLORS['text_dim']}; font-size: 11px; "
            f"background: transparent; border: none;"
        )
        info_col.addWidget(lbl_name); info_col.addWidget(lbl_type)

        hl.addWidget(dot)
        hl.addLayout(info_col, stretch=1)

        # Boutons enfants — un QPushButton consomme toujours son propre relâchement de souris,
        # jamais propagé au mouseReleaseEvent de la carte parente (même assemblage que
        # _QueryCard._btn_del, ui/main_window/queries_view.py — vérifié, aucun garde-fou
        # supplémentaire nécessaire).
        btn_rename = _action_btn("fa5s.pen", object_name="secondary", tooltip="Renommer",
                                  size=(22, 22))
        btn_rename.clicked.connect(
            lambda _, tid=template.id, cur=template.name: self._on_rename_template(tid, cur)
        )
        hl.addWidget(btn_rename)

        btn_delete = _action_btn("fa5s.trash-alt", object_name="danger", tooltip="Supprimer",
                                  size=(22, 22))
        btn_delete.clicked.connect(
            lambda _, tid=template.id, nm=template.name: self._on_delete_template(tid, nm)
        )
        hl.addWidget(btn_delete)

        card.mouseReleaseEvent = lambda _, t=template: self._choose_template(t)
        return card

    def _on_rename_template(self, template_id: int, current_name: str):
        from database import db_manager as db
        new_name, ok = QInputDialog.getText(
            self, "Renommer le modèle", "Nom :", text=current_name,
        )
        new_name = new_name.strip()
        if not ok or not new_name:
            return
        new_name = db.unique_step_template_name(new_name, exclude_id=template_id)
        db.rename_step_template(template_id, new_name)
        self._refresh_templates_section()

    def _on_delete_template(self, template_id: int, name: str):
        from database import db_manager as db
        reply = QMessageBox.question(
            self, "Supprimer", f"Supprimer le modèle « {name} » ?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        db.delete_step_template(template_id)
        self._refresh_templates_section()

    def _choose_template(self, template):
        self.chosen_type = template.step_type
        self.chosen_config = json.loads(template.config_json or "{}")
        self.accept()

    def _make_card(self, step_type: str, desc: str) -> QFrame:
        meta = STEP_META[step_type]

        btn_row = QFrame()
        btn_row.setCursor(Qt.PointingHandCursor)
        btn_row.setStyleSheet(
            f"QFrame {{ background: {COLORS['bg_card']}; border: 1px solid {COLORS['border']}; "
            f"border-radius: 6px; }}"
            f"QFrame:hover {{ border-color: {meta['color']}; background: {meta['color']}11; }}"
        )
        hl = QHBoxLayout(btn_row)
        hl.setContentsMargins(14, 10, 14, 10)
        hl.setSpacing(14)

        dot = QLabel()
        icon = _icon(meta.get("icon", "fa5s.circle"), meta["color"])
        if icon:
            dot.setPixmap(icon.pixmap(QSize(18, 18)))
        dot.setStyleSheet("background: transparent; border: none;")
        dot.setFixedWidth(20)

        info_col = QVBoxLayout(); info_col.setSpacing(2)
        lbl_type = QLabel(meta["label"])
        lbl_type.setStyleSheet(
            f"color: {COLORS['text_main']}; font-size: 13px; font-weight: 600; "
            f"background: transparent; border: none;"
        )
        lbl_desc = QLabel(desc)
        lbl_desc.setStyleSheet(
            f"color: {COLORS['text_dim']}; font-size: 11px; "
            f"background: transparent; border: none;"
        )
        lbl_desc.setWordWrap(True)
        info_col.addWidget(lbl_type); info_col.addWidget(lbl_desc)

        hl.addWidget(dot)
        hl.addLayout(info_col, stretch=1)

        # Rendre la card cliquable via mousePressEvent override
        btn_row.mouseReleaseEvent = lambda _, t=step_type: self._choose(t)
        return btn_row

    def _on_search_changed(self, text: str):
        needle = text.strip().lower()
        for card, search_text in self._cards:
            card.setVisible(not needle or needle in search_text)
        for header, frames in self._category_sections.values():
            # isHidden() reflète l'état explicitement fixé par setVisible() ci-dessus,
            # indépendamment du fait que le dialogue lui-même ait déjà été affiché ou non
            # (isVisible() dépendrait aussi de la visibilité des parents).
            header.setVisible(any(not f.isHidden() for f in frames))

    def _choose(self, step_type: str):
        self.chosen_type = step_type
        self.accept()

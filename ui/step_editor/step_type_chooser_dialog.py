"""
DataScheduler — ui/step_editor/step_type_chooser_dialog.py
Dialogue de choix du type d'une nouvelle étape : recherche en direct, regroupement par
catégorie, défilement — pensé pour rester utilisable avec beaucoup plus de types qu'aujourd'hui
(voir docs/ARCHITECTURE.md, section sélecteur de type d'étape).
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QFrame,
    QScrollArea, QWidget,
)
from PySide6.QtCore import Qt, QSize
from ui.styles import COLORS, DIALOG_STYLE
from core.steps import is_routing_node
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
    "DB_EXECUTE":     "Exécution d'une instruction SQL/PLSQL (DML, DDL, procédure) sans extraction, tout moteur.",
    "FTP_DOWNLOAD":   "Téléchargement d'un fichier distant (FTP / FTPS / SFTP) comme source du pipeline.",
    "DB_LOAD":        "Chargement du fichier produit (CSV) dans une table, tout moteur.",
    "EMAIL_NOTIFY":   "Envoi d'un email, avec le fichier produit en pièce jointe optionnelle.",
    "HTTP_REQUEST":   "Appel d'une API REST / webhook, avec le fichier produit en option.",
    "CONDITION":      "Évalue une expression sur le contexte et route vers l'une de ses deux "
                      "sorties (Vrai/Faux) — à connecter dans le canevas.",
}


class StepTypeChooserDialog(QDialog):
    """Dialogue de sélection du type d'étape à ajouter."""

    def __init__(self, parent=None, include_routing_nodes: bool = False):
        super().__init__(parent)
        self.chosen_type: str = ""
        self._include_routing_nodes = include_routing_nodes
        self._cards: list[tuple[QFrame, str]] = []          # (carte, texte de recherche)
        self._category_sections: dict[str, tuple[QLabel, list[QFrame]]] = {}
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

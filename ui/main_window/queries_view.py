"""
DataScheduler — ui/main_window/queries_view.py
Vue Requêtes SQL : atelier maître-détail (chantier atelier SQL) — remplace le tableau + dialogue
modal historique (une popup à rouvrir pour chaque modification était le principal frein
utilisateur signalé). Bibliothèque à gauche (recherche sur nom/description ET corps SQL, pas
seulement le nom comme avant), éditeur plein cadre à droite — ui/sql_editor.py::SqlEditorWidget,
le même composant que la modale rapide ouverte depuis un dialogue de step ("+ Nouvelle requête
SQL"), jamais deux implémentations divergentes de l'édition SQL.

Sauvegarde explicite (bouton « Enregistrer »), jamais automatique à la frappe — un formatage ou
une correction en cours ne doit jamais être persisté par accident avant que l'utilisateur ait
décidé que la requête est prête.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QPushButton, QFrame, QListWidget, QListWidgetItem,
    QLabel, QLineEdit, QComboBox, QMessageBox, QFileDialog, QAbstractItemView, QSizePolicy,
)
from ui.styles import COLORS, FONT_MONO
from ui.sql_editor import SqlEditorWidget
from .widgets import _action_btn, _make_search_input


# ──────────────────────────────────────────────
#  CARTE DE LA LISTE (widget d'un QListWidgetItem)
# ──────────────────────────────────────────────

class _QueryCard(QFrame):
    def __init__(self, query, usage_count: int, parent_view: "QueriesView"):
        super().__init__()
        self.query_id = query.id
        self._view = parent_view
        self._active = False
        self.setCursor(Qt.PointingHandCursor)

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 8, 8, 8)
        root.setSpacing(3)

        top = QHBoxLayout(); top.setSpacing(6)
        name = QLabel(query.name)
        name.setStyleSheet(f"font-size: 12.5px; font-weight: 600; color: {COLORS['text_main']};")
        name.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        top.addWidget(name, stretch=1)

        badge = QLabel(f"{usage_count} pipeline(s)" if usage_count else "Aucun")
        badge_bg = "rgba(62,143,176,.18)" if usage_count else COLORS["bg_card"]
        badge_fg = COLORS["signal_pale"] if usage_count else COLORS["text_dim"]
        badge.setStyleSheet(
            f"background: {badge_bg}; color: {badge_fg}; font-size: 9.5px; font-weight: 700; "
            f"padding: 1px 6px; border-radius: 8px;"
        )
        top.addWidget(badge)

        btn_del = _action_btn("fa5s.trash-alt", object_name="danger", tooltip="Supprimer",
                              size=(20, 20))
        btn_del.clicked.connect(lambda: self._view._on_delete_query(self.query_id))
        top.addWidget(btn_del)
        root.addLayout(top)

        desc = QLabel(query.description or "—")
        desc.setStyleSheet(f"font-size: 10.5px; color: {COLORS['text_dim']};")
        desc.setWordWrap(False)
        root.addWidget(desc)

        preview_text = (query.sql_text or "").replace("\n", " ").strip()[:80]
        preview = QLabel(preview_text)
        preview.setStyleSheet(
            f"font-size: 9.5px; color: {COLORS['text_muted']}; font-family: {FONT_MONO};"
        )
        root.addWidget(preview)

        self._search_text = " ".join([
            query.name.lower(), (query.description or "").lower(), (query.sql_text or "").lower(),
        ])

        self.set_active(False)

    def matches(self, needle: str) -> bool:
        return not needle or needle in self._search_text

    def set_active(self, active: bool):
        self._active = active
        border = f"2px solid {COLORS['accent']}" if active else "1px solid transparent"
        bg = COLORS["bg_active"] if active else "transparent"
        self.setStyleSheet(
            f"QFrame {{ background: {bg}; border-left: {border}; border-radius: 4px; }}"
        )

    def mouseReleaseEvent(self, event):
        self._view._select_query(self.query_id)
        super().mouseReleaseEvent(event)


# ──────────────────────────────────────────────
#  VUE PRINCIPALE
# ──────────────────────────────────────────────

class QueriesView(QWidget):
    def __init__(self):
        super().__init__()
        self._active_id: int | None = None
        self._build_ui()
        self.refresh()

    # ── Construction ───────────────────────────

    def _build_ui(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_sidebar())

        vline = QFrame(); vline.setFrameShape(QFrame.VLine)
        vline.setStyleSheet(f"background: {COLORS['border']}; max-width: 1px;")
        root.addWidget(vline)

        root.addWidget(self._build_workshop(), stretch=1)

    def _build_sidebar(self) -> QWidget:
        panel = QWidget()
        panel.setFixedWidth(300)
        panel.setStyleSheet(f"background: {COLORS['bg_panel']};")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(16, 18, 16, 12)
        layout.setSpacing(8)

        title = QLabel("Requêtes SQL")
        title.setStyleSheet(f"font-size: 15px; font-weight: 700; color: {COLORS['text_main']};")
        subtitle = QLabel("Bibliothèque de requêtes réutilisables")
        subtitle.setStyleSheet(f"font-size: 11px; color: {COLORS['text_muted']};")
        layout.addWidget(title); layout.addWidget(subtitle)

        self.inp_search = _make_search_input("Rechercher (nom, description, SQL…)")
        self.inp_search.setMinimumWidth(0)
        self.inp_search.setMaximumWidth(16_777_215)   # occupe la largeur du panneau, pas 240px fixe
        self.inp_search.textChanged.connect(self._on_search_changed)
        layout.addWidget(self.inp_search)

        hint = QLabel("cherche aussi dans le corps SQL, pas seulement le nom")
        hint.setWordWrap(True)
        hint.setStyleSheet(f"font-size: 10px; color: {COLORS['text_muted']}; font-style: italic;")
        layout.addWidget(hint)

        btn_new = QPushButton("+ Nouvelle requête")
        btn_new.setFixedHeight(32)
        btn_new.clicked.connect(self._on_new_query)
        layout.addWidget(btn_new)

        self.list_widget = QListWidget()
        self.list_widget.setSelectionMode(QAbstractItemView.NoSelection)
        self.list_widget.setFocusPolicy(Qt.NoFocus)
        self.list_widget.setStyleSheet(
            "QListWidget { background: transparent; border: none; }"
            "QListWidget::item { border: none; padding: 0px; margin: 1px 0; }"
        )
        layout.addWidget(self.list_widget, stretch=1)

        self._empty_label = QLabel(
            "Aucune requête enregistrée — créez la première ci-dessus. Une requête est "
            "réutilisable par les étapes DB_EXTRACT, DB_EXECUTE et Spark SQL de vos pipelines."
        )
        self._empty_label.setWordWrap(True)
        self._empty_label.setAlignment(Qt.AlignCenter)
        self._empty_label.setStyleSheet(
            f"color: {COLORS['text_muted']}; font-size: 11px; font-style: italic; padding: 20px 8px;"
        )
        self._empty_label.setVisible(False)
        layout.addWidget(self._empty_label)

        return panel

    def _build_workshop(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QWidget()
        header.setStyleSheet(f"border-bottom: 1px solid {COLORS['border']};")
        h_layout = QVBoxLayout(header)
        h_layout.setContentsMargins(22, 14, 22, 12)
        h_layout.setSpacing(10)

        row1 = QHBoxLayout(); row1.setSpacing(10)
        self.inp_name = QLineEdit()
        self.inp_name.setStyleSheet(
            f"QLineEdit {{ background: transparent; border: none; font-size: 18px; "
            f"font-weight: 700; color: {COLORS['text_main']}; padding: 2px 4px; border-radius: 4px; }}"
            f"QLineEdit:hover, QLineEdit:focus {{ background: {COLORS['bg_card']}; }}"
        )
        sep_dot = QLabel("·")
        sep_dot.setStyleSheet(f"color: {COLORS['text_muted']};")
        self.inp_desc = QLineEdit()
        self.inp_desc.setPlaceholderText("Description courte (optionnel)")
        self.inp_desc.setStyleSheet(
            f"QLineEdit {{ background: transparent; border: none; font-size: 12px; "
            f"font-style: italic; color: {COLORS['text_dim']}; padding: 2px 4px; border-radius: 4px; }}"
            f"QLineEdit:hover, QLineEdit:focus {{ background: {COLORS['bg_card']}; }}"
        )
        row1.addWidget(self.inp_name)
        row1.addWidget(sep_dot)
        row1.addWidget(self.inp_desc, stretch=1)
        h_layout.addLayout(row1)

        row2 = QHBoxLayout(); row2.setSpacing(10)
        lbl_profile = QLabel("PROFIL")
        lbl_profile.setStyleSheet(
            f"font-size: 10.5px; color: {COLORS['text_muted']}; font-weight: 700; letter-spacing: .4px;"
        )
        self.cb_oracle = QComboBox()
        self.cb_oracle.setFixedWidth(160)
        row2.addWidget(lbl_profile); row2.addWidget(self.cb_oracle)
        row2.addStretch()

        self.btn_dup    = QPushButton("⧉ Dupliquer");     self.btn_dup.setObjectName("secondary")
        self.btn_import = QPushButton("⇪ Importer .sql"); self.btn_import.setObjectName("secondary")
        self.btn_export = QPushButton("⇩ Exporter .sql"); self.btn_export.setObjectName("secondary")
        self.btn_format = QPushButton("✦ Formater");      self.btn_format.setObjectName("secondary")
        self.btn_save   = QPushButton("Enregistrer")
        for b in (self.btn_dup, self.btn_import, self.btn_export, self.btn_format, self.btn_save):
            b.setFixedHeight(30)
            row2.addWidget(b)
        h_layout.addLayout(row2)

        layout.addWidget(header)

        self.editor = SqlEditorWidget()
        self.editor.set_placeholder(
            "SELECT col1, col2\nFROM ma_table\nWHERE condition = :param\nORDER BY col1"
        )
        layout.addWidget(self.editor, stretch=1)

        status = QWidget()
        status.setStyleSheet(f"background: {COLORS['bg_panel']}; border-top: 1px solid {COLORS['border']};")
        s_layout = QHBoxLayout(status)
        s_layout.setContentsMargins(18, 5, 18, 5)
        s_layout.setSpacing(14)
        self.lbl_usage = QLabel("Aucun pipeline")
        self.lbl_usage.setStyleSheet(
            f"background: {COLORS['bg_card']}; color: {COLORS['text_dim']}; font-size: 10px; "
            f"font-weight: 600; padding: 2px 8px; border-radius: 9px;"
        )
        s_layout.addWidget(self.lbl_usage)
        s_layout.addStretch()
        tokens = QLabel(
            "Jetons : {yyyy} {MM} {dd} {HH} {mm} {ss} {yyyyMMdd} {yyyyMMddHHmm}"
        )
        tokens.setStyleSheet(
            f"font-family: {FONT_MONO}; font-size: 10px; color: {COLORS['accent_pale']};"
        )
        s_layout.addWidget(tokens)
        layout.addWidget(status)

        self._workshop = panel
        self._set_workshop_enabled(False)

        self.btn_dup.clicked.connect(self._on_duplicate_query)
        self.btn_import.clicked.connect(self._on_import_sql)
        self.btn_export.clicked.connect(self._on_export_sql)
        self.btn_format.clicked.connect(self.editor.format_sql)
        self.btn_save.clicked.connect(self._on_save_query)

        return panel

    def _set_workshop_enabled(self, enabled: bool):
        self._workshop.setEnabled(enabled)

    # ── Chargement / rafraîchissement ──────────

    def refresh(self):
        from database import db_manager as db

        queries = db.get_sql_queries()
        self._load_oracle_profiles()

        self.list_widget.clear()
        self.list_widget.setVisible(bool(queries))
        self._empty_label.setVisible(not queries)

        ids = [q.id for q in queries]
        if self._active_id not in ids:
            self._active_id = ids[0] if ids else None

        for q in queries:
            used_by = db.find_pipelines_using_profile("sql_query_id", q.id)
            card = _QueryCard(q, len(used_by), self)
            item = QListWidgetItem()
            self.list_widget.addItem(item)
            self.list_widget.setItemWidget(item, card)
            item.setSizeHint(card.sizeHint())
            card.set_active(q.id == self._active_id)

        if self._active_id is not None:
            self._load_query_into_workshop(self._active_id)
        else:
            self._set_workshop_enabled(False)

        self._apply_search_filter()

    def _load_oracle_profiles(self):
        from database import db_manager as db
        current = self.cb_oracle.currentData()
        self.cb_oracle.blockSignals(True)
        self.cb_oracle.clear()
        self.cb_oracle.addItem("(aucun)", None)
        for p in db.get_oracle_profiles():
            self.cb_oracle.addItem(p.name, p.id)
        if current is not None:
            idx = self.cb_oracle.findData(current)
            if idx >= 0:
                self.cb_oracle.setCurrentIndex(idx)
        self.cb_oracle.blockSignals(False)

    def _load_query_into_workshop(self, query_id: int):
        from database import db_manager as db

        q = db.get_sql_query(query_id)
        if not q:
            self._set_workshop_enabled(False)
            return
        self.inp_name.setText(q.name)
        self.inp_desc.setText(q.description or "")
        self.editor.set_text(q.sql_text or "")
        if q.oracle_profile_id:
            idx = self.cb_oracle.findData(q.oracle_profile_id)
            self.cb_oracle.setCurrentIndex(idx if idx >= 0 else 0)
        else:
            self.cb_oracle.setCurrentIndex(0)

        used_by = db.find_pipelines_using_profile("sql_query_id", q.id)
        self.lbl_usage.setText(f"{len(used_by)} pipeline(s)" if used_by else "Aucun pipeline")
        self.lbl_usage.setToolTip(", ".join(used_by))
        self._set_workshop_enabled(True)

    def _apply_search_filter(self):
        needle = self.inp_search.text().strip().lower()
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            card = self.list_widget.itemWidget(item)
            item.setHidden(not card.matches(needle))

    # ── Sélection ──────────────────────────────

    def _select_query(self, query_id: int):
        if query_id == self._active_id:
            return
        self._active_id = query_id
        for i in range(self.list_widget.count()):
            card = self.list_widget.itemWidget(self.list_widget.item(i))
            card.set_active(card.query_id == query_id)
        self._load_query_into_workshop(query_id)

    def _on_search_changed(self, _text: str):
        self._apply_search_filter()

    # ── Actions ────────────────────────────────

    def _on_new_query(self):
        from database import db_manager as db

        existing_names = {q.name for q in db.get_sql_queries()}
        base = "NOUVELLE_REQUETE"
        name = base
        i = 2
        while name in existing_names:
            name = f"{base}_{i}"; i += 1
        q = db.create_sql_query(name=name, sql_text="SELECT *\nFROM \nWHERE ")
        self._active_id = q.id
        self.refresh()
        self.inp_name.setFocus()
        self.inp_name.selectAll()

    def _on_duplicate_query(self):
        from database import db_manager as db

        if self._active_id is None:
            return
        copy = db.duplicate_sql_query(self._active_id)
        if copy:
            self._active_id = copy.id
            self.refresh()

    def _on_delete_query(self, query_id: int):
        from database import db_manager as db

        used_by = db.find_pipelines_using_profile("sql_query_id", query_id)
        if used_by:
            names = ", ".join(used_by)
            msg = (
                f"Cette requête est utilisée par {len(used_by)} pipeline(s) : {names}.\n\n"
                f"La supprimer quand même ? Ces pipelines échoueront à leur prochaine exécution."
            )
        else:
            msg = "Supprimer cette requête ?"
        reply = QMessageBox.question(self, "Supprimer", msg, QMessageBox.Yes | QMessageBox.No)
        if reply != QMessageBox.Yes:
            return
        db.delete_sql_query(query_id)
        if query_id == self._active_id:
            self._active_id = None
        self.refresh()

    def _on_save_query(self):
        from database import db_manager as db

        if self._active_id is None:
            return
        name = self.inp_name.text().strip()
        sql  = self.editor.text().strip()
        if not name:
            QMessageBox.warning(self, "Champ requis", "Le nom de la requête ne peut pas être vide.")
            return
        if not sql:
            QMessageBox.warning(self, "Champ requis", "La requête SQL ne peut pas être vide.")
            return
        db.update_sql_query(
            self._active_id, name=name, sql_text=sql,
            description=self.inp_desc.text().strip() or None,
            oracle_profile_id=self.cb_oracle.currentData(),
        )
        self.refresh()

    def _on_import_sql(self):
        path, _ = QFileDialog.getOpenFileName(self, "Importer un fichier SQL", "", "Fichiers SQL (*.sql);;Tous les fichiers (*)")
        if not path:
            return
        try:
            text = open(path, "r", encoding="utf-8").read()
        except OSError as e:
            QMessageBox.warning(self, "Import impossible", f"Impossible de lire ce fichier : {e}")
            return
        self.editor.set_text(text)

    def _on_export_sql(self):
        if self._active_id is None:
            return
        default_name = (self.inp_name.text().strip() or "requete").lower() + ".sql"
        path, _ = QFileDialog.getSaveFileName(self, "Exporter en .sql", default_name,
                                              "Fichiers SQL (*.sql);;Tous les fichiers (*)")
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(self.editor.text())
        except OSError as e:
            QMessageBox.warning(self, "Export impossible", f"Impossible d'écrire ce fichier : {e}")

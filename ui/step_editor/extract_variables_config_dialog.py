"""
DataScheduler — ui/step_editor/extract_variables_config_dialog.py
Dialogue de configuration d'une étape EXTRACT_VARIABLES.

Premier dialogue de step à liste dynamique (chantier EXTRACT_VARIABLES) : la liste des
correspondances (colonne source → variable cible) se construit ligne par ligne via les boutons
"+ Ajouter"/"− Retirer" plutôt que d'être un nombre de champs fixe comme tous les autres
dialogues de step — voir le tableau `tbl_mappings` ci-dessous.
"""

from PySide6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QWidget, QFileDialog,
    QMessageBox, QScrollArea, QFrame, QComboBox, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView,
)
from PySide6.QtCore import Qt
from ui.styles import COLORS
from .base_config_dialog import _BaseStepConfigDialog
from .common import CSV_SEPARATORS, CSV_ENCODINGS

_MAPPING_TYPES = [
    ("Texte", "text"), ("Nombre", "number"), ("Date", "date"), ("Date et heure", "datetime"),
]
_COL_SOURCE, _COL_TYPE, _COL_FORMAT, _COL_TARGET = range(4)


class _ExtractVariablesConfigDialog(_BaseStepConfigDialog):
    STEP_TYPE = "EXTRACT_VARIABLES"

    def __init__(self, config: dict, parent=None, label: str = "", **_):
        super().__init__(config, parent, label,
                          retry_count=_.get("retry_count", 0),
                          retry_interval_s=_.get("retry_interval_s", 5),
                          run_always=_.get("run_always", False),
                          timeout_s=_.get("timeout_s", 0))
        self._prior_steps = _.get("prior_steps") or []
        self.setWindowTitle("Étape — Extraction de variables")
        self.setMinimumSize(600, 560)
        self._build_ui()
        self._prefill()

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("background: transparent;")
        content = QWidget()
        scroll.setWidget(content)
        outer.addWidget(scroll, stretch=1)

        root = QVBoxLayout(content); root.setContentsMargins(28, 24, 28, 20); root.setSpacing(16)
        title = QLabel("Extraction de variables")
        title.setStyleSheet(f"font-size: 15px; font-weight: 700; color: {COLORS['text_main']};")
        subtitle = QLabel(
            "Lit un fichier source déjà produit, attendu à UNE seule ligne de données (ex : "
            "résultat d'agrégation SQL), et publie les colonnes choisies comme variables — "
            "utilisables dans une Condition via var:nom, ou dans un champ templaté via {var:nom}."
        )
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 11px;")
        root.addWidget(title); root.addWidget(subtitle); root.addWidget(self._sep())

        form = self._form()
        self._add_label_row(form)
        self._add_execution_policy_row(form)
        self.cb_source = self._source_row(form, self._prior_steps)

        self.inp_explicit_path = self._input("ex : C:/data/resultat_{yyyyMMdd}.csv")
        src_row = QHBoxLayout(); src_row.setSpacing(6)
        src_row.addWidget(self.inp_explicit_path, stretch=1)
        btn_browse_src = QPushButton("Parcourir…"); btn_browse_src.setObjectName("secondary")
        btn_browse_src.setFixedHeight(34); btn_browse_src.setFixedWidth(100)
        btn_browse_src.clicked.connect(self._browse_source_file)
        src_row.addWidget(btn_browse_src)
        src_widget = QWidget(); src_widget.setLayout(src_row)
        form.addRow(self._lbl("Chemin source explicite"), src_widget)
        hint_src = QLabel(
            "Si renseigné, prioritaire sur la Source ci-dessus — utile quand cette étape est la "
            "seule du pipeline."
        )
        hint_src.setWordWrap(True)
        hint_src.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 10px; font-style: italic;")
        form.addRow("", hint_src)

        self.cb_sep = QComboBox(); self.cb_sep.setStyleSheet(self._combo_style())
        for lbl, val in CSV_SEPARATORS: self.cb_sep.addItem(lbl, val)
        self.cb_enc = QComboBox(); self.cb_enc.setStyleSheet(self._combo_style())
        for lbl, val in CSV_ENCODINGS: self.cb_enc.addItem(lbl, val)
        form.addRow(self._lbl("Séparateur CSV"), self.cb_sep)
        form.addRow(self._lbl("Encodage"),       self.cb_enc)
        root.addLayout(form)

        # Correspondances
        root.addWidget(self._sep())
        map_title = QLabel("Correspondances")
        map_title.setStyleSheet(f"font-size: 13px; font-weight: 600; color: {COLORS['text_main']};")
        root.addWidget(map_title)
        map_hint = QLabel(
            "Une ligne par valeur à extraire : « Colonne source » désigne l'en-tête tel qu'il "
            "apparaît dans le fichier ; « Variable cible » est le nom sous lequel la valeur "
            "devient disponible (var:nom). Format requis pour Date/Date-heure — mêmes tokens que "
            "partout ailleurs ({dd}/{MM}/{yyyy}...)."
        )
        map_hint.setWordWrap(True)
        map_hint.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 10.5px; font-style: italic;")
        root.addWidget(map_hint)

        self.tbl_mappings = QTableWidget(0, 4)
        self.tbl_mappings.setHorizontalHeaderLabels(
            ["Colonne source", "Type", "Format (date)", "Variable cible"]
        )
        self.tbl_mappings.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tbl_mappings.verticalHeader().setVisible(False)
        self.tbl_mappings.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tbl_mappings.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tbl_mappings.setMinimumHeight(160)
        self.tbl_mappings.setStyleSheet(
            f"QTableWidget {{ background: {COLORS['bg_card']}; border: 1px solid {COLORS['border']}; "
            f"border-radius: 4px; color: {COLORS['text_main']}; gridline-color: {COLORS['border']}; }}"
            f"QHeaderView::section {{ background: {COLORS['bg_active']}; color: {COLORS['text_dim']}; "
            f"padding: 4px; border: none; font-size: 11px; }}"
        )
        root.addWidget(self.tbl_mappings)

        btn_row = QHBoxLayout(); btn_row.setSpacing(8)
        btn_add = QPushButton("+ Ajouter"); btn_add.setObjectName("secondary")
        btn_add.setFixedHeight(30); btn_add.clicked.connect(lambda: self._add_mapping_row())
        btn_remove = QPushButton("− Retirer"); btn_remove.setObjectName("secondary")
        btn_remove.setFixedHeight(30); btn_remove.clicked.connect(self._remove_selected_row)
        btn_row.addWidget(btn_add); btn_row.addWidget(btn_remove); btn_row.addStretch()
        root.addLayout(btn_row)
        root.addStretch()

        footer = QVBoxLayout()
        footer.setContentsMargins(28, 0, 28, 20)
        self._buttons(footer)
        outer.addLayout(footer)

    # ── Table de correspondances ───────────────────────

    def _add_mapping_row(self, source: str = "", type_: str = "text",
                          date_format: str = "", target: str = ""):
        row = self.tbl_mappings.rowCount()
        self.tbl_mappings.insertRow(row)
        self.tbl_mappings.setItem(row, _COL_SOURCE, QTableWidgetItem(source))

        cb_type = QComboBox(); cb_type.setStyleSheet(self._combo_style())
        for lbl, val in _MAPPING_TYPES: cb_type.addItem(lbl, val)
        idx = cb_type.findData(type_)
        if idx >= 0:
            cb_type.setCurrentIndex(idx)
        cb_type.currentIndexChanged.connect(lambda _i, r=row: self._toggle_format_column(r))
        self.tbl_mappings.setCellWidget(row, _COL_TYPE, cb_type)

        fmt_item = QTableWidgetItem(date_format)
        fmt_item.setToolTip("ex : {dd}/{MM}/{yyyy}  ou  {dd}/{MM}/{yyyy} {HH}:{mm}:{ss}")
        self.tbl_mappings.setItem(row, _COL_FORMAT, fmt_item)
        self.tbl_mappings.setItem(row, _COL_TARGET, QTableWidgetItem(target))
        self._toggle_format_column(row)

    def _toggle_format_column(self, row: int):
        cb_type = self.tbl_mappings.cellWidget(row, _COL_TYPE)
        fmt_item = self.tbl_mappings.item(row, _COL_FORMAT)
        if cb_type is None or fmt_item is None:
            return
        needs_format = cb_type.currentData() in ("date", "datetime")
        flags = fmt_item.flags()
        if needs_format:
            fmt_item.setFlags(flags | Qt.ItemIsEnabled)
        else:
            fmt_item.setFlags(flags & ~Qt.ItemIsEnabled)
            fmt_item.setText("")

    def _remove_selected_row(self):
        rows = {i.row() for i in self.tbl_mappings.selectedIndexes()}
        for row in sorted(rows, reverse=True):
            self.tbl_mappings.removeRow(row)

    def _collect_mappings(self) -> list[dict]:
        mappings = []
        for row in range(self.tbl_mappings.rowCount()):
            source_item = self.tbl_mappings.item(row, _COL_SOURCE)
            target_item = self.tbl_mappings.item(row, _COL_TARGET)
            fmt_item    = self.tbl_mappings.item(row, _COL_FORMAT)
            cb_type     = self.tbl_mappings.cellWidget(row, _COL_TYPE)
            source = source_item.text().strip() if source_item else ""
            target = target_item.text().strip() if target_item else ""
            if not source and not target:
                continue
            mappings.append({
                "source": source,
                "target": target,
                "type": cb_type.currentData() if cb_type else "text",
                "date_format": fmt_item.text().strip() if fmt_item else "",
            })
        return mappings

    # ── Divers ───────────────────────

    def _browse_source_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Choisir le fichier source")
        if path:
            self.inp_explicit_path.setText(path)

    def _prefill(self):
        c = self._config
        self._set_combo(self.cb_source, c.get("reads_from_step_key"))
        self.inp_explicit_path.setText(c.get("explicit_path", ""))
        self._set_combo_by_data(self.cb_sep, c.get("csv_separator", ";"))
        self._set_combo_by_data(self.cb_enc, c.get("csv_encoding", "utf-8-sig"))
        for mapping in c.get("mappings") or []:
            self._add_mapping_row(
                mapping.get("source", ""), mapping.get("type", "text"),
                mapping.get("date_format", ""), mapping.get("target", ""),
            )
        if self.tbl_mappings.rowCount() == 0:
            self._add_mapping_row()

    def _collect_config(self) -> dict:
        return {
            "reads_from_step_key": self.cb_source.currentData(),
            "explicit_path": self.inp_explicit_path.text().strip(),
            "csv_separator": self.cb_sep.currentData(),
            "csv_encoding":  self.cb_enc.currentData(),
            "mappings": self._collect_mappings(),
        }

    def _on_ok(self):
        mappings = self._collect_mappings()
        if not mappings:
            QMessageBox.warning(self, "Champ requis", "Ajoutez au moins une correspondance.")
            return
        seen_targets = set()
        for m in mappings:
            if not m["source"] or not m["target"]:
                QMessageBox.warning(
                    self, "Correspondance incomplète",
                    "Chaque correspondance doit avoir une colonne source et une variable cible."
                )
                return
            if m["type"] in ("date", "datetime") and not m["date_format"]:
                QMessageBox.warning(
                    self, "Format requis",
                    f"La correspondance « {m['source']} » → « {m['target']} » est de type "
                    "Date/Date-heure : indiquez son format."
                )
                return
            if m["target"] in seen_targets:
                QMessageBox.warning(
                    self, "Variable en double",
                    f"La variable cible « {m['target']} » est utilisée plusieurs fois."
                )
                return
            seen_targets.add(m["target"])
        self.accept()

    @staticmethod
    def _set_combo_by_data(cb: QComboBox, value):
        for i in range(cb.count()):
            if cb.itemData(i) == value:
                cb.setCurrentIndex(i); return

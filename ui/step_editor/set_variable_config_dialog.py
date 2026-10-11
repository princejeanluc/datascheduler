"""
DataScheduler — ui/step_editor/set_variable_config_dialog.py
Dialogue de configuration d'une étape SET_VARIABLE : une liste dynamique d'assignations
(variable cible <- expression), même patron de liste que EXTRACT_VARIABLES
(extract_variables_config_dialog.py) mais réduit à 2 colonnes — pas de Source/CSV (cette étape
ne lit aucun fichier), pas de Type/Format (evaluate() renvoie déjà une valeur typée).
"""

from PySide6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QMessageBox, QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
)
from ui.styles import COLORS, FONT_MONO_STACK
from .base_config_dialog import _BaseStepConfigDialog
from core.expr_lang import compile_expression

_COL_TARGET, _COL_EXPRESSION = range(2)


class _SetVariableConfigDialog(_BaseStepConfigDialog):
    STEP_TYPE = "SET_VARIABLE"

    def __init__(self, config: dict, parent=None, label: str = "", **_):
        super().__init__(config, parent, label,
                          retry_count=_.get("retry_count", 0),
                          retry_interval_s=_.get("retry_interval_s", 5),
                          run_always=_.get("run_always", False),
                          timeout_s=_.get("timeout_s", 0))
        self.setWindowTitle("Étape — Définir une variable")
        self.setMinimumSize(560, 460)
        self._build_ui()
        self._prefill()

    def _build_ui(self):
        root = QVBoxLayout(self); root.setContentsMargins(28, 24, 28, 20); root.setSpacing(16)
        title = QLabel("Définir une variable")
        title.setStyleSheet(f"font-size: 15px; font-weight: 700; color: {COLORS['text_main']};")
        subtitle = QLabel(
            "Calcule une ou plusieurs variables (var:nom) à partir d'une expression — "
            "arithmétique, fonctions de date/texte, ou référence à rows_count/artifact:/var: "
            "déjà connus. Aucun fichier source requis, contrairement à Extraction de variables."
        )
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 11px;")
        root.addWidget(title); root.addWidget(subtitle); root.addWidget(self._sep())

        form = self._form()
        self._add_label_row(form)
        self._add_execution_policy_row(form)
        root.addLayout(form)

        root.addWidget(self._sep())
        map_title = QLabel("Assignations")
        map_title.setStyleSheet(f"font-size: 13px; font-weight: 600; color: {COLORS['text_main']};")
        root.addWidget(map_title)
        map_hint = QLabel(
            "Une ligne par variable : « Variable cible » est le nom sous lequel la valeur "
            "devient disponible (var:nom) ; « Expression » est évaluée via le même langage que "
            "Condition — ex : date_add(today(), -7), var:total * 1.2, rows_count."
        )
        map_hint.setWordWrap(True)
        map_hint.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 10.5px; font-style: italic;")
        root.addWidget(map_hint)

        self.tbl_assignments = QTableWidget(0, 2)
        self.tbl_assignments.setHorizontalHeaderLabels(["Variable cible", "Expression"])
        self.tbl_assignments.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tbl_assignments.verticalHeader().setVisible(False)
        self.tbl_assignments.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tbl_assignments.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tbl_assignments.setMinimumHeight(160)
        self.tbl_assignments.setStyleSheet(
            f"QTableWidget {{ background: {COLORS['bg_card']}; border: 1px solid {COLORS['border']}; "
            f"border-radius: 4px; color: {COLORS['text_main']}; gridline-color: {COLORS['border']}; }}"
            f"QHeaderView::section {{ background: {COLORS['bg_active']}; color: {COLORS['text_dim']}; "
            f"padding: 4px; border: none; font-size: 11px; }}"
        )
        root.addWidget(self.tbl_assignments)

        btn_row = QHBoxLayout(); btn_row.setSpacing(8)
        btn_add = QPushButton("+ Ajouter"); btn_add.setObjectName("secondary")
        btn_add.setFixedHeight(30); btn_add.clicked.connect(lambda: self._add_assignment_row())
        btn_remove = QPushButton("− Retirer"); btn_remove.setObjectName("secondary")
        btn_remove.setFixedHeight(30); btn_remove.clicked.connect(self._remove_selected_row)
        btn_row.addWidget(btn_add); btn_row.addWidget(btn_remove); btn_row.addStretch()
        root.addLayout(btn_row)

        hint = QLabel(
            "Grammaire : arithmétique + - * /, fonctions date_add(date, jours[, format]), now(), "
            "today(), fmt(valeur, format), concat(...), upper(s), lower(s), round(nombre, "
            "décimales), champs rows_count / artifact:<nom> / var:<nom>."
        )
        hint.setStyleSheet(
            f"color: {COLORS['text_muted']}; font-size: 10px; font-family: {FONT_MONO_STACK}; "
            f"font-style: italic;"
        )
        hint.setWordWrap(True)
        root.addWidget(hint)

        root.addStretch()
        self._buttons(root)

    def _add_assignment_row(self, target: str = "", expression: str = ""):
        row = self.tbl_assignments.rowCount()
        self.tbl_assignments.insertRow(row)
        self.tbl_assignments.setItem(row, _COL_TARGET, QTableWidgetItem(target))
        self.tbl_assignments.setItem(row, _COL_EXPRESSION, QTableWidgetItem(expression))

    def _remove_selected_row(self):
        rows = {i.row() for i in self.tbl_assignments.selectedIndexes()}
        for row in sorted(rows, reverse=True):
            self.tbl_assignments.removeRow(row)

    def _collect_assignments(self) -> list[dict]:
        assignments = []
        for row in range(self.tbl_assignments.rowCount()):
            target_item     = self.tbl_assignments.item(row, _COL_TARGET)
            expression_item = self.tbl_assignments.item(row, _COL_EXPRESSION)
            target     = target_item.text().strip() if target_item else ""
            expression = expression_item.text().strip() if expression_item else ""
            if not target and not expression:
                continue
            assignments.append({"target": target, "expression": expression})
        return assignments

    def _prefill(self):
        for assignment in self._config.get("assignments") or []:
            self._add_assignment_row(assignment.get("target", ""), assignment.get("expression", ""))
        if self.tbl_assignments.rowCount() == 0:
            self._add_assignment_row()

    def _collect_config(self) -> dict:
        return {"assignments": self._collect_assignments()}

    def _on_ok(self):
        assignments = self._collect_assignments()
        if not assignments:
            QMessageBox.warning(self, "Champ requis", "Ajoutez au moins une assignation.")
            return
        seen_targets = set()
        for a in assignments:
            if not a["target"] or not a["expression"]:
                QMessageBox.warning(
                    self, "Assignation incomplète",
                    "Chaque assignation doit avoir une variable cible et une expression."
                )
                return
            try:
                compile_expression(a["expression"])
            except ValueError as e:
                QMessageBox.warning(self, "Expression invalide", f"« {a['target']} » : {e}")
                return
            if a["target"] in seen_targets:
                QMessageBox.warning(
                    self, "Variable en double",
                    f"La variable cible « {a['target']} » est utilisée plusieurs fois."
                )
                return
            seen_targets.add(a["target"])
        self.accept()

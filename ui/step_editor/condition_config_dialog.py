"""
DataScheduler — ui/step_editor/condition_config_dialog.py
Dialogue de configuration d'une étape CONDITION (chantier 6a/6b) : une seule expression, évaluée
par core/steps/condition.py::ConditionStep. Pas de sélecteur "Source" (chantier 3) — un nœud
Condition n'consomme pas "le fichier", il évalue le contexte ; sa vraie source de données est
l'arête entrante dessinée dans l'éditeur graphique (chantier 6b).
"""

from PySide6.QtWidgets import QVBoxLayout, QLabel, QMessageBox
from ui.styles import COLORS
from .base_config_dialog import _BaseStepConfigDialog


class _ConditionConfigDialog(_BaseStepConfigDialog):
    STEP_TYPE = "CONDITION"

    def __init__(self, config: dict, parent=None, label: str = "", **_):
        super().__init__(config, parent, label,
                          retry_count=_.get("retry_count", 0),
                          run_always=_.get("run_always", False))
        self.setWindowTitle("Étape — Condition / Routeur")
        self._build_ui()
        self._prefill()

    def _build_ui(self):
        root = QVBoxLayout(self); root.setContentsMargins(28, 24, 28, 20); root.setSpacing(16)
        title = QLabel("Condition / Routeur")
        title.setStyleSheet(f"font-size: 15px; font-weight: 700; color: {COLORS['text_main']};")
        root.addWidget(title); root.addWidget(self._sep())

        form = self._form()
        self._add_label_row(form)
        self._add_execution_policy_row(form)

        self.inp_expression = self._input("ex : rows_count > 0")
        form.addRow(self._lbl("Expression *"), self.inp_expression)

        hint = QLabel(
            "Grammaire : <champ> <opérateur> <valeur>.  Champs : rows_count, artifact:<nom>.  "
            "Opérateurs : == != > >= < <=.  Deux sorties (Vrai/Faux) à connecter dans le canevas."
        )
        hint.setStyleSheet(
            f"color: {COLORS['text_muted']}; font-size: 10px; font-family: Consolas; "
            f"font-style: italic;"
        )
        hint.setWordWrap(True)
        form.addRow("", hint)

        root.addLayout(form)
        root.addStretch()
        self._buttons(root)

    def _prefill(self):
        self.inp_expression.setText(self._config.get("expression", ""))

    def _collect_config(self) -> dict:
        return {"expression": self.inp_expression.text().strip()}

    def _on_ok(self):
        if not self.inp_expression.text().strip():
            QMessageBox.warning(self, "Champ requis", "Saisir une expression.")
            return
        self.accept()

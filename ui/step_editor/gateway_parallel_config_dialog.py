"""
DataScheduler — ui/step_editor/gateway_parallel_config_dialog.py
Dialogue de configuration d'une étape GATEWAY_PARALLEL (chantier Gateway) — le plus minimal des
dialogues existants : aucun champ spécifique, juste le libellé et la politique d'exécution. Le
fork lui-même (une arête sortante par branche) se dessine dans le canevas, pas ici — voir
core/steps/gateway_parallel.py.
"""

from PySide6.QtWidgets import QVBoxLayout, QLabel
from ui.styles import COLORS
from .base_config_dialog import _BaseStepConfigDialog


class _GatewayParallelConfigDialog(_BaseStepConfigDialog):
    STEP_TYPE = "GATEWAY_PARALLEL"

    def __init__(self, config: dict, parent=None, label: str = "", **_):
        super().__init__(config, parent, label,
                          retry_count=_.get("retry_count", 0),
                          retry_interval_s=_.get("retry_interval_s", 5),
                          run_always=_.get("run_always", False),
                          timeout_s=_.get("timeout_s", 0))
        self.setWindowTitle("Étape — Passerelle parallèle")
        self._build_ui()
        self._prefill()

    def _build_ui(self):
        root = QVBoxLayout(self); root.setContentsMargins(28, 24, 28, 20); root.setSpacing(16)
        title = QLabel("Passerelle parallèle")
        title.setStyleSheet(f"font-size: 15px; font-weight: 700; color: {COLORS['text_main']};")
        root.addWidget(title); root.addWidget(self._sep())

        form = self._form()
        self._add_label_row(form)
        self._add_execution_policy_row(form)

        hint = QLabel(
            "Marque un embranchement parallèle — connectez son port de sortie à chaque branche "
            "directement dans le canevas, aucune configuration supplémentaire n'est nécessaire ici."
        )
        hint.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 10.5px; font-style: italic;")
        hint.setWordWrap(True)
        form.addRow("", hint)

        root.addLayout(form)
        root.addStretch()
        self._buttons(root)

    def _prefill(self):
        pass

    def _collect_config(self) -> dict:
        return {}

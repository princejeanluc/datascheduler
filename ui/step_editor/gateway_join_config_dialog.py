"""
DataScheduler — ui/step_editor/gateway_join_config_dialog.py
Dialogue de configuration d'une étape GATEWAY_JOIN (chantier Gateway) : le mode de jonction
(ET/OU, voir core/steps/gateway_join.py + get_join_mode() dans core/steps/__init__.py) et la
désignation optionnelle de la branche dont l'artefact continue en aval — jamais de fusion
implicite entre branches convergentes.
"""

from PySide6.QtWidgets import QVBoxLayout, QLabel, QComboBox
from ui.styles import COLORS
from .base_config_dialog import _BaseStepConfigDialog


class _GatewayJoinConfigDialog(_BaseStepConfigDialog):
    STEP_TYPE = "GATEWAY_JOIN"

    def __init__(self, config: dict, parent=None, label: str = "", prior_steps: list | None = None, **_):
        super().__init__(config, parent, label,
                          retry_count=_.get("retry_count", 0),
                          retry_interval_s=_.get("retry_interval_s", 5),
                          run_always=_.get("run_always", False),
                          timeout_s=_.get("timeout_s", 0))
        self._prior_steps = prior_steps or []
        self.setWindowTitle("Étape — Passerelle de jonction")
        self._build_ui()
        self._prefill()

    def _build_ui(self):
        root = QVBoxLayout(self); root.setContentsMargins(28, 24, 28, 20); root.setSpacing(16)
        title = QLabel("Passerelle de jonction")
        title.setStyleSheet(f"font-size: 15px; font-weight: 700; color: {COLORS['text_main']};")
        root.addWidget(title); root.addWidget(self._sep())

        form = self._form()
        self._add_label_row(form)
        self._add_execution_policy_row(form)

        self.cb_join_mode = QComboBox(); self.cb_join_mode.setStyleSheet(self._combo_style())
        self.cb_join_mode.addItem("OU — une seule branche suffit", "OR")
        self.cb_join_mode.addItem("ET — toutes les branches doivent réussir", "AND")
        self.cb_join_mode.setToolTip(
            "OU : avance dès qu'au moins une branche entrante a abouti, ignore les autres. "
            "ET : n'avance que si toutes les branches entrantes ont abouti — une seule "
            "indisponible fait échouer la jonction elle-même."
        )
        form.addRow(self._lbl("Mode de jonction"), self.cb_join_mode)

        self.cb_source = self._source_row(
            form, self._prior_steps,
            empty_label="Aucune (synchronisation seulement)",
            tooltip=(
                "Branche dont l'artefact continue en aval — il n'y a pas d'« étape précédente » "
                "unique pour une jonction à plusieurs branches. Laissé vide, la jonction ne fait "
                "que synchroniser : aucune donnée n'est transmise."
            ),
        )

        hint = QLabel(
            "Connectez chaque branche entrante directement dans le canevas — le nombre "
            "d'arêtes n'est pas limité ici."
        )
        hint.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 10.5px; font-style: italic;")
        hint.setWordWrap(True)
        form.addRow("", hint)

        root.addLayout(form)
        root.addStretch()
        self._buttons(root)

    def _prefill(self):
        join_mode = self._config.get("join_mode") or "OR"
        idx = self.cb_join_mode.findData(join_mode)
        if idx >= 0:
            self.cb_join_mode.setCurrentIndex(idx)
        self._set_combo(self.cb_source, self._config.get("artifact_source_step_key"))

    def _collect_config(self) -> dict:
        return {
            "join_mode": self.cb_join_mode.currentData(),
            "artifact_source_step_key": self.cb_source.currentData(),
        }

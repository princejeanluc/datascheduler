"""
DataScheduler — ui/step_editor/compress_config_dialog.py
Dialogue de configuration d'une étape COMPRESS.
"""

from PySide6.QtWidgets import QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QWidget, QFileDialog
from ui.styles import COLORS
from .base_config_dialog import _BaseStepConfigDialog


class _CompressConfigDialog(_BaseStepConfigDialog):
    STEP_TYPE = "COMPRESS"

    def __init__(self, config: dict, parent=None, label: str = "", **_):
        super().__init__(config, parent, label,
                          retry_count=_.get("retry_count", 0),
                          retry_interval_s=_.get("retry_interval_s", 5),
                          run_always=_.get("run_always", False),
                          timeout_s=_.get("timeout_s", 0))
        self._prior_steps = _.get("prior_steps") or []
        self.setWindowTitle("Étape — Compression (ZIP)")
        self._build_ui()
        self._prefill()

    def _build_ui(self):
        root = QVBoxLayout(self); root.setContentsMargins(28, 24, 28, 20); root.setSpacing(16)
        title = QLabel("Compression (ZIP)")
        title.setStyleSheet(f"font-size: 15px; font-weight: 700; color: {COLORS['text_main']};")
        root.addWidget(title); root.addWidget(self._sep())

        form = self._form()
        self._add_label_row(form)
        self._add_execution_policy_row(form)
        self.cb_source = self._source_row(form, self._prior_steps)

        self.inp_explicit_path = self._input("ex : C:/data/export_{yyyyMMdd}.csv")
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
            "seule du pipeline (ou compresse un fichier hors chaîne, ex : un export manuel)."
        )
        hint_src.setWordWrap(True)
        hint_src.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 10px; font-style: italic;")
        form.addRow("", hint_src)

        self.inp_archive_name = self._input("ex : export_{yyyyMMdd}.zip  (vide = nom source + .zip)")
        form.addRow(self._lbl("Nom de l'archive"), self.inp_archive_name)
        form.addRow("", self._tokens_hint())

        self.inp_output_name = self._output_name_row(form, default="archive")

        root.addLayout(form)
        root.addStretch()
        self._buttons(root)

    def _browse_source_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Choisir le fichier source")
        if path:
            self.inp_explicit_path.setText(path)

    def _prefill(self):
        c = self._config
        self._set_combo(self.cb_source, c.get("reads_from_step_key"))
        self.inp_explicit_path.setText(c.get("explicit_path", ""))
        self.inp_archive_name.setText(c.get("archive_name_tpl", ""))
        self.inp_output_name.setText(c.get("output_name", ""))

    def _collect_config(self) -> dict:
        return {
            "reads_from_step_key": self.cb_source.currentData(),
            "explicit_path": self.inp_explicit_path.text().strip(),
            "archive_name_tpl": self.inp_archive_name.text().strip(),
            "output_name": self.inp_output_name.text().strip(),
        }

    def _on_ok(self):
        self.accept()

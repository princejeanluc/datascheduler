"""
DataScheduler — ui/step_editor/local_copy_config_dialog.py
Dialogue de configuration d'une étape LOCAL_COPY.
"""

from PySide6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QWidget, QFileDialog,
    QMessageBox,
)
from ui.styles import COLORS
from .base_config_dialog import _BaseStepConfigDialog


class _LocalCopyConfigDialog(_BaseStepConfigDialog):
    STEP_TYPE = "LOCAL_COPY"

    def __init__(self, config: dict, parent=None, label: str = "", **_):
        super().__init__(config, parent, label,
                          retry_count=_.get("retry_count", 0),
                          run_always=_.get("run_always", False))
        self._prior_steps = _.get("prior_steps") or []
        self.setWindowTitle("Étape — Copie locale")
        self._build_ui()
        self._prefill()

    def _build_ui(self):
        root = QVBoxLayout(self); root.setContentsMargins(28, 24, 28, 20); root.setSpacing(16)
        title = QLabel("Copie locale")
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
            "seule du pipeline."
        )
        hint_src.setWordWrap(True)
        hint_src.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 10px; font-style: italic;")
        form.addRow("", hint_src)

        # Dossier destination
        self.inp_dest = self._input("ex : C:/backup/{yyyy}/{MM}/")
        dir_row = QHBoxLayout(); dir_row.setSpacing(6)
        dir_row.addWidget(self.inp_dest, stretch=1)
        btn_browse = QPushButton("Parcourir…"); btn_browse.setObjectName("secondary")
        btn_browse.setFixedHeight(34); btn_browse.setFixedWidth(100)
        btn_browse.clicked.connect(self._browse_dir)
        dir_row.addWidget(btn_browse)
        dir_widget = QWidget(); dir_widget.setLayout(dir_row)
        form.addRow(self._lbl("Dossier dest. *"), dir_widget)

        self.inp_file = self._input("ex : ventes_{yyyyMMdd}.csv  (vide = même nom)")
        form.addRow(self._lbl("Nom du fichier"),  self.inp_file)
        form.addRow("", self._tokens_hint())

        # Aperçu
        self.lbl_preview = QLabel()
        self.lbl_preview.setStyleSheet(
            f"color: {COLORS['accent']}; font-size: 12px; font-family: Consolas; "
            f"background: {COLORS['bg_card']}; border: 1px solid {COLORS['border']}; "
            f"border-radius: 5px; padding: 6px 10px;"
        )
        self.inp_dest.textChanged.connect(self._refresh_preview)
        self.inp_file.textChanged.connect(self._refresh_preview)
        form.addRow(self._lbl("Aperçu"), self.lbl_preview)
        root.addLayout(form)
        root.addStretch()
        self._buttons(root)

    def _browse_dir(self):
        path = QFileDialog.getExistingDirectory(self, "Choisir le dossier de destination")
        if path:
            self.inp_dest.setText(path)

    def _browse_source_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Choisir le fichier source")
        if path:
            self.inp_explicit_path.setText(path)

    def _refresh_preview(self):
        from core.steps.base import StepContext
        ctx  = StepContext()
        dest = ctx.resolve_tokens(self.inp_dest.text().strip() or "C:/backup/")
        fil  = ctx.resolve_tokens(self.inp_file.text().strip() or "fichier.csv")
        self.lbl_preview.setText(f"  {dest}/{fil}")

    def _prefill(self):
        c = self._config
        self._set_combo(self.cb_source, c.get("reads_from_step_key"))
        self.inp_explicit_path.setText(c.get("explicit_path", ""))
        self.inp_dest.setText(c.get("dest_dir", ""))
        self.inp_file.setText(c.get("filename_tpl", ""))
        self._refresh_preview()

    def _collect_config(self) -> dict:
        return {
            "dest_dir":     self.inp_dest.text().strip(),
            "filename_tpl": self.inp_file.text().strip(),
            "reads_from_step_key": self.cb_source.currentData(),
            "explicit_path": self.inp_explicit_path.text().strip(),
        }

    def _on_ok(self):
        if not self.inp_dest.text().strip():
            QMessageBox.warning(self, "Champ requis", "Saisir le dossier de destination.")
            return
        self.accept()

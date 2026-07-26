"""
DataScheduler — ui/step_editor/python_script_config_dialog.py
Dialogue de configuration d'une étape PYTHON_SCRIPT.
"""

from PySide6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QLabel, QSpinBox, QPlainTextEdit, QPushButton,
    QWidget, QFileDialog, QMessageBox,
)
from PySide6.QtGui import QFont
from ui.styles import COLORS
from .common import TOKENS_HINT
from .base_config_dialog import _BaseStepConfigDialog


class _PythonScriptConfigDialog(_BaseStepConfigDialog):
    STEP_TYPE = "PYTHON_SCRIPT"

    def __init__(self, config: dict, parent=None, label: str = "", **_):
        super().__init__(config, parent, label,
                          retry_count=_.get("retry_count", 0),
                          run_always=_.get("run_always", False))
        self.setWindowTitle("Étape — Script Python")
        self.setMinimumSize(540, 520)
        self._build_ui()
        self._prefill()

    def _build_ui(self):
        root = QVBoxLayout(self); root.setContentsMargins(28, 24, 28, 20); root.setSpacing(16)
        title = QLabel("Exécution d'un script Python")
        title.setStyleSheet(f"font-size: 15px; font-weight: 700; color: {COLORS['text_main']};")
        root.addWidget(title); root.addWidget(self._sep())

        form = self._form()
        self._add_label_row(form)
        self._add_execution_policy_row(form)

        # Script
        self.inp_script = self._input("ex : C:/scripts/traitement.py")
        script_row = QHBoxLayout(); script_row.setSpacing(6)
        script_row.addWidget(self.inp_script, stretch=1)
        btn_browse = QPushButton("Parcourir…"); btn_browse.setObjectName("secondary")
        btn_browse.setFixedHeight(34); btn_browse.setFixedWidth(100)
        btn_browse.clicked.connect(self._browse_script)
        script_row.addWidget(btn_browse)
        sw = QWidget(); sw.setLayout(script_row)
        form.addRow(self._lbl("Script * (.py)"), sw)

        # Python exe
        self.inp_py_exe = self._input("ex : python  ou  C:/Python311/python.exe")
        form.addRow(self._lbl("Exécutable Python"), self.inp_py_exe)

        # Arguments (un par ligne)
        args_lbl = QLabel("Arguments (un par ligne) :")
        args_lbl.setStyleSheet(f"color: {COLORS['text_dim']}; font-size: 12px; font-weight: 500;")
        root.addLayout(form)
        root.addWidget(args_lbl)

        self.txt_args = QPlainTextEdit()
        self.txt_args.setFont(QFont("Consolas", 11))
        self.txt_args.setPlaceholderText(
            "--date {yyyyMMdd}\n--input {output_file}\n--mode production\n"
            "--context-in {ds_context_in}\n--context-out {ds_context_out}"
        )
        self.txt_args.setFixedHeight(110)
        self.txt_args.setStyleSheet(
            f"background: {COLORS['bg_main']}; color: {COLORS['text_main']}; "
            f"border: 1px solid {COLORS['border']}; border-radius: 4px; padding: 6px;"
        )
        root.addWidget(self.txt_args)

        hint = QLabel("Tokens disponibles : " + TOKENS_HINT + "  {ds_context_in}  {ds_context_out}")
        hint.setStyleSheet(
            f"color: {COLORS['text_muted']}; font-size: 10px; font-family: Consolas; font-style: italic;"
        )
        hint.setWordWrap(True)
        root.addWidget(hint)

        context_hint = QLabel(
            "{ds_context_in} / {ds_context_out} : chemins de fichiers JSON facultatifs pour lire "
            "les artefacts déjà produits et en publier de nouveaux vers les étapes suivantes "
            "(voir docs/COOKBOOK.md). Ignorés si non référencés — aucun changement pour un script "
            "existant."
        )
        context_hint.setStyleSheet(
            f"color: {COLORS['text_muted']}; font-size: 10px; font-style: italic;"
        )
        context_hint.setWordWrap(True)
        root.addWidget(context_hint)

        form2 = self._form()
        self.inp_workdir = self._input("Dossier de travail (optionnel)")
        workdir_row = QHBoxLayout(); workdir_row.setSpacing(6)
        workdir_row.addWidget(self.inp_workdir, stretch=1)
        btn_wdir = QPushButton("Parcourir…"); btn_wdir.setObjectName("secondary")
        btn_wdir.setFixedHeight(34); btn_wdir.setFixedWidth(100)
        btn_wdir.clicked.connect(self._browse_workdir)
        workdir_row.addWidget(btn_wdir)
        ww = QWidget(); ww.setLayout(workdir_row)
        form2.addRow(self._lbl("Répertoire travail"), ww)

        self.inp_timeout = QSpinBox()
        self.inp_timeout.setRange(10, 86400); self.inp_timeout.setValue(300)
        self.inp_timeout.setSuffix(" s"); self.inp_timeout.setFixedWidth(110)
        self.inp_timeout.setStyleSheet(self._spinbox_style())
        form2.addRow(self._lbl("Timeout"), self.inp_timeout)
        root.addLayout(form2)

        root.addStretch()
        self._buttons(root)

    def _browse_script(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Choisir le script Python", "", "Scripts Python (*.py)"
        )
        if path:
            self.inp_script.setText(path)

    def _browse_workdir(self):
        path = QFileDialog.getExistingDirectory(self, "Répertoire de travail")
        if path:
            self.inp_workdir.setText(path)

    def _prefill(self):
        import sys as _sys
        c = self._config
        self.inp_script.setText(c.get("script_path", ""))
        self.inp_py_exe.setText(c.get("python_executable", _sys.executable))
        args = c.get("args", [])
        self.txt_args.setPlainText("\n".join(args))
        self.inp_workdir.setText(c.get("working_dir", ""))
        self.inp_timeout.setValue(int(c.get("timeout", 300)))

    def _collect_config(self) -> dict:
        import sys as _sys
        raw  = self.txt_args.toPlainText()
        args = [a.strip() for a in raw.splitlines() if a.strip()]
        exe  = self.inp_py_exe.text().strip() or _sys.executable
        return {
            "script_path":        self.inp_script.text().strip(),
            "python_executable":  exe,
            "args":               args,
            "working_dir":        self.inp_workdir.text().strip() or None,
            "timeout":            self.inp_timeout.value(),
        }

    def _on_ok(self):
        if not self.inp_script.text().strip():
            QMessageBox.warning(self, "Champ requis", "Saisir le chemin du script Python.")
            return
        self.accept()

"""
DataScheduler — ui/step_editor/python_script_config_dialog.py
Dialogue de configuration d'une étape PYTHON_SCRIPT.
"""

from PySide6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QLabel, QSpinBox, QPlainTextEdit, QPushButton,
    QWidget, QFileDialog, QMessageBox,
)
from PySide6.QtCore import QSize
from PySide6.QtGui import QFont
from ui.styles import COLORS, FONT_MONO, FONT_MONO_STACK
from .common import TOKENS_HINT, _icon
from .base_config_dialog import _BaseStepConfigDialog
from .python_script_template import PYTHON_SCRIPT_TEMPLATE


class _PythonScriptConfigDialog(_BaseStepConfigDialog):
    STEP_TYPE = "PYTHON_SCRIPT"

    def __init__(self, config: dict, parent=None, label: str = "", **_):
        super().__init__(config, parent, label,
                          retry_count=_.get("retry_count", 0),
                          run_always=_.get("run_always", False),
                          timeout_s=_.get("timeout_s", 0))
        self._prior_steps = _.get("prior_steps") or []
        self.setWindowTitle("Étape — Script Python")
        self.setMinimumSize(540, 520)
        self._build_ui()
        self._prefill()

    def _build_ui(self):
        root = QVBoxLayout(self); root.setContentsMargins(28, 24, 28, 20); root.setSpacing(16)
        title_row = QHBoxLayout()
        title = QLabel("Exécution d'un script Python")
        title.setStyleSheet(f"font-size: 15px; font-weight: 700; color: {COLORS['text_main']};")
        title_row.addWidget(title); title_row.addStretch()
        btn_template = QPushButton("  Télécharger un modèle de script")
        btn_template.setObjectName("secondary")
        btn_template.setFixedHeight(32)
        btn_template.setIcon(_icon("fa5s.file-download", COLORS["text_main"]))
        btn_template.setIconSize(QSize(12, 12))
        btn_template.setToolTip(
            "Enregistre un fichier .py commenté, prêt à adapter — couvre les 3 cas d'usage "
            "(script autonome, lecture du contexte, publication d'un résultat)."
        )
        btn_template.clicked.connect(self._download_template)
        title_row.addWidget(btn_template)
        root.addLayout(title_row); root.addWidget(self._sep())

        form = self._form()
        self._add_label_row(form)
        self._add_execution_policy_row(form)

        # Script
        self.inp_script = self._input("ex : C:/scripts/traitement.py")
        self.inp_script.setToolTip("Chemin vers le script Python à exécuter.")
        script_row = QHBoxLayout(); script_row.setSpacing(6)
        script_row.addWidget(self.inp_script, stretch=1)
        btn_browse = QPushButton("Parcourir…"); btn_browse.setObjectName("secondary")
        btn_browse.setFixedHeight(34); btn_browse.setFixedWidth(100)
        btn_browse.clicked.connect(self._browse_script)
        script_row.addWidget(btn_browse)
        sw = QWidget(); sw.setLayout(script_row)
        form.addRow(self._lbl("Script * (.py)"), sw)

        # Python exe — obligatoire : DataScheduler n'a pas de "Python par défaut" utilisable pour
        # lancer un script une fois packagé en .exe (voir tooltip). Champ jamais pré-rempli
        # automatiquement pour éviter de suggérer une valeur qui n'existe pas.
        self.inp_py_exe = self._input("ex : C:/mon_projet/venv/Scripts/python.exe")
        self.inp_py_exe.setToolTip(
            "Chemin complet vers le python.exe du script (son propre venv/conda — jamais celui "
            "de DataScheduler, qui n'existe pas en tant qu'interpréteur autonome une fois "
            "l'application packagée en .exe). Chaque étape peut pointer vers un environnement "
            "différent si vos scripts viennent de projets distincts."
        )
        form.addRow(self._lbl("Exécutable Python *"), self.inp_py_exe)

        # Arguments (un par ligne)
        self.txt_args = QPlainTextEdit()
        self.txt_args.setFont(QFont(FONT_MONO, 11))
        self.txt_args.setPlaceholderText(
            "--date {yyyyMMdd}\n--input {output_file}\n--mode production\n"
            "--context-in {ds_context_in}\n--context-out {ds_context_out}"
        )
        self.txt_args.setFixedHeight(110)
        self.txt_args.setStyleSheet(
            f"background: {COLORS['bg_main']}; color: {COLORS['text_main']}; "
            f"border: 1px solid {COLORS['border']}; border-radius: 4px; padding: 6px;"
        )

        args_lbl = QLabel("Arguments (un par ligne) :")
        args_lbl.setStyleSheet(f"color: {COLORS['text_dim']}; font-size: 12px; font-weight: 500;")
        root.addLayout(form)
        args_hdr = QHBoxLayout(); args_hdr.setSpacing(8)
        args_hdr.addWidget(args_lbl); args_hdr.addStretch()
        args_hdr.addWidget(self._artifact_reference_button(self.txt_args, self._prior_steps))
        root.addLayout(args_hdr)
        root.addWidget(self.txt_args)

        hint = QLabel("Tokens disponibles : " + TOKENS_HINT + "  {ds_context_in}  {ds_context_out}")
        hint.setStyleSheet(
            f"color: {COLORS['text_muted']}; font-size: 10px; font-family: {FONT_MONO_STACK}; font-style: italic;"
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
        wdir_lbl = self._lbl("Répertoire travail")
        wdir_lbl.setToolTip(
            "Dossier depuis lequel le script est lancé — utile s'il référence des chemins "
            "relatifs."
        )
        form2.addRow(wdir_lbl, ww)

        self.inp_timeout = QSpinBox()
        self.inp_timeout.setRange(10, 86400); self.inp_timeout.setValue(300)
        self.inp_timeout.setSuffix(" s"); self.inp_timeout.setFixedWidth(110)
        self.inp_timeout.setStyleSheet(self._spinbox_style())
        self.inp_timeout.setToolTip(
            "Durée maximale d'exécution avant que le script soit interrompu automatiquement."
        )
        form2.addRow(self._lbl("Timeout"), self.inp_timeout)

        self.inp_output_names = self._input("ex : rapport_csv, resume_json")
        form2.addRow(self._lbl("Sortie(s) publiées"), self.inp_output_names)
        names_hint = QLabel(
            "Auto-déclaratif : le script publie déjà ces clés lui-même via {ds_context_out} — "
            "ce champ sert seulement à ce que les étapes suivantes puissent les découvrir "
            "(bouton « + Artefact » ci-dessus) et les référencer via {artifact:nom}."
        )
        names_hint.setWordWrap(True)
        names_hint.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 10px; font-style: italic;")
        form2.addRow("", names_hint)
        root.addLayout(form2)

        root.addStretch()
        self._buttons(root)

    def _download_template(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Enregistrer le modèle de script", "mon_script_datascheduler.py",
            "Scripts Python (*.py)",
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(PYTHON_SCRIPT_TEMPLATE)
        except OSError as e:
            QMessageBox.critical(self, "Échec de l'enregistrement", str(e))

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
        c = self._config
        self.inp_script.setText(c.get("script_path", ""))
        self.inp_py_exe.setText(c.get("python_executable", ""))
        args = c.get("args", [])
        self.txt_args.setPlainText("\n".join(args))
        self.inp_workdir.setText(c.get("working_dir", ""))
        self.inp_timeout.setValue(int(c.get("timeout", 300)))
        self.inp_output_names.setText(", ".join(c.get("output_names", [])))

    def _collect_config(self) -> dict:
        raw  = self.txt_args.toPlainText()
        args = [a.strip() for a in raw.splitlines() if a.strip()]
        output_names = [n.strip() for n in self.inp_output_names.text().split(",") if n.strip()]
        return {
            "script_path":        self.inp_script.text().strip(),
            "python_executable":  self.inp_py_exe.text().strip(),
            "args":               args,
            "working_dir":        self.inp_workdir.text().strip() or None,
            "timeout":            self.inp_timeout.value(),
            "output_names":       output_names,
        }

    def _on_ok(self):
        if not self.inp_script.text().strip():
            QMessageBox.warning(self, "Champ requis", "Saisir le chemin du script Python.")
            return
        if not self.inp_py_exe.text().strip():
            QMessageBox.warning(
                self, "Champ requis",
                "Saisir le chemin de l'exécutable Python (python.exe du venv/conda du script) — "
                "DataScheduler n'a pas d'interpréteur par défaut utilisable pour ça une fois "
                "packagé en .exe.",
            )
            return
        self.accept()

"""
DataScheduler — ui/step_editor/base_config_dialog.py
Classe de base commune à tous les dialogues de configuration d'étape.
"""

import uuid

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QLineEdit,
    QSpinBox, QComboBox, QPushButton, QFrame, QWidget, QCheckBox, QMenu,
)
from PySide6.QtCore import Qt
from ui.styles import COLORS, DIALOG_STYLE, FONT_MONO_STACK
from .common import STEP_META, TOKENS_HINT


class _BaseStepConfigDialog(QDialog):
    """Dialogue de configuration d'une étape (base commune)."""

    STEP_TYPE = ""

    # Types de step à effet de bord externe — un retry peut dupliquer une action réelle
    # (upload, email, appel HTTP, commit SQL). Affiche un avertissement sous le champ retry.
    SIDE_EFFECT_TYPES = {"FTP_UPLOAD", "EMAIL_NOTIFY", "HTTP_REQUEST", "DB_EXECUTE"}

    def __init__(self, config: dict, parent=None, label: str = "",
                 retry_count: int = 0, run_always: bool = False, timeout_s: int = 0):
        super().__init__(parent)
        self._config = config
        self._init_label = label
        self._init_retry_count = retry_count
        self._init_run_always  = run_always
        self._init_timeout_s   = timeout_s
        self.setMinimumWidth(500)
        self.setStyleSheet(DIALOG_STYLE)

    def result_step(self) -> dict:
        config = self._collect_config()
        # Clé stable de l'étape, conservée à travers les réenregistrements — voir
        # docs/ARCHITECTURE.md. Contrairement à PipelineStep.id (réattribué à chaque
        # save_steps()), cette clé voyage avec le config_json, donc survit au cycle
        # delete/recreate. Utilisée pour cibler explicitement "la sortie de cette
        # étape précise" depuis une étape consommatrice ultérieure (voir _source_row).
        config["_step_key"] = self._config.get("_step_key") or str(uuid.uuid4())
        return {
            "step_type":   self.STEP_TYPE,
            "label":       self._get_label(),
            "config":      config,
            "retry_count": self.inp_retry.value() if hasattr(self, "inp_retry") else 0,
            "run_always":  self.chk_run_always.isChecked() if hasattr(self, "chk_run_always") else False,
            "timeout_s":   self.inp_timeout.value() if hasattr(self, "inp_timeout") else 0,
        }

    def _get_label(self) -> str:
        return getattr(self, "inp_label", None) and self.inp_label.text().strip() or ""

    def _collect_config(self) -> dict:
        raise NotImplementedError

    # ── Widgets communs ───────────────────────

    def _add_label_row(self, form: QFormLayout):
        self.inp_label = QLineEdit()
        self.inp_label.setPlaceholderText("ex : Export Ventes (optionnel)")
        self.inp_label.setText(self._init_label)
        self.inp_label.setFixedHeight(34)
        self.inp_label.setStyleSheet(self._input_style())
        self.inp_label.setToolTip(
            "Nom facultatif affiché dans la liste des étapes et dans le journal d'exécution. "
            "Laissé vide, un libellé générique est utilisé."
        )
        form.addRow(self._lbl("Libellé"), self.inp_label)

    def _add_execution_policy_row(self, form: QFormLayout):
        self.inp_retry = QSpinBox()
        self.inp_retry.setRange(0, 10)
        self.inp_retry.setValue(self._init_retry_count)
        self.inp_retry.setSuffix(" tentative(s) supplémentaire(s)")
        self.inp_retry.setStyleSheet(self._spinbox_style())
        self.inp_retry.setToolTip(
            "Nombre de tentatives supplémentaires si l'étape échoue, avant d'abandonner le "
            "pipeline (0 = aucune tentative supplémentaire)."
        )
        form.addRow(self._lbl("Réessayer en cas d'échec"), self.inp_retry)

        if self.STEP_TYPE in self.SIDE_EFFECT_TYPES:
            warn = QLabel(
                "⚠ Un réessai peut dupliquer l'action (nouvel envoi/appel/commit) si le "
                "premier essai a partiellement réussi."
            )
            warn.setWordWrap(True)
            warn.setStyleSheet(f"color: {COLORS['warning']}; font-size: 10.5px; font-style: italic;")
            form.addRow("", warn)

        self.chk_run_always = QCheckBox("Exécuter même si une étape précédente a échoué")
        self.chk_run_always.setChecked(self._init_run_always)
        self.chk_run_always.setStyleSheet(f"color: {COLORS['text_main']};")
        self.chk_run_always.setToolTip(
            "Utile par exemple pour toujours envoyer une notification email en fin de pipeline, "
            "même si une étape en amont a échoué."
        )
        form.addRow("", self.chk_run_always)

        self.inp_timeout = QSpinBox()
        self.inp_timeout.setRange(0, 21600)
        self.inp_timeout.setValue(self._init_timeout_s)
        self.inp_timeout.setSuffix(" s")
        self.inp_timeout.setSpecialValueText("Aucune limite")
        self.inp_timeout.setStyleSheet(self._spinbox_style())
        self.inp_timeout.setToolTip(
            "Délai maximal avant d'abandonner l'étape (0 = aucune limite). Utile pour une "
            "connexion SSH/Spark, FTP ou un appel HTTP qui pourrait rester bloqué indéfiniment. "
            "Un dépassement compte comme un échec normal (donc soumis à la relance ci-dessus)."
        )
        form.addRow(self._lbl("Délai maximal"), self.inp_timeout)

    def _profile_row(self, form: QFormLayout, label: str, items: list,
                     empty_label: str, new_fn) -> QComboBox:
        cb = QComboBox(); cb.setStyleSheet(self._combo_style())
        cb.setToolTip(
            f"{label.rstrip(' *')} à utiliser pour cette étape. « + Nouveau » permet d'en créer "
            "un sans quitter ce dialogue."
        )
        cb.addItem(empty_label, None)
        for item in items:
            cb.addItem(item.name, item.id)
        row = QHBoxLayout(); row.setSpacing(6)
        row.addWidget(cb, stretch=1)
        btn_new = QPushButton("+ Nouveau")
        btn_new.setObjectName("secondary"); btn_new.setFixedHeight(30)
        btn_new.setFixedWidth(90)
        btn_new.clicked.connect(lambda: new_fn(cb))
        row.addWidget(btn_new)
        w = QWidget(); w.setLayout(row)
        form.addRow(self._lbl(label), w)
        return cb

    def _db_profile_row(self, form: QFormLayout, label: str, profiles: list) -> QComboBox:
        """
        Sélecteur de profil de base de données, tout moteur confondu (Oracle/MySQL/
        PostgreSQL/SQL Server). L'itemData est un tuple (db_type, id) — un profile_id seul
        ne suffit pas à identifier un profil de façon unique puisque OracleProfile et
        DatabaseProfile sont deux tables distinctes qui peuvent partager le même id.
        """
        cb = QComboBox(); cb.setStyleSheet(self._combo_style())
        cb.setToolTip(
            "Profil de base de données à utiliser pour cette étape (tout moteur confondu). "
            "« + Nouveau » permet d'en créer un sans quitter ce dialogue."
        )
        self._populate_db_combo(cb, profiles)
        row = QHBoxLayout(); row.setSpacing(6)
        row.addWidget(cb, stretch=1)
        btn_new = QPushButton("+ Nouveau")
        btn_new.setObjectName("secondary"); btn_new.setFixedHeight(30)
        btn_new.setFixedWidth(90)
        btn_new.clicked.connect(lambda: self._new_db_profile(cb))
        row.addWidget(btn_new)
        w = QWidget(); w.setLayout(row)
        form.addRow(self._lbl(label), w)
        return cb

    def _source_row(self, form: QFormLayout, prior_steps: list,
                     empty_label: str = "Étape précédente (par défaut)",
                     tooltip: str | None = None) -> QComboBox:
        """
        Sélecteur de source explicite : par défaut "étape précédente" (comportement
        historique, ctx.output_file tel que rempli par la dernière étape productrice),
        ou une étape productrice antérieure précise (ctx.artifacts[son _step_key]) —
        utile dès qu'un pipeline contient plusieurs étapes productrices (ex: deux
        DB_EXTRACT) et qu'une étape en aval doit choisir laquelle consommer.

        `empty_label`/`tooltip` (chantier Gateway) : personnalisables pour un appelant dont
        l'entrée par défaut n'a pas de sens ("étape précédente" ne veut rien dire pour une
        jonction à plusieurs branches convergentes) — défauts inchangés pour les 7 appelants
        existants.
        """
        from core.steps import step_produces_output_file
        cb = QComboBox(); cb.setStyleSheet(self._combo_style())
        cb.setToolTip(tooltip or (
            "Étape dont la sortie alimente celle-ci. Par défaut, la dernière étape ayant produit "
            "un fichier — à choisir explicitement dès que plusieurs étapes en amont en "
            "produisent un."
        ))
        cb.addItem(empty_label, None)
        for i, s in enumerate(prior_steps or []):
            if not step_produces_output_file(s.get("step_type", ""), s.get("config") or {}):
                continue
            key = (s.get("config") or {}).get("_step_key")
            if not key:
                continue
            label = s.get("label") or f"Étape {i + 1} — {STEP_META.get(s['step_type'], {}).get('label', s['step_type'])}"
            cb.addItem(label, key)
        form.addRow(self._lbl("Source"), cb)
        return cb

    def _output_name_row(self, form: QFormLayout, default: str = "output_file") -> QLineEdit:
        """
        Nom de sortie éditable — alias cosmétique publié EN PLUS de la clé interne
        _step_key (voir core/pipeline.py), jamais à sa place : renommer ce nom ne casse
        jamais le graphe (les arêtes ne s'appuient jamais dessus), seul un script/token qui
        référençait l'ancien nom cesse de le trouver. Vide = aucun alias publié, comportement
        actuel inchangé. Le paramètre `default` n'est qu'un exemple affiché en placeholder —
        c'est à l'appelant de préremplir la valeur réelle dans son _prefill().
        """
        inp = self._input(f"ex : {default}")
        inp.setToolTip(
            "Nom sous lequel cette sortie est publiée pour les étapes suivantes, en plus du "
            "câblage automatique — permet de la référencer explicitement via {artifact:nom}. "
            "Laissez vide pour ne pas publier d'alias."
        )
        form.addRow(self._lbl("Nom de sortie"), inp)
        return inp

    def _artifact_reference_button(self, target_field, prior_steps: list) -> QPushButton:
        """
        Bouton listant les noms d'artefact déclarés par les étapes précédentes (via
        _output_name_row ou le champ "Sortie(s) publiées" de PYTHON_SCRIPT) — un clic insère
        {artifact:nom} dans target_field à la position du curseur. Complète _tokens_hint() :
        ceci résout la découvrabilité des noms, {artifact:nom} (core/steps/base.py) est le
        mécanisme de référence lui-même — deux problèmes distincts, pas redondants.
        """
        btn = QPushButton("+ Artefact"); btn.setObjectName("secondary")
        btn.setFixedHeight(28)

        names: list[str] = []
        for s in prior_steps or []:
            cfg = s.get("config") or {}
            if cfg.get("output_name"):
                names.append(cfg["output_name"])
            names.extend(cfg.get("output_names") or [])

        if not names:
            btn.setEnabled(False)
            btn.setToolTip("Aucune sortie nommée disponible parmi les étapes précédentes.")
            return btn

        menu = QMenu(btn)
        for name in dict.fromkeys(names):   # dédoublonne en gardant l'ordre
            action = menu.addAction(name)
            action.triggered.connect(
                lambda checked=False, n=name: self._insert_at_cursor(target_field, f"{{artifact:{n}}}")
            )
        btn.setMenu(menu)
        return btn

    @staticmethod
    def _insert_at_cursor(field, text: str) -> None:
        if hasattr(field, "insertPlainText"):   # QPlainTextEdit
            field.insertPlainText(text)
        else:                                    # QLineEdit
            field.insert(text)

    @staticmethod
    def _populate_db_combo(cb: QComboBox, profiles: list, keep_current: bool = False):
        from ui.dialogs import DB_TYPE_META
        cur = cb.currentData() if keep_current else None
        cb.blockSignals(True)
        cb.clear()
        cb.addItem("— Sélectionner un profil —", None)
        for p in profiles:
            type_label = DB_TYPE_META.get(p["db_type"], {}).get("label", p["db_type"])
            cb.addItem(f"[{type_label}] {p['name']}", (p["db_type"], p["id"]))
        cb.blockSignals(False)
        if keep_current:
            _BaseStepConfigDialog._set_combo(cb, cur)

    def _new_db_profile(self, cb: QComboBox):
        from ui.dialogs import DbTypeChooserDialog, OracleDialog, DatabaseProfileDialog
        from database import db_manager as db
        chooser = DbTypeChooserDialog(self)
        if not chooser.exec():
            return
        db_type = chooser.chosen_type
        dlg = OracleDialog(self) if db_type == "ORACLE" else DatabaseProfileDialog(self, db_type=db_type)
        if not dlg.exec():
            return
        profiles = db.list_all_db_profiles()
        if hasattr(self, "_db_profiles"):
            self._db_profiles = profiles
        self._populate_db_combo(cb, profiles)
        cb.setCurrentIndex(cb.count() - 1)

    def _tokens_hint(self) -> QLabel:
        lbl = QLabel("Tokens : " + TOKENS_HINT)
        lbl.setStyleSheet(
            f"color: {COLORS['text_muted']}; font-size: 10px; font-family: {FONT_MONO_STACK}; font-style: italic;"
        )
        lbl.setWordWrap(True)
        return lbl

    def _input(self, placeholder="") -> QLineEdit:
        w = QLineEdit(); w.setPlaceholderText(placeholder); w.setFixedHeight(34)
        w.setStyleSheet(self._input_style()); return w

    def _input_style(self, error=False) -> str:
        border = COLORS["danger"] if error else COLORS["border"]
        return (
            f"QLineEdit {{ background: {COLORS['bg_card']}; border: 1px solid {border}; "
            f"border-radius: 4px; padding: 6px 10px; color: {COLORS['text_main']}; font-size: 13px; }}"
            f"QLineEdit:focus {{ border-color: {COLORS['accent']}; }}"
        )

    def _spinbox_style(self) -> str:
        return (
            f"QSpinBox {{ background: {COLORS['bg_card']}; border: 1px solid {COLORS['border']}; "
            f"border-radius: 4px; padding: 6px 8px; color: {COLORS['text_main']}; font-size: 13px; }}"
            f"QSpinBox:focus {{ border-color: {COLORS['accent']}; }}"
        )

    def _combo_style(self) -> str:
        return (
            f"QComboBox {{ background: {COLORS['bg_card']}; border: 1px solid {COLORS['border']}; "
            f"border-radius: 4px; padding: 6px 10px; color: {COLORS['text_main']}; font-size: 13px; }}"
            f"QComboBox:focus {{ border-color: {COLORS['accent']}; }}"
            f"QComboBox::drop-down {{ border: none; padding-right: 8px; }}"
            f"QComboBox QAbstractItemView {{ background: {COLORS['bg_card']}; "
            f"border: 1px solid {COLORS['border']}; "
            f"selection-background-color: {COLORS['bg_active']}; color: {COLORS['text_main']}; }}"
        )

    def _lbl(self, text: str) -> QLabel:
        l = QLabel(text)
        l.setStyleSheet(f"color: {COLORS['text_dim']}; font-size: 12px; font-weight: 500;")
        return l

    def _form(self) -> QFormLayout:
        f = QFormLayout(); f.setSpacing(12)
        f.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        f.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)
        return f

    def _sep(self) -> QFrame:
        f = QFrame(); f.setFrameShape(QFrame.HLine)
        f.setStyleSheet(f"background: {COLORS['border']}; max-height: 1px;")
        return f

    def _buttons(self, root: QVBoxLayout):
        root.addWidget(self._sep())
        btn_row = QHBoxLayout(); btn_row.setSpacing(10); btn_row.addStretch()
        btn_cancel = QPushButton("Annuler"); btn_cancel.setObjectName("secondary")
        btn_cancel.setFixedHeight(36); btn_cancel.clicked.connect(self.reject)
        btn_ok = QPushButton("Valider l'étape")
        btn_ok.setFixedHeight(36); btn_ok.clicked.connect(self._on_ok)
        btn_row.addWidget(btn_cancel); btn_row.addWidget(btn_ok)
        root.addLayout(btn_row)

    def _on_ok(self):
        self.accept()

    @staticmethod
    def _set_combo(cb: QComboBox, value):
        for i in range(cb.count()):
            if cb.itemData(i) == value:
                cb.setCurrentIndex(i); return

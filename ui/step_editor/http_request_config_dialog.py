"""
DataScheduler — ui/step_editor/http_request_config_dialog.py
Dialogue de configuration d'une étape HTTP_REQUEST.
"""

from PySide6.QtWidgets import (
    QVBoxLayout, QLabel, QSpinBox, QComboBox, QPlainTextEdit, QCheckBox,
    QMessageBox,
)
from PySide6.QtGui import QFont
from ui.styles import COLORS, FONT_MONO
from .base_config_dialog import _BaseStepConfigDialog


class _HttpRequestConfigDialog(_BaseStepConfigDialog):
    STEP_TYPE = "HTTP_REQUEST"

    METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE"]

    def __init__(self, config: dict, parent=None, label: str = "", **_):
        super().__init__(config, parent, label,
                          retry_count=_.get("retry_count", 0),
                          run_always=_.get("run_always", False),
                          timeout_s=_.get("timeout_s", 0))
        self._prior_steps = _.get("prior_steps") or []
        self.setWindowTitle("Étape — Appel HTTP")
        self.setMinimumSize(540, 560)
        self._build_ui()
        self._prefill()

    def _build_ui(self):
        root = QVBoxLayout(self); root.setContentsMargins(28, 24, 28, 20); root.setSpacing(16)
        title = QLabel("Appel HTTP (API REST / webhook)")
        title.setStyleSheet(f"font-size: 15px; font-weight: 700; color: {COLORS['text_main']};")
        root.addWidget(title); root.addWidget(self._sep())

        form = self._form()
        self._add_label_row(form)
        self._add_execution_policy_row(form)

        self.cb_method = QComboBox(); self.cb_method.setStyleSheet(self._combo_style())
        for m in self.METHODS: self.cb_method.addItem(m, m)
        self.cb_method.setToolTip("Méthode HTTP à utiliser pour l'appel.")
        form.addRow(self._lbl("Méthode"), self.cb_method)

        self.inp_url = self._input("ex : https://api.company.com/webhook/{yyyyMMdd}")
        form.addRow(self._lbl("URL *"), self.inp_url)
        form.addRow("", self._tokens_hint())

        self.inp_timeout = QSpinBox()
        self.inp_timeout.setRange(1, 3600); self.inp_timeout.setValue(30)
        self.inp_timeout.setSuffix(" s"); self.inp_timeout.setFixedWidth(110)
        self.inp_timeout.setStyleSheet(self._spinbox_style())
        self.inp_timeout.setToolTip("Durée maximale d'attente de la réponse avant d'abandonner l'appel.")
        form.addRow(self._lbl("Timeout"), self.inp_timeout)
        root.addLayout(form)

        headers_lbl = QLabel("En-têtes (un par ligne, format « Clé: Valeur ») :")
        headers_lbl.setStyleSheet(f"color: {COLORS['text_dim']}; font-size: 12px; font-weight: 500;")
        root.addWidget(headers_lbl)
        self.txt_headers = QPlainTextEdit()
        self.txt_headers.setFont(QFont(FONT_MONO, 11))
        self.txt_headers.setPlaceholderText("Content-Type: application/json\nAuthorization: Bearer {output_file}")
        self.txt_headers.setToolTip("Un en-tête par ligne, au format « Clé: Valeur ».")
        self.txt_headers.setFixedHeight(70)
        self.txt_headers.setStyleSheet(
            f"background: {COLORS['bg_main']}; color: {COLORS['text_main']}; "
            f"border: 1px solid {COLORS['border']}; border-radius: 4px; padding: 6px;"
        )
        root.addWidget(self.txt_headers)

        body_lbl = QLabel("Corps de la requête :")
        body_lbl.setStyleSheet(f"color: {COLORS['text_dim']}; font-size: 12px; font-weight: 500;")
        root.addWidget(body_lbl)
        self.txt_body = QPlainTextEdit()
        self.txt_body.setFont(QFont(FONT_MONO, 11))
        self.txt_body.setPlaceholderText('{"date": "{yyyyMMdd}", "rows": {rows_count}}')
        self.txt_body.setToolTip("Corps envoyé avec la requête (JSON, XML…) — laissez vide pour un GET.")
        self.txt_body.setFixedHeight(90)
        self.txt_body.setStyleSheet(
            f"background: {COLORS['bg_main']}; color: {COLORS['text_main']}; "
            f"border: 1px solid {COLORS['border']}; border-radius: 4px; padding: 6px;"
        )
        root.addWidget(self.txt_body)

        self.chk_attach = QCheckBox("Envoyer le fichier produit en pièce jointe (multipart)")
        self.chk_attach.setStyleSheet(f"color: {COLORS['text_main']};")
        self.chk_attach.setToolTip(
            "Envoie le fichier produit par l'étape précédente (ou la Source choisie ci-dessous) "
            "en pièce jointe, en plus du corps de la requête."
        )
        root.addWidget(self.chk_attach)

        attach_form = self._form()
        self.cb_source = self._source_row(attach_form, self._prior_steps)
        root.addLayout(attach_form)

        root.addStretch()
        self._buttons(root)

    def _prefill(self):
        c = self._config
        idx = self.cb_method.findData(c.get("method", "GET"))
        if idx >= 0:
            self.cb_method.setCurrentIndex(idx)
        self.inp_url.setText(c.get("url_tpl", ""))
        self.inp_timeout.setValue(int(c.get("timeout", 30)))
        self.txt_headers.setPlainText(c.get("headers", ""))
        self.txt_body.setPlainText(c.get("body_tpl", ""))
        self.chk_attach.setChecked(c.get("attach_output_file", False))
        self._set_combo(self.cb_source, c.get("reads_from_step_key"))

    def _collect_config(self) -> dict:
        return {
            "method":             self.cb_method.currentData(),
            "url_tpl":            self.inp_url.text().strip(),
            "timeout":            self.inp_timeout.value(),
            "headers":            self.txt_headers.toPlainText(),
            "body_tpl":           self.txt_body.toPlainText(),
            "attach_output_file": self.chk_attach.isChecked(),
            "reads_from_step_key": self.cb_source.currentData(),
        }

    def _on_ok(self):
        if not self.inp_url.text().strip():
            QMessageBox.warning(self, "Champ requis", "Saisir l'URL.")
            return
        self.accept()

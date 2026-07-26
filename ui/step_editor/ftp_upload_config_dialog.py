"""
DataScheduler — ui/step_editor/ftp_upload_config_dialog.py
Dialogue de configuration d'une étape FTP_UPLOAD.
"""

from PySide6.QtWidgets import (
    QVBoxLayout, QLabel, QComboBox, QMessageBox,
)
from ui.styles import COLORS
from .base_config_dialog import _BaseStepConfigDialog


class _FtpUploadConfigDialog(_BaseStepConfigDialog):
    STEP_TYPE = "FTP_UPLOAD"

    def __init__(self, config: dict, parent=None, label: str = "",
                 oracle_profiles=None, sql_queries=None, ftp_profiles=None,
                 smtp_profiles=None, db_profiles=None,
                 retry_count: int = 0, run_always: bool = False,
                 prior_steps=None):
        super().__init__(config, parent, label, retry_count, run_always)
        self._ftp_profiles = ftp_profiles or []
        self._prior_steps  = prior_steps or []
        self.setWindowTitle("Étape — Envoi FTP")
        self._build_ui()
        self._prefill()

    def _build_ui(self):
        root = QVBoxLayout(self); root.setContentsMargins(28, 24, 28, 20); root.setSpacing(16)
        title = QLabel("Envoi FTP / FTPS / SFTP")
        title.setStyleSheet(f"font-size: 15px; font-weight: 700; color: {COLORS['text_main']};")
        root.addWidget(title); root.addWidget(self._sep())

        form = self._form()
        self._add_label_row(form)
        self._add_execution_policy_row(form)
        self.cb_ftp = self._profile_row(
            form, "Profil FTP *",
            self._ftp_profiles, "— Sélectionner un profil FTP —",
            self._new_ftp_profile,
        )
        self.cb_source = self._source_row(form, self._prior_steps)
        self.inp_path = self._input("ex : /export/{yyyy}/{MM}/")
        self.inp_file = self._input("ex : ventes_{yyyyMMdd}.csv")
        form.addRow(self._lbl("Dossier distant *"), self.inp_path)
        form.addRow(self._lbl("Nom du fichier *"),  self.inp_file)
        form.addRow("", self._tokens_hint())

        # Aperçu
        self.lbl_preview = QLabel()
        self.lbl_preview.setStyleSheet(
            f"color: {COLORS['accent']}; font-size: 12px; font-family: Consolas; "
            f"background: {COLORS['bg_card']}; border: 1px solid {COLORS['border']}; "
            f"border-radius: 5px; padding: 6px 10px;"
        )
        self.inp_path.textChanged.connect(self._refresh_preview)
        self.inp_file.textChanged.connect(self._refresh_preview)
        form.addRow(self._lbl("Aperçu"), self.lbl_preview)
        root.addLayout(form)
        root.addStretch()
        self._buttons(root)

    def _refresh_preview(self):
        from core.ftp import resolve_remote_path
        try:
            preview = resolve_remote_path(
                self.inp_path.text().strip() or "/export/",
                self.inp_file.text().strip() or "fichier_{yyyyMMdd}.csv",
            )
            self.lbl_preview.setText(f"  {preview}")
        except Exception:
            self.lbl_preview.setText("  —")

    def _prefill(self):
        c = self._config
        self._set_combo(self.cb_ftp, c.get("ftp_profile_id"))
        self._set_combo(self.cb_source, c.get("reads_from_step_key"))
        self.inp_path.setText(c.get("remote_path_tpl", ""))
        self.inp_file.setText(c.get("filename_tpl", ""))
        self._refresh_preview()

    def _new_ftp_profile(self, cb: QComboBox):
        from ui.dialogs import FtpDialog
        from database import db_manager as db
        if FtpDialog(self).exec():
            self._ftp_profiles = db.get_ftp_profiles()
            cb.clear(); cb.addItem("— Sélectionner un profil FTP —", None)
            for p in self._ftp_profiles: cb.addItem(p.name, p.id)
            cb.setCurrentIndex(cb.count() - 1)

    def _collect_config(self) -> dict:
        return {
            "ftp_profile_id":     self.cb_ftp.currentData(),
            "remote_path_tpl":    self.inp_path.text().strip(),
            "filename_tpl":       self.inp_file.text().strip(),
            "reads_from_step_key": self.cb_source.currentData(),
        }

    def _on_ok(self):
        if not self.cb_ftp.currentData():
            QMessageBox.warning(self, "Champ requis", "Sélectionner un profil FTP.")
            return
        if not self.inp_path.text().strip():
            QMessageBox.warning(self, "Champ requis", "Saisir le dossier distant.")
            return
        if not self.inp_file.text().strip():
            QMessageBox.warning(self, "Champ requis", "Saisir le nom du fichier.")
            return
        self.accept()

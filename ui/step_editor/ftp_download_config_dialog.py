"""
DataScheduler — ui/step_editor/ftp_download_config_dialog.py
Dialogue de configuration d'une étape FTP_DOWNLOAD.
"""

from PySide6.QtWidgets import (
    QVBoxLayout, QLabel, QComboBox, QMessageBox,
)
from ui.styles import COLORS
from .base_config_dialog import _BaseStepConfigDialog


class _FtpDownloadConfigDialog(_BaseStepConfigDialog):
    STEP_TYPE = "FTP_DOWNLOAD"

    def __init__(self, config: dict, parent=None, label: str = "", **_):
        super().__init__(config, parent, label,
                          retry_count=_.get("retry_count", 0),
                          run_always=_.get("run_always", False),
                          timeout_s=_.get("timeout_s", 0))
        self._ftp_profiles = _.get("ftp_profiles") or []
        self.setWindowTitle("Étape — Téléchargement FTP")
        self._build_ui()
        self._prefill()

    def _build_ui(self):
        root = QVBoxLayout(self); root.setContentsMargins(28, 24, 28, 20); root.setSpacing(16)
        title = QLabel("Téléchargement FTP / FTPS / SFTP")
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
        self.inp_remote = self._input("ex : /export/{yyyy}/{MM}/ventes_{yyyyMMdd}.csv")
        form.addRow(self._lbl("Chemin distant *"), self.inp_remote)
        form.addRow("", self._tokens_hint())
        self.inp_output_name = self._output_name_row(form)
        root.addLayout(form)
        root.addStretch()
        self._buttons(root)

    def _prefill(self):
        c = self._config
        self._set_combo(self.cb_ftp, c.get("ftp_profile_id"))
        self.inp_remote.setText(c.get("remote_path_tpl", ""))
        self.inp_output_name.setText(c.get("output_name", ""))

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
            "ftp_profile_id":  self.cb_ftp.currentData(),
            "remote_path_tpl": self.inp_remote.text().strip(),
            "output_name":     self.inp_output_name.text().strip(),
        }

    def _on_ok(self):
        if not self.cb_ftp.currentData():
            QMessageBox.warning(self, "Champ requis", "Sélectionner un profil FTP.")
            return
        if not self.inp_remote.text().strip():
            QMessageBox.warning(self, "Champ requis", "Saisir le chemin distant.")
            return
        self.accept()

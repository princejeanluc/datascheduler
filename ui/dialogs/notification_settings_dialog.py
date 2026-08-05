"""
DataScheduler — ui/dialogs/notification_settings_dialog.py
Paramètres du digest manager (chantier UX post-personas) : résumé périodique des exécutions
envoyé par email, pour les personas qui n'ouvrent jamais l'application (voir
core/scheduler.py::PipelineScheduler._run_digest).
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QLineEdit,
    QComboBox, QCheckBox, QPushButton, QFrame, QMessageBox, QWidget,
)
from PySide6.QtCore import Qt
from ui.styles import COLORS, DIALOG_STYLE
from ui.step_editor.common import DAYS_OF_WEEK


class NotificationSettingsDialog(QDialog):
    """Active/configure le digest — profil SMTP, destinataires, fréquence."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Notifications")
        self.setMinimumWidth(460)
        self.setStyleSheet(DIALOG_STYLE)
        self._load_data()
        self._build_ui()
        self._prefill()

    def _load_data(self):
        from database import db_manager as db
        self._settings = db.get_notification_settings()
        self._smtp_profiles = db.get_smtp_profiles()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(16)

        title = QLabel("Digest par email")
        title.setStyleSheet(f"font-size: 16px; font-weight: 700; color: {COLORS['text_main']};")
        root.addWidget(title)
        note = QLabel(
            "Envoie un résumé périodique (succès/échecs depuis le dernier envoi) — utile pour "
            "être informé sans avoir à ouvrir l'application."
        )
        note.setWordWrap(True)
        note.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 11px; font-style: italic;")
        root.addWidget(note)
        root.addWidget(self._sep())

        self.chk_enabled = QCheckBox("Activer le digest")
        self.chk_enabled.setStyleSheet(f"color: {COLORS['text_main']};")
        root.addWidget(self.chk_enabled)

        form = QFormLayout()
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        form.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)

        self.cb_smtp = QComboBox(); self.cb_smtp.setStyleSheet(self._combo_style())
        self.cb_smtp.addItem("— Sélectionner un profil SMTP —", None)
        for p in self._smtp_profiles:
            self.cb_smtp.addItem(p.name, p.id)
        form.addRow(self._label("Profil SMTP *"), self.cb_smtp)

        self.inp_recipients = QLineEdit()
        self.inp_recipients.setPlaceholderText("ex : sophie@entreprise.com, karim@entreprise.com")
        self.inp_recipients.setFixedHeight(34)
        self.inp_recipients.setStyleSheet(self._input_style())
        form.addRow(self._label("Destinataires *"), self.inp_recipients)

        self.cb_frequency = QComboBox(); self.cb_frequency.setStyleSheet(self._combo_style())
        self.cb_frequency.addItem("Quotidien", "DAILY")
        self.cb_frequency.addItem("Hebdomadaire", "WEEKLY")
        self.cb_frequency.currentIndexChanged.connect(self._on_frequency_changed)
        form.addRow(self._label("Fréquence"), self.cb_frequency)

        time_row = QHBoxLayout(); time_row.setSpacing(8)
        self.cb_day = QComboBox(); self.cb_day.setStyleSheet(self._combo_style())
        self.cb_day.setFixedWidth(120)
        for i, d in enumerate(DAYS_OF_WEEK):
            self.cb_day.addItem(d, i)
        self.inp_time = QLineEdit("07:00")
        self.inp_time.setFixedWidth(80); self.inp_time.setFixedHeight(34)
        self.inp_time.setStyleSheet(self._input_style())
        time_row.addWidget(self.cb_day)
        time_row.addWidget(self.inp_time)
        time_row.addStretch()
        time_widget = QWidget(); time_widget.setLayout(time_row)
        form.addRow(self._label("Heure d'envoi"), time_widget)

        root.addLayout(form)

        self.lbl_last_sent = QLabel()
        self.lbl_last_sent.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 11px;")
        root.addWidget(self.lbl_last_sent)

        root.addWidget(self._sep())
        btn_row = QHBoxLayout(); btn_row.setSpacing(10); btn_row.addStretch()
        btn_cancel = QPushButton("Annuler"); btn_cancel.setObjectName("secondary")
        btn_cancel.setFixedHeight(36); btn_cancel.clicked.connect(self.reject)
        btn_save = QPushButton("Enregistrer")
        btn_save.setFixedHeight(36); btn_save.clicked.connect(self._on_save)
        btn_row.addWidget(btn_cancel); btn_row.addWidget(btn_save)
        root.addLayout(btn_row)

    def _prefill(self):
        s = self._settings
        self.chk_enabled.setChecked(bool(s.digest_enabled))
        if s.digest_smtp_profile_id:
            idx = self.cb_smtp.findData(s.digest_smtp_profile_id)
            if idx >= 0:
                self.cb_smtp.setCurrentIndex(idx)
        self.inp_recipients.setText(s.digest_recipients or "")
        idx = self.cb_frequency.findData(s.digest_frequency or "DAILY")
        if idx >= 0:
            self.cb_frequency.setCurrentIndex(idx)
        self.inp_time.setText(s.digest_time or "07:00")
        day_idx = self.cb_day.findData(s.digest_day_of_week if s.digest_day_of_week is not None else 0)
        if day_idx >= 0:
            self.cb_day.setCurrentIndex(day_idx)
        self._on_frequency_changed()
        if s.digest_last_sent_at:
            self.lbl_last_sent.setText(
                f"Dernier envoi : {s.digest_last_sent_at.strftime('%d/%m/%Y %H:%M')}"
            )
        else:
            self.lbl_last_sent.setText("Aucun envoi pour l'instant.")

    def _on_frequency_changed(self):
        self.cb_day.setVisible(self.cb_frequency.currentData() == "WEEKLY")

    @staticmethod
    def _is_valid_time(value: str) -> bool:
        try:
            h, m = value.split(":")
            return 0 <= int(h) <= 23 and 0 <= int(m) <= 59
        except (ValueError, AttributeError):
            return False

    def _on_save(self):
        enabled = self.chk_enabled.isChecked()
        if enabled:
            if not self.cb_smtp.currentData():
                QMessageBox.warning(self, "Champ requis", "Sélectionner un profil SMTP.")
                return
            if not self.inp_recipients.text().strip():
                QMessageBox.warning(self, "Champ requis", "Saisir au moins un destinataire.")
                return
        if not self._is_valid_time(self.inp_time.text().strip()):
            QMessageBox.warning(self, "Champ invalide", "Heure d'envoi invalide (format HH:MM).")
            return

        from database import db_manager as db
        db.update_notification_settings(
            digest_enabled=enabled,
            digest_smtp_profile_id=self.cb_smtp.currentData(),
            digest_recipients=self.inp_recipients.text().strip(),
            digest_frequency=self.cb_frequency.currentData(),
            digest_time=self.inp_time.text().strip(),
            digest_day_of_week=self.cb_day.currentData(),
        )

        try:
            from core.scheduler import get_scheduler
            get_scheduler().refresh_digest_job()
        except RuntimeError:
            pass   # scheduler pas encore démarré (ne devrait pas arriver depuis l'UI)

        self.accept()

    def _input_style(self, error=False) -> str:
        border = COLORS["danger"] if error else COLORS["border"]
        return (f"QLineEdit {{ background: {COLORS['bg_card']}; border: 1px solid {border}; "
                f"border-radius: 4px; padding: 6px 10px; color: {COLORS['text_main']}; font-size: 13px; }}"
                f"QLineEdit:focus {{ border-color: {COLORS['accent']}; }}")

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

    def _label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(f"color: {COLORS['text_dim']}; font-size: 12px; font-weight: 500;")
        return lbl

    def _sep(self) -> QFrame:
        f = QFrame(); f.setFrameShape(QFrame.HLine)
        f.setStyleSheet(f"background: {COLORS['border']}; max-height: 1px;")
        return f

"""
DataScheduler — ui/main_window/settings_view.py
Vue Paramètres : réglages transverses à l'application, jusqu'ici câblés en dur dans le code sans
aucun endroit pour les consulter ou les modifier sans reconstruire l'exe (fuseau horaire du
scheduler, niveau de log, fréquences de rafraîchissement de l'UI…). Recherche + catégories à
gauche, détail à droite (patron "façon VSCode", maquette validée avec l'utilisateur) — intégré
dans la nav rail existante comme une vue de plus, pas une fenêtre à part.

Reprend aussi les champs du digest de notification (NotificationSettings, existant) dans la
catégorie "Notifications" — NotificationSettingsDialog est retiré au profit de cet écran unique.
"""

from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton, QFrame, QScrollArea,
    QComboBox, QCheckBox, QSpinBox, QLineEdit, QMessageBox,
)
from PySide6.QtCore import Qt, QTimer
from ui.styles import COLORS
from ui.step_editor.common import DAYS_OF_WEEK
from .widgets import _icon, _make_title, _make_subtitle, _make_search_input

_CATEGORIES = [
    {"key": "scheduler",     "label": "Ordonnanceur",    "icon": "fa5s.clock",
     "sub": "Comportement du planificateur APScheduler."},
    {"key": "logging",       "label": "Journalisation",  "icon": "fa5s.file-alt",
     "sub": "Fichier de logs (%APPDATA%/DataScheduler/logs)."},
    {"key": "interface",     "label": "Interface",       "icon": "fa5s.sync-alt",
     "sub": "Fréquences de rafraîchissement automatique."},
    {"key": "notifications", "label": "Notifications",   "icon": "fa5s.bell",
     "sub": "Résumé périodique des exécutions par email."},
]

_TIMEZONES = ["UTC", "Europe/Paris"]
_LOG_LEVELS = ["DEBUG", "INFO", "WARNING", "ERROR"]


def _input_style(error: bool = False) -> str:
    border = COLORS["danger"] if error else COLORS["border"]
    return (
        f"QLineEdit {{ background: {COLORS['bg_card']}; border: 1px solid {border}; "
        f"border-radius: 4px; padding: 6px 10px; color: {COLORS['text_main']}; font-size: 13px; }}"
        f"QLineEdit:focus {{ border-color: {COLORS['accent']}; }}"
    )


def _combo_style() -> str:
    return (
        f"QComboBox {{ background: {COLORS['bg_card']}; border: 1px solid {COLORS['border']}; "
        f"border-radius: 4px; padding: 6px 10px; color: {COLORS['text_main']}; font-size: 13px; }}"
        f"QComboBox:focus {{ border-color: {COLORS['accent']}; }}"
        f"QComboBox::drop-down {{ border: none; padding-right: 8px; }}"
        f"QComboBox QAbstractItemView {{ background: {COLORS['bg_card']}; "
        f"border: 1px solid {COLORS['border']}; "
        f"selection-background-color: {COLORS['bg_active']}; color: {COLORS['text_main']}; }}"
    )


def _spinbox_style() -> str:
    return (
        f"QSpinBox {{ background: {COLORS['bg_card']}; border: 1px solid {COLORS['border']}; "
        f"border-radius: 4px; padding: 6px 8px; color: {COLORS['text_main']}; font-size: 13px; }}"
        f"QSpinBox:focus {{ border-color: {COLORS['accent']}; }}"
    )


class SettingsView(QWidget):
    def __init__(self):
        super().__init__()
        self._active_category = "scheduler"
        self._row_widgets: list[dict] = []   # {category, label, desc, widget, category_chip}
        self._build_ui()
        self._prefill()

    # ── Construction ──────────────────────────

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        header = QVBoxLayout()
        header.setContentsMargins(32, 24, 32, 18)
        header.setSpacing(2)
        header.addWidget(_make_title("Paramètres"))
        header.addWidget(_make_subtitle(
            "Réglages transverses à l'application — jusqu'ici répartis en dur dans le code."))
        outer.addLayout(header)

        sep = QFrame(); sep.setObjectName("separator"); sep.setFrameShape(QFrame.HLine)
        outer.addWidget(sep)

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)

        body.addWidget(self._build_rail())

        vline = QFrame(); vline.setFrameShape(QFrame.VLine)
        vline.setStyleSheet(f"background: {COLORS['border']}; max-width: 1px;")
        body.addWidget(vline)

        body.addLayout(self._build_detail(), stretch=1)
        outer.addLayout(body, stretch=1)

    def _build_rail(self) -> QWidget:
        rail = QWidget()
        rail.setFixedWidth(240)
        rail_layout = QVBoxLayout(rail)
        rail_layout.setContentsMargins(16, 16, 16, 16)
        rail_layout.setSpacing(14)

        self.inp_search = _make_search_input("Rechercher un paramètre…")
        self.inp_search.setFixedWidth(208)
        self.inp_search.textChanged.connect(self._on_search_changed)
        rail_layout.addWidget(self.inp_search)

        self._category_buttons: dict[str, QPushButton] = {}
        for cat in _CATEGORIES:
            btn = QPushButton(f"  {cat['label']}")
            btn.setIcon(_icon(cat["icon"], COLORS["text_dim"]))
            btn.setFlat(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setFixedHeight(34)
            btn.clicked.connect(lambda _, k=cat["key"]: self._select_category(k))
            rail_layout.addWidget(btn)
            self._category_buttons[cat["key"]] = btn

        rail_layout.addStretch()
        return rail

    def _build_detail(self) -> QVBoxLayout:
        col = QVBoxLayout()
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(0)

        self._detail_title = QLabel()
        self._detail_title.setStyleSheet(
            f"font-size: 15px; font-weight: 700; color: {COLORS['text_main']};")
        self._detail_sub = QLabel()
        self._detail_sub.setStyleSheet(f"color: {COLORS['text_dim']}; font-size: 12px;")
        self._detail_sub.setWordWrap(True)

        title_block = QVBoxLayout()
        title_block.setContentsMargins(28, 20, 28, 4)
        title_block.setSpacing(2)
        title_block.addWidget(self._detail_title)
        title_block.addWidget(self._detail_sub)
        col.addLayout(title_block)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("background: transparent;")
        content = QWidget()
        scroll.setWidget(content)
        self._rows_layout = QVBoxLayout(content)
        self._rows_layout.setContentsMargins(28, 4, 28, 8)
        self._rows_layout.setSpacing(4)
        col.addWidget(scroll, stretch=1)

        self._build_rows()

        footer = QHBoxLayout()
        footer.setContentsMargins(28, 10, 28, 20)
        self._save_status_lbl = QLabel("")
        self._save_status_lbl.setStyleSheet(
            f"color: {COLORS['success']}; font-size: 12px; font-weight: 600;")
        footer.addWidget(self._save_status_lbl)
        footer.addStretch()
        btn_save = QPushButton("Enregistrer")
        btn_save.setFixedHeight(36); btn_save.setMinimumWidth(140)
        btn_save.clicked.connect(self._on_save)
        footer.addWidget(btn_save)
        col.addLayout(footer)

        self._select_category("scheduler")
        return col

    def _add_row(self, category: str, label: str, desc: str, widget, badge: str | None = None):
        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 10, 0, 10)
        row_layout.setSpacing(20)

        text_col = QVBoxLayout(); text_col.setSpacing(3)
        chip = QLabel(next(c["label"] for c in _CATEGORIES if c["key"] == category))
        chip.setStyleSheet(
            f"color: {COLORS['signal_pale']}; font-size: 9.5px; font-weight: 700; "
            f"text-transform: uppercase; letter-spacing: 0.4px;"
        )
        chip.setVisible(False)
        text_col.addWidget(chip)

        label_row = QHBoxLayout(); label_row.setSpacing(8)
        lbl = QLabel(label)
        lbl.setStyleSheet(f"color: {COLORS['text_main']}; font-size: 13px; font-weight: 600;")
        label_row.addWidget(lbl)
        if badge:
            badge_lbl = QLabel(badge.upper())
            badge_lbl.setStyleSheet(
                f"color: {COLORS['warning']}; font-size: 9.5px; font-weight: 700; "
                f"letter-spacing: 0.4px; padding: 2px 6px; border-radius: 3px; "
                f"background: rgba(232, 179, 57, 0.16); border: 1px solid rgba(232, 179, 57, 0.35);"
            )
            label_row.addWidget(badge_lbl)
        label_row.addStretch()
        text_col.addLayout(label_row)

        if desc:
            desc_lbl = QLabel(desc)
            desc_lbl.setWordWrap(True)
            desc_lbl.setStyleSheet(f"color: {COLORS['text_dim']}; font-size: 11.5px;")
            text_col.addWidget(desc_lbl)

        row_layout.addLayout(text_col, stretch=1)
        control_box = QWidget(); control_box.setFixedWidth(200)
        control_layout = QHBoxLayout(control_box)
        control_layout.setContentsMargins(0, 0, 0, 0)
        control_layout.addWidget(widget)
        row_layout.addWidget(control_box)

        sep = QFrame(); sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet(f"background: {COLORS['border']}; max-height: 1px;")

        wrapper = QWidget()
        wrapper_layout = QVBoxLayout(wrapper)
        wrapper_layout.setContentsMargins(0, 0, 0, 0)
        wrapper_layout.setSpacing(0)
        wrapper_layout.addWidget(row)
        wrapper_layout.addWidget(sep)

        self._rows_layout.addWidget(wrapper)
        self._row_widgets.append({
            "category": category, "label": label.lower(), "desc": desc.lower(),
            "wrapper": wrapper, "chip": chip,
        })

    def _build_rows(self):
        # Ordonnanceur
        self.cb_timezone = QComboBox(); self.cb_timezone.setStyleSheet(_combo_style())
        self.cb_timezone.addItems(_TIMEZONES)
        self._add_row("scheduler", "Fuseau horaire",
                       "Référence pour l'heure de toutes les planifications (Quotidien, Hebdo, "
                       "Cron). Redémarrage requis pour prendre effet.", self.cb_timezone)

        self.spin_misfire = QSpinBox(); self.spin_misfire.setStyleSheet(_spinbox_style())
        self.spin_misfire.setRange(1, 1440); self.spin_misfire.setSuffix(" min")
        self._add_row("scheduler", "Tolérance de rattrapage",
                       "Délai après lequel une exécution planifiée manquée (PC éteint) n'est "
                       "plus rattrapée du tout.", self.spin_misfire)

        self.chk_coalesce = QCheckBox(); self.chk_coalesce.setStyleSheet(
            f"color: {COLORS['text_main']};")
        self._add_row("scheduler", "Regrouper les rattrapages manqués",
                       "Si plusieurs déclenchements ont été manqués pendant la tolérance "
                       "ci-dessus, n'en rejoue qu'un seul plutôt que tous d'affilée.",
                       self.chk_coalesce)

        self.spin_max_concurrent = QSpinBox(); self.spin_max_concurrent.setStyleSheet(_spinbox_style())
        self.spin_max_concurrent.setRange(1, 100)
        self._add_row("scheduler", "Plafond d'exécutions simultanées",
                       "« Tout exécuter » et le déclenchement en chaîne n'ont aujourd'hui aucune "
                       "limite. Pas encore appliqué — arrive avec le prochain chantier sur le "
                       "suivi des ressources.", self.spin_max_concurrent, badge="Nouveau")

        # Journalisation
        self.cb_log_level = QComboBox(); self.cb_log_level.setStyleSheet(_combo_style())
        self.cb_log_level.addItems(_LOG_LEVELS)
        self._add_row("logging", "Niveau de journalisation",
                       "INFO ne conserve pas le détail utile pour diagnostiquer un comportement "
                       "rare.", self.cb_log_level)

        self.spin_log_mb = QSpinBox(); self.spin_log_mb.setStyleSheet(_spinbox_style())
        self.spin_log_mb.setRange(1, 500); self.spin_log_mb.setSuffix(" Mo")
        self._add_row("logging", "Taille max par fichier",
                       "Au-delà, rotation vers un nouveau fichier. Redémarrage requis.",
                       self.spin_log_mb)

        self.spin_log_backups = QSpinBox(); self.spin_log_backups.setStyleSheet(_spinbox_style())
        self.spin_log_backups.setRange(1, 50)
        self._add_row("logging", "Fichiers conservés",
                       "Nombre de fichiers de rotation gardés avant suppression du plus ancien. "
                       "Redémarrage requis.", self.spin_log_backups)

        # Interface
        self.spin_dashboard_refresh = QSpinBox(); self.spin_dashboard_refresh.setStyleSheet(_spinbox_style())
        self.spin_dashboard_refresh.setRange(5, 600); self.spin_dashboard_refresh.setSuffix(" s")
        self._add_row("interface", "Rafraîchissement — Dashboard",
                       "Vue d'ensemble, badges d'état des pipelines. Redémarrage requis.",
                       self.spin_dashboard_refresh)

        self.spin_pipelines_refresh = QSpinBox(); self.spin_pipelines_refresh.setStyleSheet(_spinbox_style())
        self.spin_pipelines_refresh.setRange(5, 600); self.spin_pipelines_refresh.setSuffix(" s")
        self._add_row("interface", "Rafraîchissement — Pipelines",
                       "Liste des pipelines et leur statut courant. Redémarrage requis.",
                       self.spin_pipelines_refresh)

        self.spin_live_log_refresh = QSpinBox(); self.spin_live_log_refresh.setStyleSheet(_spinbox_style())
        self.spin_live_log_refresh.setRange(1, 60); self.spin_live_log_refresh.setSuffix(" s")
        self._add_row("interface", "Log d'exécution en direct",
                       "Fenêtre de suivi d'un run en cours. Effet à la prochaine ouverture.",
                       self.spin_live_log_refresh)

        self.spin_trace_glow_refresh = QSpinBox(); self.spin_trace_glow_refresh.setStyleSheet(_spinbox_style())
        self.spin_trace_glow_refresh.setRange(1, 60); self.spin_trace_glow_refresh.setSuffix(" s")
        self._add_row("interface", "Traçage lumineux (éditeur graphique)",
                       "Interrogation de l'étape en cours pour surligner le nœud actif. Effet à "
                       "la prochaine ouverture.", self.spin_trace_glow_refresh)

        # Notifications
        self.chk_digest_enabled = QCheckBox(); self.chk_digest_enabled.setStyleSheet(
            f"color: {COLORS['text_main']};")
        self._add_row("notifications", "Résumé périodique activé",
                       "Envoie un email récapitulatif des exécutions depuis le dernier envoi.",
                       self.chk_digest_enabled)

        self.cb_smtp = QComboBox(); self.cb_smtp.setStyleSheet(_combo_style())
        self._add_row("notifications", "Profil SMTP",
                       "Utilisé pour l'envoi du résumé.", self.cb_smtp)

        self.inp_recipients = QLineEdit(); self.inp_recipients.setFixedHeight(34)
        self.inp_recipients.setStyleSheet(_input_style())
        self.inp_recipients.setPlaceholderText("ex : sophie@entreprise.com, karim@entreprise.com")
        self._add_row("notifications", "Destinataires",
                       "Adresses séparées par une virgule.", self.inp_recipients)

        self.cb_frequency = QComboBox(); self.cb_frequency.setStyleSheet(_combo_style())
        self.cb_frequency.addItem("Quotidien", "DAILY")
        self.cb_frequency.addItem("Hebdomadaire", "WEEKLY")
        self.cb_frequency.currentIndexChanged.connect(self._on_frequency_changed)
        self._add_row("notifications", "Fréquence", "", self.cb_frequency)

        self.cb_day = QComboBox(); self.cb_day.setStyleSheet(_combo_style())
        for i, d in enumerate(DAYS_OF_WEEK):
            self.cb_day.addItem(d, i)
        self._add_row("notifications", "Jour (si hebdomadaire)", "", self.cb_day)

        self.inp_time = QLineEdit(); self.inp_time.setFixedHeight(34)
        self.inp_time.setStyleSheet(_input_style())
        self._add_row("notifications", "Heure d'envoi", "Format HH:MM.", self.inp_time)

    # ── Données ───────────────────────────────

    def _prefill(self):
        from database import db_manager as db
        settings = db.get_app_settings()

        idx = self.cb_timezone.findText(settings.timezone)
        self.cb_timezone.setCurrentIndex(idx if idx >= 0 else 0)
        self.spin_misfire.setValue(settings.misfire_grace_time_min)
        self.chk_coalesce.setChecked(settings.coalesce_missed_runs)
        self.spin_max_concurrent.setValue(settings.max_concurrent_runs)

        idx = self.cb_log_level.findText(settings.log_level)
        self.cb_log_level.setCurrentIndex(idx if idx >= 0 else 1)
        self.spin_log_mb.setValue(max(1, settings.log_max_bytes // 1_000_000))
        self.spin_log_backups.setValue(settings.log_backup_count)

        self.spin_dashboard_refresh.setValue(settings.dashboard_refresh_s)
        self.spin_pipelines_refresh.setValue(settings.pipelines_refresh_s)
        self.spin_live_log_refresh.setValue(settings.live_log_refresh_s)
        self.spin_trace_glow_refresh.setValue(settings.trace_glow_refresh_s)

        notif = db.get_notification_settings()
        self._smtp_profiles = db.get_smtp_profiles()
        self.cb_smtp.clear()
        self.cb_smtp.addItem("— Sélectionner un profil SMTP —", None)
        for p in self._smtp_profiles:
            self.cb_smtp.addItem(p.name, p.id)
        self.chk_digest_enabled.setChecked(bool(notif.digest_enabled))
        if notif.digest_smtp_profile_id:
            idx = self.cb_smtp.findData(notif.digest_smtp_profile_id)
            if idx >= 0:
                self.cb_smtp.setCurrentIndex(idx)
        self.inp_recipients.setText(notif.digest_recipients or "")
        idx = self.cb_frequency.findData(notif.digest_frequency or "DAILY")
        if idx >= 0:
            self.cb_frequency.setCurrentIndex(idx)
        self.inp_time.setText(notif.digest_time or "07:00")
        day_idx = self.cb_day.findData(notif.digest_day_of_week if notif.digest_day_of_week is not None else 0)
        if day_idx >= 0:
            self.cb_day.setCurrentIndex(day_idx)
        self._on_frequency_changed()

    # ── Navigation catégories / recherche ─────

    def select_category(self, key: str):
        """Point d'entrée public — utilisé par le raccourci 🔔 du Dashboard pour amener
        directement sur la catégorie Notifications."""
        self.inp_search.clear()
        self._select_category(key)

    def _select_category(self, key: str):
        self._active_category = key
        cat = next(c for c in _CATEGORIES if c["key"] == key)
        self._detail_title.setText(cat["label"])
        self._detail_sub.setText(cat["sub"])
        for k, btn in self._category_buttons.items():
            active = k == key
            cat_icon = next(c["icon"] for c in _CATEGORIES if c["key"] == k)
            btn.setIcon(_icon(cat_icon, COLORS["signal"] if active else COLORS["text_dim"]))
            btn.setStyleSheet(
                f"QPushButton {{ text-align: left; border: none; border-radius: 5px; "
                f"padding: 0 10px; color: {COLORS['text_main'] if active else COLORS['text_dim']}; "
                f"background: {COLORS['bg_card'] if active else 'transparent'}; "
                f"border-left: 2px solid {COLORS['signal'] if active else 'transparent'}; }}"
                f"QPushButton:hover {{ background: {COLORS['bg_hover']}; }}"
            )
        for row in self._row_widgets:
            row["chip"].setVisible(False)
            row["wrapper"].setVisible(row["category"] == key)
        self._on_frequency_changed()   # ré-applique le masquage conditionnel de "Jour"

    def _on_search_changed(self, text: str):
        query = text.strip().lower()
        if not query:
            self._select_category(self._active_category)
            return
        for row in self._row_widgets:
            match = query in row["label"] or query in row["desc"]
            row["wrapper"].setVisible(match)
            row["chip"].setVisible(match)
        self._detail_title.setText("Résultats")
        self._detail_sub.setText(f"Paramètres correspondant à « {text.strip()} »")

    def _on_frequency_changed(self):
        weekly = self.cb_frequency.currentData() == "WEEKLY"
        for row in self._row_widgets:
            if row["label"] == "jour (si hebdomadaire)":
                row["wrapper"].setVisible(weekly and self._active_category == "notifications"
                                           and not self.inp_search.text().strip())

    # ── Enregistrement ────────────────────────

    @staticmethod
    def _is_valid_time(value: str) -> bool:
        try:
            h, m = value.split(":")
            return 0 <= int(h) <= 23 and 0 <= int(m) <= 59
        except (ValueError, AttributeError):
            return False

    def _on_save(self):
        digest_enabled = self.chk_digest_enabled.isChecked()
        if digest_enabled:
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
        db.update_app_settings(
            timezone=self.cb_timezone.currentText(),
            misfire_grace_time_min=self.spin_misfire.value(),
            coalesce_missed_runs=self.chk_coalesce.isChecked(),
            max_concurrent_runs=self.spin_max_concurrent.value(),
            log_level=self.cb_log_level.currentText(),
            log_max_bytes=self.spin_log_mb.value() * 1_000_000,
            log_backup_count=self.spin_log_backups.value(),
            dashboard_refresh_s=self.spin_dashboard_refresh.value(),
            pipelines_refresh_s=self.spin_pipelines_refresh.value(),
            live_log_refresh_s=self.spin_live_log_refresh.value(),
            trace_glow_refresh_s=self.spin_trace_glow_refresh.value(),
        )
        db.update_notification_settings(
            digest_enabled=digest_enabled,
            digest_smtp_profile_id=self.cb_smtp.currentData(),
            digest_recipients=self.inp_recipients.text().strip(),
            digest_frequency=self.cb_frequency.currentData(),
            digest_time=self.inp_time.text().strip(),
            digest_day_of_week=self.cb_day.currentData(),
        )

        import logging
        logging.getLogger().setLevel(self.cb_log_level.currentText())

        try:
            from core.scheduler import get_scheduler
            sched = get_scheduler()
            sched.apply_settings()
            sched.refresh_digest_job()
        except RuntimeError:
            pass   # scheduler pas encore démarré (ne devrait pas arriver depuis l'UI)

        # Confirmation non bloquante (pas de QMessageBox.information ici, volontairement) : un
        # "Enregistrer" qu'on peut cliquer plusieurs fois de suite sans devoir fermer une boîte
        # de dialogue à chaque fois est plus confortable sur un écran de paramètres — et ça évite
        # tout risque de blocage en environnement offscreen (tests) où rien ne clique le bouton.
        self._save_status_lbl.setText(
            "Enregistré ✓ — certains réglages ne prennent effet qu'au prochain redémarrage.")
        QTimer.singleShot(4000, lambda: self._save_status_lbl.setText(""))

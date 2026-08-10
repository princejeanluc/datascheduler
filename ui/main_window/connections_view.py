"""
DataScheduler — ui/main_window/connections_view.py
Vue Connexions : profils Oracle/FTP/SMTP/BDD génériques.
"""

from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton, QFrame,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QMessageBox, QTabWidget,
)
from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor
from ui.styles import COLORS
from .widgets import _icon, _action_btn, _configure_columns, _filter_table_rows, _make_search_input, _make_empty_label, _make_title, _make_subtitle, _status_str


def _health_badge(success) -> QLabel:
    """Statut du dernier test de connexion, déjà stocké sur chaque profil (bilan de santé,
    chantier C.4/D.1) — ici simplement affiché en ligne au lieu d'être réservé à la fenêtre
    modale "Bilan de santé"."""
    if success is True:
        text, obj_name = "OK", "badge_success"
    elif success is False:
        text, obj_name = "Échec", "badge_failed"
    else:
        text, obj_name = "Jamais testé", "badge_idle"
    lbl = QLabel(text); lbl.setObjectName(obj_name)
    lbl.setAlignment(Qt.AlignCenter)
    return lbl


class ConnectionsView(QWidget):
    def __init__(self):
        super().__init__()
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(24)

        header = QHBoxLayout()
        title_col = QVBoxLayout(); title_col.setSpacing(2)
        title_col.addWidget(_make_title("Connexions"))
        title_col.addWidget(_make_subtitle("Profils de bases de données, FTP et SMTP réutilisables dans les pipelines"))
        header.addLayout(title_col); header.addStretch()
        self.inp_search = _make_search_input("Rechercher un profil…")
        self.inp_search.textChanged.connect(self._on_search_changed)
        header.addWidget(self.inp_search)
        btn_health = QPushButton("  Bilan de santé"); btn_health.setObjectName("secondary")
        btn_health.setFixedHeight(36)
        btn_health.setIcon(_icon("fa5s.heartbeat", COLORS["text_main"]))
        btn_health.setIconSize(QSize(13, 13))
        btn_health.clicked.connect(self._on_health_check)
        header.addWidget(btn_health)
        layout.addLayout(header)

        sep = QFrame(); sep.setObjectName("separator"); sep.setFrameShape(QFrame.HLine)
        layout.addWidget(sep)

        # Regroupées par usage plutôt que par technologie brute : une pile de 5 panneaux
        # verticaux complets ne passait plus à l'échelle, et SSH/Kerberos (toujours utilisés en
        # paire pour l'étape Spark SQL) gagnent à être visuellement co-localisés.
        self.tabs = QTabWidget()

        tab_db = QWidget(); tab_db_layout = QVBoxLayout(tab_db)
        tab_db_layout.setContentsMargins(0, 16, 0, 0); tab_db_layout.setSpacing(20)
        tab_db_layout.addWidget(self._build_databases_panel())
        tab_db_layout.addStretch()
        self.tabs.addTab(tab_db, "Bases de données")

        tab_files = QWidget(); tab_files_layout = QVBoxLayout(tab_files)
        tab_files_layout.setContentsMargins(0, 16, 0, 0); tab_files_layout.setSpacing(20)
        tab_files_layout.addWidget(self._build_ftp_panel())
        tab_files_layout.addWidget(self._build_smtp_panel())
        tab_files_layout.addStretch()
        self.tabs.addTab(tab_files, "Fichiers && notifications")

        tab_bigdata = QWidget(); tab_bigdata_layout = QVBoxLayout(tab_bigdata)
        tab_bigdata_layout.setContentsMargins(0, 16, 0, 0); tab_bigdata_layout.setSpacing(20)
        tab_bigdata_layout.addWidget(self._build_ssh_panel())
        tab_bigdata_layout.addWidget(self._build_kerberos_panel())
        tab_bigdata_layout.addWidget(self._build_elevation_panel())
        tab_bigdata_layout.addStretch()
        self.tabs.addTab(tab_bigdata, "Big Data / Spark SQL")

        layout.addWidget(self.tabs, stretch=1)

        self.refresh()

    # ── Panels ───────────────────────────────────

    def _build_databases_panel(self) -> QFrame:
        card = QFrame(); card.setObjectName("card")
        vl = QVBoxLayout(card); vl.setContentsMargins(20, 18, 20, 18); vl.setSpacing(14)

        top = QHBoxLayout()
        lbl = QLabel("Bases de données")
        lbl.setStyleSheet("font-size: 14px; font-weight: 700; background: transparent; border: none;")
        btn = QPushButton("  Nouveau profil"); btn.setFixedHeight(32)
        btn.setIcon(_icon("fa5s.plus", "#000000")); btn.setIconSize(QSize(12, 12))
        btn.clicked.connect(self._on_new_database)
        top.addWidget(lbl); top.addStretch(); top.addWidget(btn)
        vl.addLayout(top)

        hdrs = ["Nom", "Type", "Hôte", "Port", "Utilisateur", "État"]
        self.database_table = self._make_table(hdrs, stretch_cols={0, 2})
        vl.addWidget(self.database_table)
        self._database_empty = _make_empty_label(
            "Aucun profil de base de données — cliquez sur « Nouveau profil » "
            "(Oracle, MySQL, PostgreSQL ou SQL Server)."
        )
        self._database_empty.setVisible(False)
        vl.addWidget(self._database_empty)
        return card

    def _build_ftp_panel(self) -> QFrame:
        card = QFrame(); card.setObjectName("card")
        vl = QVBoxLayout(card); vl.setContentsMargins(20, 18, 20, 18); vl.setSpacing(14)

        top = QHBoxLayout()
        lbl = QLabel("FTP / FTPS / SFTP")
        lbl.setStyleSheet("font-size: 14px; font-weight: 700; background: transparent; border: none;")
        btn = QPushButton("  Nouveau profil FTP"); btn.setFixedHeight(32)
        btn.setIcon(_icon("fa5s.plus", "#000000")); btn.setIconSize(QSize(12, 12))
        btn.clicked.connect(self._on_new_ftp)
        top.addWidget(lbl); top.addStretch(); top.addWidget(btn)
        vl.addLayout(top)

        hdrs = ["Nom", "Hôte", "Port", "Protocole", "Utilisateur", "État"]
        self.ftp_table = self._make_table(hdrs, stretch_cols={0, 1})
        vl.addWidget(self.ftp_table)
        self._ftp_empty = _make_empty_label("Aucun profil FTP — cliquez sur « Nouveau profil FTP ».")
        self._ftp_empty.setVisible(False)
        vl.addWidget(self._ftp_empty)
        return card

    def _build_smtp_panel(self) -> QFrame:
        card = QFrame(); card.setObjectName("card")
        vl = QVBoxLayout(card); vl.setContentsMargins(20, 18, 20, 18); vl.setSpacing(14)

        top = QHBoxLayout()
        lbl = QLabel("SMTP")
        lbl.setStyleSheet("font-size: 14px; font-weight: 700; background: transparent; border: none;")
        btn = QPushButton("  Nouveau profil SMTP"); btn.setFixedHeight(32)
        btn.setIcon(_icon("fa5s.plus", "#000000")); btn.setIconSize(QSize(12, 12))
        btn.clicked.connect(self._on_new_smtp)
        top.addWidget(lbl); top.addStretch(); top.addWidget(btn)
        vl.addLayout(top)

        hdrs = ["Nom", "Hôte", "Port", "Sécurité", "Expéditeur", "État"]
        self.smtp_table = self._make_table(hdrs, stretch_cols={0, 1, 4})
        vl.addWidget(self.smtp_table)
        self._smtp_empty = _make_empty_label("Aucun profil SMTP — cliquez sur « Nouveau profil SMTP ».")
        self._smtp_empty.setVisible(False)
        vl.addWidget(self._smtp_empty)
        return card

    def _build_ssh_panel(self) -> QFrame:
        card = QFrame(); card.setObjectName("card")
        vl = QVBoxLayout(card); vl.setContentsMargins(20, 18, 20, 18); vl.setSpacing(14)

        top = QHBoxLayout()
        lbl = QLabel("SSH (nœud edge / master — étape Spark SQL)")
        lbl.setStyleSheet("font-size: 14px; font-weight: 700; background: transparent; border: none;")
        btn = QPushButton("  Nouveau profil SSH"); btn.setFixedHeight(32)
        btn.setIcon(_icon("fa5s.plus", "#000000")); btn.setIconSize(QSize(12, 12))
        btn.clicked.connect(self._on_new_ssh)
        top.addWidget(lbl); top.addStretch(); top.addWidget(btn)
        vl.addLayout(top)

        hdrs = ["Nom", "Hôte", "Port", "Utilisateur", "Via", "État"]
        self.ssh_table = self._make_table(hdrs, stretch_cols={0, 1})
        vl.addWidget(self.ssh_table)
        self._ssh_empty = _make_empty_label("Aucun profil SSH — cliquez sur « Nouveau profil SSH ».")
        self._ssh_empty.setVisible(False)
        vl.addWidget(self._ssh_empty)
        return card

    def _build_kerberos_panel(self) -> QFrame:
        card = QFrame(); card.setObjectName("card")
        vl = QVBoxLayout(card); vl.setContentsMargins(20, 18, 20, 18); vl.setSpacing(14)

        top = QHBoxLayout()
        lbl = QLabel("Kerberos (kinit — étape Spark SQL)")
        lbl.setStyleSheet("font-size: 14px; font-weight: 700; background: transparent; border: none;")
        btn = QPushButton("  Nouveau profil Kerberos"); btn.setFixedHeight(32)
        btn.setIcon(_icon("fa5s.plus", "#000000")); btn.setIconSize(QSize(12, 12))
        btn.clicked.connect(self._on_new_kerberos)
        top.addWidget(lbl); top.addStretch(); top.addWidget(btn)
        vl.addLayout(top)

        hdrs = ["Nom", "Principal", "État"]
        self.kerberos_table = self._make_table(hdrs, stretch_cols={0, 1})
        vl.addWidget(self.kerberos_table)
        self._kerberos_empty = _make_empty_label(
            "Aucun profil Kerberos — cliquez sur « Nouveau profil Kerberos »."
        )
        self._kerberos_empty.setVisible(False)
        vl.addWidget(self._kerberos_empty)
        return card

    def _build_elevation_panel(self) -> QFrame:
        card = QFrame(); card.setObjectName("card")
        vl = QVBoxLayout(card); vl.setContentsMargins(20, 18, 20, 18); vl.setSpacing(14)

        top = QHBoxLayout()
        lbl = QLabel("Élévation (sudo su — étape Export Sqoop)")
        lbl.setStyleSheet("font-size: 14px; font-weight: 700; background: transparent; border: none;")
        btn = QPushButton("  Nouveau profil d'élévation"); btn.setFixedHeight(32)
        btn.setIcon(_icon("fa5s.plus", "#000000")); btn.setIconSize(QSize(12, 12))
        btn.clicked.connect(self._on_new_elevation)
        top.addWidget(lbl); top.addStretch(); top.addWidget(btn)
        vl.addLayout(top)

        hdrs = ["Nom", "Utilisateur cible", "État"]
        self.elevation_table = self._make_table(hdrs, stretch_cols={0, 1})
        vl.addWidget(self.elevation_table)
        self._elevation_empty = _make_empty_label(
            "Aucun profil d'élévation — cliquez sur « Nouveau profil d'élévation »."
        )
        self._elevation_empty.setVisible(False)
        vl.addWidget(self._elevation_empty)
        return card

    def _make_table(self, headers: list, stretch_cols: set) -> QTableWidget:
        t = QTableWidget(0, len(headers) + 1)
        t.setHorizontalHeaderLabels(headers + [""])
        t.verticalHeader().setVisible(False)
        t.setEditTriggers(QAbstractItemView.NoEditTriggers)
        t.setSelectionBehavior(QAbstractItemView.SelectRows)
        t.setShowGrid(False)
        _configure_columns(t, stretch_cols)
        t.horizontalHeader().setSectionResizeMode(len(headers), QHeaderView.Fixed)
        t.setColumnWidth(len(headers), 90)
        return t

    # ── Recherche ────────────────────────────────

    def _on_search_changed(self, text: str):
        _filter_table_rows(self.database_table, text, columns=[0, 1, 2, 3, 4])
        _filter_table_rows(self.ftp_table, text, columns=[0, 1, 2, 3, 4])
        _filter_table_rows(self.smtp_table, text, columns=[0, 1, 2, 3, 4])
        _filter_table_rows(self.ssh_table, text, columns=[0, 1, 2, 3])
        _filter_table_rows(self.kerberos_table, text, columns=[0, 1])
        _filter_table_rows(self.elevation_table, text, columns=[0, 1])

    # ── Refresh ──────────────────────────────────

    def refresh(self):
        self._refresh_databases()
        self._refresh_ftp()
        self._refresh_smtp()
        self._refresh_ssh()
        self._refresh_kerberos()
        self._refresh_elevation()
        self._on_search_changed(self.inp_search.text())

    def _refresh_databases(self):
        from database import db_manager as db
        from ui.dialogs import DB_TYPE_META
        profiles = db.list_all_db_profiles()
        self.database_table.setVisible(bool(profiles))
        self._database_empty.setVisible(not profiles)
        self.database_table.setRowCount(len(profiles))
        for r_idx, p in enumerate(profiles):
            type_label = DB_TYPE_META.get(p["db_type"], {}).get("label", p["db_type"])
            cells = [p["name"], type_label, p["host"], str(p["port"]), p["username"]]
            for c_idx, cell in enumerate(cells):
                item = QTableWidgetItem(cell)
                item.setForeground(QColor(COLORS["text_main"]))
                self.database_table.setItem(r_idx, c_idx, item)
            self.database_table.setCellWidget(r_idx, 5, _health_badge(p.get("last_test_success")))
            pid, dtype = p["id"], p["db_type"]
            w = QWidget(); hl = QHBoxLayout(w); hl.setContentsMargins(4, 4, 4, 4); hl.setSpacing(4)
            btn_edit = _action_btn("fa5s.pencil-alt", object_name="secondary", tooltip="Modifier")
            btn_del  = _action_btn("fa5s.trash-alt",  object_name="danger",    tooltip="Supprimer")
            btn_edit.clicked.connect(lambda _, i=pid, t=dtype: self._on_edit_database(i, t))
            btn_del.clicked.connect(lambda _, i=pid, t=dtype: self._on_delete_database(i, t))
            hl.addWidget(btn_edit); hl.addWidget(btn_del); hl.addStretch()
            self.database_table.setCellWidget(r_idx, 6, w)
            self.database_table.setRowHeight(r_idx, 44)

    def _refresh_ftp(self):
        from database import db_manager as db
        profiles = db.get_ftp_profiles()
        self.ftp_table.setVisible(bool(profiles))
        self._ftp_empty.setVisible(not profiles)
        self.ftp_table.setRowCount(len(profiles))
        for r_idx, p in enumerate(profiles):
            protocol = _status_str(p.protocol)
            cells = [p.name, p.host, str(p.port), protocol, p.username]
            for c_idx, cell in enumerate(cells):
                item = QTableWidgetItem(cell)
                item.setForeground(QColor(COLORS["text_main"]))
                self.ftp_table.setItem(r_idx, c_idx, item)
            self.ftp_table.setCellWidget(r_idx, 5, _health_badge(p.last_test_success))
            pid = p.id
            w = QWidget(); hl = QHBoxLayout(w); hl.setContentsMargins(4, 4, 4, 4); hl.setSpacing(4)
            btn_edit = _action_btn("fa5s.pencil-alt", object_name="secondary", tooltip="Modifier")
            btn_del  = _action_btn("fa5s.trash-alt",  object_name="danger",    tooltip="Supprimer")
            btn_edit.clicked.connect(lambda _, i=pid: self._on_edit_ftp(i))
            btn_del.clicked.connect(lambda _, i=pid: self._on_delete_ftp(i))
            hl.addWidget(btn_edit); hl.addWidget(btn_del); hl.addStretch()
            self.ftp_table.setCellWidget(r_idx, 6, w)
            self.ftp_table.setRowHeight(r_idx, 44)

    def _refresh_smtp(self):
        from database import db_manager as db
        profiles = db.get_smtp_profiles()
        self.smtp_table.setVisible(bool(profiles))
        self._smtp_empty.setVisible(not profiles)
        self.smtp_table.setRowCount(len(profiles))
        for r_idx, p in enumerate(profiles):
            security = "STARTTLS" if p.use_tls else "Aucune"
            cells = [p.name, p.host, str(p.port), security, p.from_address]
            for c_idx, cell in enumerate(cells):
                item = QTableWidgetItem(cell)
                item.setForeground(QColor(COLORS["text_main"]))
                self.smtp_table.setItem(r_idx, c_idx, item)
            self.smtp_table.setCellWidget(r_idx, 5, _health_badge(p.last_test_success))
            pid = p.id
            w = QWidget(); hl = QHBoxLayout(w); hl.setContentsMargins(4, 4, 4, 4); hl.setSpacing(4)
            btn_edit = _action_btn("fa5s.pencil-alt", object_name="secondary", tooltip="Modifier")
            btn_del  = _action_btn("fa5s.trash-alt",  object_name="danger",    tooltip="Supprimer")
            btn_edit.clicked.connect(lambda _, i=pid: self._on_edit_smtp(i))
            btn_del.clicked.connect(lambda _, i=pid: self._on_delete_smtp(i))
            hl.addWidget(btn_edit); hl.addWidget(btn_del); hl.addStretch()
            self.smtp_table.setCellWidget(r_idx, 6, w)
            self.smtp_table.setRowHeight(r_idx, 44)

    def _refresh_ssh(self):
        from database import db_manager as db
        profiles = db.get_ssh_profiles()
        name_by_id = {p.id: p.name for p in profiles}
        self.ssh_table.setVisible(bool(profiles))
        self._ssh_empty.setVisible(not profiles)
        self.ssh_table.setRowCount(len(profiles))
        for r_idx, p in enumerate(profiles):
            via = name_by_id.get(p.jump_via_id, "—") if p.jump_via_id else "—"
            cells = [p.name, p.host, str(p.port), p.username, via]
            for c_idx, cell in enumerate(cells):
                item = QTableWidgetItem(cell)
                item.setForeground(QColor(COLORS["text_main"]))
                self.ssh_table.setItem(r_idx, c_idx, item)
            self.ssh_table.setCellWidget(r_idx, 5, _health_badge(p.last_test_success))
            pid = p.id
            w = QWidget(); hl = QHBoxLayout(w); hl.setContentsMargins(4, 4, 4, 4); hl.setSpacing(4)
            btn_edit = _action_btn("fa5s.pencil-alt", object_name="secondary", tooltip="Modifier")
            btn_del  = _action_btn("fa5s.trash-alt",  object_name="danger",    tooltip="Supprimer")
            btn_edit.clicked.connect(lambda _, i=pid: self._on_edit_ssh(i))
            btn_del.clicked.connect(lambda _, i=pid: self._on_delete_ssh(i))
            hl.addWidget(btn_edit); hl.addWidget(btn_del); hl.addStretch()
            self.ssh_table.setCellWidget(r_idx, 6, w)
            self.ssh_table.setRowHeight(r_idx, 44)

    def _refresh_kerberos(self):
        from database import db_manager as db
        profiles = db.get_kerberos_profiles()
        self.kerberos_table.setVisible(bool(profiles))
        self._kerberos_empty.setVisible(not profiles)
        self.kerberos_table.setRowCount(len(profiles))
        for r_idx, p in enumerate(profiles):
            cells = [p.name, p.principal]
            for c_idx, cell in enumerate(cells):
                item = QTableWidgetItem(cell)
                item.setForeground(QColor(COLORS["text_main"]))
                self.kerberos_table.setItem(r_idx, c_idx, item)
            self.kerberos_table.setCellWidget(r_idx, 2, _health_badge(p.last_test_success))
            pid = p.id
            w = QWidget(); hl = QHBoxLayout(w); hl.setContentsMargins(4, 4, 4, 4); hl.setSpacing(4)
            btn_edit = _action_btn("fa5s.pencil-alt", object_name="secondary", tooltip="Modifier")
            btn_del  = _action_btn("fa5s.trash-alt",  object_name="danger",    tooltip="Supprimer")
            btn_edit.clicked.connect(lambda _, i=pid: self._on_edit_kerberos(i))
            btn_del.clicked.connect(lambda _, i=pid: self._on_delete_kerberos(i))
            hl.addWidget(btn_edit); hl.addWidget(btn_del); hl.addStretch()
            self.kerberos_table.setCellWidget(r_idx, 3, w)
            self.kerberos_table.setRowHeight(r_idx, 44)

    def _refresh_elevation(self):
        from database import db_manager as db
        profiles = db.get_elevation_profiles()
        self.elevation_table.setVisible(bool(profiles))
        self._elevation_empty.setVisible(not profiles)
        self.elevation_table.setRowCount(len(profiles))
        for r_idx, p in enumerate(profiles):
            cells = [p.name, p.target_user]
            for c_idx, cell in enumerate(cells):
                item = QTableWidgetItem(cell)
                item.setForeground(QColor(COLORS["text_main"]))
                self.elevation_table.setItem(r_idx, c_idx, item)
            self.elevation_table.setCellWidget(r_idx, 2, _health_badge(p.last_test_success))
            pid = p.id
            w = QWidget(); hl = QHBoxLayout(w); hl.setContentsMargins(4, 4, 4, 4); hl.setSpacing(4)
            btn_edit = _action_btn("fa5s.pencil-alt", object_name="secondary", tooltip="Modifier")
            btn_del  = _action_btn("fa5s.trash-alt",  object_name="danger",    tooltip="Supprimer")
            btn_edit.clicked.connect(lambda _, i=pid: self._on_edit_elevation(i))
            btn_del.clicked.connect(lambda _, i=pid: self._on_delete_elevation(i))
            hl.addWidget(btn_edit); hl.addWidget(btn_del); hl.addStretch()
            self.elevation_table.setCellWidget(r_idx, 3, w)
            self.elevation_table.setRowHeight(r_idx, 44)

    # ── Callbacks ────────────────────────────────

    def _on_health_check(self):
        from ui.dialogs import ConnectionHealthDialog
        ConnectionHealthDialog(self).exec()

    def _on_new_database(self):
        from ui.dialogs import DbTypeChooserDialog, OracleDialog, DatabaseProfileDialog
        chooser = DbTypeChooserDialog(self)
        if not chooser.exec():
            return
        db_type = chooser.chosen_type
        dlg = OracleDialog(self) if db_type == "ORACLE" else DatabaseProfileDialog(self, db_type=db_type)
        if dlg.exec():
            self._refresh_databases()

    def _on_edit_database(self, profile_id: int, db_type: str):
        from database import db_manager as db
        from ui.dialogs import OracleDialog, DatabaseProfileDialog
        if db_type == "ORACLE":
            p = db.get_oracle_profile(profile_id)
            dlg = OracleDialog(self, profile=p) if p else None
        else:
            p = db.get_database_profile(profile_id)
            dlg = DatabaseProfileDialog(self, db_type=db_type, profile=p) if p else None
        if dlg and dlg.exec():
            self._refresh_databases()

    def _on_delete_database(self, profile_id: int, db_type: str):
        from database import db_manager as db
        from ui.dialogs import DB_TYPE_META
        used_by = db.find_pipelines_using_db_profile(db_type, profile_id)
        label = DB_TYPE_META.get(db_type, {}).get("label", db_type)
        if not self._confirm_delete(label, used_by):
            return
        if db_type == "ORACLE":
            db.delete_oracle_profile(profile_id)
        else:
            db.delete_database_profile(profile_id)
        self._refresh_databases()

    def _on_new_ftp(self):
        from ui.dialogs import FtpDialog
        dlg = FtpDialog(self)
        if dlg.exec():
            self._refresh_ftp()

    def _on_edit_ftp(self, profile_id: int):
        from database import db_manager as db
        from ui.dialogs import FtpDialog
        p = db.get_ftp_profile(profile_id)
        if p and FtpDialog(self, profile=p).exec():
            self._refresh_ftp()

    def _on_delete_ftp(self, profile_id: int):
        from database import db_manager as db
        used_by = db.find_pipelines_using_profile("ftp_profile_id", profile_id)
        if not self._confirm_delete("FTP", used_by):
            return
        db.delete_ftp_profile(profile_id)
        self._refresh_ftp()

    def _on_new_smtp(self):
        from ui.dialogs import SmtpDialog
        dlg = SmtpDialog(self)
        if dlg.exec():
            self._refresh_smtp()

    def _on_edit_smtp(self, profile_id: int):
        from database import db_manager as db
        from ui.dialogs import SmtpDialog
        p = db.get_smtp_profile(profile_id)
        if p and SmtpDialog(self, profile=p).exec():
            self._refresh_smtp()

    def _on_delete_smtp(self, profile_id: int):
        from database import db_manager as db
        used_by = db.find_pipelines_using_profile("smtp_profile_id", profile_id)
        if not self._confirm_delete("SMTP", used_by):
            return
        db.delete_smtp_profile(profile_id)
        self._refresh_smtp()

    def _on_new_ssh(self):
        from ui.dialogs import SshProfileDialog
        dlg = SshProfileDialog(self)
        if dlg.exec():
            self._refresh_ssh()

    def _on_edit_ssh(self, profile_id: int):
        from database import db_manager as db
        from ui.dialogs import SshProfileDialog
        p = db.get_ssh_profile(profile_id)
        if p and SshProfileDialog(self, profile=p).exec():
            self._refresh_ssh()

    def _on_delete_ssh(self, profile_id: int):
        from database import db_manager as db
        used_by = db.find_pipelines_using_profile("edge_profile_id", profile_id)
        bastion_users = db.find_ssh_profiles_using_as_bastion(profile_id)
        if not self._confirm_delete("SSH", used_by, bastion_users=bastion_users):
            return
        db.delete_ssh_profile(profile_id)
        self._refresh_ssh()

    def _on_new_kerberos(self):
        from ui.dialogs import KerberosProfileDialog
        dlg = KerberosProfileDialog(self)
        if dlg.exec():
            self._refresh_kerberos()

    def _on_edit_kerberos(self, profile_id: int):
        from database import db_manager as db
        from ui.dialogs import KerberosProfileDialog
        p = db.get_kerberos_profile(profile_id)
        if p and KerberosProfileDialog(self, profile=p).exec():
            self._refresh_kerberos()

    def _on_delete_kerberos(self, profile_id: int):
        from database import db_manager as db
        used_by = db.find_pipelines_using_profile("kerberos_profile_id", profile_id)
        if not self._confirm_delete("Kerberos", used_by):
            return
        db.delete_kerberos_profile(profile_id)
        self._refresh_kerberos()

    def _on_new_elevation(self):
        from ui.dialogs import ElevationProfileDialog
        dlg = ElevationProfileDialog(self)
        if dlg.exec():
            self._refresh_elevation()

    def _on_edit_elevation(self, profile_id: int):
        from database import db_manager as db
        from ui.dialogs import ElevationProfileDialog
        p = db.get_elevation_profile(profile_id)
        if p and ElevationProfileDialog(self, profile=p).exec():
            self._refresh_elevation()

    def _on_delete_elevation(self, profile_id: int):
        from database import db_manager as db
        used_by = db.find_pipelines_using_profile("elevation_profile_id", profile_id)
        if not self._confirm_delete("d'élévation", used_by):
            return
        db.delete_elevation_profile(profile_id)
        self._refresh_elevation()

    def _confirm_delete(self, profile_kind: str, used_by: list,
                         bastion_users: list | None = None) -> bool:
        """Confirmation de suppression — avertit si des pipelines utilisent ce profil, et (pour
        un profil SSH) si d'autres profils SSH l'utilisent comme bastion."""
        lines = []
        if used_by:
            names = ", ".join(used_by)
            lines.append(f"utilisé par {len(used_by)} pipeline(s) : {names}")
        if bastion_users:
            names = ", ".join(bastion_users)
            lines.append(f"utilisé comme bastion par {len(bastion_users)} profil(s) SSH : {names}"
                          " (ils repasseront en connexion directe)")
        if lines:
            msg = (
                f"Ce profil {profile_kind} est " + " et ".join(lines) + ".\n\n"
                f"Le(s) supprimer quand même ? Ces pipelines échoueront à leur prochaine exécution."
            )
        else:
            msg = f"Supprimer ce profil {profile_kind} ?"
        reply = QMessageBox.question(self, "Supprimer", msg, QMessageBox.Yes | QMessageBox.No)
        return reply == QMessageBox.Yes

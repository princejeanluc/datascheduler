"""
DataScheduler — ui/main_window/connections_view.py
Vue Connexions : profils Oracle/FTP/SMTP/BDD génériques.
"""

from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton, QFrame,
    QTableWidget, QHeaderView, QAbstractItemView,
    QMessageBox, QTabWidget,
)
from PySide6.QtCore import QSize
from ui.styles import COLORS
from ui.components import make_page_header
from .widgets import (
    _icon, _action_btn, _configure_columns, _filter_table_rows, _make_search_input,
    _make_empty_label, _status_str, _type_icon_badge, _two_line_cell, _last_test_cell,
)

# Mêmes 6 colonnes pour les 6 tableaux (A3/A5/A6/A7, refonte lot A-Connexions) : icône de
# famille, Connexion (nom + type), Cible (hôte:port/principal/commande + utilisateur ou relation),
# Dernier test (badge + heure relative), Utilisée par, Actions. Seul le CONTENU différait avant
# (colonnes Nom/Type/Hôte/Port/Utilisateur séparées pour les bases, 4 colonnes seulement pour
# Kerberos/Élévation sans hôte/port) — la forme est désormais identique partout.
_TABLE_HEADERS = ["", "Connexion", "Cible", "Dernier test", "Utilisée par", ""]


class ConnectionsView(QWidget):
    def __init__(self):
        super().__init__()
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(24)

        self.inp_search = _make_search_input("Nom, hôte, utilisateur…")
        self.inp_search.textChanged.connect(self._on_search_changed)
        btn_health = QPushButton("  Bilan de santé"); btn_health.setObjectName("secondary")
        btn_health.setFixedHeight(36)
        btn_health.setIcon(_icon("fa5s.heartbeat", COLORS["text_main"]))
        btn_health.setIconSize(QSize(13, 13))
        btn_health.clicked.connect(self._on_health_check)

        header = make_page_header("", "Connexions", actions=[self.inp_search, btn_health])
        # make_page_header() ne renvoie pas de référence à son surtitre — recherché une fois ici
        # par objectName (même patron que les lots précédents), tenu à jour dans refresh() (A2 :
        # "N connexions · N en échec · N jamais testées").
        self._eyebrow_lbl = header.findChild(QLabel, "page_eyebrow")
        layout.addWidget(header)

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

        self.database_table = self._make_table(_TABLE_HEADERS, stretch_cols={1, 2})
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

        self.ftp_table = self._make_table(_TABLE_HEADERS, stretch_cols={1, 2})
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

        self.smtp_table = self._make_table(_TABLE_HEADERS, stretch_cols={1, 2})
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

        self.ssh_table = self._make_table(_TABLE_HEADERS, stretch_cols={1, 2})
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

        self.kerberos_table = self._make_table(_TABLE_HEADERS, stretch_cols={1, 2})
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

        self.elevation_table = self._make_table(_TABLE_HEADERS, stretch_cols={1, 2})
        vl.addWidget(self.elevation_table)
        self._elevation_empty = _make_empty_label(
            "Aucun profil d'élévation — cliquez sur « Nouveau profil d'élévation »."
        )
        self._elevation_empty.setVisible(False)
        vl.addWidget(self._elevation_empty)
        return card

    def _make_table(self, headers: list, stretch_cols: set) -> QTableWidget:
        """Layout uniforme à 6 colonnes (A3/A5/A6/A7) : icône(0)/Connexion(1)/Cible(2)/
        Dernier test(3)/Utilisée par(4)/Actions(5) — `headers` est toujours `_TABLE_HEADERS`,
        gardé en paramètre pour que la largeur de chaque colonne reste calculée par nom plutôt
        que par position en dur."""
        t = QTableWidget(0, len(headers))
        t.setHorizontalHeaderLabels(headers)
        t.verticalHeader().setVisible(False)
        t.setEditTriggers(QAbstractItemView.NoEditTriggers)
        t.setSelectionBehavior(QAbstractItemView.SelectRows)
        t.setShowGrid(False)
        _configure_columns(t, stretch_cols)

        # Icône de famille (toujours colonne 0) : pastille 30px + marges.
        t.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
        t.setColumnWidth(0, 46)
        if "Dernier test" in headers:
            idx = headers.index("Dernier test")
            t.horizontalHeader().setSectionResizeMode(idx, QHeaderView.Fixed)
            t.setColumnWidth(idx, 150)
        if "Utilisée par" in headers:
            idx = headers.index("Utilisée par")
            t.horizontalHeader().setSectionResizeMode(idx, QHeaderView.Fixed)
            t.setColumnWidth(idx, 110)
        # Actions (dernière colonne, en-tête vide) : largeur fixe pour les 2 boutons 26px
        # (ResizeToContents sur un en-tête vide se calcule trop juste et les rogne légèrement,
        # même piège déjà rencontré et corrigé pour cette colonne avant ce lot).
        last = len(headers) - 1
        t.horizontalHeader().setSectionResizeMode(last, QHeaderView.Fixed)
        t.setColumnWidth(last, 76)
        return t

    def _usage_label(self, used_by: list) -> QLabel:
        """Colonne « Utilisée par » (A6) — jamais la couleur seule, un nombre toujours lisible."""
        n = len(used_by)
        text = f"{n} pipeline{'s' if n != 1 else ''}" if n else "aucun pipeline"
        lbl = QLabel(text)
        lbl.setStyleSheet(
            f"font-size: 12.5px; color: {COLORS['text_main'] if n else COLORS['text_muted']}; "
            f"background: transparent; border: none;"
        )
        return lbl

    # ── Recherche ────────────────────────────────

    def _on_search_changed(self, text: str):
        # Colonnes 1 (Connexion) et 2 (Cible) systématiquement cherchables sur les 6 tableaux —
        # les autres colonnes sont des widgets de statut/comptage, sans sens pour une recherche
        # libre (A1 : "Nom, hôte, utilisateur…").
        for table in (
            self.database_table, self.ftp_table, self.smtp_table,
            self.ssh_table, self.kerberos_table, self.elevation_table,
        ):
            _filter_table_rows(table, text, columns=[1, 2])

    # ── Refresh ──────────────────────────────────

    def refresh(self):
        self._refresh_databases()
        self._refresh_ftp()
        self._refresh_smtp()
        self._refresh_ssh()
        self._refresh_kerberos()
        self._refresh_elevation()
        self._on_search_changed(self.inp_search.text())
        if self._eyebrow_lbl is not None:
            self._eyebrow_lbl.setText(self._compute_eyebrow_text())

    def _compute_eyebrow_text(self) -> str:
        """A2 : surtitre dynamique, compté sur les 7 listes déjà chargées par refresh() — aucune
        nouvelle fonction de données, juste un comptage côté vue sur last_test_success
        (False -> échec, None -> jamais testée)."""
        from database import db_manager as db

        successes = [p.get("last_test_success") for p in db.list_all_db_profiles()]
        for getter in (db.get_ftp_profiles, db.get_smtp_profiles, db.get_ssh_profiles,
                       db.get_kerberos_profiles, db.get_elevation_profiles):
            successes.extend(p.last_test_success for p in getter())

        n = len(successes)
        n_fail = sum(1 for s in successes if s is False)
        n_never = sum(1 for s in successes if s is None)
        return (
            f"{n} CONNEXION{'S' if n != 1 else ''} · {n_fail} EN ÉCHEC · "
            f"{n_never} JAMAIS TESTÉE{'S' if n_never != 1 else ''}"
        )

    def _refresh_databases(self):
        from database import db_manager as db
        from ui.dialogs import DB_TYPE_META
        profiles = db.list_all_db_profiles()
        self.database_table.setVisible(bool(profiles))
        self._database_empty.setVisible(not profiles)
        self.database_table.setRowCount(len(profiles))
        for r_idx, p in enumerate(profiles):
            type_label = DB_TYPE_META.get(p["db_type"], {}).get("label", p["db_type"])
            icon_key = "oracle" if p["db_type"] == "ORACLE" else "database"
            self.database_table.setCellWidget(r_idx, 0, _type_icon_badge(icon_key))
            self.database_table.setCellWidget(
                r_idx, 1, _two_line_cell(p["name"], COLORS["text_main"], type_label))
            self.database_table.setCellWidget(r_idx, 2, _two_line_cell(
                f"{p['host']}:{p['port']}", COLORS["text_main"], p["username"], mono_main=True))
            self.database_table.setCellWidget(
                r_idx, 3, _last_test_cell(p.get("last_test_success"), p.get("last_tested_at")))

            used_by = db.find_pipelines_using_db_profile(p["db_type"], p["id"])
            if p["db_type"] == "ORACLE":
                # Steps SQOOP_EXPORT/SQOOP_IMPORT référencent le profil Oracle sous la clé
                # "oracle_profile_id" (sans "db_type"), jamais vus par find_pipelines_using_db_profile
                # seul (correctif K1) — même union déjà appliquée par _on_delete_database, reprise
                # ici pour que le comptage affiché reste cohérent avec l'avertissement affiché à
                # la suppression.
                used_by = sorted(set(used_by) |
                                  set(db.find_pipelines_using_profile("oracle_profile_id", p["id"])))
            self.database_table.setCellWidget(r_idx, 4, self._usage_label(used_by))

            pid, dtype = p["id"], p["db_type"]
            w = QWidget(); hl = QHBoxLayout(w); hl.setContentsMargins(4, 4, 4, 4); hl.setSpacing(4)
            btn_edit = _action_btn("fa5s.pencil-alt", object_name="secondary", tooltip="Modifier")
            btn_del  = _action_btn("fa5s.trash-alt",  object_name="danger",    tooltip="Supprimer")
            btn_edit.clicked.connect(lambda _, i=pid, t=dtype: self._on_edit_database(i, t))
            btn_del.clicked.connect(lambda _, i=pid, t=dtype: self._on_delete_database(i, t))
            hl.addWidget(btn_edit); hl.addWidget(btn_del); hl.addStretch()
            self.database_table.setCellWidget(r_idx, 5, w)
            self.database_table.setRowHeight(r_idx, 46)

    def _refresh_ftp(self):
        from database import db_manager as db
        profiles = db.get_ftp_profiles()
        self.ftp_table.setVisible(bool(profiles))
        self._ftp_empty.setVisible(not profiles)
        self.ftp_table.setRowCount(len(profiles))
        for r_idx, p in enumerate(profiles):
            protocol = _status_str(p.protocol)
            self.ftp_table.setCellWidget(r_idx, 0, _type_icon_badge("ftp"))
            self.ftp_table.setCellWidget(
                r_idx, 1, _two_line_cell(p.name, COLORS["text_main"], protocol))
            self.ftp_table.setCellWidget(r_idx, 2, _two_line_cell(
                f"{p.host}:{p.port}", COLORS["text_main"], p.username, mono_main=True))
            self.ftp_table.setCellWidget(
                r_idx, 3, _last_test_cell(p.last_test_success, p.last_tested_at))
            used_by = db.find_pipelines_using_profile("ftp_profile_id", p.id)
            self.ftp_table.setCellWidget(r_idx, 4, self._usage_label(used_by))

            pid = p.id
            w = QWidget(); hl = QHBoxLayout(w); hl.setContentsMargins(4, 4, 4, 4); hl.setSpacing(4)
            btn_edit = _action_btn("fa5s.pencil-alt", object_name="secondary", tooltip="Modifier")
            btn_del  = _action_btn("fa5s.trash-alt",  object_name="danger",    tooltip="Supprimer")
            btn_edit.clicked.connect(lambda _, i=pid: self._on_edit_ftp(i))
            btn_del.clicked.connect(lambda _, i=pid: self._on_delete_ftp(i))
            hl.addWidget(btn_edit); hl.addWidget(btn_del); hl.addStretch()
            self.ftp_table.setCellWidget(r_idx, 5, w)
            self.ftp_table.setRowHeight(r_idx, 46)

    def _refresh_smtp(self):
        from database import db_manager as db
        profiles = db.get_smtp_profiles()
        self.smtp_table.setVisible(bool(profiles))
        self._smtp_empty.setVisible(not profiles)
        self.smtp_table.setRowCount(len(profiles))
        for r_idx, p in enumerate(profiles):
            security = "SMTP · STARTTLS" if p.use_tls else "SMTP · Aucune"
            self.smtp_table.setCellWidget(r_idx, 0, _type_icon_badge("smtp"))
            self.smtp_table.setCellWidget(
                r_idx, 1, _two_line_cell(p.name, COLORS["text_main"], security))
            self.smtp_table.setCellWidget(r_idx, 2, _two_line_cell(
                f"{p.host}:{p.port}", COLORS["text_main"], p.from_address, mono_main=True))
            self.smtp_table.setCellWidget(
                r_idx, 3, _last_test_cell(p.last_test_success, p.last_tested_at))
            used_by = db.find_pipelines_using_profile("smtp_profile_id", p.id)
            self.smtp_table.setCellWidget(r_idx, 4, self._usage_label(used_by))

            pid = p.id
            w = QWidget(); hl = QHBoxLayout(w); hl.setContentsMargins(4, 4, 4, 4); hl.setSpacing(4)
            btn_edit = _action_btn("fa5s.pencil-alt", object_name="secondary", tooltip="Modifier")
            btn_del  = _action_btn("fa5s.trash-alt",  object_name="danger",    tooltip="Supprimer")
            btn_edit.clicked.connect(lambda _, i=pid: self._on_edit_smtp(i))
            btn_del.clicked.connect(lambda _, i=pid: self._on_delete_smtp(i))
            hl.addWidget(btn_edit); hl.addWidget(btn_del); hl.addStretch()
            self.smtp_table.setCellWidget(r_idx, 5, w)
            self.smtp_table.setRowHeight(r_idx, 46)

    def _refresh_ssh(self):
        from database import db_manager as db
        profiles = db.get_ssh_profiles()
        name_by_id = {p.id: p.name for p in profiles}
        self.ssh_table.setVisible(bool(profiles))
        self._ssh_empty.setVisible(not profiles)
        self.ssh_table.setRowCount(len(profiles))
        for r_idx, p in enumerate(profiles):
            self.ssh_table.setCellWidget(r_idx, 0, _type_icon_badge("ssh"))
            self.ssh_table.setCellWidget(
                r_idx, 1, _two_line_cell(p.name, COLORS["text_main"], "SSH"))

            # A4 : la 2e ligne de la Cible montre la relation de bastion quand il y en a une
            # (jamais les deux à la fois sur la maquette — un profil qui passe par un bastion n'y
            # est en pratique pas lui-même utilisé comme bastion) ; sinon l'utilisateur, comme
            # avant.
            if p.jump_via_id and p.jump_via_id in name_by_id:
                sub_text, sub_color = f"via {name_by_id[p.jump_via_id]}", COLORS["relation"]
            else:
                bastion_of = [other.name for other in profiles if other.jump_via_id == p.id]
                if bastion_of:
                    sub_text = f"bastion de {', '.join(bastion_of)}"
                    sub_color = COLORS["relation"]
                else:
                    sub_text, sub_color = p.username, None
            self.ssh_table.setCellWidget(r_idx, 2, _two_line_cell(
                f"{p.host}:{p.port}", COLORS["text_main"], sub_text, sub_color, mono_main=True))

            self.ssh_table.setCellWidget(
                r_idx, 3, _last_test_cell(p.last_test_success, p.last_tested_at))
            used_by = db.find_pipelines_using_profile("edge_profile_id", p.id)
            self.ssh_table.setCellWidget(r_idx, 4, self._usage_label(used_by))

            pid = p.id
            w = QWidget(); hl = QHBoxLayout(w); hl.setContentsMargins(4, 4, 4, 4); hl.setSpacing(4)
            btn_edit = _action_btn("fa5s.pencil-alt", object_name="secondary", tooltip="Modifier")
            btn_del  = _action_btn("fa5s.trash-alt",  object_name="danger",    tooltip="Supprimer")
            btn_edit.clicked.connect(lambda _, i=pid: self._on_edit_ssh(i))
            btn_del.clicked.connect(lambda _, i=pid: self._on_delete_ssh(i))
            hl.addWidget(btn_edit); hl.addWidget(btn_del); hl.addStretch()
            self.ssh_table.setCellWidget(r_idx, 5, w)
            self.ssh_table.setRowHeight(r_idx, 46)

    def _refresh_kerberos(self):
        from database import db_manager as db
        profiles = db.get_kerberos_profiles()
        self.kerberos_table.setVisible(bool(profiles))
        self._kerberos_empty.setVisible(not profiles)
        self.kerberos_table.setRowCount(len(profiles))
        for r_idx, p in enumerate(profiles):
            self.kerberos_table.setCellWidget(r_idx, 0, _type_icon_badge("kerberos"))
            self.kerberos_table.setCellWidget(
                r_idx, 1, _two_line_cell(p.name, COLORS["text_main"], "Kerberos"))
            # Pas d'hôte/port/utilisateur pour ce type — une seule ligne de Cible (le principal).
            self.kerberos_table.setCellWidget(
                r_idx, 2, _two_line_cell(p.principal, COLORS["text_main"], mono_main=True))
            self.kerberos_table.setCellWidget(
                r_idx, 3, _last_test_cell(p.last_test_success, p.last_tested_at))
            used_by = db.find_pipelines_using_profile("kerberos_profile_id", p.id)
            self.kerberos_table.setCellWidget(r_idx, 4, self._usage_label(used_by))

            pid = p.id
            w = QWidget(); hl = QHBoxLayout(w); hl.setContentsMargins(4, 4, 4, 4); hl.setSpacing(4)
            btn_edit = _action_btn("fa5s.pencil-alt", object_name="secondary", tooltip="Modifier")
            btn_del  = _action_btn("fa5s.trash-alt",  object_name="danger",    tooltip="Supprimer")
            btn_edit.clicked.connect(lambda _, i=pid: self._on_edit_kerberos(i))
            btn_del.clicked.connect(lambda _, i=pid: self._on_delete_kerberos(i))
            hl.addWidget(btn_edit); hl.addWidget(btn_del); hl.addStretch()
            self.kerberos_table.setCellWidget(r_idx, 5, w)
            self.kerberos_table.setRowHeight(r_idx, 46)

    def _refresh_elevation(self):
        from database import db_manager as db
        profiles = db.get_elevation_profiles()
        self.elevation_table.setVisible(bool(profiles))
        self._elevation_empty.setVisible(not profiles)
        self.elevation_table.setRowCount(len(profiles))
        for r_idx, p in enumerate(profiles):
            self.elevation_table.setCellWidget(r_idx, 0, _type_icon_badge("elevation"))
            self.elevation_table.setCellWidget(
                r_idx, 1, _two_line_cell(p.name, COLORS["text_main"], "Élévation"))
            self.elevation_table.setCellWidget(r_idx, 2, _two_line_cell(
                f"sudo su {p.target_user}", COLORS["text_main"], mono_main=True))
            self.elevation_table.setCellWidget(
                r_idx, 3, _last_test_cell(p.last_test_success, p.last_tested_at))
            used_by = db.find_pipelines_using_profile("elevation_profile_id", p.id)
            self.elevation_table.setCellWidget(r_idx, 4, self._usage_label(used_by))

            pid = p.id
            w = QWidget(); hl = QHBoxLayout(w); hl.setContentsMargins(4, 4, 4, 4); hl.setSpacing(4)
            btn_edit = _action_btn("fa5s.pencil-alt", object_name="secondary", tooltip="Modifier")
            btn_del  = _action_btn("fa5s.trash-alt",  object_name="danger",    tooltip="Supprimer")
            btn_edit.clicked.connect(lambda _, i=pid: self._on_edit_elevation(i))
            btn_del.clicked.connect(lambda _, i=pid: self._on_delete_elevation(i))
            hl.addWidget(btn_edit); hl.addWidget(btn_del); hl.addStretch()
            self.elevation_table.setCellWidget(r_idx, 5, w)
            self.elevation_table.setRowHeight(r_idx, 46)

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
        if db_type == "ORACLE":
            # Les steps SQOOP_EXPORT/SQOOP_IMPORT référencent le profil Oracle sous la clé
            # "oracle_profile_id" (sans "db_type"), jamais détectés par
            # find_pipelines_using_db_profile ci-dessus — sans cette union, supprimer un profil
            # Oracle utilisé uniquement par des steps Sqoop ne prévenait jamais l'utilisateur
            # (correctif K1, docs/refonte/LOTS.md).
            used_by = sorted(set(used_by) | set(db.find_pipelines_using_profile("oracle_profile_id", profile_id)))
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

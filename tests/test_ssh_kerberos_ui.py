"""
DataScheduler — tests/test_ssh_kerberos_ui.py
Vérifie l'intégration UI des profils SSH/Kerberos (étape SPARK_SQL, chantier D.1) : dialogues de
profil (offscreen Qt), panneaux de ConnectionsView, câblage avec ConnectionHealthDialog —
notamment le fait qu'un test Kerberos en bulk ne s'enregistre jamais comme un échec réel
(distinction None vs False à travers le signal Qt _HealthCheckThread.row_tested).
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from database import crypto, db_manager as db


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


# ──────────────────────────────────────────────
#  SshProfileDialog
# ──────────────────────────────────────────────

def test_ssh_profile_dialog_creates_profile(qapp, test_db):
    from ui.dialogs import SshProfileDialog

    dlg = SshProfileDialog(None)
    dlg.inp_name.setText("EDGE01")
    dlg.inp_host.setText("edge01.cluster.local")
    dlg.inp_user.setText("jdupont")
    dlg.inp_pass.setText("secret")
    dlg._on_save()

    profiles = db.get_ssh_profiles()
    assert len(profiles) == 1
    assert profiles[0].host == "edge01.cluster.local"
    assert crypto.decrypt(profiles[0].password) == "secret"


def test_ssh_profile_dialog_edit_blank_password_keeps_existing(qapp, test_db):
    from ui.dialogs import SshProfileDialog

    p = db.create_ssh_profile(name="EDGE01", host="edge01", port=22, username="u", password="orig")
    dlg = SshProfileDialog(None, profile=p)
    assert dlg.inp_pass.text() == ""   # jamais réaffiché en clair

    dlg.inp_host.setText("edge02")
    dlg._on_save()

    reloaded = db.get_ssh_profile(p.id)
    assert reloaded.host == "edge02"
    assert crypto.decrypt(reloaded.password) == "orig"


def test_ssh_profile_dialog_requires_fields(qapp, test_db):
    from ui.dialogs import SshProfileDialog

    dlg = SshProfileDialog(None)
    assert dlg._validate() is False   # tous les champs vides


# ──────────────────────────────────────────────
#  SshProfileDialog — chaînage bastion (chantier M)
# ──────────────────────────────────────────────

def test_ssh_profile_dialog_bastion_combo_excludes_self_when_editing(qapp, test_db):
    from ui.dialogs import SshProfileDialog

    edge01 = db.create_ssh_profile(name="EDGE01", host="edge01", port=22, username="u", password="pw")
    edge03 = db.create_ssh_profile(name="EDGE03", host="edge03", port=22, username="u", password="pw")

    dlg = SshProfileDialog(None, profile=edge03)
    names = [dlg.cb_bastion.itemText(i) for i in range(dlg.cb_bastion.count())]
    assert "EDGE01" in names
    assert "EDGE03" not in names   # ne peut pas être son propre bastion


def test_ssh_profile_dialog_saves_and_prefills_jump_via(qapp, test_db):
    from ui.dialogs import SshProfileDialog

    edge01 = db.create_ssh_profile(name="EDGE01", host="edge01", port=22, username="u", password="pw")

    dlg = SshProfileDialog(None)
    dlg.inp_name.setText("EDGE03")
    dlg.inp_host.setText("edge03")
    dlg.inp_user.setText("jdupont")
    dlg.inp_pass.setText("secret")
    idx = dlg.cb_bastion.findData(edge01.id)
    dlg.cb_bastion.setCurrentIndex(idx)
    dlg._on_save()

    edge03 = db.get_ssh_profiles()[-1]
    assert edge03.jump_via_id == edge01.id

    dlg2 = SshProfileDialog(None, profile=edge03)
    assert dlg2.cb_bastion.currentData() == edge01.id


def test_ssh_profile_dialog_build_config_resolves_bastion_chain(qapp, test_db):
    from ui.dialogs import SshProfileDialog

    edge01 = db.create_ssh_profile(name="EDGE01", host="edge01", port=22, username="u", password="pw")

    dlg = SshProfileDialog(None)
    dlg.inp_host.setText("edge03")
    dlg.inp_user.setText("jdupont")
    dlg.inp_pass.setText("secret")
    idx = dlg.cb_bastion.findData(edge01.id)
    dlg.cb_bastion.setCurrentIndex(idx)

    config = dlg._build_config()
    assert config.jump_via is not None
    assert config.jump_via.host == "edge01"


def test_ssh_profile_dialog_rejects_cycle_and_shows_error(qapp, test_db):
    from ui.dialogs import SshProfileDialog

    edge01 = db.create_ssh_profile(name="EDGE01", host="edge01", port=22, username="u", password="pw")
    edge03 = db.create_ssh_profile(name="EDGE03", host="edge03", port=22, username="u", password="pw",
                                    jump_via_id=edge01.id)

    dlg = SshProfileDialog(None, profile=edge01)
    idx = dlg.cb_bastion.findData(edge03.id)
    dlg.cb_bastion.setCurrentIndex(idx)
    dlg._on_save()   # EDGE01 -> EDGE03 -> EDGE01 : doit être rejeté, pas planter

    assert db.get_ssh_profile(edge01.id).jump_via_id is None
    assert "boucle" in dlg.lbl_test_result.text()


# ──────────────────────────────────────────────
#  KerberosProfileDialog
# ──────────────────────────────────────────────

def test_kerberos_profile_dialog_creates_profile(qapp, test_db):
    from ui.dialogs import KerberosProfileDialog

    dlg = KerberosProfileDialog(None)
    dlg.inp_name.setText("KRB1")
    dlg.inp_principal.setText("jdupont@REALM.EXAMPLE")
    dlg.inp_pass.setText("secret")
    dlg._on_save()

    profiles = db.get_kerberos_profiles()
    assert len(profiles) == 1
    assert profiles[0].principal == "jdupont@REALM.EXAMPLE"
    assert crypto.decrypt(profiles[0].password) == "secret"


def test_kerberos_profile_dialog_lists_ssh_profiles_for_testing(qapp, test_db):
    from ui.dialogs import KerberosProfileDialog

    db.create_ssh_profile(name="EDGE01", host="edge01", port=22, username="u", password="p")
    dlg = KerberosProfileDialog(None)
    assert dlg.cb_ssh_profile.findText("EDGE01") >= 0


def test_kerberos_profile_dialog_test_without_ssh_profile_shows_warning(qapp, test_db):
    from ui.dialogs import KerberosProfileDialog

    dlg = KerberosProfileDialog(None)
    dlg.inp_principal.setText("a@REALM")
    dlg.inp_pass.setText("pw")
    dlg._on_test()   # aucun profil SSH sélectionné dans le combo
    assert "profil SSH" in dlg.lbl_test_result.text()
    assert dlg._test_thread is None


# ──────────────────────────────────────────────
#  ConnectionsView — panneaux SSH/Kerberos
# ──────────────────────────────────────────────

def test_connections_view_shows_ssh_and_kerberos_rows(qapp, test_db):
    from ui.main_window.connections_view import ConnectionsView

    db.create_ssh_profile(name="EDGE01", host="edge01", port=22, username="u", password="p")
    db.create_kerberos_profile(name="KRB1", principal="a@REALM", password="p")

    view = ConnectionsView()
    assert view.ssh_table.rowCount() == 1
    assert view.kerberos_table.rowCount() == 1
    assert view.ssh_table.item(0, 0).text() == "EDGE01"
    assert view.kerberos_table.item(0, 1).text() == "a@REALM"


def test_connections_view_delete_ssh_checks_pipeline_usage(qapp, test_db, monkeypatch):
    from ui.main_window import connections_view as cv_module

    p = db.create_ssh_profile(name="EDGE01", host="edge01", port=22, username="u", password="p")
    monkeypatch.setattr(cv_module.QMessageBox, "question",
                         lambda *a, **kw: cv_module.QMessageBox.No)

    view = cv_module.ConnectionsView()
    view._on_delete_ssh(p.id)   # répond "No" -> pas supprimé
    assert db.get_ssh_profile(p.id) is not None


def test_connections_view_ssh_via_column_shows_bastion_name_or_dash(qapp, test_db):
    from ui.main_window.connections_view import ConnectionsView

    edge01 = db.create_ssh_profile(name="EDGE01", host="edge01", port=22, username="u", password="p")
    db.create_ssh_profile(name="EDGE03", host="edge03", port=22, username="u", password="p",
                           jump_via_id=edge01.id)

    view = ConnectionsView()
    rows = {view.ssh_table.item(r, 0).text(): view.ssh_table.item(r, 4).text()
            for r in range(view.ssh_table.rowCount())}
    assert rows["EDGE01"] == "—"
    assert rows["EDGE03"] == "EDGE01"


def test_connections_view_delete_ssh_warns_when_used_as_bastion(qapp, test_db, monkeypatch):
    from ui.main_window import connections_view as cv_module

    edge01 = db.create_ssh_profile(name="EDGE01", host="edge01", port=22, username="u", password="p")
    db.create_ssh_profile(name="EDGE03", host="edge03", port=22, username="u", password="p",
                           jump_via_id=edge01.id)

    captured = {}
    def _fake_question(self_, title, msg, *a, **kw):
        captured["msg"] = msg
        return cv_module.QMessageBox.No
    monkeypatch.setattr(cv_module.QMessageBox, "question", _fake_question)

    view = cv_module.ConnectionsView()
    view._on_delete_ssh(edge01.id)
    assert "EDGE03" in captured["msg"]
    assert "bastion" in captured["msg"]


# ──────────────────────────────────────────────
#  ConnectionHealthDialog — câblage des 2 nouvelles catégories
# ──────────────────────────────────────────────

def test_health_dialog_collects_ssh_and_kerberos_profiles(qapp, test_db):
    from ui.dialogs import ConnectionHealthDialog

    db.create_ssh_profile(name="EDGE01", host="edge01", port=22, username="u", password="p")
    db.create_kerberos_profile(name="KRB1", principal="a@REALM", password="p")

    dlg = ConnectionHealthDialog(None)
    categories = {r["category"] for r in dlg._rows}
    assert "ssh" in categories
    assert "kerberos" in categories


def test_health_dialog_kerberos_bulk_test_does_not_record_a_result(qapp, test_db):
    """Un test Kerberos en bulk ne doit jamais s'enregistrer comme un échec réel — voir
    _test_one()/_HealthCheckThread : None (pas False) doit traverser le signal Qt intact."""
    from ui.dialogs.connection_health_dialog import _test_one

    p = db.create_kerberos_profile(name="KRB1", principal="a@REALM", password="p")
    success, message = _test_one("kerberos", p.id, None)
    assert success is None
    assert "profil SSH" in message

    # Confirme qu'aucun enregistrement n'a eu lieu (last_test_success toujours None).
    assert db.get_kerberos_profile(p.id).last_test_success is None


def test_health_dialog_on_row_tested_preserves_state_for_none_success(qapp, test_db):
    from ui.dialogs import ConnectionHealthDialog

    p = db.create_kerberos_profile(name="KRB1", principal="a@REALM", password="p")
    dlg = ConnectionHealthDialog(None)
    row_idx = next(i for i, r in enumerate(dlg._rows) if r["id"] == p.id)

    dlg._on_row_tested(row_idx, None, "Test uniquement disponible depuis le profil Kerberos.")
    status_item = dlg.table.item(row_idx, 3)
    assert status_item.text() == "—"   # jamais testé, statut inchangé (pas un échec affiché)
    assert status_item.toolTip() == "Test uniquement disponible depuis le profil Kerberos."

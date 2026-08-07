"""
DataScheduler — tests/test_email_notify_size_guard.py
Vérifie le garde-fou de taille sur la pièce jointe de EMAIL_NOTIFY (max_attachment_mb /
on_oversized) : envoi non concerné par défaut (pas de limite), échec propre au-delà de la
limite (comportement par défaut "fail"), envoi sans pièce jointe si "skip".
"""

from core.steps.email_notify import EmailNotifyStep
from core.steps.base import StepContext
import core.email as email_module
from core.email import SendResult
from database import db_manager as db


def _smtp_profile():
    return db.create_smtp_profile(name="SMTP1", host="h", port=587, from_address="ds@test.com")


def test_no_limit_by_default_sends_regardless_of_size(test_db, monkeypatch, tmp_path):
    smtp = _smtp_profile()
    big = tmp_path / "gros.csv"
    big.write_bytes(b"x" * 1024)   # petit fichier, mais aucune limite n'est configurée

    captured = {}
    def fake_send(self, to, subject, body, attachment=None):
        captured["attachment"] = attachment
        return SendResult(success=True)
    monkeypatch.setattr(email_module.EmailSender, "send", fake_send)

    ctx = StepContext(); ctx.output_file = big
    step = EmailNotifyStep({
        "smtp_profile_id": smtp.id, "to": "a@b.com", "subject_tpl": "s", "body_tpl": "b",
        "attach_output_file": True,
    })
    result = step.run(ctx)

    assert result.success, result.error
    assert captured["attachment"] == big


def test_oversized_attachment_fails_the_step_by_default(test_db, monkeypatch, tmp_path):
    smtp = _smtp_profile()
    big = tmp_path / "gros.csv"
    big.write_bytes(b"x" * (2 * 1024 * 1024))   # 2 Mo

    monkeypatch.setattr(
        email_module.EmailSender, "send",
        lambda self, to, subject, body, attachment=None: SendResult(success=True),
    )

    ctx = StepContext(); ctx.output_file = big
    step = EmailNotifyStep({
        "smtp_profile_id": smtp.id, "to": "a@b.com", "subject_tpl": "s", "body_tpl": "b",
        "attach_output_file": True, "max_attachment_mb": 1,
    })
    result = step.run(ctx)

    assert not result.success
    assert "trop volumineuse" in result.error


def test_oversized_attachment_skipped_sends_without_it_when_configured(test_db, monkeypatch, tmp_path):
    smtp = _smtp_profile()
    big = tmp_path / "gros.csv"
    big.write_bytes(b"x" * (2 * 1024 * 1024))   # 2 Mo

    captured = {}
    def fake_send(self, to, subject, body, attachment=None):
        captured["attachment"] = attachment
        return SendResult(success=True)
    monkeypatch.setattr(email_module.EmailSender, "send", fake_send)

    ctx = StepContext(); ctx.output_file = big
    step = EmailNotifyStep({
        "smtp_profile_id": smtp.id, "to": "a@b.com", "subject_tpl": "s", "body_tpl": "b",
        "attach_output_file": True, "max_attachment_mb": 1, "on_oversized": "skip",
    })
    result = step.run(ctx)

    assert result.success, result.error
    assert captured["attachment"] is None


def test_attachment_within_limit_is_sent_normally(test_db, monkeypatch, tmp_path):
    smtp = _smtp_profile()
    small = tmp_path / "petit.csv"
    small.write_bytes(b"x" * 1024)   # 1 Ko, largement sous la limite

    captured = {}
    def fake_send(self, to, subject, body, attachment=None):
        captured["attachment"] = attachment
        return SendResult(success=True)
    monkeypatch.setattr(email_module.EmailSender, "send", fake_send)

    ctx = StepContext(); ctx.output_file = small
    step = EmailNotifyStep({
        "smtp_profile_id": smtp.id, "to": "a@b.com", "subject_tpl": "s", "body_tpl": "b",
        "attach_output_file": True, "max_attachment_mb": 5,
    })
    result = step.run(ctx)

    assert result.success, result.error
    assert captured["attachment"] == small

"""
DataScheduler — tests/test_notification_digest.py
Vérifie NotificationSettings (get-or-create/update) et le digest manager (chantier UX
post-personas, persona "Sophie" — être prévenue sans avoir à ouvrir l'application).
"""

from database import db_manager as db
from core.scheduler import PipelineScheduler
import core.email as email_module
from core.email import SendResult


def test_get_notification_settings_creates_default_row(test_db):
    settings = db.get_notification_settings()
    assert settings.id == 1
    assert settings.digest_enabled is False
    assert settings.digest_frequency == "DAILY"


def test_get_notification_settings_is_idempotent(test_db):
    s1 = db.get_notification_settings()
    s2 = db.get_notification_settings()
    assert s1.id == s2.id == 1


def test_update_notification_settings_persists(test_db):
    db.update_notification_settings(
        digest_enabled=True, digest_recipients="a@b.com,c@d.com", digest_frequency="WEEKLY",
    )
    reloaded = db.get_notification_settings()
    assert reloaded.digest_enabled is True
    assert reloaded.digest_recipients == "a@b.com,c@d.com"
    assert reloaded.digest_frequency == "WEEKLY"


def test_refresh_digest_job_registers_nothing_when_disabled(test_db):
    sched = PipelineScheduler()
    sched.refresh_digest_job()
    assert sched._scheduler.get_job(sched.DIGEST_JOB_ID) is None


def test_refresh_digest_job_registers_when_enabled(test_db):
    db.update_notification_settings(digest_enabled=True)
    sched = PipelineScheduler()
    sched.refresh_digest_job()
    assert sched._scheduler.get_job(sched.DIGEST_JOB_ID) is not None


def test_refresh_digest_job_removes_when_disabled_again(test_db):
    db.update_notification_settings(digest_enabled=True)
    sched = PipelineScheduler()
    sched.refresh_digest_job()
    assert sched._scheduler.get_job(sched.DIGEST_JOB_ID) is not None

    db.update_notification_settings(digest_enabled=False)
    sched.refresh_digest_job()
    assert sched._scheduler.get_job(sched.DIGEST_JOB_ID) is None


def test_run_digest_skips_cleanly_without_smtp_or_recipients(test_db):
    db.update_notification_settings(digest_enabled=True)
    sched = PipelineScheduler()
    sched._run_digest()   # ne doit pas lever, juste logguer un avertissement


def test_run_digest_sends_summary_and_updates_last_sent(test_db, monkeypatch):
    smtp = db.create_smtp_profile(name="SMTP1", host="h", port=587, from_address="ds@test.com")
    pipeline = db.create_pipeline(name="digest-pipeline")
    run = db.create_run(pipeline.id)
    db.finish_run(run.id, status="FAILED", error_message="Connexion refusée")

    db.update_notification_settings(
        digest_enabled=True, digest_smtp_profile_id=smtp.id, digest_recipients="a@b.com, c@d.com",
    )

    captured = {}
    def fake_send(self, to, subject, body, attachment=None):
        captured["to"] = to
        captured["subject"] = subject
        captured["body"] = body
        return SendResult(success=True)
    monkeypatch.setattr(email_module.EmailSender, "send", fake_send)

    sched = PipelineScheduler()
    sched._run_digest()

    assert captured["to"] == ["a@b.com", "c@d.com"]
    assert "Échecs : 1" in captured["body"]
    assert "digest-pipeline" in captured["body"]
    assert "Connexion refusée" in captured["body"]

    assert db.get_notification_settings().digest_last_sent_at is not None


def test_run_digest_does_not_resend_when_no_new_runs(test_db, monkeypatch):
    smtp = db.create_smtp_profile(name="SMTP1", host="h", port=587, from_address="ds@test.com")
    db.update_notification_settings(
        digest_enabled=True, digest_smtp_profile_id=smtp.id, digest_recipients="a@b.com",
    )

    calls = []
    monkeypatch.setattr(
        email_module.EmailSender, "send",
        lambda self, to, subject, body, attachment=None: calls.append(1) or SendResult(success=True),
    )

    sched = PipelineScheduler()
    sched._run_digest()   # aucun run -> ne doit pas envoyer d'email
    assert calls == []

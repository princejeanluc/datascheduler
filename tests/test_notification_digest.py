"""
DataScheduler — tests/test_notification_digest.py
Vérifie NotificationSettings (get-or-create/update) et le digest manager (chantier UX
post-personas, persona "Sophie" — être prévenue sans avoir à ouvrir l'application).
"""

from sqlalchemy import create_engine, text

from database import db_manager as db
from core.scheduler import PipelineScheduler
import core.email as email_module
from core.email import SendResult


def test_migrate_adds_digest_time_columns_on_legacy_db(tmp_path):
    """notification_settings existait avant l'ajout de digest_time/digest_day_of_week
    (heure/jour du digest auparavant figés en dur à 07:00/lundi) — la migration doit les
    ajouter de façon idempotente sur une base déjà en place, sans perdre les valeurs existantes."""
    db_path = tmp_path / "legacy_notif.db"
    engine = create_engine(f"sqlite:///{db_path}")

    with engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE notification_settings (
                id                     INTEGER PRIMARY KEY,
                digest_enabled         BOOLEAN NOT NULL DEFAULT 0,
                digest_smtp_profile_id INTEGER,
                digest_recipients      TEXT,
                digest_frequency       VARCHAR(10) NOT NULL DEFAULT 'DAILY',
                digest_last_sent_at    DATETIME
            )
        """))
        conn.execute(text(
            "INSERT INTO notification_settings (id, digest_enabled, digest_recipients, digest_frequency) "
            "VALUES (1, 1, 'legacy@test.com', 'WEEKLY')"
        ))
        conn.commit()
    engine.dispose()

    db.init_db(db_path)
    cols = {r[1] for r in create_engine(f"sqlite:///{db_path}").connect()
            .execute(text("PRAGMA table_info(notification_settings)")).fetchall()}
    assert "digest_time" in cols
    assert "digest_day_of_week" in cols

    settings = db.get_notification_settings()
    assert settings.digest_recipients == "legacy@test.com"   # valeurs existantes préservées
    assert settings.digest_time == "07:00"                    # défaut appliqué rétroactivement
    assert settings.digest_day_of_week == 0

    db.init_db(db_path)   # idempotence : un second démarrage ne doit pas planter
    db._engine = None
    db._SessionFactory = None


def test_get_notification_settings_creates_default_row(test_db):
    settings = db.get_notification_settings()
    assert settings.id == 1
    assert settings.digest_enabled is False
    assert settings.digest_frequency == "DAILY"
    assert settings.digest_time == "07:00"
    assert settings.digest_day_of_week == 0


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


def test_refresh_digest_job_uses_configured_daily_time(test_db):
    """Autrefois figé en dur à 07:00 (core/scheduler.py) — la fréquence/l'heure du digest
    doivent maintenant refléter les paramètres enregistrés."""
    db.update_notification_settings(digest_enabled=True, digest_frequency="DAILY", digest_time="18:45")
    sched = PipelineScheduler()
    sched.refresh_digest_job()
    job = sched._scheduler.get_job(sched.DIGEST_JOB_ID)
    trigger_str = str(job.trigger)
    assert "hour='18'" in trigger_str
    assert "minute='45'" in trigger_str


def test_refresh_digest_job_uses_configured_weekly_day_and_time(test_db):
    """Autrefois toujours lundi (day_of_week=0) — doit maintenant refléter digest_day_of_week."""
    db.update_notification_settings(
        digest_enabled=True, digest_frequency="WEEKLY", digest_time="09:15", digest_day_of_week=4,
    )
    sched = PipelineScheduler()
    sched.refresh_digest_job()
    job = sched._scheduler.get_job(sched.DIGEST_JOB_ID)
    trigger_str = str(job.trigger)
    assert "day_of_week='4'" in trigger_str
    assert "hour='9'" in trigger_str
    assert "minute='15'" in trigger_str


def test_refresh_digest_job_falls_back_to_default_time_on_empty_value(test_db):
    """digest_time vide (ex: valeur legacy) -> repli 07:00, pas de crash."""
    db.update_notification_settings(digest_enabled=True, digest_frequency="DAILY", digest_time="")
    sched = PipelineScheduler()
    sched.refresh_digest_job()
    job = sched._scheduler.get_job(sched.DIGEST_JOB_ID)
    trigger_str = str(job.trigger)
    assert "hour='7'" in trigger_str
    assert "minute='0'" in trigger_str


def test_refresh_digest_job_falls_back_to_default_time_on_malformed_value(test_db):
    """digest_time malformé (pas de ':') -> repli 07:00, pas de crash."""
    db.update_notification_settings(digest_enabled=True, digest_frequency="DAILY", digest_time="not-a-time")
    sched = PipelineScheduler()
    sched.refresh_digest_job()
    job = sched._scheduler.get_job(sched.DIGEST_JOB_ID)
    trigger_str = str(job.trigger)
    assert "hour='7'" in trigger_str
    assert "minute='0'" in trigger_str


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

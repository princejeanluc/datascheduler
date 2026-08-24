"""
DataScheduler — tests/test_task_scheduler.py
Chantier exécution en arrière-plan : core/task_scheduler.py invoque schtasks.exe en sous-process
— frontière OS réelle (vérifiée manuellement à l'exe, voir le plan du chantier), mais ce module
ne doit lui-même jamais lever, quel que soit l'aboutissement du sous-processus (succès, échec,
absence même de l'exécutable). Sous-process systématiquement mocké ici — pas de vrai schtasks
en test. La tâche est enregistrée via une définition XML (`/xml`, pas `/tr`+`/sc`) depuis l'ajout
du watchdog périodique — deux déclencheurs (connexion + répétition) ne tiennent pas dans un seul
`schtasks /create /sc ...` classique.
"""

import os
import subprocess
import sys

from core import task_scheduler


def test_register_logon_task_returns_true_on_success(monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: None)
    assert task_scheduler.register_logon_task() is True


def test_register_logon_task_returns_false_and_never_raises_on_failure(monkeypatch):
    def _raise(*a, **k):
        raise subprocess.CalledProcessError(1, "schtasks")
    monkeypatch.setattr(subprocess, "run", _raise)
    assert task_scheduler.register_logon_task() is False


def test_register_logon_task_returns_false_when_schtasks_missing(monkeypatch):
    def _raise(*a, **k):
        raise FileNotFoundError("schtasks introuvable")
    monkeypatch.setattr(subprocess, "run", _raise)
    assert task_scheduler.register_logon_task() is False


def test_unregister_logon_task_returns_true_on_success(monkeypatch):
    class _Result:
        returncode = 0
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _Result())
    assert task_scheduler.unregister_logon_task() is True


def test_unregister_logon_task_is_a_silent_noop_when_task_absent(monkeypatch):
    """La tâche n'existe déjà plus (bascule répétée) — schtasks /delete rendra un code non nul,
    mais ça ne doit pas être traité comme un échec puisqu'on ne lève pas non plus."""
    class _Result:
        returncode = 1
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _Result())
    assert task_scheduler.unregister_logon_task() is True


def test_unregister_logon_task_never_raises_on_subprocess_failure(monkeypatch):
    def _raise(*a, **k):
        raise OSError("échec inattendu")
    monkeypatch.setattr(subprocess, "run", _raise)
    assert task_scheduler.unregister_logon_task() is False


def test_register_logon_task_logs_real_schtasks_stderr_on_failure(monkeypatch, caplog):
    """str(CalledProcessError) seul ("returned non-zero exit status 1") ne dit jamais pourquoi —
    le vrai message de schtasks.exe (stderr) doit apparaître dans le log, pas être avalé."""
    def _raise(*a, **k):
        raise subprocess.CalledProcessError(
            1, "schtasks", output="", stderr="ERREUR : Accès refusé.\n"
        )
    monkeypatch.setattr(subprocess, "run", _raise)

    with caplog.at_level("ERROR"):
        assert task_scheduler.register_logon_task() is False

    assert "Accès refusé" in caplog.text


def _capture_xml(monkeypatch):
    """Intercepte le fichier XML temporaire passé via /xml AVANT qu'il ne soit supprimé (le code
    le nettoie dans un `finally` juste après l'appel à subprocess.run)."""
    captured = {}

    def _fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        xml_path = cmd[cmd.index("/xml") + 1]
        captured["xml_path"] = xml_path
        with open(xml_path, encoding="utf-16") as f:
            captured["xml"] = f.read()
    monkeypatch.setattr(subprocess, "run", _fake_run)
    return captured


def test_register_logon_task_command_uses_xml_with_absolute_paths(monkeypatch, tmp_path):
    """sys.argv[0] peut être relatif ("main.py") au lancement depuis les sources — le
    Planificateur de tâches n'hérite pas forcément du même répertoire de travail au
    déclenchement, donc la commande enregistrée doit toujours porter des chemins absolus."""
    captured = _capture_xml(monkeypatch)
    monkeypatch.setattr(sys, "argv", ["main.py"])
    monkeypatch.chdir(tmp_path)

    task_scheduler.register_logon_task()

    assert os.path.abspath("main.py") in captured["xml"]
    assert '"main.py"' not in captured["xml"]


def test_register_logon_task_xml_includes_worker_flag_and_no_elevation(monkeypatch):
    captured = _capture_xml(monkeypatch)

    task_scheduler.register_logon_task()

    assert "schtasks" in captured["cmd"][0]
    assert "--worker" in captured["xml"]
    assert "<RunLevel>LeastPrivilege</RunLevel>" in captured["xml"]
    assert "<LogonType>InteractiveToken</LogonType>" in captured["xml"]


def test_register_logon_task_xml_has_logon_and_watchdog_triggers(monkeypatch):
    """Deux déclencheurs sur la même tâche : connexion (démarrage immédiat) + répétition
    périodique (watchdog, relance si le worker a planté ou n'a jamais démarré). La politique
    IgnoreNew garantit qu'une instance déjà active n'est jamais dupliquée par le watchdog."""
    captured = _capture_xml(monkeypatch)

    task_scheduler.register_logon_task()

    xml = captured["xml"]
    assert "<LogonTrigger>" in xml
    assert "<TimeTrigger>" in xml
    assert f"<Interval>PT{task_scheduler.WATCHDOG_INTERVAL_MINUTES}M</Interval>" in xml
    assert "<MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>" in xml


def test_register_logon_task_xml_has_no_execution_time_limit(monkeypatch):
    """La limite PAR DÉFAUT d'une tâche XML est PT72H (3 jours) — sans PT0S explicite, Windows
    tuerait silencieusement le worker au bout de 3 jours d'activité continue."""
    captured = _capture_xml(monkeypatch)

    task_scheduler.register_logon_task()

    assert "<ExecutionTimeLimit>PT0S</ExecutionTimeLimit>" in captured["xml"]


def test_register_logon_task_cleans_up_temp_xml_file(monkeypatch):
    captured = _capture_xml(monkeypatch)

    task_scheduler.register_logon_task()

    assert not os.path.exists(captured["xml_path"])


def test_register_logon_task_cleans_up_temp_xml_file_even_on_failure(monkeypatch):
    captured = {}

    def _raise(cmd, **kwargs):
        captured["xml_path"] = cmd[cmd.index("/xml") + 1]
        raise subprocess.CalledProcessError(1, "schtasks", stderr="échec")
    monkeypatch.setattr(subprocess, "run", _raise)

    assert task_scheduler.register_logon_task() is False
    assert not os.path.exists(captured["xml_path"])

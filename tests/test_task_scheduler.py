"""
DataScheduler — tests/test_task_scheduler.py
Chantier exécution en arrière-plan : core/task_scheduler.py invoque schtasks.exe en sous-process
— frontière OS réelle (vérifiée manuellement à l'exe, voir le plan du chantier), mais ce module
ne doit lui-même jamais lever, quel que soit l'aboutissement du sous-processus (succès, échec,
absence même de l'exécutable). Sous-process systématiquement mocké ici — pas de vrai schtasks
en test.
"""

import subprocess

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


def test_register_logon_task_command_line_uses_absolute_paths(monkeypatch, tmp_path):
    """sys.argv[0] peut être relatif ("main.py") au lancement depuis les sources — le
    Planificateur de tâches n'hérite pas forcément du même répertoire de travail au
    déclenchement, donc la commande enregistrée doit toujours porter des chemins absolus."""
    import os
    import sys

    captured = {}

    def _fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
    monkeypatch.setattr(subprocess, "run", _fake_run)
    monkeypatch.setattr(sys, "argv", ["main.py"])
    monkeypatch.chdir(tmp_path)

    task_scheduler.register_logon_task()

    tr_index = captured["cmd"].index("/tr")
    tr_value = captured["cmd"][tr_index + 1]
    assert os.path.abspath("main.py") in tr_value
    assert '"main.py"' not in tr_value


def test_register_logon_task_command_line_includes_worker_flag(monkeypatch):
    captured = {}

    def _fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
    monkeypatch.setattr(subprocess, "run", _fake_run)

    task_scheduler.register_logon_task()

    assert "schtasks" in captured["cmd"][0]
    tr_index = captured["cmd"].index("/tr")
    assert "--worker" in captured["cmd"][tr_index + 1]
    assert "/rl" in captured["cmd"]
    rl_index = captured["cmd"].index("/rl")
    assert captured["cmd"][rl_index + 1] == "limited"

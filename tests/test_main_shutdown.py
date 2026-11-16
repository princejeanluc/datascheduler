"""
DataScheduler — tests/test_main_shutdown.py
Vérifie que main()::scheduler.stop() s'exécute bien à la fermeture de l'UI. ui.main_window.run()
se termine par sys.exit(app.exec()), qui lève SystemExit — sans try/finally autour de l'appel,
l'arrêt du scheduler situé juste après n'était jamais atteint (bug découvert pendant la note
d'impact du lot D2-D4, corrigé séparément ici). Toutes les dépendances lourdes (DB réelle,
scheduler réel, boucle Qt) sont mockées : ce test ne vérifie que l'ordre des opérations.
"""

import types

import pytest

import main


class _FakeAppSettings:
    execution_mode = "IN_APP"
    log_level = "INFO"


class _FakeScheduler:
    def __init__(self):
        self.stopped = False

    def start(self):
        pass

    def load_all_pipelines(self):
        pass

    def list_jobs(self):
        return []

    def stop(self):
        self.stopped = True


def test_scheduler_stop_runs_even_though_run_raises_system_exit(monkeypatch):
    fake_scheduler = _FakeScheduler()

    monkeypatch.setattr("database.db_manager.init_db", lambda: None)
    monkeypatch.setattr("database.db_manager.get_app_settings", lambda: _FakeAppSettings())
    monkeypatch.setattr("database.db_manager.reconcile_stale_runs", lambda: 0)
    monkeypatch.setattr("core.missed_runs.detect_missed_runs", lambda app_settings: [])
    monkeypatch.setattr("core.scheduler.init_scheduler", lambda: fake_scheduler)

    def _raise_system_exit():
        raise SystemExit(0)

    fake_ui_module = types.SimpleNamespace(run=_raise_system_exit)
    monkeypatch.setitem(__import__("sys").modules, "ui.main_window", fake_ui_module)

    with pytest.raises(SystemExit):
        main.main()

    assert fake_scheduler.stopped

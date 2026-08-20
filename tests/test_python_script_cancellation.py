"""
DataScheduler — tests/test_python_script_cancellation.py
Vérifie l'annulation coopérative (chantier dédié) de PYTHON_SCRIPT — le seul type d'étape où
elle se traduit par une vraie interruption immédiate (subprocess.Popen + sondage, remplace
subprocess.run(timeout=...)) plutôt qu'un simple abandon : un sous-processus, contrairement à un
thread Python, peut être tué de force par l'OS (voir core/steps/python_script.py).
"""

import sys
import threading
import time

from core.steps.base import StepContext
from core.steps.python_script import PythonScriptStep


def _write_script(tmp_path, code: str):
    script = tmp_path / "script.py"
    script.write_text(code, encoding="utf-8")
    return script


def test_cancel_event_kills_a_long_running_script_well_before_its_own_sleep_ends(tmp_path):
    script = _write_script(tmp_path, """
import time
time.sleep(30)
""")
    ctx = StepContext()
    step = PythonScriptStep({
        "script_path": str(script),
        "python_executable": sys.executable,
        "timeout": 300,   # largement suffisant — ce n'est pas le timeout qui doit intervenir
    })
    cancel_event = threading.Event()
    threading.Timer(0.3, cancel_event.set).start()

    start = time.monotonic()
    result = step.run(ctx, cancel_event=cancel_event)
    elapsed = time.monotonic() - start

    assert not result.success
    assert "Annulé" in result.error
    assert elapsed < 5   # tué bien avant les 30s de sommeil du script (et le timeout de 300s)


def test_without_cancel_event_a_short_script_still_succeeds_normally(tmp_path):
    """cancel_event=None (défaut) — comportement historique inchangé, aucune régression sur le
    chemin normal introduite par le passage à subprocess.Popen + sondage."""
    script = _write_script(tmp_path, "import sys; sys.exit(0)")
    ctx = StepContext()
    step = PythonScriptStep({
        "script_path": str(script),
        "python_executable": sys.executable,
    })

    result = step.run(ctx)

    assert result.success, result.error


def test_script_failure_with_nonzero_exit_code_still_reported_normally(tmp_path):
    """Un vrai échec (code de sortie non nul) doit encore produire le message habituel, pas être
    confondu avec une annulation — cancel_event jamais positionné ici."""
    script = _write_script(tmp_path, """
import sys
print("boom", file=sys.stderr)
sys.exit(1)
""")
    ctx = StepContext()
    step = PythonScriptStep({
        "script_path": str(script),
        "python_executable": sys.executable,
    })
    cancel_event = threading.Event()

    result = step.run(ctx, cancel_event=cancel_event)

    assert not result.success
    assert "code 1" in result.error
    assert "Annulé" not in result.error

"""
DataScheduler — tests/test_python_script_error_message.py
Un script qui échoue ne remontait que "Script terminé avec le code N" — la vraie raison (la
dernière ligne de stderr, en général le message d'exception d'un traceback) était loggée ligne
par ligne mais absente du message d'erreur principal affiché en premier (Historique, tooltip
Dashboard). Chantier "script Python pour un utilisateur inconnu de l'app".
"""

import sys

from core.steps.base import StepContext
from core.steps.python_script import PythonScriptStep


def _write_script(tmp_path, code: str):
    script = tmp_path / "script.py"
    script.write_text(code, encoding="utf-8")
    return script


def test_error_message_includes_last_stderr_line(tmp_path):
    script = _write_script(tmp_path, """
import sys
print("préparation du traitement", file=sys.stderr)
raise ValueError("fichier introuvable : ventes_20260101.csv")
""")
    step = PythonScriptStep({"script_path": str(script), "python_executable": sys.executable})
    result = step.run(StepContext())

    assert result.success is False
    assert "code 1" in result.error
    assert "fichier introuvable : ventes_20260101.csv" in result.error


def test_error_message_falls_back_cleanly_without_stderr(tmp_path):
    script = _write_script(tmp_path, "import sys; sys.exit(2)")
    step = PythonScriptStep({"script_path": str(script), "python_executable": sys.executable})
    result = step.run(StepContext())

    assert result.success is False
    assert result.error == "Script terminé avec le code 2"


def test_full_stderr_still_logged_line_by_line(tmp_path):
    """Le message d'erreur résumé ne remplace pas le log complet — juste un premier indice."""
    script = _write_script(tmp_path, """
import sys
print("ligne 1", file=sys.stderr)
print("ligne 2 — la vraie erreur", file=sys.stderr)
sys.exit(1)
""")
    ctx = StepContext()
    step = PythonScriptStep({"script_path": str(script), "python_executable": sys.executable})
    step.run(ctx)

    assert any("ligne 1" in line for line in ctx.log_lines)
    assert any("ligne 2" in line for line in ctx.log_lines)

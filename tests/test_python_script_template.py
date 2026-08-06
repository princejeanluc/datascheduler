"""
DataScheduler — tests/test_python_script_template.py
Vérifie le modèle de script téléchargeable (ui/step_editor/python_script_template.py) — pas
seulement qu'il est syntaxiquement valide, mais qu'il fonctionne réellement à travers
PythonScriptStep (les deux branches : autonome, et avec {ds_context_in}/{ds_context_out}), pour
qu'il tienne ses promesses auprès de quelqu'un qui le télécharge en confiance.
"""

import ast
import sys

from core.steps.base import StepContext
from core.steps.python_script import PythonScriptStep
from ui.step_editor.python_script_template import PYTHON_SCRIPT_TEMPLATE


def test_template_is_syntactically_valid_python():
    ast.parse(PYTHON_SCRIPT_TEMPLATE)


def _write_template(tmp_path):
    script = tmp_path / "modele.py"
    script.write_text(PYTHON_SCRIPT_TEMPLATE, encoding="utf-8")
    return script


def test_template_runs_standalone_without_context_tokens(tmp_path):
    script = _write_template(tmp_path)
    step = PythonScriptStep({
        "script_path": str(script),
        "python_executable": sys.executable,
        "args": ["--date", "20260806"],
    })
    result = step.run(StepContext())

    assert result.success, result.error


def test_template_reads_context_in_and_publishes_context_out(tmp_path):
    script = _write_template(tmp_path)
    ctx = StepContext()
    ctx.output_file = tmp_path / "ventes.csv"
    ctx.rows_count = 42

    step = PythonScriptStep({
        "script_path": str(script),
        "python_executable": sys.executable,
        "args": ["--date", "20260806", "--context-in", "{ds_context_in}",
                  "--context-out", "{ds_context_out}"],
    })
    result = step.run(ctx)

    assert result.success, result.error
    assert "output_file" in ctx.artifacts

"""
DataScheduler — tests/test_python_script_context.py
Vérifie le contrat d'E/S JSON optionnel de PYTHON_SCRIPT ({ds_context_in}/{ds_context_out}),
et sa rétrocompatibilité stricte quand ces tokens ne sont pas référencés.
"""

import json
import sys

from core.steps.base import StepContext
from core.steps.python_script import PythonScriptStep


def _write_script(tmp_path, code: str):
    script = tmp_path / "script.py"
    script.write_text(code, encoding="utf-8")
    return script


def test_script_reads_context_and_publishes_new_artifact(tmp_path):
    result_file = tmp_path / "result.csv"
    script = _write_script(tmp_path, f"""
import json, sys
in_path, out_path = sys.argv[1], sys.argv[2]
data = json.loads(open(in_path, encoding="utf-8").read())
assert data["rows_count"] == 42
assert "output_file" in data["artifacts"]
open(r"{result_file}", "w").write("content")
json.dump({{"artifacts": {{"cleaned": r"{result_file}"}}}}, open(out_path, "w", encoding="utf-8"))
""")
    ctx = StepContext()
    ctx.output_file = tmp_path / "input.csv"
    ctx.rows_count = 42

    step = PythonScriptStep({
        "script_path": str(script),
        "python_executable": sys.executable,
        "args": ["{ds_context_in}", "{ds_context_out}"],
    })
    result = step.run(ctx)

    assert result.success, result.error
    assert ctx.artifacts["cleaned"] == result_file


def test_script_without_output_json_still_succeeds(tmp_path):
    script = _write_script(tmp_path, """
import sys
# Ne référence pas le contexte du tout, ne touche pas au fichier de sortie.
sys.exit(0)
""")
    ctx = StepContext()
    step = PythonScriptStep({
        "script_path": str(script),
        "python_executable": sys.executable,
        "args": ["{ds_context_in}", "{ds_context_out}"],
    })
    result = step.run(ctx)

    assert result.success, result.error
    assert ctx.artifacts == {}


def test_script_with_invalid_output_json_still_succeeds(tmp_path):
    script = _write_script(tmp_path, """
import sys
out_path = sys.argv[1]
open(out_path, "w").write("ceci n'est pas du JSON")
""")
    ctx = StepContext()
    step = PythonScriptStep({
        "script_path": str(script),
        "python_executable": sys.executable,
        "args": ["{ds_context_out}"],
    })
    result = step.run(ctx)

    assert result.success, result.error
    assert ctx.artifacts == {}


def test_existing_script_config_without_tokens_gets_unchanged_argv(tmp_path):
    marker = tmp_path / "argv_seen.json"
    script = _write_script(tmp_path, f"""
import json, sys
json.dump(sys.argv[1:], open(r"{marker}", "w"))
""")
    ctx = StepContext()
    step = PythonScriptStep({
        "script_path": str(script),
        "python_executable": sys.executable,
        "args": ["--mode", "production"],
    })
    result = step.run(ctx)

    assert result.success, result.error
    seen_argv = json.loads(marker.read_text())
    assert seen_argv == ["--mode", "production"]

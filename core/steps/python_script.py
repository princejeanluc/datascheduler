"""
DataScheduler — core/steps/python_script.py
Étape : exécution d'un script Python avec arguments résolus (tokens datetime + contexte).
"""

import subprocess
import sys

from .base import BaseStep, StepContext, StepResult


class PythonScriptStep(BaseStep):

    def run(self, ctx: StepContext, on_progress=None) -> StepResult:
        result = StepResult()

        try:
            script_path = self.config.get("script_path", "")
            if not script_path:
                result.error = "Chemin du script non configuré."
                return result

            python_exe  = self.config.get("python_executable") or sys.executable
            raw_args    = self.config.get("args", [])
            working_dir = self.config.get("working_dir") or None
            timeout     = int(self.config.get("timeout", 300))

            # Résolution des tokens dans chaque argument
            args = [ctx.resolve_tokens(str(a)) for a in raw_args]
            cmd  = [python_exe, script_path] + args

            ctx.log(f"Script Python : {' '.join(cmd)}")
            if on_progress:
                on_progress("Exécution du script Python…", 50)

            proc = subprocess.run(
                cmd,
                cwd=working_dir,
                capture_output=True,
                text=True,
                timeout=timeout,
            )

            for line in (proc.stdout or "").strip().splitlines():
                ctx.log(f"  stdout: {line}")
            for line in (proc.stderr or "").strip().splitlines():
                ctx.log(f"  stderr: {line}")

            if proc.returncode != 0:
                result.error = f"Script terminé avec le code {proc.returncode}"
                return result

            ctx.log("Script Python : OK (code 0)")
            result.success = True

        except subprocess.TimeoutExpired:
            result.error = f"Délai dépassé ({self.config.get('timeout', 300)}s)"
        except Exception as e:
            result.error = str(e)

        return result

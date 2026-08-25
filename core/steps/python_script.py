"""
DataScheduler — core/steps/python_script.py
Étape : exécution d'un script Python avec arguments résolus (tokens datetime + contexte).

Contrat d'E/S optionnel : deux tokens supplémentaires, {ds_context_in} et {ds_context_out},
peuvent être placés dans les arguments configurés. S'ils le sont, le script reçoit le chemin
de deux fichiers JSON :
  - en entrée : {"artifacts": {<nom>: <chemin>, ...}, "rows_count": <int>} — tout ce que le
    contexte contient déjà (fichiers produits par les étapes précédentes, nommés).
  - en sortie (facultatif, à écrire par le script) : {"artifacts": {<nom>: <chemin>, ...}} —
    fusionné dans le contexte après coup, pour que les étapes suivantes puissent le consommer
    (sous "output_file" pour être repris implicitement par l'étape suivante, ou sous un nom
    personnalisé pour un ciblage explicite — voir docs/COOKBOOK.md).
Un script qui ne référence pas ces tokens n'est pas concerné : son argv est strictement
identique à avant l'introduction de ce contrat. Toujours passé en argument, jamais en variable
d'environnement (contrainte des postes cibles — modifier une variable d'environnement y
nécessite souvent un accès admin/helpdesk).
"""

import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from .base import BaseStep, StepContext, StepResult


def _same_executable(a: str, b: str) -> bool:
    try:
        return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))
    except (TypeError, ValueError):
        return False


class PythonScriptStep(BaseStep):

    def run(self, ctx: StepContext, cancel_event=None, on_progress=None) -> StepResult:
        result = StepResult()
        ctx_in_path: Path | None = None
        ctx_out_path: Path | None = None

        try:
            script_path = self.config.get("script_path", "")
            if not script_path:
                result.error = "Chemin du script non configuré."
                return result

            python_exe  = self.config.get("python_executable") or sys.executable
            raw_args    = self.config.get("args", [])
            working_dir = self.config.get("working_dir") or None
            timeout     = int(self.config.get("timeout", 300))

            # Piège réel (voir docs/COOKBOOK.md, "Pièges déjà rencontrés") : dans un .exe
            # PyInstaller, sys.executable est le chemin de KULU.exe lui-même, pas un
            # interpréteur Python — ce n'est vrai qu'en lançant `python main.py` directement. Un
            # step qui garde ce défaut (ou le reçoit via un ancien config_json/import) ne lance
            # pas le script : il relance une deuxième instance complète de l'application, qui
            # bloque jusqu'au timeout avant d'échouer sans indice sur la vraie cause. Détecté et
            # refusé ici plutôt que de laisser ce piège silencieux se reproduire.
            if getattr(sys, "frozen", False) and _same_executable(python_exe, sys.executable):
                result.error = (
                    "L'exécutable Python configuré pointe vers KULU.exe lui-même, pas "
                    "vers un interpréteur Python — impossible d'exécuter le script. Renseignez "
                    "explicitement le chemin d'un python.exe (venv/conda du script) dans le "
                    "champ « Exécutable Python » de cette étape."
                )
                return result

            ctx_in_path  = Path(tempfile.mkstemp(suffix=".json", prefix="ds_ctx_in_")[1])
            ctx_out_path = Path(tempfile.mkstemp(suffix=".json", prefix="ds_ctx_out_")[1])
            payload = {
                "artifacts":  {k: str(v) for k, v in ctx.artifacts.items() if v is not None},
                "rows_count": ctx.rows_count,
            }
            ctx_in_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

            # Résolution des tokens habituels d'abord, puis des deux tokens de contexte —
            # ces derniers n'ont de sens que pour cette exécution précise, donc traités ici
            # plutôt que dans StepContext.resolve_tokens() (générique à tous les steps).
            def resolve(raw: str) -> str:
                s = ctx.resolve_tokens(str(raw))
                s = s.replace("{ds_context_in}",  str(ctx_in_path))
                s = s.replace("{ds_context_out}", str(ctx_out_path))
                return s

            args = [resolve(a) for a in raw_args]
            cmd  = [python_exe, script_path] + args

            ctx.log(f"Script Python : {' '.join(cmd)}")
            if on_progress:
                on_progress("Exécution du script Python…", 50)

            # subprocess.Popen + sondage (au lieu de subprocess.run(timeout=...)) — un
            # sous-processus, contrairement à un thread Python, PEUT être tué de force par l'OS ;
            # c'est le seul type d'étape de ce chantier où l'annulation coopérative se traduit par
            # une vraie interruption immédiate plutôt qu'un abandon (voir core/pipeline.py::
            # _run_step_with_policy pour le cas général, threads orphelins compris).
            proc = subprocess.Popen(
                cmd, cwd=working_dir,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            )
            start = time.monotonic()
            cancelled = False
            while True:
                try:
                    stdout, stderr = proc.communicate(timeout=0.2)
                    break
                except subprocess.TimeoutExpired:
                    if cancel_event is not None and cancel_event.is_set():
                        cancelled = True
                        proc.terminate()
                        try:
                            stdout, stderr = proc.communicate(timeout=5)
                        except subprocess.TimeoutExpired:
                            proc.kill()
                            stdout, stderr = proc.communicate()
                        break
                    if time.monotonic() - start > timeout:
                        proc.kill()
                        proc.communicate()
                        raise subprocess.TimeoutExpired(cmd, timeout)

            for line in (stdout or "").strip().splitlines():
                ctx.log(f"  stdout: {line}")
            for line in (stderr or "").strip().splitlines():
                ctx.log(f"  stderr: {line}")

            if cancelled:
                result.error = "Annulé par l'utilisateur."
                return result

            if proc.returncode != 0:
                # La dernière ligne non vide de stderr est en général la plus utile (le message
                # d'exception d'un traceback Python) — le log complet, ligne par ligne, reste
                # disponible ci-dessus (ctx.log), mais un nouvel utilisateur qui débogue son
                # propre script mérite un premier indice sans avoir à l'ouvrir.
                stderr_lines = [l for l in (stderr or "").strip().splitlines() if l.strip()]
                result.error = f"Script terminé avec le code {proc.returncode}"
                if stderr_lines:
                    result.error += f" — {stderr_lines[-1]}"
                return result

            if ctx_out_path.exists() and ctx_out_path.stat().st_size:
                try:
                    data = json.loads(ctx_out_path.read_text(encoding="utf-8"))
                    new_artifacts = data.get("artifacts") or {}
                    for key, value in new_artifacts.items():
                        ctx.artifacts[key] = Path(value)
                    if new_artifacts:
                        ctx.log(f"Script Python : {len(new_artifacts)} artefact(s) reçu(s) : "
                                 f"{', '.join(new_artifacts)}")
                except (ValueError, OSError) as e:
                    ctx.log(f"Avertissement : sortie JSON du script invalide, ignorée ({e}).")

            ctx.log("Script Python : OK (code 0)")
            result.success = True

        except subprocess.TimeoutExpired:
            result.error = f"Délai dépassé ({self.config.get('timeout', 300)}s)"
        except Exception as e:
            result.error = str(e)
        finally:
            for p in (ctx_in_path, ctx_out_path):
                if p and p.exists():
                    try:
                        p.unlink()
                    except OSError:
                        pass

        return result

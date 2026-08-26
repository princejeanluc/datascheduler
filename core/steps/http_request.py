"""
DataScheduler — core/steps/http_request.py
Étape : appel HTTP (API REST / webhook), avec envoi optionnel du fichier
de contexte en pièce jointe multipart et sauvegarde optionnelle de la réponse.
"""

import tempfile
from pathlib import Path

from .base import BaseStep, StepContext, StepResult


def _parse_headers(raw: str) -> dict:
    headers = {}
    for line in (raw or "").splitlines():
        line = line.strip()
        if not line or ":" not in line:
            continue
        key, _, value = line.partition(":")
        headers[key.strip()] = value.strip()
    return headers


class HttpRequestStep(BaseStep):
    # PRODUCES volontairement vide, pas {"output_file"} : la sauvegarde de la réponse est
    # conditionnelle à la config (save_response), pas systématique — même raisonnement déjà
    # appliqué à PythonScriptStep/SparkSqlStep.PRODUCES (voir docs/COOKBOOK.md).

    def run(self, ctx: StepContext, cancel_event=None, on_progress=None) -> StepResult:
        result = StepResult()
        tmp_path: Path | None = None

        try:
            import requests

            method  = (self.config.get("method") or "GET").upper()
            url     = ctx.resolve_tokens(self.config.get("url_tpl", ""))
            headers = _parse_headers(ctx.resolve_tokens(self.config.get("headers", "")))
            body    = ctx.resolve_tokens(self.config.get("body_tpl", ""))
            timeout = int(self.config.get("timeout", 30))
            attach_output = self.config.get("attach_output_file", False)
            save_response = self.config.get("save_response", False)

            if not url:
                result.error = "URL non configurée."
                return result

            ctx.log(f"HTTP {method} : {url}")
            if on_progress:
                on_progress("Appel HTTP…", 60)

            files = None
            data  = body or None
            file_handle = None
            if attach_output and ctx.output_file and ctx.output_file.exists():
                file_handle = open(ctx.output_file, "rb")
                files = {"file": (ctx.output_file.name, file_handle)}

            try:
                response = requests.request(
                    method, url, headers=headers, data=data,
                    files=files, timeout=timeout,
                )
            finally:
                if file_handle:
                    file_handle.close()

            ctx.extra["status_code"] = response.status_code
            snippet = (response.text or "")[:500]
            ctx.log(f"HTTP {method} : statut {response.status_code} — {snippet}")

            if not response.ok:
                result.error = f"HTTP {response.status_code} : {snippet}"
                return result

            if save_response:
                # Sauvegardé brut, sans essayer de deviner/parser le type de contenu (JSON,
                # fichier binaire...) — reste cohérent avec le modèle d'artefacts existant,
                # toujours un fichier, jamais une valeur typée en mémoire.
                tmp = tempfile.NamedTemporaryFile(suffix=".dat", delete=False, prefix="ds_")
                tmp_path = Path(tmp.name)
                tmp.write(response.content)
                tmp.close()
                ctx.output_file = tmp_path
                ctx.log(f"Réponse sauvegardée : {tmp_path} ({len(response.content)} octet(s))")

            result.success = True

        except Exception as e:
            result.error = str(e)
        finally:
            # Même garde que FtpDownloadStep : un fichier temporaire créé avant de savoir si le
            # reste de l'étape va réussir ne sera jamais référencé dans ctx.artifacts en cas
            # d'échec, donc jamais nettoyé par run_pipeline — à nettoyer ici.
            if tmp_path is not None and not result.success and tmp_path.exists():
                try:
                    tmp_path.unlink()
                except OSError:
                    pass

        return result

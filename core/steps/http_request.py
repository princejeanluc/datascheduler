"""
DataScheduler — core/steps/http_request.py
Étape : appel HTTP (API REST / webhook), avec envoi optionnel du fichier
de contexte en pièce jointe multipart.
"""

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

    def run(self, ctx: StepContext, on_progress=None) -> StepResult:
        result = StepResult()

        try:
            import requests

            method  = (self.config.get("method") or "GET").upper()
            url     = ctx.resolve_tokens(self.config.get("url_tpl", ""))
            headers = _parse_headers(ctx.resolve_tokens(self.config.get("headers", "")))
            body    = ctx.resolve_tokens(self.config.get("body_tpl", ""))
            timeout = int(self.config.get("timeout", 30))
            attach_output = self.config.get("attach_output_file", False)

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

            result.success = True

        except Exception as e:
            result.error = str(e)

        return result

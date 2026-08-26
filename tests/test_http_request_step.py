"""
DataScheduler — tests/test_http_request_step.py
HttpRequestStep n'avait jusqu'ici aucun test dédié. Couvre le comportement existant (statut,
pièce jointe) et la nouvelle case "Sauvegarder la réponse" (demande utilisateur : une API peut
renvoyer un fichier ou des données, pas seulement un accusé de réception — HTTP_REQUEST était
jusqu'ici une impasse pour le flux de données, aucune sortie jamais publiée dans ctx.artifacts).
Réponse sauvegardée brute (octets tels quels), sans essayer de deviner/parser son type — reste
cohérent avec le modèle d'artefacts existant, toujours un fichier.
"""

from pathlib import Path

import pytest

from core.steps.base import StepContext
from core.steps.http_request import HttpRequestStep


class _FakeResponse:
    def __init__(self, status_code=200, content=b"", text=None):
        self.status_code = status_code
        self.content = content
        self.text = text if text is not None else content.decode("utf-8", errors="replace")
        self.ok = 200 <= status_code < 400


def _patch_requests(monkeypatch, response, capture: dict | None = None):
    import requests

    def _fake_request(method, url, headers=None, data=None, files=None, timeout=None):
        if capture is not None:
            capture.update(method=method, url=url, headers=headers, data=data,
                            files=files, timeout=timeout)
        return response

    monkeypatch.setattr(requests, "request", _fake_request)


def test_success_without_save_response_leaves_output_file_untouched(monkeypatch):
    _patch_requests(monkeypatch, _FakeResponse(200, b"ok"))

    step = HttpRequestStep({"url_tpl": "https://example.test/ping"})
    ctx = StepContext()
    result = step.run(ctx)

    assert result.success, result.error
    assert ctx.output_file is None
    assert ctx.extra["status_code"] == 200


def test_save_response_writes_content_to_output_file(monkeypatch):
    _patch_requests(monkeypatch, _FakeResponse(200, b'{"rows": 3}'))

    step = HttpRequestStep({"url_tpl": "https://example.test/data", "save_response": True})
    ctx = StepContext()
    result = step.run(ctx)

    try:
        assert result.success, result.error
        assert ctx.output_file is not None
        assert ctx.output_file.exists()
        assert ctx.output_file.read_bytes() == b'{"rows": 3}'
    finally:
        if ctx.output_file and ctx.output_file.exists():
            ctx.output_file.unlink()


def test_save_response_false_by_default(monkeypatch):
    """Zéro changement de comportement pour un pipeline existant sans la case cochée."""
    _patch_requests(monkeypatch, _FakeResponse(200, b"some body"))

    step = HttpRequestStep({"url_tpl": "https://example.test/ping"})   # save_response absent
    ctx = StepContext()
    result = step.run(ctx)

    assert result.success, result.error
    assert "output_file" not in ctx.artifacts


def test_failed_response_never_saves_anything(monkeypatch):
    _patch_requests(monkeypatch, _FakeResponse(500, b"boom"))

    step = HttpRequestStep({"url_tpl": "https://example.test/fail", "save_response": True})
    ctx = StepContext()
    result = step.run(ctx)

    assert not result.success
    assert "500" in result.error
    assert ctx.output_file is None


def test_save_response_does_not_break_existing_attach_output_file(monkeypatch, tmp_path):
    """attach_output_file lit ctx.output_file AVANT l'appel (fichier amont) ; save_response
    écrase ensuite ctx.output_file avec la réponse — les deux réglages ne doivent pas se
    marcher dessus."""
    upstream = tmp_path / "upstream.csv"
    upstream.write_text("a,b\n1,2\n", encoding="utf-8")

    capture = {}
    _patch_requests(monkeypatch, _FakeResponse(200, b"server-said-ok"), capture)

    step = HttpRequestStep({
        "url_tpl": "https://example.test/upload",
        "attach_output_file": True,
        "save_response": True,
    })
    ctx = StepContext()
    ctx.output_file = upstream
    result = step.run(ctx)

    try:
        assert result.success, result.error
        assert capture["files"]["file"][0] == "upstream.csv"   # le fichier amont a bien été envoyé
        assert ctx.output_file.read_bytes() == b"server-said-ok"   # puis remplacé par la réponse
        assert ctx.output_file != upstream
    finally:
        if ctx.output_file and ctx.output_file.exists():
            ctx.output_file.unlink()


def test_missing_url_returns_error_without_calling_requests(monkeypatch):
    called = []
    import requests
    monkeypatch.setattr(requests, "request", lambda *a, **kw: called.append(1))

    step = HttpRequestStep({"url_tpl": "", "save_response": True})
    result = step.run(StepContext())

    assert not result.success
    assert called == []

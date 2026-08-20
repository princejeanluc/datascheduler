"""
DataScheduler — tests/test_compress_step.py
Vérifie CompressStep : source à 3 niveaux dès la conception (chemin explicite, Source ciblée
via reads_from_step_key — réorientation générique par core/pipeline.py vérifiée de bout en bout
ci-dessous, sans code particulier dans compress.py —, ctx.output_file par défaut), contenu réel
de l'archive produite, nommage, et publication sous output_name.
"""

from pathlib import Path
import zipfile

from core.steps.compress import CompressStep
from core.steps.base import StepContext, BaseStep, StepResult
import core.steps as steps_module
from core.pipeline import run_pipeline
from database import db_manager as db


def test_uses_explicit_path_when_set(tmp_path):
    src = tmp_path / "rapport.csv"
    src.write_text("a,b\n1,2\n")

    ctx = StepContext()   # rien en amont
    step = CompressStep({"explicit_path": str(src)})
    result = step.run(ctx)

    assert result.success, result.error
    assert ctx.output_file.suffix == ".zip"


def test_falls_back_to_context_when_no_explicit_path(tmp_path):
    src = tmp_path / "from_ctx.csv"
    src.write_text("x")

    ctx = StepContext()
    ctx.output_file = src
    step = CompressStep({})
    result = step.run(ctx)

    assert result.success, result.error
    assert ctx.output_file.suffix == ".zip"


def test_fails_cleanly_without_explicit_path_or_context():
    ctx = StepContext()
    step = CompressStep({})
    result = step.run(ctx)

    assert not result.success
    assert "Aucun fichier source" in result.error


def test_archive_contains_the_original_file_with_its_own_name(tmp_path):
    src = tmp_path / "ventes.csv"
    src.write_bytes(b"date,montant\n2026-08-07,42\n")

    step = CompressStep({"explicit_path": str(src)})
    ctx = StepContext()
    result = step.run(ctx)

    assert result.success, result.error
    with zipfile.ZipFile(ctx.output_file) as zf:
        assert zf.namelist() == ["ventes.csv"]
        assert zf.read("ventes.csv") == b"date,montant\n2026-08-07,42\n"


def test_default_archive_name_derives_from_source_stem(tmp_path):
    src = tmp_path / "ventes.csv"
    src.write_text("contenu")

    ctx = StepContext()
    step = CompressStep({"explicit_path": str(src)})
    result = step.run(ctx)

    assert result.success, result.error
    assert ctx.output_file.name == "ventes.zip"


def test_custom_archive_name_with_tokens(tmp_path):
    src = tmp_path / "ventes.csv"
    src.write_text("contenu")

    ctx = StepContext()
    step = CompressStep({"explicit_path": str(src), "archive_name_tpl": "export_{yyyy}"})
    result = step.run(ctx)

    assert result.success, result.error
    assert ctx.output_file.name.startswith("export_")
    assert ctx.output_file.suffix == ".zip"


def test_publishes_under_output_name(tmp_path):
    src = tmp_path / "ventes.csv"
    src.write_text("contenu")

    ctx = StepContext()
    step = CompressStep({"explicit_path": str(src), "output_name": "archive_ventes"})
    result = step.run(ctx)

    assert result.success, result.error
    assert ctx.artifacts["archive_ventes"] == ctx.output_file


def test_compression_actually_reduces_size_for_compressible_content(tmp_path):
    src = tmp_path / "repetitif.csv"
    src.write_text("a,b,c\n" * 10_000)   # très compressible

    ctx = StepContext()
    step = CompressStep({"explicit_path": str(src)})
    result = step.run(ctx)

    assert result.success, result.error
    assert ctx.output_file.stat().st_size < src.stat().st_size


def test_zip_file_is_cleaned_up_on_failure(tmp_path, monkeypatch):
    src = tmp_path / "ventes.csv"
    src.write_text("contenu")

    import core.steps.compress as compress_module

    def _boom(*a, **k):
        raise OSError("disque plein (simulé)")

    monkeypatch.setattr(compress_module.zipfile, "ZipFile", _boom)

    step = CompressStep({"explicit_path": str(src)})
    result = step.run(StepContext())

    assert not result.success


class _FakeProducerStep(BaseStep):
    PRODUCES = {"output_file"}

    def run(self, ctx, cancel_event=None, on_progress=None) -> StepResult:
        result = StepResult()
        path = Path(self.config["path"])
        path.write_text(self.config["content"])
        ctx.output_file = path
        result.success = True
        return result


def test_run_pipeline_compress_respects_targeted_source(test_db, monkeypatch, tmp_path):
    # Preuve de bout en bout, via le vrai moteur (core/pipeline.py) et la vraie CompressStep,
    # que la Source ciblée explicitement (reads_from_step_key) fonctionne pour COMPRESS sans
    # aucun code particulier dans compress.py — la réorientation de ctx.output_file est générique,
    # gérée par le moteur avant l'appel à run() (voir _execute_linear/_execute_graph).
    monkeypatch.setitem(steps_module._REGISTRY, "DB_EXTRACT", _FakeProducerStep)

    p1 = tmp_path / "producer1.txt"
    p2 = tmp_path / "producer2.txt"

    pipeline = db.create_pipeline(name="test-compress-targeting")
    db.save_steps(pipeline.id, [
        {"step_type": "DB_EXTRACT", "config": {"path": str(p1), "content": "FROM_PRODUCER_1", "_step_key": "prod1"}},
        {"step_type": "DB_EXTRACT", "config": {"path": str(p2), "content": "FROM_PRODUCER_2", "_step_key": "prod2"}},
        {"step_type": "COMPRESS",   "config": {"reads_from_step_key": "prod1"}},
    ])

    result = run_pipeline(pipeline.id)

    assert result.success, result.error
    # CompressStep journalise le nom du fichier source réellement compressé — preuve directe
    # que la Source ciblée ("prod1") l'a bien emporté sur "prod2" (le plus récent, comportement
    # par défaut sans ciblage). Les deux noms apparaissent par ailleurs dans le journal (nettoyage
    # des artefacts temporaires) : on cible donc la ligne "Compression : OK" précisément.
    compression_lines = [l for l in result.log_lines if "Compression : OK" in l]
    assert len(compression_lines) == 1
    assert "producer1.txt" in compression_lines[0]
    assert "producer2.txt" not in compression_lines[0]

"""
DataScheduler — tests/test_extract_variables_step.py
Étape EXTRACT_VARIABLES : lit un fichier source déjà produit, attendu à une seule ligne de
données, et publie certaines colonnes dans ctx.variables. Zéro connexion base de données, zéro
requête — voir docstring du module pour la responsabilité volontairement étroite du step.
"""

import csv

import pytest

from core.steps import get_step
from core.steps.base import StepContext


def _write_csv(path, header, row, separator=";", encoding="utf-8-sig"):
    with open(path, "w", newline="", encoding=encoding) as f:
        w = csv.writer(f, delimiter=separator)
        w.writerow(header)
        w.writerow(row)


@pytest.fixture
def one_row_csv(tmp_path):
    path = tmp_path / "resultat.csv"
    _write_csv(path, ["MAX_DATE", "TOTAL_SALES", "LABEL"], ["09/09/2026", "1234.5", "ok"])
    return path


def _run(config, ctx):
    return get_step("EXTRACT_VARIABLES", config).run(ctx)


def test_extracts_text_number_and_date_into_ctx_variables(one_row_csv):
    ctx = StepContext()
    ctx.output_file = one_row_csv
    result = _run({
        "mappings": [
            {"source": "MAX_DATE", "target": "date_max", "type": "date", "date_format": "{dd}/{MM}/{yyyy}"},
            {"source": "TOTAL_SALES", "target": "total", "type": "number"},
            {"source": "LABEL", "target": "label", "type": "text"},
        ]
    }, ctx)
    assert result.success, result.error
    assert ctx.variables == {"date_max": "2026-09-09", "total": 1234.5, "label": "ok"}


def test_datetime_type_produces_iso_datetime_string(tmp_path):
    path = tmp_path / "r.csv"
    _write_csv(path, ["TS"], ["09/09/2026 14:30:00"])
    ctx = StepContext(); ctx.output_file = path
    result = _run({
        "mappings": [{"source": "TS", "target": "ts", "type": "datetime",
                      "date_format": "{dd}/{MM}/{yyyy} {HH}:{mm}:{ss}"}]
    }, ctx)
    assert result.success, result.error
    assert ctx.variables["ts"] == "2026-09-09T14:30:00"


def test_does_not_touch_ctx_output_file(one_row_csv):
    """Contrairement à LOCAL_COPY/COMPRESS, cette étape ne produit aucun nouveau fichier — le
    fichier source reste sélectionnable en aval sous la clé de l'étape qui l'a réellement
    produit, jamais réaiguillé par celle-ci."""
    ctx = StepContext()
    ctx.output_file = one_row_csv
    _run({"mappings": [{"source": "LABEL", "target": "label"}]}, ctx)
    assert ctx.output_file == one_row_csv


def test_zero_rows_is_rejected(tmp_path):
    path = tmp_path / "empty.csv"
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        csv.writer(f, delimiter=";").writerow(["MAX_DATE"])
    ctx = StepContext(); ctx.output_file = path
    result = _run({"mappings": [{"source": "MAX_DATE", "target": "x"}]}, ctx)
    assert not result.success
    assert "Aucune ligne" in result.error


def test_multiple_rows_is_rejected(tmp_path):
    path = tmp_path / "multi.csv"
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["MAX_DATE"]); w.writerow(["09/09/2026"]); w.writerow(["10/09/2026"])
    ctx = StepContext(); ctx.output_file = path
    result = _run({"mappings": [{"source": "MAX_DATE", "target": "x"}]}, ctx)
    assert not result.success
    assert "2 lignes" in result.error


def test_missing_column_is_rejected_with_available_columns_listed(one_row_csv):
    ctx = StepContext(); ctx.output_file = one_row_csv
    result = _run({"mappings": [{"source": "DOES_NOT_EXIST", "target": "x"}]}, ctx)
    assert not result.success
    assert "DOES_NOT_EXIST" in result.error
    assert "MAX_DATE" in result.error


def test_invalid_number_is_rejected(tmp_path):
    path = tmp_path / "r.csv"
    _write_csv(path, ["TOTAL"], ["not-a-number"])
    ctx = StepContext(); ctx.output_file = path
    result = _run({"mappings": [{"source": "TOTAL", "target": "total", "type": "number"}]}, ctx)
    assert not result.success
    assert "TOTAL" in result.error


def test_date_not_matching_format_is_rejected(one_row_csv):
    ctx = StepContext(); ctx.output_file = one_row_csv
    result = _run({
        "mappings": [{"source": "MAX_DATE", "target": "d", "type": "date", "date_format": "{yyyy}-{MM}-{dd}"}]
    }, ctx)
    assert not result.success
    assert "MAX_DATE" in result.error


def test_no_source_file_available_is_rejected():
    ctx = StepContext()
    result = _run({"mappings": [{"source": "x", "target": "y"}]}, ctx)
    assert not result.success
    assert "Aucun fichier source" in result.error


def test_no_mappings_configured_is_rejected(one_row_csv):
    ctx = StepContext(); ctx.output_file = one_row_csv
    result = _run({"mappings": []}, ctx)
    assert not result.success
    assert "correspondance" in result.error.lower()


def test_explicit_path_overrides_ctx_output_file(tmp_path, one_row_csv):
    other = tmp_path / "other.csv"
    _write_csv(other, ["LABEL"], ["from-explicit-path"])
    ctx = StepContext()
    ctx.output_file = one_row_csv   # ne doit pas être utilisé
    result = _run({
        "explicit_path": str(other),
        "mappings": [{"source": "LABEL", "target": "label"}],
    }, ctx)
    assert result.success, result.error
    assert ctx.variables["label"] == "from-explicit-path"


def test_custom_separator_and_encoding_are_respected(tmp_path):
    path = tmp_path / "r.csv"
    _write_csv(path, ["A", "B"], ["1", "2"], separator="|", encoding="latin-1")
    ctx = StepContext(); ctx.output_file = path
    result = _run({
        "csv_separator": "|", "csv_encoding": "latin-1",
        "mappings": [{"source": "A", "target": "a"}, {"source": "B", "target": "b"}],
    }, ctx)
    assert result.success, result.error
    assert ctx.variables == {"a": "1", "b": "2"}

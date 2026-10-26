"""
DataScheduler — tests/test_run_status.py
Fonctions pures de ui/graph_editor/run_status.py (C9, Atelier-echec) — aucune dépendance Qt ni DB,
SimpleNamespace en guise de ligne PipelineRunStep (mêmes attributs, jamais une vraie session).
"""

from datetime import datetime, timedelta
from types import SimpleNamespace

from ui.graph_editor.run_status import (
    format_step_duration, format_rows_count, format_bytes_fr,
    node_status_text, node_card_state, edge_run_state,
    summarize_run_steps, parse_attempts, what_happened_next,
)


def _step(status="SUCCESS", attempts=1, attempts_json=None, started_at=None, finished_at=None,
          rows_count=None, output_size_bytes=None, port_taken=None, error_message=None,
          step_label="Étape", reused_from_resume=False):
    return SimpleNamespace(
        status=status, attempts=attempts, attempts_json=attempts_json,
        started_at=started_at, finished_at=finished_at, rows_count=rows_count,
        output_size_bytes=output_size_bytes, port_taken=port_taken, error_message=error_message,
        step_label=step_label, reused_from_resume=reused_from_resume,
    )


# ── Formatage ──────────────────────────────────

def test_format_step_duration_matches_the_pipelines_view_convention():
    assert format_step_duration(0) == "0 s"
    assert format_step_duration(41) == "41 s"
    assert format_step_duration(62) == "1 min 02"


def test_format_rows_count_uses_space_thousands_separator_and_french_suffix():
    assert format_rows_count(83212) == "83 212 l."
    assert format_rows_count(0) is None
    assert format_rows_count(None) is None


def test_format_bytes_fr_picks_the_smallest_useful_unit():
    assert format_bytes_fr(500) == "500 o"
    assert format_bytes_fr(4_300_000) == "4,1 Mo"
    assert format_bytes_fr(None) is None


# ── Statut par nœud ────────────────────────────

def test_node_status_text_none_when_step_was_never_part_of_this_run():
    assert node_status_text(None) is None


def test_node_status_text_success_shows_duration_and_rows_count():
    t0 = datetime(2026, 10, 18, 11, 0, 0)
    row = _step(status="SUCCESS", started_at=t0, finished_at=t0 + timedelta(seconds=41), rows_count=83212)
    text, color = node_status_text(row)
    assert text == "✓ 41 s · 83 212 l."
    assert color == "success"


def test_node_status_text_success_via_error_port_is_prefixed():
    t0 = datetime(2026, 10, 18, 11, 0, 0)
    row = _step(status="SUCCESS", started_at=t0, finished_at=t0 + timedelta(seconds=1))
    text, color = node_status_text(row, via_error_port=True)
    assert text == "✓ via le port d'erreur · 1 s"
    assert color == "success"


def test_node_status_text_failed_with_one_attempt_is_singular():
    row = _step(status="FAILED", attempts=1)
    text, color = node_status_text(row)
    assert text == "✕ échouée"
    assert color == "danger"


def test_node_status_text_failed_with_several_attempts_counts_them():
    row = _step(status="FAILED", attempts=3)
    text, color = node_status_text(row)
    assert text == "✕ 3 tentatives refusées"
    assert color == "danger"


def test_node_status_text_skipped_is_not_executed():
    text, color = node_status_text(_step(status="SKIPPED"))
    assert text == "non exécutée"
    assert color == "text_dim"


def test_node_status_text_skipped_resume_is_reused():
    text, color = node_status_text(_step(status="SKIPPED_RESUME"))
    assert text == "réutilisée (reprise)"


# ── État de carte ──────────────────────────────

def test_node_card_state_skipped_is_not_executed():
    assert node_card_state(_step(status="SKIPPED")) == "not_executed"
    assert node_card_state(_step(status="CANCELLED")) == "not_executed"


def test_node_card_state_success_via_error_port_is_error_triggered():
    assert node_card_state(_step(status="SUCCESS"), via_error_port=True) == "error_triggered"


def test_node_card_state_plain_success_is_none():
    assert node_card_state(_step(status="SUCCESS")) is None


def test_node_card_state_none_for_a_step_not_in_this_run():
    assert node_card_state(None) is None


# ── État des arêtes ────────────────────────────

def test_edge_run_state_true_false_ports_are_never_overridden_by_the_run():
    assert edge_run_state("true", _step(status="SUCCESS"), _step(status="SUCCESS")) is None
    assert edge_run_state("false", None, None) is None


def test_edge_run_state_plain_port_taken_when_source_succeeded_and_target_ran():
    assert edge_run_state("output_file", _step(status="SUCCESS"), _step(status="SUCCESS")) == "taken"


def test_edge_run_state_plain_port_not_taken_when_source_failed():
    assert edge_run_state("output_file", _step(status="FAILED"), None) == "not_taken"


def test_edge_run_state_plain_port_not_taken_when_target_never_ran():
    assert edge_run_state("output_file", _step(status="SUCCESS"), None) == "not_taken"


def test_edge_run_state_error_port_triggered_when_target_ran():
    assert edge_run_state("error", _step(status="FAILED"), _step(status="SUCCESS")) == "error_triggered"


def test_edge_run_state_error_port_waiting_when_target_never_ran():
    assert edge_run_state("error", _step(status="SUCCESS"), None) == "error_waiting"


# ── Bandeau résumé ─────────────────────────────

def test_summarize_run_steps_counts_each_status_and_followed_error_paths():
    rows = [
        _step(status="SUCCESS"), _step(status="SUCCESS"), _step(status="SUCCESS"),
        _step(status="SUCCESS"), _step(status="SUCCESS"),
        _step(status="FAILED"),
        _step(status="FAILED", port_taken="error"),   # la jonction ET elle-même, en échec
        _step(status="SKIPPED"), _step(status="SKIPPED"),
        _step(status="SUCCESS", port_taken="error"),   # Signaler l'échec, atteint par le port d'erreur
    ]
    summary = summarize_run_steps(rows)
    assert summary == {
        "success": 6, "failed": 2, "not_executed": 2, "error_paths_followed": 2,
    }


def test_summarize_run_steps_empty_list():
    assert summarize_run_steps([]) == {
        "success": 0, "failed": 0, "not_executed": 0, "error_paths_followed": 0,
    }


# ── Tentatives ─────────────────────────────────

def test_parse_attempts_returns_the_decoded_list():
    row = _step(attempts_json='[{"n": 1, "started_at": "x", "finished_at": "y", "error": "refused"}]')
    assert parse_attempts(row) == [{"n": 1, "started_at": "x", "finished_at": "y", "error": "refused"}]


def test_parse_attempts_tolerates_missing_or_invalid_json():
    assert parse_attempts(_step(attempts_json=None)) == []
    assert parse_attempts(_step(attempts_json="not json")) == []
    assert parse_attempts(None) == []


# ── Ce qui s'est passé ensuite ─────────────────

def test_what_happened_next_reports_the_error_port_target_outcome():
    steps_by_key = {"webhook": _step(status="SUCCESS", step_label="Signaler l'échec")}
    lines = what_happened_next("depot", [("webhook", "error")], steps_by_key)
    assert lines == ["Port d'erreur suivi : Signaler l'échec a réussi."]


def test_what_happened_next_reuses_the_real_stored_error_message_for_a_failed_successor():
    steps_by_key = {
        "join": _step(status="FAILED", step_label="Toutes (ET)",
                       error_message="Passerelle de jonction (ET) : au moins une branche entrante n'a pas abouti."),
    }
    lines = what_happened_next("depot", [("join", "output_file")], steps_by_key)
    assert lines == [
        "Toutes (ET) a échoué : Passerelle de jonction (ET) : au moins une branche entrante n'a pas abouti.",
    ]


def test_what_happened_next_reports_skipped_successors():
    steps_by_key = {"notify": _step(status="SKIPPED", step_label="Prévenir l'équipe")}
    lines = what_happened_next("join", [("notify", "output_file")], steps_by_key)
    assert lines == ["Prévenir l'équipe n'a pas été exécutée."]


def test_what_happened_next_ignores_successors_absent_from_this_run():
    lines = what_happened_next("depot", [("never_ran", "output_file")], {})
    assert lines == []

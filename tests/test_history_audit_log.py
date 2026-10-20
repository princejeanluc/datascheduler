"""
DataScheduler — tests/test_history_audit_log.py
Fumée (offscreen Qt) : le "Journal des modifications" de la vue Historique (chantier UX
post-personas, item 3 couche 3 — persona "Nadia") affiche bien les AuditEvent en base, sans
avoir à ouvrir la base SQLite à la main.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_audit_table_lists_events_most_recent_first(qapp, test_db):
    """A11 : le type est traduit à l'affichage (event_type reste stocké tel quel en base,
    db.get_audit_events() ci-dessus le prouve déjà)."""
    from database import db_manager as db
    from ui.main_window.history_view import HistoryView

    db.log_audit_event("pipeline_created", pipeline_id=1, pipeline_name="p1", detail="détail 1")
    db.log_audit_event("pipeline_edited", pipeline_id=1, pipeline_name="p1", detail="détail 2")

    events = db.get_audit_events()
    table = HistoryView._build_audit_table(events)

    assert table.rowCount() == 2
    assert table.item(0, 1).text() == "Modification"
    assert table.item(0, 2).text() == "p1"
    assert table.item(0, 4).text() == "détail 2"
    assert table.item(1, 1).text() == "Création"


def test_audit_table_handles_missing_optional_fields(qapp, test_db):
    from database import db_manager as db
    from ui.main_window.history_view import HistoryView

    db.log_audit_event("pipeline_deleted")

    events = db.get_audit_events()
    table = HistoryView._build_audit_table(events)

    assert table.item(0, 2).text() == "—"
    assert table.item(0, 4).text() == "—"


def test_audit_table_empty_when_no_events(qapp, test_db):
    from ui.main_window.history_view import HistoryView

    table = HistoryView._build_audit_table([])
    assert table.rowCount() == 0


def test_event_type_label_and_color_covers_known_and_unknown_types():
    """A11 : seuls les 6 types connus ont un libellé/couleur dédiés — un type futur (B6 :
    connexion, requête, réglage) retombe sur le texte brut + text_main, jamais un crash."""
    from ui.main_window.history_view import _event_type_label_and_color

    assert _event_type_label_and_color("pipeline_created") == ("Création", "success")
    assert _event_type_label_and_color("pipeline_edited") == ("Modification", "text_main")
    assert _event_type_label_and_color("pipeline_deleted") == ("Suppression", "danger")
    assert _event_type_label_and_color("pipeline_duplicated") == ("Duplication", "text_main")
    assert _event_type_label_and_color("pipeline_exported") == ("Export", "text_main")
    assert _event_type_label_and_color("pipeline_imported") == ("Import", "signal_pale")
    assert _event_type_label_and_color("connection_created") == ("connection_created", "text_main")


def test_translate_audit_detail_reformulates_only_the_import_action_pattern(qapp, test_db):
    """A11, question 5 (tranchée par l'utilisateur) : seul le motif technique brut
    "action=..." de l'import est reformulé — un detail déjà lisible (save_steps,
    save_pipeline_graph, export, duplication) reste tel quel, et un detail vide reste "—" (jamais
    de donnée inventée, ex. pas de recalcul du nombre d'étapes pour "Création")."""
    from database import db_manager as db
    from ui.main_window.history_view import _translate_audit_detail

    db.log_audit_event("pipeline_imported", detail="action=overwrite")
    db.log_audit_event("pipeline_imported", detail="action=inconnu")
    db.log_audit_event("pipeline_created")
    db.log_audit_event("pipeline_duplicated", detail="depuis « original »")

    overwrite_event = next(e for e in db.get_audit_events() if e.detail == "action=overwrite")
    assert _translate_audit_detail(overwrite_event) == "Pipeline existant écrasé"

    unknown_action_event = next(e for e in db.get_audit_events() if e.detail == "action=inconnu")
    assert _translate_audit_detail(unknown_action_event) == "action=inconnu"

    created_event = next(e for e in db.get_audit_events() if e.event_type == "pipeline_created")
    assert _translate_audit_detail(created_event) == "—"

    dup_event = next(e for e in db.get_audit_events() if e.event_type == "pipeline_duplicated")
    assert _translate_audit_detail(dup_event) == "depuis « original »"


def test_history_view_audit_tab_has_the_verbatim_footnote(qapp, test_db):
    """A12 : texte de bas de page repris mot pour mot de la maquette (footer de
    Historique-modifications.html)."""
    from PySide6.QtWidgets import QLabel

    from ui.main_window.history_view import HistoryView

    view = HistoryView()
    mod_page = view._tabs_stack.widget(1)
    texts = " ".join(lbl.text() for lbl in mod_page.findChildren(QLabel))
    assert "Les lignes « proposé » étendent le suivi aux connexions" in texts


def test_history_view_second_tab_shows_the_audit_table(qapp, test_db):
    """A1/A11 : remplace l'ancien bouton + QDialog (_on_audit_log, supprimé) — le second onglet
    "Journal des modifications" affiche directement la table, sans dialogue à ouvrir."""
    from database import db_manager as db
    from ui.main_window.history_view import HistoryView

    db.log_audit_event("pipeline_created", pipeline_id=1, pipeline_name="p1")

    view = HistoryView()
    assert not hasattr(view, "_on_audit_log")
    assert view.audit_table.rowCount() == 1

    view._set_active_tab(1)
    assert view._mod_layout.indexOf(view.audit_table) >= 0


def test_day_runs_table_lists_runs_most_recent_first(qapp, test_db):
    """Détail d'une case du calendrier de fréquence (chantier identité, vague 4, idée 13)."""
    from database import db_manager as db
    from ui.main_window.history_view import HistoryView

    p = db.create_pipeline(name="day-detail-test")
    r1 = db.create_run(p.id)
    db.finish_run(r1.id, status="SUCCESS", rows_exported=100)
    r2 = db.create_run(p.id)
    db.finish_run(r2.id, status="FAILED")

    runs = db.get_runs(p.id)
    table = HistoryView._build_day_runs_table(runs)

    assert table.rowCount() == 2
    assert table.item(0, 2).text() == "—"   # r2 (le plus récent) — FAILED, pas de lignes


def test_on_frequency_day_clicked_opens_bubble_with_that_days_runs(qapp, test_db):
    """A9 (refonte, lot A-Historique) : remplace l'ancien QDialog par la bulle ancrée Bubble —
    une ligne par run du jour, toute la ligne cliquable (vérifié séparément, voir
    test_history_status_filter_and_navigation.py)."""
    from datetime import date

    from database import db_manager as db
    from ui.main_window.history_view import HistoryView

    p = db.create_pipeline(name="day-click-test")
    run = db.create_run(p.id)
    db.finish_run(run.id, status="SUCCESS")
    today = date.today()

    view = HistoryView()
    view._on_frequency_day_clicked(p, today)

    assert view._bubble is not None
    assert view._bubble.isVisible()


def test_bubble_run_row_click_closes_bubble_and_opens_the_run_panel(qapp, test_db):
    """A9+A10 : cliquer une ligne de la bulle ferme la bulle et ouvre le panneau latéral de ce
    run (pas run_log_dialog.py directement depuis cet écran, qui reste réservé à
    PipelineDetailDialog — un chemin séparé, pas remplacé ici)."""
    from PySide6.QtWidgets import QLabel
    from database import db_manager as db
    from ui.main_window.history_view import HistoryView

    p = db.create_pipeline(name="day-click-row-test")
    run = db.create_run(p.id)
    db.finish_run(run.id, status="SUCCESS")

    view = HistoryView()
    view._on_frequency_day_clicked(p, run.started_at.date())
    bubble = view._bubble
    assert bubble.isVisible()

    view._on_bubble_run_clicked(run.id)

    assert not bubble.isVisible()
    assert not view._side_panel.isHidden()
    content_text = " ".join(lbl.text() for lbl in view._side_panel.findChildren(QLabel))
    assert f"EXÉCUTION #{run.id}" in content_text


def test_on_frequency_day_clicked_no_op_when_day_has_no_runs(qapp, test_db):
    """Aucune exécution ce jour-là — pas de bulle vide à ouvrir."""
    from datetime import date

    from database import db_manager as db
    from ui.main_window.history_view import HistoryView

    p = db.create_pipeline(name="day-click-empty-test")

    view = HistoryView()
    view._on_frequency_day_clicked(p, date.today())
    assert view._bubble is None

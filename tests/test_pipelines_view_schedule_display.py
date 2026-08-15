"""
DataScheduler — tests/test_pipelines_view_schedule_display.py
Bug réel signalé par l'utilisateur : la colonne "Planification" de PipelinesView affichait
"CUSTOM 06:00" pour un pipeline en fréquence Personnalisée (Cron), quelle que soit l'expression
cron réellement enregistrée — scheduled_time n'est jamais utilisé par le scheduler pour CUSTOM
(voir core/scheduler.py::build_cron_trigger), mais la colonne le concaténait quand même au lieu
de réutiliser describe_schedule(), qui gère déjà ce cas correctement.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from database import db_manager as db


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_planning_column_shows_cron_expression_for_custom_frequency(qapp, test_db):
    from ui.main_window.pipelines_view import PipelinesView

    db.create_pipeline(name="custom-freq", frequency="CUSTOM", cron_expression="30 5 * * 1,3,5")

    view = PipelinesView()
    view.refresh()

    plan_text = view.table.item(0, 3).text()
    assert plan_text == "30 5 * * 1,3,5"
    assert "06:00" not in plan_text


def test_planning_column_shows_daily_time_unaffected(qapp, test_db):
    from ui.main_window.pipelines_view import PipelinesView

    db.create_pipeline(name="daily-freq", frequency="DAILY", scheduled_time="08:15")

    view = PipelinesView()
    view.refresh()

    assert view.table.item(0, 3).text() == "Quotidien 08:15"

"""
DataScheduler — tests/test_queries_view_workshop.py
QueriesView (chantier atelier SQL) : atelier maître-détail — remplace le tableau + dialogue modal
(voir tests/test_sql_query_dialog.py, supprimé : tests/test_queries_view_usage_column.py, écrit
contre l'ancien view.table qui n'existe plus).
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


def test_empty_state_shown_when_no_queries(qapp, test_db):
    from ui.main_window.queries_view import QueriesView

    view = QueriesView()
    assert not view._empty_label.isHidden()
    assert view.list_widget.isHidden()
    assert view._active_id is None


def test_loads_first_query_alphabetically_by_default(qapp, test_db):
    from ui.main_window.queries_view import QueriesView

    db.create_sql_query(name="ZEBRA", sql_text="SELECT 1")
    db.create_sql_query(name="ALPHA", sql_text="SELECT 2")
    view = QueriesView()
    assert view.inp_name.text() == "ALPHA"
    assert view.editor.text() == "SELECT 2"


def test_select_query_loads_it_into_the_workshop(qapp, test_db):
    from ui.main_window.queries_view import QueriesView

    q1 = db.create_sql_query(name="Q1", sql_text="SELECT 1", description="premiere")
    q2 = db.create_sql_query(name="Q2", sql_text="SELECT 2", description="seconde")
    view = QueriesView()
    view._select_query(q2.id)
    assert view.inp_name.text() == "Q2"
    assert view.inp_desc.text() == "seconde"
    assert view.editor.text() == "SELECT 2"
    view._select_query(q1.id)
    assert view.inp_name.text() == "Q1"


def test_search_matches_name_description_and_sql_body(qapp, test_db):
    from ui.main_window.queries_view import QueriesView

    db.create_sql_query(name="VENTES", sql_text="SELECT * FROM ventes", description="chiffre")
    db.create_sql_query(name="STOCK", sql_text="SELECT * FROM stock_telco", description="inventaire")
    view = QueriesView()

    def visible_names():
        names = []
        for i in range(view.list_widget.count()):
            item = view.list_widget.item(i)
            if not item.isHidden():
                names.append(view.list_widget.itemWidget(item).query_id)
        return names

    view.inp_search.setText("stock_telco")   # présent uniquement dans le corps SQL
    assert len(visible_names()) == 1

    view.inp_search.setText("chiffre")   # présent uniquement dans la description
    assert len(visible_names()) == 1

    view.inp_search.setText("")
    assert len(visible_names()) == 2


def test_usage_pill_reflects_pipelines_using_the_query(qapp, test_db):
    from ui.main_window.queries_view import QueriesView

    q = db.create_sql_query(name="Q", sql_text="SELECT 1")
    view = QueriesView()
    assert view.lbl_usage.text() == "Aucun pipeline"

    p = db.create_pipeline(name="p-using-q")
    db.save_steps(p.id, [{"step_type": "DB_EXTRACT", "config": {"sql_query_id": q.id}}])
    view.refresh()
    assert view.lbl_usage.text() == "1 pipeline(s)"


def test_new_query_creates_a_row_and_selects_it(qapp, test_db):
    from ui.main_window.queries_view import QueriesView

    view = QueriesView()
    view._on_new_query()
    assert view.list_widget.count() == 1
    assert view._active_id is not None
    assert view.inp_name.text().startswith("NOUVELLE_REQUETE")


def test_new_query_disambiguates_name_on_repeated_creation(qapp, test_db):
    from ui.main_window.queries_view import QueriesView

    view = QueriesView()
    view._on_new_query()
    view._on_new_query()
    names = {q.name for q in db.get_sql_queries()}
    assert "NOUVELLE_REQUETE" in names
    assert "NOUVELLE_REQUETE_2" in names


def test_duplicate_creates_a_second_query_and_selects_it(qapp, test_db):
    from ui.main_window.queries_view import QueriesView

    q = db.create_sql_query(name="ORIGINAL", sql_text="SELECT 1")
    view = QueriesView()
    view._select_query(q.id)
    view._on_duplicate_query()
    assert view.list_widget.count() == 2
    assert view.inp_name.text() == "ORIGINAL (copie)"
    assert view._active_id != q.id


def test_delete_without_usage_prompts_and_removes(qapp, test_db, monkeypatch):
    from ui.main_window.queries_view import QueriesView
    from PySide6.QtWidgets import QMessageBox

    q = db.create_sql_query(name="Q", sql_text="SELECT 1")
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **kw: QMessageBox.Yes)
    view = QueriesView()
    view._on_delete_query(q.id)
    assert db.get_sql_queries() == []
    assert view.list_widget.count() == 0
    assert not view._empty_label.isHidden()


def test_delete_declined_keeps_the_query(qapp, test_db, monkeypatch):
    from ui.main_window.queries_view import QueriesView
    from PySide6.QtWidgets import QMessageBox

    q = db.create_sql_query(name="Q", sql_text="SELECT 1")
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **kw: QMessageBox.No)
    view = QueriesView()
    view._on_delete_query(q.id)
    assert len(db.get_sql_queries()) == 1


def test_delete_warns_when_used_by_pipelines(qapp, test_db, monkeypatch):
    from ui.main_window.queries_view import QueriesView
    from PySide6.QtWidgets import QMessageBox

    q = db.create_sql_query(name="Q", sql_text="SELECT 1")
    p = db.create_pipeline(name="p-using-q")
    db.save_steps(p.id, [{"step_type": "DB_EXTRACT", "config": {"sql_query_id": q.id}}])

    captured = {}
    def fake_question(_self, _title, msg, *_a, **_kw):
        captured["msg"] = msg
        return QMessageBox.Yes
    monkeypatch.setattr(QMessageBox, "question", fake_question)

    view = QueriesView()
    view._on_delete_query(q.id)
    assert "p-using-q" in captured["msg"]
    assert db.get_sql_queries() == []


def test_save_persists_name_description_sql_and_profile(qapp, test_db):
    from ui.main_window.queries_view import QueriesView

    profile = db.create_oracle_profile(name="ORA1", host="h", port=1521, username="u",
                                       password="p", service_name="S")
    q = db.create_sql_query(name="Q", sql_text="SELECT 1")
    view = QueriesView()
    view._select_query(q.id)
    view.inp_name.setText("RENOMMEE")
    view.inp_desc.setText("nouvelle description")
    view.editor.set_text("SELECT 2 FROM dual")
    idx = view.cb_oracle.findData(profile.id)
    view.cb_oracle.setCurrentIndex(idx)
    view._on_save_query()

    reloaded = db.get_sql_query(q.id)
    assert reloaded.name == "RENOMMEE"
    assert reloaded.description == "nouvelle description"
    assert reloaded.sql_text == "SELECT 2 FROM dual"
    assert reloaded.oracle_profile_id == profile.id


def test_save_rejects_empty_name(qapp, test_db, monkeypatch):
    from ui.main_window.queries_view import QueriesView
    from PySide6.QtWidgets import QMessageBox

    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **kw: warnings.append(a) or None)

    q = db.create_sql_query(name="Q", sql_text="SELECT 1")
    view = QueriesView()
    view._select_query(q.id)
    view.inp_name.setText("")
    view._on_save_query()

    assert warnings
    assert db.get_sql_query(q.id).name == "Q"


def test_save_rejects_empty_sql(qapp, test_db, monkeypatch):
    from ui.main_window.queries_view import QueriesView
    from PySide6.QtWidgets import QMessageBox

    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **kw: warnings.append(a) or None)

    q = db.create_sql_query(name="Q", sql_text="SELECT 1")
    view = QueriesView()
    view._select_query(q.id)
    view.editor.set_text("")
    view._on_save_query()

    assert warnings
    assert db.get_sql_query(q.id).sql_text == "SELECT 1"


def test_format_button_reformats_editor_content(qapp, test_db):
    from ui.main_window.queries_view import QueriesView

    q = db.create_sql_query(name="Q", sql_text="select a from t")
    view = QueriesView()
    view._select_query(q.id)
    view.btn_format.click()
    assert "SELECT" in view.editor.text()


def test_import_sql_loads_file_content_into_editor(qapp, test_db, monkeypatch, tmp_path):
    from ui.main_window.queries_view import QueriesView
    from PySide6.QtWidgets import QFileDialog

    sql_file = tmp_path / "imported.sql"
    sql_file.write_text("SELECT imported_column FROM imported_table", encoding="utf-8")
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a, **kw: (str(sql_file), ""))

    q = db.create_sql_query(name="Q", sql_text="SELECT 1")
    view = QueriesView()
    view._select_query(q.id)
    view._on_import_sql()
    assert view.editor.text() == "SELECT imported_column FROM imported_table"


def test_export_sql_writes_editor_content_to_file(qapp, test_db, monkeypatch, tmp_path):
    from ui.main_window.queries_view import QueriesView
    from PySide6.QtWidgets import QFileDialog

    dest = tmp_path / "exported.sql"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **kw: (str(dest), ""))

    q = db.create_sql_query(name="Q", sql_text="SELECT exported_column FROM t")
    view = QueriesView()
    view._select_query(q.id)
    view._on_export_sql()
    assert dest.read_text(encoding="utf-8") == "SELECT exported_column FROM t"


def test_list_widget_and_empty_label_share_the_same_stretch_factor(qapp, test_db):
    """Régression réelle (constatée à l'usage, diagnostiquée par rendu réel puis reproduite ici
    sous une forme légère — sans .show()/processEvents/rendu de pixels, instable en fin de suite
    complète offscreen) : list_widget était le SEUL widget de la colonne de gauche à porter
    stretch=1 dans son QVBoxLayout. Masqué (bibliothèque vide), plus aucun widget ne réclamait
    l'espace vertical restant — Qt le distribuait alors aux QLabel voisins (politique de taille
    par défaut Preferred), qui gonflaient chacun à plus de 130px de haut au lieu d'une ligne.
    Corrigé en donnant aussi stretch=1 à _empty_label : quel que soit l'état de la bibliothèque,
    le widget effectivement visible (liste OU message vide) absorbe l'espace restant, jamais les
    libellés. Ce test vérifie directement l'invariant structurel (même facteur de stretch pour
    les deux), sans avoir besoin de peindre quoi que ce soit à l'écran."""
    from ui.main_window.queries_view import QueriesView

    view = QueriesView()
    sidebar = view.list_widget.parentWidget()
    layout = sidebar.layout()
    stretch_list  = layout.stretch(layout.indexOf(view.list_widget))
    stretch_empty = layout.stretch(layout.indexOf(view._empty_label))
    assert stretch_list == stretch_empty == 1


def test_workshop_disabled_when_no_query_selected(qapp, test_db):
    from ui.main_window.queries_view import QueriesView

    view = QueriesView()
    assert not view._workshop.isEnabled()


def test_plain_labels_have_transparent_background(qapp, test_db):
    """Régression réelle (constatée à l'usage — "rectangles noirs derrière le texte" dans la
    bibliothèque) : GLOBAL_STYLE peint tout QWidget non spécifié en bg_main (règle générique
    "QWidget { background-color: ... }") — un QLabel qui ne déclare pas explicitement
    "background: transparent" peint un rectangle opaque bg_main derrière son propre texte,
    visible dès qu'il repose sur un fond différent (carte sélectionnée, panneau...). Convention
    déjà appliquée partout ailleurs dans l'appli (voir dashboard_view.py, connections_view.py...)
    — ce test balaie TOUTE la vue (bibliothèque + atelier), pour chaque libellé qui n'a PAS sa
    propre pastille colorée (le badge d'usage et lbl_usage gardent intentionnellement un fond)."""
    from PySide6.QtWidgets import QLabel
    from ui.main_window.queries_view import QueriesView

    db.create_sql_query(name="Q", sql_text="SELECT 1", description="d")
    view = QueriesView()

    for lbl in view.findChildren(QLabel):
        if "border-radius: 8px" in lbl.styleSheet() or "border-radius: 9px" in lbl.styleSheet():
            continue   # badge d'usage (carte) / lbl_usage (statut) : fond en pastille intentionnel
        assert "background: transparent" in lbl.styleSheet(), (
            f"QLabel {lbl.text()!r} : pas de fond transparent explicite"
        )


def test_containers_use_qualified_stylesheet_selectors(qapp, test_db):
    """Régression réelle (constatée à l'usage, diagnostiquée par rendu de pixels réel — voir
    CHANGELOG — puis reproduite ici sous une forme légère : rendre des pixels via .show()/.grab()
    à répétition s'est montré instable en fin de suite complète offscreen sur cette machine) : un
    style QSS BRUT SANS SÉLECTEUR posé sur un widget conteneur (ex: `"background: X;"`) coupe la
    cascade de GLOBAL_STYLE (posé au niveau QApplication) pour tous ses descendants — un
    QPushButton niché dedans perd alors silencieusement son fond accent et devient quasi invisible
    (fond sombre sur fond sombre), sans lever d'erreur. Un sélecteur QUALIFIÉ (`"#id { ... }"`) ne
    coupe pas la cascade — vérifié empiriquement par rendu de pixels avant d'écrire ce correctif.
    Ce test vérifie directement l'invariant (chaque style de conteneur est qualifié par son
    objectName), sans avoir besoin de peindre quoi que ce soit à l'écran."""
    from PySide6.QtWidgets import QWidget
    from ui.main_window.queries_view import QueriesView

    db.create_sql_query(name="Q", sql_text="SELECT 1")
    view = QueriesView()

    for object_name in ("queriesSidebar", "workshopHeader", "workshopStatus"):
        w = view.findChild(QWidget, object_name)
        assert w is not None, f"widget #{object_name} introuvable"
        assert w.styleSheet().strip(), f"#{object_name} : aucun style — objectName inutile ?"
        assert f"#{object_name}" in w.styleSheet(), (
            f"#{object_name} : style non qualifié ({w.styleSheet()!r}) — "
            "couperait la cascade de GLOBAL_STYLE pour ses descendants."
        )

    card = view.list_widget.itemWidget(view.list_widget.item(0))
    assert card.objectName() == "queryCard"
    assert "#queryCard" in card.styleSheet()

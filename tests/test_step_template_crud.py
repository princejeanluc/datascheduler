"""
DataScheduler — tests/test_step_template_crud.py
CRUD de database/db_manager.py pour StepTemplate (chantier bibliothèque d'étapes réutilisables) —
instantané figé de la configuration d'une étape, même patron que SqlQuery (database/models.py)
mais sans FK. Pas de Qt nécessaire ici.
"""

import json

from database import db_manager as db


def test_create_step_template_sets_uuid_and_timestamps(test_db):
    t = db.create_step_template(
        name="FTP partenaire A", step_type="FTP_UPLOAD",
        config={"ftp_profile_id": 1, "remote_path_tpl": "/export/"},
    )
    assert t.id is not None
    assert t.uuid
    assert t.step_type == "FTP_UPLOAD"
    assert json.loads(t.config_json) == {"ftp_profile_id": 1, "remote_path_tpl": "/export/"}
    assert t.created_at is not None
    assert t.updated_at is not None


def test_create_step_template_stores_label_when_given(test_db):
    t = db.create_step_template(name="M", step_type="DB_EXTRACT", config={},
                                 label="Extraction Oracle")
    assert t.label == "Extraction Oracle"


def test_create_step_template_label_defaults_to_none(test_db):
    t = db.create_step_template(name="M", step_type="DB_EXTRACT", config={})
    assert t.label is None


def test_get_step_templates_sorted_by_name(test_db):
    db.create_step_template(name="Zeta", step_type="DB_EXTRACT", config={})
    db.create_step_template(name="Alpha", step_type="DB_EXTRACT", config={})
    names = [t.name for t in db.get_step_templates()]
    assert names == ["Alpha", "Zeta"]


def test_get_step_template_returns_none_for_unknown_id(test_db):
    assert db.get_step_template(999999) is None


def test_get_step_template_round_trips(test_db):
    created = db.create_step_template(name="M", step_type="CONDITION",
                                       config={"expression": "rows_count > 0"})
    fetched = db.get_step_template(created.id)
    assert fetched.name == "M"
    assert json.loads(fetched.config_json) == {"expression": "rows_count > 0"}


def test_rename_step_template(test_db):
    t = db.create_step_template(name="Ancien nom", step_type="DB_EXTRACT", config={})
    renamed = db.rename_step_template(t.id, "Nouveau nom")
    assert renamed.name == "Nouveau nom"
    assert db.get_step_template(t.id).name == "Nouveau nom"


def test_rename_step_template_does_not_touch_config(test_db):
    t = db.create_step_template(name="M", step_type="DB_EXTRACT", config={"profile_id": 7})
    db.rename_step_template(t.id, "M2")
    assert json.loads(db.get_step_template(t.id).config_json) == {"profile_id": 7}


def test_rename_step_template_unknown_id_returns_none(test_db):
    assert db.rename_step_template(999999, "X") is None


def test_delete_step_template(test_db):
    t = db.create_step_template(name="M", step_type="DB_EXTRACT", config={})
    assert db.delete_step_template(t.id) is True
    assert db.get_step_template(t.id) is None


def test_delete_step_template_unknown_id_returns_false(test_db):
    assert db.delete_step_template(999999) is False


# ──────────────────────────────────────────────
#  unique_step_template_name — désambiguïsation silencieuse, jamais d'IntegrityError
# ──────────────────────────────────────────────

def test_unique_step_template_name_returns_base_when_free(test_db):
    assert db.unique_step_template_name("Mon modèle") == "Mon modèle"


def test_unique_step_template_name_disambiguates_when_taken(test_db):
    db.create_step_template(name="Mon modèle", step_type="DB_EXTRACT", config={})
    assert db.unique_step_template_name("Mon modèle") == "Mon modèle (2)"


def test_unique_step_template_name_disambiguates_multiple_collisions(test_db):
    db.create_step_template(name="M", step_type="DB_EXTRACT", config={})
    db.create_step_template(name="M (2)", step_type="DB_EXTRACT", config={})
    assert db.unique_step_template_name("M") == "M (3)"


def test_unique_step_template_name_excludes_self_on_rename(test_db):
    """Renommer un modèle en laissant son nom inchangé ne doit jamais se voir suffixé — son
    propre nom actuel ne compte pas comme une collision avec lui-même."""
    t = db.create_step_template(name="M", step_type="DB_EXTRACT", config={})
    assert db.unique_step_template_name("M", exclude_id=t.id) == "M"


def test_create_step_template_with_colliding_name_raises_without_disambiguation(test_db):
    """create_step_template() lui-même ne désambiguïse jamais — c'est à l'appelant d'utiliser
    unique_step_template_name() avant d'appeler create_step_template() (même répartition des
    responsabilités que duplicate_sql_query/create_sql_query), name étant unique=True en base."""
    import pytest
    from sqlalchemy.exc import IntegrityError

    db.create_step_template(name="M", step_type="DB_EXTRACT", config={})
    with pytest.raises(IntegrityError):
        db.create_step_template(name="M", step_type="DB_EXTRACT", config={})

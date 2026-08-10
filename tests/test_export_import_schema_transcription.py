"""
DataScheduler — tests/test_export_import_schema_transcription.py
Vérifie la chaîne de transcription entre versions de schéma (database/export_import.py) :
- garde-fou empêchant un futur bump de CURRENT_SCHEMA_VERSION sans classer explicitement le
  passage (transcripteur réel ou additif reconnu) ;
- le mécanisme lui-même (_transcribe_bundle) applique bien les transcripteurs enregistrés, dans
  l'ordre, et ne fait rien pour un passage additif (comportement actuel v1->v2, déjà couvert par
  test_v1_style_bundle_without_edges_key_still_imports côté import complet).
"""

import database.export_import as export_import_module
from database.export_import import (
    CURRENT_SCHEMA_VERSION, _TRANSCRIBERS, _ADDITIVE_VERSION_BUMPS, _transcribe_bundle,
)


def test_all_schema_version_gaps_are_accounted_for():
    """Garde-fou : si CURRENT_SCHEMA_VERSION est incrémentée sans enregistrer explicitement le
    passage (transcripteur réel dans _TRANSCRIBERS OU additif reconnu dans
    _ADDITIVE_VERSION_BUMPS), ce test échoue — plutôt que de laisser un import d'ancien bundle
    échouer confusément ou silencieusement plus tard faute de transformation oubliée."""
    for version in range(1, CURRENT_SCHEMA_VERSION):
        assert version in _TRANSCRIBERS or version in _ADDITIVE_VERSION_BUMPS, (
            f"Le passage de la version {version} à {version + 1} n'est ni un transcripteur "
            f"enregistré dans _TRANSCRIBERS ni marqué additif dans _ADDITIVE_VERSION_BUMPS — "
            f"classez-le explicitement avant de bumper CURRENT_SCHEMA_VERSION."
        )


def test_transcribe_bundle_is_noop_for_the_current_purely_additive_gap():
    bundle = {"schema_version": 1, "marker": "unchanged"}
    result = _transcribe_bundle(bundle, from_version=1)
    assert result == {"schema_version": 1, "marker": "unchanged"}


def test_transcribe_bundle_applies_a_registered_transcriber(monkeypatch):
    def _fake_v1_to_v2(bundle: dict) -> dict:
        bundle = dict(bundle)
        bundle["migrated_by"] = "fake_v1_to_v2"
        return bundle

    monkeypatch.setitem(_TRANSCRIBERS, 1, _fake_v1_to_v2)

    result = _transcribe_bundle({"schema_version": 1}, from_version=1)
    assert result["migrated_by"] == "fake_v1_to_v2"


def test_transcribe_bundle_chains_multiple_transcribers_in_order(monkeypatch):
    monkeypatch.setattr(export_import_module, "CURRENT_SCHEMA_VERSION", 4)

    calls = []
    monkeypatch.setitem(_TRANSCRIBERS, 1, lambda b: (calls.append("1->2"), b)[1])
    monkeypatch.setitem(_TRANSCRIBERS, 2, lambda b: (calls.append("2->3"), b)[1])
    monkeypatch.setitem(_TRANSCRIBERS, 3, lambda b: (calls.append("3->4"), b)[1])

    _transcribe_bundle({}, from_version=1)

    assert calls == ["1->2", "2->3", "3->4"]


def test_transcribe_bundle_skips_versions_without_a_registered_transcriber(monkeypatch):
    """Un passage additif (pas d'entrée dans _TRANSCRIBERS) est simplement sauté — le bundle
    traverse tel quel, comme aujourd'hui pour v1->v2."""
    monkeypatch.setattr(export_import_module, "CURRENT_SCHEMA_VERSION", 3)
    monkeypatch.setitem(_TRANSCRIBERS, 2, lambda b: {**b, "touched": True})
    # Rien enregistré pour la version 1 — doit être ignoré sans lever.

    result = _transcribe_bundle({"schema_version": 1}, from_version=1)

    assert result["touched"] is True

"""
DataScheduler — tests/test_help_content.py
Vérifie l'intégrité des rubriques de la section Aide (chantier UX "autonomie utilisateur") :
chaque rubrique a un contenu réel, les clés sont uniques (utilisées comme identifiant stable).
"""

from ui.help.content import HELP_TOPICS


def test_help_topics_not_empty():
    assert len(HELP_TOPICS) > 0


def test_every_topic_has_title_and_markdown():
    for topic in HELP_TOPICS:
        assert topic.title.strip()
        assert topic.markdown.strip()
        assert topic.icon.strip()


def test_topic_keys_are_unique():
    keys = [t.key for t in HELP_TOPICS]
    assert len(keys) == len(set(keys))


def test_topic_titles_are_unique():
    titles = [t.title for t in HELP_TOPICS]
    assert len(titles) == len(set(titles))

# Note d'impact : lot A-Aujourd'hui — alignement visuel de l'écran Aujourd'hui

## Ce que le lot change
Alignement visuel de l'écran Aujourd'hui (`ui/main_window/dashboard_view.py`, classe
`DashboardView`) sur sa maquette déjà validée (A1-A12 de `docs/refonte/ecrans/Aujourdhui.md`) :
en-tête via `make_page_header` (surtitre date/heure en français, titre « Aujourd'hui » statique,
bouton « + Nouveau pipeline »), rail restructuré en deux groupes MAINTENANT/ENSUITE avec libellé
d'étape en cours, nouvelle colonne « À traiter » avec une carte par pipeline manqué ou en échec
(remplace l'actuel bandeau unique de rattrapage), bloc santé restructuré (anneau au-dessus d'une
rangée de 4 cartes, au lieu d'une disposition côte à côte), bloc à onglets « Dernières exécutions »/
« Dépendances entre pipelines » (remplace deux sections empilées), nouveau composant partagé
panneau latéral (`ui/components/side_panel.py`) pour le détail d'une exécution en échec ou en
cours, fenêtre de rattrapage restylée en cartes, accueil « premier pipeline » reconstruit en trois
cartes + deux liens. **Aucun changement de base** (Lot B de la fiche — origine/heure prévue d'un
run, table `pipeline_run_steps`, dernière fermeture de Kulu — reste hors périmètre de ce lot A,
comme `LOTS.md` le prescrit pour tous les lots A).

Contrairement aux deux écrans précédents, aucune frame de cette maquette ne porte de pastille
« proposé » (la fiche le signale elle-même en question ouverte 1) : le partage entre ce qui est
construit ici et ce qui reste gated (Lot C, C1-C9) repose entièrement sur les tableaux explicites
de la fiche, pas sur un badge à repérer visuellement.

**Décision utilisateur** (question ouverte 6 de la fiche, sans recommandation écrite — arrêt et
question avant de coder, REGLES.md règle T8) : la place des actions groupées « Lancer tout »/
« Ignorer tout » quand plusieurs cartes MANQUÉE existent. Choisi : une mini-barre au-dessus de la
colonne « À traiter » (« N manquées · Lancer tout · Ignorer tout »), visible seulement si ≥ 2
cartes MANQUÉE.

## Fichiers touchés
| Fichier | Nature du changement |
|---|---|
| `ui/main_window/dashboard_view.py` | l'essentiel du lot (A1-A10, A12), restructuration du layout en 2 colonnes |
| `ui/components/side_panel.py` (nouveau) | `SidePanel(QWidget)` — composant FONDATIONS « Panneau latéral », premier consommateur |
| `ui/components/__init__.py` | réexporte `SidePanel` |
| `ui/main_window/widgets.py` | `StatCard` gagne `value_font_size` optionnel (rétrocompatible) |
| `ui/dialogs/missed_pipelines_dialog.py` | A11 : cartes, `_format_late` étendu aux jours, texte |
| `ui/main_window/window.py` | câblage des nouveaux signaux (nouveau pipeline, ouverture Atelier depuis Aujourd'hui, accueil) |
| `tests/test_side_panel.py` (nouveau) | tests du composant partagé |
| `tests/test_dashboard_*.py`, `tests/test_missed_*.py` | extensions pour les nouveaux éléments |

## Base de données
- Changement de schéma : aucun.
- Une base 0.45.0 s'ouvre sans erreur : sans objet, rien ne touche `database/`.
- L'ancien worker tolère le nouveau schéma : sans objet.

## Format d'export
Aucun changement.

## Heures affichées
Toutes passent par `ui/time_display.py` (lot 0b), déjà utilisé par ce fichier
(`fmt_datetime`/`fmt_datetime_local`/`fmt_time_local`) : `started_at`/`finished_at` (cartes À
traiter, panneaux latéraux), `next_run_at`/`expected_at` restent en variante non-convertissante
(déjà le fuseau réglé). Le surtitre de l'en-tête (date/heure courante) utilise un nouveau petit
formateur local en français (noms de jours/mois en dur, pas de dépendance à la locale système
dans l'exécutable packagé), basé sur l'heure courante déjà dans le fuseau réglé.

## Noms publics
`refresh()`, `navigate_to_history(str)`, `navigate_to_settings(str)`, `_onboarding_banner`
(attribut, testé par `test_onboarding_empty_states.py`), `_format_late` (importable depuis
`missed_pipelines_dialog.py`) gardent exactement leur nom et comportement — vérifiés par grep.
Nouveaux signaux ajoutés (jamais de renommage) : `new_pipeline_requested`,
`open_atelier_requested` (même signature que `PipelinesView.open_atelier_requested`), signaux de
l'accueil A12.

## Tests
- Concernés : `test_dashboard_active_pipelines_count.py`, `test_dashboard_missed_banner.py`,
  `test_dashboard_notifications.py`, `test_dashboard_run_all_confirm.py`,
  `test_history_status_filter_and_navigation.py`, `test_onboarding_empty_states.py`,
  `test_run_progress_dialog.py`, `test_pipeline_topology_dialog.py` — tous revérifiés verts avant
  le premier changement de code (74 tests, confirmé).
- Ajoutés : `tests/test_side_panel.py` (ouverture/fermeture, Échap, contenu remplaçable), et des
  extensions dans les fichiers `test_dashboard_*`/`test_missed_*` existants pour les cartes À
  traiter, la mini-barre groupée, le rail à deux groupes, les onglets, les panneaux latéraux.

## Dépendances et build
Aucune dépendance ajoutée. Aucune icône nouvelle hors `qtawesome` déjà utilisé.

## Risques et retour arrière
Risque visuel et de navigation (nouveaux signaux entre vues) — aucune donnée persistée n'est
affectée, aucun comportement de lancement/rattrapage de pipeline ne change (toute la logique
« à garder tel quel » de la fiche reste strictement identique, seule sa présentation change).
Retour arrière : revert des commits de ce lot, aucune migration à défaire.

## Questions ouvertes
1. **Reprendre depuis l'échec sans historique de reprise (question ouverte 4 de la fiche)** : la
   maquette montre « Reprendre depuis l'échec » même quand rien n'a réussi avant (pas de
   `resumable_state_json`). Aucune recommandation écrite dans la fiche sur un bouton de repli
   (« Relancer ») dans ce cas — comportement actuel conservé à l'identique (le bouton
   n'apparaît que si `get_last_resumable_run` désigne un run), rien inventé.
2. **Lien « Tout l'historique » (A7) sans filtre de statut** : à vérifier en implémentation si
   `HistoryView`/`navigate_to_history` supporte déjà un argument vide pour « tout afficher » ;
   sinon petite extension côté `HistoryView`, documentée ici si nécessaire.
3. **Points d'entrée de `PipelinesView`** (`_on_new_pipeline`, `_on_start_from_template`,
   `_on_import_pipeline`) appelés depuis `window.py` via les nouveaux signaux d'Aujourd'hui : à
   confirmer en implémentation s'ils restent appelables tels quels (convention Python, pas
   d'encapsulation stricte dans ce projet) ou si un alias public est ajouté — sans les renommer.

# Lots de la refonte

Un lot donne une branche et une PR. Chaque lot suit `REGLES.md` : note d'impact validée d'abord, captures et tests à la fin. L'ordre limite le risque : on commence par ce qui ne touche pas la base, et par un écran simple pour caler la méthode.

## Étape 0 : fondations

| Lot | Contenu | Dépend de |
|---|---|---|
| 0a | `FONDATIONS.md` sections 1 à 3 et 6 : clés de couleur ajoutées, paliers de police, module `ui/components/`, couleur des étapes par famille, script `scripts/capture_views.py` | — |
| 0b | `FONDATIONS.md` section 4 : `ui/time_display.py`, puis conversion de toutes les heures affichées (17 `strftime` dans `ui/` aujourd'hui) | — |

0b corrige un vrai défaut (heures des runs affichées en UTC). Il peut partir avant 0a.

## Étape 1 : correctifs relevés en lisant le code (décision T5)

Petits lots, chacun avec un test qui échoue avant et passe après.

| Lot | Défaut | Où |
|---|---|---|
| K1 | Supprimer un profil Oracle ne signale pas les étapes Sqoop qui l'utilisent (`oracle_profile_id`) | `connections_view.py::_on_delete_database` |
| K2 | Après « Nouvelle requête » depuis une étape, la requête sélectionnée n'est pas forcément la nouvelle (`_sql_queries[-1]` sur une liste triée par nom) | `_new_sql_query` dans les dialogues d'étape |
| K3 | `list_all_db_profiles` ne renvoie pas `last_tested_at` : impossible d'afficher l'ancienneté du test des bases | `database/db_manager.py` |
| K4 | Le champ « Dossier distant » du profil FTP n'est ni enregistré ni relu. Par défaut : retirer le champ du formulaire (l'enregistrer demanderait de changer le format d'export) | `ui/dialogs/ftp_dialog.py` |
| K5 | Interrompre un run en mode arrière-plan n'appelle pas `request_cancel_run` | `pipelines_view.py::_on_interrupt_pipeline` |
| K6 | La carte « Pipelines actifs » compte tous les pipelines (`len(pipelines)`) | `dashboard_view.py` |

## Étape 2 : alignement visuel, écran par écran (lots A)

Sans changement de base. Chaque fiche a sa section « Lot A ».

| Ordre | Lot | Pourquoi à cette place |
|---|---|---|
| 1 | A-Parametres | Écran simple, maquette déjà validée : lot pilote pour vérifier que Claude Code suit bien les règles |
| 2 | A-Ressources | Simple aussi ; teste les graphiques et les heures converties |
| 3 | A-Aujourdhui | Premier écran ouvert chaque jour |
| 4 | A-Pipelines | |
| 5 | A-Historique | |
| 6 | A-Connexions | |
| 7 | A-Requetes-SQL | |
| 8 | A-Atelier | Le plus gros ; vient quand les composants ont fait leurs preuves |

Après le lot pilote, relis la PR avec attention : les écarts qu'il révèle servent à compléter `REGLES.md` avant la suite.

## Étape 3 : données (lot D)

`DONNEES.md` D1, D2, D3 et D4 dans un seul lot, car ils touchent tous `core/pipeline.py`. Le lot inclut un test de migration sur une copie de base 0.45.0.

## Étape 4 : fonctions nouvelles (lots C)

Seulement si la décision P1 est « oui ». Ordre proposé, par valeur pour un profil data :

| Ordre | Lot | Dépend de |
|---|---|---|
| 1 | C-Historique : panneau d'un run avec ses étapes, origine, journal filtrable | D |
| 2 | C-Aujourdhui : panneaux d'exécution, Tout exécuter et rattrapage dans l'ordre des dépendances | D, P9 |
| 3 | C-Requetes-SQL : aperçu des résultats, SQL résolu, jetons | P12 |
| 4 | C-Atelier-1 : édition d'une étape dans le panneau de droite | — |
| 5 | C-Atelier-2 : panneau d'ajout, glisser, insertion sur une liaison | C-Atelier-1 |
| 6 | C-Atelier-3 : compartiment du bas (chronogramme, journal, variables, validation) | D |
| 7 | C-Palette | les écrans qu'elle ouvre |
| 8 | C-Pipelines, C-Connexions, C-Parametres, C-Ressources | selon les fiches |

Un lot C trop gros pour une PR lisible (plus de 800 lignes modifiées environ) est découpé. La note d'impact propose le découpage.

## Pas encore dans ce dossier

L'écran Aide, la configuration des 18 types d'étape, l'exécution à distance, la topologie des dépendances, les retours système et le thème clair. Leurs fiches viendront avec leurs maquettes.

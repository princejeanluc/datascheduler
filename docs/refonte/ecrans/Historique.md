# Historique

Vue : `ui/main_window/history_view.py` (et `ui/main_window/run_log_dialog.py`, `ui/dialogs/pipeline_detail_dialog.py`, `ui/main_window/widgets.py::RunFrequencyHeatmap`). Maquettes : `maquettes/png/Historique*.png`.

## Intention
L'Historique sert à répondre vite à « qu'est-ce qui a tourné, qu'est-ce qui a cassé, et pourquoi ». La refonte remplace les trois fenêtres modales actuelles (jour de la carte, log complet, journal des modifications) par une bulle, un panneau latéral et un onglet, groupe les exécutions par jour, affiche les heures dans le fuseau réglé, et prépare les données qui manquent pour lire un run passé : résultat par étape, origine du run, journal à niveaux.

## États (frames)
| Frame | Ce qu'elle montre | Déclencheur dans l'application |
|---|---|---|
| Historique | Onglet « Exécutions » : en-tête, filtres, carte de fréquence, tableau groupé par jour | Entrée Historique du rail, ou `set_status_filter` depuis les cartes du Dashboard |
| Historique-jour | Bulle ancrée à une case de la carte : exécutions de ce pipeline ce jour-là | Clic sur une case qui a au moins une exécution (`RunFrequencyHeatmap.day_clicked`) |
| Historique-run | Panneau latéral d'une exécution : résumé, erreur, étapes, journal, actions | Clic sur une ligne du tableau, sur une ligne de la bulle, ou sur une ligne de `PipelineDetailDialog` |
| Historique-pipeline | Tableau filtré sur un pipeline, avec bandeau résumé | Filtre pipeline, lien « Tout son historique » de la bulle |
| Historique-modifications | Onglet « Journal des modifications » | Onglet en haut à droite (remplace le bouton actuel) |

## À garder tel quel
Ces fonctions existent et ne se voient pas toutes sur les maquettes. Un refactor ne doit en perdre aucune.

1. Filtre de statut combiné avec la recherche libre : une ligne doit satisfaire les deux (`HistoryView._apply_filters`). Aujourd'hui le filtre compare `badge.text()` au code de statut (`SUCCESS`, `FAILED`…) : si la pastille affiche « Réussi », le code doit être porté par une donnée de la ligne, pas par le texte.
2. `HistoryView.set_status_filter(status)` reste public : `window.py::_on_dashboard_navigate_to_history` l'appelle avec `SUCCESS` ou `FAILED` après un clic sur les cartes du Dashboard (`dashboard_view.py`, signal `navigate_to_history`).
3. Signal `open_atelier_requested(int, object, bool)` et `_open_graph` : « Voir dans le graphe » n'apparaît que si le run est `FAILED` et a un `failed_step_key`, recharge le pipeline par `db.get_pipeline` (commentaire sur `DetachedInstanceError`), et ouvre l'Atelier sur l'étape fautive via `MainWindow.open_atelier`.
4. Carte de fréquence : 90 jours (`_HEATMAP_DAYS`), pipelines actifs seulement, plafond de 10 lignes par `get_most_active_pipelines(limit=_MAX_FREQUENCY_ROWS)` en une requête, plafond levé et filtre par nom en SQL pendant une recherche (`_on_search_changed`, `_refresh_frequency`), message « Aucun pipeline actif pour l'instant. ».
5. `RunFrequencyHeatmap` : infobulle propre à chaque case (`_heatmap_day_tooltip`), clic émis seulement si le jour a au moins une exécution, règle « le pire résultat du jour l'emporte » (`_heatmap_day_color_key`).
6. Détail d'un jour : `db.get_runs_for_pipeline_on_day`, aucune ouverture si le jour est vide, ouverture du log d'un run depuis la liste. `HistoryView._build_day_runs_table` est testé.
7. Log d'un run (`open_run_log_dialog(parent, run_id)`, fonction publique aussi appelée par `PipelineDetailDialog`) : rafraîchissement en direct tant que le run est `RUNNING`, à l'intervalle `AppSettings.live_log_refresh_s`, défilement collé en bas si l'utilisateur y était, arrêt au statut terminal, libellé « Étape en cours : … », message d'erreur, texte « (aucun log enregistré) ».
8. Reprise d'un run : bouton « Reprendre depuis l'échec » seulement si `resumable_state_json` est renseigné, qui lance `RunProgressDialog(pipeline_id, pname, parent, resume_from_run_id=run_id)`.
9. Journal des modifications : `db.get_audit_events(limit=200)`, nom de pipeline conservé après suppression (`AuditEvent.pipeline_name`), auteur (`actor`), message vide « Aucun événement enregistré pour l'instant. ». `HistoryView._build_audit_table` est testé.
10. État vide du tableau : « Aucune exécution enregistrée pour l'instant. ». Repli du nom sur `pipeline_id` quand le pipeline n'existe plus.
11. `refresh()` est appelé à chaque arrivée sur la vue (`_navigate`), par F5, et après chaque fin de run (`_on_scheduler_success`, `_on_scheduler_error`). Pastille « En cours » qui pulse (`_make_status_badge` et `_apply_pulse`).
12. Défilement global de la vue (`QScrollArea`) et largeurs fixes des colonnes à widget : les commentaires de `_build_ui` décrivent des bugs déjà corrigés.
13. Entrées vers la vue détail d'un pipeline : double-clic dans `pipelines_view.py::_on_row_dbl_click` et clic sur un nœud dans `pipeline_topology_dialog.py::_on_node_clicked`. Elles doivent continuer de mener quelque part tant que la question 3 n'est pas tranchée.
14. `RunHistoryDots` n'est pas utilisé par l'Historique (seulement `dashboard_view.py`). Ne le touche pas dans ces lots.

## Lot A : alignement visuel, sans changer la base
| # | Changement | Frame | Source des données (code) |
|---|---|---|---|
| A1 | En-tête : surtitre « N EXÉCUTIONS SUR 7 JOURS · N ÉCHECS », titre « Historique », onglets « Exécutions » et « Journal des modifications » à droite | toutes | sommes de `db.get_run_counts_by_day(days=7)` |
| A2 | Recherche « Pipeline, fichier, message d'erreur… » : ajoute `run.error_message` au texte cherché | Historique | `get_recent_runs` (déjà chargé) |
| A3 | Filtre de statut en boutons segmentés « Tous, Échecs, En cours, Annulés » à la place de `cb_status` | Historique | `_STATUS_FILTER_OPTIONS` (voir question 1) |
| A4 | Carte « Fréquence d'exécution » : sous-titre « 90 derniers jours · clic sur un jour pour ses exécutions », légende à 4 niveaux, repères de mois et « aujourd'hui », case `success_dim` pour une seule réussite | Historique | `get_run_counts_by_day(days=90, pipeline_id)`, `_heatmap_day_color_key` étendu |
| A5 | Tableau : colonnes Heure, Pipeline, Durée, Lignes, Statut, Fichier déposé, actions ; lignes groupées sous « AUJOURD'HUI », « HIER », puis la date | Historique | `run.started_at` via `fmt_time` (FONDATIONS §4), `duration_seconds`, `rows_exported`, `remote_path` |
| A6 | Formats : durée « 38 s », « 2 min 04 », « en cours » ; lignes « 1 204 » ; « 0 » quand la valeur est 0 et « — » quand elle est nulle | Historique | `PipelineRun` |
| A7 | Pastille de statut avec le mot français : Réussi, Échec, En cours, Annulé (aujourd'hui `CANCELLED` tombe sur `badge_idle`) | toutes | `_make_status_badge` étendu |
| A8 | Actions de ligne : icône « Reprendre depuis l'échec » si `resumable_state_json`, icône « Voir dans le graphe » aux conditions du point 3 de « À garder » ; la loupe disparaît, le clic sur la ligne ouvre le panneau | Historique | `run_log_dialog.py`, `_open_graph` |
| A9 | Bulle du jour à la place du `QDialog` : nom, date longue et nombre, une ligne par run (heure, statut · durée, première ligne de l'erreur), flèche vers le panneau | Historique-jour | `get_runs_for_pipeline_on_day`, composant Bulle |
| A10 | Panneau latéral de 560 px à la place du `QDialog` de log : surtitre « EXÉCUTION #id · STATUT », nom, « début → fin · durée », encadré d'erreur préfixé du libellé de l'étape fautive, journal en Mono, boutons « Reprendre depuis l'échec » et « Voir dans le graphe » ; ligne ouverte surlignée | Historique-run | `PipelineRun.id`, `started_at`, `finished_at`, `error_message`, `failed_step_key` + `db.get_steps`, `log_text` |
| A11 | Journal des modifications en onglet : colonnes Quand, Type, Élément, Auteur, Ce qui a changé ; types traduits et colorés (Création `success`, Suppression `danger`, Import `signal_pale`, Modification `text_main`) ; `pipeline_exported` et `pipeline_duplicated` restent affichés | Historique-modifications | `get_audit_events`, `AuditEvent.event_type`, `detail` |
| A12 | Note de bas de l'onglet modifications, texte de la maquette | Historique-modifications | aucune |
| A13 | Toutes les heures (tableau, bulle, panneau, onglet modifications, infobulle de la carte) passent par `fmt_time`, `fmt_datetime` ou `fmt_relative` | toutes | FONDATIONS §4 |

## Lot B : changements de données

> Le schéma de référence est dans `../DONNEES.md`. Si un nom ou une colonne diffère ici, c'est `DONNEES.md` qui fait foi.

Toutes les migrations s'ajoutent dans `database/db_manager.py::_migrate`, sur le modèle de `failed_step_key` (`PRAGMA table_info` puis `ALTER TABLE … ADD COLUMN`). Aucune ne touche `export_import.py` : les runs et l'audit ne sont pas exportés.

**B1. Résultat par étape.** Besoin : durée, essais, lignes et statut de chaque étape d'un run passé (section « Étapes », « 1 min 12 de travail »). Schéma : nouvelle table `pipeline_run_steps` (`id` INTEGER PK, `run_id` INTEGER NOT NULL, `step_key` VARCHAR(255), `step_label` VARCHAR(100), `step_type` VARCHAR(30), `status` VARCHAR(20), `attempts` INTEGER DEFAULT 1, `started_at` DATETIME, `finished_at` DATETIME, `rows` INTEGER NULL, `error_message` TEXT NULL), index sur `run_id`. Écriture : une fonction `db.record_run_step(...)` appelée autour de `_run_step_with_policy` dans `_execute_linear`, `_execute_graph` et `_execute_graph_parallel` (`core/pipeline.py`), `attempts` compté dans la boucle de relance, `rows` pris dans `ctx.rows_count` après l'étape. Une étape sautée par une reprise est notée `SKIPPED_RESUME`. Run d'avant la refonte : aucune ligne, la section « Étapes » est absente du panneau et le résumé n'affiche que « début → fin · durée », sans erreur. Worker : un ancien worker n'écrit pas dans la table, ses runs s'affichent comme des runs anciens ; un nouveau worker face à une ancienne interface écrit dans une table que celle-ci ignore. Suppression : `delete_pipeline` supprime les runs par cascade ORM ; il faut supprimer aussi leurs lignes d'étapes (pas de clé étrangère active).

**B2. Origine du run.** Besoin : colonne « Déclenchement » (planifié, manuel, déclenché, rattrapé) et « ↳ après X ». Schéma : `pipeline_runs.trigger_origin VARCHAR(20) NULL` et `pipeline_runs.triggered_by_run_id INTEGER NULL`. Écriture : paramètre `origin=None` ajouté à `run_pipeline` et `create_run`, et à `PipelineScheduler.trigger_now`. Valeurs : `SCHEDULED` dans `_run_scheduled_pipeline`, `MANUAL` dans `trigger_now` par défaut et `RunProgressDialog`, `TRIGGERED` dans `_trigger_downstream_pipelines` (qui doit recevoir l'id du run parent), `CATCHUP` dans `MissedPipelinesDialog._on_launch_selected`, `RESUME` quand `resume_from_run_id` est fourni. Le worker lit une clé `origin` facultative dans la charge utile de `RUN_NOW` (`core/scheduler.py`), absente chez un ancien émetteur. Run d'avant la refonte ou écrit par un ancien worker : `NULL`, affiché « — », sauf si `resumed_from_run_id` est renseigné (« reprise du #N », donnée existante). Un rattrapage fait par APScheduler lui-même (`misfire_grace_time`, `coalesce`) reste vu comme `SCHEDULED`.

**B3. Journal à niveaux.** Besoin : filtre « Erreurs », couleurs par niveau, heures convertibles (le log actuel ne garde que `[HH:MM:SS]` en UTC, sans date). Schéma : `pipeline_runs.log_json TEXT NULL`, liste de `{"t": ISO UTC, "lvl": "INFO|WARN|ERROR|OK", "step_key": …, "msg": …}`. `log_text` reste écrit à l'identique. Écriture : `PipelineResult.log(msg, level="INFO")`, `fail` en `ERROR`, la ligne « Tentative n/m » en `WARN` ; `update_run_progress` et `finish_run` reçoivent `log_json` en paramètre facultatif. Run d'avant la refonte : lecture de `log_text` ligne à ligne, niveau `ERROR` si la ligne contient « ERREUR : », sinon `INFO`, heure recomposée avec la date de `started_at` (avec passage de minuit). Le filtre « Erreurs » fonctionne donc aussi sur ces runs, de façon approximative. Worker : un ancien worker n'écrit que `log_text`, même repli.

**B4. Période et pagination.** Besoin : « 24 h, 7 j, 30 j, 90 j, Période… » et « charger les suivantes » (aujourd'hui 100 runs au plus, `get_recent_runs`). Proposition : `db.get_runs_page(since, until, pipeline_id=None, status=None, offset=0, limit=100)` et `db.count_runs(...)`, plus `CREATE INDEX IF NOT EXISTS ix_pipeline_runs_started_at`. `get_recent_runs` reste inchangé pour ses autres appelants. Aucun impact worker.

**B5. Habitude d'un pipeline.** Besoin : médiane de durée et de lignes, réussites sur 30 jours, courbes des 30 derniers runs. Proposition : `db.get_pipeline_run_stats(pipeline_ids, last_n=30)` en une requête, médiane calculée en Python sur les runs `SUCCESS`. Pas de schéma.

**B6. Journal des modifications étendu.** Besoin : connexions, requêtes, désactivation, détail des réglages. Schéma : `audit_events.object_type VARCHAR(20) NULL`, `object_id INTEGER NULL`, `object_name VARCHAR(100) NULL` ; `log_audit_event` reçoit ces paramètres en option. Une ligne ancienne (`object_type` NULL) est lue comme un pipeline. Écriture ajoutée dans `set_pipeline_active`, dans les fonctions d'enregistrement des connexions et des requêtes, et un diff champ par champ dans `update_pipeline` à la place de « Nom/description/planification ». L'ancien worker n'écrit pas d'audit, rien à tolérer de plus.

**B7. Jours dans le fuseau réglé.** `get_run_counts_by_day` et `get_runs_for_pipeline_on_day` découpent les jours en UTC (`strftime` SQLite sur `started_at`). Ajoute un paramètre facultatif de fuseau qui calcule les bornes locales puis les convertit en UTC ; sans paramètre, le comportement actuel reste celui du Dashboard. Sans B7, un run à 00:30 heure de Paris tombe sur la case de la veille.

## Lot C : fonctions nouvelles (« proposé »)
| # | Fonction | Frame | Dépend de |
|---|---|---|---|
| C1 | Sélecteur de période 24 h, 7 j, 30 j, 90 j, Période… (pastille) | Historique, -pipeline | B4 |
| C2 | Pied « N exécutions sur 7 jours · charger les suivantes » (sans pastille, absent du code) | Historique, -pipeline | B4 |
| C3 | Colonne « Déclenchement » et mot d'origine dans le surtitre du panneau (pastille) | Historique, -run | B2 |
| C4 | Section « Étapes » du panneau, avec barres et « non exécutée » ; « de travail, le reste en attente de réessai » (pastille) | Historique-run | B1 |
| C5 | Filtre « Tout / Erreurs » et couleurs par niveau dans le journal (sans pastille, absent du code) | Historique-run | B3 |
| C6 | Recherche dans le journal et bouton « Copier » (sans pastille, absents du code) | Historique-run | aucune |
| C7 | Bouton « Exporter le journal » vers un fichier texte (sans pastille, absent du code) | Historique-run | aucune |
| C8 | Filtre « Tous les pipelines ▾ », puce « Pipeline : X × » (sans pastille, absent du code) | Historique, -pipeline | aucune (`db.get_pipelines`) |
| C9 | Bandeau résumé d'un pipeline : planification, « déclenche … », « Ouvrir dans l'Atelier », 3 cartes de chiffres, courbes durée et lignes (sans pastille, proposition dans `manquements.md`) | Historique-pipeline | B5, C8, `get_pipelines_triggered_by` |
| C10 | Colonne « Durée · vs habitude » : barre, trait pointillé à la médiane, ambre au-delà de 1,5 fois, note de pied (sans pastille, proposition dans `manquements.md`) | Historique, -pipeline | B5 |
| C11 | Liens de la bulle « Ce pipeline, ce jour-là » et « Tout son historique → » | Historique-jour | C8, C1 |
| C12 | Recherche « Nom, détail… » de l'onglet modifications (sans pastille, absente du code) | Historique-modifications | aucune |
| C13 | Catégories Tout, Pipelines, Connexions, Requêtes, Imports (pastille) | Historique-modifications | B6 |
| C14 | Lignes de modification de connexion, de requête, de désactivation et de réglage détaillé (pastilles) | Historique-modifications | B6 |

## Hors périmètre
Les messages du journal ne changent pas : la maquette écrit « Réessai 1/2 dans 30 s » là où `_run_step_with_policy` écrit « Tentative 1/2 après échec : … ». Le nombre de lignes en direct d'un run en cours (« 1 204 » sur la ligne « en cours ») n'est pas fourni : `rows_exported` n'est écrit qu'à la fin. Le plafond de 10 lignes de la carte de fréquence reste. `RunHistoryDots` et le Dashboard ne bougent pas. Les données des maquettes (noms, chiffres, chemins) sont des exemples.

## Critères d'acceptation
- [ ] Capture « Historique » à 1440×900 avec un jeu de runs couvrant aujourd'hui, hier et un jour antérieur : trois groupes de jours, pastilles en français, aucune colonne C.
- [ ] Test : un run démarré à 05:00 UTC un jour d'été s'affiche 07:00 avec `Europe/Paris`, dans le tableau, la bulle, le panneau et l'onglet modifications.
- [ ] Test : le surtitre compte les runs et les échecs des 7 derniers jours.
- [ ] Les tests existants `test_history_status_filter_and_navigation.py`, `test_history_audit_log.py`, `test_history_view_graph_link.py`, `test_run_log_dialog.py`, `test_pipeline_detail_dialog.py`, `test_pipelines_view_detail.py`, `test_pipeline_topology_dialog.py`, `test_activity_stats.py` et `test_db_manager.py` passent sans être assouplis (voir question 6).
- [ ] Test : filtre « Échecs » plus une recherche ne laissent que les échecs qui contiennent le texte ; une recherche sur un extrait de `error_message` trouve le run.
- [ ] Test : `set_status_filter("FAILED")` appelé par la navigation depuis le Dashboard active le bon segment.
- [ ] Test : la recherche lève le plafond de la carte et révèle un pipeline peu actif.
- [ ] Test : une case avec une seule réussite prend `success_dim`, plusieurs `success`, un échec `danger`.
- [ ] Capture « Historique-jour » : la bulle s'ouvre sur le clic d'une case pleine, ne s'ouvre pas sur une case vide, se ferme par Échap ou clic extérieur.
- [ ] Capture « Historique-run » sur un échec avec `resumable_state_json` et `failed_step_key` : les deux boutons sont présents ; sur un succès, aucun des deux.
- [ ] Test : un run `RUNNING` ouvert dans le panneau se met à jour à l'intervalle `live_log_refresh_s` et cesse au statut terminal.
- [ ] Test : « Reprendre depuis l'échec » ouvre `RunProgressDialog` avec `resume_from_run_id` égal à l'id du run.
- [ ] Test : « Voir dans le graphe » émet `open_atelier_requested(pipeline_id, failed_step_key, False)`.
- [ ] Capture « Historique-modifications » : types en français et colorés, export et duplication visibles.
- [ ] B1 : test qu'un run de 3 étapes écrit 3 lignes avec essais et durée ; test qu'un run sans lignes affiche le panneau sans section « Étapes » ni erreur.
- [ ] B2 : test d'une valeur par origine (planifié, manuel, déclenché avec `triggered_by_run_id`, rattrapé, reprise) ; test qu'un run à `NULL` affiche « — ».
- [ ] B3 : test du filtre « Erreurs » sur `log_json`, et sur un `log_text` ancien contenant « ERREUR : ».
- [ ] B1, B2, B3, B6 : test qu'une base 0.45.0 s'ouvre, migre et que l'ancien code ORM lit et écrit un run dans la base migrée.
- [ ] B4 : « charger les suivantes » ajoute la page suivante sans doublon ; test du compte par période.
- [ ] B7 : test qu'un run à 22:30 UTC en été tombe sur la case du lendemain à Paris.
- [ ] C9 : capture « Historique-pipeline » ; « Ouvrir dans l'Atelier » émet `open_atelier_requested(id, None, False)`.
- [ ] C10 : test qu'un run à 1,6 fois la médiane passe en `warning`, et qu'un pipeline sans run réussi n'affiche pas de trait.

## Questions ouvertes
1. Le filtre de la maquette n'a pas de segment « Réussis », alors que le Dashboard ouvre l'Historique filtré sur `SUCCESS` (`dashboard_view.py`, carte des réussites). Ajouter « Réussis », ou que doit faire ce clic ?
2. Plusieurs éléments sans pastille n'existent pas dans le code : filtre pipeline, bandeau du pipeline, durée comparée à l'habitude, recherche, « Copier » et « Exporter » du journal, filtre « Erreurs », recherche des modifications, pied de pagination. Ils sont classés en C. Confirmer qu'ils entrent dans ce lot.
3. Le bandeau de pipeline remplace `PipelineDetailDialog` d'après `manquements.md`. Les deux entrées actuelles (Pipelines, topologie) doivent-elles ouvrir l'Historique filtré ? Le bandeau perd la description, le statut actuel et « Déclenché après X » que montre le dialogue : à garder ?
4. La ligne « Suppression · 4 exécutions conservées » contredit le code : `Pipeline.runs` est en `cascade="all, delete-orphan"`, la suppression efface les runs. Changer ce comportement sort du Lot A ; faut-il le faire ?
5. Les textes de « Création », « Import » et « Modification » de la maquette ne correspondent pas à ce que le code écrit (`detail` vide à la création, « action=… » à l'import, « +1 étape(s) (…) · +1 arête(s) (éditeur graphique) »). Reformuler à l'affichage, changer l'écriture (B6), ou garder le texte stocké ?
6. Les tests lisent `view.table.item(r, 0)` comme nom de pipeline, comptent une ligne par run et cherchent les actions en colonne 6. La maquette met l'heure en premier et des lignes de jour dans le tableau. Garder ces indices (en-têtes de jour hors du `QTableWidget`) ou adapter les tests dans la note d'impact ?
7. « 29/30 réussites sur 30 jours » : réussites sur nombre de runs, ou jours réussis sur 30 ?
8. Clic simple ou double-clic pour ouvrir le panneau ? Aujourd'hui c'est le double-clic, et la loupe disparaît de la maquette.
9. B7 change aussi le graphique du Dashboard si le paramètre devient le défaut. Le faire dans ce lot ou laisser le Dashboard en UTC ?
10. « Voir dans le graphe » depuis le panneau mène à l'Atelier, dont la sortie ramène à Pipelines et non à l'Historique (`_open_graph`, CHANGELOG). Garder ?

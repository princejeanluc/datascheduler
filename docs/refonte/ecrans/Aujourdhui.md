# Aujourd'hui

Vue : `ui/main_window/dashboard_view.py` (classe `DashboardView`, indice 0 de `window.py`), avec `widgets.py`, `activity_chart.py`, `ui/dialogs/missed_pipelines_dialog.py`, `run_progress_dialog.py`, `pipeline_topology_dialog.py` et `core/missed_runs.py`. Maquettes : `maquettes/png/Aujourdhui*.png`.

## Intention
Le profil data ouvre Kulu le matin pour savoir ce qui a échoué, ce qui a été manqué et ce qui va tourner. Aujourd'hui l'écran empile des blocs de même poids (bandeau, rail, santé, topologie, tableau). La refonte met en tête une liste « À traiter » triée par urgence, garde la santé et les dernières exécutions, et ouvre le détail d'une exécution dans un panneau latéral au lieu de renvoyer vers l'Historique.

## États (frames)
| Frame | Ce qu'elle montre | Déclencheur dans l'application |
|---|---|---|
| Aujourdhui | En-tête, rail Maintenant/Ensuite, À traiter, santé, ligne du temps, dernières exécutions | Ouverture de l'application ou clic sur l'entrée 0 de la barre de navigation |
| Aujourdhui-execution | Panneau latéral d'une exécution en échec | « Détails » d'une carte ÉCHEC, ou clic sur une ligne du tableau ou une marque de la ligne du temps |
| Aujourdhui-encours | Panneau latéral d'une exécution en cours | Clic sur la pastille MAINTENANT ou sur une marque « en cours » |
| Aujourdhui-tout | Fenêtre flottante de confirmation de « Tout exécuter » | Bouton « Tout exécuter » (`_on_run_all`) |
| Aujourdhui-rattrapage | Fenêtre de rattrapage au démarrage | `window.py::_show_missed_pipelines_dialog` quand `get_pending()` n'est pas vide |
| Aujourdhui-premier | Trois pas d'accueil et ligne du temps vide | `db.get_pipelines()` vide (condition actuelle de `_onboarding_banner`) |

## À garder tel quel
- Rafraîchissement périodique (`QTimer`, `AppSettings.dashboard_refresh_s`) et F5 (`window.py::_refresh_current_view` appelle `refresh()`). Le nom `refresh()` reste public.
- Les signaux `navigate_to_history(str)` et `navigate_to_settings(str)` et leurs branchements dans `window.py`. Les cartes Succès et Échecs restent cliquables et ouvrent l'Historique filtré sur `SUCCESS` ou `FAILED`.
- Le bouton cloche ouvre Paramètres sur la catégorie `notifications` (`_on_notifications`).
- « Tout exécuter » : message « Aucun pipeline actif à lancer. » sans pipeline actif, avertissement « Le scheduler n'est pas encore démarré. » sur `RuntimeError` (cas du mode arrière-plan), confirmation avant tout lancement, lancement par `get_scheduler().trigger_now`.
- Rattrapage : détection uniquement en mode IN_APP et avant `init_scheduler()` (`main.py`), tolérance `misfire_grace_time_min`. Décocher ou « Plus tard » ne résout rien. Un pipeline reste en attente jusqu'à « Lancer » ou « Ignorer » explicite (`core/missed_runs.py::resolve`), jamais un simple masquage. Le lancement résout même sans scheduler (test `test_launch_actions_work_without_an_initialized_scheduler`). « Lancer tout », « Ignorer tout » et la croix (même effet qu'« Ignorer tout ») restent disponibles quand il y a plusieurs pipelines manqués (voir Questions). `_format_late` reste importable depuis `missed_pipelines_dialog.py`.
- Rail : pastille en cours animée (`_apply_pulse`), trois prochaines exécutions au plus, texte « Aucune exécution en cours ni planifiée pour l'instant. » quand il n'y a rien. Hauteur fixe des pastilles (commentaire de `_make_rail_chip`).
- Santé : l'anneau ne compte que les pipelines actifs dont le dernier statut est SUCCESS ou FAILED (`HealthRingWidget`, `_ring_arcs`). La ligne « N jamais exécuté(s) » reste quand N > 0.
- Tableau : une ligne par pipeline à partir des 100 derniers runs, pastilles des 8 derniers statuts (`RunHistoryDots`), nom en rouge gras avec `error_message` en infobulle sur un échec (test `test_failed_run_pipeline_name_is_highlighted`), état vide « Aucune exécution pour l'instant… ».
- Dépendances : aperçu plafonné à 6 chaînes (`_cap_topology_preview`, testée), lien « Voir tous les pipelines (N) → » qui ouvre `PipelineTopologyDialog` (recherche, filtre de statut, zoom molette, clic qui ouvre `PipelineDetailDialog`).
- `RunProgressDialog` : « Fermer » ne stoppe pas le run, référence forte `_background_runs`, `wait()` dans `_on_finished`, « Arrêter » coopératif avec son message, « Reprendre depuis l'échec » seulement si `get_last_resumable_run` désigne ce run, libellé des étapes parallèles (`_poll_active_steps`). Ses commentaires décrivent des crashs réels.
- Le défilement global de la vue (`QScrollArea`, commentaire en tête de `_build_ui`).
- `ActivityChartWidget` n'est plus sur cet écran mais reste utilisé par `PipelineDetailDialog`. Ne le supprime pas.
- L'attribut `_onboarding_banner` garde ce nom et porte le bloc d'accueil (tests `test_onboarding_empty_states.py`).

## Lot A : alignement visuel, sans changer la base
Un élément est en lot A quand la fonction ou la donnée existe déjà, même si on l'appelle depuis un nouvel endroit.

| # | Changement | Frame | Source des données (code) |
|---|---|---|---|
| A1 | En-tête : surtitre date et heure, titre (« Aujourd'hui » tant que C1 n'est pas livré), cloche, « Tout exécuter » en bouton secondaire, « + Nouveau pipeline » en bouton principal | Aujourdhui | `_on_notifications`, `_on_run_all` ; création via un nouveau signal vers `PipelinesView._on_new_pipeline` |
| A2 | Rail en deux groupes MAINTENANT et ENSUITE, pastille en cours « étape 2/4 · 00:42 », pastilles à venir « nom HH:MM » | Aujourdhui | `_refresh_rail`, `is_pipeline_running`, `db.get_running_step_labels()` (libellé « Étape i/n : … ») |
| A3 | Colonne « À traiter » : carte MANQUÉE par pipeline en attente, avec « Lancer maintenant » et « Ignorer » | Aujourdhui | `get_pending()`, `_on_missed_launch_one`, `resolve(pid)`, `_format_late` |
| A4 | Carte ÉCHEC par pipeline actif dont le dernier statut est FAILED : heure, étape fautive, nombre de réessais, erreur en Mono, « Reprendre depuis l'échec » si reprenable, « Détails » | Aujourdhui | `db.get_runs(pid, 1)`, `failed_step_key` relié à `PipelineStep.retry_count` et au libellé, `error_message`, `get_last_resumable_run`, `RunProgressDialog(resume_from_run_id=…)` |
| A5 | Bloc santé recomposé : anneau, légende, quatre petites cartes (valeur en Mono 22 px, durée au format « 3:08 ») | Aujourdhui | `HealthRingWidget`, `StatCard` étendu sans changer sa signature |
| A6 | Carte « actifs » qui compte `p.is_active` au lieu de tous les pipelines | Aujourdhui | `refresh()` ; voir Questions |
| A7 | Bloc à onglets « Dernières exécutions » et « Dépendances entre pipelines », lien « Tout l'historique → » | Aujourdhui | tableau actuel, `PipelineTopologyWidget`, `_on_open_topology_dialog`, `navigate_to_history` |
| A8 | Tableau : colonnes Pipeline, 8 dernières, Lignes, Durée (« 2 min 04 », « 38 s »), Date (« aujourd'hui 11:28 »), Fichier déposé en Mono | Aujourdhui | `get_recent_runs(100)`, `rows_exported`, `duration_seconds`, `remote_path` |
| A9 | Panneau latéral (composant FONDATIONS) pour une exécution en échec : surtitre « EXÉCUTION #id · ÉCHEC », partie et arrêtée à, durée, 8 dernières, erreur, pieds « Reprendre depuis l'échec », « Ouvrir dans l'Atelier », « Journal » | Aujourdhui-execution | `db.get_run`, `RunHistoryDots`, `window.open_atelier(pid, highlight_step_key=failed_step_key)` via un nouveau signal, `open_run_log_dialog` |
| A10 | Panneau latéral d'une exécution en cours : départ, barre de progression, étape courante, journal en direct qui suit la fin, « Arrêter », « Ouvrir dans l'Atelier » | Aujourdhui-encours | `current_step_label`, `log_text` relus comme `run_log_dialog._refresh_live`, `request_cancel` ou `execution_mode.request_cancel_run` selon le mode |
| A11 | Fenêtre de rattrapage restylée : textes de la maquette, « prévue samedi 07:00 », retard en jours (« 1 j 2 h ») | Aujourdhui-rattrapage | `MissedPipelinesDialog`, `_format_late` étendu aux jours |
| A12 | Accueil en trois cartes et deux liens : « Créer une connexion », « Ouvrir l'éditeur SQL », « Partir du modèle », « Importer un fichier .dspipeline », « Lire le guide pas à pas » | Aujourdhui-premier | navigation vers les vues 2, 3 et 7 ; `PipelinesView._on_start_from_template` et `_on_import_pipeline` via de nouveaux signaux |

**Heures (FONDATIONS section 4).** Toutes passent par le module de conversion du lot 0 :
- Converties par `to_display` / `fmt_time` / `fmt_relative` : `PipelineRun.started_at` et `finished_at` (tableau, cartes ÉCHEC, panneaux, ligne du temps), les préfixes `[HH:MM:SS]` du `log_text` (écrits en UTC par `PipelineResult.log`), et `last_closed_at` du lot B.
- Variante sans conversion : `Pipeline.next_run_at` (pastilles ENSUITE, ligne du temps future) et `expected_at` des pipelines manqués (copie de `next_run_at`).
- Sans conversion car ce sont des durées : écoulé d'un run en cours, durées, retard.
- Le surtitre (« DIMANCHE 18 OCTOBRE · 14:05 ») est l'heure courante dans le fuseau réglé, en français.

## Lot B : changements de données

> Le schéma de référence est dans `../DONNEES.md`. Si un nom ou une colonne diffère ici, c'est `DONNEES.md` qui fait foi.

- **B1. Origine et heure prévue d'un run.** Besoin : « relance manuelle 11:28 » et « Planifiée à 07:00, partie à 07:00:04 ». Schéma : `pipeline_runs.trigger_origin VARCHAR(20) NULL` (`SCHEDULED`, `MANUAL`, `TRIGGERED`, `CATCHUP`, `RESUME`) et `pipeline_runs.scheduled_for DATETIME NULL` en UTC, écrits par `core/scheduler.py` et `run_pipeline`. Worker : une ancienne version n'écrit rien, l'interface affiche alors l'heure de départ seule. Export : les runs ne sont pas exportés, aucun impact.
- **B2. Parcours par étape.** Besoin : statut, tentatives et durée de chaque étape (« 3 tentatives, 30 s d'attente », « non exécutée », « Variables · 0,2 s »). Schéma : nouvelle table `pipeline_run_steps` (`id`, `run_id`, `step_key`, `label`, `status`, `attempts`, `started_at`, `finished_at`, `message`), écrite par `_execute_linear`, `_execute_graph` et `_execute_graph_parallel`. Worker : une ancienne version n'y écrit pas, le panneau retombe sur `failed_step_key`, `current_step_key` et `resumable_state_json`. Export : aucun impact.
- **B3. Dernière fermeture de Kulu.** Besoin : « Kulu était fermé entre vendredi 19:12 et ce matin 08:47 ». Schéma : `app_settings.last_closed_at DATETIME NULL` en UTC, écrit à la sortie de `run()` dans `main.py`. Après un crash la valeur est ancienne : la phrase s'affiche alors sans heure de fermeture. Worker et export : aucun impact.

## Lot C : fonctions nouvelles (« proposé »)
| # | Fonction | Frame | Dépend de |
|---|---|---|---|
| C1 | Titre dynamique « N points demandent ton attention » (nombre de cartes À traiter) | Aujourdhui | A3, A4, C3 |
| C2 | Ce que l'échec bloque : « Bloque aussi : … », « 1 bloqué derrière », bloc CONSÉQUENCES | Aujourdhui, -execution | `get_pipelines_triggered_by` avec condition SUCCESS |
| C3 | Connexion jamais testée : carte CONNEXION « Utilisé par N pipelines », mention dans ENSUITE et dans « Tout exécuter », « Tester maintenant » | Aujourdhui, -tout | nouvelle fonction profil vers pipelines (`_STEP_REFERENCES`), `last_tested_at` |
| C4 | Ligne du temps « La journée des pipelines » (6 h, 24 h, 7 j) : runs passés, en cours, manqués, occurrences futures, repère de l'heure, clic qui ouvre le panneau, double-clic qui ouvre l'Atelier, légende | Aujourdhui, -premier | calcul des occurrences futures dans `core/scheduler.py` ; B1 pour « relance manuelle » |
| C5 | « Tout exécuter » en fenêtre flottante à cases, durée estimée, ordre des dépendances, déjà en cours ignoré | Aujourdhui-tout | moyenne des `duration_seconds`, C2, C3 |
| C6 | Rattrapage dans l'ordre des dépendances, « Lancée en premier », « Suivra automatiquement… », période de fermeture | Aujourdhui-rattrapage | C2, B3 |
| C7 | Panneau d'échec enrichi : PARCOURS, « 1er échec depuis 9 jours », hôte et port, explication de l'erreur, « fonctionnait encore hier », « Tester la connexion », phrase sur ce que la reprise rejoue | Aujourdhui-execution | B1, B2, `_test_reference_connection` |
| C8 | Durée habituelle et fin estimée d'un run en cours, PARCOURS avec durées | Aujourdhui-encours | moyenne des runs réussis, B2 |
| C9 | Accueil : la première étape non faite est mise en avant | Aujourdhui-premier | existence d'un profil, d'une requête |

## Hors périmètre
- Le champ « Aller à, exécuter… Ctrl K » relève de la fiche Palette. Ne laisse pas de place vide.
- La pastille orange de la cloche (notifications non lues) : aucun centre de notifications n'existe.
- Le renommage de l'entrée « Dashboard » de la barre de navigation (fiche Main).
- Le rail et la détection des manqués en mode arrière-plan (`is_pipeline_running` ne voit que le processus courant) : à noter dans la PR, sans correction ici.
- Les jours de `get_run_counts_by_day` groupés en UTC (graphique de `PipelineDetailDialog`).

## Critères d'acceptation
- [ ] Capture Aujourdhui : avec un échec, un manqué et des runs du jour, l'écran montre l'en-tête, le rail, À traiter, la santé et le bloc à onglets, sans élément « proposé » non livré ni place vide.
- [ ] Un run démarré à 05:00 UTC s'affiche 07:00 dans le tableau avec `Europe/Paris` en été ; un `next_run_at` à 07:00 s'affiche 07:00 dans ENSUITE.
- [ ] Carte MANQUÉE : « Lancer maintenant » appelle `trigger_now` puis `resolve` ; « Ignorer » appelle `resolve` sans lancer ; la carte disparaît au `refresh()` suivant et ne revient pas.
- [ ] Carte ÉCHEC : « Reprendre depuis l'échec » n'apparaît que si `get_last_resumable_run` renvoie un run, et ouvre `RunProgressDialog` avec ce `resume_from_run_id`.
- [ ] Capture Aujourdhui-execution : « Détails » ouvre le panneau, Échap le ferme, « Ouvrir dans l'Atelier » émet l'ouverture avec `failed_step_key`.
- [ ] Capture Aujourdhui-encours : le journal se met à jour à l'intervalle `live_log_refresh_s` et reste en bas ; « Arrêter » appelle `request_cancel` (IN_APP) ou `request_cancel_run` (arrière-plan).
- [ ] Capture Aujourdhui-tout ; tests `test_dashboard_run_all_confirm.py` verts (adaptés seulement si la question 2 est tranchée en ce sens).
- [ ] Capture Aujourdhui-rattrapage ; décocher puis « Lancer la sélection » laisse le pipeline décoché dans À traiter ; « Plus tard » laisse tout en attente ; bouton désactivé à 0 sélection.
- [ ] Capture Aujourdhui-premier sans pipeline ; chaque bouton mène à sa vue ou à sa fonction ; `_onboarding_banner` caché dès qu'un pipeline existe.
- [ ] Les cartes Succès et Échecs ouvrent l'Historique filtré ; la cloche ouvre Paramètres sur Notifications ; « Voir tous les pipelines » ouvre la vue globale.
- [ ] Fermer `RunProgressDialog` pendant un run ne l'arrête pas (test existant vert).
- [ ] Tests existants verts : `test_dashboard_*`, `test_missed_*`, `test_run_progress_dialog`, `test_pipeline_topology_dialog`, `test_onboarding_empty_states`, `test_activity_chart`.

## Questions ouvertes
1. Aucune frame de cet écran ne porte de pastille « proposé », alors que les éléments C1 à C9 et les panneaux n'existent pas dans le code. Confirme qu'ils sont bien à livrer, et dans quel lot.
2. « Tout exécuter » passe d'un `QMessageBox.question` à une fenêtre à cases. Les tests de `test_dashboard_run_all_confirm.py` simulent `QMessageBox.question` : peut-on les réécrire pour la nouvelle fenêtre ?
3. Ordre des dépendances (C5, C6) : un enfant déclenché par un parent sélectionné n'est plus lancé séparément. Aujourd'hui il est lancé deux fois (une fois direct, une fois par déclenchement). Ce changement de comportement est-il voulu ?
4. La maquette propose « Reprendre depuis l'échec » alors que « rien n'a réussi avant ». Dans le code, `resumable_state_json` n'est écrit que si une étape a réussi : sans cela il n'y a pas de reprise. Faut-il afficher « Relancer » dans ce cas ?
5. ~~La carte « actifs » compte aujourd'hui tous les pipelines (`len(pipelines)`) sous le libellé « Pipelines actifs ».~~ Corrigé hors Lot A, en correctif K6 (`docs/refonte/LOTS.md`) : la carte ne compte plus que les pipelines actifs.
6. Le bandeau des manqués disparaît au profit des cartes MANQUÉE. Où placer « Lancer tout » et « Ignorer tout » quand il y en a plusieurs ?
7. Titre de la page quand rien n'est à traiter : « Aujourd'hui », ou une phrase du type « Rien ne demande ton attention » ?
8. Les heures du journal sont écrites en UTC dans `log_text`. On convertit le préfixe à l'affichage (proposé ici), ou on change l'écriture (hors règle) ?
9. Le panneau « en cours » remplace-t-il `RunProgressDialog` quand on lance depuis Pipelines, ou les deux coexistent-ils (proposé ici : ils coexistent) ?

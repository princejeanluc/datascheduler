# Manquements et propositions qui demandent du code

Ce fichier suit, écran par écran, ce que les maquettes montrent mais que le code de Kulu ne fait pas encore. Il distingue deux cas :

- **Manquement** : un défaut constaté en lisant le code (une incohérence, une information cachée, une fonction absente alors qu'elle est attendue).
- **Proposition** : une idée de conception nouvelle, marquée « proposé » sur les frames.

Chaque ligne indique où regarder dans le code. Version lue : 0.45.0.

## Atelier

| Type | Sujet | Détail | Où |
|---|---|---|---|
| Proposition | Brouillon et publication | Bouton Publier : séparer la version en cours d'édition de celle qui tourne | nouveau |
| Proposition | Exécuter jusqu'ici | Lancer le pipeline jusqu'à l'étape sélectionnée | `core/pipeline.py::run_pipeline` |
| Proposition | Paramètres en phrase | Déclenchement écrit « Lancer aussi après X si elle réussit » | `ui/step_editor/pipeline_settings_panel.py` |

## Aujourd'hui

| Type | Sujet | Détail | Où |
|---|---|---|---|
| Proposition | Ordre de lancement | Rattrapage et Tout exécuter lancent dans l'ordre des dépendances | `ui/dialogs/missed_pipelines_dialog.py`, `dashboard_view.py::_on_run_all` |
| Proposition | Durée estimée | Fin estimée d'un run en cours à partir des durées passées | `ui/dialogs/run_progress_dialog.py` |
| Proposition | Ce que l'échec bloque | Le détail d'un échec liste les pipelines déclenchés après lui | nouveau |
| Manquement | Tout exécuter | Un simple Oui/Non, sans dire ce qui tourne déjà ni quelle connexion n'a jamais été testée | `dashboard_view.py::_on_run_all` |

## Palette de commandes

| Type | Sujet | Détail | Où |
|---|---|---|---|
| Manquement | Palette absente | Aucune palette ni recherche globale ; 4 raccourcis seulement (Ctrl N, F5, Ctrl D, Suppr) | `ui/main_window/window.py` |
| Proposition | Ctrl K, Ctrl 1 à 6, « ? » | Palette partout, changement d'écran au clavier, aide des raccourcis | nouveau |

## Pipelines

| Type | Sujet | Détail | Où |
|---|---|---|---|
| Proposition | Port d'erreur non relié | Avertissement dans la validation à blanc quand un échec n'est rattrapé par rien | `core/pipeline.py::dry_run_pipeline` |
| Proposition | Regroupement de la liste | Par enchaînements, prochaine exécution ou nom | `ui/main_window/pipelines_view.py` |

## Connexions

| Type | Sujet | Détail | Où |
|---|---|---|---|
| Manquement | Historique des tests | Seul le dernier test est gardé (succès et date), sans le message | `database/models.py`, `record_profile_test_result` |
| Manquement | Kerberos dans le bilan | Non testable depuis le bilan de santé, seulement depuis sa fiche | `ui/dialogs/connection_health_dialog.py::_test_one` |
| Proposition | Pipelines touchés | Le bilan liste les pipelines concernés par chaque échec | nouveau |
| Proposition | Remplacer puis supprimer | Faire pointer les étapes vers une autre connexion avant de supprimer | `connections_view.py::_confirm_delete` |

## Requêtes SQL

| Type | Sujet | Détail | Où |
|---|---|---|---|
| Manquement | Pas d'exécution | Impossible de lancer une requête pour voir ce qu'elle renvoie | `ui/main_window/queries_view.py` |
| Manquement | Jetons incomplets | La barre d'état ne liste que les jetons de date, alors que `{var:}`, `{expr:}`, `{artifact:}` fonctionnent dans le SQL (`ctx.resolve_tokens`) | `queries_view.py::_build_workshop`, `core/steps/db_extract.py` |
| Manquement | Champ Profil trompeur | Ne propose que des profils Oracle et n'est pas utilisé à l'exécution (l'étape choisit la connexion) | `queries_view.py::_load_oracle_profiles`, `SqlQuery.oracle_profile_id` |
| Manquement | Modification non signalée | Rien n'indique qu'une requête est modifiée mais pas enregistrée | `queries_view.py` |
| Manquement | Import .sql | Remplace le texte de l'éditeur sans confirmation | `queries_view.py::_on_import_sql` |
| Manquement | Pas de journal | Les modifications de requêtes ne vont pas dans le journal des modifications | `database/db_manager.py::log_audit_event` |
| Proposition | Aperçu des résultats | 100 premières lignes, lecture seule, connexion et date simulées ; refusé pour une requête qui écrit | nouveau, via `core/sql_db.py::SqlConnector` |
| Proposition | SQL résolu | Ce que la base recevra, avec la valeur de chaque jeton | `StepContext.resolve_tokens` |
| Proposition | Autocomplétion des jetons | Taper `{` propose variables, dates, calculs | `ui/sql_editor.py` |
| Proposition | Alerte à l'enregistrement | Dire quels pipelines la modification touche | `find_pipelines_using_profile` |
| Proposition | Ctrl S | Enregistrer au clavier | `ui/sql_editor.py` |

## Historique

| Type | Sujet | Détail | Où |
|---|---|---|---|
| Manquement | 100 runs maximum | La liste ne charge que les 100 dernières exécutions, sans période ni pagination | `db_manager.py::get_recent_runs`, `history_view.py::refresh` |
| Manquement | Résultat par étape absent | Un run ne garde que son journal texte : ni durée ni lignes par étape, donc pas de chronogramme d'un run passé | `database/models.py::PipelineRun` |
| Manquement | Origine du run absente | Rien ne dit si un run est planifié, manuel, déclenché par un autre pipeline ou rattrapé (seule la reprise est notée) | `PipelineRun.resumed_from_run_id` |
| Manquement | Journal brut | Le journal d'un run est un texte sans niveaux : pas de filtre « erreurs » ni de recherche | `ui/main_window/run_log_dialog.py` |
| Manquement | Journal des modifications partiel | Ne suit que les pipelines (création, modification, suppression, import) ; une modification de réglage n'est décrite que par « Nom/description/planification » | `db_manager.py::log_audit_event`, `_diff_pipeline_graph` |
| Manquement | Carte de fréquence plafonnée | 10 pipelines au plus, sauf pendant une recherche | `history_view.py::_MAX_FREQUENCY_ROWS` |
| Proposition | Durée comparée à l'habitude | Barre de durée avec la médiane du pipeline, ambre au-delà de 1,5 fois | nouveau |
| Proposition | Historique d'un pipeline | Bandeau résumé (réussites, médianes, courbes durée et lignes) quand un seul pipeline est filtré ; remplace `PipelineDetailDialog` | `ui/dialogs/pipeline_detail_dialog.py` |
| Proposition | Jour en bulle | Le clic sur un jour de la carte ouvre une bulle au lieu d'une fenêtre | `history_view.py::_on_frequency_day_clicked` |

## Paramètres

| Type | Sujet | Détail | Où |
|---|---|---|---|
| Manquement | Prise d'effet cachée | « Redémarrage requis » n'est écrit que dans le texte des descriptions ; le paramètre `badge` de `_add_row` existe mais n'est jamais utilisé, et le message d'enregistrement dit seulement « certains réglages » | `settings_view.py::_add_row`, `_on_save` |
| Manquement | Modifications non signalées | Rien n'indique qu'un réglage est modifié mais pas enregistré, ni dans quelle catégorie ; pas d'annulation | `settings_view.py` |
| Manquement | Validation par fenêtres | Chaque champ invalide ouvre une `QMessageBox`, une à la fois, alors que la réussite est un message non bloquant | `settings_view.py::_on_save` |
| Manquement | État du worker figé | Calculé au chargement et à l'enregistrement seulement, jamais rafraîchi pendant que l'écran est ouvert | `settings_view.py::_refresh_worker_status` |
| Manquement | Pas d'essai du résumé | Impossible d'envoyer un résumé de test ou de voir ce qu'il contiendra avant le premier envoi | `core/scheduler.py::refresh_digest_job` |
| Proposition | Pastille de prise d'effet | Chaque réglage porte « immédiat », « à la prochaine ouverture » ou « au redémarrage » | `_add_row(badge=…)` |
| Proposition | Explication avant l'arrière-plan | Choisir le mode arrière-plan dit ce qui va se passer (tâche Windows, refus possible, redémarrage) avant d'enregistrer | `core/task_scheduler.py::register_logon_task` |
| Proposition | Refus en bandeau | L'échec « accès refusé » reste affiché avec le détail à copier pour le support, au lieu de disparaître après 10 s | `settings_view.py::_on_save` |
| Proposition | Validation en ligne | Erreurs sous chaque champ, toutes à la fois | `settings_view.py::_on_save` |
| Proposition | Redémarrer depuis l'écran | Après l'enregistrement, nommer les réglages en attente et proposer « Redémarrer Kulu » | nouveau |
| Proposition | Ctrl S et Ctrl F | Enregistrer et chercher au clavier | `settings_view.py` |

## Ressources

| Type | Sujet | Détail | Où |
|---|---|---|---|
| Manquement | Pas d'axes | Aucun axe du temps ni graduation : on ne peut lire ni l'heure d'une pointe ni sa valeur | `resources_view.py::_TimeSeriesChart.paintEvent` |
| Manquement | Valeur survolée absente | Le titre de chaque graphique montre la dernière valeur, pas celle de l'instant survolé | `resources_view.py::_chart_title_row`, `_on_chart_hover` |
| Manquement | CPU écrêté | `psutil.Process().cpu_percent` dépasse 100 % sur plusieurs cœurs, mais l'échelle est fixée à 100 | `core/scheduler.py::_sample_resources`, `_TimeSeriesChart(max_value=100)` |
| Manquement | 7 jours non agrégés | Jusqu'à 10 080 points chargés et dessinés tels quels, sans regroupement | `db_manager.py::get_resource_samples` |
| Manquement | « En cours » local | La carte lit `_active_runs` du processus de la fenêtre ; en mode arrière-plan, les runs du worker n'y sont pas comptés (déduit) | `resources_view.py::refresh` |
| Manquement | Échec de mesure silencieux | Une mesure qui échoue (psutil absent, par exemple) n'est écrite que dans les logs ; l'écran reste vide sans explication | `core/scheduler.py::_sample_resources` |
| Manquement | Rafraîchissement figé | La minuterie de l'écran garde l'intervalle lu au démarrage, même si on le change dans Paramètres | `ResourcesView.__init__` |
| Proposition | Plafond sur le graphique | Ligne pointillée du plafond d'exécutions simultanées sur « Pipelines en cours » | `AppSettings.max_concurrent_runs` |
| Proposition | Pastilles enrichies | Statut et durée de chaque run, clic pour l'ouvrir dans l'Historique | `_pipeline_chip` |
| Proposition | Plage au glisser | Choisir une plage, voir ses runs alignés sur le même temps, zoomer ou ouvrir l'Historique filtré | nouveau |
| Proposition | Enveloppe sur 7 jours | Moyenne par heure avec zone min–max, et marques des runs en échec | nouveau |
| Proposition | Heure du pic | La carte « Pic CPU » dit quand il a eu lieu | `resources_view.py::refresh` |

## Transverse

| Type | Sujet | Détail | Où |
|---|---|---|---|
| Manquement | Fuseau appliqué à moitié | Le fuseau de Paramètres pilote la planification (déclencheurs, prochaine exécution, rattrapages). Mais les heures de ce qui a tourné (début et fin de run, lignes du journal, échantillons) sont enregistrées en UTC et affichées sans conversion : à Paris, un pipeline prévu à 07:00 apparaît à 05:00 dans l'Historique (déduit du code). `next_run_at` est lui stocké dans le fuseau réglé, d'où deux conventions dans la même base | `core/pipeline.py` (`utcnow`), `core/scheduler.py` (`next_run_at`), `history_view.py`, `dashboard_view.py`, `resources_view.py` |
| Proposition | Une fonction d'affichage | Garder l'UTC en base, convertir à l'affichage dans le fuseau réglé par une seule fonction partagée ; aucune migration nécessaire | nouveau, `ui/` |

## Défauts relevés en préparant la passation

| Type | Sujet | Détail | Où |
|---|---|---|---|
| Manquement | Oracle utilisé par Sqoop | Supprimer un profil Oracle ne signale pas les étapes Sqoop qui l'utilisent | `connections_view.py::_on_delete_database` — fait (lot K1) |
| Manquement | Requête créée depuis une étape | La requête sélectionnée après création n'est pas forcément la nouvelle | `_new_sql_query` |
| Manquement | Date de test des bases | `list_all_db_profiles` ne renvoie pas `last_tested_at` | `database/db_manager.py` |
| Manquement | Dossier distant FTP | Champ du formulaire jamais enregistré | `ui/dialogs/ftp_dialog.py`, `FtpProfile` |
| Manquement | Élévation dans le bilan | Le bilan de santé ignore les profils d'élévation | `connection_health_dialog.py::_collect_profiles` |
| Manquement | Test en modification | Un test sur des valeurs non enregistrées est inscrit sur le profil enregistré | dialogues de profils |
| Manquement | Interruption en arrière-plan | Interrompre un run en mode arrière-plan n'appelle pas `request_cancel_run` | `pipelines_view.py::_on_interrupt_pipeline` |
| Manquement | Runs du worker invisibles | En mode arrière-plan, la liste ne voit pas les runs en cours (`is_pipeline_running` ne regarde que le processus courant) | `core/pipeline.py` |
| Manquement | Carte « Pipelines actifs » | Compte tous les pipelines | `dashboard_view.py` |
| Manquement | Lancement en double | Tout exécuter et le rattrapage lancent un pipeline enfant directement et encore par son parent | `dashboard_view.py::_on_run_all`, `missed_pipelines_dialog.py` |
| Manquement | Heure des jetons | Les jetons de date utilisent l'heure de la machine, pas le fuseau réglé | `StepContext.resolve_tokens`, `expr_lang` |
| Manquement | Jours en UTC | La carte de fréquence et le détail d'un jour découpent les jours en UTC | `history_view.py` |

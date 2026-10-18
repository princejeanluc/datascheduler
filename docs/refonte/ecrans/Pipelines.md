# Pipelines

Vue : `ui/main_window/pipelines_view.py` (classe `PipelinesView`, indice 1 de `window.py`), avec `ui/dialogs/pipeline_dry_run_dialog.py`, `pipeline_import_dialogs.py`, `pipeline_export_dialog.py`, `database/export_import.py` et `core/pipeline.py` (`dry_run_pipeline`, reprise). Maquettes : `maquettes/png/Pipelines*.png`.

## Intention
Le profil data y gère son parc : lancer, reprendre, valider, dupliquer, exporter, désactiver, supprimer. Aujourd'hui l'état d'un pipeline tient dans un badge et ses actions dans un menu sans contexte. La refonte montre sur chaque ligne l'état du dernier run, la forme du graphe et ses 8 derniers résultats, met en avant l'action utile (reprendre, lancer ou arrêter) et remplace les boîtes de message par des fenêtres qui disent les conséquences.

## États (frames)
| Frame | Ce qu'elle montre | Déclencheur dans l'application |
|---|---|---|
| Pipelines | Liste des pipelines, chaînes de déclenchement en arbre | Entrée 1 de la barre de navigation |
| Pipelines-menu | Menu « … » d'une ligne | Bouton « Plus d'actions » (`btn_more`) |
| Pipelines-validation | Panneau latéral de validation à blanc | Menu « Valider à blanc » (`_on_validate_pipeline`) |
| Pipelines-import | Fenêtre d'import, étape Revue avec collision | Bouton « Importer » (`_on_import_pipeline`) |
| Pipelines-export | Fenêtre d'export | Menu « Exporter… » (`_on_export_pipeline`) |
| Pipelines-suppression | Confirmation de suppression avec dépendants | Menu « Supprimer… » (`_on_delete_pipeline`) |
| Pipelines-vide | Trois manières de commencer | `db.get_pipelines()` vide (`_empty_label`) |

## À garder tel quel
- `Ctrl+N` (`QShortcut` dans `_build_ui`) et « + Nouveau pipeline » : nom demandé par `QInputDialog`, puis `open_atelier_requested.emit(id, None, True)`.
- Le signal `open_atelier_requested(int, object, bool)` et son branchement vers `window.open_atelier`. Les boutons graphe et engrenage l'émettent avec `False`.
- `refresh()` ne reconstruit rien tant qu'un menu est ouvert (`QApplication.activePopupWidget()`, commentaire sur le crash), rafraîchissement périodique `pipelines_refresh_s`, F5.
- Recherche en direct sur les lignes (`_filter_table_rows`), appliquée à nouveau après chaque `refresh()`.
- Double-clic sur une ligne : `PipelineDetailDialog` (test `test_pipelines_view_detail.py`), voir Questions.
- Lancer (`_on_run_pipeline`) : en mode arrière-plan, `request_run_now` puis fenêtre distante ; `prevent_overlap` avec proposition d'interrompre ; validation à blanc sans test réseau avant lancement, erreurs bloquantes, avertissements avec « Continuer quand même ? » (test `test_pipelines_view_pre_run_validation`).
- Reprendre depuis l'échec : proposé seulement si `db.get_last_resumable_run(pid)` renvoie un run (`test_pipelines_view_resume_menu.py`), lancé par `RunProgressDialog(resume_from_run_id=…)`.
- Interrompre : entrée présente seulement pendant un run (`is_pipeline_running`), confirmation, arrêt coopératif, badge « ARRÊT EN COURS » (`is_cancel_requested`), infobulle de l'étape en cours sur le badge, pulsation du badge en cours.
- Activer ou désactiver : `set_pipeline_active` puis `schedule_pipeline` ou `remove_pipeline`.
- Dupliquer : `duplicate_pipeline`, copie désactivée, message « la copie est désactivée par défaut ».
- Export : mot de passe facultatif, identifiants omis sans mot de passe, avertissements après export, journal d'audit.
- Import : le mot de passe faux se corrige sans fermer la fenêtre (`verify=`), la revue modifie `plan` sans rien écrire, copie renommée par défaut en collision, remappage vers un profil local, aperçu actif et planification avec l'avertissement de changement d'état, avertissements après `apply_import`, `_schedule_if_possible` (passe par `request_reload` en arrière-plan).
- Modèle de démarrage : `_on_start_from_template` (import du bundle, planification, ouverture de l'Atelier).
- Suppression : liste des dépendants (`get_pipelines_triggered_by`) ; `delete_pipeline` remet leur `trigger_after_pipeline_id` à NULL.
- Validation à blanc : exécutée dans un thread, fermeture bloquée tant qu'elle tourne (`closeEvent`).
- Quatre boutons par ligne et colonne Actions de largeur fixe d'au moins 140 px (`test_pipelines_view_action_menu.py`). Lignes inactives atténuées. Enfants placés sous leur parent (`_ordered_with_chains`). Vignette `PipelineStepDagThumbnail` avec losanges pour les passerelles. Infobulle du résumé complet des étapes.

## Lot A : alignement visuel, sans changer la base
Un élément est en lot A quand la fonction ou la donnée existe déjà, même si on l'appelle depuis un nouvel endroit.

| # | Changement | Frame | Source des données (code) |
|---|---|---|---|
| A1 | En-tête : surtitre « N PIPELINES · M ACTIFS », titre, « Importer » secondaire, « + Nouveau pipeline » principal avec « Ctrl N » affiché ; le texte « (Ctrl+N : nouveau) » quitte la recherche | Pipelines | `db.get_pipelines()`, `is_active` |
| A2 | Colonne PIPELINE : nom, description en dessous, connecteur d'arbre pour les enfants | Pipelines | `Pipeline.description`, profondeur de `_ordered_with_chains` |
| A3 | Colonne ÉTAT : pastille de statut (point et mot) et ligne de détail : heure et durée du dernier run, début de l'erreur sur un échec, « étape i/n · écoulé » en cours, « prévue HH:MM » si manqué, « Inactif » | Pipelines | `last_status`, `db.get_runs(pid, 1)`, `get_running_step_labels`, `core/missed_runs.get_pending` |
| A4 | Colonne FORME · 8 DERNIERS : vignette du graphe, « N étapes », pastilles des 8 derniers runs | Pipelines | `PipelineStepDagThumbnail`, `RunHistoryDots`, `db.get_runs(pid, 8)` |
| A5 | Colonne PLANIFICATION : planification, puis « ↳ après X » et la condition sur une seconde ligne (aujourd'hui en infobulle) | Pipelines | `describe_schedule`, `trigger_after_pipeline`, `trigger_condition` |
| A6 | Colonne PROCHAINE en Mono, « demain 07:00 » ou « 16:00 » | Pipelines | `next_run_at` |
| A7 | Premier bouton selon l'état : reprendre si reprenable, arrêter si en cours, lancer sinon | Pipelines | `_on_resume_pipeline`, `_on_interrupt_pipeline`, `_on_run_pipeline` ; voir Questions |
| A8 | Menu « … » restylé : en-tête au nom du pipeline, « Reprendre depuis l'échec », « Exécuter depuis le début », « Valider à blanc », « Dupliquer », « Exporter… », « Désactiver » avec « ne partira plus à HH:MM », « Supprimer… » en `danger` ; « Interrompre l'exécution en cours » reste pendant un run | Pipelines-menu | actions actuelles du `QMenu` ; `next_run_at` |
| A9 | Pied de liste : légende et « actualisé il y a N s » | Pipelines | heure du dernier `refresh()` |
| A10 | Validation dans un panneau latéral : surtitre « VALIDATION À BLANC · RIEN N'EST EXÉCUTÉ », compteurs d'erreurs et d'avertissements, messages actuels, « Relancer la validation » | Pipelines-validation | `DryRunResult.errors`, `warnings`, `checked_connections`, `_DryRunThread` |
| A11 | Import en une fenêtre à quatre étapes (Fichier, Mot de passe, Revue, Réglages) : nom du fichier, « Exporté le … depuis Kulu … », « identifiants déchiffrés », options de collision avec le nom réel de la copie (`_unique_name(f"{nom} (import)", …)`, donc « … (import) » et non « … (2) ») et « remplace définitivement ses N étapes », tableau Réutilisé ou Nouveau, « Créer une nouvelle requête » pour une requête SQL, « Rien n'est encore écrit. » | Pipelines-import | `plan_import_from_file`, `bundle["exported_at"]`, `bundle["app_version"]`, `bundle["kdf"]`, `_unique_name`, `ImportPlan.profile_decisions`, `_build_settings_preview` |
| A12 | Export restylé : surtitre, nom, champ mot de passe, texte d'aide de la maquette | Pipelines-export | `PipelineExportDialog`, `export_pipeline_to_file` |
| A13 | Suppression en fenêtre modale : dépendants avec leur planification, « Exporter d'abord », « Supprimer » en `danger` | Pipelines-suppression | `get_pipelines_triggered_by`, `describe_schedule`, `PipelineExportDialog`, `delete_pipeline` |
| A14 | État vide en trois cartes : « Partir du modèle », « Toile vierge », « Importer un .dspipeline » | Pipelines-vide | `_on_start_from_template`, `_on_new_pipeline`, `_on_import_pipeline` |

**Heures (FONDATIONS section 4).** Converties : heure du dernier run (`started_at`, `finished_at`), `exported_at` du fichier importé (ISO avec fuseau UTC), date de désactivation du lot B. Variante sans conversion : `next_run_at` (PROCHAINE, « ne partira plus à », « demain »), `expected_at` des manqués. Sans conversion : durées, écoulé, « actualisé il y a ».

## Lot B : changements de données

> Le schéma de référence est dans `../DONNEES.md`. Si un nom ou une colonne diffère ici, c'est `DONNEES.md` qui fait foi.

- **B1. Date de désactivation.** Besoin : « désactivé le 02/10 ». Proposition sans migration : `set_pipeline_active` écrit un événement d'audit `pipeline_deactivated` ou `pipeline_activated` (`log_audit_event`, table d'audit existante). La date affichée est celle du dernier `pipeline_deactivated`. `apply_import` appelle aussi `set_pipeline_active` lors d'un écrasement : l'événement s'écrit donc aussi à l'import, ce qui est juste. Worker : il n'appelle pas cette fonction, aucun impact. Export : aucun. L'Historique (onglet Modifications) affichera ces nouveaux types : vérifie leur libellé.
- **B2. Déclenchements dans l'export (conditionnel, question 4).** La fenêtre d'export annonce « planification, déclenchements, variables », mais le bundle n'écrit ni `trigger_after_pipeline_id` ni `trigger_condition`. Si on les ajoute : clés `trigger_after_pipeline_uuid` et `trigger_condition` dans `pipeline`, `CURRENT_SCHEMA_VERSION` passe à 4, `_transcribe_bundle` gère 3 vers 4 (valeurs nulles), parent introuvable à l'import ignoré avec un avertissement. Conséquence : un Kulu 0.45.0 refusera les fichiers v4. Worker : aucun impact.
- **B3. Pipeline sans planification propre (conditionnel, question 5).** Les maquettes montrent des enfants sans planification (« — », « n'a pas d'autre planification »). Le code planifie tout pipeline (aucune `CronFrequency` ne veut dire « aucune »). Si on l'ajoute : `pipelines.schedule_enabled BOOLEAN NOT NULL DEFAULT 1`, clé ajoutée à l'export (même passage en v4 que B2). Risque : un ancien worker ignore la colonne et continue de planifier ces pipelines.

## Lot C : fonctions nouvelles (« proposé »)
| # | Fonction | Frame | Dépend de |
|---|---|---|---|
| C1 | Filtres « Tous », « À traiter », « En cours », « Inactifs » avec compteurs | Pipelines | A3 |
| C2 | Regrouper par « Enchaînements » (ordre actuel), « Prochaine exécution », « Nom » | Pipelines | `_ordered_with_chains` |
| C3 | Recherche étendue aux étapes, connexions et requêtes (« Nom, étape, connexion, requête… ») | Pipelines | `_STEP_REFERENCES` |
| C4 | État « En attente · attend une synchro réussie » pour un enfant dont le parent a échoué | Pipelines | `trigger_condition`, statut du parent |
| C5 | Planification en clair des cron (« toutes les 4 h », « 09:00 et 21:00 », « hebdo dimanche 18:00 », « 1er du mois 05:00 ») par une nouvelle fonction ; `describe_schedule` ne change pas | Pipelines | `cron_expression` |
| C6 | Code d'erreur extrait (« ORA-12541 ») dans la ligne ÉTAT | Pipelines | `error_message` |
| C7 | Clic sur la vignette qui ouvre l'Atelier | Pipelines | `open_atelier_requested` |
| C8 | Raccourcis du menu (R, Entrée, V, Ctrl D, E, A, Suppr) sur la ligne sélectionnée, et sous-titre « rejoue X et la suite » | Pipelines-menu | `resumable_state_json` |
| C9 | Validation structurée : sections GRAPHE, RÉFÉRENCES, CONNEXIONS RÉELLES, contrôles réussis listés, durée de chaque test, avertissement « port d'erreur non relié », « Ouvrir l'étape en cause » | Pipelines-validation | `dry_run_pipeline` renvoie aussi une liste structurée ; `DryRunResult` garde ses champs |
| C10 | Suggestion de remappage quand un profil local a le même hôte, présélectionnée | Pipelines-import | `ImportPlan.profile_decisions` |
| C11 | Résumé « Le fichier contiendra » et nombre d'identifiants chiffrés | Pipelines-export | `export_pipeline(pid)` sans écriture |
| C12 | Nombre de runs de l'historique dans la confirmation de suppression | Pipelines-suppression | question 3 |
| C13 | Glisser-déposer d'un `.dspipeline` sur l'état vide | Pipelines-vide | `plan_import_from_file` |

## Hors périmètre
- Les couleurs des étapes par famille dans la vignette : lot 0 (`STEP_META["family"]`).
- Le correctif de `_on_interrupt_pipeline`, qui n'appelle pas `request_cancel_run` en mode arrière-plan : à noter dans la PR, section « Hors périmètre repéré ».
- Le lien « Vérification proposée » du panneau de validation tant que la question 6 n'est pas tranchée.

## Critères d'acceptation
- [ ] Capture Pipelines avec un échec reprenable, un enfant, un run en cours, un manqué et un inactif ; aucun élément « proposé » non livré ni place vide.
- [ ] Une ligne en échec montre l'heure du dernier run convertie (05:00 UTC affiché 07:00 avec `Europe/Paris` en été) ; PROCHAINE affiche `next_run_at` sans conversion.
- [ ] Le premier bouton reprend sur un échec reprenable, interrompt pendant un run, lance sinon ; quatre boutons par ligne ; colonne Actions en largeur fixe.
- [ ] Capture Pipelines-menu ; « Reprendre » absent sans état reprenable ; « Interrompre » présent seulement pendant un run ; « Désactiver » bascule `is_active` et retire le job.
- [ ] Un menu ouvert n'est pas détruit par le rafraîchissement périodique (test existant vert).
- [ ] Capture Pipelines-validation ; fermeture impossible pendant la validation ; « Relancer la validation » relance le thread.
- [ ] Capture Pipelines-import ; un mot de passe faux affiche l'erreur sans fermer ; « Annuler » à toute étape n'écrit rien en base ; un fichier v1 à v3 s'importe toujours (tests `test_export_import*`, `test_import*` verts).
- [ ] Capture Pipelines-export ; sans mot de passe, le fichier ne contient aucun identifiant (test existant).
- [ ] Capture Pipelines-suppression ; « Annuler » ne supprime rien ; « Supprimer » remet le `trigger_after_pipeline_id` des dépendants à NULL ; « Exporter d'abord » ouvre l'export sans supprimer.
- [ ] Capture Pipelines-vide ; chaque carte appelle sa fonction ; Ctrl+N ouvre la création depuis la liste et depuis l'état vide.
- [ ] Si B1 est livré : désactiver écrit un événement `pipeline_deactivated` et la ligne affiche « désactivé le JJ/MM ».
- [ ] Tests existants verts : `test_pipelines_view_*`, `test_pipeline_dry_run_dialog`, `test_dry_run`, `test_export_dialog`, `test_pipeline_resume`, `test_pipeline_duplication`, `test_onboarding_empty_states`.

## Questions ouvertes
1. Aucune frame de cet écran ne porte de pastille « proposé ». Les éléments C1 à C13 n'existent pas dans le code : confirme qu'ils sont à livrer.
2. Double-clic sur une ligne : la maquette dit « ouvre l'Atelier », le code ouvre `PipelineDetailDialog` (test `test_pipelines_view_detail.py`). Lequel garder ? La fiche garde le code.
3. La fenêtre de suppression dit « Les 52 exécutions de l'historique sont conservées ». Faux dans le code : `Pipeline.runs` a `cascade="all, delete-orphan"`, les runs partent avec le pipeline. On corrige le texte (« seront supprimées ») ou on change le comportement (hors règle « ajout seulement ») ?
4. L'export annonce « déclenchements » mais ne les écrit pas. On corrige le texte, ou on livre B2 (passage en v4) ?
5. Pipelines déclenchés sans planification propre (B3) : à faire, ou les maquettes montrent-elles un cas qui n'existe pas ?
6. Que fait le lien « Vérification proposée » (ajouter une étape d'alerte sur le port d'erreur ? ouvrir l'Atelier ?)
7. A7 change un comportement : pendant un run sans `prevent_overlap`, le premier bouton lance aujourd'hui un second run ; avec la maquette il l'arrête. Valide ce changement.
8. Lignes inactives : la maquette grise les quatre boutons, le code permet de lancer, ouvrir et réactiver un pipeline inactif. On garde le code ?
9. Les tests imposent des textes que la maquette change : libellés exacts du menu (`["Désactiver", "Valider (à blanc)", "Dupliquer", "Exporter", "Supprimer"]`), « Connexions » et « Requêtes SQL » dans l'état vide, `table.item(0, 3).text() == "Quotidien 08:15"`. Peut-on mettre à jour ces assertions pour les nouveaux textes ?
10. L'import détecte une collision par UUID (même pipeline déjà importé), pas par nom, et nomme la copie « nom (import) », pas « nom (2) » comme la maquette. Le titre « UN PIPELINE PORTE DÉJÀ CE NOM » devient-il « CE PIPELINE EXISTE DÉJÀ », et garde-t-on le suffixe « (import) » ?

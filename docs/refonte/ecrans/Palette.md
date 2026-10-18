# Palette de commandes

Vue : aucune aujourd'hui. Nouveau module proposé `ui/palette/` (fenêtre flottante sans cadre, parentée à `MainWindow`), raccourcis dans `ui/main_window/window.py`. Maquettes : `maquettes/png/Palette.png`, `Palette-recherche.png`, `Palette-actions.png`, `Palette-atelier.png`, `Palette-raccourcis.png`.

Prérequis : lot 0 (`FONDATIONS.md` : couleurs, composants « Champ de recherche » et « Fenêtre modale », `time_display`). Les écrans en fond (Aujourd'hui, Atelier) relèvent de leurs propres fiches.

## Intention
Un profil data passe son temps à aller d'un pipeline à une requête ou à une connexion, et à relancer ce qui a échoué. La palette donne un point d'entrée unique au clavier : Ctrl K partout, taper quelques lettres, Entrée pour agir, Tab pour voir toutes les actions. Aujourd'hui, Kulu n'a ni palette ni recherche globale, et seulement quelques raccourcis liés à un écran (manquements, section « Palette de commandes »). Presque tout est donc en lot C ; la palette ne fait que rappeler des fonctions qui existent déjà, sans en changer le comportement.

## États (frames)
| Frame | Ce qu'elle montre | Déclencheur dans l'application |
|---|---|---|
| Palette | Palette ouverte, champ vide : « À traiter maintenant », « Récents », grille « Aller à » (6 écrans, Ctrl 1 à 6), pied d'aide | Ctrl K ou clic sur le champ « Aller à, exécuter… » d'un en-tête (proposé) |
| Palette-recherche | Saisie « vent » : résultats groupés (Pipelines, Étapes, Requêtes SQL, Fichiers déposés, Commandes), lettres trouvées surlignées, aperçu du pipeline à droite, « 11 résultats » | Saisie dans le champ |
| Palette-actions | Puce « Reporting ventes J-1 × », actions du pipeline groupées (Lancer, Modifier, Autres) avec une lettre chacune | Tab sur un résultat pipeline |
| Palette-atelier | Ouverte depuis l'Atelier : puce du pipeline, « Ajouter à ce pipeline », « Dans ce pipeline », « Atelier » | Ctrl K quand l'Atelier est affiché |
| Palette-raccourcis | Aide des raccourcis en quatre groupes (Partout, Atelier, Éditeur SQL, Dans la palette) | Saisie de « ? » |

## À garder tel quel
Les raccourcis et comportements suivants existent. La palette s'y ajoute et ne doit ni les déplacer ni changer leur portée sans décision (voir questions).
- F5 rafraîchit la vue courante et affiche « Vue actualisée » dans la barre d'état (`window.py::_refresh_current_view`). Dans l'Atelier, il ne rafraîchit que la sidebar (`AtelierPipelinesView.refresh`).
- Ctrl+N crée un pipeline, **seulement sur l'écran Pipelines** (`pipelines_view.py`, `QShortcut` sur la vue, `_on_new_pipeline`).
- Ctrl+D duplique la sélection dans le canevas (`graph_editor_widget.py`), aussi dans le menu contextuel et le rail. Suppr **et** Retour arrière suppriment la sélection du canevas (`graph_scene.py::keyPressEvent`).
- Éditeur SQL : Ctrl+F et Ctrl+H ouvrent la barre de recherche, Échap la ferme (`ui/sql_editor.py`, raccourcis portés par l'éditeur).
- Recherche de nœud de l'Atelier : Entrée centre sur le résultat suivant (`graph_editor_widget._on_search_jump`).
- Les actions déjà offertes ailleurs gardent leurs confirmations et contrôles : validation avant lancement et gestion de `prevent_overlap` (`PipelinesView._on_run_pipeline`), « la copie est désactivée par défaut » (`_on_duplicate_pipeline`), confirmation de suppression (`_on_delete_pipeline`), messages « Reprise impossible… » (`core/pipeline.py::run_pipeline`), dialogue d'export (`PipelineExportDialog`).
- Le dialogue des pipelines manqués au démarrage (`MainWindow._show_missed_pipelines_dialog`) et les signaux de navigation du Dashboard (`navigate_to_history`, `navigate_to_settings`) restent.
- L'ordre des écrans dans le `QStackedWidget` (0 à 7, Atelier en 8) ne change pas : Ctrl 1 à 6 s'appuient dessus.

## Lot A : alignement visuel, sans changer la base
| # | Changement | Frame | Source des données (code) |
|---|---|---|---|
| A1 | Composant partagé « touche » (Mono 11 px, contour `border`, fond `bg_card`) pour afficher Ctrl K, Entrée, Tab, Échap, à ajouter au module de composants | Toutes | `ui/components/` (lot 0), `FONT_MONO_STACK` |
| A2 | Infobulles des actions existantes complétées par leur raccourci : « Nouveau pipeline (Ctrl+N) », « Supprimer la sélection (Suppr) » (le rail affiche déjà « Dupliquer la sélection (Ctrl+D) ») | Palette-raccourcis | `pipelines_view.py` (bouton Nouveau pipeline), `tool_rail.py::btn_delete` |

## Lot B : changements de données

> Le schéma de référence est dans `../DONNEES.md`. Si un nom ou une colonne diffère ici, c'est `DONNEES.md` qui fait foi.

**B1. Table `recent_items` (section « Récents »).** Besoin : « ouvert dans l'Atelier il y a 20 min », « requête SQL modifiée hier », « connexion consultée ce matin ». Rien ne trace aujourd'hui l'ouverture d'un pipeline ou la consultation d'une connexion ; seules les dates `updated_at` des requêtes et profils existent.
Schéma (création par `create_all`) : `id`, `kind` String(20) (`pipeline`, `query`, `connection`), `ref_id` Integer, `ref_category` String(20) nullable (catégorie de profil pour une connexion), `action` String(30) (`opened_atelier`, `modified`, `viewed`), `at` DateTime UTC naïf, unicité sur (`kind`, `ref_category`, `ref_id`) avec mise à jour de `at`. Écrit uniquement par l'interface : `MainWindow.open_atelier`, enregistrement d'une requête (`queries_view.py`), ouverture d'un profil (`connections_view.py`). Lignes orphelines ignorées à l'affichage (élément supprimé). Worker : ne lit ni n'écrit cette table, aucun impact. Export : non exporté.

La taille des fichiers déposés (« 4,1 Mo ») dépend de `pipeline_run_steps.output_size_bytes` (Atelier, B1) ; sans elle, la taille est omise.

## Lot C : fonctions nouvelles (« proposé »)
| # | Fonction | Frame | Dépend de |
|---|---|---|---|
| C1 | Palette : fenêtre flottante centrée au-dessus de l'écran assombri, champ « Aller à, exécuter, chercher… », touche Échap, navigation ↑ ↓, Entrée, pied d'aide contextuel (« partout dans Kulu », « actions du pipeline », « propre à l'Atelier », « aide des raccourcis ») | Toutes | A1, `QShortcut("Ctrl+K")` sur `MainWindow` |
| C2 | Champ « Aller à, exécuter… Ctrl K » des en-têtes qui ouvre la palette | Palette, Palette-atelier | Fiches Aujourd'hui et Atelier |
| C3 | « À traiter maintenant » : reprendre un run en échec (avec ce qu'il bloque), tester une connexion jamais testée utilisée par un pipeline planifié, lancer un pipeline manqué ; premier élément sélectionné | Palette | `db.get_last_resumable_run`, `PipelineRun.error_message`, `_trigger_downstream_pipelines` (pipelines déclenchés après), `last_tested_at`, `db.find_pipelines_using_profile`, `find_pipelines_using_db_profile`, `core.missed_runs.get_pending` ; même liste que « À traiter » de la fiche Aujourd'hui |
| C4 | « Récents » : trois derniers éléments avec leur type | Palette | B1 |
| C5 | « Aller à » : six écrans en grille, et raccourcis globaux Ctrl+1 à Ctrl+6 vers les indices 0 à 5 | Palette | `MainWindow._navigate` |
| C6 | Recherche groupée : Pipelines (nom, description, planification, dernier statut), Étapes (libellé, type, pipeline), Requêtes SQL (nom, début du SQL), Fichiers déposés (chemin, heure), Commandes ; lettres trouvées en `accent_pale` ; nombre de résultats | Palette-recherche | `db.get_pipelines`, `db.get_steps`, `STEP_META`, `db.get_sql_queries`, `db.get_recent_runs` (`remote_path`, `finished_at`) |
| C7 | Aperçu d'un pipeline : surtitre « PIPELINE · ACTIF », description, vignette du graphe, dernière exécution, 8 dernières, prochaine, « Déclenche » et « déclenché par », connexions utilisées ; « Exécuter » (Entrée), « Ouvrir dans l'Atelier » (Ctrl Entrée), « Toutes les actions » (Tab) | Palette-recherche | `PipelineStepDagThumbnail`, `RunHistoryDots`, `db.get_runs(limit=8)`, `Pipeline.next_run_at` (sans conversion), `trigger_after_pipeline_id`, `node_facts.compute_node_facts` pour les profils |
| C8 | Préfixes : « > » commandes, « # » requêtes, « @ » connexions, « ? » aide ; Retour arrière sur champ vide quitte le filtre ou la puce | Palette | C6 |
| C9 | Actions d'un pipeline avec lettre directe : Exécuter maintenant (Entrée), Valider à blanc (V), Reprendre depuis l'échec (grisé avec sa raison s'il n'y a rien à reprendre), Ouvrir dans l'Atelier (Ctrl Entrée), Paramètres du pipeline (P), Dupliquer, Désactiver ou Activer (A), Voir l'historique (H), Exporter en .dspipeline (E), Supprimer… (`danger`, confirmation) | Palette-actions | `PipelinesView._on_run_pipeline`, `_on_validate_pipeline`, `_on_resume_pipeline`, `open_atelier_requested`, `_on_duplicate_pipeline`, `_on_toggle_pipeline`, `_on_export_pipeline`, `_on_delete_pipeline` ; historique : `_navigate(4)` puis `HistoryView.inp_search` |
| C10 | Sous-titres calculés : « durée habituelle 2 min », « 52 exécutions · 1 échec ce mois-ci », « ne partira plus à 06:00 jusqu'à réactivation » | Palette-actions | `db.get_runs` (`started_at`, `finished_at`, `status`), `next_run_at` |
| C11 | Palette dans l'Atelier : puce du pipeline ouvert ; « Ajouter à ce pipeline » (types, modèles, modèle de script Python) ; « Dans ce pipeline » (Aller à une étape, Dupliquer la sélection) ; « Atelier » (Exécuter jusqu'à l'étape sélectionnée, Réorganiser automatiquement) ; Entrée insère à la sélection, Maj Entrée insère en fin | Palette-atelier | `StepTypeChooserDialog` (types, `get_step_templates`), `python_script_template.py`, `graph_editor_widget._on_search_jump` et `centerOn`, `_on_duplicate_selected`, `_on_auto_layout`, `_on_add_step` ; insertion à la sélection et « Exécuter jusqu'ici » : Atelier C7 et C5 |
| C12 | Aide des raccourcis (« ? ») en quatre groupes, sans la ligne « Les raccourcis marqués « proposé »… » ni les pastilles, et ne listant que les raccourcis réellement livrés | Palette-raccourcis | Liste centralisée des raccourcis (un seul endroit, lu par l'aide) |
| C13 | Raccourcis de l'Atelier : Ctrl+F donne le focus à la recherche de nœud ; Échap revient aux paramètres du pipeline ; Ctrl+Entrée exécute jusqu'à l'étape sélectionnée | Palette-raccourcis | `inp_search` ; Atelier C1 et C5 |

## Hors périmètre
- L'écran Aujourd'hui et l'Atelier visibles derrière la palette : fiches `Aujourdhui.md` et `Atelier.md`.
- La recherche plein texte dans les journaux d'exécution, absente des maquettes.
- Les valeurs d'exemple (noms, heures, chiffres, chemins).

## Critères d'acceptation
- [ ] Palette : Ctrl K ouvre la palette depuis chacun des huit écrans et l'Atelier ; Échap la ferme et rend le focus au widget précédent (test).
- [ ] Ctrl K n'ouvre rien quand un dialogue modal est affiché (test).
- [ ] Palette : capture champ vide avec « À traiter maintenant » (premier élément sélectionné), « Récents », grille « Aller à » et pied d'aide.
- [ ] Sans élément à traiter, la section est absente, sans place vide ; sans B1, « Récents » est absente (test).
- [ ] Ctrl+1 à Ctrl+6 affichent les écrans d'indice 0 à 5 et surlignent le bon bouton de navigation, palette ouverte ou non (test).
- [ ] Palette-recherche : la saisie « vent » sur une base de test renvoie les groupes attendus, surligne les lettres et affiche le nombre de résultats (test sur la fonction de recherche, capture).
- [ ] L'aperçu affiche la prochaine exécution à partir de `next_run_at` sans conversion de fuseau, et la dernière exécution convertie par `time_display` (test).
- [ ] Entrée sur un pipeline passe par la même validation que la liste : un graphe invalide affiche « Pipeline invalide » (test réutilisant `test_pipelines_view_pre_run_validation.py`).
- [ ] Palette-actions : Tab ouvre la liste ; chaque lettre déclenche son action ; « Reprendre depuis l'échec » est grisé avec sa raison quand `get_last_resumable_run` est vide ; « Supprimer… » demande confirmation (tests).
- [ ] Retour arrière sur un champ vide retire la puce et revient à la recherche (test).
- [ ] Palette-atelier : ouverte dans l'Atelier, la palette montre la puce du pipeline et les trois groupes ; « Aller à <étape> » centre le canevas sur le nœud ; « Réorganiser automatiquement » active « Annuler le rangement » (tests).
- [ ] Retour arrière tapé dans la palette ouverte sur l'Atelier ne supprime aucun nœud sélectionné (test).
- [ ] Palette-raccourcis : « ? » affiche l'aide ; chaque raccourci listé fonctionne ; aucune pastille ni phrase « proposé » n'apparaît (capture et test qui parcourt la liste centralisée).
- [ ] F5, Ctrl+N sur Pipelines, Ctrl+D, Suppr, Retour arrière dans le canevas et Ctrl+F, Ctrl+H, Échap dans l'éditeur SQL se comportent comme avant (tests existants verts).
- [ ] B1 : une base 0.45.0 s'ouvre ; ouvrir un pipeline dans l'Atelier crée ou met à jour sa ligne ; un élément supprimé n'apparaît pas dans « Récents » (tests).

## Questions ouvertes
1. La maquette range « Nouveau pipeline Ctrl N » dans « Partout » sans pastille, mais le raccourci n'est actif que sur l'écran Pipelines (`QShortcut` posé sur `PipelinesView`). Le rendre global (lot C) ou le ranger sous « Pipelines » dans l'aide ?
2. Palette-actions affiche « Dupliquer Ctrl D » pour un pipeline. Ctrl+D n'existe que dans le canevas, pour un nœud. Ctrl+D vaut-il seulement dans la palette, ou aussi sur la liste des pipelines ?
3. Le « ? » global : ouvrir l'aide seulement quand le focus n'est pas dans un champ de saisie (sinon l'éditeur SQL, les expressions et les libellés ne peuvent plus contenir « ? »), ou seulement par saisie de « ? » dans la palette, comme sur la maquette ?
4. Ctrl+Entrée signifie « Ouvrir dans l'Atelier » dans la palette et « Exécuter jusqu'ici » dans l'Atelier. Accepté tel quel ?
5. « Exécuter maintenant · en arrière-plan » n'est vrai qu'en mode arrière-plan (`request_run_now`). En mode bureau, le run ouvre `RunProgressDialog`. Sous-titre selon le mode ?
6. La grille « Aller à » et les maquettes nomment le premier écran « Aujourd'hui » ; la navigation dit « Dashboard » (`window.py::nav_items`). Le renommage relève de la fiche Aujourd'hui : la palette suit-elle le libellé livré ?
7. Le résultat « Copie vers SFTP » ne correspond à aucun type d'étape (`FTP_UPLOAD` s'appelle « Envoi FTP »). Faut-il des mots-clés de recherche par type, et qui les rédige ?
8. La recherche dans les étapes lit les étapes de tous les pipelines. Index construit à chaque ouverture de la palette, ou en cache invalidé à l'enregistrement d'un graphe ?
9. « Durée habituelle » : médiane des dernières exécutions réussies, sur combien de runs ?
10. « Paramètres du pipeline (P) » ouvre l'Atelier sur le panneau de droite, ou le dialogue `PipelineSettingsDialog` ?

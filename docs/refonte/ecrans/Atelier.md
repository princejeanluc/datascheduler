# Atelier

Vue : `ui/main_window/atelier_pipelines_view.py` (avec `atelier_sidebar.py`, `ui/graph_editor/`, `ui/step_editor/`). Maquettes : `maquettes/png/Grammaire.png`, `Main.png`, `Atelier-etape.png`, `Atelier-ajout.png`, `Atelier-echec.png`.

Prérequis : lot 0 (couleurs par famille via `STEP_META["family"]`, composants, `time_display`). Voir `FONDATIONS.md`, rien n'est redécrit ici.

## Intention
L'Atelier est l'endroit où un profil data construit et répare un pipeline : canevas au centre, paramètres du pipeline à droite. La refonte rend le graphe lisible d'un coup d'œil (la couleur dit la famille, la forme dit étape ou passerelle, l'ambre dit l'erreur) et rapproche l'Atelier de l'exécution : valider, lancer et reprendre un échec sans revenir à la liste. Aucune de ces maquettes ne porte de pastille « proposé », mais beaucoup d'éléments n'existent pas dans le code : ils sont classés en B ou C ci-dessous et listés dans les questions ouvertes.

## États (frames)
| Frame | Ce qu'elle montre | Déclencheur dans l'application |
|---|---|---|
| Grammaire | Référence visuelle : carte d'étape (repliée, dépliée), trois passerelles, cinq styles de liaison, quatre états de nœud | Aucun écran : règle de rendu de `node_item.py` et `edge_item.py` |
| Main | Atelier ouvert, aucune étape sélectionnée, paramètres du pipeline à droite, compartiment bas sur le chronogramme | `MainWindow.open_atelier(pipeline_id)` depuis Pipelines ou Historique |
| Atelier-etape | Une étape sélectionnée : ses liaisons en couleur, son édition dans le panneau de droite, journal de l'étape en bas | Aujourd'hui : double-clic sur un nœud, qui ouvre un dialogue modal |
| Atelier-ajout | Panneau « Ajouter » à gauche, insertion glissée sur une liaison, aperçu du type à droite | Aujourd'hui : bouton « + » du rail, qui ouvre `StepTypeChooserDialog` puis le dialogue de config |
| Atelier-echec | Vue d'un run en échec : état de chaque nœud, détail de l'échec, reprise | Aujourd'hui : `open_atelier(pid, highlight_step_key)` depuis une ligne d'historique en échec (surlignage seul) |

## À garder tel quel
Ces fonctions existent et ne sont pas toutes visibles sur les maquettes. Un refactor ne doit en supprimer aucune.

**Vue et navigation (`atelier_pipelines_view.py`, `window.py`)**
- La vue reste l'indice 8 du `QStackedWidget`, hors de `nav_items`. `open_atelier()` appelle `open_pipeline()` avant `_navigate(8)`, jamais l'inverse.
- `open_pipeline(pipeline_id, highlight_step_key, is_new_pipeline)` garde sa signature (appelée par `PipelinesView`, `HistoryView`, la sidebar). Le cas « Pipeline introuvable » reste affiché.
- `_on_back_clicked` : un pipeline neuf sans étape est supprimé au retour ; `stop_polling()` est appelé ; `back_requested` ramène à Pipelines.
- `_on_new_pipeline_graph_first_saved` : un pipeline neuf est planifié à son premier enregistrement.
- `refresh()` ne touche que la sidebar (timer `pipelines_refresh_s` et F5) et n'écrase jamais une édition en cours.
- Deux enregistrements distincts : « Enregistrer le graphe » (`PipelineGraphEditorWidget.save`) et « Enregistrer les paramètres » (`PipelineSettingsPanel.save`). Aucune sauvegarde automatique n'existe.
- Sidebar `AtelierSidebar` : liste des pipelines avec pastille de statut ou INACTIF, ligne active surlignée, repli persisté dans `AppSettings.atelier_sidebar_collapsed`, signal `pipeline_selected`.

**Canevas (`graph_editor_widget.py`, `graph_scene.py`, `graph_view.py`)**
- Rail d'outils `EditorToolRail`, dix boutons dans cet ordre : ajouter une étape, ajouter une zone, dupliquer, supprimer, ranger automatiquement, ranger la sélection, annuler le rangement (désactivé tant qu'aucun rangement), mini-carte (état actif), tout déplier ou replier, aide (`GraphHelpDialog`, rubrique `graph-editor`).
- Mini-carte cliquable visible par défaut ; widget de zoom (−, pourcentage, +) ; zoom à la molette ; pan au bouton du milieu ; sélection par rectangle ; grille de points ; guides d'alignement et accrochage.
- Zones : ajout, déplacement par l'en-tête, redimensionnement par le coin, renommage au double-clic, enregistrées avec le graphe.
- Recherche de nœud : filtre par type ou libellé, nœuds non trouvés à 35 % d'opacité sauf ceux en cours ou en échec, Entrée centre sur le résultat suivant.
- Liaison par glisser d'un port de sortie vers un port d'entrée. Ports : entrée à gauche, sorties nommées (`true`/`false` pour une condition), port `error` toujours en bas et ambre sur toutes les étapes et passerelles (`core.steps.get_step_output_ports`).
- Chevron par nœud pour déplier le détail (faits de `node_facts.compute_node_facts`, variables lues et écrites) ; état non persisté.
- Double-clic sur un nœud : dialogue de config avec les étapes amont réellement reliées (`_incoming_prior_steps`) et les variables du pipeline relues à chaque ouverture. Double-clic sur une zone : renommage.
- Menu contextuel d'un nœud : Dupliquer (Ctrl+D), Enregistrer comme modèle…, Supprimer. Ctrl+D au clavier. Suppr **et** Retour arrière suppriment nœuds, liaisons et zones sélectionnés.
- Traçage lumineux pendant un run (`start_polling`, `get_running_step_keys_multi` puis repli sur `get_running_step_keys`) ; pas de polling quand `highlight_step_key` est fourni ; surlignage rouge du nœud en échec et de ses liaisons entrantes.
- `save()` : refus sans étape, erreurs de `validate_pipeline_graph` bloquantes, avertissements avec Oui/Non. Rangement refusé si le graphe a un cycle.
- `PipelineGraphEditorDialog` et `PipelineSettingsDialog` restent comme enveloppes de compatibilité ; signaux `saved` et `pipeline_renamed` inchangés.

**Ajout et configuration d'étape (`ui/step_editor/`)**
- `StepTypeChooserDialog` : recherche en direct, section « Mes modèles » avec renommer et supprimer, nœuds de routage inclus dans le canevas, `chosen_type` et `chosen_config`.
- Champs communs de `_BaseStepConfigDialog` : Libellé, Réessayer en cas d'échec, Intervalle de relance (masqué à 0), avertissement de duplication pour FTP_UPLOAD, EMAIL_NOTIFY, HTTP_REQUEST et DB_EXECUTE, « Exécuter même si une étape précédente a échoué », Délai maximal, Source, Nom de sortie, boutons « + Artefact », « + Variable », « + Nouveau » profil, aide des jetons. `result_step()` garde la génération de `_step_key`.

**Paramètres du pipeline (`pipeline_settings_panel.py`)**
- Validations : nom requis, variable sans nom ou sans expression, expression compilée par `compile_expression`, nom en double. L'ordre des variables compte. Le bouton « − Retirer » reste.
- Déclenchement : option « Aucun (planification seule) », condition désactivée sans parent, avertissement si `set_pipeline_trigger` lève une erreur.
- « Branches en parallèle max » masqué tant que la case n'est pas cochée ; cron affiche « Expression invalide » ; replanification par `request_reload()` ou `schedule_pipeline()` après enregistrement ; infobulles actuelles.

**Reprise (`core/pipeline.py`)**
- `run_pipeline(..., resume_from_run_id)` refuse la reprise si une étape réussie a changé (`_step_fingerprint`), si les liaisons ont changé (`_edges_fingerprint`) ou si un fichier temporaire manque, avec les messages « Reprise impossible… » actuels. Purge des états de reprise périmés inchangée.

## Lot A : alignement visuel, sans changer la base
| # | Changement | Frame | Source des données (code) |
|---|---|---|---|
| A1 | Carte d'étape : surtitre Mono en majuscules « FAMILLE · MOTEUR », libellé en titre, objet principal (requête, fichier) en sous-titre Mono, point de famille à la place du badge d'icône | Grammaire, Main | `node_item.py::paint`, `_node_text_hierarchy` ; moteur : `_build_profile_names` étendu avec `db_type` et `FtpProfile.protocol` ; objet : premier fait de `compute_node_facts` |
| A2 | Contenu déplié restylé : lignes Profil, Requête, Fichier ; puces « ↳ lit var:x » (`signal_pale`) et « ↳ écrit y » (`accent_pale`) | Grammaire | `node_item.py::_paint_expanded_content`, `node_facts.extract_var_references_from_config`, `compute_written_variables` |
| A3 | Passerelles en losange de la famille Passerelles, symbole « ? », « + », « ET » ou « OU » selon `join_mode`, nom au-dessus du losange (il est dessous aujourd'hui) | Grammaire, Main | `node_item.py::paint` (branche `routing`), `config["join_mode"]` |
| A4 | Sélection : bordure `accent`, liaisons de la sélection en `accent` et son chemin d'erreur en `warning`, autres nœuds atténués | Atelier-etape | `node_item.py::paint` (`isSelected`), `edge_item.py::paint`, `QGraphicsScene.selectionChanged` |
| A5 | Liaison issue du port `error` en pointillé `warning` ; mots « vrai » et « faux » sur les liaisons `true`/`false` | Grammaire, Main | `edge_item.py::paint` (`from_port`), `node_item._PORT_STYLE` |
| A6 | En-tête : fil « Pipelines / nom » ; « Pipelines » déclenche `_on_back_clicked` | Main | `atelier_pipelines_view._build_ui`, `_title_lbl` |
| A7 | Bouton secondaire « Valider à blanc » dans l'en-tête | Main | `PipelineDryRunDialog(pipeline_id, name)`, comme `PipelinesView._on_validate_pipeline` |
| A8 | Bouton principal « Exécuter » dans l'en-tête, même chemin que la liste (validation préalable, `prevent_overlap`, `request_run_now` ou `RunProgressDialog`) | Main | `PipelinesView._on_run_pipeline` (à factoriser sans le renommer) |
| A9 | Quand un run est reprenable : « Relancer tout » et « Reprendre depuis l'échec » (principal) dans l'en-tête | Atelier-echec | `db.get_last_resumable_run`, `RunProgressDialog(..., resume_from_run_id=)` |
| A10 | Recherche de nœud en surimpression en haut à droite du canevas ; aide « Tirer d'un port de sortie vers un port d'entrée pour relier deux nœuds » | Main | `graph_editor_widget._build_ui` (`inp_search`, `hint`) |
| A11 | Panneau de droite : surtitre PIPELINE, case Actif en haut à droite, nom en titre éditable, description | Main | `PipelineSettingsPanel.inp_name`, `inp_desc`, `chk_active` |
| A12 | Planification en boutons segmentés Jour, Semaine, Mois, Cron (DAILY, WEEKLY, MONTHLY, CUSTOM), heure, cron généré, fuseau affiché en lecture seule | Main | `_freq_buttons`, `lbl_cron`, `_refresh_cron`, `AppSettings.timezone` |
| A13 | Déclenchement en phrase : « Lancer aussi après [pipeline] si elle [réussit, échoue, se termine] », valeurs SUCCESS, FAILURE, ALWAYS inchangées | Main | `_build_trigger_ui` (`cb_trigger_parent`, `cb_trigger_condition`) |
| A14 | Section EXÉCUTION : deux cases, nombre maximal en ligne (« 4 max ») | Main | `chk_prevent_overlap`, `chk_parallel_execution`, `spin_max_parallel_branches` |
| A15 | Variables : nom et valeur en Mono, « + Ajouter » en lien ; variables écrites par les étapes affichées en lecture seule « écrite par X » | Main | `tbl_variables` ; `compute_written_variables` sur les nœuds du canevas |
| A16 | Le bouton Pipelines de la barre de navigation reste surligné dans l'Atelier | Main | `MainWindow._navigate` (`set_active_index`) |

## Lot B : changements de données

> Le schéma de référence est dans `../DONNEES.md`. Si un nom ou une colonne diffère ici, c'est `DONNEES.md` qui fait foi.

**B1. Table `pipeline_run_steps` (une ligne par étape et par run).** Besoin : statut et résumé sous chaque nœud (« ✓ 41 s · 83 212 l. », « non exécutée », « ✗ 3 tentatives refusées »), branche prise ou non au dernier passage, chemin d'erreur déclenché, chronogramme, journal et historique de l'étape, récapitulatif « 5 réussies · 2 en échec… », tentatives horodatées. Aujourd'hui `PipelineRun` ne garde que l'étape courante, l'étape en échec et un `log_text` global ; `active_ports` n'est conservé qu'en cas d'échec reprenable.
Schéma (création par `create_all`, aucune colonne modifiée ailleurs) : `id`, `run_id` (→ `pipeline_runs.id`), `step_key` String(36), `step_type` String(50), `step_label` String(255) nullable, `status` String(20) (SUCCESS, FAILED, SKIPPED, CANCELLED, RUNNING), `started_at`, `finished_at` (UTC naïf), `attempts` Integer défaut 1, `attempts_json` Text nullable (`[{n, started_at, finished_at, error}]`), `rows_count` Integer nullable, `output_path` String(500) nullable, `output_size_bytes` Integer nullable, `port_taken` String(50) nullable, `error_message` Text nullable, `reused_from_resume` Boolean défaut False.
Écriture : `core/pipeline.py` (`_run_step_with_policy`, `_execute_linear`, `_execute_graph`, `_execute_graph_parallel`). Worker : un ancien worker n'écrit pas cette table ; l'interface affiche alors l'état du run seul, sans détail par étape. Le nouveau worker sur une ancienne interface est sans effet. `delete_pipeline` doit aussi supprimer ces lignes. Export : les runs ne sont pas exportés, `.dspipeline` inchangé.

**B2. Brouillon (seulement si C6 est retenu).** Table `pipeline_drafts` (`pipeline_id` unique, `graph_json`, `settings_json`, `changes_count`, `updated_at`). Le worker et le scheduler continuent de lire les tables publiées et ignorent cette table. Export : on exporte la version publiée.

## Lot C : fonctions nouvelles (« proposé »)
| # | Fonction | Frame | Dépend de |
|---|---|---|---|
| C1 | Édition de l'étape dans le panneau de droite (onglets Configuration, Données, Historique ; « ← Paramètres du pipeline », Échap) au lieu du dialogue modal | Atelier-etape | Rendre les 18 `_Base…ConfigDialog` hébergeables comme `PipelineSettingsPanel` ; B1 pour Historique |
| C2 | Annotations « fournit <fichier> » et « reçoit {error} » sur les voisins, aperçu du chemin résolu | Atelier-etape | `StepContext.resolve_tokens` (`core/steps/base.py`) |
| C3 | Connexion de l'étape avec « Tester » et « Jamais testée » | Atelier-etape | `test_connection()` des clients `core/`, `db.record_profile_test_result`, `last_tested_at` |
| C4 | « Tester l'étape » (exécution isolée d'une étape) | Atelier-etape | Nouveau dans `core/pipeline.py` |
| C5 | « Exécuter jusqu'ici » (manquements) | Atelier-etape, Palette-atelier | `core/pipeline.py::run_pipeline`, nouveau paramètre d'arrêt après une `step_key` |
| C6 | Brouillon et Publier, enregistrement automatique, pastille « Brouillon · N modifications » | Main | B2 |
| C7 | Panneau « Ajouter » latéral : recherche, glisser sur le canevas ou sur une liaison avec reliage automatique, Entrée insère après la sélection, aperçu « Reçoit, Produit, Connexion, Port d'erreur », champs à remplir, « Insérer à l'emplacement marqué » | Atelier-ajout | Contenu de `StepTypeChooserDialog`, `step_produces_output_file`, `get_step_output_ports` |
| C8 | Compartiment bas repliable : Chronogramme, Journal, Variables, Validation (n), statut du dernier run, « Exécutions précédentes » | Main, Atelier-ajout | Journal : `PipelineRun.log_text` ; Validation : `dry_run_pipeline` ; Chronogramme : B1 |
| C9 | Vue d'un run (« Vue de l'exécution du … · revenir à l'édition ») : canevas en lecture seule, état par nœud, panneau d'échec (message, tentatives, suite, piste, carte de reprise) | Atelier-echec | B1, `highlight_step_key`, `error_message`, `resumable_state_json` |
| C10 | « Prochaines exécutions » : trois dates et délai restant | Main | Nouvelle fonction de calcul dans `core/scheduler.py` |
| C11 | Bouton d'ajustement du zoom à la vue | Main | `ZoomWidget` |
| C12 | Menu ▾ de changement de pipeline à côté du nom | Main | `db.get_pipelines`, `open_pipeline` |

## Hors périmètre
- La palette et le champ « Aller à, exécuter… Ctrl K » de l'en-tête : voir `Palette.md`.
- La couleur par famille et les composants partagés : lot 0.
- La barre de navigation globale, sauf A16.
- Les noms de pipelines, d'étapes, de fichiers et les chiffres des maquettes.

## Critères d'acceptation
- [ ] Grammaire : capture d'un nœud de chaque famille, replié et déplié, avec surtitre famille · moteur et puces lit/écrit (A1, A2).
- [ ] Grammaire : condition, parallèle et jonction en losange, nom au-dessus, jonction affichant ET ou OU selon `join_mode` (test unitaire sur la fonction de symbole) (A3).
- [ ] Une liaison issue de `error` est en pointillé `warning` ; une liaison `true` porte « vrai » (test sur la couleur et le style retournés) (A5).
- [ ] Sélectionner un nœud met sa bordure et ses liaisons en `accent`, son chemin d'erreur en `warning`, et atténue les autres ; désélectionner rétablit tout (A4).
- [ ] Main : capture à 1440×900 avec rail d'outils à dix boutons, recherche en haut à droite, mini-carte, zoom, panneau de paramètres complet (A6 à A15).
- [ ] « Pipelines » dans le fil d'Ariane supprime un pipeline neuf sans étape, comme l'ancien bouton (test existant `test_atelier_pipelines_view.py` vert).
- [ ] « Valider à blanc » ouvre `PipelineDryRunDialog` pour le pipeline ouvert (A7).
- [ ] « Exécuter » refuse un graphe invalide et propose l'interruption si `prevent_overlap` et run en cours, comme depuis la liste (A8).
- [ ] Atelier-echec : avec un run reprenable, l'en-tête montre « Relancer tout » et « Reprendre depuis l'échec » ; sans run reprenable, aucun des deux (A9).
- [ ] La phrase de déclenchement enregistre SUCCESS, FAILURE ou ALWAYS ; « Aucun » désactive la condition (A13).
- [ ] Toutes les validations du panneau de paramètres donnent les mêmes messages qu'avant (`test_pipeline_settings_dialog.py` vert).
- [ ] Ctrl+D, Suppr, Retour arrière, double-clic sur nœud et zone, menu contextuel et les dix boutons du rail fonctionnent (`test_graph_tool_rail.py`, `test_node_context_menu.py`, `test_duplicate_node.py` verts).
- [ ] La sidebar, le repli persisté et les deux boutons d'enregistrement sont présents tant que les questions 1 et 2 ne sont pas tranchées.
- [ ] B1 : une base 0.45.0 s'ouvre, la table est créée, un run linéaire, graphe et parallèle écrit une ligne par étape exécutée, et une reprise marque `reused_from_resume` (tests dans `tests/`).
- [ ] B1 : sans lignes d'étape (ancien worker), Main et Atelier-echec s'affichent sans erreur ni place vide.
- [ ] Chaque fonction C retenue a sa capture d'état et un test de comportement.

## Questions ouvertes
1. La sidebar des pipelines (`AtelierSidebar`) n'apparaît sur aucune maquette. La garder, la replier par défaut, ou la remplacer par le menu ▾ (C12) ?
2. Les maquettes affichent « enregistré automatiquement » et aucun bouton d'enregistrement ; le code n'a aucune sauvegarde automatique, par choix documenté. Garder les deux boutons jusqu'à C6 ?
3. « Exécuter » lance la version en base : que faire des modifications non enregistrées du canevas (enregistrer d'abord, demander, refuser) ?
4. Atelier-etape (édition dans le panneau, « Tester l'étape ») et Atelier-ajout (panneau latéral, glisser, insertion sur une liaison) n'ont pas de pastille « proposé » mais n'existent pas. Confirmer le classement en C. Le double-clic doit-il toujours ouvrir le dialogue ?
5. Aujourd'hui, le dialogue de config s'ouvre avant que le nœud soit posé ; la maquette pose d'abord puis fait remplir. Un nœud non configuré peut-il exister sur le canevas et être enregistré ?
6. Les sections de la maquette d'ajout (Appel HTTP dans « Exécution et scripts », groupe « Big Data · Notification · Variables ») diffèrent de `_CATEGORY_ORDER`, que `FONDATIONS.md` interdit de changer au lot 0. Les libellés diffèrent aussi de `STEP_META["label"]` : Instruction SQL, Compression ZIP, Aiguillage, Parallèle, Jonction. Renommer, et si oui dans quel lot ?
7. « En cours · 62 % » : le pourcentage n'existe que dans le rappel `on_progress`, ni par étape ni en base. Abandonner, ou ajouter une colonne à B1 ?
8. Le bouton d'ajustement du zoom (C11) et « Prochaines exécutions » (C10) n'ont pas de pastille mais n'existent pas.
9. La Grammaire remplace le badge d'icône rond du nœud par un point : confirmer la disparition des icônes de type sur le canevas.
10. « Abandonner après 5 min » est relié à `timeout_s`, qui limite chaque tentative et non l'étape entière. Changer le libellé ou le comportement ?
11. Les lignes de `log_text` sont horodatées en UTC au moment de l'écriture (`PipelineResult.log`). Les afficher dans le fuseau réglé demande de les relire et convertir ; accepté, ou B1 suffit pour le journal de l'étape ?

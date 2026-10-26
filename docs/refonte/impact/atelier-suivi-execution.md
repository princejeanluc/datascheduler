# Note d'impact : lot atelier-suivi-execution — suivre une exécution (succès, échec, en cours)

## Contexte

Suite à C9 (Atelier-echec, déjà livré) : l'utilisateur fait remarquer que la vue d'un run existe
aujourd'hui seulement pour les échecs, alors que le besoin réel est de **suivre une exécution**,
quel que soit son statut — en direct si elle tourne encore, sur ses données une fois terminée
(succès compris). Discussion complémentaire : une exécution doit se comporter comme une version
figée du pipeline au moment où elle a tourné, indépendante des modifications faites depuis (y
compris pendant qu'elle tourne).

Deux constats issus de la relecture du code, avant d'écrire quoi que ce soit :

1. **L'exécution elle-même est déjà protégée.** `run_pipeline()` (`core/pipeline.py:1626`) charge
   `steps = db.get_steps(pipeline_id)` **une seule fois**, en mémoire, au tout début du run. Les
   exécuteurs (`_execute_linear`, `_execute_graph`, `_execute_graph_parallel`) travaillent sur
   cette liste Python, jamais requêtée à nouveau. Une modification enregistrée pendant qu'un run
   tourne ne peut pas changer son comportement. Rien à corriger ici.
2. **Le trou est côté affichage.** La vue d'un run (C9) reconstruit aujourd'hui le canevas depuis
   `db.get_steps`/`db.get_edges` **actuels** (`_load_graph()`), puis superpose les résultats par
   étape (B1, `pipeline_run_steps`) par correspondance `step_key`. Si la config d'une étape change
   après le run (ou si l'étape est supprimée), la vue du run montre l'état d'aujourd'hui, pas celui
   qui a réellement tourné. Précédent existant dans le code : `_step_fingerprint()` /
   `_edges_fingerprint()` (`core/pipeline.py:362-375`), utilisés aujourd'hui uniquement pour
   invalider une **reprise** quand le pipeline a changé depuis l'échec — même idée, portée plus
   étroite (une empreinte, pas le contenu ; seulement pour les runs repris).

Autre constat utile : l'infrastructure de suivi en direct existe déjà en partie —
`start_polling()`/`stop_polling()`/`_poll_executing_step()` (`graph_editor_widget.py:136-153`,
« traçage lumineux ») fait déjà vivre un `QTimer` réglé sur `AppSettings.trace_glow_refresh_s`
pendant qu'un pipeline s'exécute en mode édition normale. Ce lot l'étend à la vue d'un run plutôt
que d'inventer un second mécanisme de sondage.

## Ce que le lot change

1. **Photo figée par run (D, extension au-delà de D1/B1).** Nouvelle colonne
   `pipeline_runs.graph_snapshot_json` (TEXT NULL), écrite une fois au début de chaque run, à
   partir des `steps`/`edges` déjà chargés en mémoire dans `run_pipeline()` — config complète de
   chaque étape (pas seulement une empreinte comme `resumable_state_json`), liaisons. Contrairement
   à `resumable_state_json`, jamais purgée : c'est un historique permanent, pas un état de reprise
   transitoire.
2. **La vue d'un run lit la photo quand elle existe.** `_load_graph()` devient capable de
   construire la scène depuis une liste de steps/edges fournie (décodée du snapshot) plutôt que de
   toujours interroger la base en direct. Sans snapshot (run antérieur à ce lot, ou ancien worker
   qui ne l'écrit pas) : repli sur le comportement actuel, inchangé.
3. **Étape supprimée depuis l'exécution, rendue visible.** Cas résiduel sans snapshot (runs
   antérieurs à ce lot) : une ligne de `pipeline_run_steps` sans correspondance dans le graphe
   vivant n'est plus silencieusement ignorée — une mention explicite apparaît (où exactement : voir
   « Questions ouvertes »).
4. **`_apply_run_view` accessible pour un run réussi, pas seulement en échec.** Le gros du code
   (`node_status_text`, `node_card_state`, `edge_run_state`) fonctionne déjà pour `SUCCESS` — seul
   le panneau d'échec est conditionné à `failed_step_key`. Ce qui manque : un point d'entrée. Or
   `Historique.md` dit explicitement, dans sa section « À garder tel quel », point 3 : *« Voir dans
   le graphe » n'apparaît que si le run est `FAILED` et a un `failed_step_key`* — un choix de
   contrat documenté, pas un oubli. L'étendre aux runs réussis est donc un changement de contrat
   assumé, pas un simple ajout (voir « Questions ouvertes »).
5. **Suivi en direct (run `RUNNING`).** Réutilise `start_polling`/`stop_polling` : tant que
   `run.status == "RUNNING"`, un timer relit `db.get_run_steps(run_id)`/`db.get_run(run_id)` au même
   intervalle que le traçage lumineux existant, ré-applique les statuts nœud/liaison, et s'arrête
   dès que le statut devient terminal (la vue se fige sur l'état final, comme pour un run déjà
   terminé).

## Fichiers touchés

| Fichier | Nature du changement |
|---|---|
| `database/models.py` | `PipelineRun.graph_snapshot_json` Text nullable (nouvelle colonne) |
| `database/db_manager.py` | migration `_migrate()` (ALTER TABLE ADD COLUMN) ; `create_run()` accepte `graph_snapshot_json=None` optionnel |
| `core/pipeline.py` | `_build_graph_snapshot_json(steps, edges)` (parallèle à `_build_resumable_state_json`, contenu complet au lieu d'empreintes), appelé dans `run_pipeline()` juste après le chargement de `steps`/`edges`, transmis à `create_run(...)` |
| `ui/graph_editor/graph_editor_widget.py` | `_load_graph()` paramétrable (source steps/edges alternative) ; `_apply_run_view()` étendu (étape orpheline, démarrage du polling si `RUNNING`) ; nouvelle méthode de sondage réutilisant `start_polling`/`stop_polling` |
| `ui/main_window/history_view.py` | nouveau point d'entrée « Voir dans le graphe » pour un run réussi (sous réserve de validation du point 4 ci-dessus) |
| `docs/refonte/ecrans/Historique.md` | section « À garder tel quel » point 3 à réviser si le point 4 est validé (le contrat documenté change) |
| `tests/test_run_status.py`, `test_graph_editor_run_view.py`, `test_atelier_pipelines_view.py`, `test_history_view.py` (noms à confirmer par grep) | revérifiés en premier ; tests ajoutés pour chaque point ci-dessus |

## Base de données

- Changement de schéma : colonne `pipeline_runs.graph_snapshot_json` TEXT NULL, ajoutée en pur
  ajout (`ALTER TABLE ... ADD COLUMN`), aucune valeur par défaut nécessaire (NULL = « pas de
  photo pour ce run », comportement de repli).
- Une base 0.45.0 s'ouvre sans erreur : runs antérieurs à `NULL`, lus comme aujourd'hui (repli sur
  le graphe vivant) — même filet de sécurité que B1, vérifié par un test de migration sur une
  copie de base 0.45.0.
- L'ancien worker tolère le nouveau schéma : oui. Colonne nullable, aucune contrainte ; un ancien
  worker qui ne la peuple pas laisse simplement `NULL` (repli automatique). Un ancien worker lisant
  une base migrée par la nouvelle interface n'est pas affecté (il ignore une colonne absente de son
  propre modèle SQLAlchemy).

## Format d'export

Aucun changement. Les runs ne sont pas exportés (confirmé par B1) : `.dspipeline` inchangé.

## Heures affichées

Aucune heure nouvelle affichée par ce lot (les horodatages du run-view viennent déjà de B1/A9,
déjà convertis).

## Noms publics

- `_apply_run_view`, `_load_graph`, `start_polling`/`stop_polling` : noms conservés, signatures
  étendues avec des paramètres optionnels seulement — comportement actuel strictement inchangé
  pour tout appelant qui ne passe pas ces nouveaux paramètres (vérifié par grep des appelants
  avant modification).
- `open_atelier_requested` / `open_atelier_run_requested` (Historique, Dashboard) : signatures
  inchangées ; seul l'endroit où le bouton/lien apparaît change (gated par statut, pas par la
  signature du signal).

## Tests

- Tests existants concernés (à revérifier verts avant/après, grep à refaire au moment du code) :
  `test_run_status.py`, `test_node_run_visual.py`, `test_graph_editor_run_view.py`,
  `test_atelier_pipelines_view.py`, tests de migration de `database/db_manager.py`, tests
  d'historique touchant `_open_graph`/« Voir dans le graphe ».
- Tests ajoutés : écriture du snapshot à la création d'un run (linéaire, graphe, parallèle) ;
  repli sur le graphe vivant quand le snapshot est `NULL` ; rendu depuis le snapshot quand il
  existe et que le pipeline a changé depuis ; étape supprimée affichée explicitement ; nouveau
  point d'entrée pour un run réussi ; timer de sondage qui s'arrête à la sortie de `RUNNING`.

## Dépendances et build

Aucune dépendance ajoutée.

## Risques et retour arrière

- Risque : `_load_graph()` modifié pourrait affecter l'édition normale si le nouveau paramètre
  n'est pas strictement neutre par défaut — mitigation : seul le chemin run_id+snapshot change de
  branche, tout le reste du code (y compris l'édition sans `run_id`) appelle `_load_graph()`
  exactement comme avant.
- Risque : grossissement de la base — un JSON par run (pas seulement à l'échec comme
  `resumable_state_json` aujourd'hui). Taille attendue modeste (config d'un pipeline, quelques Ko
  au pire) ; aucune purge/TTL prévue dans ce lot (noté en question ouverte, pas bloquant).
- Retour arrière : la colonne n'est jamais supprimée (règle du projet) ; en cas de problème, on
  peut cesser de l'écrire/la lire par un simple retrait de code, sans migration arrière.

## Questions ouvertes

1. **Étendre « Voir dans le graphe » aux runs réussis change un point documenté comme « à garder
   tel quel » dans `Historique.md` (point 3).** Je recommande de l'étendre (c'est tout le sens de
   la demande de ce lot), mais ça suppose de mettre à jour cette ligne de la fiche en même temps
   que le code plutôt que de la laisser se contredire avec le comportement livré — à confirmer.
2. **Panneau latéral pour un run réussi.** C9 ne construit un panneau que pour l'échec
   (`RunFailurePanel`). Pour un succès : rien (seulement canevas + chronogramme), ou un petit
   résumé positif (durée totale, lignes traitées, déclenchement) ? Pas dans la fiche C9 actuelle —
   proposition : rien de nouveau pour ce lot (le chronogramme + le statut par nœud suffisent déjà
   à « voir les données de l'exécution » demandé), un panneau de résumé pourrait être un lot
   distinct si le besoin se confirme à l'usage.
3. **Politique de purge/TTL de `graph_snapshot_json`** dans le temps (pipelines très fréquents) :
   pas tranchée ici, explicitement hors périmètre de ce lot.
4. **Emplacement exact de la mention « étape supprimée depuis cette exécution »** (point 3 ci-
   dessus de la section « Ce que le lot change ») : dans le panneau Journal existant, ou une ligne
   dédiée au-dessus du canevas ? À trancher au moment du code, pas structurant pour la validation
   de cette note.

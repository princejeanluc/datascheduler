# Note d'impact : lot B1 — table `pipeline_run_steps`

## Ce que le lot change
Implémente **B1** (`docs/refonte/DONNEES.md::D1`, fiche Atelier) : une nouvelle table
`pipeline_run_steps`, une ligne par étape exécutée OU sautée pendant un run. Aujourd'hui
`PipelineRun` ne garde que l'étape COURANTE et celle en ÉCHEC (`current_step_key`/
`failed_step_key`) — rien par étape, pas d'historique. Ce lot ajoute cet historique, prérequis
des items Lot C de l'Atelier (C1 onglet Historique, C8 chronogramme, C9 vue d'un run en échec)
et d'autres écrans (Aujourd'hui, Historique section Étapes, Palette) qui ne sont PAS construits
dans ce lot — B1 écrit seulement la donnée, personne ne la lit encore côté UI.

**Pur ajout** : aucune colonne existante modifiée, aucun comportement d'exécution changé pour
l'utilisateur (même ordre, mêmes retries, mêmes règles de skip/échec — vérifié par la suite de
tests existante, intégralement verte sans modification de ses assertions).

## Schéma
Nouvelle table (création par `Base.metadata.create_all()`, appelée à chaque `init_db()` — crée
seulement les tables manquantes, une base 0.45.0 n'a donc rien de spécial à migrer) :

| Colonne | Type | Remarque |
|---|---|---|
| `id` | INTEGER PK | |
| `run_id` | INTEGER NOT NULL, indexé | FK `pipeline_runs.id` |
| `step_key` | VARCHAR(36) nullable | absent pour une étape "keyless" (résiduelle, sans arête possible) |
| `step_type` | VARCHAR(50) nullable | |
| `step_label` | VARCHAR(255) nullable | libellé au moment du run |
| `status` | VARCHAR(20) | SUCCESS, FAILED, SKIPPED, SKIPPED_RESUME, CANCELLED |
| `attempts` | INTEGER défaut 1 | |
| `attempts_json` | TEXT nullable | `[{"n", "started_at", "finished_at", "error"}]` |
| `started_at`/`finished_at` | DATETIME nullable | UTC naïf, comme `PipelineRun` |
| `rows_count` | INTEGER nullable | `ctx.rows_count` au moment où cette étape finit |
| `output_path`/`output_size_bytes` | VARCHAR(500)/INTEGER nullable | |
| `port_taken` | VARCHAR(50) nullable | sortie de passerelle ou port d'erreur emprunté |
| `error_message` | TEXT nullable | sans aucun secret, même garantie que `PipelineRun` |
| `reused_from_resume` | BOOLEAN défaut False | vrai pour une étape SKIPPED_RESUME |

`PipelineRun.run_steps` (nouvelle relation, `cascade="all, delete-orphan"`) : supprimer un run —
directement, ou via la cascade déjà existante `Pipeline.runs` — supprime aussi ses lignes
`pipeline_run_steps`. Testé explicitement (`test_deleting_a_pipeline_cascades_to_its_run_steps`).

## Écriture
`core/pipeline.py::_record_run_step` (nouvelle, jamais fatale — même garde que
`_trigger_downstream_pipelines`/`_persist_active_steps`), appelée à CHAQUE point de décision des
3 moteurs :
- **`_execute_linear`** : SKIPPED_RESUME (étape déjà réussie, reprise), SKIPPED (pipeline déjà en
  échec, étape pas `run_always`), SUCCESS/FAILED/CANCELLED après `_run_step_with_policy`.
- **`_execute_graph`** : + SKIPPED (branche non sélectionnée ou dépendance en échec/sautée), +
  FAILED (jonction ET dont une branche entrante n'a pas abouti). `port_taken` vient directement de
  `step_result.active_port`, déjà calculé par ce moteur.
- **`_execute_graph_parallel`** : mêmes statuts, répartis entre `_resolve_skip`/
  `_resolve_join_failure` (résolution immédiate, hors thread) et la résolution de
  `results_queue` dans la boucle principale (après qu'un thread worker a terminé) — jamais depuis
  un thread lui-même, cohérent avec la règle existante "seul ce coordinateur touche `ctx`".
  Les étapes "keyless" (résiduelles, exécutées séquentiellement en fin de fonction) sont aussi
  couvertes, avec `step_key=None`.

`_run_step_with_policy` retourne désormais `(step_result, attempts_log)` au lieu de `step_result`
seul — `attempts_log` horodate CHAQUE tentative réelle (une boucle de retry en logue plusieurs).
Signature changée, 4 points d'appel internes + 2 tests qui l'appellent directement mis à jour
(T1).

## Base de données
- Changement de schéma : une table neuve, aucune colonne existante touchée.
- Une base 0.45.0 s'ouvre et fonctionne : testé explicitement
  (`test_a_045_style_database_gets_the_new_table_created`, même patron que les tests de migration
  existants de `test_db_manager.py`).
- Un ancien worker (ne connaît pas cette table) : n'écrit jamais dedans, un run qu'il exécute
  n'a simplement aucune ligne — toléré par construction (rien ne lit encore cette table).

## Format d'export
Aucun changement — les runs ne sont jamais exportés (`.dspipeline` ne contient que la définition
du pipeline), donc `pipeline_run_steps` n'a rien à y faire.

## Noms publics
`_run_step_with_policy` change de signature (retour `(step_result, attempts_log)`) — fonction
privée du module, aucun appelant hors de `core/pipeline.py` et de 2 tests qui l'appellent
directement (mis à jour). Tous les autres noms publics inchangés.

## Tests
Nouveau fichier `tests/test_pipeline_run_steps.py` (8 tests) : migration 0.45.0, écriture par
moteur (linéaire avec et sans retry, graphe avec branche de CONDITION non sélectionnée,
parallèle), reprise (`reused_from_resume`), cascade de suppression.

Revérifiés verts, sans modification de leurs assertions existantes (sauf les 2 citées) :
`test_pipeline_graph_engine.py`, `test_pipeline_graph_engine_parallel.py`,
`test_pipeline_resume.py`, `test_cooperative_cancellation.py` (2 assertions complétées, pas
retirées — `len(attempts_log)` ajouté), `test_dry_run.py`, `test_dynamic_producer_chaining.py`,
`test_export_import.py`, `test_import.py`, et la suite complète.

## Dépendances et build
Aucune dépendance ajoutée.

## Risques et retour arrière
Risque principal : une erreur dans `_record_run_step` qui ferait échouer un run réel — mitigé par
le `try/except` large (jamais fatal, journalisé seulement) et par le fait que `result.run_id` est
vérifié avant tout appel DB. Aucun changement de comportement d'exécution observable par
l'utilisateur. Retour arrière : revert des commits de ce lot ; la table neuve peut rester en base
sans effet (rien ne la lit).

## Suite
Ce lot ne construit AUCUN écran. La suite logique (choisie avec l'utilisateur) : reprendre les
items A6-A16 de la frame Main de l'Atelier, puis les items C qui dépendent de cette table
(Atelier-echec/C9, Atelier-etape/C1).

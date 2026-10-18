# Changements de données : schéma de référence

Plusieurs écrans ont besoin des mêmes nouvelles données (résultat par étape, origine d'un run). Ce fichier les fixe une seule fois. Les fiches d'écran y renvoient.

Toutes les règles de `REGLES.md` section 4 s'appliquent : ajout seulement, colonnes nullables ou avec valeur par défaut, migration dans `database/db_manager.py::_migrate` (ou `create_all` pour une table nouvelle), aucun changement du format d'export.

## D1. Résultat de chaque étape d'un run

Nouvelle table `pipeline_run_steps`, une ligne par étape exécutée (ou sautée) dans un run.

| Colonne | Type | Remarque |
|---|---|---|
| `id` | INTEGER PK | |
| `run_id` | INTEGER NOT NULL, indexé | `pipeline_runs.id` |
| `step_key` | VARCHAR(255) | |
| `step_type` | VARCHAR(50) | |
| `step_label` | VARCHAR(255) NULL | libellé au moment du run |
| `status` | VARCHAR(20) | `RUNNING`, `SUCCESS`, `FAILED`, `SKIPPED` (branche non prise), `SKIPPED_RESUME` (déjà faite avant une reprise), `CANCELLED` |
| `attempts` | INTEGER DEFAULT 1 | |
| `attempts_json` | TEXT NULL | `[{"n", "started_at", "finished_at", "error"}]` |
| `started_at`, `finished_at` | DATETIME NULL | UTC naïf |
| `rows_count` | INTEGER NULL | depuis `ctx.rows_count` |
| `output_path` | VARCHAR(500) NULL | |
| `output_size_bytes` | INTEGER NULL | |
| `port_taken` | VARCHAR(50) NULL | sortie d'une passerelle ou port d'erreur emprunté |
| `error_message` | TEXT NULL | sans aucun secret |

Écriture : une fonction `db.record_run_step(...)` appelée autour de `_run_step_with_policy` dans `_execute_linear`, `_execute_graph` et `_execute_graph_parallel` (`core/pipeline.py`).

Utilisée par : Atelier (statut sous les nœuds, chronogramme), Aujourd'hui (parcours d'un run), Historique (section Étapes), Palette (taille d'un fichier produit).

Compatibilité :
- un run d'avant la refonte n'a aucune ligne : les écrans affichent l'état du run seul, sans erreur ;
- un ancien worker n'écrit pas dans la table : ses runs s'affichent comme des runs anciens ;
- `delete_pipeline` doit supprimer ces lignes avec les runs (pas de clé étrangère active en SQLite ici).

## D2. Origine d'un run

Colonnes ajoutées à `pipeline_runs` :

| Colonne | Type | Valeurs |
|---|---|---|
| `trigger_origin` | VARCHAR(20) NULL | `SCHEDULED`, `MANUAL`, `TRIGGERED`, `CATCHUP`, `RESUME` |
| `triggered_by_run_id` | INTEGER NULL | run parent quand `TRIGGERED` |
| `scheduled_for` | DATETIME NULL | heure prévue, UTC naïf, quand `SCHEDULED` ou `CATCHUP` |

Écriture : paramètre `origin=None` sur `run_pipeline`, `create_run` et `PipelineScheduler.trigger_now`. Le worker lit une clé `origin` facultative dans la commande `RUN_NOW`. Un ancien émetteur ne l'envoie pas : la valeur reste `NULL` et s'affiche « — », sauf si `resumed_from_run_id` est renseigné (« reprise du #N »).

Utilisée par : Aujourd'hui, Historique.

## D3. Journal à niveaux

Colonne ajoutée à `pipeline_runs` : `log_json` TEXT NULL, liste de `{"t": ISO UTC, "lvl": "INFO|WARN|ERROR|OK", "step_key", "msg"}`. `log_text` continue d'être écrit à l'identique.

Run d'avant la refonte : on lit `log_text` ligne à ligne ; niveau `ERROR` si la ligne contient « ERREUR : », sinon `INFO` ; heure recomposée avec la date de `started_at`, en gérant le passage de minuit.

Utilisée par : Historique, Aujourd'hui, Atelier (journal d'une étape).

## D4. Dernière fermeture de Kulu

`app_settings.last_closed_at` DATETIME NULL (UTC), écrit à la sortie de l'application. Utilisée par Aujourd'hui (« Kulu était fermé entre … »).

## D5. Tables propres à un écran

Décrites dans la fiche de l'écran, à créer seulement si le lot C correspondant est retenu : `recent_items` (Palette), `pipeline_drafts` (Atelier, brouillon), historique des tests de connexion (Connexions), audit étendu (Historique).

## Ordre conseillé

D1, D2 et D3 dans un même lot, car ils touchent tous `core/pipeline.py`. Le lot comprend un test qui ouvre une copie d'une base 0.45.0, vérifie la migration, puis relit un ancien run sans erreur.

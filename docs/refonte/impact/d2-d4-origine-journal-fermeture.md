# Note d'impact : lot d2-d4-origine-journal-fermeture — origine du run, journal à niveaux, dernière fermeture

## Ce que le lot change

Lot D (étape 3 du plan, `LOTS.md`) : trois ajouts de données, purement additifs, sans aucun écran
livré — les futurs lots C (C-Historique, C-Aujourd'hui, Atelier) les consommeront. D1 (résultat
par étape, `pipeline_run_steps`) est déjà fait, livré comme B1 dans le lot C9. Ce lot fait D2, D3
et D4, comme `DONNEES.md::Ordre conseillé` le recommande (tous touchent `core/pipeline.py`).

1. **D2 — Origine d'un run.** `pipeline_runs` gagne `trigger_origin` (`SCHEDULED`, `MANUAL`,
   `TRIGGERED`, `CATCHUP`, `RESUME`), `triggered_by_run_id`, `scheduled_for`. Un paramètre
   `origin=None` traverse `run_pipeline()` → `create_run()`. `trigger_now()` prend `origin="MANUAL"`
   par défaut (son usage le plus courant) et un `triggered_by_run_id=None` optionnel. Chaque
   appelant fixe l'origine réelle :
   - `_run_scheduled_pipeline` (job APScheduler) → `"SCHEDULED"`, `scheduled_for` = la valeur de
     `pipeline.next_run_at` lue avant que cette exécution ne la fasse avancer (à vérifier au
     moment du code : `next_run_at` doit encore porter l'heure prévue à cet instant précis, pas
     la suivante).
   - `RunProgressDialog`/`RunProgressThread.run()` (appel direct à `run_pipeline`, hors
     scheduler) → `"MANUAL"`.
   - `MissedPipelinesDialog._on_launch_selected` (`scheduler.trigger_now(pipeline_id)`) →
     `"CATCHUP"`.
   - `_trigger_downstream_pipelines(parent_pipeline_id, parent_status)` (`core/pipeline.py`,
     appelle `trigger_now(child.id)`) → `"TRIGGERED"` avec `triggered_by_run_id` = l'id du run
     parent. Cette fonction n'a aujourd'hui pas accès à cet id : ajout d'un paramètre
     `parent_run_id=None`, à faire passer par ses 3 points d'appel internes (`run_id` déjà en
     portée à chacun, confirmé par exploration).
   - `resume_from_run_id` fourni à `run_pipeline()` → `"RESUME"`, toujours, quel que soit l'
     `origin` par ailleurs transmis (dérivé, pas une valeur que l'appelant choisit).
   - Worker en arrière-plan : `request_run_now()` ajoute une clé `origin` facultative au payload
     JSON de la commande `RUN_NOW` (aujourd'hui `{"pipeline_id": ...}` seul) ; côté réception,
     `_poll_worker_commands()` lit `payload.get("origin") or "MANUAL"` — un ancien émetteur (sans
     cette clé) retombe sur `"MANUAL"`, jamais une exception.
   - **À reprendre avant de coder** : `grep` exhaustif de tous les appelants de `trigger_now(` et
     `request_run_now(` (celui listé ci-dessus vient d'une exploration, pas garanti complet) pour
     confirmer qu'aucun ne casse avec les nouveaux paramètres par défaut.

2. **D3 — Journal à niveaux.** `pipeline_runs.log_json` (TEXT NULL), liste de `{"t", "lvl",
   "step_key", "msg"}`. `PipelineResult.log(msg)` devient `log(msg, lvl="INFO", step_key=None)` :
   construit en parallèle `self.log_entries` (liste de dicts) en plus de `self.log_lines` (déjà
   existant, inchangé). `fail(msg)` (qui appelle déjà `self.log(f"ERREUR : {msg}")`) passe
   `lvl="ERROR"`. Nouvelle propriété `log_json` (= `json.dumps(self.log_entries)`), transmise aux
   deux points d'écriture existants : `finish_run(...)` (nouveau paramètre `log_json=None`) et
   `update_run_progress(...)` (incrémental, même patron que `log_text` aujourd'hui). `WARN`/`OK`
   sont des valeurs possibles par le schéma mais ne sont affectées nulle part dans ce lot — les
   lots C qui consommeront `log_json` pourront les utiliser plus tard sans migration
   supplémentaire ; rien dans le code actuel ne distingue encore un avertissement d'une simple
   information. `log_text` continue d'être écrit à l'identique (B1/D1 : jamais retiré, toujours la
   source pour un run d'avant ce lot).

3. **D4 — Dernière fermeture de Kulu.** `app_settings.last_closed_at` (DATETIME NULL, UTC).
   `update_app_settings(**kwargs)` est déjà générique (`setattr` par clé) : aucun changement de
   `db_manager.py` au-delà de la colonne sur le modèle. Écriture dans
   `ui/main_window/window.py::run()`, via `app.aboutToQuit.connect(...)` posé avant
   `app.exec()` — pas un `MainWindow.closeEvent`, pour couvrir aussi une sortie qui ne passe pas
   par la fermeture de la fenêtre (ex. Alt+F4 système, signal de fermeture de session Windows).

## Découverte notable (hors périmètre, à signaler) : `scheduler.stop()` jamais atteint

En lisant le point d'arrêt de l'application pour D4, `main.py` lignes ~116-122 :
`ui.main_window.run()` appelle `sys.exit(app.exec())`, qui lève `SystemExit` — cette exception
remonte à travers `run()` et sort de `main()` directement, donc les lignes qui suivent
(`if scheduler: scheduler.stop()`) ne s'exécutent jamais sur un arrêt normal. Pré-existant, sans
rapport avec D4 (le `aboutToQuit` ajouté par ce lot n'en dépend pas et fonctionne indépendamment).
**Pas touché dans ce lot** (REGLES.md section 5) — signalé dans la PR, section « Hors périmètre
repéré », pour une correction séparée si souhaitée.

## Fichiers touchés

| Fichier | Nature du changement |
|---|---|
| `database/models.py` | `PipelineRun.trigger_origin`, `triggered_by_run_id`, `scheduled_for`, `log_json` ; `AppSettings.last_closed_at` |
| `database/db_manager.py` | migration `_migrate()` (4 `ALTER TABLE ADD COLUMN`, pattern déjà établi) ; `create_run()` gagne `trigger_origin=None`, `triggered_by_run_id=None`, `scheduled_for=None` ; `finish_run()` gagne `log_json=None` ; `update_run_progress()` gagne `log_json=None` |
| `core/pipeline.py` | `PipelineResult.log()`/`fail()`/nouvelle propriété `log_json` ; `run_pipeline()` gagne `origin=None`, `triggered_by_run_id=None`, `scheduled_for=None`, dérive `"RESUME"` si `resume_from_run_id` ; `_trigger_downstream_pipelines()` gagne `parent_run_id=None`, ses 3 appelants internes le transmettent |
| `core/scheduler.py` | `trigger_now()` gagne `origin="MANUAL"`, `triggered_by_run_id=None` ; `_run_scheduled_pipeline` passe `origin="SCHEDULED"` + `scheduled_for` ; `_poll_worker_commands()` lit `payload.get("origin")` |
| `core/execution_mode.py` | `request_run_now()` gagne `origin=None`, ajouté au payload JSON de `RUN_NOW` |
| `ui/dialogs/run_progress_dialog.py` | `RunProgressThread`/l'appel à `run_pipeline()` passe `origin="MANUAL"` |
| `ui/dialogs/missed_pipelines_dialog.py` | `_on_launch_selected` passe `origin="CATCHUP"` à `trigger_now()` |
| `ui/main_window/window.py` | `run()` : `app.aboutToQuit.connect(...)` avant `app.exec()` |
| `tests/` | nouveaux tests par item (voir plus bas) ; aucun test existant ne doit changer de valeur attendue (ajout pur de colonnes et de paramètres à défaut rétrocompatible) |

## Base de données

- Changement de schéma : 4 colonnes nullables ajoutées par pur `ALTER TABLE` — 3 sur
  `pipeline_runs` (`trigger_origin`, `triggered_by_run_id`, `scheduled_for`, `log_json` — 4 en
  tout sur cette table), 1 sur `app_settings` (`last_closed_at`). Aucune valeur par défaut
  nécessaire (`NULL` = information absente, affichée « — » par les futurs écrans qui la
  consomment, déjà le principe retenu pour toutes les colonnes similaires de ce projet).
- Une base 0.45.0 s'ouvre sans erreur : runs et réglages antérieurs à `NULL`, mêmes test de
  migration que les lots précédents (copie de base 0.45.0, `_migrate()`, relecture sans erreur).
- L'ancien worker tolère le nouveau schéma : oui. Colonnes nullables, aucune contrainte. Un ancien
  worker qui envoie `RUN_NOW` sans la clé `origin` fonctionne (`payload.get("origin")` tolère son
  absence) ; une nouvelle interface qui lit une base écrite par un ancien worker voit simplement
  `trigger_origin = NULL` pour ces runs-là.

## Format d'export

Aucun changement. Les runs ne sont pas exportés (B1/D1 déjà confirmé) ; `app_settings` non plus.

## Heures affichées

Aucune heure affichée par ce lot (pas d'écran livré). `scheduled_for` et `last_closed_at` sont
stockées en UTC naïf, comme tout le reste de `pipeline_runs`/`app_settings` — la conversion vers
le fuseau réglé sera la responsabilité du futur écran qui les affiche, via la fonction partagée
existante (`FONDATIONS.md`), pas de ce lot.

## Noms publics

- `create_run`, `finish_run`, `update_run_progress`, `run_pipeline`, `trigger_now`,
  `request_run_now` : tous des paramètres **additionnels à valeur par défaut** — aucun appelant
  existant (grep à refaire au moment du code) ne doit changer de comportement sans passer les
  nouveaux arguments.
- `_trigger_downstream_pipelines` : nouveau paramètre `parent_run_id=None` — fonction privée
  (préfixe `_`), seuls ses 3 appels internes à `core/pipeline.py` à mettre à jour.

## Tests

- Tests existants concernés (à revérifier verts avant/après, grep à refaire au moment du code) :
  tous les tests de `core/pipeline.py` appelant `run_pipeline`/`create_run`/`finish_run` (très
  nombreux, voir `tests/test_pipeline_*.py`, `tests/test_db_manager.py`), `tests/test_scheduler*.py`
  pour `trigger_now`, `tests/test_missed_pipelines_dialog.py`, `tests/test_run_progress_dialog.py`.
- Tests ajoutés : migration des 4 nouvelles colonnes sur une base « legacy » (même patron que
  `test_run_graph_snapshot.py`) ; `trigger_origin` correct pour chacune des 5 origines (planifié,
  manuel, déclenché avec `triggered_by_run_id`, rattrapé, repris) ; un run à `NULL` (appel sans
  `origin`) ; `log_json` contient les entrées `INFO`/`ERROR` attendues, dans l'ordre, avec
  `step_key` quand fourni ; `last_closed_at` écrit par `aboutToQuit` (test Qt, émettre le signal
  manuellement plutôt que fermer un vrai processus).

## Dépendances et build

Aucune.

## Risques et retour arrière

- Risque principal : paramètres additionnels mal répercutés chez un appelant oublié (ex. un
  script ou un test qui appelle `trigger_now` directement) — mitigation : grep exhaustif avant de
  changer les signatures, pas seulement les appelants déjà identifiés par l'exploration.
- Risque : `app.aboutToQuit` ne se déclenche pas sur un arrêt brutal (kill du process, crash) —
  accepté, `last_closed_at` resterait alors à sa valeur précédente, ce qui est déjà le comportement
  voulu par la fiche (« Kulu était fermé entre … » reste une estimation, jamais une garantie).
- Retour arrière : aucune colonne supprimée (règle du projet) ; en cas de problème, cesser
  d'écrire/lire les nouveaux champs sans migration arrière.

## Questions ouvertes

- Aucune contradiction fiche/code/maquette trouvée — ce lot ne livre aucun écran, donc aucune
  maquette à comparer. Le seul point à vérifier précisément au moment du code (pas bloquant pour
  valider cette note) : la valeur exacte de `scheduled_for` pour un run `SCHEDULED` dépend de ce
  que `pipeline.next_run_at` porte encore au moment où `_run_scheduled_pipeline` s'exécute, avant
  recalcul — à confirmer en lisant `core/scheduler.py` en détail à ce moment-là plutôt qu'en le
  supposant ici.

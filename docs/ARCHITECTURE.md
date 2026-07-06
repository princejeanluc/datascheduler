# Architecture de DataScheduler

> Public visé : vous, dans 6 mois, quand vous aurez oublié pourquoi c'est fait comme ça.
> Ce document explique **comment le projet est construit**, pas ce qu'il fait pour l'utilisateur
> (pour ça, voir `docs/Description.md` et `docs/architecture_prod.md`, qui décrivent le besoin
> métier d'origine — un peu datés depuis l'architecture à base de steps, mais toujours valables
> pour comprendre le "pourquoi" initial).

## En une phrase

Une appli desktop Windows (PySide6, packagée en `.exe` via PyInstaller) qui exécute des
**pipelines** — des suites d'étapes configurables (Oracle, FTP, email, HTTP, scripts…) — à la
demande ou selon une planification, avec un historique complet en SQLite.

## Les 4 couches, et la règle qui les tient ensemble

```
ui/            ← présentation (PySide6) : fenêtres, dialogues, tableaux
core/          ← logique métier : Oracle, FTP, email, HTTP, planification, exécuteur de pipeline
core/steps/    ← les "briques" d'un pipeline (une classe par type d'étape)
database/      ← persistance : modèles SQLAlchemy + CRUD SQLite
```

**La règle à ne jamais casser** : `ui/` importe `core/` et `database/`, jamais l'inverse.
`core/` importe `database/`, jamais l'inverse. Un module de `core/` ou `database/` qui se met à
faire `from ui import ...` est un signe que quelque chose est mal placé — la logique métier doit
pouvoir tourner sans jamais ouvrir une fenêtre (c'est d'ailleurs exactement ce qu'on a fait tout
au long de cette session pour vérifier chaque step : les appeler directement en script Python,
sans lancer l'UI).

Concrètement, un import typique :
```python
# core/steps/oracle_execute.py
from database import db_manager as db      # ✅ core → database
from core.oracle import OracleConnector     # ✅ core → core

# ui/main_window.py
from database import db_manager as db      # ✅ ui → database
from core.scheduler import get_scheduler    # ✅ ui → core
```

## Le modèle de données

Tables SQLite (définies dans [database/models.py](../database/models.py)), toutes gérées par
SQLAlchemy :

```
OracleProfile ──┐
FtpProfile     ──┼──< SqlQuery (optionnel, lié à un OracleProfile)
SmtpProfile    ──┘
                                    ┌──< PipelineStep (step_type, config_json)
Pipeline ───────────────────────────┤
                                    └──< PipelineRun (historique d'exécution)
```

- **`OracleProfile` / `FtpProfile` / `SmtpProfile`** — des identifiants de connexion réutilisables
  entre plusieurs pipelines (host/port/user/password + spécificités par protocole). Trois classes
  quasi identiques, volontairement : c'est plus simple à lire que de les factoriser derrière une
  abstraction commune pour trois lignes de différence.
- **`SqlQuery`** — une requête SQL/PLSQL nommée et réutilisable, rattachée (optionnellement) à un
  profil Oracle par défaut.
- **`Pipeline`** — le conteneur nommé, planifié (`frequency`, `cron_expression`,
  `scheduled_time`...) et son dernier statut connu. Les colonnes `oracle_profile_id`,
  `sql_query_id`, `ftp_profile_id`, `remote_path_tpl`, `filename_tpl` sont **legacy** : elles
  dataient de la v0.1.0 (Oracle→FTP figé) et restent en base uniquement pour la migration
  automatique des anciens pipelines (voir plus bas). Un pipeline moderne ne les utilise pas — sa
  vraie configuration vit dans ses `PipelineStep`.
- **`PipelineStep`** — une étape d'un pipeline : `step_type` (une valeur de l'enum `StepType`),
  `step_order` (ordre d'exécution), `config_json` (un blob JSON libre, différent par type
  d'étape). **Important** : `config_json` n'est pas structuré au niveau de la base — SQLite ne
  sait pas qu'un `oracle_profile_id` dedans référence vraiment un `OracleProfile`. C'est une
  clé étrangère "molle", vérifiée à la main quand c'est utile (voir
  `find_pipelines_using_profile` dans [database/db_manager.py](../database/db_manager.py)).
- **`PipelineRun`** — une ligne d'historique par exécution : statut, durée, lignes exportées,
  log texte complet, message d'erreur.

## Le cœur du système : les steps

C'est l'idée qui a transformé DataScheduler d'un outil à fonction unique (Oracle→FTP) en petit
moteur d'orchestration générique. Trois pièces :

**1. `BaseStep` et `StepContext`** ([core/steps/base.py](../core/steps/base.py))
Chaque étape est une classe qui hérite de `BaseStep` et implémente une seule méthode :
```python
def run(self, ctx: StepContext, on_progress=None) -> StepResult: ...
```
`StepContext` est l'état partagé qui voyage d'étape en étape : le fichier produit par l'étape
précédente (`ctx.output_file`), le nombre de lignes, un dictionnaire libre `ctx.extra` pour tout
ce qui ne rentre pas ailleurs, et un log (`ctx.log(...)`). Une étape lit ce que la précédente y a
mis, et y écrit ce que la suivante pourra lire — c'est le seul canal de communication entre
étapes, il n'y en a pas d'autre.

**2. Le registre** ([core/steps/\_\_init\_\_.py](../core/steps/__init__.py))
```python
_REGISTRY = {
    "ORACLE_EXTRACT": OracleExtractStep,
    "FTP_UPLOAD":     FtpUploadStep,
    ...
}
def get_step(step_type: str, config: dict) -> BaseStep:
    return _REGISTRY[step_type](config)
```
Un dictionnaire qui associe un nom de type d'étape (string, stocké tel quel en base) à la classe
qui sait l'exécuter. Ajouter un type d'étape = ajouter une entrée ici (voir `docs/COOKBOOK.md`).

**3. L'exécuteur** ([core/pipeline.py](../core/pipeline.py), fonction `run_pipeline`)
Charge les `PipelineStep` d'un pipeline dans l'ordre, et pour chacune : résout son type via le
registre, l'exécute avec le `StepContext` courant, s'arrête au premier échec. C'est une boucle
`for` toute simple — pas de branchement conditionnel, pas de parallélisme. Si un jour vous voulez
du "si telle condition alors sauter telle étape", c'est ici qu'il faudra toucher, et ça changera
la nature de l'exécuteur (voir la section correspondante dans `docs/CONCEPTS.md`).

## Cycle de vie d'une exécution

Que ce soit un clic sur "Exécuter maintenant" ou un déclenchement planifié, le chemin est le
même à partir d'un moment :

```
[UI: clic "Exécuter"]  ou  [APScheduler: tick planifié]
        │
        ▼
run_pipeline(pipeline_id)          core/pipeline.py
        │
        ├─ db.create_run(...)                    → PipelineRun "RUNNING"
        ├─ pour chaque PipelineStep, dans l'ordre :
        │     get_step(step_type, config).run(ctx, on_progress)
        │     échec ? → on s'arrête, on enregistre l'erreur
        ├─ db.finish_run(..., status, log_text)   → PipelineRun terminé
        └─ met à jour Pipeline.last_status / last_run_at
```

La différence entre les deux déclencheurs est **qui** appelle `run_pipeline` et **sur quel
thread** :
- Un clic UI passe par [ui/dialogs.py](../ui/dialogs.py) `RunProgressDialog`, qui lance
  l'exécution dans un `QThread` dédié — sinon l'interface se figerait pendant toute la durée du
  pipeline (surtout gênant pour un `ORACLE_EXTRACT` de plusieurs minutes).
- Un déclenchement planifié passe par `PipelineScheduler` ([core/scheduler.py](../core/scheduler.py)),
  qui tourne déjà sur son propre thread de fond (APScheduler `BackgroundScheduler`).

## Le pont thread-safe scheduler → UI

Un problème classique de toute UI graphique : on ne touche **jamais** un widget Qt depuis un
thread qui n'est pas le thread principal — ça plante ou ça corrompt l'affichage de façon
imprévisible. Or le scheduler tourne sur son propre thread et doit prévenir l'UI qu'un run vient
de se terminer (pour rafraîchir les tableaux, afficher un message).

La solution, dans [ui/main_window.py](../ui/main_window.py) (`SchedulerNotifier`) : une classe
`QObject` avec des signaux Qt (`job_success`, `job_error`). Le scheduler appelle un simple
callback Python (`on_job_success(pipeline_id, path)`) depuis son thread ; ce callback ne fait
qu'`emit` un signal Qt. Qt garantit que le code connecté à ce signal (`_on_scheduler_success`)
s'exécute sur le thread principal, même si le signal a été émis depuis un thread différent.
C'est le pattern standard pour tout thread de fond qui doit parler à une UI Qt — retenez-le, vous
le referez à chaque nouvelle source d'événements asynchrones (un futur watcher de fichier, un
websocket, etc.).

## Persistance et migrations

SQLite, un seul fichier, situé dans `%APPDATA%/DataScheduler/datascheduler.db`
(`database/db_manager.py`, fonction `get_db_path`). Deux chemins de création coexistent :

1. **Nouvelle installation** : `Base.metadata.create_all(engine)` crée toutes les tables depuis
   les classes SQLAlchemy de `models.py`.
2. **Mise à jour d'une base existante** : la fonction `_migrate()` applique des `ALTER TABLE` /
   `CREATE TABLE IF NOT EXISTS` bruts en SQL, un par changement de schéma historique (ex :
   l'ajout de `pipeline_steps`, puis de `smtp_profiles`).

C'est un choix pragmatique (pas d'Alembic, pas de système de migration versionné) qui convient
tant que les migrations restent additives (nouvelle colonne avec valeur par défaut, nouvelle
table). Le jour où il faudra une migration destructive (renommer/supprimer une colonne), SQLite
n'a pas d'`ALTER COLUMN` — il faut reconstruire la table (déjà fait une fois pour `pipelines`,
voir `_migrate()`).

La fonction `_migrate_legacy_pipelines()` mérite une mention : elle convertit automatiquement,
au démarrage, les anciens pipelines "v0.1.0" (Oracle→FTP figé sur les colonnes legacy de
`Pipeline`) en `PipelineStep` équivalents — pour qu'un utilisateur qui avait déjà des pipelines
avant l'architecture à base de steps ne perde rien en mettant à jour l'appli.

## Packaging

[DataScheduler.spec](../DataScheduler.spec) pilote PyInstaller en mode **one-folder**
(`dist/DataScheduler/DataScheduler.exe` + un dossier `_internal/`), pas one-file — plus rapide au
démarrage, plus facile à déboguer si un import manque.

Point notable : `oracledb` tourne en **mode thin** — un pilote Oracle 100% Python, qui ne
nécessite pas d'installer le "Oracle Instant Client" sur chaque poste. C'est ce qui permet de
distribuer un simple dossier `.exe` sans prérequis d'installation côté utilisateur final.

PyInstaller ne détecte pas toujours tout seul les imports "dynamiques" (ceux qui ne sont pas des
`import X` visibles statiquement dans le code — par exemple les plugins internes d'`oracledb` ou
de `paramiko`) : c'est pour ça que le `.spec` liste des `hiddenimports` explicites. Si vous
ajoutez une nouvelle dépendance et que l'`.exe` plante au démarrage avec un `ModuleNotFoundError`
alors que `python main.py` fonctionne, c'est presque toujours ça — ajoutez le module manquant à
`hiddenimports` (voir `docs/COOKBOOK.md`).

## Arborescence commentée

```
main.py                    Point d'entrée : init DB → démarre le scheduler → lance l'UI
database/
  models.py                Toutes les tables SQLAlchemy
  db_manager.py            init_db(), migrations, et un helper CRUD par entité
core/
  oracle.py                Connexion Oracle + export CSV (OracleExporter) + chargement (OracleLoader)
  ftp.py                   Upload/download FTP-FTPS-SFTP
  email.py                 Envoi SMTP
  pipeline.py              run_pipeline() — l'exécuteur séquentiel de steps
  scheduler.py             PipelineScheduler — wrapper APScheduler
  steps/
    base.py                BaseStep, StepContext, StepResult
    __init__.py             Le registre _REGISTRY + get_step()
    <nom>.py                Une classe par type d'étape (9 aujourd'hui)
ui/
  main_window.py           Fenêtre principale, navigation, les 5 vues (Dashboard, Pipelines, ...)
  step_editor.py           Éditeur de pipeline : liste d'étapes + dialogues de config par type
  dialogs.py               Dialogues de profils (Oracle/FTP/SMTP) + requêtes SQL + run/log
  styles.py                Palette de couleurs + feuilles de style Qt (QSS)
DataScheduler.spec         Configuration PyInstaller
requirements.txt           Dépendances Python
docs/                      Vous êtes ici
```

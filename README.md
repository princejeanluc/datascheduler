# DataScheduler

Application de bureau Windows permettant d'automatiser des pipelines de données : extraction et
exécution SQL multi-SGBD (Oracle, MySQL, PostgreSQL, SQL Server), transferts FTP/FTPS/SFTP,
notifications email, appels HTTP, scripts Python — enchaînés en séquence ou en graphe, selon vos besoins.  
Développée avec Python 3 + PySide6, elle offre une interface graphique sombre aux couleurs d'Orange SA.

> Pour un tour d'horizon technique complet (couches, modèle de données, comment ajouter un type
> d'étape...), voir [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) et le reste de `docs/`. Pour un
> guide utilisateur (premier pipeline, glossaire des étapes, dépannage...), voir la section
> **Aide** intégrée à l'application.

---

## Fonctionnement en un coup d'œil

Un **pipeline** est une suite d'**étapes** (steps), chacune pouvant consommer le fichier produit
par une étape précédente. Deux éditeurs, selon le besoin :

```
Éditeur linéaire (par défaut)      Éditeur graphique (branchement, fan-out)
[Étape 1] → [Étape 2] → [Étape 3]   [Étape 1] ─┬─► [Étape 2A]
    └── planification cron              (Condition) └─► [Étape 2B]
        (APScheduler), ou
        déclenchement manuel
```

10 types d'étapes disponibles aujourd'hui, combinables librement dans un même pipeline :

| Étape | Rôle |
|---|---|
| `DB_EXTRACT` | Exécute une requête SELECT (Oracle/MySQL/PostgreSQL/SQL Server), exporte le résultat en CSV |
| `DB_EXECUTE` | Exécute une instruction SQL/PLSQL (DML, DDL, procédure) sans extraction |
| `DB_LOAD` | Charge un CSV dans une table du SGBD cible (chemin source explicite possible) |
| `FTP_UPLOAD` | Envoie un fichier vers un serveur FTP/FTPS/SFTP (chemin source explicite possible) |
| `FTP_DOWNLOAD` | Récupère un fichier distant (source d'un pipeline) |
| `LOCAL_COPY` | Copie un fichier localement, avec tokens de date (chemin source explicite possible) |
| `PYTHON_SCRIPT` | Exécute un script Python externe, avec contrat d'E/S JSON optionnel |
| `EMAIL_NOTIFY` | Envoie un email, pièce jointe optionnelle |
| `HTTP_REQUEST` | Appelle une API REST / un webhook |
| `CONDITION` | Routeur conditionnel à deux sorties (`true`/`false`) — éditeur graphique uniquement |

> Les anciens types `ORACLE_EXTRACT`/`ORACLE_EXECUTE`/`ORACLE_LOAD` sont dépréciés : les pipelines
> existants qui les utilisaient encore sont migrés automatiquement vers leurs équivalents `DB_*`
> au démarrage (voir `_migrate_oracle_steps_to_generic()` dans `database/db_manager.py`).

Chaque type d'étape réutilisant des identifiants (base de données, FTP, SMTP) s'appuie sur un
**profil** créé une fois et réutilisable dans plusieurs pipelines. Les connexions base de données
passent par un **profil unifié** (`DatabaseProfile`) couvrant Oracle, MySQL, PostgreSQL et SQL
Server, affiché dans une page "Connexions" commune.

Une étape peut publier sa sortie sous un **nom personnalisé** (en plus de son câblage automatique),
référençable depuis n'importe quelle étape en aval via le token générique `{artifact:nom}` — utile
dès qu'un pipeline a plusieurs sources en parallèle.

---

## Sécurité

Les mots de passe des profils (Oracle, FTP, SMTP, bases de données) sont **chiffrés au repos**
(Fernet), avec une clé maître générée au premier lancement et stockée dans le Gestionnaire
d'identification Windows (DPAPI, via `keyring`) — jamais en clair dans la base SQLite ni dans les
fichiers exportés sans mot de passe. Un mot de passe n'est jamais réaffiché en édition ; le champ
reste vide et n'est mis à jour que si une nouvelle valeur est saisie.

---

## Prérequis

| Outil | Version minimale |
|---|---|
| Python | 3.11 |
| Oracle Instant Client | non requis (`python-oracledb` mode thin) |
| Client MySQL / PostgreSQL / SQL Server natif | non requis (pilotes 100% Python : `pymysql`, `psycopg2-binary`, `pymssql` ; `pyodbc` optionnel si un pilote ODBC est déjà présent) |
| Windows | 10 / 11 |

---

## Installation

```bash
# 1. Cloner le dépôt
git clone https://github.com/<votre-org>/DataScheduler.git
cd DataScheduler

# 2. Créer et activer un environnement virtuel
python -m venv envfs
envfs\Scripts\activate

# 3. Installer les dépendances
pip install -r requirements.txt

# 4. Lancer l'application
python main.py
```

La base de données SQLite est créée automatiquement dans `%APPDATA%\DataScheduler\datascheduler.db` au premier démarrage.  
Les migrations de schéma sont appliquées automatiquement à chaque démarrage.  
Les logs applicatifs (rotation automatique) sont écrits dans `%APPDATA%\DataScheduler\logs\app.log`.

---

## Structure du projet

```
DataScheduler/
├── main.py                    # Point d'entrée — logging, init DB + scheduler + UI
├── version.py                 # __version__ de l'application
│
├── core/
│   ├── oracle.py               # OracleConnector + OracleExporter/OracleLoader (CSV chunked, Oracle)
│   ├── sql_db.py                # SqlConnector générique SQLAlchemy — Oracle/MySQL/PostgreSQL/SQL Server
│   ├── ftp.py                    # FtpUploader (upload + download, FTP / FTPS / SFTP)
│   ├── email.py                  # EmailSender (SMTP)
│   ├── pipeline.py               # run_pipeline() — exécuteur (linéaire ou DAG), validate_*, dry_run_pipeline()
│   ├── scheduler.py              # Wrapper APScheduler (cron jobs + digest de notifications)
│   └── steps/
│       ├── base.py               # BaseStep, StepContext (artefacts nommés), StepResult
│       ├── condition.py          # ConditionStep — routeur à ports nommés (éditeur graphique)
│       ├── __init__.py           # Registre des types d'étape (_REGISTRY, get_step())
│       └── <nom>.py              # Une classe par type d'étape (10 aujourd'hui)
│
├── database/
│   ├── models.py                # Modèles SQLAlchemy (profils, SqlQuery, Pipeline, PipelineStep,
│   │                             #   PipelineEdge, PipelineRun, NotificationSettings, AuditEvent)
│   ├── db_manager.py             # Init DB, migrations DDL, helpers CRUD, journal d'audit
│   ├── crypto.py                 # Chiffrement Fernet des mots de passe (clé maître via keyring/DPAPI)
│   └── export_import.py          # Export/import de pipeline versionné et chiffré, duplication
│
├── ui/
│   ├── main_window/               # Fenêtre principale, navigation, vues (Dashboard, Pipelines,
│   │                               #   Connexions, Requêtes SQL, Historique) + widgets partagés
│   ├── step_editor/                # Éditeur linéaire : liste d'étapes + un dialogue de config par type
│   ├── graph_editor/                # Éditeur graphique Qt (QGraphicsView/Scene) — nœuds, arêtes, DAG
│   ├── dialogs/                      # Dialogues de profils, export/import, exécution, détail pipeline...
│   ├── help/                          # Section Aide intégrée (rubriques pédagogiques)
│   └── styles.py                      # Palette couleurs (charte Orange SA #FF7900)
│
├── docs/                       # Architecture, librairies, concepts, cookbook d'extension
├── tests/                      # Suite pytest (pas de dépendance à la vraie base %APPDATA%)
├── requirements.txt
├── DataScheduler.spec          # Configuration PyInstaller
└── .gitignore
```

---

## Fonctionnalités avancées

- **Éditeur graphique** — pour les pipelines avec branchement conditionnel ou plusieurs
  sources/destinations en parallèle, un canevas Qt natif (glisser-déposer les nœuds, tirer des
  arêtes) vient compléter l'éditeur linéaire, sans le remplacer. Exécution en ordre topologique ;
  l'échec d'une étape ne bloque que ses dépendants, les branches indépendantes continuent.
- **Export / import** — exporter un pipeline vers un fichier `.dspipeline` (JSON versionné,
  secrets chiffrés par mot de passe optionnel), le réimporter ailleurs avec détection de
  collision et réutilisation des profils déjà présents (jamais de duplication silencieuse). La
  **duplication** d'un pipeline dans la même base réutilise ce même mécanisme.
- **Notifications** — les échecs (manuels ou planifiés) sont détectés de façon fiable et
  peuvent déclencher un digest email quotidien ou hebdomadaire.
- **Journal des modifications** — chaque création/édition/suppression/export/import de pipeline
  est tracé (qui, quand, quoi), consultable depuis l'Historique.
- **Validation à blanc** — vérifie qu'un pipeline est exécutable (références valides, connexions
  réelles) sans rien exécuter, avant d'activer sa planification.
- **Vue détaillée par pipeline & bilan de santé des connexions** — activité et historique
  scopés à un pipeline (double-clic sur une ligne), statut du dernier test de connexion mémorisé
  pour chaque profil.
- **Statistiques** — graphique d'activité (succès/échecs/annulés par jour) sur le Dashboard.

---

## Options d'export CSV

Chaque pipeline peut configurer indépendamment :

| Paramètre | Options |
|---|---|
| **Séparateur** | `,`  `;`  `\t`  `\|` |
| **Encodage** | `utf-8-sig` *(recommandé Excel)*  `utf-8`  `latin-1`  `cp1252` |
| **Guillemets** | Chaines & dates seulement *(défaut)* · Minimal · Tout · Aucun |
| **Taille chunk** | 1 000 – 1 000 000 lignes (export en flux, faible empreinte RAM) |

Le mode **Minimal** supprime les guillemets autour des chaînes et dates lorsqu'ils ne sont pas nécessaires — utile pour des systèmes cibles stricts sur le format.

---

## Tokens disponibles dans les champs configurables

Chemins FTP, noms de fichiers, sujets/corps d'email, URL et corps HTTP acceptent tous les mêmes
tokens, résolus à l'exécution :

| Token | Valeur exemple / usage |
|---|---|
| `{yyyy}` `{yy}` `{MM}` `{dd}` `{HH}` `{mm}` `{ss}` | Composants de date/heure (`2025`, `25`, `06`, `11`...) |
| `{yyyyMMdd}` | `20250611` |
| `{yyyyMMddHHmm}` | `202506110823` |
| `{output_file}` | Chemin du fichier produit par l'étape précédente (ou la Source choisie) |
| `{rows_count}` | Nombre de lignes traitées jusqu'ici |
| `{error}` / `{failed_step}` | Détail d'un échec — utile dans une notification "toujours exécuter" |
| `{artifact:nom}` | Référence explicite à une sortie publiée sous un nom personnalisé |
| `{ds_context_in}` / `{ds_context_out}` | (PYTHON_SCRIPT uniquement) chemins JSON pour lire/publier des artefacts depuis le script |

Exemple : `chemin = /export/{yyyy}/{MM}/`  ·  `fichier = employes_{yyyyMMdd}.csv`

---

## Packaging Windows (exécutable)

```bash
pyinstaller DataScheduler.spec
# → dist/DataScheduler/DataScheduler.exe
```

---

## Dépendances principales

| Package | Rôle |
|---|---|
| `PySide6` | Interface graphique Qt6 |
| `qtawesome` | Icônes Font Awesome dans l'UI |
| `sqlalchemy` | ORM + SQLite, et connecteur générique multi-SGBD (`core/sql_db.py`) |
| `oracledb` | Pilote Oracle (mode thin, sans client Oracle) |
| `pymysql` | Pilote MySQL |
| `psycopg2-binary` | Pilote PostgreSQL |
| `pyodbc` / `pymssql` | Pilote SQL Server (ODBC si présent, sinon repli TDS pur Python) |
| `pandas` | Export/chargement CSV chunked (`DB_EXTRACT`/`DB_LOAD`) |
| `apscheduler` | Planificateur de tâches cron |
| `paramiko` | SFTP sécurisé |
| `requests` | Appels HTTP (étape `HTTP_REQUEST`) |
| `cryptography` | Chiffrement Fernet des mots de passe stockés |
| `keyring` | Stockage de la clé maître dans le Gestionnaire d'identification Windows (DPAPI) |
| `pytest` | Suite de tests automatisés |

Détail de chaque dépendance et de son usage réel dans ce repo : [docs/LIBRARIES.md](docs/LIBRARIES.md).

---

## Licence

Usage interne Orange SA.

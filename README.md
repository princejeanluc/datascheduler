# DataScheduler

Application de bureau Windows permettant d'automatiser des pipelines de données : extraction et
exécution Oracle, transferts FTP/FTPS/SFTP, notifications email, appels HTTP, scripts Python —
enchaînés dans l'ordre de votre choix.  
Développée avec Python 3 + PySide6, elle offre une interface graphique sombre aux couleurs d'Orange SA.

> Pour un tour d'horizon technique complet (couches, modèle de données, comment ajouter un type
> d'étape...), voir [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) et le reste de `docs/`.

---

## Fonctionnement en un coup d'œil

Un **pipeline** est une suite d'**étapes** (steps) exécutées dans l'ordre, chacune pouvant
consommer le fichier produit par la précédente :

```
[Étape 1] ──►  [Étape 2] ──►  [Étape 3] ──► ...
                    └── planification cron (APScheduler), ou déclenchement manuel
```

9 types d'étapes disponibles aujourd'hui, combinables librement dans un même pipeline :

| Étape | Rôle |
|---|---|
| `ORACLE_EXTRACT` | Exécute une requête SELECT, exporte le résultat en CSV |
| `ORACLE_EXECUTE` | Exécute une instruction SQL/PLSQL (DML, DDL, procédure) sans extraction |
| `ORACLE_LOAD` | Charge un CSV dans une table Oracle |
| `FTP_UPLOAD` | Envoie un fichier vers un serveur FTP/FTPS/SFTP |
| `FTP_DOWNLOAD` | Récupère un fichier distant (source d'un pipeline) |
| `LOCAL_COPY` | Copie un fichier localement, avec tokens de date |
| `PYTHON_SCRIPT` | Exécute un script Python externe |
| `EMAIL_NOTIFY` | Envoie un email, pièce jointe optionnelle |
| `HTTP_REQUEST` | Appelle une API REST / un webhook |

Chaque type d'étape réutilisant des identifiants (Oracle, FTP, SMTP) s'appuie sur un **profil**
créé une fois et réutilisable dans plusieurs pipelines.

---

## Prérequis

| Outil | Version minimale |
|---|---|
| Python | 3.11 |
| Oracle Instant Client | non requis (`python-oracledb` mode thin) |
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

---

## Structure du projet

```
DataScheduler/
├── main.py                  # Point d'entrée — init DB + scheduler + UI
│
├── core/
│   ├── oracle.py            # OracleConnector + OracleExporter/OracleLoader (CSV chunked)
│   ├── ftp.py               # FtpUploader (upload + download, FTP / FTPS / SFTP)
│   ├── email.py             # EmailSender (SMTP)
│   ├── pipeline.py          # run_pipeline() — exécuteur séquentiel de steps
│   ├── scheduler.py         # Wrapper APScheduler (cron jobs)
│   └── steps/
│       ├── base.py          # BaseStep, StepContext, StepResult
│       ├── __init__.py      # Registre des types d'étape (_REGISTRY, get_step())
│       └── <nom>.py         # Une classe par type d'étape (9 aujourd'hui)
│
├── database/
│   ├── models.py            # Modèles SQLAlchemy (profils, SqlQuery, Pipeline,
│   │                        #   PipelineStep, PipelineRun)
│   └── db_manager.py        # Init DB, migrations DDL, helpers CRUD
│
├── ui/
│   ├── main_window.py       # Fenêtre principale + navigation latérale + vues
│   ├── step_editor.py       # Éditeur de pipeline : liste d'étapes + dialogues de config
│   ├── dialogs.py           # Dialogues de profils (Oracle/FTP/SMTP), SQL, progression
│   └── styles.py            # Palette couleurs (charte Orange SA #FF7900)
│
├── docs/                    # Architecture, librairies, concepts, cookbook d'extension
├── requirements.txt
├── DataScheduler.spec       # Configuration PyInstaller
└── .gitignore
```

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

| Token | Valeur exemple |
|---|---|
| `{yyyy}` | `2025` |
| `{MM}` | `06` |
| `{dd}` | `11` |
| `{HH}` | `08` |
| `{yyyyMMdd}` | `20250611` |
| `{yyyyMMddHHmm}` | `202506110823` |
| `{output_file}` | Chemin du fichier produit par l'étape précédente |
| `{rows_count}` | Nombre de lignes traitées jusqu'ici |

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
| `sqlalchemy` | ORM + SQLite |
| `oracledb` | Pilote Oracle (mode thin, sans client Oracle) |
| `pandas` | Export CSV chunked depuis Oracle |
| `apscheduler` | Planificateur de tâches cron |
| `paramiko` | SFTP sécurisé |
| `requests` | Appels HTTP (étape `HTTP_REQUEST`) |

Détail de chaque dépendance et de son usage réel dans ce repo : [docs/LIBRARIES.md](docs/LIBRARIES.md).

---

## Licence

Usage interne Orange SA.

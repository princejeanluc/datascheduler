# DataScheduler

Application de bureau Windows permettant d'automatiser l'export de données Oracle vers des serveurs FTP.  
Développée avec Python 3 + PySide6, elle offre une interface graphique sombre aux couleurs d'Orange SA.

---

## Fonctionnement en un coup d'œil

```
Profil Oracle  ──►  Requête SQL  ──►  Fichier CSV (tmp)  ──►  Upload FTP
                         └── planification cron (APScheduler)
```

Chaque **pipeline** combine :
- une connexion Oracle (profil réutilisable)
- une requête SQL stockée en bibliothèque
- des options d'export CSV (séparateur, encodage, guillemets)
- une destination FTP/FTPS/SFTP avec nommage dynamique
- une planification (quotidienne, hebdomadaire, mensuelle ou cron custom)

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
│   ├── oracle.py            # OracleConnector + OracleExporter (CSV chunked)
│   ├── ftp.py               # FtpUploader (FTP / FTPS / SFTP via paramiko)
│   ├── pipeline.py          # Orchestration complète Oracle → CSV → FTP
│   └── scheduler.py         # Wrapper APScheduler (cron jobs)
│
├── database/
│   ├── models.py            # Modèles SQLAlchemy (OracleProfile, FtpProfile,
│   │                        #   SqlQuery, Pipeline, PipelineRun)
│   └── db_manager.py        # Init DB, migrations DDL, helpers CRUD
│
├── ui/
│   ├── main_window.py       # Fenêtre principale + navigation latérale + vues
│   ├── pipeline_dialog.py   # Dialogue de création/édition de pipeline (5 onglets)
│   ├── dialogs.py           # Dialogues Oracle, FTP, SQL, progression
│   └── styles.py            # Palette couleurs (charte Orange SA #FF7900)
│
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

## Templates de nommage FTP

Le chemin distant et le nom du fichier acceptent des tokens de date résolus à l'exécution :

| Token | Valeur exemple |
|---|---|
| `{yyyy}` | `2025` |
| `{MM}` | `06` |
| `{dd}` | `11` |
| `{HH}` | `08` |
| `{yyyyMMdd}` | `20250611` |
| `{yyyyMMddHHmm}` | `202506110823` |

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

---

## Licence

Usage interne Orange SA.

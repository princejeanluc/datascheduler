# Les librairies de DataScheduler — à quoi chacune sert vraiment

Ce document ne remplace pas la documentation officielle de chaque librairie — il vous donne
juste assez pour savoir **pourquoi elle est là** et **où regarder dans ce repo** pour voir un
exemple réel avant d'aller chercher plus loin dans la doc officielle.

Liste complète des versions figées : [requirements.txt](../requirements.txt).

---

## SQLAlchemy — parler à la base sans écrire de SQL à la main

**Le problème qu'elle résout** : sans elle, chaque lecture/écriture en base serait une chaîne SQL
manuscrite (`"SELECT * FROM pipelines WHERE ..."`), fragile et pénible à maintenir dès que le
schéma évolue.

**Comment DataScheduler l'utilise** : le mode "ORM" (Object-Relational Mapping — voir
`docs/CONCEPTS.md`). Chaque table est une classe Python ([database/models.py](../database/models.py)) :
```python
class Pipeline(Base):
    __tablename__ = "pipelines"
    id   = Column(Integer, primary_key=True)
    name = Column(String(100), unique=True, nullable=False)
    steps = relationship("PipelineStep", back_populates="pipeline")
```
Et [database/db_manager.py](../database/db_manager.py) fait les requêtes en manipulant ces
objets Python, jamais en écrivant du SQL (sauf dans `_migrate()`, où on est volontairement en SQL
brut car SQLAlchemy ne sait pas faire de `ALTER TABLE`) :
```python
def get_pipeline(pipeline_id: int) -> Pipeline | None:
    with get_session() as s:
        return s.get(Pipeline, pipeline_id)
```

**À retenir** : une `Session` (voir `get_session()` dans `db_manager.py`) est l'unité de travail —
on l'ouvre, on fait des lectures/écritures, on la ferme (ou elle se ferme toute seule via le
context manager `with`). Ne gardez jamais un objet SQLAlchemy (ex: un `Pipeline`) après que sa
session soit fermée si vous comptez accéder à ses relations (`.steps`, `.oracle_profile`...) —
elles peuvent ne plus être chargées (`DetachedInstanceError`). C'est pour ça que
`get_pipelines()` utilise `joinedload(...)` : ça précharge les relations avant de fermer la
session.

## oracledb — parler à Oracle sans installer de client Oracle

**Le problème qu'elle résout** : historiquement, parler à Oracle depuis Python demandait
d'installer le lourd "Oracle Instant Client" sur chaque machine. `oracledb` (le successeur de
`cx_Oracle`) sait fonctionner en **mode thin** : un pilote 100% Python, zéro dépendance système.
C'est ce qui permet à DataScheduler d'être un simple `.exe` sans installation préalable.

**Comment DataScheduler l'utilise** : [core/oracle.py](../core/oracle.py), classe
`OracleConnector`. Le DSN (l'adresse d'une base Oracle) se construit avec `oracledb.makedsn(...)`,
la connexion avec `oracledb.connect(...)`.

**Gotcha déjà rencontré dans ce projet** : `pandas.read_sql()` attend officiellement soit une
connexion SQLAlchemy, soit `sqlite3`, soit une URI — pas une connexion `oracledb` brute. Ça
fonctionne quand même (oracledb respecte l'interface DBAPI2 dont pandas a besoin), mais pandas
émet un `UserWarning` à chaque appel pour le signaler. C'est ce warning que vous avez vu à
l'usage — cosmétique, pas un bug, mais expliqué dans `docs/CONCEPTS.md` (section DBAPI2).

## pandas — lire un gros résultat SQL/CSV sans exploser la mémoire

**Le problème qu'elle résout** : charger 2 millions de lignes d'un coup en RAM avant de les
écrire en CSV serait dangereux sur une machine bureautique.

**Comment DataScheduler l'utilise** : `chunksize=` partout où un gros volume est en jeu —
[core/oracle.py](../core/oracle.py), `OracleExporter.export()` (`pd.read_sql(..., chunksize=...)`)
et `OracleLoader.load()` (`pd.read_csv(..., chunksize=...)`). Le résultat n'est plus un seul
`DataFrame` mais un itérateur de petits `DataFrame` (les "chunks") — on les traite un par un et on
les jette, la mémoire reste plate quel que soit le volume total.

## PySide6 (Qt pour Python) — toute l'interface graphique

**Le problème qu'elle résout** : construire une fenêtre native Windows avec des menus, tableaux,
formulaires, sans réinventer le rendu graphique.

**Comment DataScheduler l'utilise** : partout dans `ui/`. Trois idées à connaître avant de
modifier quoi que ce soit ici :
1. **Widgets emboîtés** : une fenêtre est un arbre de `QWidget` (boutons, labels, tableaux...),
   organisés par des `QLayout` (`QVBoxLayout`/`QHBoxLayout`/`QFormLayout`) qui gèrent
   l'espacement — vous ne positionnez presque jamais un widget en coordonnées absolues.
2. **Signaux et slots** : un bouton ne "sait" pas quoi faire au clic — il émet un signal
   (`clicked`), et vous connectez ce signal à une fonction (`btn.clicked.connect(self._on_click)`).
   C'est le mécanisme d'événements de tout Qt, détaillé dans `docs/CONCEPTS.md`.
3. **QSS (feuilles de style Qt)** : une syntaxe très proche du CSS pour styler les widgets — voir
   [ui/styles.py](../ui/styles.py). `GLOBAL_STYLE` s'applique à toute l'app, `DIALOG_STYLE` aux
   dialogues.

**qtawesome** est une petite librairie complémentaire qui fournit les icônes (Font Awesome) —
`_icon("fa5s.plus", couleur)` dans `ui/main_window.py`.

## paramiko — SFTP (SSH File Transfer Protocol)

**Le problème qu'elle résout** : `ftplib` (dans la bibliothèque standard Python) ne sait faire
que FTP/FTPS, pas SFTP (qui passe par SSH, un protocole complètement différent). `paramiko`
implémente SSH et son sous-protocole SFTP.

**Comment DataScheduler l'utilise** : [core/ftp.py](../core/ftp.py), `FtpUploader._upload_sftp` /
`_download_sftp` — ouvre un `paramiko.Transport`, puis un `SFTPClient` par-dessus.

## requests — appeler une API HTTP

**Le problème qu'elle résout** : le module standard `urllib.request` existe déjà mais son API est
verbeuse (gérer soi-même l'encodage JSON, les en-têtes, les erreurs). `requests` est l'équivalent
"ergonomique" devenu standard de facto dans l'écosystème Python.

**Comment DataScheduler l'utilise** : [core/steps/http_request.py](../core/steps/http_request.py),
un seul appel `requests.request(method, url, headers=..., data=..., files=...)` qui couvre GET,
POST, et l'envoi de fichier en multipart.

## smtplib / email — envoyer un mail (bibliothèque standard, zéro dépendance)

**Le problème qu'elle résout** : notifier par email sans dépendance externe — `smtplib` (parler
au serveur SMTP) et `email.message.EmailMessage` (construire le message, pièces jointes
comprises) font partie de Python lui-même, pas besoin d'`pip install` quoi que ce soit.

**Comment DataScheduler l'utilise** : [core/email.py](../core/email.py), classe `EmailSender`.

## APScheduler — exécuter des tâches selon un planning (cron-like)

**Le problème qu'elle résout** : traduire "tous les jours à 6h" ou une expression cron en
"réveille-toi et appelle cette fonction au bon moment", en tâche de fond, sans bloquer le reste
du programme.

**Comment DataScheduler l'utilise** : [core/scheduler.py](../core/scheduler.py),
`PipelineScheduler` encapsule un `BackgroundScheduler` — il tourne sur son propre thread pendant
toute la durée de vie de l'application (démarré dans `main.py`, arrêté à la fermeture).
`CronTrigger` traduit la fréquence choisie par l'utilisateur (DAILY/WEEKLY/MONTHLY/CUSTOM) en
expression cron réelle (`build_cron_trigger`).

## PyInstaller — transformer le projet Python en `.exe`

**Le problème qu'elle résout** : un utilisateur final n'a pas Python installé, ni les
dépendances du projet — PyInstaller regroupe l'interpréteur Python, toutes les dépendances, et le
code du projet dans un dossier autonome (`dist/DataScheduler/`).

**Comment DataScheduler l'utilise** : [DataScheduler.spec](../DataScheduler.spec) est le fichier
de configuration (quels fichiers inclure, quels modules "cachés" forcer). Voir la section
Packaging de `docs/ARCHITECTURE.md` et la recette correspondante dans `docs/COOKBOOK.md`.

# Cookbook — recettes pour faire évoluer DataScheduler

Des marches à suivre concrètes, pour les besoins qui reviendront. Chaque recette part du principe
que vous avez lu `docs/ARCHITECTURE.md` au moins une fois (pour savoir où sont les choses) —
elle ne réexplique pas le "pourquoi", juste le "comment, dans quel ordre, sans rien casser".

---

## Recette : ajouter un nouveau type d'étape (step)

C'est l'opération la plus fréquente désormais que l'architecture est flexible. Reprenez ce
patron dans l'ordre — c'est exactement celui suivi pour les 5 derniers steps ajoutés
(`ORACLE_EXECUTE`, `FTP_DOWNLOAD`, `ORACLE_LOAD`, `EMAIL_NOTIFY`, `HTTP_REQUEST`).

1. **`database/models.py`** — ajouter la valeur dans l'enum `StepType` :
   ```python
   class StepType(str, enum.Enum):
       ...
       MON_NOUVEAU_STEP = "MON_NOUVEAU_STEP"
   ```
   Aucune migration nécessaire pour ça seul : `pipeline_steps.step_type` est un simple
   `VARCHAR`, pas de contrainte `CHECK` qui listerait les valeurs autorisées.

2. **`core/steps/mon_nouveau_step.py`** (nouveau fichier) — la classe qui fait le travail :
   ```python
   from .base import BaseStep, StepContext, StepResult

   class MonNouveauStep(BaseStep):
       def run(self, ctx: StepContext, on_progress=None) -> StepResult:
           result = StepResult()
           try:
               # ... votre logique, en utilisant self.config (dict) et ctx ...
               result.success = True
           except Exception as e:
               result.error = str(e)
           return result
   ```
   Conventions à respecter : ne jamais lever d'exception hors de `run()` (voir
   `docs/CONCEPTS.md`), lire la config via `self.config.get("cle", valeur_par_defaut)`, résoudre
   les tokens de date avec `ctx.resolve_tokens(...)` si votre step utilise un texte configurable
   par l'utilisateur (chemin, sujet d'email, URL...).

3. **`core/steps/__init__.py`** — importer et enregistrer :
   ```python
   from .mon_nouveau_step import MonNouveauStep
   _REGISTRY["MON_NOUVEAU_STEP"] = MonNouveauStep
   ```

4. **`ui/step_editor.py`** — 4 endroits à toucher, tous mécaniques :
   - `STEP_META` : label affiché + couleur du badge.
   - `StepTypeChooserDialog._build_ui`, dictionnaire `descriptions` : la phrase d'aide.
   - Une classe `_MonNouveauStepConfigDialog(_BaseStepConfigDialog)` — copiez la classe d'un step
     existant qui ressemble le plus à votre besoin (`_LocalCopyConfigDialog` si c'est simple,
     `_OracleExecuteConfigDialog` si ça touche Oracle...) et adaptez les champs.
   - `_step_summary()` : la ligne résumée affichée dans la liste des étapes du pipeline.
   - `_open_config_dialog()`, dictionnaire `mapping` : enregistrer votre classe de dialogue.

5. **Si votre step a besoin d'un nouveau type de profil réutilisable** (identifiants, config
   partagée entre pipelines) → voir la recette suivante d'abord.

6. **Tester sans lancer l'UI** (voir la recette "tester sans polluer vos vraies données" plus
   bas) — c'est la façon la plus rapide de valider la logique avant de toucher aux dialogues Qt.

## Recette : ajouter un nouveau type de profil réutilisable

Suivre le patron `SmtpProfile`, qui est le plus récent :

1. **`database/models.py`** — nouvelle classe héritant de `Base`, avec `__tablename__`.
2. **`database/db_manager.py`** :
   - dans `_migrate()`, ajouter la création de la table si absente (copier le bloc
     `smtp_profiles` et adapter les colonnes) ;
   - 4 fonctions CRUD : `create_X_profile`, `get_X_profiles`, `get_X_profile`, `delete_X_profile`
     (copier celles de `smtp_profile`).
3. **`ui/dialogs.py`** — une classe `XDialog(QDialog)` (copier `SmtpDialog`), avec si pertinent
   un thread de test de connexion (copier `SmtpTestThread`).
4. **`ui/main_window.py`**, `ConnectionsView` — un panneau de plus (copier
   `_build_smtp_panel`/`_refresh_smtp`/callbacks), et l'ajouter à la pile verticale dans
   `_build_ui`.
5. **`ui/step_editor.py`**, `PipelineEditorDialog._load_profiles()` — charger la nouvelle liste de
   profils et la propager partout où `smtp_profiles` circule déjà (`_open_config_dialog`, les
   dialogues de config qui en ont besoin).

## Recette : ajouter une migration de schéma

Dans `database/db_manager.py`, fonction `_migrate()` :
```python
cols = {r[1] for r in conn.execute(text("PRAGMA table_info(ma_table)")).fetchall()}
if "ma_nouvelle_colonne" not in cols:
    conn.execute(text(
        "ALTER TABLE ma_table ADD COLUMN ma_nouvelle_colonne VARCHAR(50) DEFAULT 'valeur'"
    ))
    conn.commit()
```
Règles à respecter :
- **Toujours** vérifier avant d'agir (`PRAGMA table_info`, ou `SELECT name FROM sqlite_master`
  pour une table) — la fonction tourne à *chaque* démarrage, elle doit être idempotente (sans
  effet si déjà appliquée).
- SQLite ne sait pas modifier/supprimer une colonne avec `ALTER TABLE` — s'il faut vraiment le
  faire, il faut recréer la table entière (voir le bloc `pipelines_new` dans `_migrate()` comme
  modèle : créer la table cible, `INSERT INTO ... SELECT ...`, `DROP TABLE` de l'ancienne,
  renommer la nouvelle).
- N'oubliez pas d'ajouter aussi la colonne/table dans la classe SQLAlchemy correspondante
  (`models.py`) — sinon une **nouvelle** installation (qui passe par `Base.metadata.create_all`,
  pas par `_migrate()`) ne l'aura pas.

## Recette : tester une modification sans polluer vos vraies données

**Piège vécu pendant cette session** : `db.init_db()` sans argument pointe vers la vraie base de
l'application (`%APPDATA%/DataScheduler/datascheduler.db`) — un script de test lancé tel quel
insère ses données de test au milieu des vraies. Toujours passer un chemin explicite pour un
script jetable :
```python
import tempfile
from pathlib import Path
from database import db_manager as db

tmp_db = Path(tempfile.mktemp(suffix=".db"))
db.init_db(tmp_db)          # base jetable, jamais la vraie
...
```
Pour tester un step isolément (sans base du tout, avec des objets simulés) :
```python
from unittest.mock import MagicMock, patch
from core.steps.mon_nouveau_step import MonNouveauStep
from core.steps.base import StepContext

with patch("database.db_manager.get_oracle_profile", return_value=MagicMock(host="h")):
    step = MonNouveauStep({"cle": "valeur"})
    result = step.run(StepContext())
    print(result.success, result.error)
```
C'est ainsi qu'ont été validés `OracleExecuteStep` (résolution de tokens, rowcount, garde-fou
commit) et `OracleLoader` (construction du `INSERT`, conversion NaN→None) sans jamais toucher à
une vraie base Oracle ni au fichier applicatif réel.

## Recette : lancer et déboguer en local

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python main.py
```
Les logs (niveau `INFO`) s'affichent dans la console — c'est `main.py` qui configure
`logging.basicConfig(...)`. Si l'UI plante silencieusement, lancez toujours depuis un terminal
(pas en double-cliquant) pour voir la trace complète.

## Recette : construire l'exécutable Windows

```bash
pyinstaller DataScheduler.spec
```
Le résultat est dans `dist/DataScheduler/`. Si l'`.exe` se lance puis plante immédiatement avec
un `ModuleNotFoundError` alors que `python main.py` fonctionne sans problème : une nouvelle
dépendance a des sous-modules que PyInstaller n'a pas détectés automatiquement (fréquent avec les
librairies qui font du chargement dynamique de plugins, comme `oracledb` ou `paramiko`).
Ajoutez le module manquant à la liste `hiddenimports` du `.spec` (voir comment `requests` a été
ajouté comme modèle : `'requests', 'urllib3', 'certifi', 'idna', 'charset_normalizer'`).

## Recette : inspecter ou remettre à zéro la base locale

Le fichier vit dans `%APPDATA%\DataScheduler\datascheduler.db` (Windows). Pour l'inspecter sans
rien casser, utilisez un outil en lecture seule comme *DB Browser for SQLite*, ou en Python :
```python
from database import db_manager as db
db.init_db()
print(db.get_pipelines())
```
Pour repartir de zéro (⚠️ perd tout l'historique et tous les profils) : fermez l'application,
supprimez le fichier `datascheduler.db`, relancez — `init_db()` en recrée un vide.

## Pièges déjà rencontrés (pour ne pas les refaire)

- **`sys.executable` dans un `.exe` packagé** n'est pas un interpréteur Python — c'est le chemin
  du `.exe` lui-même. L'étape `PYTHON_SCRIPT` doit donc toujours recevoir un
  `python_executable` explicite (chemin vers le `python.exe` d'un venv/conda cible) une fois
  packagé ; le champ par défaut (`sys.executable`) ne fonctionne qu'en lançant `python main.py`
  directement.
- **`pandas.read_sql()` avec une connexion `oracledb` brute** émet un `UserWarning` — cosmétique,
  pas un bug (voir `docs/LIBRARIES.md`).
- **`chunk.where(chunk.notnull(), None)`** ne convertit pas vraiment les `NaN` en `None` sur une
  colonne numérique (pandas les recoerce en `NaN`) — il faut `chunk.astype(object).where(...)`
  d'abord. Sinon `oracledb` reçoit un `float('nan')` qu'une colonne `NUMBER` refuse.
- **`QHeaderView.ResizeToContents`** sur une colonne qui contient un widget stylé (un badge de
  statut, par exemple) peut sous-estimer sa largeur réelle avant que le style soit pleinement
  appliqué — préférez une largeur fixe (`setColumnWidth`) pour ces colonnes-là plutôt que de
  compter sur le calcul automatique.
- **Supprimer un profil (Oracle/FTP/SMTP) ou une requête SQL** ne vérifie pas par défaut qui
  l'utilise, car la référence vit dans un `config_json` (pas une vraie clé étrangère). Utilisez
  `db.find_pipelines_using_profile(cle, id)` avant de supprimer si vous ajoutez un nouvel endroit
  de suppression.
- **`cursor.rowcount` après un bloc PL/SQL (`BEGIN ... END;`) reste à 0 même si des lignes ont
  vraiment été insérées/modifiées** — si le bloc appelle une procédure stockée qui fait le DML en
  interne, oracledb ne remonte que le résultat de l'appel du bloc lui-même, pas les lignes
  affectées par les instructions exécutées à l'intérieur. Ce n'est pas un bug de DataScheduler,
  c'est un comportement du pilote Oracle. `ORACLE_EXECUTE`
  (`core/steps/oracle_execute.py`) détecte ce cas via `core.oracle.is_plsql_block()` et log un
  message honnête au lieu d'afficher un « 0 ligne(s) affectée(s) » trompeur. Si vous avez besoin
  du nombre réel de lignes affectées par une procédure stockée, faites-le remonter explicitement
  via un paramètre `OUT` dans la procédure elle-même (Oracle ne l'expose pas autrement côté client).

# Cookbook — recettes pour faire évoluer DataScheduler

Des marches à suivre concrètes, pour les besoins qui reviendront. Chaque recette part du principe
que vous avez lu `docs/ARCHITECTURE.md` au moins une fois (pour savoir où sont les choses) —
elle ne réexplique pas le "pourquoi", juste le "comment, dans quel ordre, sans rien casser".

---

## Recette : ajouter un nouveau type d'étape (step)

C'est l'opération la plus fréquente désormais que l'architecture est flexible. Reprenez ce
patron dans l'ordre — c'est exactement celui suivi pour les derniers steps ajoutés
(`FTP_DOWNLOAD`, `EMAIL_NOTIFY`, `HTTP_REQUEST`, puis la généralisation `DB_EXTRACT`/
`DB_EXECUTE`/`DB_LOAD` qui a remplacé les anciens steps Oracle-only).

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

4. **`ui/step_editor/`** — package (un fichier par dialogue, voir `docs/ARCHITECTURE.md`), 5 endroits
   à toucher, tous mécaniques :
   - `common.py`, `STEP_META` : label affiché + couleur du badge.
   - `step_type_chooser_dialog.py`, `StepTypeChooserDialog._build_ui`, dictionnaire `descriptions` :
     la phrase d'aide.
   - Nouveau fichier `mon_nouveau_step_config_dialog.py`, une classe
     `_MonNouveauStepConfigDialog(_BaseStepConfigDialog)` (import depuis `.base_config_dialog`) —
     copiez la classe d'un step existant qui ressemble le plus à votre besoin
     (`local_copy_config_dialog.py` si c'est simple, `db_execute_config_dialog.py` si ça touche une
     base de données...) et adaptez les champs.
     **Piège déjà rencontré** : `_open_config_dialog()` passe un seul dict `kwargs` partagé,
     identique, à toutes les classes de dialogue — la vôtre doit soit accepter `**_` en fin de
     signature (le plus simple, voir `_LocalCopyConfigDialog`), soit lister explicitement tous les
     paramètres du dict (`prior_steps` compris). Une signature explicite qui en oublie un lève un
     `TypeError: unexpected keyword argument` à la première ouverture du dialogue.
   - `pipeline_editor_dialog.py`, `_step_summary()` : la ligne résumée affichée dans la liste des
     étapes du pipeline.
   - `__init__.py` : importer votre nouveau fichier et enregistrer la classe dans le dictionnaire
     `mapping` de `_open_config_dialog()`.

5. **Si votre step a besoin d'un nouveau type de profil réutilisable** (identifiants, config
   partagée entre pipelines) → voir la recette suivante d'abord.

6. **Tester sans lancer l'UI** (voir la recette "tester sans polluer vos vraies données" plus
   bas) — c'est la façon la plus rapide de valider la logique avant de toucher aux dialogues Qt.

## Recette : lire/écrire le contexte depuis un script (PYTHON_SCRIPT)

Un script lancé par l'étape `PYTHON_SCRIPT` tourne dans son propre process, avec son propre
interpréteur/environnement — voulu, pour ne jamais mélanger ses dépendances avec celles de
DataScheduler. Il n'a donc pas d'accès direct à `ctx` (l'objet Python `StepContext` ne franchit
jamais la frontière du process). Le pont : deux tokens facultatifs, `{ds_context_in}` et
`{ds_context_out}`, à placer dans le champ "Arguments" du step exactement comme `{output_file}` ou
`{yyyy}` — voir `core/steps/python_script.py`, `PythonScriptStep.run()`.

**Toujours passés en argument de ligne de commande, jamais en variable d'environnement** —
certains postes cibles nécessitent un accès admin/helpdesk pour modifier une variable
d'environnement système, même si un `env=` passé à un unique sous-processus ne l'exigerait pas
techniquement ; l'argument évite toute ambiguïté.

Si votre script référence `{ds_context_in}`, il reçoit le chemin d'un fichier JSON à lire :
```json
{
  "artifacts": {"output_file": "C:/tmp/ds_xxx.csv", "b18f...": "C:/tmp/ds_yyy.csv"},
  "rows_count": 12345
}
```
`artifacts` contient tout ce que les étapes précédentes ont déjà produit, par nom. Si votre script
référence `{ds_context_out}`, vous pouvez (facultatif) y écrire un JSON similaire — chaque entrée de
son `artifacts` est fusionnée dans le contexte réel après l'exécution :
```json
{"artifacts": {"output_file": "C:/tmp/mon_resultat.csv"}}
```
Publier sous la clé `"output_file"` fait consommer votre résultat par l'étape suivante exactement
comme n'importe quel autre step producteur (comportement par défaut du sélecteur "Source" —
voir `docs/ARCHITECTURE.md`, section StepContext). Publier sous un autre nom fonctionne aussi (le
contexte le retient), mais ce nom n'apparaîtra pas dans le sélecteur "Source" des dialogues suivants
tant qu'aucune interface ne l'expose — à récupérer pour l'instant via un autre `PYTHON_SCRIPT` qui
lit ce même nom dans son propre `{ds_context_in}`.

Un script qui ne référence ni l'un ni l'autre token n'est pas concerné : son `argv` est strictement
identique à ce qu'il aurait reçu avant l'existence de ce contrat. Un JSON de sortie absent ou
invalide n'échoue pas le step (juste un avertissement loggé) — le code de retour du process reste
le seul signal d'échec/réussite.

## Recette : ajouter un nouveau type de profil réutilisable

Suivre le patron `SmtpProfile` (le plus simple à lire) ou `DatabaseProfile` (si votre profil doit
couvrir plusieurs variantes proches d'un même besoin — c'est le patron le plus récent, utilisé
pour fusionner MySQL/PostgreSQL/SQL Server en une seule table plutôt qu'une par moteur) :

1. **`database/models.py`** — nouvelle classe héritant de `Base`, avec `__tablename__`.
2. **`database/db_manager.py`** :
   - dans `_migrate()`, ajouter la création de la table si absente (copier le bloc
     `smtp_profiles` et adapter les colonnes) ;
   - 4 fonctions CRUD : `create_X_profile`, `get_X_profiles`, `get_X_profile`, `delete_X_profile`
     (copier celles de `smtp_profile`).
3. **`ui/dialogs/`** — nouveau fichier `x_dialog.py`, une classe `XDialog(QDialog)` (copier
   `smtp_dialog.py`), avec si pertinent un thread de test de connexion (copier `SmtpTestThread`) ;
   réexporter la classe dans `ui/dialogs/__init__.py`.
4. **`ui/main_window/connections_view.py`**, `ConnectionsView` — un panneau de plus (copier
   `_build_smtp_panel`/`_refresh_smtp`/callbacks), et l'ajouter à la pile verticale dans
   `_build_ui`.
5. **`ui/step_editor/pipeline_editor_dialog.py`**, `PipelineEditorDialog._load_profiles()` — charger
   la nouvelle liste de profils et la propager partout où `smtp_profiles` circule déjà
   (`_open_config_dialog`, les dialogues de config qui en ont besoin).

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
C'est ainsi qu'ont été validés `DbExecuteStep` (résolution de tokens, rowcount, garde-fou
commit) et `SqlLoader` (construction du `INSERT`, conversion NaN→None) sans jamais toucher à
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
  c'est un comportement du pilote Oracle. `DB_EXECUTE`
  (`core/steps/db_execute.py`) détecte ce cas via `core.sql_db.is_plsql_block()` (réexporté depuis
  `core.oracle.is_plsql_block()`, seul le connecteur Oracle a cette notion de bloc PL/SQL) et log
  un message honnête au lieu d'afficher un « 0 ligne(s) affectée(s) » trompeur. Si vous avez besoin
  du nombre réel de lignes affectées par une procédure stockée, faites-le remonter explicitement
  via un paramètre `OUT` dans la procédure elle-même (Oracle ne l'expose pas autrement côté client).

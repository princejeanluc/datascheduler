# Concepts et paradigmes utilisés dans DataScheduler

Ce document explique les idées de programmation derrière le code — pas les librairies qui les
implémentent (ça, c'est `docs/LIBRARIES.md`). L'objectif : que vous reconnaissiez ces patterns la
prochaine fois que vous les croisez, ici ou ailleurs, et que vous sachiez quand les réutiliser
vous-même.

---

## Le pattern registre (registry) — l'idée la plus importante du projet

**Le problème** : on veut pouvoir ajouter un nouveau type d'étape (`ORACLE_EXECUTE`,
`HTTP_REQUEST`...) sans modifier le code qui *exécute* les pipelines. Si l'exécuteur devait faire
`if step_type == "ORACLE_EXTRACT": ... elif step_type == "FTP_UPLOAD": ...`, chaque ajout
obligerait à retoucher cette fonction centrale — risque de régression sur tout ce qui existe déjà.

**La solution** : un dictionnaire qui associe un nom à une classe, rempli une fois, consulté
partout ([core/steps/\_\_init\_\_.py](../core/steps/__init__.py)) :
```python
_REGISTRY = {"ORACLE_EXTRACT": OracleExtractStep, "FTP_UPLOAD": FtpUploadStep, ...}

def get_step(step_type: str, config: dict) -> BaseStep:
    return _REGISTRY[step_type](config)
```
L'exécuteur ([core/pipeline.py](../core/pipeline.py)) ne connaît qu'une seule ligne :
`get_step(step_type, config)`. Il n'a jamais besoin de savoir que 9 types d'étapes existent, ni
lesquels. Ajouter un dixième type = ajouter une ligne au dictionnaire, zéro ligne changée dans
l'exécuteur. C'est l'essence du **principe ouvert/fermé** (une des idées derrière "SOLID") :
ouvert à l'extension (on peut ajouter des types), fermé à la modification (le code qui les
utilise n'a pas à changer).

**Où le revoir ailleurs dans ce projet** : `ui/step_editor.py`, `_open_config_dialog()` fait
exactement la même chose côté UI — un dictionnaire `step_type → classe de dialogue`.

**Où vous le recroiserez** : c'est le même principe derrière les "plugins" de n'importe quel
outil (extensions VS Code, middlewares Django, providers Terraform...). Dès que vous voyez
"comment ajouter un type de X sans toucher au moteur", pensez registre.

## L'interface commune (pourquoi toutes les étapes ont la même forme)

Le registre ne fonctionne que parce que **toutes** les classes de step respectent le même
contrat : hériter de `BaseStep` et implémenter `run(self, ctx, on_progress=None) -> StepResult`.
L'exécuteur peut appeler `.run(...)` sur n'importe laquelle sans savoir laquelle c'est vraiment —
c'est du **polymorphisme** : des objets de classes différentes, utilisés de façon interchangeable
parce qu'ils partagent la même interface. C'est ce qui permet au registre d'exister : sans
interface commune, il faudrait quand même un `if/elif` quelque part pour savoir comment appeler
chaque type différemment.

## Programmation orientée objet — au minimum syndical, et c'est voulu

Vous remarquerez que ce projet n'utilise l'héritage que pour une seule chose : `BaseStep`. Pas de
hiérarchies de classes profondes ailleurs, pas d'abstraction pour l'abstraction. `OracleProfile`,
`FtpProfile`, `SmtpProfile` sont trois classes séparées, presque identiques, plutôt qu'une classe
abstraite `Profile` dont elles hériteraient — délibérément, parce que factoriser 3 champs communs
sur 6 aurait ajouté de l'indirection pour un gain minuscule. Retenez la leçon inverse de
"toujours factoriser dès que ça se ressemble" : dupliquer un peu est parfois plus lisible que
factoriser trop tôt. Le code du projet lui-même applique ce principe (voir la règle donnée à
l'assistant : "trois lignes similaires valent mieux qu'une abstraction prématurée").

## ORM — manipuler des lignes de base de données comme des objets Python

Un ORM (*Object-Relational Mapping*) fait correspondre une classe Python à une table SQL, et une
instance de cette classe à une ligne. `pipeline.name = "X"` puis un commit, plutôt que
`UPDATE pipelines SET name = 'X' WHERE id = ...`. Le gain : le code manipule des objets typés
(autocomplétion, pas de faute de frappe dans un nom de colonne écrit en dur), et n'a pas besoin de
connaître la syntaxe SQL exacte de SQLite si demain la base change (Postgres, MySQL...) —
SQLAlchemy traduit. Le prix : une couche d'indirection en plus, et des sessions à gérer (voir plus
bas). Voir `docs/LIBRARIES.md` pour l'usage concret avec SQLAlchemy.

## Context managers (`with ... as ...`)

Un context manager garantit qu'une ressource est correctement libérée, même si une exception
survient au milieu. `get_session()` dans
[database/db_manager.py](../database/db_manager.py) en est un exemple :
```python
@contextmanager
def get_session():
    session = _SessionFactory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
```
`with get_session() as s: ...` garantit que la session est toujours fermée (`finally`), et que
toute exception dans le bloc annule les changements (`rollback`) plutôt que de laisser la base
dans un état à moitié modifié. Le même principe protège les connexions Oracle/FTP
(`OracleConnector.__enter__`/`__exit__`) et les fichiers (`open(...)` est lui-même un context
manager standard de Python).

## Dataclasses — des structures de données sans cérémonie

`@dataclass` génère automatiquement `__init__`, `__repr__` et l'égalité pour une classe qui ne
sert qu'à porter des champs — pas de logique, juste des données. Exemples dans ce projet :
`ExportResult`, `LoadResult`, `UploadResult`, `SendResult` (tous dans `core/`) : le résultat d'une
opération qui peut réussir ou échouer, avec un message. Le pattern qui revient partout :
```python
@dataclass
class SendResult:
    success: bool
    error: str = ""
```
plutôt que de lever une exception. Voir "ne jamais lever d'exception" ci-dessous — ce sont les
deux faces de la même pièce.

## Enums — une liste fermée de valeurs valides, au lieu de strings libres

`StepType`, `PipelineStatus`, `CronFrequency` ([database/models.py](../database/models.py)) sont
des `enum.Enum` : au lieu d'écrire `"SUCCESS"` en dur un peu partout (avec le risque de faire une
faute de frappe qui ne sera détectée qu'à l'exécution), on écrit `PipelineStatus.SUCCESS` — un nom
que l'éditeur peut autocompléter et vérifier. Le fait d'hériter aussi de `str`
(`class StepType(str, enum.Enum)`) est un détail pratique : ça permet de comparer directement
`step_type == "ORACLE_EXTRACT"` sans conversion, tout en gardant les avantages de l'enum.

## « Ne jamais lever d'exception, toujours retourner un résultat »

Remarquez que `OracleConnector.test_connection()`, `FtpUploader.upload()`,
`EmailSender.send()` etc. ne laissent **jamais** remonter une exception — elles l'attrapent en
interne et retournent un objet `...Result(success=False, error="...")`. C'est un choix
délibéré pour du code appelé depuis l'UI ou un scheduler en tâche de fond : une exception non
attrapée dans un thread de fond peut faire planter l'application entière ou disparaître
silencieusement selon le contexte. Retourner un résultat oblige l'appelant à gérer explicitement
le cas d'échec (`if not result.success: ...`) plutôt que de compter sur un `try/except` qu'on
pourrait oublier quelque part.

Ce n'est pas une règle absolue partout dans le projet : le code interne (par exemple à
l'intérieur d'un `step.run()`) utilise encore des exceptions classiques en interne, capturées une
seule fois au bon endroit (`except Exception as e: result.error = str(e)`). La règle s'applique à
la **frontière** entre un module et son appelant, pas à l'intérieur d'un module.

## Signaux et slots (Qt) — une forme du patron Observateur

Un bouton ne sait pas quoi faire quand on clique dessus — il *émet un signal*, et n'importe quel
code peut s'y abonner (*se connecter*) sans que le bouton ait besoin de le connaître :
```python
btn_run.clicked.connect(self._on_run_pipeline)
```
C'est une instance du patron de conception **Observateur** : un objet notifie des changements
sans connaître qui écoute. Vous l'utiliserez à chaque nouveau bouton/champ de l'UI. La variante
la plus intéressante du projet : `SchedulerNotifier` (voir `docs/ARCHITECTURE.md`, section "pont
thread-safe") utilise ce même mécanisme pour faire communiquer un thread de fond avec le thread
principal de l'UI — pas juste pour des clics de souris.

## Threads et pourquoi l'UI ne doit jamais attendre

Une interface graphique tourne sur un seul thread ("thread principal" / "thread UI") qui fait
deux choses en boucle : dessiner l'écran, et réagir aux clics/frappes clavier. Si ce thread se met
à attendre une réponse réseau (connexion Oracle, upload FTP...) qui prend 10 secondes,
l'application entière se fige pendant ces 10 secondes — aucun redessin, aucun clic pris en compte.

La solution : déplacer le travail long dans un `QThread` séparé (voir `OracleTestThread`,
`FtpTestThread`, `_OracleExecuteTestThread` dans `ui/dialogs.py` et `ui/step_editor.py`), et
laisser le thread principal libre de continuer à rafraîchir l'écran pendant ce temps. Le résultat
revient ensuite via... un signal Qt (encore le même pattern). Retenez la règle simple : **toute
opération qui peut prendre plus qu'un instant perceptible (réseau, disque, calcul lourd) ne doit
jamais s'exécuter directement dans un callback de clic** — elle doit partir dans un thread.

## DBAPI2 — le standard caché derrière tous les pilotes de base de données

Python définit une interface standard (PEP 249, dite "DBAPI2") que tout pilote de base de données
doit respecter : une méthode `connect()`, un objet `cursor()`, des méthodes `execute()` /
`fetchall()`... `oracledb`, `sqlite3` (inclus dans Python), et le pilote SQLite utilisé en
interne par SQLAlchemy la respectent tous. C'est ce qui permet à du code générique (comme
`pandas.read_sql()`) de fonctionner avec n'importe lequel sans code spécifique par base de
données — même si, comme vu dans `docs/LIBRARIES.md`, pandas ne "certifie" officiellement que
certaines combinaisons et râle (un `UserWarning`, pas une erreur) pour les autres.

## Migrations de schéma — faire évoluer une base sans perdre les données existantes

Contrairement à une nouvelle installation (où on peut créer les tables depuis zéro), une base
existante contient déjà des données réelles qu'on ne veut pas perdre en ajoutant une colonne ou
une table. La fonction `_migrate()` de `database/db_manager.py` applique, au démarrage, une série
de vérifications ("cette colonne existe-t-elle déjà ? cette table existe-t-elle ?") et n'agit que
si nécessaire — chaque migration ne s'exécute donc qu'une seule fois dans la vie d'une base
donnée, la fois où le schéma qu'elle attend n'est pas encore là. Voir `docs/COOKBOOK.md` pour la
recette d'ajout d'une nouvelle migration.

## Séparation des responsabilités (pourquoi 4 dossiers et pas un seul fichier)

Le principe général derrière la structure `database/` / `core/` / `core/steps/` / `ui/` (détaillé
dans `docs/ARCHITECTURE.md`) : chaque couche a une seule responsabilité, et ne connaît que celle
juste en-dessous d'elle. Le bénéfice concret que vous avez vu cette session : on a pu écrire et
**tester** chaque nouveau step (`ORACLE_EXECUTE`, `HTTP_REQUEST`...) en les important
directement dans un script Python, sans jamais lancer l'interface graphique — impossible si
la logique métier était mélangée avec le code Qt.

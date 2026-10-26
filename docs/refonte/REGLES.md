# Règles de la refonte

Ces règles existent pour une raison : la refonte doit livrer exactement ce qui a été conçu, sans rien casser chez les utilisateurs qui ont déjà une base, des pipelines exportés ou un worker en arrière-plan.

## 1. Ce qui fait référence

Par ordre de priorité, quand deux sources ne disent pas la même chose :

1. **`DECISIONS.md`**, qui tranche les questions ouvertes des fiches. Une décision « à trancher » bloque le lot qui en dépend.
2. **La fiche de l'écran** (`docs/refonte/ecrans/<écran>.md`). C'est le contrat : ce qui est dans le périmètre du lot, ce qui ne l'est pas, les critères d'acceptation. Pour les données, `DONNEES.md` fait foi.
3. **Le code actuel**, pour le comportement. Une maquette ne change jamais un comportement que la fiche ne mentionne pas.
4. **Les maquettes** (`docs/refonte/maquettes/png/` pour voir, `html/` pour lire les valeurs exactes : couleurs, tailles, espacements, textes).

Si la fiche, le code et la maquette se contredisent sur un point qui compte, arrête-toi et pose la question. Ne tranche pas seul.

## 2. Ce que veut dire « proposé »

Sur les maquettes, une pastille orange « proposé » marque un élément qui n'existe pas dans le code.

- Un élément « proposé » ne s'implémente **que si la fiche du lot le liste dans « À faire »**. Sinon, il est absent de l'écran livré, et il ne laisse pas de place vide.
- La pastille elle-même n'est jamais reproduite dans l'application.
- Les données des maquettes (noms de pipelines, chiffres, heures) sont des exemples. Les vraies valeurs viennent des fonctions citées dans la fiche.

## 3. Traduire une maquette web en Qt

Les maquettes sont en HTML pour être lisibles. Elles ne sont pas une structure à recopier.

- Reprends les couleurs, tailles de police, espacements, rayons et textes. Le placement exact au pixel près n'est pas exigé.
- Couleurs : uniquement les clés de `ui/styles.py::COLORS`. La correspondance des valeurs hexadécimales est dans `FONDATIONS.md`. N'ajoute pas de couleur en dur dans un widget.
- Polices : IBM Plex Sans et JetBrains Mono sont déjà embarquées (`ui/fonts.py`). N'en ajoute pas.
- Composants : utilise ceux de `FONDATIONS.md`. Si un écran a besoin d'une pièce qui n'y figure pas, ajoute-la au module partagé plutôt que dans la vue.
- Les textes affichés sont en français, et repris tels quels de la maquette sauf indication contraire de la fiche.
- Un même élément (catégorie, ligne…) peut avoir deux textes différents sur la maquette selon l'endroit où il apparaît (ex. un sous-titre court dans une liste de navigation vs. une description plus longue dans le panneau qu'elle ouvre). Vérifie le HTML brut de chaque emplacement avant de réutiliser une seule chaîne aux deux endroits — comparer seulement le PNG peut masquer des textes tronqués identiques en apparence mais différents dans le code source (leçon du lot A-Paramètres, point 8 de sa note d'impact).
- Pièges connus du moteur QSS de Qt (PySide6), à vérifier systématiquement sur tout nouveau conteneur/label : une règle globale `QWidget { background-color: ... }` (`widgets.py::GLOBAL_STYLE`) peint un fond opaque derrière tout `QLabel` qui ne déclare pas lui-même `background: transparent` ; un `setStyleSheet()` sans sélecteur posé sur un conteneur se propage à ses descendants et peut écraser une règle globale pourtant plus spécifique (ex. un `QPushButton` enfant). `QLabel` hérite de `QFrame`, pas seulement de `QWidget` : une règle `QFrame { border: ...; background: ... }` posée sur un conteneur (carte, encart) se propage donc *aussi* à chaque `QLabel` enfant qui ne fixe pas lui-même `border`/`background` — vu deux fois indépendamment (lot A-Ressources, lot A-Aujourd'hui), la seconde fois malgré la leçon déjà écrite ici pour `QWidget`. **Le cas `QPushButton` ci-dessus n'est pas qu'un exemple théorique : vu trois fois indépendamment** (Requêtes SQL, Aujourd'hui, Atelier-main) — un bouton par défaut (sans `objectName`, fond accent plein attendu de `GLOBAL_STYLE`) niché dans un conteneur à la règle nue (`"background: transparent;"` sur une `QScrollArea`, ou `"background: X; border-bottom: Y;"` sur un en-tête) s'affiche silencieusement **sans aucun fond visible** — pas d'erreur, juste un bouton qui a l'air cassé/invisible en capture. Ne pas se fier à ce que chaque futur enfant pense à neutraliser `border: none` : toujours scoper le style d'un conteneur à un sélecteur d'ID (`objectName` + `QWidget#nom { ... }` ou `QFrame#nom { ... }`) ou à un sélecteur de type (`QScrollArea { ... }`) plutôt qu'une règle nue, quel que soit le type ciblé — et vérifier en particulier tout bouton par défaut hébergé dans le conteneur qu'on stylise.

## 4. Avant d'écrire du code : la note d'impact

Chaque lot commence en mode plan, par une note d'impact rédigée avec le modèle `NOTE-IMPACT.md` et enregistrée dans `docs/refonte/impact/<lot>.md`. Attends que la note soit validée avant de modifier le code.

La note répond au minimum à ces points, propres à Kulu :

- **Base de données.** Les migrations sont des `ALTER TABLE` écrits à la main dans `database/db_manager.py::_migrate`. On ne fait qu'ajouter : colonne avec valeur par défaut, nouvelle table. Jamais de renommage, de suppression ni de changement de type. Une base de la version 0.45.0 doit s'ouvrir et fonctionner.
- **Format d'export.** `database/export_import.py::CURRENT_SCHEMA_VERSION` vaut 3. Un fichier `.dspipeline` exporté avant la refonte doit toujours s'importer. Si le lot change ce format, il passe par `_transcribe_bundle()` et la version augmente.
- **Worker en arrière-plan.** En mode arrière-plan, un processus séparé lit et écrit la même base SQLite (`core/execution_mode.py`, `core/scheduler.py`). Une ancienne version du worker peut tourner pendant que la nouvelle interface a migré la base : une colonne ajoutée doit être tolérée par l'ancien code.
- **Heures.** La base stocke en UTC (`datetime.utcnow`), sauf `Pipeline.next_run_at`, stocké dans le fuseau réglé (`AppSettings.timezone`). On ne change pas ce stockage. Toute heure affichée passe par la fonction de conversion partagée (voir `FONDATIONS.md`).
- **Build.** Les polices sont embarquées en base64 dans `ui/fonts.py` et les icônes en SVG dans `ui/icons.py` : aucun fichier de ressources séparé, donc rien à ajouter à `KULU.spec`. Garde ce mode pour les nouvelles icônes. Une dépendance Python ajoutée doit, elle, être vérifiée dans `KULU.spec` (voir les `collect_all`).
- **Tests.** Liste les tests existants qui touchent les fichiers modifiés (`grep` dans `tests/`). Ils doivent rester verts. Une assertion qui fige un texte ou une colonne que la fiche change est mise à jour (décision T1) ; un test de comportement n'est jamais retiré ni assoupli.

## 5. Pendant le lot

- Un lot, une branche, une PR. Pas de nettoyage hors périmètre dans la même PR : note-le dans la PR, section « Hors périmètre repéré ».
- Garde les noms publics existants (méthodes appelées depuis d'autres vues, signaux, `select_category`, etc.). Cherche les appelants avant de renommer quoi que ce soit.
- Respecte les commentaires du code qui expliquent un choix (par exemple un widget gardé dans le layout pour éviter un crash). Ils décrivent des bugs déjà rencontrés.
- N'ajoute aucune dépendance Python sans la noter dans la note d'impact.

## 6. Définition de « terminé »

Un lot est terminé quand :

1. tous les critères d'acceptation de la fiche sont cochés dans la description de la PR ;
2. `python -m pytest tests -q` passe, avec des tests ajoutés pour les comportements nouveaux ;
3. une capture de chaque état listé dans la fiche est jointe à la PR, à côté de la maquette correspondante. Pour la produire sans affichage : `QT_QPA_PLATFORM=offscreen`, puis `widget.grab().save("capture.png")` sur la vue à 1440×900. `scripts/capture_views.py` appelle `.show()` sur chaque vue comme fenêtre top-level sans parent : Qt donne alors le focus clavier par défaut au premier widget focusable (ex. un champ de recherche), ce qui ne reflète pas l'app réelle (vue intégrée à une fenêtre déjà active) et fait apparaître à tort une bordure de focus sur la capture — à nettoyer explicitement dans le script pour les états qui ne simulent pas une saisie en cours ;
4. les écarts volontaires avec la maquette sont listés dans la PR, avec leur raison ;
5. `docs/refonte/manquements.md` est mis à jour : les lignes traitées sont marquées « fait (lot X) ».

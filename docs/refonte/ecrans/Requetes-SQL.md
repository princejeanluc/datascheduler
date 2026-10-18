# Requêtes SQL

Vue : `ui/main_window/queries_view.py` (et `ui/sql_editor.py`, `ui/dialogs/sql_query_dialog.py`). Exécution : `core/steps/db_extract.py`, `core/steps/base.py::StepContext.resolve_tokens`, `core/sql_db.py`. Maquettes : `maquettes/png/SQL*.png`.

## Intention
Un profil data écrit et corrige ici les requêtes que ses étapes d'extraction, d'exécution et Spark SQL réutilisent. Aujourd'hui il ne peut ni voir ce que la requête renvoie, ni ce que la base recevra une fois les jetons remplacés, ni savoir qu'une modification n'est pas enregistrée. La refonte garde l'atelier maître-détail et lui ajoute ces trois retours, sans jamais exécuter une requête qui écrit.

## États (frames)
| Frame | Ce qu'elle montre | Déclencheur dans l'application |
|---|---|---|
| SQL | Bibliothèque à gauche, éditeur à droite, requête modifiée non enregistrée, panneau du bas replié | Clic sur « Requêtes SQL » dans la navigation, puis sur une requête |
| SQL-apercu | Onglet « Résultats » déplié : 6 lignes, types de colonnes, durée, limite de 100 lignes | Bouton « Aperçu » ou Ctrl Entrée |
| SQL-jetons | Liste de jetons sous le curseur : variables des pipelines, dates, calculs | Frappe de `{` dans l'éditeur |
| SQL-resolu | Onglet « SQL résolu » : lignes modifiées par les jetons et tableau des 3 jetons résolus | Onglet « SQL résolu » |
| SQL-rechercher | Barre rechercher et remplacer, 2/3 occurrences surlignées | Ctrl F ou Ctrl H |
| SQL-enregistrer | Onglet « Utilisée par » et encadré « Enregistrer touchera ces 2 pipelines » | « Enregistrer » sur une requête utilisée |
| SQL-depuis-etape | Modale de création ouverte depuis une étape, avec aperçu | « + Nouvelle requête SQL » dans le dialogue d'une étape |

## À garder tel quel
- L'atelier maître-détail (`QueriesView._build_sidebar`, `_build_workshop`) et le principe d'enregistrement explicite, jamais à la frappe (docstring du module).
- La recherche sur le nom, la description et le corps SQL (`_QueryCard.matches`, `_apply_search_filter`).
- « + Nouvelle requête » : crée `NOUVELLE_REQUETE`, puis `NOUVELLE_REQUETE_2`…, avec le gabarit `SELECT * FROM WHERE`, la sélectionne et met le focus sur le nom (`_on_new_query`).
- La carte de requête : nom, compteur « N pipeline(s) » ou « Aucun », description, aperçu du SQL sur 80 caractères en Mono, carte active surlignée, et le bouton de suppression (`_QueryCard`). La maquette n'a plus ce bouton : voir Questions, point 2.
- La suppression avec confirmation, qui nomme les pipelines utilisateurs (`_on_delete_query`, `find_pipelines_using_profile("sql_query_id", …)`).
- Le nom et la description modifiables sur place dans l'en-tête (`inp_name`, `inp_desc`).
- Le champ « Profil » (`cb_oracle`, `SqlQuery.oracle_profile_id`) : il n'est pas lu à l'exécution, mais il filtre la liste des requêtes dans `db_extract_config_dialog.py` et `db_execute_config_dialog.py`. Voir Questions, point 1.
- Dupliquer (`duplicate_sql_query`, suffixe « (copie) » puis « (copie 2) »), Importer .sql et Exporter .sql en UTF-8 (`_on_import_sql`, `_on_export_sql`), Formater (`SqlEditorWidget.format_sql`, `sqlparse` avec mots-clés en majuscules).
- Les contrôles d'enregistrement : nom et SQL non vides (`_on_save_query`), même chose dans la modale (`SqlQueryDialog._on_save`).
- L'éditeur partagé `SqlEditorWidget` : numéros de ligne, coloration, ligne courante surlignée, barre rechercher et remplacer (Ctrl F, Ctrl H, compteur `n/N`, précédent et suivant en boucle, « Remplacer », « Tout remplacer » sans tenir compte de la casse, Échap ferme), texte d'exemple. Les tests de `tests/test_sql_editor_widget.py` restent verts.
- La modale rapide `SqlQueryDialog`, ouverte depuis les étapes DB_EXTRACT, DB_EXECUTE et SPARK_SQL (`_new_sql_query`), avec nom, description, profil, éditeur, « Formater », « Annuler », « Enregistrer ».
- La vue désactivée quand aucune requête n'est sélectionnée et le message de bibliothèque vide (`_set_workshop_enabled`, `_empty_label`).
- Les commentaires qui expliquent les sélecteurs qualifiés (`#queryCard`, `#queriesSidebar`, `#workshopHeader`) et le `stretch=1` du message vide : ce sont des bugs déjà rencontrés, vérifiés par `tests/test_queries_view_workshop.py`.
- Les jetons tels que l'exécution les résout (`StepContext.resolve_tokens`) : dates `{yyyy}` `{yy}` `{MM}` `{dd}` `{HH}` `{mm}` `{ss}` `{yyyyMMdd}` `{yyyyMMddHHmm}`, `{rows_count}`, `{error}`, `{failed_step}`, `{output_file}`, `{artifact:…}`, `{var:…}`, `{expr:…}` ; un jeton inconnu reste littéral.
- Sécurité : l'aperçu et la modale ouvrent la connexion avec les profils de `core/sql_db.py::config_from_profile`, dont le mot de passe est déchiffré en mémoire par `database/crypto.py` et jamais affiché, copié ni écrit dans un message d'erreur montré à l'écran.

## Lot A : alignement visuel, sans changer la base
Lot A restyle l'existant et peut afficher une valeur déjà disponible. Il ne crée ni comportement ni fonction de données.

| # | Changement | Frame | Source des données (code) |
|---|---|---|---|
| A1 | En-tête de la bibliothèque : « Requêtes SQL », « 8 dans la bibliothèque » à droite, recherche « Nom, description ou SQL… » ; retirer l'aide en italique | SQL | `get_sql_queries`, `_build_sidebar` |
| A2 | Bouton « + Nouvelle requête » en bouton secondaire bordé `accent` pleine largeur | SQL | `_on_new_query` |
| A3 | Carte : nom 13 px, pastille « 2 pipelines » en `signal_pale` ou « aucun » en `text_dim`, description 11 px, aperçu Mono ; carte active en `bg_active` avec bord gauche `accent` | SQL | `_QueryCard` |
| A4 | En-tête de l'éditeur : nom en 18 px, « · », description en italique `text_dim` | SQL | `inp_name`, `inp_desc` |
| A5 | Formater, Dupliquer, Exporter, Importer en boutons à icône seule de 30 px, infobulles « Formater », « Dupliquer », « Exporter en .sql », « Importer un .sql » ; « Enregistrer » en bouton principal | SQL | `btn_format`, `btn_dup`, `btn_export`, `btn_import`, `btn_save` |
| A6 | Couleurs de l'éditeur prises dans `COLORS` : mots-clés `accent`, fonctions `signal_pale`, commentaires en italique `text_muted`, fond `bg_main`, ligne courante `bg_hover` ; supprimer les valeurs en dur de `SqlHighlighter` | SQL | `ui/sql_editor.py` |
| A7 | Jetons `{…}` surlignés dans l'éditeur (fond et contour orangés, Questions point 6) | SQL | `SqlHighlighter._rules` |
| A8 | Barre d'état : liste de jetons complétée en « {yyyyMMdd} {var:…} {expr:…} {artifact:…} » (manquement « Jetons incomplets ») | SQL | `_build_workshop` |
| A9 | Barre rechercher : champ Mono bordé `accent` au focus, compteur « 2/3 », flèches, croix, « Remplacer », « Tout remplacer » | SQL-rechercher | `_FindBar` |
| A10 | Modale depuis une étape : fenêtre modale (FONDATIONS §3), nom et description côte à côte, éditeur pleine largeur, pied « Annuler » et bouton principal ; surtitre « NOUVELLE REQUÊTE · POUR L'ÉTAPE « X » DE Y » si l'appelant passe `step_label` et `pipeline_name` (paramètres facultatifs, signature actuelle conservée) | SQL-depuis-etape | `SqlQueryDialog`, `_new_sql_query` des 3 dialogues d'étape |

## Lot B : changements de données

> Le schéma de référence est dans `../DONNEES.md`. Si un nom ou une colonne diffère ici, c'est `DONNEES.md` qui fait foi.

- **B1. Résolution simulée.** `resolve_tokens` et `core/expr_lang.py` (`_fn_now`, `_fn_today`) lisent `datetime.now()`. Ajouter un paramètre facultatif `now: datetime | None = None` à `resolve_tokens` et un moyen équivalent pour `expr_lang` (horloge portée par le contexte). Valeur par défaut inchangée : le worker et `db_extract.py` se comportent comme avant. Aucune colonne, rien à l'export.
- **B2. Détail des jetons.** Nouvelle fonction `resolve_tokens_report(template, ctx, now)` dans `core/steps/base.py`, qui renvoie le texte résolu et, pour chaque jeton, sa forme brute, sa valeur, son origine (date d'exécution, variable de pipeline, calcul, artefact) et s'il est resté non résolu. Elle s'appuie sur les mêmes expressions régulières que `resolve_tokens` ; un test vérifie que les deux donnent le même texte.
- **B3. Usages détaillés.** Comme dans la fiche Connexions (B4) : `find_profile_usages("sql_query_id", query_id)` renvoie, par étape, le pipeline, le libellé et la clé d'étape, la connexion (`db_type`, `profile_id`), `is_active` et `next_run_at`. `find_pipelines_using_profile` reste.
- **B4. Variables proposées.** Nouvelle fonction qui liste, pour les pipelines utilisant une requête, les variables déclarées (`get_pipeline_variables`, `default_expression`) et les noms publiés par les étapes EXTRACT_VARIABLES et SET_VARIABLE. Lecture seule.
- **B5. Journal.** Les créations, modifications, duplications et suppressions de requêtes ne passent pas par `log_audit_event`. Ajouter les types `sql_query_created`, `sql_query_updated`, `sql_query_deleted`, avec une ligne par pipeline touché (`pipeline_id` renseigné) ou une seule ligne sans pipeline si la requête est inutilisée. Aucune colonne (`AuditEvent.pipeline_id` accepte NULL). Le worker n'écrit pas ces événements. L'écran Historique doit savoir les afficher.

## Lot C : fonctions nouvelles (« proposé »)
Portent la pastille : C2 (à côté de « Comme le », dans SQL-apercu et SQL-resolu), C4, C5 (sous « Valider à blanc d'abord ») et C12 (aperçu de la modale). C1 et C3 n'ont pas de pastille sur leur frame mais figurent comme propositions dans `manquements.md`. Les autres sont absents du code sans pastille (Questions, point 3).

| # | Fonction | Frame | Dépend de |
|---|---|---|---|
| C1 | **Aperçu des résultats.** Bouton « Aperçu » et Ctrl Entrée. Règles : (1) lecture seule : la requête résolue est analysée par `sqlparse` ; une seule instruction, de type SELECT ou WITH … SELECT, sinon refus avec « L'aperçu n'exécute que des requêtes de lecture. » ; (2) même acceptée, elle tourne dans une transaction ouverte en lecture seule quand le moteur le permet (Oracle, PostgreSQL, MySQL), toujours annulée par `rollback` à la fin, jamais validée ; (3) limite de 100 lignes, lues par `fetchmany(100)` sans réécrire le SQL, mention « limité aux 100 premières lignes » ; (4) délai maximal de 30 s, comme le test Oracle ; (5) exécution dans un `QThread`, bouton « Annuler » ; (6) rien n'est écrit dans les runs ni l'historique. Affiche « ✓ 6 lignes », la durée, « sur Oracle VENTES, en lecture seule », « jetons résolus comme le 19/10 à 06:00 », colonnes avec leur type, « Copier » et « Exporter CSV ». Refusé pour une requête Spark SQL, qui ne passe pas par `SqlConnector` | SQL-apercu | `core/sql_db.py::SqlConnector`, `config_from_profile`, C2, C6, B1 |
| C2 | « Tester sur » (connexion, liste de `list_all_db_profiles`, préremplie avec celle de la première étape utilisatrice) et « Comme le » (prochaine exécution et variables d'un pipeline utilisateur, ou date libre) | SQL-apercu, SQL-resolu | B1, B3, B4 |
| C3 | **SQL résolu** : « Ce que la base recevra le 19/10 à 06:00, dans Reporting ventes J-1 », lignes contenant des jetons, tableau « N JETONS RÉSOLUS » (jeton, valeur, origine), phrase sur les jetons inconnus ; un jeton non résolu est signalé en `warning` | SQL-resolu | B1, B2, C2 |
| C4 | **Autocomplétion des jetons** à la frappe de `{` : « VARIABLES · DES PIPELINES QUI UTILISENT CETTE REQUÊTE », « AUSSI DISPONIBLES » (dates, `{expr:date_add(today(), -1)}`, `{rows_count}`), Tab insère, Échap ferme ; texte « tape { pour insérer » dans la barre d'état | SQL-jetons | B4, `ui/sql_editor.py` |
| C5 | **Alerte à l'enregistrement** d'une requête utilisée : onglet « Utilisée par » ouvert, « Enregistrer touchera ces N pipelines », nombre de lignes modifiées, prochain run, « Enregistrer quand même », « Valider à blanc d'abord » (`PipelineDryRunDialog`) | SQL-enregistrer | B3, C7 |
| C6 | Panneau du bas à 3 onglets « Résultats », « SQL résolu », « Utilisée par · N », « Déplier ▴ » et « Replier ▾ » ; dans « Utilisée par », flèche vers `MainWindow.open_atelier(pipeline_id, highlight_step_key)` | tous | B3 |
| C7 | « modifiée, non enregistrée » en haut à droite et repère `accent` dans la marge des lignes modifiées ; confirmation avant de quitter une requête modifiée ou d'en sélectionner une autre | SQL | `ui/sql_editor.py` |
| C8 | Ctrl S enregistre, affiché dans le bouton « Enregistrer » | SQL | `_on_save_query` |
| C9 | Confirmation avant « Importer .sql » quand l'éditeur n'est pas vide | SQL | `_on_import_sql` |
| C10 | Classement lecture ou écriture : pastille « écrit » sur la carte, filtres « Toutes », « Lecture », « Écriture », « Inutilisées », mention « lecture seule (SELECT) » dans la barre d'état ; même analyse que C1 | SQL | nouvelle fonction `classify_sql` |
| C11 | Barre d'état « ligne 12, col 31 » et « 14 lignes » | SQL | `QPlainTextEdit` |
| C12 | Modale depuis une étape : « Testée sur la connexion de l'étape : Oracle VENTES », aperçu intégré (« ✓ 214 lignes · 4 colonnes · 0,4 s »), « Aperçu », lien « Ouvrir dans l'atelier SQL », bouton « Enregistrer et utiliser dans l'étape » qui sélectionne bien la requête créée | SQL-depuis-etape | C1 ; Questions point 4 |

## Hors périmètre
- L'Atelier et le panneau du pipeline visibles derrière la modale de SQL-depuis-etape (fiche Atelier).
- La barre de navigation de gauche (lot 0).
- Les noms de requêtes, valeurs, durées et dates des maquettes : ce sont des exemples.
- L'exécution d'une requête qui écrit, sous quelque forme que ce soit, depuis cet écran.
- Le format des requêtes dans les exports `.dspipeline` (`_serialize_sql_query`) : inchangé.

## Critères d'acceptation
- [ ] Capture « SQL » à 1440×900 avec 8 requêtes : compteur, cartes, carte active, en-tête et barre d'état conformes à la maquette.
- [ ] Toutes les actions existantes fonctionnent après le restyle : nouvelle requête, dupliquer, importer, exporter, formater, enregistrer, supprimer (tests de `test_queries_view_workshop.py` et `test_sql_query_dialog.py` verts sans modification).
- [ ] Chaque bouton à icône seule a une infobulle (test).
- [ ] Aucune couleur en dur dans `ui/sql_editor.py` : `grep "#[0-9a-fA-F]\{6\}" ui/sql_editor.py` ne renvoie rien.
- [ ] Les jetons `{yyyy}`, `{var:region}`, `{expr:…}` sont surlignés ; un texte entre accolades dans une chaîne SQL ordinaire suit la même règle (test sur `SqlHighlighter`).
- [ ] Capture « SQL-rechercher » : 3 occurrences de `v.date_vente`, compteur 2/3.
- [ ] Capture « SQL-depuis-etape » ouverte depuis une étape DB_EXTRACT ; après « Enregistrer », l'étape sélectionne la requête créée, même si son nom n'est pas le dernier dans l'ordre alphabétique (test).
- [ ] B1 : sans paramètre `now`, `resolve_tokens` renvoie le même texte qu'avant (tests `test_variables_context.py`, `test_named_ports.py` verts) ; avec `now=2026-10-19 06:00`, `{yyyyMMdd}` donne `20261019` (test).
- [ ] B2 : `resolve_tokens_report` et `resolve_tokens` produisent le même texte sur 10 gabarits mêlant tous les jetons (test).
- [ ] C1 : une requête `DELETE`, `UPDATE`, `INSERT`, `MERGE`, `CREATE`, `DROP`, `ALTER`, `TRUNCATE` ou deux instructions séparées par `;` est refusée sans ouvrir de connexion (test avec un connecteur simulé).
- [ ] C1 : un SELECT qui renverrait 1 000 lignes n'en affiche que 100 et l'indique ; la transaction se termine par un `rollback` (test avec un connecteur simulé).
- [ ] C1 : capture « SQL-apercu » ; aucune ligne n'est ajoutée à `pipeline_runs` (test).
- [ ] C1 : un échec de connexion affiche le message du pilote sans le mot de passe (test qui cherche le mot de passe dans le texte affiché).
- [ ] C3 : capture « SQL-resolu » ; un jeton `{var:inconnue}` apparaît comme non résolu (test).
- [ ] C4 : capture « SQL-jetons » ; Tab insère `{var:region}` à la place de `{var:re` (test).
- [ ] C5 : capture « SQL-enregistrer » ; « Enregistrer » sur une requête inutilisée enregistre sans encadré (test).
- [ ] C7, C8, C9 : modifier le texte affiche « modifiée, non enregistrée » ; Ctrl S enregistre et l'efface ; importer un .sql sur un éditeur non vide demande confirmation (tests).
- [ ] B5 : enregistrer une requête utilisée par 2 pipelines écrit 2 lignes `sql_query_updated` (test).

## Questions ouvertes
1. **« Profil » ou « Tester sur ».** La maquette remplace « PROFIL » par « TESTER SUR », qui sert à l'aperçu et accepte tous les moteurs. Or `oracle_profile_id` filtre la liste des requêtes dans les dialogues DB_EXTRACT et DB_EXECUTE pour Oracle, et `test_save_persists_name_description_sql_and_profile` l'enregistre. Garder « Profil » à côté, ou retirer ce filtre et ce champ (la colonne reste en base) ? La modale SQL-depuis-etape n'a pas non plus de champ « Profil Oracle ».
2. **Suppression d'une requête.** Le bouton corbeille des cartes disparaît de la maquette, et aucun autre emplacement n'est dessiné. Où placer « Supprimer » ?
3. **Éléments sans pastille mais absents du code** : filtres Lecture, Écriture, Inutilisées et pastille « écrit », « modifiée, non enregistrée » et repère dans la marge, Ctrl S, « Tester sur », panneau du bas à onglets, « ligne, col », « lecture seule (SELECT) », « Ouvrir dans l'atelier SQL ». Classés en Lot C. À confirmer.
4. **Sélection après création depuis une étape.** `_new_sql_query` choisit `self._sql_queries[-1]`, alors que `get_sql_queries` trie par nom : la requête sélectionnée n'est pas forcément celle créée. Corriger dans C12 ou en correctif séparé ?
5. **Heure des jetons.** `resolve_tokens` et `expr_lang` utilisent l'heure locale de la machine, pas `AppSettings.timezone`. L'affichage « comme le 19/10 à 06:00 » doit-il suivre le fuseau réglé, au risque de différer de l'exécution réelle ?
6. **Couleurs sans clé.** Fond `#2a1d10` et contour `#4a3520` des jetons, chaînes `#7ec8a4`, ligne courante `#1f1c18`, repère `#6b4520`, encadré `#5a4416` ne sont pas dans `COLORS` ni dans FONDATIONS. Ajouter des clés au module partagé ou se rabattre sur `bg_active`, `border_strong`, `success`, `bg_hover` ?
7. **Aperçu sur SQL Server.** Il n'y a pas de transaction en lecture seule : le refus par analyse et le `rollback` suffisent-ils, ou faut-il exiger un compte en lecture seule ?

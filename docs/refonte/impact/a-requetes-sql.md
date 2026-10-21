# Note d'impact : lot A-Requetes-SQL — alignement visuel de l'écran Requêtes SQL

## Ce que le lot change
Alignement visuel de `ui/main_window/queries_view.py`, `ui/sql_editor.py` et
`ui/dialogs/sql_query_dialog.py` sur la maquette déjà validée (A1-A10 de
`docs/refonte/ecrans/Requetes-SQL.md`) : en-tête de la bibliothèque restylé avec surtitre dynamique
(« N dans la bibliothèque ») et aide en italique retirée, bouton « + Nouvelle requête » en
secondaire bordé accent pleine largeur, carte de requête ajustée (tailles de police, bord gauche
accent sur la carte active au lieu d'un contour complet), en-tête de l'éditeur, 4 des 5 boutons
d'action passés en icône seule 30px avec infobulle, couleurs de l'éditeur SQL prises dans `COLORS`
(plus aucune valeur en dur, nouvelle catégorie « fonctions » distincte des mots-clés), jetons
`{…}` surlignés (fond + texte orangés), liste de jetons de la barre d'état complétée avec
l'ensemble réellement résolu par `StepContext.resolve_tokens`, barre rechercher/remplacer
restylée, et la modale de création rapide (`SqlQueryDialog`) enrichie d'un surtitre contextuel
optionnel (« NOUVELLE REQUÊTE · POUR L'ÉTAPE « X » DE Y ») quand l'appelant le fournit. **Aucun
changement de base, de format d'export, ni de comportement d'exécution** (Lot B — résolution
simulée des jetons, détail des jetons résolus, usages détaillés, variables proposées, journal
d'audit — reste hors périmètre, comme pour tout lot A).

10 items Lot A, 5 Lot B, 12 Lot C (gated par `DECISIONS.md::P1`, comme tous les lots précédents).

Les 7 questions ouvertes de la fiche sont toutes résolues sans arbitrage nouveau nécessaire :
P6 (garder « Profil », pas « Tester sur »), la section « à garder tel quel » de la fiche elle-même
tranche la question du bouton de suppression (il reste sur la carte, la question ne se posait que
si on le retirait), P1 (éléments sans pastille gated Lot C), le bug de sélection `[-1]` déjà
corrigé par le correctif K2 (confirmé par grep, plus aucune occurrence dans le code — la fiche est
restée obsolète sur ce point), T4 (heure des jetons : garder l'heure machine), et les couleurs
citées comme sans clé (`#2a1d10`, `#4a3520`, `#7ec8a4`, `#6b4520`) ont déjà leurs clés
(`token_bg`, `token_border`, `sql_string`, `border_active`) — `#1f1c18`/`#5a4416` n'apparaissent
que dans des éléments Lot C, aucune nouvelle clé `COLORS` n'est nécessaire pour ce lot.

Un écart est nécessaire pour respecter le critère d'acceptation « aucune couleur en dur dans
`ui/sql_editor.py` » : la couleur des nombres (`#b5cea8` actuellement, non mentionnée par l'item
A6 de la fiche) est remplacée par `COLORS["sql_string"]` plutôt que par une nouvelle clé non
demandée — documenté en « Hors périmètre repéré » / écart volontaire dans la PR.

## Fichiers touchés
| Fichier | Nature du changement |
|---|---|
| `ui/main_window/queries_view.py` | A1-A5, A8 (en-tête sidebar, bouton nouvelle requête, carte, en-tête éditeur, boutons icône+tooltip, barre d'état) |
| `ui/sql_editor.py` | A6 (couleurs depuis COLORS + catégorie fonctions), A7 (surlignage jetons), A9 (restyle barre rechercher) |
| `ui/dialogs/sql_query_dialog.py` | A10 (paramètres optionnels `step_label`/`pipeline_name`, surtitre conditionnel) |
| `ui/step_editor/db_extract_config_dialog.py`, `db_execute_config_dialog.py`, `spark_sql_config_dialog.py` | A10 (passent `step_label`/`pipeline_name` à `SqlQueryDialog`) |
| `docs/refonte/manquements.md` | « Jetons incomplets » marqué fait (lot A-Requetes-SQL) |
| `scripts/capture_views.py` | nouveaux états SQL, SQL-rechercher, SQL-depuis-etape |
| `tests/test_queries_view_workshop.py`, `test_sql_query_dialog.py`, `test_sql_editor_widget.py` | revérifiés en premier (doivent rester verts **sans modification** selon la fiche), étendus avec des tests pour les comportements nouveaux |

Aucun nouveau fichier, aucune nouvelle clé `COLORS`, aucune dépendance Python ajoutée.

## Base de données
- Changement de schéma : aucun.
- Une base 0.45.0 s'ouvre sans erreur : sans objet, rien ne touche `database/db_manager.py::_migrate`.
- L'ancien worker tolère le nouveau schéma : sans objet (aucun schéma touché).

## Format d'export
Aucun changement. `_serialize_sql_query` et `CURRENT_SCHEMA_VERSION` (3) ne sont pas touchés.

## Heures affichées
Aucun changement : ce lot ne touche à aucun affichage d'heure (la question 5 de la fiche, heure
des jetons en machine locale, est tranchée par T4 — gardée telle quelle, non modifiée ici).

## Noms publics
`QueriesView.inp_search`, `.list_widget`, `._empty_label`, `._active_id`, `.inp_name`, `.inp_desc`,
`.editor`, `.cb_oracle`, `.lbl_usage`, `.btn_format/.btn_dup/.btn_export/.btn_import/.btn_save`,
`._on_new_query/._on_duplicate_query/._on_delete_query/._on_save_query/._on_import_sql/._on_export_sql`,
`._select_query`, `._workshop` gardent leur nom — vérifiés par grep avant tout changement (utilisés
par `tests/test_queries_view_workshop.py` et `tests/test_onboarding_empty_states.py`). Les
sélecteurs qualifiés `#queryCard`/`#queriesSidebar`/`#workshopHeader`/`#workshopStatus` et le
`stretch=1` partagé entre `list_widget`/`_empty_label` sont test-enforced
(`test_containers_use_qualified_stylesheet_selectors`,
`test_list_widget_and_empty_label_share_the_same_stretch_factor`) et ne changent pas de nom.
`SqlQueryDialog.__init__(parent=None, query=None)` garde sa signature actuelle en tête ;
`step_label`/`pipeline_name` sont ajoutés en paramètres optionnels à la fin, aucun appelant
existant n'est cassé.

## Tests
- Concernés : `test_queries_view_workshop.py`, `test_sql_query_dialog.py`,
  `test_sql_editor_widget.py`, `test_new_sql_query_selection.py`, `test_onboarding_empty_states.py`
  — tous revérifiés verts avant le premier changement de code.
- `test_queries_view_workshop.py` et `test_sql_query_dialog.py` doivent rester verts **sans
  modification de leurs assertions existantes** (critère d'acceptation explicite de la fiche) —
  seuls des tests sont ajoutés, aucun n'est modifié ni retiré.
- Ajoutés : tooltips non vides sur les 4 boutons d'action icône seule ; surlignage des jetons
  `{…}` (y compris dans une chaîne SQL ordinaire) ; absence de couleur en dur dans
  `ui/sql_editor.py` (reproduction du critère `grep`) ; surtitre conditionnel de `SqlQueryDialog`
  quand `step_label`/`pipeline_name` sont fournis, absent sinon ; liste de jetons complète dans la
  barre d'état.

## Dépendances et build
Aucune dépendance ajoutée. Icônes qtawesome déjà utilisées par l'application pour les 4 nouveaux
boutons icône seule (noms exacts choisis et vérifiés disponibles au moment de l'implémentation).

## Risques et retour arrière
Risque principal : le critère d'acceptation strict sur `ui/sql_editor.py` (zéro hex en dur), qui
oblige à trancher seul la couleur des nombres (voir écart documenté ci-dessus). Aucune donnée
persistée n'est affectée, aucun comportement d'exécution ne change. Retour arrière : revert des
commits de ce lot, aucune migration à défaire.

## Questions ouvertes
1. **Couleur des nombres dans l'éditeur** — A6 ne la mentionne pas ; `COLORS["sql_string"]` est
   réutilisée plutôt que d'introduire une clé non demandée par la fiche, pour satisfaire le
   critère d'acceptation « aucune couleur en dur ». Signalé en « Hors périmètre repéré » / écart
   volontaire.
2. **Texte du bouton principal de la modale `SqlQueryDialog`** — reste « Enregistrer » (texte
   actuel) : le texte long « Enregistrer et utiliser dans l'étape » vu sur la maquette
   `SQL-depuis-etape.html` appartient au contexte C12 (aperçu intégré), pas à l'item A10 qui ne
   demande qu'un « bouton principal » sans préciser de nouveau texte.
3. **Câblage de `step_label`/`pipeline_name` dans les 3 dialogues d'étape** — ajouté dans ce lot
   car trivial (les deux valeurs sont déjà disponibles dans chaque dialogue appelant) et
   explicitement couvert par l'item A10 de la fiche, même si la signature de `SqlQueryDialog` à
   elle seule aurait suffi au critère d'acceptation minimal.

## État final
À compléter en fin de lot (version, nombre de tests, écarts constatés en capturant).

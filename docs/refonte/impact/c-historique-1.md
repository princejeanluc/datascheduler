# Note d'impact : lot C-Historique-1 — panneau d'un run (origine, étapes, journal filtrable)

## Découpage retenu

`docs/refonte/ecrans/Historique.md` liste 14 items de Lot C (C1-C14). Plusieurs dépendent de
données qui n'existent pas encore (B5 : habitude d'un pipeline — C9/C10/C11 ; B6 : journal des
modifications étendu — C13/C14) ou d'un lot de données séparé (B4 : période/pagination — C1/C2).
Ce lot ne prend que les items dont la donnée existe déjà **et** qui portent sur le panneau d'un
run — exactement la description du lot 1 de l'Étape 4 dans `LOTS.md` : « panneau d'un run avec
ses étapes, son origine et son journal filtrable ».

**Dans ce lot** : C3 (colonne Déclenchement + mot d'origine), C4 (section Étapes), C5 (filtre
Tout/Erreurs + couleurs par niveau dans le journal), plus un prérequis découvert en lisant le
code (ci-dessous).

**Pas dans ce lot** (prochains découpages) : C6/C7 (recherche + copier/exporter le journal — pas
de dépendance bloquante, mais hors du périmètre strict « origine/étapes/journal filtrable » pour
garder la PR lisible) ; C8/C12 (filtre pipeline, recherche modifications — idem) ; C1/C2 (bloqués
par B4, non fait) ; C9/C10/C11 (bloqués par B5, non fait) ; C13/C14 (bloqués par B6, non fait).

## Découverte notable : A10 incomplet (prérequis de ce lot)

En lisant `ui/main_window/history_view.py`, le panneau latéral A10 (`_open_run_panel`/
`_build_run_panel_content`, lot A-Historique déjà mergé) existe bien, mais n'est atteint que
depuis la bulle du jour (`_on_bubble_run_clicked`). Le double-clic sur une ligne du tableau
principal (`_on_row_dbl_click` → `_open_log`) ouvre encore l'ancien `QDialog`
(`run_log_dialog.py::open_run_log_dialog`) — alors que la fiche décrit un seul frame
« Historique-run » atteint indifféremment depuis la bulle **ou** le tableau. Le panneau, en plus,
n'a pas le rafraîchissement en direct d'un run `RUNNING` que l'ancien dialogue a (point 7 de
« À garder tel quel »).

Comme C3/C4/C5 s'ajoutent à ce panneau, le construire sur un panneau qu'on n'atteint pas depuis
l'entrée principale de l'écran n'aurait pas de sens. Ce lot complète donc A10 : le double-clic sur
le tableau principal route désormais aussi vers `_open_run_panel`, et le rafraîchissement en
direct est porté dans le panneau — même patron que `dashboard_view.py` l.1213-1236
(`QTimer(content)`, arrêt sur statut terminal ou `self._side_panel.closed`), lui-même copié de
`run_log_dialog.py::_refresh_live`. `run_log_dialog.py` reste inchangé : toujours utilisé par
`PipelineDetailDialog` (chemin séparé, remplacé seulement quand C9/le bandeau pipeline existera —
fiche, question ouverte 3, hors périmètre ici).

## Ce que le lot change

- **C3 — Origine.** Colonne « Déclenchement » dans le tableau (8ᵉ colonne), mot d'origine dans le
  surtitre du panneau (`EXÉCUTION #id · STATUT · ORIGINE`). Table de traduction
  `trigger_origin` → `SCHEDULED` « Planifié », `MANUAL` « Manuel », `TRIGGERED` « Déclenché »
  (avec un lien discret « ↳ après #N » si `triggered_by_run_id`, sans navigation — juste la
  référence, comme le reste de la colonne, lot B4/pagination non fait), `CATCHUP` « Rattrapé »,
  `RESUME` « Reprise », `None` → « — » (run d'avant la refonte ou écrit par un ancien worker,
  conforme à `DONNEES.md`).
- **C4 — Étapes.** Nouvelle section « ÉTAPES » dans le panneau, sous le journal (ou au-dessus,
  à ajuster visuellement), lue via `db.get_run_steps(run_id)`. Réutilise les traductions déjà
  écrites pour l'Atelier (`ui/graph_editor/run_status.py`, même table statut/durée/tentatives —
  pas de nouvelle logique) : une ligne par étape (libellé, statut traduit, durée, tentatives si
  `>1`, lignes si renseigné), bandeau résumé « N min de travail » (somme des durées), étape
  `SKIPPED`/`SKIPPED_RESUME` affichée comme « non exécutée » / « reprise, non ré-exécutée ». Un
  run sans ligne (`get_run_steps` vide — run d'avant B1/D1, ou écrit par un ancien worker) :
  section absente, pas d'erreur (déjà le comportement actuel sans cette section).
- **C5 — Journal filtrable.** Barre de filtre « Tout / Erreurs » au-dessus du journal du panneau.
  Le journal passe d'un `QPlainTextEdit` à un rendu par ligne colorée (niveau → couleur :
  `ERROR`→`danger`, `WARN`→`warning`, `OK`→`success`, `INFO`→`text_dim`, mêmes clés que
  `_PANEL_EYEBROW_COLOR`/les badges de statut existants, aucune nouvelle clé `COLORS`). Source :
  `run.log_json` (lot D2-D4, déjà en place) si renseigné ; sinon repli décrit par la fiche (B3) —
  chaque ligne de `log_text` lue comme `ERROR` si elle contient « ERREUR : », sinon `INFO`, heure
  recomposée avec la date de `run.started_at` (le `[HH:MM:SS]` actuel n'a pas de date, voir T3) et
  passage de minuit géré (si une heure est plus petite que la précédente, jour suivant). Le filtre
  « Erreurs » fonctionne donc aussi, de façon approximative, sur un run d'avant la refonte.

Aucun changement de base : D2 (`trigger_origin`, `triggered_by_run_id`), D3 (`log_json`) et D1/B1
(`pipeline_run_steps`, via `get_run_steps` déjà existant) sont déjà en place (lots D2-D4 et B1,
mergés). Ce lot ne fait que les lire.

## Fichiers touchés

| Fichier | Nature du changement |
|---|---|
| `ui/main_window/history_view.py` | Colonne Déclenchement (tableau), route du double-clic vers le panneau, rafraîchissement en direct du panneau, sections Origine/Étapes/Journal filtrable du panneau |
| `ui/graph_editor/run_status.py` | Aucun changement de code — réutilisé tel quel (import) pour C4 |
| `docs/refonte/manquements.md` | Marquer « Résultat par étape absent », « Origine du run absente », « Journal brut » fait (lot C-Historique-1) |
| `tests/test_history_status_filter_and_navigation.py`, `test_history_view_graph_link.py` | Revérifiés, étendus si le double-clic change de comportement observable |
| Nouveaux tests | Panneau atteint depuis le tableau (pas seulement la bulle), colonne Déclenchement par valeur d'origine, section Étapes présente/absente, filtre Erreurs sur `log_json` et sur un `log_text` ancien, rafraîchissement en direct d'un run `RUNNING` ouvert depuis le tableau |

## Base de données
Aucun changement de schéma — ce lot consomme des colonnes déjà migrées (D1/D2/D3). Pas de
nouvelle migration, donc rien à vérifier côté base 0.45.0 au-delà de ce qui l'a déjà été pour ces
lots.

## Format d'export
Aucun changement — les runs et l'audit ne sont pas exportés (rappel de la fiche, Lot B).

## Heures affichées
Le surtitre du panneau, la colonne Déclenchement et la reconstruction d'heure du repli journal
(cas `log_text` ancien) passent par `to_display`/`fmt_time` (déjà utilisés dans ce fichier pour
l'heure de début/fin du panneau) — pas de nouvelle heure affichée brute.

## Noms publics
Aucun renommage. `_open_log` reste la méthode connectée au double-clic du tableau (son corps
change : elle appelle `_open_run_panel` au lieu de `open_run_log_dialog`) — pas de recherche
d'appelants externes nécessaire, c'est une méthode privée de `HistoryView` déjà seulement
connectée en interne au signal `doubleClicked` du tableau.

## Tests
- Tests existants concernés : `test_history_status_filter_and_navigation.py`,
  `test_history_view_graph_link.py`, `test_history_audit_log.py` (non touché par ce lot, vérifié
  pour confirmer qu'aucune de ses assertions ne dépend du chemin du double-clic), `test_run_log_dialog.py`
  (doit rester vert sans modification — `run_log_dialog.py` n'est pas touché).
- Tests ajoutés : voir tableau « Fichiers touchés » ci-dessus.

## Dépendances et build
Aucune dépendance ajoutée.

## Risques et retour arrière
Risque principal : remplacer la destination du double-clic change un comportement observable
existant (`T1` — le test concerné doit être mis à jour, pas assoupli, et le dire ici : c'est fait
dans le tableau ci-dessus). Retour arrière : une seule PR, un seul revert suffit, aucune migration
à défaire.

## Questions ouvertes
Aucune bloquante pour ce découpage précis. Pour mémoire (déjà vérifié dans le code, pas besoin de
demander) :
- Q1 de la fiche (segment « Réussis » manquant) : déjà résolu dans le code, un segment « Succès »
  existe (`_STATUS_FILTER_OPTIONS`) — la fiche décrivait un état antérieur au lot A. Rien à faire.
- Q6 (structure du tableau, lignes de jour) : déjà résolu, un seul `QTableWidget` avec `setSpan` —
  rien à faire.
- Q8 (simple/double-clic) : déjà résolu, double-clic, conforme à T6 — rien à faire.
- Q3, Q4, Q7, Q9, Q10 : portent sur C9/C10/C11 (bandeau pipeline, B5) ou B7 (fuseau des jours) ou
  la navigation de sortie de l'Atelier — hors périmètre de ce lot précis, non touchés.

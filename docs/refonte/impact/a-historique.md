# Note d'impact : lot A-Historique — alignement visuel de l'écran Historique

## Ce que le lot change
Alignement visuel de l'écran Historique (`ui/main_window/history_view.py`, classe `HistoryView`)
sur sa maquette déjà validée (A1-A13 de `docs/refonte/ecrans/Historique.md`) : en-tête avec
surtitre dynamique (« N EXÉCUTIONS SUR 7 JOURS · N ÉCHECS ») et deux onglets « Exécutions »/
« Journal des modifications » remplaçant l'actuel bouton+`QDialog`, recherche étendue au message
d'erreur, filtre de statut en boutons segmentés (remplace la liste déroulante), carte de
fréquence à 4 niveaux de couleur, tableau principal réordonné (Heure en premier) et groupé par
jour (AUJOURD'HUI/HIER/date), statuts affichés en français, actions de ligne sans la loupe (le
double-clic ouvre) avec « Reprendre depuis l'échec » ajouté, bulle ancrée (nouveau composant
partagé) remplaçant le `QDialog` du jour cliqué, panneau latéral partagé (`SidePanel`) remplaçant
l'ouverture directe du journal complet pour cet écran, onglet « Journal des modifications » avec
types traduits et colorés + note de bas de page. **Aucun changement de base** (Lot B de la fiche —
résultat par étape, origine du run, journal à niveaux, pagination, habitude d'un pipeline, journal
étendu, fuseau des jours — reste hors périmètre, comme pour tout lot A).

Fiche la plus large jusqu'ici (13 items Lot A, 7 Lot B, 14 Lot C). Contrairement à Aujourd'hui/
Pipelines, cette maquette porte par endroits des pastilles « proposé » (période, colonne
Déclenchement, section Étapes, catégories du journal) — mais pas partout où la fiche gate un item
(la colonne « Durée · vs habitude », C10, n'en a pas) : le partage Lot A/B/C repose entièrement sur
les tableaux de la fiche, jamais sur la présence d'une pastille dans une maquette donnée.

Les questions ouvertes de la fiche sont résolues par `DECISIONS.md` (P1, P4, T6), par la fiche
elle-même (questions 3, 7, 9, 10 sans objet car dépendantes d'items gated), ou déjà tranchées
(segment « Réussis » déjà présent dans le code, confirmé en le lisant) — seule la question 5
(textes du journal des modifications) a nécessité une vraie décision utilisateur
(`AskUserQuestion`), tranchée sur **reformuler à l'affichage** (traduire le type + le motif
`action=...` de l'import, sans jamais inventer une donnée non stockée).

## Fichiers touchés
| Fichier | Nature du changement |
|---|---|
| `ui/main_window/history_view.py` | l'essentiel du lot (A1-A13) |
| `ui/main_window/widgets.py` | `_heatmap_day_color_key` étendu à 4 niveaux (T2 : `bg_card` au lieu de `border` pour une case vide, `success_dim` pour 1 réussite) |
| `ui/components/bubble.py` (nouveau) | `Bubble`, composant partagé « ancrée à un élément, avec une flèche » (FONDATIONS.md section 3) |
| `ui/components/__init__.py` | réexporte `Bubble` |
| `scripts/capture_views.py` | nouveaux états Historique/-jour/-run/-modifications |
| `tests/test_history_*.py` | revérifiés en premier, étendus/mis à jour (T1) |

`ui/main_window/run_log_dialog.py` et `ui/dialogs/pipeline_detail_dialog.py` ne sont **pas**
modifiés : le premier reste utilisé tel quel par le second (qui n'est lui-même touché par aucun
item de ce lot, question ouverte 3 de la fiche — le bandeau qui le remplacerait un jour est C9,
gated). La nouvelle vue détail en panneau latéral d'Historique (A10) est un chemin de code séparé,
pas un remplacement de cette fonction partagée.

## Base de données
- Changement de schéma : aucun.
- Une base 0.45.0 s'ouvre sans erreur : sans objet, rien ne touche `database/db_manager.py::_migrate`.
- L'ancien worker tolère le nouveau schéma : sans objet (aucun schéma touché).

## Format d'export
Aucun changement. `CURRENT_SCHEMA_VERSION` reste à 3.

## Heures affichées
- Converties (`fmt_time`/`fmt_datetime`/`fmt_relative`) : heure de chaque run (tableau, bulle,
  panneau), horodatage du journal des modifications.
- Préfixes `[HH:MM:SS]` de `log_text` (écrits en UTC par `PipelineResult.log`) reconvertis à
  l'affichage en reconstruisant la date depuis `run.started_at` avec détection du passage de
  minuit (T3 — l'écriture ne change pas ; c'est l'algorithme que la fiche décrit elle-même comme
  seul disponible sans B3).
- `get_run_counts_by_day`/`get_runs_for_pipeline_on_day` restent en UTC (B7, hors périmètre) : un
  run de fin de journée peut apparaître sur la case du calendrier du lendemain à Paris — signalé
  dans la PR, non corrigé.

## Noms publics
`refresh()`, `set_status_filter(status)`, `open_atelier_requested(int, object, bool)`,
`_build_audit_table`, `_build_day_runs_table` gardent exactement leur nom et signature — vérifiés
par grep avant tout changement. `cb_status` (QComboBox) disparaît, remplacé par des boutons
segmentés internes — aucun appelant externe ne le référence (vérifié par grep, seul
`set_status_filter` est l'API publique utilisée par `window.py`).

## Tests
- Concernés : `test_history_status_filter_and_navigation.py`, `test_history_audit_log.py`,
  `test_history_view_graph_link.py`, `test_run_log_dialog.py`, `test_pipeline_detail_dialog.py`,
  `test_pipeline_topology_dialog.py`, `test_activity_stats.py`, `test_audit_log.py`,
  `test_db_manager.py`, `test_capture_views.py` — tous revérifiés verts avant le premier
  changement de code, et à chaque étape ensuite.
- Mis à jour (T1) : tout test lisant `table.item(r, 0)` comme nom de pipeline (devient colonne 1,
  colonne 0 = Heure, retrouvé par `view._run_ids.index(run.id)` plutôt qu'une ligne fixe une fois
  les en-têtes de groupe de jour introduites) ; `test_heatmap_day_color_key_worst_result_wins`
  (case vide : `"border"` → `"bg_card"`, + cas `success_dim`) ; tests ouvrant un `QDialog` pour le
  jour cliqué ou le journal des modifications (remplacés par `Bubble`/onglet, plus de `QDialog` à
  monkeypatcher à cet endroit) ; `test_history_view_has_audit_log_button` (méthode supprimée,
  remplacé par un test du second onglet).
- Ajoutés : un test par comportement nouveau — onglets, surtitre dynamique, 4 niveaux du
  calendrier + légende + repères de mois, groupes de jours, formats durée/lignes, badge français +
  `status_code`, filtre segmenté, recherche étendue à l'erreur, actions de ligne (reprendre),
  `Bubble` (ouverture/clic de ligne/fermeture), panneau de run (boutons de pied, conversion
  `log_text`), types/détail traduits du journal des modifications, note de bas de page.
- Suite complète : 1 seul échec, préexistant et sans rapport (`test_pipeline_graph_engine_parallel.py
  ::test_run_pipeline_uses_parallel_engine_when_pipeline_opted_in`, un seuil de minuterie dépassé de
  quelques dizaines de ms — flaky, pas touché par ce lot).

## Version
`0.50.0` → `0.51.0` (MINOR — nouvel écran aligné, aucune rupture de compatibilité).

## Dépendances et build
Aucune dépendance ajoutée. Aucune icône nouvelle hors `qtawesome` déjà utilisé.

## Risques et retour arrière
Risque visuel/structurel (réordonnancement de colonnes, remplacement de deux `QDialog` par un
nouveau composant partagé) — aucune donnée persistée n'est affectée, aucun comportement de
lancement/reprise de pipeline ne change. Retour arrière : revert des commits de ce lot, aucune
migration à défaire.

## Questions ouvertes
1. **Surtitre identique sur les deux onglets** — la fiche (A1, frame « toutes ») décrit un seul
   surtitre dynamique partagé ; la maquette `Historique-modifications.html` montre un texte
   différent (« QUI A CHANGÉ QUOI, ET QUAND »). Fiche prime (REGLES.md section 1) : même surtitre
   sur les deux onglets, écart documenté plutôt que source d'un arrêt pour une question cosmétique.
2. **Textes du journal des modifications** — tranché par l'utilisateur : reformulés à l'affichage
   (type + motif `action=...` de l'import), jamais de donnée inventée pour un `detail` vide ou
   sparse (ex. « Création » sans détail reste « — », pas un recalcul du nombre d'étapes actuel).
3. **`HistoryView._build_day_runs_table`** — la fiche (point 6 de « à garder tel quel ») la cite
   comme testée ; A9 construit la bulle avec des lignes composites (heure/statut·durée/erreur/
   flèche) plutôt que cette `QTableWidget`, pour coller au rendu de la maquette
   `Historique-jour.html` (pas une grille à en-têtes de colonnes dans une bulle de 330px). Devenue
   orpheline (plus aucun appelant en production), tranché par l'utilisateur : supprimée avec son
   test plutôt que gardée inutilisée ou réintroduite comme contenu de la bulle.

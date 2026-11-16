# Note d'impact : lot C-Historique-2 — recherche, copier et exporter le journal

## Contexte

Suite de C-Historique-1 (C3/C4/C5, mergé PR #96). Reprend les deux items Lot C de la fiche
`docs/refonte/ecrans/Historique.md` qui n'ont **aucune dépendance** (« aucune » dans la colonne
« Dépend de ») et qui sont restés hors périmètre de C-Historique-1 uniquement pour la taille de
la PR :

- **C6** — Recherche dans le journal et bouton « Copier ».
- **C7** — Bouton « Exporter le journal » vers un fichier texte.

C8 (filtre « Tous les pipelines ▾ » sur le tableau principal) a aussi « aucune » dépendance mais
porte sur un autre cadre (Historique, pas Historique-run) : laissé à une slice séparée pour garder
ce lot à une seule préoccupation (le panneau d'un run).

## Ce que le lot change

- Un champ « Chercher dans le journal » apparaît dans le panneau latéral d'un run, au-dessus du
  journal, à gauche du bascule Tout/Erreurs (C6). Une ligne n'est affichée que si elle passe **à
  la fois** le filtre de niveau et la recherche (sous-chaîne, insensible à la casse, sur le texte
  du message).
- Un bouton « Copier » apparaît dans la même rangée (C6) : copie dans le presse-papiers le texte
  actuellement affiché (donc déjà filtré par niveau et par recherche).
- Un bouton « Exporter le journal » apparaît dans le pied du panneau, aligné à droite comme sur la
  maquette (C7) : `QFileDialog.getSaveFileName` (même patron que `queries_view.py::_on_export_sql`),
  nom par défaut `run-{id}-journal.txt`, écrit le même texte affiché (filtré) dans le fichier.
- Aucun changement sur le tableau principal, la bulle du jour, ni l'onglet des modifications.

**Choix non précisé par la fiche, documenté ici plutôt que tranché ailleurs** : « Copier » et
« Exporter » agissent sur le texte **filtré actuellement visible**, pas sur le journal complet.
Raison : cohérent avec ce que l'utilisateur voit à l'écran au moment du clic, et évite d'exporter
des lignes qu'il vient justement de masquer avec la recherche/le filtre. Réversible sans migration
si ce choix est contesté.

## Fichiers touchés

| Fichier | Nature du changement |
|---|---|
| `ui/main_window/history_view.py` | `_build_run_panel_content` : champ de recherche + bouton Copier dans `log_filter_row` ; bouton Exporter dans `footer` ; `_render_log_entries`/`_apply_log_filter` étendus pour filtrer aussi par sous-chaîne |
| `docs/refonte/manquements.md` | ligne « Journal brut » : recherche et export marqués faits (lot C-Historique-2, C6/C7) |
| `tests/test_history_run_panel.py` | tests ajoutés (recherche filtre le journal affiché, combinée au filtre de niveau ; Copier met le texte filtré dans le presse-papiers ; Exporter écrit le texte filtré dans le fichier choisi) |

Aucun autre fichier : pas de changement de `core/`, `database/`, ni d'un autre écran.

## Base de données
Aucun changement de schéma. Rien à migrer, rien à tolérer côté ancien worker (le worker n'est pas
concerné, ce lot est purement une vue sur des données déjà en base).

## Format d'export
Aucun changement. Le fichier `.txt` produit par « Exporter le journal » est un export utilisateur
ponctuel, sans rapport avec `.dspipeline`/`CURRENT_SCHEMA_VERSION`.

## Heures affichées
Aucune nouvelle heure affichée ; le texte de chaque ligne du journal (déjà converti par
`_log_entries_for_render`/`to_display`, lot C-Historique-1) est repris tel quel pour la recherche,
la copie et l'export.

## Noms publics
Aucun. `_render_log_entries` et `_apply_log_filter` restent des fonctions/fermetures internes au
module, déjà non publiques.

## Tests
- Tests existants concernés : `tests/test_history_run_panel.py` (doit rester vert, aucune
  assertion existante modifiée).
- Tests ajoutés : recherche seule, recherche + filtre Erreurs combinés, recherche sans résultat
  (message dédié ou liste vide à définir pendant l'implémentation), Copier (mock du presse-papiers
  Qt ou lecture de `QApplication.clipboard().text()`), Exporter (mock de
  `QFileDialog.getSaveFileName` pour pointer vers un fichier temporaire, puis lecture de son
  contenu).

## Dépendances et build
Aucune dépendance ajoutée. `QApplication.clipboard()` et `QFileDialog` sont déjà importés ailleurs
dans le code (`queries_view.py`, `pipeline_export_dialog.py`) — aucun nouvel import de module
externe.

## Risques et retour arrière
Risque faible : ajout d'éléments dans un panneau existant, aucune donnée ni fichier stocké ne
change. Retour arrière : revert du commit, rien à nettoyer en base.

## Questions ouvertes
Aucune contradiction fiche/code/maquette trouvée pour C6/C7. Le point « filtré vs. complet » pour
Copier/Exporter ci-dessus est un choix d'implémentation, pas une question bloquante.

# Note d'impact : lot C-Historique-3 — filtre « Tous les pipelines »

## Contexte

Suite de C-Historique-1 (C3/C4/C5) et C-Historique-2 (C6/C7). Reprend **C8** — le dernier item
Lot C de la fiche `Historique.md` sans aucune dépendance de données — resté hors périmètre de
C-Historique-2 uniquement parce qu'il porte sur un autre cadre (Historique, pas Historique-run).

C9/C10/C11 (bandeau résumé, colonne « vs habitude », liens de la bulle), qui apparaissent sur la
même maquette (`Historique-pipeline.html`) que C8, dépendent de B5 (habitude d'un pipeline, pas
fait) et/ou de C8+C1 (C1 dépend de B4, pas fait non plus) : ils restent hors périmètre.

## Ce que le lot change

- Un bouton « Tous les pipelines ▾ » apparaît dans la rangée de filtres du tableau Historique,
  entre la recherche et les segments de statut (ordre de la maquette `Historique.html`). Un clic
  ouvre un menu listant tous les pipelines (`db.get_pipelines()`, actifs et inactifs confondus —
  un pipeline désactivé peut avoir un historique à consulter, cohérent avec le point 10 de « À
  garder tel quel » : un pipeline supprimé garde son nom affiché).
- Choisir un pipeline remplace ce bouton par une puce « Pipeline : *Nom* × » (maquette
  `Historique-pipeline.html`) ; le tableau ne montre plus que les runs de ce pipeline. Un clic sur
  « × » revient à « Tous les pipelines » et à la liste complète.
- Le filtre pipeline se combine avec le filtre de statut et la recherche libre, déjà combinés
  entre eux (`_apply_filters`) : une ligne doit satisfaire les trois pour rester visible.
- La carte « Fréquence d'exécution » et le surtitre (« N EXÉCUTIONS SUR 7 JOURS ») ne changent
  pas : la maquette `Historique-pipeline.html` montre le même surtitre global que `Historique.html`
  (148 exécutions, non filtré) — confirmé en relisant son HTML brut, pas seulement le PNG.

**Limite documentée, pas un défaut introduit par ce lot** : comme le filtre de statut et la
recherche, le filtre pipeline s'applique aux 100 runs déjà chargés par `get_recent_runs(limit=100)`
— un run plus ancien d'un pipeline peu actif, au-delà de ce plafond global, n'apparaît pas tant que
B4 (pagination, qui lève justement ce plafond) n'est pas fait. Comportement déjà partagé par le
filtre de statut et la recherche existants, pas une régression propre à C8.

## Fichiers touchés

| Fichier | Nature du changement |
|---|---|
| `ui/main_window/history_view.py` | `_build_ui` : bouton + puce dans `filters_row` ; `refresh()` : `self._run_pipeline_ids` (ligne → `run.pipeline_id`) ; `_apply_filters` étendu au filtre pipeline |
| `tests/test_history_status_filter_and_navigation.py` | tests ajoutés (sélection filtre le tableau, combinaison avec statut/recherche, « × » réinitialise) |

Aucun autre fichier : pas de nouvelle fonction `db.*`, `db.get_pipelines()` existe déjà et sert
déjà ailleurs (menu « ⋯ » de Pipelines, etc.).

## Base de données
Aucun changement de schéma.

## Format d'export
Aucun changement.

## Heures affichées
Aucune nouvelle heure affichée.

## Noms publics
Aucun changement de nom public existant. Nouveaux attributs internes (`_run_pipeline_ids`,
`_pipeline_filter_id`), non exposés.

## Tests
- Tests existants concernés : `tests/test_history_status_filter_and_navigation.py`,
  `tests/test_history_view_graph_link.py` (doivent rester verts sans modification — aucune
  assertion sur l'ensemble des colonnes ou boutons n'est touchée par cet ajout, qui ne change ni
  le nombre de colonnes ni l'ordre des actions de ligne).
- Tests ajoutés : sélectionner un pipeline dans le menu filtre le tableau à ses seuls runs ;
  combinaison avec le filtre « Échecs » ; « × » de la puce réinitialise à « Tous les pipelines ».

## Dépendances et build
Aucune. `QMenu` est déjà utilisé ailleurs (`pipelines_view.py`).

## Risques et retour arrière
Risque faible : nouvel élément d'interface, filtre purement client-side sur des données déjà
chargées. Retour arrière : revert du commit.

## Questions ouvertes
Aucune contradiction fiche/code/maquette trouvée pour C8.

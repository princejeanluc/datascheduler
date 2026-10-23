# Note d'impact — Lot A-Atelier-main (A6 à A16)

Huitième lot de la refonte Atelier, après Grammaire (PR #85) et B1 (PR #86). Portée : le cadre
Main de l'Atelier (`docs/refonte/ecrans/Atelier.md`, états « Main ») — en-tête, recherche de
nœud, panneau de paramètres du pipeline. Pur alignement visuel/structurel, **sans changement de
base ni de format d'export**.

Gouvernance : `DECISIONS.md::P11` et `P1` tranchés ce tour-ci (voir le fichier) — le point de
couleur de famille (déjà livré) est acté définitivement, et le Lot C de l'Atelier (C7, C9) est
autorisé à démarrer avant le Lot A des autres écrans, à la demande explicite de l'utilisateur à
partir des maquettes Atelier-ajout/Atelier-echec. Ce lot-ci reste du Lot A pur ; C7/C9 suivront en
lots séparés.

## Items couverts

- **A6** — En-tête : fil d'Ariane « Pipelines / <nom> », « Pipelines » déclenche le même code que
  l'actuel bouton « Retour aux pipelines » (`_on_back_clicked`, nom public inchangé).
- **A7** — Bouton secondaire « Valider à blanc » : instancie `PipelineDryRunDialog(pipeline_id,
  name)` — ce dialogue existe déjà dans le code (orphelin depuis que `PipelinesView` utilise un
  panneau latéral, cf. commentaire `_on_validate_pipeline`), la fiche demande explicitement de le
  réutiliser ici.
- **A8** — Bouton principal « Exécuter » : factorise le corps de `PipelinesView._on_run_pipeline`
  dans une nouvelle fonction libre `ui/main_window/pipeline_actions.py::run_pipeline_now(parent,
  pipeline_id)`, appelée par les deux écrans. `PipelinesView._on_run_pipeline` devient un appel à
  cette fonction + son `self.refresh()` — nom public conservé.
- **A10** — Recherche de nœud en surimpression en haut à droite du canevas (actuellement dans une
  barre horizontale au-dessus) : nouveau petit widget flottant parenté au viewport, même patron
  que `ZoomWidget`/`GraphMinimapWidget`/`EditorToolRail`. Le texte d'aide (« Tirer d'un port de
  sortie… ») devient un label flottant en haut à gauche du canevas (position fixe, pas une
  info-bulle — la maquette le montre en permanence).
- **A11** — Panneau de droite : surtitre Mono « PIPELINE » + case « Actif » sur la même ligne.
- **A12** — Planification : boutons segmentés (Jour/Semaine/Mois/Cron) remplaçant les
  `QRadioButton` actuels — même groupe logique, juste un autre widget de présentation.
- **A13** — Déclenchement en phrase : « Lancer aussi après [pipeline] si elle [réussit/échoue/se
  termine] » remplaçant les labels « Après : »/« Si : » — mêmes `QComboBox`, mêmes valeurs
  SUCCESS/FAILURE/ALWAYS.
- **A14** — Section « EXÉCUTION » : étiquette de section ajoutée au-dessus des deux cases à
  cocher déjà existantes (aucune logique changée), « 4 max » inline sur la case parallèle.
- **A15** — Variables : table en police Mono, « + Ajouter » devient un lien (texte seul, couleur
  accent) au lieu d'un bouton bordé ; variables écrites par une étape du canevas (
  `node_facts.compute_written_variables` sur chaque `PipelineStep` du pipeline) affichées en
  lecture seule « écrite par <libellé étape> » si elles ne sont pas déjà une variable déclarée.
- **A16** — `MainWindow.open_atelier()` force `self._nav_rail.set_active_index(1)` après
  `_navigate(8)` (qui ne surligne rien pour l'indice hors-rail 8) — aucune modification de
  `NavRail` lui-même.

## Hors périmètre de ce lot (signalé, pas fait)

- **A9** (bandeau « Relancer tout »/« Reprendre depuis l'échec ») appartient à la frame
  Atelier-echec (C9), lot séparé à venir.
- **C6** (Brouillon/Publier, pastille « N modifications », enregistrement automatique) : dépend de
  B2 (`pipeline_drafts`), qui n'existe pas. Les deux boutons « Enregistrer le graphe »/
  « Enregistrer les paramètres » restent tels quels (`DECISIONS.md::P2`).
  « Aller à, exécuter… Ctrl K » : hors périmètre explicite (`Palette.md`).
- **C8** (compartiment bas Chronogramme/Journal/Variables/Validation) et **C10/C11/C12** : Lot C,
  lots séparés à venir (C8/C9 directement après celui-ci).

## Base de données / export / build

Aucun changement. Aucune nouvelle dépendance.

## Fichiers touchés

| Fichier | Nature |
|---|---|
| `ui/main_window/window.py` | A16 (forcer l'index 1 de la nav rail) |
| `ui/main_window/atelier_pipelines_view.py` | A6, A7, A8 (en-tête restructuré) |
| `ui/main_window/pipeline_actions.py` (nouveau) | A8 (factorisation `run_pipeline_now`) |
| `ui/main_window/pipelines_view.py` | A8 (`_on_run_pipeline` délègue à `run_pipeline_now`) |
| `ui/graph_editor/graph_editor_widget.py`, `graph_view.py` | A10 |
| `ui/graph_editor/node_search_overlay.py` (nouveau) | A10 |
| `ui/step_editor/pipeline_settings_panel.py` | A11-A15 |
| `scripts/capture_views.py` | nouvel état Main (Atelier) |

## Tests

Revérifiés sans affaiblissement : `tests/test_atelier_pipelines_view.py`,
`tests/test_pipeline_settings_dialog.py`, `tests/test_pipelines_view*.py`,
`tests/test_graph_editor_dialog.py` (ou équivalent couvrant `_build_ui`/recherche),
`tests/test_node_facts.py`. Tests ajoutés pour : `run_pipeline_now` factorisée, position/présence
du widget de recherche flottant, boutons segmentés de fréquence, phrase de déclenchement, lignes
« écrite par X » des variables, `set_active_index(1)` appelé depuis `open_atelier()`.

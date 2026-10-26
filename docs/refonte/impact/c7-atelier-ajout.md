# Note d'impact — C7 : panneau « Ajouter » (Atelier-ajout)

Premier lot C de l'Atelier (`docs/refonte/ecrans/Atelier.md`), débloqué par `DECISIONS.md::P1`
tranché pour l'Atelier. Remplace le flux actuel « bouton + du rail → `StepTypeChooserDialog`
(modal) → dialogue de config (modal) » par un panneau latéral persistant avec aperçu et
insertion par clic, glisser-déposer ou Entrée — fonction nouvelle (« proposé »), **sans
changement de base ni de format d'export** : aucune nouvelle table, les étapes insérées suivent
exactement le même chemin d'écriture (`PipelineGraphScene.add_node`/`add_edge`) qu'aujourd'hui.

## Ce qui ne change pas

- `StepTypeChooserDialog` reste intact (recherche, catégories, Mes modèles avec renommer/
  supprimer) — toujours utilisé par `PipelineGraphEditorDialog` (enveloppe de compatibilité,
  ~13 fichiers de tests). Seul l'appelant `graph_editor_widget.py::_on_add_step` change de
  comportement, et seulement en mode Atelier réel (`show_settings_shortcut_button=False`) — même
  bascule déjà établie pour A10 (recherche de nœud). Le dialogue de compatibilité garde le
  flux modal actuel à l'identique.
- Le dialogue de configuration d'étape (`_open_config_dialog`) reste le point de saisie des
  champs : ce lot n'implémente pas l'édition inline après insertion (C1, qui reste un lot séparé
  à venir). Après un clic sur « Insérer à l'emplacement marqué », un glisser-déposer abouti, ou
  Entrée, le dialogue de config s'ouvre immédiatement — comme aujourd'hui pour un ajout via le
  rail — pré-rempli par `chosen_config` si le choix vient de « Mes modèles ».
- Renommer/Supprimer un modèle reste possible : repris dans le nouveau panneau (le compacter
  aurait rendu cette fonction inaccessible en pratique, `_on_add_step` étant son seul appelant).

## Décisions d'implémentation (aucune question ouverte de la fiche ne couvre ces détails — jugement
documenté, pas de question posée : risque faible, réversible)

1. **Sélection vs glisser** : un clic simple sur une carte la *sélectionne* (aperçu à droite,
   active le bouton d'insertion) ; un glisser réel (au-delà de `QApplication::startDragDistance`)
   démarre un `QDrag`. Nécessaire car la fiche distingue explicitement les deux usages
   (« glisser… · Entrée insère après la sélection »).
2. **Emplacement « marqué »** : une arête sélectionnée dans le canevas (déjà sélectionnable,
   `EdgeItem.ItemIsSelectable`, rien à ajouter) devient le point de greffe — le bouton/Entrée
   greffent la nouvelle étape dedans (ancienne arête supprimée, deux nouvelles créées,
   reliage automatique). Sinon, un seul nœud sélectionné devient le point d'« après » (une
   arête ajoutée depuis son premier port de sortie non-erreur). Sinon, insertion flottante à la
   position par défaut actuelle (`_next_new_node_pos`), comme aujourd'hui.
3. **Glisser-déposer sur le canevas** : déposer sur une arête greffe (même logique que 2) ;
   déposer sur du vide ajoute un nœud flottant à la position de dépôt. Le survol d'une arête
   pendant le glisser la sélectionne visuellement (retour déjà existant du style de sélection,
   rien de nouveau à peindre).
4. **Données du panneau d'aperçu** : « Reçoit »/« Produit » viennent de `get_step_requirements`/
   `step_produces_output_file` (citées par la fiche) — jamais une chaîne en dur par type. « Port
   d'erreur » est constant (« oui, comme toutes les étapes », `get_step_output_ports` ajoute
   toujours `error`). « Connexion » et « À remplir après l'insertion » n'ont pas de fonction
   source dans le code (texte descriptif, pas une donnée) : deux petits dictionnaires statiques
   dans `step_preview_panel.py`, un par type, dérivés des champs réels de chaque dialogue de
   config (vérifiés un par un) — pas une invention.

## Fichiers touchés (nouveaux)

| Fichier | Contenu |
|---|---|
| `ui/graph_editor/step_library_panel.py` | `StepLibraryPanel` : recherche, Mes modèles, Passerelles (3 badges losange), catégories — cartes sélectionnables + source de glisser. Réutilise `_DESCRIPTIONS`/`_CATEGORY_ORDER` de `step_type_chooser_dialog.py` (import, pas de duplication). |
| `ui/graph_editor/step_preview_panel.py` | `StepPreviewPanel` : aperçu + bouton d'insertion. |

## Fichiers touchés (modifiés)

| Fichier | Nature |
|---|---|
| `ui/graph_editor/graph_editor_widget.py` | `_on_add_step` ouvre le panneau (mode Atelier réel) au lieu du dialogue modal ; logique d'insertion (greffe/après/flottant) ; signal exposé pour que l'hôte bascule son panneau de droite. |
| `ui/graph_editor/graph_view.py` | `setAcceptDrops`, `dragEnterEvent`/`dragMoveEvent`/`dropEvent` (mode Atelier réel seulement). |
| `ui/main_window/atelier_pipelines_view.py` | Bascule le conteneur de droite entre `PipelineSettingsPanel` (existant, jamais détruit) et `StepPreviewPanel` selon l'état du panneau Ajouter. |
| `scripts/capture_views.py` | Nouvel état `atelier-ajout`. |
| `tests/test_graph_tool_rail.py` | Le test qui vérifie que le bouton + ouvre `StepTypeChooserDialog` est mis à jour (T1) : en mode Atelier réel, il ouvre désormais le panneau. |

## Base de données / export / build

Aucun changement. Aucune dépendance Python ajoutée (glisser-déposer = `QDrag`/`QMimeData`,
déjà dans PySide6).

## Tests

Revérifiés : `tests/test_graph_tool_rail.py`, `tests/test_step_type_chooser.py` (inchangé, dialogue
intact), `tests/test_graph_editor_dialog.py`. Ajoutés : construction du panneau, filtrage par
recherche, sélection met à jour l'aperçu, insertion flottante/après-sélection/greffe-sur-arête
(bouton et Entrée), glisser-déposer sur arête et sur vide, Mes modèles (renommer/supprimer
toujours accessibles), bascule du panneau de droite dans `AtelierPipelinesView`.

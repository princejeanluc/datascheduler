# Note d'impact : lot A-Pipelines — alignement visuel de l'écran Pipelines

## Ce que le lot change
Alignement visuel de l'écran Pipelines (`ui/main_window/pipelines_view.py`, classe
`PipelinesView`) sur sa maquette déjà validée (A1-A14 de `docs/refonte/ecrans/Pipelines.md`) :
en-tête via `make_page_header` (surtitre « N PIPELINES · M ACTIFS », bouton « + Nouveau pipeline »
avec « Ctrl N » affiché), colonne PIPELINE avec description sous le nom, colonne ÉTAT enrichie
d'une ligne de détail par état (échec/réussi/en cours/manqué/inactif), colonne FORME · 8 DERNIERS
avec pastilles d'historique (`RunHistoryDots`), colonne PLANIFICATION avec la relation de
déclenchement visible (plus seulement en infobulle), colonne PROCHAINE au format relatif
(« demain HH:MM »), premier bouton de ligne qui change selon l'état (reprendre/interrompre/lancer
— P8), menu « ⋯ » réordonné et complété (« Exécuter depuis le début », sous-titre de
désactivation), pied de liste (légende + « actualisé il y a N s »), validation à blanc déplacée
dans un panneau latéral partagé (`SidePanel`), bandeau à 4 repères dans la fenêtre d'import,
nouvelle fenêtre de suppression modale avec dépendants et bouton danger, état vide en trois
cartes. **Aucun changement de base** (Lot B de la fiche — date de désactivation, déclenchements
dans l'export, pipeline sans planification propre — reste hors périmètre, comme pour tout lot A).

Comme pour Aujourd'hui, aucune frame de cette maquette ne porte de pastille « proposé » (question
ouverte 1) : le partage Lot A / Lot C repose sur les tableaux explicites de la fiche. Les autres
questions ouvertes de la fiche sont déjà résolues par `DECISIONS.md` (P4, P8, P10, T1) ou par la
fiche elle-même (questions 4, 5, 6, 8) — seule la question 10 (titre de la section de collision
d'import) a nécessité une vraie décision utilisateur (`AskUserQuestion`), tranchée sur
**« CE PIPELINE EXISTE DÉJÀ »** (décrit ce que le code détecte réellement — collision par UUID,
jamais par nom).

## Fichiers touchés
| Fichier | Nature du changement |
|---|---|
| `ui/main_window/pipelines_view.py` | l'essentiel du lot (A1-A10, A14) |
| `ui/main_window/widgets.py` | `_make_button_with_hint` (nouveau), `_action_btn` étendu (`object_name="accent_action"`), `GLOBAL_STYLE` |
| `ui/styles.py` | `border_active`, `bg_row_selected` (T2) |
| `ui/components/side_panel.py` | `set_close_guard()` optionnel, rétrocompatible |
| `ui/dialogs/pipeline_import_dialogs.py` | bandeau 4 repères, titre de collision (A11) |
| `ui/dialogs/pipeline_export_dialog.py` | texte d'aide vérifié (A12) |
| `ui/dialogs/pipeline_delete_dialog.py` (nouveau) | remplace le `QMessageBox` inline de `_on_delete_pipeline` (A13) |
| `database/db_manager.py` | `count_runs(pipeline_id)` (nouvelle fonction de lecture, A13) |
| `docs/refonte/FONDATIONS.md` | nouvelles clés couleur, catalogue du bouton avec raccourci |
| `scripts/capture_views.py` | nouveaux états Pipelines/-menu/-validation/-suppression/-vide |
| `tests/test_pipelines_view_*.py` | revérifiés en premier, étendus/mis à jour (T1) |
| `tests/test_export_dialog.py` | étendu (bandeau 4 repères, titre de collision) |
| `tests/test_pipeline_delete_dialog.py` (nouveau) | |
| `tests/test_side_panel.py` | extension `set_close_guard` |

`ui/dialogs/pipeline_dry_run_dialog.py` n'est pas modifié : la classe reste fonctionnelle et son
test (`test_pipeline_dry_run_dialog.py`) reste vert, mais elle devient orpheline (plus appelée par
`PipelinesView`, qui ouvre désormais le panneau latéral A10 à la place) — signalé en « Hors
périmètre repéré » de la PR plutôt que supprimée dans ce même lot.

## Base de données
- Changement de schéma : aucun.
- Une base 0.45.0 s'ouvre sans erreur : sans objet, rien ne touche `database/db_manager.py::_migrate`.
- L'ancien worker tolère le nouveau schéma : sans objet (aucun schéma touché). La seule addition
  (`count_runs`) est une fonction de lecture pure (`COUNT`), jamais appelée par le worker.

## Format d'export
Aucun changement. `CURRENT_SCHEMA_VERSION` reste à 3 (B2, qui l'aurait fait passer à 4, est hors
périmètre de ce lot A).

## Heures affichées
- Converties (`fmt_time`/`fmt_time_local`) : heure du dernier run (colonne ÉTAT, détail), erreur
  (début tronqué, même heure). `fmt_relative` (déjà existant, lot 0b) pour « actualisé il y a N s ».
- Variante sans conversion : `next_run_at` (colonne PROCHAINE, nouveau petit formateur local
  « demain HH:MM »/« JJ/MM HH:MM »), `expected_at` des pipelines manqués (déjà dans le fuseau
  réglé, comme pour Aujourd'hui).
- Sans conversion car ce sont des durées : écoulé d'un run en cours, durée d'un run terminé.

## Noms publics
`refresh()`, `open_atelier_requested(int, object, bool)`, `_empty_label` (attribut, testé par
`test_onboarding_empty_states.py`), tous les `_on_*` existants gardent exactement leur nom et
signature — vérifiés par grep avant tout renommage (aucun n'a été renommé). Nouvelle méthode
publique-par-l'usage `_on_validate_pipeline` : signature inchangée, seul son contenu change
(ouvre le panneau latéral au lieu du dialogue modal). `SidePanel.set_close_guard` est un ajout
(pas un renommage), rétrocompatible avec Aujourd'hui (seul autre consommateur actuel).

## Tests
- Concernés : `test_pipelines_view_action_menu.py`, `test_pipelines_view_background_mode.py`,
  `test_pipelines_view_detail.py`, `test_pipelines_view_duplicate.py`,
  `test_pipelines_view_new_pipeline.py`, `test_pipelines_view_pre_run_validation.py`,
  `test_pipelines_view_refresh_skips_open_menu.py`, `test_pipelines_view_resume_menu.py`,
  `test_pipelines_view_schedule_display.py`, `test_pipelines_view_starter_template.py`,
  `test_pipeline_dry_run_dialog.py`, `test_export_dialog.py`, `test_pipeline_resume.py`,
  `test_pipeline_duplication.py`, `test_onboarding_empty_states.py`, `test_side_panel.py` — tous
  revérifiés verts avant le premier changement de code.
- Mis à jour (T1, texte/ordre que la fiche change) :
  `test_pipelines_view_action_menu.py::test_overflow_menu_contains_expected_actions` (nouvel
  ordre/texte des items), `::test_overflow_menu_toggle_action_triggers_callback` (recherche de
  l'action par texte, plus par position, puisque Désactiver change de place).
- Ajoutés : un test par comportement nouveau (surtitre dynamique, bouton avec raccourci, colonne
  ÉTAT par état, `RunHistoryDots` en colonne FORME, 2e ligne PLANIFICATION, formateur PROCHAINE,
  premier bouton par état, pied de liste, panneau de validation + `set_close_guard`, bandeau
  d'import, `pipeline_delete_dialog.py`, état vide à 3 cartes), `database/db_manager.py::count_runs`.

## Dépendances et build
Aucune dépendance ajoutée. Aucune icône nouvelle hors `qtawesome` déjà utilisé
(`fa5s.history`, `fa5s.stop` — déjà dans la famille d'icônes embarquée, rien à ajouter à
`KULU.spec`).

## Risques et retour arrière
Changement de comportement réel (pas seulement visuel) sur deux points, les deux couverts par une
décision déjà écrite dans `DECISIONS.md` : le premier bouton de ligne arrête un run en cours au
lieu d'en lancer un second (P8) ; le menu « ⋯ » gagne une action permanente « Exécuter depuis le
début » pour compenser. Risque limité : `prevent_overlap`/le menu restent les filets de sécurité
existants, rien n'est supprimé. Retour arrière : revert des commits de ce lot, aucune migration à
défaire.

## Questions ouvertes
1. **Titre de collision d'import (question 10)** — tranché par l'utilisateur :
   « CE PIPELINE EXISTE DÉJÀ » plutôt que le texte de la maquette (« UN PIPELINE PORTE DÉJÀ CE
   NOM »), qui décrit une détection par nom que le code ne fait pas (détection réelle par UUID).
2. **Bandeau d'import à 4 repères sans 4 pages** — la fiche décrit visuellement 4 étapes
   (Fichier/Mot de passe/Revue/Réglages) mais le code actuel garde Revue et Réglages combinés
   dans un seul dialogue (`PipelineImportReviewDialog`, déjà le cas avant ce lot). Scinder en deux
   pages navigables serait un changement de structure qu'aucune ligne de la fiche ne demande
   explicitement (seule l'apparence est en Lot A) — le bandeau marque donc les deux dernières
   étapes « en cours » simultanément plutôt que de forcer une vraie pagination. Signalé dans la
   PR, pas une surprise de dernière minute.
3. **Sous-titres/couleur du menu « ⋯ »** — seul le sous-titre de « Désactiver » est explicitement
   demandé par A8 (rendu en texte inline sur une seule ligne, pas un `QWidgetAction` à deux
   lignes — risque jugé trop élevé vis-à-vis de l'invariant `QApplication.activePopupWidget()` qui
   protège `refresh()` contre un crash déjà documenté). Les sous-titres de « Reprendre depuis
   l'échec »/« Valider à blanc » et la coloration rouge de « Supprimer… » ne sont pas construits
   (non listés par A8 littéralement / limite native de `QMenu`).

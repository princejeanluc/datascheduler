# Note d'impact : lot A-Paramètres — alignement visuel (écran pilote)

## Ce que le lot change
Alignement visuel de l'écran Paramètres sur sa maquette déjà validée (A1-A8 de
`docs/refonte/ecrans/Parametres.md`) : rail de gauche restylé (icône/nom/sous-titre, catégorie
active en `accent`/`bg_active`), en-tête de page via `make_page_header`, lignes restylées (14px/
12.5px), pastille de prise d'effet sur chaque réglage (« immédiat »/« à la prochaine ouverture »/
« au redémarrage »), recherche enrichie (compteur par catégorie, estompage, surlignage, ligne
d'aide), point coloré sur l'état du worker, bandeau persistant en cas d'échec d'activation du
mode arrière-plan, indice « Ctrl S » au pied. **Aucun changement de base** (Lot B de la fiche :
toutes les valeurs existent déjà). Tout ce qui porte un badge « proposé » sur la maquette (C1-C8,
gated par la décision P1 « à trancher ») est explicitement hors périmètre — voir section
« Questions ouvertes ».

## Fichiers touchés
| Fichier | Nature du changement |
|---|---|
| `ui/styles.py` | +1 clé `COLORS["search_highlight"]` |
| `ui/components/info_pill.py` (nouveau) | `make_info_pill(text, variant, tooltip="")` — 3 variantes : `neutral`, `success`, `info` |
| `ui/components/banner.py` (nouveau) | `make_banner(variant, icon_name, title, text, actions=None)` — variante `danger` exercée dans ce lot |
| `ui/components/__init__.py` | réexporte les deux nouveaux composants |
| `ui/main_window/settings_view.py` | l'essentiel du lot (A1-A8) |
| `scripts/capture_views.py` | scénarios supplémentaires pour les états de Paramètres |
| `tests/test_settings_view.py` | extensions (badges, recherche, bandeau, point coloré) |
| `tests/test_info_pill.py`, `tests/test_banner.py` (nouveaux) | tests des 2 composants |

## Base de données
- Changement de schéma : aucun.
- Une base 0.45.0 s'ouvre sans erreur : sans objet, rien ne touche `database/`.
- L'ancien worker tolère le nouveau schéma : sans objet.

## Format d'export
Aucun changement.

## Heures affichées
Aucune nouvelle heure affichée par ce lot (`_refresh_worker_status` utilisait déjà `fmt_relative`
depuis le lot 0b — seule sa présentation visuelle change, pas la fonction de formatage).

## Noms publics
`select_category(key)` garde exactement son nom et son comportement (appelé par
`window.py::_on_dashboard_navigate_to_settings` et plusieurs tests). Aucun autre nom public
renommé. `_category_buttons` change de type interne (QPushButton → widget composite) mais aucun
test ni appelant externe n'y touche (vérifié par grep).

## Tests
- Concernés : les ~25 tests de `tests/test_settings_view.py` déjà en place (aucune assertion ne
  porte sur une structure que ce lot change), les tests de `tests/test_dashboard_notifications.py`
  touchant `SettingsView` (`select_category`, `cb_frequency`, `inp_time`, `cb_day`),
  `tests/test_app_settings_scheduler_wiring.py` (aucun couplage à la vue, inaffecté),
  `tests/test_execution_mode.py` (comportement `SHUTDOWN`, inchangé).
- Ajoutés : `tests/test_info_pill.py`, `tests/test_banner.py`, extensions de
  `tests/test_settings_view.py` (pastilles par ligne, descriptions sans « Redémarrage requis »,
  compteur/estompage/surlignage de recherche, visibilité du bandeau d'échec et de son bouton
  Fermer, texte du point coloré de l'état du worker).

## Dépendances et build
Aucune dépendance ajoutée. Aucune icône nouvelle hors qtawesome déjà utilisé.

## Risques et retour arrière
Risque visuel seul (recoloration du rail, nouvelles pastilles, bandeau) — aucune donnée
persistée n'est affectée, aucun comportement de sauvegarde ne change. Retour arrière : revert des
commits de ce lot, aucune migration à défaire.

## Questions ouvertes
1. **Échap** : les critères d'acceptation de la fiche listent « Échap revient à la catégorie
   active » sans le marquer (C7), alors que C7 liste explicitement « Échap la vide » comme
   raccourci clavier nouveau (gated). Interprété comme : la logique déjà existante
   (`inp_search.clear()` déclenche déjà un retour à la catégorie active) suffit à satisfaire ce
   critère — vérifiable par un test qui vide le champ par programme. Aucune vraie liaison de
   touche Échap n'est ajoutée dans ce lot (ce serait C7). Signalé ici plutôt que tranché en
   silence ; pas d'objection reçue au moment de la validation du plan.
2. **Bandeau d'échec vs pied (A7)** : la fiche dit le bandeau persistant remplace « le texte du
   pied qui disparaît après 10s », mais la maquette `Parametres-refus.html` montre les deux
   simultanément (pied toujours rouge, bandeau en plus). Résolu en gardant `_save_status_lbl`
   totalement inchangé (aucune régression possible sur les 2 tests qui l'exercent) et en ajoutant
   le bandeau comme complément, pas un remplacement — cohérent avec la maquette, et avec l'esprit
   de la fiche (un échec doit rester visible, pas disparaître après 10s) puisque c'est désormais
   le bandeau, pas le pied, qui porte cette garantie de persistance.
3. **Version affichée (A2)** : la maquette montre « CE POSTE · KULU 0.45 » (tronqué), la fiche
   cite `version.__version__` comme source. La valeur réelle et complète est utilisée (ex.
   « 0.46.7 »), pas une troncature — la maquette datait de sa conception à une version antérieure.
4. **`Parametres-validation` non capturée** : son contenu distinctif (bandeau de validation en
   ligne par champ) est C3, gated par P1. Le comportement actuel sur un champ invalide reste une
   `QMessageBox.warning` bloquante, non capturable proprement en offscreen — capture omise,
   signalé dans la PR plutôt que simulée de façon trompeuse.
5. **Fidélité au texte des maquettes (relecture a posteriori)** : une première passe avait édité
   le texte existant du code plutôt que de reprendre les maquettes mot pour mot (REGLES.md
   section 3). Corrigé après relecture directe du HTML brut de `Parametres.html`,
   `Parametres-refus.html` et `Parametres-notifications.html` — texte des lignes Ordonnanceur/
   Interface/Notifications désormais repris tel quel. `Parametres-arriere-plan`,
   `Parametres-enregistre` et `Parametres-recherche` n'ont pas été relues en HTML brut (confiance
   dans le résumé déjà produit, revérifié cohérent avec les rendus réels) ; `Parametres-validation`
   non plus (hors périmètre, voir point 4).
6. **Interrupteurs** : la section « composants construits dès maintenant » ci-dessus ne
   mentionnait pas l'Interrupteur (FONDATIONS.md section 3, marqué « non » à l'origine). Une
   relecture des maquettes a montré qu'il est bien utilisé sur cet écran (3 réglages booléens,
   `role="switch"` sur la maquette, sans badge « proposé ») — construit dans ce lot
   (`ui/components/switch.py`), contrairement à la lecture initiale qui l'avait classé « sans
   consommateur, différé ».
7. **Artefact visuel résiduel** : un très léger changement de teinte est visible au zoom sur le
   bord droit de la ligne de catégorie active (capture au-delà de la résolution native). Investigué
   en profondeur (geométrie de widgets masqués, `border-radius`, règles `:hover`, dépassement de
   largeur du contenu, cache de style Qt, effets graphiques, tooltips — tous exclus un par un,
   chacun confirmé non responsable par un test isolé) sans en trouver la cause exacte. Non bloquant
   (REGLES.md : pixel-exact non exigé), signalé pour trace plutôt que masqué.

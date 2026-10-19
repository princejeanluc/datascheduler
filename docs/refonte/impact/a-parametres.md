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
7. **Artefact visuel résiduel (corrigé après relecture utilisateur)** : la première version de la
   PR laissait un encart sombre visible derrière le texte de la ligne de catégorie active
   (icône, nom, sous-titre) — signalé par l'utilisateur avec une capture, en plus d'un bouton
   « Enregistrer » sans son fond accent. Cause racine identifiée et reproduite isolément (script
   jetable, pixel-sampling) : la règle globale `QWidget { background-color: bg_main }`
   (`widgets.py::GLOBAL_STYLE`) peint un rectangle opaque derrière CHAQUE `QLabel` qui ne déclare
   pas son propre `background: transparent` — invisible tant que le label est posé sur `bg_main`
   ou une teinte proche (`bg_panel`), flagrant dès qu'il est posé sur une teinte contrastée
   (`bg_active`, le rail actif). Deuxième mécanisme trouvé par la même méthode : une règle QSS
   posée via `setStyleSheet()` SANS sélecteur sur un conteneur (`footer_wrap`, `title_wrap`) se
   propage à ses descendants pour les propriétés qu'ils ne fixent pas eux-mêmes — `footer_wrap`
   écrasait ainsi le fond accent du bouton Enregistrer (règle globale `QPushButton { background-
   color: accent }`, de spécificité pourtant plus précise mais d'origine plus basse). Corrigé en
   ajoutant `background: transparent` à chaque `QLabel` du rail et du panneau, et en scopant
   `footer_wrap`/`title_wrap` à un sélecteur d'ID (même traitement que `settings_panel`/
   `category_row` au lot précédent). Troisième bug trouvé par la même relecture : l'indice
   « Échap » de la ligne d'aide de recherche (A5) restait invisible malgré un `<span
   style="background-color:...">` apparemment correct — `FONT_MONO_STACK` contient des guillemets
   doubles intégrés, qui terminaient prématurément l'attribut `style="..."` lui-même en
   guillemets doubles ; corrigé en guillemets simples pour cet attribut HTML. L'« artefact visuel
   résiduel » documenté précédemment comme non résolu (bord droit de la ligne active) était la
   même cause racine que le premier bug — confirmé disparu une fois la correction appliquée,
   plutôt qu'une limite de rendu Qt distincte comme supposé initialement.
8. **Relecture complète contre les 7 maquettes (sur demande explicite)** : après le point 7,
   l'utilisateur a demandé une nouvelle relecture intégrale des `Parametres-*.png` et de la fiche,
   estimant qu'« il y a encore des éléments qui manquent ». Comparaison HTML brut (pas seulement
   visuelle) de chaque maquette contre le code, catégorie par catégorie :
   - Les éléments manquants repérés portent tous un badge « proposé » visible sur la maquette
     (encart « Ce qui se passe à l'enregistrement » C2, compteur « N réglages modifiés » + liseré/
     point par ligne + « Annuler les modifications » C1, bandeau de succès détaillé C4, « testé
     hier »/aperçu du résumé C5-C6, « Copier le détail » C8) — tous gated par la décision P1
     (`DECISIONS.md`, toujours « à trancher » : réponse par défaut « oui, comme lots C, après les
     lots A de tous les écrans »). Confirmé hors périmètre de ce lot, pas une omission.
   - Trois écarts réels, sans rapport avec P1, ont en revanche été trouvés et corrigés :
     a. Le sous-titre du rail (`_CATEGORIES[].sub`) et la description du panneau de détail
        réutilisaient le même texte, alors que la maquette distingue un texte court au rail
        (« Planification, rattrapages, exécution en arrière-plan ») d'un texte plus long en
        détail (« Comportement du planificateur : fuseau, rattrapages, exécution en
        arrière-plan. ») — confirmé par lecture du HTML brut des 5 catégories (rail) et des 2
        panneaux de détail capturés par une maquette (Ordonnanceur, Notifications). `_CATEGORIES`
        gagne un champ `desc` distinct de `sub` ; Journalisation/Interface/Ressources n'ont pas de
        panneau de détail capturé par une maquette, leur `desc` garde le texte déjà en place,
        faute de référence à reprendre (REGLES.md section 1, le code actuel fait foi à défaut de
        maquette).
     b. La pastille « au redémarrage » perdait sa petite icône de rechargement (SVG sur la
        maquette, confirmée absente des deux autres variantes) — `make_info_pill` gagne un
        paramètre `icon` optionnel (un caractère préfixé au texte, pas un widget composite, pour
        ne pas toucher au calcul de sizeHint déjà documenté comme fragile sur ce composant).
     c. Le texte par défaut du pied « Aucune modification » (Parametres.html, sans badge
        « proposé ») n'était jamais affiché (le label restait vide hors confirmation d'enregistre-
        ment) ; les messages de succès/échec n'avaient pas l'icône de la maquette (point plein
        rouge devant le texte d'échec, coche verte devant « Enregistré ») et utilisaient 12px au
        lieu de 12,5px. Le texte de succès contenait aussi une clause inventée (« certains
        réglages ne prennent effet qu'au prochain redémarrage ») qui empiète sur le territoire du
        bandeau détaillé de C4 (gated) — simplifié à « ✓ Enregistré », conforme à
        Parametres-enregistre.html.
   - Effet de bord trouvé pendant cette relecture, sans rapport avec la demande initiale : chaque
     capture officielle montrait à tort le champ de recherche avec sa bordure de focus (accent),
     y compris sur les états qui ne simulent aucune saisie — `scripts/capture_views.py` appelle
     `view.show()` sur une fenêtre top-level sans parent, qui donne par défaut le focus clavier au
     premier widget focusable (le champ de recherche) ; ça ne reproduit pas l'app réelle, où la
     vue est intégrée à une fenêtre déjà active. Corrigé en vidant ce focus après `show()`, sauf
     pour l'état "recherche" qui doit le garder (Parametres-recherche.html).
   - Les 7 maquettes ont aussi servi à vérifier, sans rien changer, que des écarts déjà tranchés
     dans ce document restaient corrects : absence de pastilles « immédiat » sur certaines lignes
     de la maquette (la fiche prime, déjà couvert par ce point avant ce lot), absence du chip
     « Ctrl F » dans la recherche (C7, gated — seul A8/« Ctrl S » au pied est explicitement listé
     hors C7 par la fiche), icônes de catégorie du rail visuellement différentes des SVG de la
     maquette (aucune des deux sources de priorité — fiche, REGLES.md section 3 — n'exige une
     correspondance pixel près des icônes, contrairement aux couleurs/tailles/espacements/textes).

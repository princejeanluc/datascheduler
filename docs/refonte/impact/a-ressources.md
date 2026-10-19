# Note d'impact : lot A-Ressources — alignement visuel de l'écran Ressources

## Ce que le lot change
Alignement visuel de l'écran Ressources sur sa maquette déjà validée (A1-A9 de
`docs/refonte/ecrans/Ressources.md`) : surtitre dynamique sur l'intervalle d'échantillonnage,
graduations et grille sur les 3 graphiques, axe du temps commun avec heure survolée, conversion
au fuseau réglé de cet axe, titre de graphique qui montre la valeur à l'instant survolé (sinon la
dernière, « maintenant »), ligne pointillée du plafond d'exécutions simultanées sur le graphique
« Pipelines en cours », heure du pic sur la carte Pic CPU, ligne de résumé (pipelines actifs/CPU/
mémoire) au survol, état vide dédié. **Aucun changement de base** (Lot B de la fiche —
agrégation 7j, échelle CPU, comptage « en cours » en arrière-plan, mémorisation d'un échec de
mesure — reste hors périmètre de ce lot A, comme `LOTS.md` le prescrit pour tous les lots A).

Plusieurs éléments listés ci-dessus portent un badge « proposé » sur la maquette (ligne du
plafond, titre « à l'instant survolé », ligne de résumé au survol) : la fiche les liste
explicitement dans son tableau Lot A (« À faire »), donc REGLES.md section 2 les autorise malgré
la pastille — même mécanisme déjà rencontré et déjà documenté sur le lot Paramètres (pastilles
« immédiat », indice « Ctrl S »).

## Fichiers touchés
| Fichier | Nature du changement |
|---|---|
| `ui/main_window/resources_view.py` | l'essentiel du lot (A1-A9), nouvelle classe `_TimeAxis`, nouvelle fonction `_interval_label` |
| `ui/main_window/widgets.py` | `_make_empty_label` étendu (icône + titre optionnels, rétrocompatible) |
| `tests/test_resources_view.py` | extensions (axe, plafond, titre survolé, pic CPU, résumé, état vide) |
| `scripts/capture_views.py` | scénarios supplémentaires pour les états capturables de Ressources |

## Base de données
- Changement de schéma : aucun.
- Une base 0.45.0 s'ouvre sans erreur : sans objet, rien ne touche `database/`.
- L'ancien worker tolère le nouveau schéma : sans objet.

## Format d'export
Aucun changement.

## Heures affichées
Toutes passent déjà ou passeront par `ui/time_display.py` (lot 0b) : `_correlate_time_lbl` et
`_pipeline_chip` l'utilisent déjà (`fmt_datetime`/`fmt_time`, conversion UTC → fuseau réglé) ;
le nouvel axe du temps (A3) et l'heure du pic CPU (A7) utiliseront les mêmes fonctions sur les
timestamps UTC naïfs de `database.models.ResourceSample.timestamp` — jamais un `.strftime()`
direct sur un instant non converti.

## Noms publics
`_TimeSeriesChart`, `ResourcesView` et leurs méthodes déjà publiques/testées
(`_on_chart_hover`, `_on_range_changed`, `_running_count_at`, etc.) gardent exactement leur nom
et comportement — aucun appelant externe ni test ne les renomme. `_make_empty_label` garde sa
signature actuelle en tête (`text`, `button=None`), les 2 nouveaux paramètres (`icon`, `title`)
sont ajoutés en fin de signature avec des défauts qui reproduisent le rendu actuel — vérifié par
grep des 7 appels existants (`connections_view.py` ×6, `dashboard_view.py`, `history_view.py`
×2, `pipelines_view.py`).

## Tests
- Concernés : les ~13 tests de `tests/test_resources_view.py` déjà en place (à revérifier verts
  en premier, avant tout changement de code, pour confirmer qu'aucun ne fige un texte que ce lot
  modifie — notamment le texte des labels « latest » des graphiques, modifié par A5).
- Ajoutés : axe du temps (présence des libellés, alignement x), ligne de plafond (position,
  libellé), titre de graphique selon survol/repos, sous-titre de la carte Pic CPU, contenu étendu
  de la ligne de résumé au survol, bascule stats-visibles/graphiques-vs-état-vide,
  rétrocompatibilité de `_make_empty_label` pour un appelant existant sans `title`/`icon`.

## Dépendances et build
Aucune dépendance ajoutée — réutilise `qtawesome` (déjà une dépendance du projet) pour l'icône de
l'état vide, et `ui/fonts.py`/`ui/icons.py` déjà embarqués (aucun fichier de ressource séparé,
rien à ajouter à `KULU.spec`).

## Risques et retour arrière
Risque visuel seul (axe, grille, titres, carte Pic CPU, état vide) — aucune donnée persistée
n'est affectée, aucune fonction de lecture/écriture en base ne change. Retour arrière : revert
des commits de ce lot, aucune migration à défaire.

## Questions ouvertes
1. **Intervalle des graduations de l'axe du temps en 1h/6h** : la fiche ne précise l'intervalle
   que pour 24h (toutes les 3h) et 7j (un libellé par jour) ; aucune maquette ne couvre 1h/6h.
   Choix par jugement (viser ~6-8 libellés répartis sur la plage), signalé ici plutôt que
   tranché en silence (REGLES.md section 1).
2. **Format de l'heure du pic CPU en 7j** : la maquette `Ressources-7j.html` montre un format
   arrondi à l'heure (« dim. 18 vers 07:00 »), qui anticipe l'agrégation horaire du Lot B (B1,
   hors périmètre ici). Les échantillons restant bruts dans ce lot, la carte Pic CPU garde un
   format exact (« DD/MM HH:MM » ou « aujourd'hui HH:MM »), cohérent avec les autres plages,
   plutôt que de simuler un arrondi que l'agrégation ne produit pas encore.
3. **Performance de la vue 7j (B1)** : le critère d'acceptation « en 7j avec 10 080 échantillons,
   l'écran s'affiche en moins d'une seconde » dépend de l'agrégation en lecture du Lot B,
   explicitement hors périmètre de ce lot A. Non garanti ici, signalé dans la PR plutôt que
   simulé.
4. **« Rafraîchissement figé »** (`manquements.md`, minuterie qui garde l'intervalle lu au
   démarrage) : présent dans `manquements.md` mais absent des tableaux Lot A/B/C de la fiche
   Ressources elle-même — par la règle T7 (`DECISIONS.md`), non traité ici, signalé dans la PR
   section « Hors périmètre repéré ».
5. **Fond des cartes (corrigé après relecture utilisateur)** : la première version de la PR
   laissait les 4 cartes de stats et les 2 encarts (graphiques, corrélation) avec le style par
   défaut de `StatCard`/`QFrame#card` (`widgets.py::GLOBAL_STYLE`) — fond `bg_card`, rayon 6px,
   liseré d'accent bleu — au lieu du fond `bg_panel`, rayon 10px, bordure unie sans accent que
   montre `Ressources.html` sur ces 6 blocs. Signalé par une capture de l'app réelle. Corrigé en
   surchargeant le style (scopé `QFrame#card`, pas une règle nue) spécifiquement sur ces
   instances, sans toucher au `QFrame#card` global ni à `StatCard` (dont le rendu par défaut
   reste inchangé pour tous les autres écrans qui l'utilisent). Même relecture : l'en-tête du
   panneau de corrélation (« Pipelines actifs à l'instant survolé » + sa description) était
   empilé sur deux lignes alors que la maquette les aligne sur une seule ligne
   (`align-items: baseline`) — corrigé, texte de la description aussi repris plus fidèlement
   (« Survolez un point des graphiques pour voir quels pipelines tournaient à ce moment. »,
   sans les ajouts « ci-dessus »/« précisément » absents de la maquette).

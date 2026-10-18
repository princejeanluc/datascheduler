# Ressources

Vue : `ui/main_window/resources_view.py`. Maquettes : `maquettes/png/Ressources*.png`.

## Intention
L'écran aide à relier une pointe de CPU ou de mémoire aux pipelines qui tournaient à ce moment. Il ne mesure pas chaque pipeline : ils partagent le même processus. La maquette d'origine a été validée (3 graphiques empilés sur un même axe du temps, jamais un graphique à deux échelles, curseur commun, pastilles des pipelines actifs) et reste la base. La refonte ajoute de quoi lire les graphiques (axes, valeurs) et de quoi enquêter sur une plage.

## États (frames)
| Frame | Ce qu'elle montre | Déclencheur dans l'application |
|---|---|---|
| Ressources | 24 h, rien de survolé | ouverture, plage 24h |
| Ressources-survol | Curseur à 07:05, valeurs et pipelines actifs à cet instant | survol d'un graphique |
| Ressources-plage | Plage 06:50 → 07:30 choisie, runs alignés | glisser sur un graphique (proposé) |
| Ressources-7j | 7 jours, une valeur par heure avec enveloppe min–max, échecs marqués | plage 7j |
| Ressources-vide | Aucune mesure, et alerte si la mesure échoue | base sans échantillon |

## À garder tel quel
- Les 3 instances de `_TimeSeriesChart`, une série chacune, empilées dans cet ordre : CPU, mémoire, pipelines en cours. Le commentaire en tête du fichier explique pourquoi : ne jamais fusionner en un graphique à deux axes.
- Les couleurs des séries `_COLOR_CPU`, `_COLOR_RAM`, `_COLOR_COUNT`, validées pour la lisibilité daltonienne.
- Le curseur synchronisé (`hovered`, `hover_left`, `_on_chart_hover`).
- Le panneau de corrélation construit une seule fois : `_correlate_time_lbl` et `_correlate_empty` restent dans le layout, seules les pastilles sont recréées. Le commentaire décrit un crash réel (« Internal C++ object already deleted ») : ne pas revenir à un layout vidé puis reconstruit.
- Le ressort final après les pastilles (`addStretch`), qui empêche une pastille de s'étirer.
- Les plages 1h, 6h, 24h, 7j, et 24h par défaut.
- Les 4 cartes : En cours (« n / plafond »), Pic CPU, Mémoire actuelle, Échantillons.
- Le rafraîchissement par minuterie à l'intervalle d'échantillonnage.
- Une seule requête par fenêtre pour les runs (`get_runs_overlapping_window`), puis filtrage en mémoire.

## Lot A : alignement visuel, sans changer la base
| # | Changement | Frame | Source des données (code) |
|---|---|---|---|
| A1 | En-tête : surtitre « PROCESSUS KULU · UN POINT PAR <intervalle> », titre, sous-titre actuel raccourci (texte de la maquette) | Ressources | `AppSettings.resource_sample_interval_s` |
| A2 | Graduations à gauche (CPU 50 et 100, mémoire en Mo, pipelines) et lignes de grille `bg_hover` | Ressources | `_TimeSeriesChart.paintEvent` |
| A3 | Axe du temps commun sous le dernier graphique, toutes les 3 h en 24h, un libellé par jour en 7j ; étiquette blanche de l'heure survolée sur l'axe | Ressources, -survol | timestamps des échantillons |
| A4 | Heures en fuseau réglé : axe, heure survolée, « depuis HH:MM » des pastilles | toutes | `FONDATIONS.md` section 4 (aujourd'hui affichées en UTC) |
| A5 | Titre de chaque graphique : valeur à l'instant survolé (sinon dernière valeur, suivie de « maintenant ») | -survol | `_on_chart_hover` |
| A6 | Ligne pointillée du plafond d'exécutions simultanées sur « Pipelines en cours », avec « plafond N » | Ressources | `AppSettings.max_concurrent_runs` |
| A7 | Carte Pic CPU : heure du pic sous la valeur | Ressources | `cpu_values`, index du maximum |
| A8 | Ligne de résumé au survol : date et heure, nombre de pipelines actifs, CPU, mémoire | -survol | `_update_correlate_panel` |
| A9 | État vide : titre « Pas encore de mesure », texte sur l'intervalle, renvoi vers Paramètres | -vide | `_samples` vide |

## Lot B : changements de données

> Le schéma de référence est dans `../DONNEES.md`. Si un nom ou une colonne diffère ici, c'est `DONNEES.md` qui fait foi.

| # | Besoin | Proposition | Impact |
|---|---|---|---|
| B1 | 7 jours : jusqu'à 10 080 points chargés et dessinés | agréger à la lecture (moyenne, min, max par heure) dans une nouvelle fonction `get_resource_samples_bucketed(since, bucket_s)` ; pas de nouvelle table | aucun schéma touché, worker et export inchangés |
| B2 | CPU au-delà de 100 % sur plusieurs cœurs | diviser par `psutil.cpu_count()` à la mesure, ou à l'affichage seulement. Recommandé : à l'affichage, pour ne pas changer le sens des mesures déjà enregistrées | aucun schéma touché |
| B3 | « En cours » ne voit pas les runs du worker en mode arrière-plan | compter les runs sans `finished_at` en base plutôt que `core.pipeline._active_runs` | vérifier qu'un run interrompu brutalement (sans `finished_at`) ne compte pas éternellement : borner par l'âge |
| B4 | Mesure en échec invisible | mémoriser le dernier échec (heure, message) : en mémoire du processus pour le mode application ; pour le worker, une colonne nullable ou une petite table d'état | si colonne ajoutée : nullable, ignorée par l'ancien worker |

## Lot C : fonctions nouvelles (« proposé »)
| # | Fonction | Frame | Dépend de |
|---|---|---|---|
| C1 | Pastilles enrichies : statut (en cours, réussi, échec) et durée du run ; clic qui ouvre le run dans l'Historique | -survol | `PipelineRun.status`, navigation vers Historique |
| C2 | Glisser sur un graphique pour choisir une plage : zone bleue sur les 3 graphiques, résumé (durée, nombre de pipelines, pics), runs alignés sur le temps de la plage, boutons Zoomer, Ouvrir dans l'Historique, Effacer | -plage | B1 pour le zoom, Historique filtrable par période |
| C3 | Vue 7 jours : ligne de moyenne, enveloppe min–max, bandeau d'explication, marques des runs en échec sur « Pipelines en cours » | -7j | B1 |
| C4 | Alerte « Aucune mesure depuis N min » avec le dernier message d'erreur, « Ouvrir le fichier de logs », « Copier le détail » | -vide | B4 |

## Hors périmètre
- Une mesure par pipeline (impossible, voir l'intention).
- D'autres métriques (disque, réseau).
- Le thème clair.

## Critères d'acceptation
- [ ] Les 3 graphiques restent séparés, avec une seule échelle chacun, et le curseur reste synchronisé.
- [ ] Survoler puis quitter un graphique 200 fois de suite ne provoque aucune erreur (protection contre le crash décrit dans le code).
- [ ] Avec `Europe/Paris` en octobre, un échantillon enregistré à 05:05 UTC s'affiche 07:05 sur l'axe et dans le panneau.
- [ ] Le titre de chaque graphique montre la valeur de l'instant survolé, puis la dernière valeur quand le curseur sort.
- [ ] La ligne du plafond suit `max_concurrent_runs` après un enregistrement dans Paramètres.
- [ ] En 7j avec 10 080 échantillons, l'écran s'affiche en moins d'une seconde (B1).
- [ ] Sans aucun échantillon, l'état vide s'affiche à la place des graphiques.
- [ ] Les tests existants qui importent `resources_view` restent verts.
- [ ] Captures des 5 états jointes à la PR (C2 et C3 seulement si ces lots sont faits).

## Questions ouvertes
- B2 : faut-il afficher le CPU sur 100 % de la machine ou sur 100 % d'un cœur ? La maquette suppose 0 à 100 % de la machine.
- En mode arrière-plan, l'interface et le worker écrivent-ils tous deux des échantillons ? Si oui, les deux séries se mélangent dans la même table. À vérifier dans `core/scheduler.py` (qui démarre `refresh_resource_sampler`) avant B3.

# <Écran>

Vue : `ui/main_window/<fichier>.py` (et dialogues liés). Maquettes : `maquettes/png/<Écran>*.png`.

## Intention
Deux ou trois phrases : à quoi sert l'écran pour un profil data, et ce que la refonte change pour lui.

## États (frames)
| Frame | Ce qu'elle montre | Déclencheur dans l'application |
|---|---|---|

## À garder tel quel
Comportements et éléments du code actuel qui doivent rester, même s'ils ne se voient pas sur les maquettes.

## Lot A : alignement visuel, sans changer la base
| # | Changement | Frame | Source des données (code) |
|---|---|---|---|

## Lot B : changements de données
Ce qui demande une colonne, une table ou une nouvelle fonction dans `database/` ou `core/`. Pour chacun : le besoin, la proposition de schéma (ajout seulement) et l'impact sur le worker et l'export.

## Lot C : fonctions nouvelles (« proposé »)
| # | Fonction | Frame | Dépend de |
|---|---|---|---|

## Hors périmètre
Ce qui apparaît sur les maquettes mais ne doit pas être fait dans ces lots.

## Critères d'acceptation
Liste à cocher, vérifiable par une capture ou un test. Un critère par état et par comportement.

## Questions ouvertes
Contradictions entre la maquette et le code, à faire trancher avant de coder.

# Note d'impact : lot A-Atelier-grammaire — rendu des nœuds et liaisons du canevas

## Correctifs (relevés en comparant une capture à la maquette, après la 1ʳᵉ version du lot)
- Losange : coins arrondis (`node_item.py::_rounded_diamond_path`, nouveau — quatre courbes
  quadratiques remplacent les quatre `lineTo` à angle vif).
- Symbole central du losange agrandi (9/8pt → 15/12pt) et mieux centré.
- Points de port (entrée, sortie normale, erreur) en ANNEAU — bordure colorée, intérieur sombre
  (`bg_main`) — au lieu d'un disque plein (`StepNodeItem._draw_port_ring`, nouveau).
- Contenu déplié : une valeur de fait trop longue pour sa largeur allouée était coupée net en
  plein milieu d'un caractère, sans indication qu'il en manque la fin. Tronquée avec « … »
  (`QFontMetrics.elidedText`), même principe déjà utilisé ailleurs dans l'appli
  (`settings_view.py::_make_category_row`).
- **A4 implémenté** (absent de la 1ʳᵉ version de ce lot, alors qu'explicitement dans le tableau
  Lot A de la fiche) : bordure `accent` sur le nœud sélectionné (remplace la bordure de couleur
  de famille, simplement épaissie, d'avant ce correctif) ; tout AUTRE nœud du canevas atténué
  (opacité 0.4) tant qu'une sélection existe quelque part ; les liaisons touchant le nœud
  sélectionné passent en `accent`, sauf le propre chemin d'erreur du nœud sélectionné qui passe
  en `warning` (la fiche distingue explicitement les deux). Nouvelles fonctions pures
  `node_item.py::_node_opacity` et `edge_item.py::edge_selection_color_key`.

## Liaisons et états — ce qui est couvert, ce qui ne l'est pas (question de l'utilisateur)
La maquette Grammaire liste 5 styles de liaison (« Donnée transmise », « Branche prise au dernier
passage », « Branche non prise », « Chemin d'erreur, en attente », « Chemin d'erreur déclenché »)
et 4 états de nœud (« Sélectionnée », « En cours · N% », « En échec », « Non exécutée »).
- **Couverts par ce lot (A5, A4)** : « Donnée transmise » (port normal, neutre `text_dim`) ;
  « Chemin d'erreur, en attente » (port `error`, pointillé `warning` — c'est l'état par défaut
  tant qu'aucune exécution n'a eu lieu) ; « Sélectionnée » (bordure `accent`, nœud).
- **Hors de portée d'un lot A pur (besoin de B1, `pipeline_run_steps`)** : « Branche prise au
  dernier passage » / « Branche non prise » et « Chemin d'erreur déclenché » (vs « en attente »)
  décrivent le résultat du DERNIER run réel — quelle branche a été empruntée, si le chemin
  d'erreur a effectivement été pris. Rien de tout cela n'est en base aujourd'hui pour une liaison
  individuelle (seul `PipelineRun.active_ports` existe, et seulement en cas d'échec reprenable).
  De même « Non exécutée » (nœud) et le pourcentage de « En cours · N% » (déjà noté comme
  question ouverte n°7 de la fiche) dépendent de B1.
- **Mécanisme déjà existant, volontairement non touché** : `EdgeItem.set_failed()`/
  `StepNodeItem.set_failed()` surlignent en ROUGE (`danger`) le nœud en échec et ses liaisons
  entrantes pendant le traçage lumineux d'un run réel ou un lien "Voir dans le graphe" — un
  mécanisme séparé, antérieur à ce lot, listé dans « À garder tel quel » de la fiche. Il n'est pas
  le même concept que « chemin d'erreur déclenché » de la légende (qui serait ambre, pas rouge) ;
  les deux coexistent sans conflit (priorité : échec réel rouge > sélection accent > base).

## Ce que le lot change
Première tranche du Lot A de l'écran Atelier (`docs/refonte/ecrans/Atelier.md`), limitée à la
frame « Grammaire » : A1, A2, A3 et A5, qui ne touchent que `ui/graph_editor/node_item.py`,
`ui/graph_editor/edge_item.py` et `ui/graph_editor/node_facts.py`. Aucune donnée nouvelle, aucun
changement de base — uniquement comment un nœud/une liaison déjà existants sont peints.

- **A1.** Carte d'étape (nœud rectangulaire) restylée en 3 lignes : surtitre Mono en majuscules
  « FAMILLE · MOTEUR » (couleur de famille), titre (libellé utilisateur ou de type), sous-titre
  Mono (premier fait de `compute_node_facts`). Le badge d'icône rond devient un simple point de
  couleur de famille. Le « moteur » n'existe pas comme champ unique : déduit du type
  (`node_facts.py::engine_label`, nouveau) — `db_type` déjà dans la config pour DB_EXTRACT/
  DB_EXECUTE/DB_LOAD, protocole résolu via `profile_names["ftp_protocol"]` (nouvelle clé, ajoutée
  par `PipelineGraphEditorWidget._build_profile_names`) pour FTP_UPLOAD/FTP_DOWNLOAD, mot fixe
  pour les autres types qui en ont un (SPARK, SQOOP, PYTHON, SMTP, HTTP, ZIP), `None` sinon
  (LOCAL_COPY, routage, variables — pas de moteur à nommer).
- **A2.** Contenu déplié : couleurs des puces « ↳ lit var:x » et « ↳ écrit y » passées de
  text_dim/accent à signal_pale/accent_pale. Structure (faits label/valeur) inchangée.
- **A3.** Nœuds de routage (losange) : symbole au centre remplace l'icône qtawesome — « ? »
  (CONDITION), « + » (GATEWAY_PARALLEL), « ET »/« OU » (GATEWAY_JOIN, selon `join_mode` via
  `core.steps.get_join_mode`, nouvelle fonction pure `node_item.py::_routing_symbol`). Le nom
  (libellé utilisateur ou de type) passe AU-DESSUS du losange au lieu d'en dessous — une seule
  ligne (le libellé de type en 2ᵉ ligne, affiché avant ce lot, est retiré : redondant avec le
  symbole + le nom).
- **A5.** Couleur/style d'une liaison dépendent désormais de son port de départ
  (`edge_item.py::edge_base_visual`, nouvelle fonction pure) : `error` en pointillé `warning`,
  `true`/`false` reprennent la couleur de leur point de port (`success`/`danger`), un port normal
  garde le neutre `text_dim` d'avant ce lot. L'état (sélection/exécution/échec) reste toujours
  prioritaire. Les mots « vrai »/« faux » sont maintenant écrits le long de la liaison elle-même —
  en conséquence, l'étiquette courte « V »/« F » posée au POINT de port (redondante une fois le
  mot sur la liaison, et visuellement encombrée sur un losange qui concentre 2-3 ports proches de
  son sommet droit) est retirée ; le point d'erreur garde son « ! ».

## Écart volontaire avec la fiche (à documenter dans la PR)
La fiche A1 dit littéralement « FAMILLE » pour le surtitre ; plusieurs maquettes montrent en
réalité un mot plus court et spécifique au type (« EXTRACTION », « CHARGEMENT », « ENVOI »...),
pas le nom de famille complet (`STEP_META["family"]`, ex. « Extraction et chargement »). Faute
d'une liste fiable de ces mots courts pour les 18 types (seuls 5-6 sont visibles sur les
captures fournies), ce lot suit le texte explicite de la fiche : la FAMILLE réelle, en majuscules.
Résultat plus long que les exemples de maquette mais défendable à la lettre de la fiche
(REGLES.md section 1, la fiche fait foi sur le comportement/contenu avant la maquette) — à
corriger facilement plus tard si une liste de mots courts est validée par écran.

## Fichiers touchés
| Fichier | Nature du changement |
|---|---|
| `ui/graph_editor/node_item.py` | A1 (surtitre/titre/sous-titre/point de famille), A2 (couleurs des puces), A3 (symbole + nom au-dessus) ; `_PORT_STYLE` true/false sans étiquette |
| `ui/graph_editor/edge_item.py` | A5 (couleur/pointillé par port, mots vrai/faux) ; nouvelle fonction pure `edge_base_visual` |
| `ui/graph_editor/node_facts.py` | nouvelle fonction pure `engine_label` |
| `ui/graph_editor/graph_editor_widget.py` | `_build_profile_names` : nouvelle clé `ftp_protocol` |
| `scripts/capture_views.py` | nouvel état `grammaire` (QGraphicsScene/View direct, pas une vue de fenêtre principale) |
| `tests/test_graph_editor_dialog.py`, `tests/test_node_facts.py` | tests ajoutés ; un test existant (`_port_visual` true/false labels) mis à jour (T1) |

## Base de données
Aucun changement. Aucune colonne, aucune table.

## Format d'export
Aucun changement — ce lot ne touche que le rendu, jamais `step`/`config`/`PipelineEdge`.

## Noms publics
`StepNodeItem.WIDTH`/`HEIGHT` inchangés (64px conservé — le nouveau contenu tient dans la hauteur
existante). `_chevron_rect(width, height, routing)` garde sa signature mais ignore désormais
`routing` en interne (même coin haut-droite dans les deux cas, simplification sans effet sur ses
appelants). `StepNodeItem.boundingRect()` grandit vers le HAUT pour un nœud de routage au lieu du
bas (même hauteur totale à peu de chose près, juste l'origine qui change) — vérifié : aucun test
ne pinne une position absolue de port qui en dépendrait.

## Tests
- Concernés : `test_graph_editor_dialog.py`, `test_node_item_expand.py`, `test_node_facts.py`,
  `test_graph_alignment_guides.py`, `test_graph_minimap.py`, `test_graph_tool_rail.py`,
  `test_duplicate_node.py`, `test_pipeline_topology_dialog.py`, `test_history_view_graph_link.py`,
  `test_node_context_menu.py` — tous revérifiés verts avant et après chaque changement.
- Mis à jour (T1) : `test_port_visual_true_false_and_error_have_distinct_colors` (labels `("V",
  "F", "!")` → `("", "", "!")`, true/false n'ont plus d'étiquette au point).
- Ajoutés : `_routing_symbol` (3 tests), `edge_base_visual` (3 tests), `engine_label` (6 tests) —
  toutes fonctions pures, sans `qapp`.

## Dépendances et build
Aucune dépendance ajoutée.

## Risques et retour arrière
Risque principal : le changement de géométrie du losange (légende au-dessus au lieu d'en dessous)
aurait pu déplacer les ports — vérifié par `test_regular_step_output_ports_unaffected_by_diamond_change`
et les tests de géométrie existants, tous verts sans modification. Aucune donnée persistée
affectée. Retour arrière : revert des commits de ce lot, aucune migration à défaire.

## Suite de la fiche Atelier
Ce lot ne couvre que la frame Grammaire. Restent, dans l'ordre choisi avec l'utilisateur : B1
(table `pipeline_run_steps`, `DONNEES.md`), puis les items A6-A16 de la frame Main (en-tête,
panneau de paramètres du pipeline, recherche de nœud...) et les items C qui dépendent de B1
(Atelier-echec, Atelier-etape).

# Note d'impact — A9 + C9 : vue d'exécution en échec (Atelier-echec)

Deuxième lot C de l'Atelier, construit directement sur B1 (`pipeline_run_steps`). Couvre A9
(en-tête « Relancer tout »/« Reprendre depuis l'échec ») et C9 (canevas en lecture seule montrant
l'état réel du dernier run, panneau de diagnostic, compartiment bas Chronogramme/Journal) — à
partir des deux images de maquette envoyées (`Atelier-echec.html`, relu intégralement). **Aucune
nouvelle table, aucun changement d'export** : lecture seule de `pipeline_run_steps`/`pipeline_runs`
déjà en place.

## Lecture précise de la maquette (pas un résumé approximatif)

En comparant `Atelier-echec.html` à `Main.html` nœud par nœud et arête par arête :

- **Nœud réussi** : apparence identique à l'édition, juste la ligne de statut (déjà absente en
  édition) en vert — `✓ 41 s · 83 212 l.`, `✓ 1 min 02`, etc.
- **Nœud en échec** (Dépôt partenaire, et la jonction ET elle-même) : bordure rouge épaisse, fond
  teinté rouge, texte `✗ N tentatives refusées`, badge ambre `!`. **C'est exactement le mécanisme
  `set_failed()` déjà existant** (aujourd'hui utilisé pour UN SEUL nœud via `highlight_step_key`) —
  ce lot l'étend à TOUS les nœuds FAILED du run, pas seulement celui pointé par le lien historique.
- **Nœud non exécuté** (Prévenir l'équipe, Alerte volume nul) : bordure pointillée grise, **tout le
  texte de la carte** (pas seulement le statut) en gris atténué, `non exécutée`. État visuel neuf,
  absent du code.
- **Nœud atteint via le port d'erreur et réussi** (Signaler l'échec) : bordure ambre pleine, fond
  teinté ambre, texte normal + statut vert `✓ via le port d'erreur · 1 s`. État visuel neuf.
- **Liaison normale (port sans sémantique) empruntée avec succès** : passe de gris neutre (édition)
  à vert plein — ex. extraction→condition, parallèle→charger. État neuf, dépend du run.
- **Liaison normale non empruntée** (dépôt→jonction ET, le port de sortie normal de Dépôt
  partenaire jamais atteint puisqu'il a échoué ; jonction ET→Prévenir l'équipe) : gris pointillé —
  même apparence que l'état « en attente » déjà par défaut, donc **rien à peindre de spécial**, il
  suffit de ne pas la faire passer au vert.
- **Liaisons `true`/`false` (condition)** : **couleur inchangée par le run** — toujours vert pour
  `true`, gris pointillé pour `false`, qu'elle ait été empruntée ou non cette fois-ci. Déjà couvert
  par A5, rien à faire.
- **Port d'erreur réellement déclenché** (Dépôt partenaire→Signaler l'échec) : passe de pointillé
  ambre (« en attente », déjà la valeur par défaut A5) à **plein ambre épais** (`stroke-width:2.6`
  contre `1.6` ailleurs). C'est précisément le 5ᵉ état de la légende « Liaisons et états » de la
  Grammaire, identifié comme bloqué sur B1 lors du lot Grammaire — maintenant réalisable.
- **Bandeau résumé** bas-gauche du canevas : `5 réussies · 2 en échec · 2 non exécutées · 1 chemin
  d'erreur suivi` — agrégation simple des statuts de `pipeline_run_steps`.
- **Rail d'outils à 50 % d'opacité** : lecture seule, cohérent avec `highlight_step_key` existant
  (pas de modification du graphe en mode vue d'un run).
- **En-tête** : fil d'Ariane + badge rouge « Échec à 11:28 · Dépôt partenaire » remplacent le
  badge/texte habituel, et « Relancer tout » + « Reprendre depuis l'échec » remplacent « Valider à
  blanc » + « Exécuter » — uniquement en mode vue d'un run, jamais en édition normale.
- **Compartiment bas** : seulement 3 onglets ici (Chronogramme/Journal/Variables, pas Validation —
  Validation n'a de sens qu'en édition), statut du run affiché, pas de « Exécutions précédentes ».
  Le Chronogramme montre les tentatives de l'étape en échec comme des barres courtes séparées par
  un trait fin (le délai d'attente entre tentatives).

## Trou d'architecture trouvé en lisant le code : aucun `run_id` ne circule jusqu'à l'Atelier

`MainWindow.open_atelier(pipeline_id, highlight_step_key, is_new_pipeline)` et le signal
`HistoryView.open_atelier_requested = Signal(int, object, bool)` ne transportent qu'un
`step_key` — jamais l'identité du run consulté. Le mécanisme actuel (`_highlight_failed_step`)
n'en a pas besoin : il se contente de peindre UN nœud en rouge. Ce lot a besoin de savoir
**quel run** afficher (pour lire ses `pipeline_run_steps`, son `error_message`, son
`resumable_state_json`).

**Décision** : signal séparé et additif, `HistoryView.open_atelier_run_requested = Signal(int, int,
object)` (pipeline_id, run_id, failed_step_key), câblé à une nouvelle méthode
`MainWindow.open_atelier_run(pipeline_id, run_id, failed_step_key)` — jamais une modification de
`open_atelier`/`open_atelier_requested` existants (3 appelants différents, dont deux n'ont pas de
run à transmettre). `PipelineGraphEditorWidget` gagne un paramètre optionnel `run_id: int | None =
None`. Compatibilité : `highlight_step_key` seul (sans `run_id`) garde exactement son comportement
actuel (lien générique, pas de base migrée ou ancien worker) — l'acceptance criterion B1 « sans
lignes d'étape (ancien worker), Main et Atelier-echec s'affichent sans erreur ni place vide » est
donc satisfait par construction : si `db.get_run_steps(run_id)` revient vide, on retombe sur
l'ancien comportement à un seul nœud.

## Décisions d'implémentation sans question ouverte correspondante (jugement documenté)

1. **« CE QUI S'EST PASSÉ ENSUITE »** : jamais un texte généré avec des règles spécifiques
   « jonction ET »/etc. codées en dur — pour chaque successeur direct de l'étape en échec déjà
   présent dans `pipeline_run_steps` : succès → « a réussi » ; échec → son propre `error_message`
   réel (qui, pour une jonction ET, contient déjà *« Passerelle de jonction (ET) : au moins une
   branche entrante n'a pas abouti »*, écrit par `core/pipeline.py` — pas besoin de le
   régénérer) ; sauté → « n'a pas été exécutée ». Fidèle aux données réelles, jamais une
   invention.
2. **« TENTATIVES »** : le mot par tentative (« refusée » sur la maquette) est spécifique à
   *cette* erreur précise (« Connection refused ») — pas un pattern à reconnaître. Mot générique
   **« échouée »** pour toute tentative de `attempts_json`, horodatage réel.
3. **« PISTE »** (connexion jamais testée) : aucune fonction du code ne relie aujourd'hui un run
   en échec au profil de connexion utilisé — `last_tested_at` vit uniquement sur les profils
   (`OracleProfile`, `FtpProfile`, `SmtpProfile`, `SshProfile`...). Construite ici, **seulement
   pour les types à un seul champ de profil simple** : `FTP_UPLOAD`/`FTP_DOWNLOAD`
   (`ftp_profile_id`), `EMAIL_NOTIFY` (`smtp_profile_id`), `SPARK_SQL`/`SQOOP_EXPORT`/
   `SQOOP_IMPORT` (`edge_profile_id`, profil SSH). **Hors périmètre** : les types `DB_*`, dont la
   résolution du profil dépend de `db_type` (plusieurs tables) — section absente plutôt qu'une
   fausse piste. Affichée seulement si `last_tested_at is None` (jamais testée) — pas de
   comparaison de date (fuseau/format incertains pour un écart mineur). **Le bouton « Tester la
   connexion » n'est pas câblé dans ce lot** : son action réelle appartient à C3 (fiche : frame
   Atelier-etape, dépendances `test_connection()`/`db.record_profile_test_result` propres à ce
   lot séparé) — **non affiché du tout** plutôt qu'un bouton mort (T7 : élément visible sur la
   maquette, action hors périmètre de ce lot, donc absent de l'écran livré).
4. **« Relancer tout » vs « Reprendre depuis l'échec » sans run reprenable** : l'acceptance
   criterion de la fiche est explicite (A9) — sans run reprenable, aucun des deux boutons.
   Repli : les boutons habituels « Valider à blanc »/« Exécuter » (le pipeline reste utilisable
   normalement même en consultant un run passé).
5. **Formats de durée** (« 41 s », « 1 min 02 ») : `_format_duration_short`, déjà dupliquée dans
   `pipelines_view.py` et `history_view.py` avec le commentaire *« même raison »* — même
   duplication ici, pas un nouvel import partagé (convention déjà établie par le code, pas une
   décision nouvelle).

## Fichiers touchés (nouveaux)

| Fichier | Contenu |
|---|---|
| `ui/graph_editor/run_status.py` | Fonctions pures : texte de statut par nœud, état d'une arête (taken/not_taken/error_waiting/error_triggered), narration « ce qui s'est passé ensuite », bandeau résumé. Aucune dépendance Qt — testable sans `QApplication`. |
| `ui/graph_editor/run_failure_panel.py` | `RunFailurePanel` : aperçu échec, tentatives, suite, piste (bornée), carte de reprise. |
| `ui/graph_editor/run_timeline_panel.py` | `RunTimelinePanel` : onglets Chronogramme/Journal, barres + marqueurs de tentatives. |

## Fichiers touchés (modifiés)

| Fichier | Nature |
|---|---|
| `database/db_manager.py` | `get_run_steps(run_id) -> list[PipelineRunStep]` (lecture, nouveau — aucune fonction existante ne lisait cette table). |
| `ui/graph_editor/node_item.py` | Nouvel état peint « non exécutée » (bordure pointillée, texte atténué) et « déclenché via port d'erreur » (bordure/fond ambre) ; `set_failed()` réutilisé tel quel pour FAILED. Ligne de statut (`✓ 41 s · 83 212 l.` etc.) sous le titre. |
| `ui/graph_editor/edge_item.py` | États « empruntée avec succès » (vert) et « port d'erreur déclenché » (plein épais) — `true`/`false` inchangés (A5 suffit déjà). |
| `ui/graph_editor/graph_editor_widget.py` | Paramètre `run_id` ; au chargement, lit `db.get_run_steps`/`db.get_run`, applique les états, construit le panneau de diagnostic et le panneau chronogramme/journal (même patron d'exposition que `preview_panel`, C7). |
| `ui/main_window/atelier_pipelines_view.py` | Mode vue d'un run : en-tête basculé (badge + Relancer tout/Reprendre), panneau de droite basculé vers le diagnostic, compartiment bas ajouté sous le canevas, lien « revenir à l'édition ». |
| `ui/main_window/history_view.py` | Nouveau signal `open_atelier_run_requested`, câblé aux deux endroits qui construisaient déjà `failed_step_key` (panneau de run, lien direct). |
| `ui/main_window/window.py` | `open_atelier_run(pipeline_id, run_id, failed_step_key)`, additif. |
| `scripts/capture_views.py` | Nouvel état `echec`. |

## Base de données / export / build

Aucun changement de schéma, aucune nouvelle dépendance. `get_run_steps` est une lecture pure.

## Tests

Nouveaux : `tests/test_run_status.py` (fonctions pures, le cœur testable sans Qt),
`tests/test_run_failure_panel.py`, `tests/test_run_timeline_panel.py`, extension de
`tests/test_graph_editor_dialog.py`/`test_atelier_pipelines_view.py`/`test_history_view*.py` pour
le nouveau signal et le mode vue d'un run. Revérifiés sans affaiblissement :
`tests/test_graph_editor_dialog.py::test_highlight_step_key_skips_the_live_polling_timer` (le
mode `highlight_step_key` seul, sans `run_id`, doit rester identique).

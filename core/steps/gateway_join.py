"""
DataScheduler — core/steps/gateway_join.py
Passerelle de jonction (chantier Gateway, inspiré BPMN) : synchronise plusieurs branches
entrantes convergeant vers ce nœud — déjà supporté structurellement par le moteur (aucune limite
sur le nombre d'arêtes entrantes vers un même nœud, voir ui/graph_editor/graph_scene.py::
add_edge()). Deux modes (config "join_mode") :

- "AND" : n'avance que si TOUTES les arêtes entrantes ont abouti — une branche indisponible ou en
  échec fait échouer la jonction ELLE-MÊME (pas un simple skip). Appliqué EN AMONT de run() par
  get_join_mode()/IS_JOIN_GATEWAY (core/steps/__init__.py), consulté par core/pipeline.py
  (_execute_graph/_execute_graph_parallel) avant même de lancer cette étape — voir leur
  commentaire complet.
- "OR" (défaut) : avance dès qu'AU MOINS UNE arête entrante a abouti, ignore les autres — déjà le
  comportement historique implicite de tout nœud multi-prédécesseurs (should_skip dans les deux
  moteurs), rendu ici explicite et intentionnel plutôt qu'accidentel — cette classe n'a donc RIEN
  de spécial à faire pour ce mode.

Artefact transmis en aval (config "artifact_source_step_key") : jamais de fusion implicite — soit
l'utilisateur désigne explicitement la branche dont l'artefact continue, soit ce champ est vide et
SEULE la synchronisation a lieu (aucune donnée transmise, ctx.output_file remis à None). Corrige
un trou réel du moteur : avec 2+ arêtes de données actives simultanément vers un même nœud, la
réorientation automatique de ctx.output_file (data_incoming == 1 uniquement, voir
core/pipeline.py) ne fait rien — sans ce champ explicite, l'artefact resterait perdu en silence.
"""

from .base import BaseStep, StepContext, StepResult


class GatewayJoinStep(BaseStep):
    REQUIRES: set[str] = set()
    PRODUCES: set[str] = set()
    IS_ROUTING_NODE = True
    IS_JOIN_GATEWAY = True

    def run(self, ctx: StepContext, cancel_event=None, on_progress=None) -> StepResult:
        source_key = self.config.get("artifact_source_step_key")
        if source_key and source_key not in ctx.artifacts:
            # Cas légitime en mode OU : la branche désignée n'a pas tourné cette fois (une autre
            # branche a suffi) — pas une erreur, juste une trace explicite plutôt qu'un silence
            # surprenant (aucune donnée transmise dans ce cas, comme si rien n'était désigné).
            ctx.log(
                f"La branche désignée ({source_key}) n'a pas produit d'artefact dans cette "
                f"exécution — aucune donnée transmise."
            )
        ctx.output_file = ctx.artifacts.get(source_key) if source_key else None
        return StepResult(success=True)

"""
DataScheduler — tests/test_gateway_parallel_step.py
GatewayParallelStep (chantier Gateway) : marqueur de fork parallèle, run() est un pur no-op
délibéré — republier ctx.artifacts[step_key] à l'intérieur même de run() ne suffit PAS dans le
moteur parallèle (StepContext.fork() isole chaque étape sur sa propre copie, jetée après le
thread). La republication passe par PRODUCES = {"output_file"} + le mécanisme générique déjà
existant du moteur (core/pipeline.py::_execute_graph/_execute_graph_parallel) — voir les tests
d'intégration bout-en-bout (tests/test_pipeline_graph_engine.py::
test_gateway_parallel_forwards_artifact_to_every_branch et son pendant parallèle) pour la
non-régression complète du fan-out.
"""

from core.steps import get_step
from core.steps.base import StepContext
from core.steps.gateway_parallel import GatewayParallelStep


def test_run_is_a_no_op_that_succeeds():
    ctx = StepContext()
    ctx.output_file = "/tmp/data.csv"
    result = get_step("GATEWAY_PARALLEL", {"_step_key": "gw"}).run(ctx)
    assert result.success
    assert result.error is None
    # Un pur no-op : ni ctx.output_file ni ctx.artifacts ne sont touchés par run() lui-même.
    assert ctx.output_file == "/tmp/data.csv"
    assert "gw" not in ctx.artifacts


def test_run_without_step_key_does_not_raise():
    ctx = StepContext()
    result = get_step("GATEWAY_PARALLEL", {}).run(ctx)
    assert result.success


def test_produces_output_file_unconditionally():
    """Contrat déclaré (pas conditionnel à la config, contrairement à SPARK_SQL) — c'est ce que
    le moteur utilise pour republier même quand ctx.output_file n'a pas visiblement changé."""
    assert GatewayParallelStep.PRODUCES == {"output_file"}

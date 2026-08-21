"""
DataScheduler — tests/test_step_output_ports.py
Chantier port d'erreur générique (analogue BPMN "événement-frontière d'erreur") :
get_step_output_ports() (core/steps/__init__.py) est le seul point d'ancrage qui ajoute "error"
à TOUS les types d'étape, sans que chaque classe ait à le déclarer elle-même.
"""

from core.steps import get_step_output_ports


def test_regular_step_gets_output_file_and_error_ports():
    assert get_step_output_ports("DB_EXTRACT") == ("output_file", "error")


def test_condition_step_keeps_true_false_and_gains_error_port():
    assert get_step_output_ports("CONDITION") == ("true", "false", "error")


def test_unknown_step_type_still_gets_the_error_port():
    assert get_step_output_ports("NOT_A_REAL_TYPE") == ("output_file", "error")


def test_every_registered_step_type_declares_exactly_one_normal_port_plus_error():
    from core.steps import _REGISTRY
    for step_type in _REGISTRY:
        ports = get_step_output_ports(step_type)
        assert ports[-1] == "error"
        assert "error" not in ports[:-1]

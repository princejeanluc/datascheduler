"""
DataScheduler — tests/test_python_script_frozen_guard.py
Piège réel documenté dans docs/COOKBOOK.md ("Pièges déjà rencontrés") : dans un .exe PyInstaller,
sys.executable est le chemin de KULU.exe lui-même, pas un interpréteur Python — le
dialogue de config le pré-remplissait comme valeur par défaut avec un tooltip qui la présentait
comme sûre. Sans garde-fou, une étape PYTHON_SCRIPT gardant ce défaut ne lance pas le script :
elle relance une deuxième instance complète de l'application et bloque jusqu'au timeout.

sys.frozen n'existe pas normalement — simulé via monkeypatch pour reproduire le cas packagé sans
avoir besoin d'un vrai .exe.
"""

import sys

import pytest

from core.steps.base import StepContext
from core.steps.python_script import PythonScriptStep, _same_executable


def test_same_executable_matches_identical_paths():
    assert _same_executable(sys.executable, sys.executable) is True


def test_same_executable_differs_for_distinct_paths(tmp_path):
    other = tmp_path / "python.exe"
    assert _same_executable(str(other), sys.executable) is False


def test_same_executable_is_case_insensitive_and_normalizes(tmp_path):
    p = tmp_path / "Python.exe"
    p.write_text("")
    assert _same_executable(str(p).upper(), str(p).lower()) is True


def test_frozen_and_default_python_exe_refuses_cleanly(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "frozen", True, raising=False)

    step = PythonScriptStep({
        "script_path": str(tmp_path / "never_run.py"),
        # pas de python_executable configuré -> tombe sur le défaut sys.executable, exactement
        # le piège : dans un .exe gelé, sys.executable EST KULU.exe.
    })
    result = step.run(StepContext())

    assert result.success is False
    assert "KULU.exe" in result.error
    assert "Exécutable Python" in result.error


def test_frozen_with_explicit_different_python_exe_is_not_blocked(monkeypatch, tmp_path):
    # Simule sys.executable == le .exe de l'app (le vrai comportement une fois gelé) ; le champ
    # de config pointe explicitement vers le vrai interpréteur dev — un choix légitime distinct,
    # qui ne doit jamais être bloqué par le garde-fou.
    real_python = sys.executable
    fake_frozen_exe = str(tmp_path / "KULU.exe")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", fake_frozen_exe)

    script = tmp_path / "ok.py"
    script.write_text("import sys; sys.exit(0)", encoding="utf-8")

    step = PythonScriptStep({
        "script_path": str(script),
        "python_executable": real_python,
    })
    result = step.run(StepContext())

    assert result.success, result.error


def test_not_frozen_default_python_exe_is_not_blocked(tmp_path):
    """Hors .exe packagé (dev, python main.py), sys.executable est un vrai interpréteur — le
    garde-fou ne doit jamais gêner ce cas, seulement le cas frozen."""
    script = tmp_path / "ok.py"
    script.write_text("import sys; sys.exit(0)", encoding="utf-8")

    step = PythonScriptStep({"script_path": str(script)})
    result = step.run(StepContext())

    assert result.success, result.error

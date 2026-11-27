"""Contrat Q-01 réel : le runtime tourne sous ``python3 -I``, hors venv (T5)."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

import linuxtools.jobnotify.runtime as runtime_module

pytestmark = pytest.mark.integration

_SYSTEM_PYTHON = "/usr/bin/python3"


def _system_python_at_least_3_11() -> bool:
    """Vrai si le python3 système sait exécuter le runtime (``enum.StrEnum``).

    Sur la cible (Fedora) le python3 système est récent ; l'image de CI peut
    en embarquer un plus ancien, que le test ne doit pas juger.
    """
    if not Path(_SYSTEM_PYTHON).exists():
        return False
    completed = subprocess.run(  # noqa: S603 - argv fixe
        [
            _SYSTEM_PYTHON,
            "-I",
            "-c",
            "import sys; sys.exit(sys.version_info < (3, 11))",
        ],
        capture_output=True,
        timeout=30,
        check=False,
    )
    return completed.returncode == 0


@pytest.mark.skipif(
    not _system_python_at_least_3_11(),
    reason="python3 système introuvable ou antérieur à 3.11",
)
def test_runtime_lance_par_python_isole_rend_zero_sans_descripteur(
    tmp_path: Path,
) -> None:
    """``python3 -I runtime.py start`` sans descripteur voisin rend 0, sans venv."""
    script = tmp_path / "job-notify"
    shutil.copyfile(Path(runtime_module.__file__), script)

    completed = subprocess.run(  # noqa: S603 - argv fixe, script copié par le test
        [_SYSTEM_PYTHON, "-I", str(script), "start"],
        cwd=tmp_path,
        env={},  # ni PYTHONPATH ni VIRTUAL_ENV : rien du venv ne doit servir
        capture_output=True,
        encoding="utf-8",
        timeout=30,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert "Traceback" not in completed.stderr
    assert "ModuleNotFoundError" not in completed.stderr

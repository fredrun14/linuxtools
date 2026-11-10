"""Tests de la cible Makefile ``bump-consumers`` (T20)."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

_RACINE = Path(__file__).resolve().parents[2]
_MAKE = shutil.which("make")

pytestmark = pytest.mark.skipif(_MAKE is None, reason="make absent")


def _lancer(
    tmp_path: Path, *variables: str
) -> tuple[subprocess.CompletedProcess[str], list[str]]:
    """Lance ``make bump-consumers`` avec un faux ``uv`` qui note son argv."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    journal = tmp_path / "argv.txt"
    faux_uv = bin_dir / "uv"
    faux_uv.write_text(
        '#!/bin/sh\nfor a in "$@"; do printf "%s\\n" "$a" >> '
        f'"{journal}"; done\n'
    )
    faux_uv.chmod(0o755)
    env = {
        **os.environ,
        "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
    }
    assert _MAKE is not None
    result = subprocess.run(  # noqa: S603
        [_MAKE, "-C", str(_RACINE), "bump-consumers", *variables],
        env=env,
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    argv = journal.read_text().splitlines() if journal.exists() else []
    return result, argv


def test_tag_malicieux_n_est_pas_execute_par_le_shell(
    tmp_path: Path,
) -> None:
    piege = tmp_path / "pwned"

    result, argv = _lancer(tmp_path, f"TAG=v1;touch {piege}")

    assert not piege.exists()
    assert result.returncode == 0
    assert argv[-1] == f"v1;touch {piege}"


def test_tag_avec_guillemet_n_echappe_pas_au_test_de_presence(
    tmp_path: Path,
) -> None:
    piege = tmp_path / "pwned"

    _, argv = _lancer(tmp_path, f'TAG=x"; touch {piege}; "')

    assert not piege.exists()
    assert argv[-1] == f'x"; touch {piege}; "'


def test_args_decoupes_en_mots_sans_interpretation_du_shell(
    tmp_path: Path,
) -> None:
    piege = tmp_path / "pwned"

    _, argv = _lancer(
        tmp_path,
        "TAG=v2.11.1",
        f"ARGS=--dry-run --only app; touch {piege}",
    )

    assert not piege.exists()
    assert argv == [
        "run",
        "python",
        "-m",
        "linuxtools.devtools",
        "bump-consumers",
        "v2.11.1",
        "--dry-run",
        "--only",
        "app;",
        "touch",
        str(piege),
    ]


def test_sans_tag_affiche_l_usage_et_sort_en_2(tmp_path: Path) -> None:
    result, argv = _lancer(tmp_path)

    assert result.returncode == 2
    assert "Usage" in result.stdout + result.stderr
    assert argv == []


def _make_n(cible: str) -> str:
    """Commandes que ``make <cible>`` lancerait (``-n`` : rien n'est exécuté)."""
    assert _MAKE is not None
    result = subprocess.run(  # noqa: S603
        [_MAKE, "-n", "-C", str(_RACINE), cible],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


def test_gate_de_format_unique_couvre_src_et_tests_devtools() -> None:
    commandes = _make_n("format-check")

    assert "ruff format --check" in commandes
    assert "src/" in commandes
    assert "tests/unit/test_devtools_bumper_real.py" in commandes
    assert "tests/unit/scripted_executor.py" in commandes
    assert "tests/integration/test_devtools_bumper.py" in commandes


def test_make_lint_passe_par_le_gate_de_format() -> None:
    assert _make_n("lint").count("ruff format --check") == 1
    assert "tests/unit/test_devtools_report.py" in _make_n("lint")


@pytest.mark.parametrize(
    "fichier", [".forgejo/workflows/ci.yml", ".githooks/pre-commit"]
)
def test_ci_et_hook_appellent_le_gate_du_makefile(fichier: str) -> None:
    texte = (_RACINE / fichier).read_text(encoding="utf-8")

    assert "make format-check" in texte
    # pas de copie du gate qui dériverait du Makefile (commentaires exclus)
    code = [
        ligne
        for ligne in texte.splitlines()
        if not ligne.lstrip().startswith("#")
    ]
    assert "ruff format" not in "\n".join(code).lower()

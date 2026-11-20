"""Garde-fou : aucune référence directe hors de l'extra ``network``.

``allow-direct-references`` est activé pour l'extra ``network`` (webapitools épinglé
par URL git). Ce test empêche qu'une référence directe passe, sans alerte, dans
``[project].dependencies`` ou dans un autre extra : elles partent dans les
métadonnées du wheel publié.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

_RACINE = Path(__file__).resolve().parents[2]

# webapitools n'est pas publié sur PyPI : il est épinglé par tag git (cf. pyproject).
_EXTRAS_AUTORISES = frozenset({"network"})


def _references_directes(pyproject: Path) -> list[str]:
    """Liste les dépendances en référence directe (PEP 508), extras autorisés exclus."""
    projet = tomllib.loads(pyproject.read_text(encoding="utf-8"))["project"]
    candidates: list[str] = list(projet["dependencies"])
    for extra, dependances in projet.get("optional-dependencies", {}).items():
        if extra not in _EXTRAS_AUTORISES:
            candidates.extend(dependances)
    # Un marqueur (après `;`) peut contenir « @ » sans être une référence directe.
    return [d for d in candidates if "@" in d.split(";", maxsplit=1)[0]]


def _ecrire(tmp_path: Path, dependances: str, extras: str) -> Path:
    copie = tmp_path / "pyproject.toml"
    copie.write_text(
        f'[project]\nname = "x"\ndependencies = {dependances}\n'
        f"[project.optional-dependencies]\n{extras}\n",
        encoding="utf-8",
    )
    return copie


def test_references_directes_detecte_url_git_dans_les_dependances(
    tmp_path: Path,
) -> None:
    copie = _ecrire(
        tmp_path, '["platformdirs>=4.12", "lib @ git+https://h/lib.git@v1"]', ""
    )

    assert _references_directes(copie) == ["lib @ git+https://h/lib.git@v1"]


def test_references_directes_detecte_url_git_dans_un_extra_non_autorise(
    tmp_path: Path,
) -> None:
    copie = _ecrire(
        tmp_path,
        '["platformdirs>=4.12"]',
        'validation = ["lib @ git+https://h/lib.git@v1"]',
    )

    assert _references_directes(copie) == ["lib @ git+https://h/lib.git@v1"]


def test_references_directes_tolere_extra_autorise_et_marqueurs(
    tmp_path: Path,
) -> None:
    copie = _ecrire(
        tmp_path,
        "[\"tomli>=2; python_version < '3.11' and extra != 'a@b'\"]",
        'network = ["w @ git+https://h/w.git@v1"]',
    )

    assert _references_directes(copie) == []


def test_pyproject_sans_reference_directe_hors_extra_network() -> None:
    assert _references_directes(_RACINE / "pyproject.toml") == []

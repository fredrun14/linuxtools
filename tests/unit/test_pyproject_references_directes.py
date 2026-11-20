"""Garde-fou : aucune référence directe dans les dépendances du cœur.

``allow-direct-references`` est activé pour l'extra ``network`` (webapitools épinglé
par URL git). Ce test empêche qu'une référence directe passe, sans alerte, dans
``[project].dependencies``, qui part dans les métadonnées du wheel publié.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

_RACINE = Path(__file__).resolve().parents[2]


def _references_directes(pyproject: Path) -> list[str]:
    """Liste les dépendances du cœur écrites en référence directe (PEP 508)."""
    donnees = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    dependances: list[str] = donnees["project"]["dependencies"]
    return [d for d in dependances if "@" in d]


def test_references_directes_detecte_url_git_dans_les_dependances(
    tmp_path: Path,
) -> None:
    copie = tmp_path / "pyproject.toml"
    copie.write_text(
        '[project]\nname = "x"\n'
        'dependencies = ["platformdirs>=4.12", "lib @ git+https://h/lib.git@v1"]\n',
        encoding="utf-8",
    )

    assert _references_directes(copie) == ["lib @ git+https://h/lib.git@v1"]


def test_pyproject_dependances_du_coeur_sans_reference_directe() -> None:
    assert _references_directes(_RACINE / "pyproject.toml") == []

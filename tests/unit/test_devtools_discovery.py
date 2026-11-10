"""Tests de la découverte des consommateurs (devtools.discovery)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from linuxtools.devtools.discovery import Consumer, discover_consumers

if TYPE_CHECKING:
    from pathlib import Path

_PIN = "linuxtools @ git+https://git.ricfasohel.fr/fred/linuxtools.git@v2.0.0"


def _projet(
    root: Path,
    dossier: str,
    *,
    name: str | None = None,
    deps: str = f'"{_PIN}"',
    git: bool = True,
    pyproject: bool = True,
) -> Path:
    """Crée un faux dépôt dans ``root``."""
    chemin = root / dossier
    chemin.mkdir()
    if git:
        (chemin / ".git").mkdir()
    if pyproject:
        nom = name or dossier
        (chemin / "pyproject.toml").write_text(
            f'[project]\nname = "{nom}"\ndependencies = [{deps}]\n'
        )
    return chemin


def test_decouvre_les_consommateurs_tries(tmp_path: Path) -> None:
    b = _projet(tmp_path, "b-projet")
    a = _projet(tmp_path, "a_projet", name="a-projet")

    resultat = discover_consumers(tmp_path)

    assert resultat == [
        Consumer(name="a-projet", path=a),
        Consumer(name="b-projet", path=b),
    ]


def test_exclut_linuxtools_lui_meme(tmp_path: Path) -> None:
    _projet(tmp_path, "linuxtools", deps='"platformdirs"')
    _projet(tmp_path, "clone-de-linuxtools", name="linuxtools")
    _projet(tmp_path, "app")

    noms = [c.name for c in discover_consumers(tmp_path)]

    assert noms == ["app"]


def test_ignore_ce_qui_n_est_pas_un_consommateur(tmp_path: Path) -> None:
    _projet(tmp_path, "sans-pin", deps='"requests"')
    _projet(tmp_path, "sans-git", git=False)
    _projet(tmp_path, "sans-pyproject", pyproject=False)
    (tmp_path / "fichier.txt").write_text("x")
    cassé = _projet(tmp_path, "toml-casse", pyproject=False)
    (cassé / "pyproject.toml").write_text(f"[project\n# {_PIN}\n")
    _projet(tmp_path, "ok")

    noms = [c.name for c in discover_consumers(tmp_path)]

    assert noms == ["ok"]


def test_nom_projet_absent_replie_sur_le_dossier(tmp_path: Path) -> None:
    chemin = _projet(tmp_path, "sans-nom", pyproject=False)
    (chemin / "pyproject.toml").write_text(
        f'[project]\ndependencies=["{_PIN}"]'
    )

    assert [c.name for c in discover_consumers(tmp_path)] == ["sans-nom"]


def test_only_filtre_par_nom_de_projet_ou_de_dossier(tmp_path: Path) -> None:
    _projet(tmp_path, "a_dir", name="a-nom")
    _projet(tmp_path, "b")
    _projet(tmp_path, "c")

    noms = [c.name for c in discover_consumers(tmp_path, only=["a-nom", "c"])]

    assert noms == ["a-nom", "c"]
    assert [c.name for c in discover_consumers(tmp_path, only=["a_dir"])] == [
        "a-nom"
    ]


def test_exclude_retire_les_projets(tmp_path: Path) -> None:
    _projet(tmp_path, "a")
    _projet(tmp_path, "b")

    noms = [c.name for c in discover_consumers(tmp_path, exclude=["a"])]

    assert noms == ["b"]


def test_only_et_exclude_sont_exclusifs(tmp_path: Path) -> None:
    _projet(tmp_path, "a")

    with pytest.raises(ValueError, match="exclusifs"):
        discover_consumers(tmp_path, only=["a"], exclude=["a"])


@pytest.mark.parametrize("option", ["only", "exclude"])
def test_nom_inconnu_leve_valueerror(tmp_path: Path, option: str) -> None:
    _projet(tmp_path, "a")

    with pytest.raises(ValueError, match="inconnu"):
        discover_consumers(tmp_path, **{option: ["fantome"]})

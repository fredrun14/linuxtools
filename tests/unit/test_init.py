"""Tests pour `linuxtools.__version__` (lecture dynamique des métadonnées)."""

import importlib
import importlib.metadata as metadata
import tomllib
from pathlib import Path

import pytest

import linuxtools

# Racine du dépôt : tests/unit/test_init.py -> tests/unit -> tests -> racine.
_RACINE_DEPOT = Path(__file__).resolve().parents[2]


class TestVersion:
    """Tests pour l'attribut `linuxtools.__version__`."""

    def test_version_correspond_a_pyproject_toml(self) -> None:
        """`__version__` correspond au champ `[project].version` de
        `pyproject.toml`, source de vérité du numéro de version.
        """
        # Arrange
        pyproject = _RACINE_DEPOT / "pyproject.toml"
        with pyproject.open("rb") as fichier:
            donnees = tomllib.load(fichier)
        version_attendue = donnees["project"]["version"]

        # Act
        version_obtenue = linuxtools.__version__

        # Assert
        assert version_obtenue == version_attendue

    def test_version_est_une_chaine_non_vide(self) -> None:
        """Filet minimal : `__version__` est toujours une chaîne non vide."""
        # Act
        version_obtenue = linuxtools.__version__

        # Assert
        assert isinstance(version_obtenue, str)
        assert version_obtenue != ""

    def test_version_repli_si_paquet_non_installe(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """`__version__` se replie sur "0.0.0+unknown" si
        `importlib.metadata.version` lève `PackageNotFoundError` (paquet
        non installé).
        """

        # Arrange : `linuxtools` importe `version` depuis
        # `importlib.metadata` via `from ... import version as _version` ;
        # patcher la source puis recharger le module relie `_version` au
        # substitut ci-dessous.
        def _version_leve_erreur(nom: str) -> str:
            raise metadata.PackageNotFoundError(nom)

        monkeypatch.setattr(metadata, "version", _version_leve_erreur)

        try:
            # Act
            importlib.reload(linuxtools)

            # Assert
            assert linuxtools.__version__ == "0.0.0+unknown"
        finally:
            # Nettoyage : restaurer l'état normal du module après le test,
            # une fois le monkeypatch de `metadata.version` annulé.
            monkeypatch.undo()
            importlib.reload(linuxtools)

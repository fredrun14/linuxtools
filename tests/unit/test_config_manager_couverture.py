"""Tests de comportement complémentaires pour ConfigurationManager."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from linuxtools.config import ConfigurationManager
from linuxtools.logging.base import Logger


def test_la_creation_de_config_par_defaut_est_journalisee(tmp_path: Path) -> None:
    """Avec un logger, la création du fichier par défaut est tracée en info."""
    logger = MagicMock(spec=Logger)
    cible = tmp_path / "app.json"
    manager = ConfigurationManager(cible, default_config={"a": 1}, logger=logger)

    manager.create_default_config()

    assert cible.exists()
    logger.log_info.assert_called_once()
    assert str(cible) in logger.log_info.call_args[0][0]


def test_aucun_emplacement_existant_donne_une_config_par_defaut(
    tmp_path: Path,
) -> None:
    """Si aucun chemin de recherche n'existe, la config par défaut est utilisée."""
    manager = ConfigurationManager(
        default_config={"a": 1},
        search_paths=[str(tmp_path / "absent.json")],
    )

    assert manager.config_path is None
    assert manager.get("a") == 1


def test_creation_de_config_sans_chemin_est_refusee() -> None:
    """Sans chemin configuré ni fourni, la création échoue explicitement."""
    manager = ConfigurationManager(default_config={"a": 1})

    with pytest.raises(ValueError, match="Aucun chemin"):
        manager.create_default_config()


def test_creation_de_config_avec_extension_inconnue_est_refusee(
    tmp_path: Path,
) -> None:
    """Une extension non supportée est refusée avec la liste des extensions."""
    manager = ConfigurationManager(default_config={"a": 1})

    with pytest.raises(ValueError, match="Extension non supportée"):
        manager.create_default_config(tmp_path / "app.xyz")

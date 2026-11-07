"""Tests de la résolution XDG du dossier des unités systemd utilisateur."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from linuxtools.systemd.base import ServiceConfig, _resolve_user_unit_path
from linuxtools.systemd.user_service import LinuxUserServiceUnitManager


def test_resolve_user_unit_path_suit_xdg_config_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Sans surcharge, le dossier suit ``XDG_CONFIG_HOME``."""
    # Arrange
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))

    # Act
    resultat = _resolve_user_unit_path("~/.config/systemd/user")

    # Assert
    assert resultat == str(tmp_path / "systemd" / "user")


def test_resolve_user_unit_path_surcharge_garde_expanduser(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Une valeur surchargée garde ``expanduser`` et ignore XDG."""
    # Arrange
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    monkeypatch.setenv("HOME", str(tmp_path))

    # Act
    resultat = _resolve_user_unit_path("~/x")

    # Assert
    assert resultat == str(tmp_path / "x")


def test_resolve_user_unit_path_defaut_sans_xdg_config_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Sans ``XDG_CONFIG_HOME``, retour à ``~/.config/systemd/user``."""
    # Arrange
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))

    # Act
    resultat = _resolve_user_unit_path("~/.config/systemd/user")

    # Assert
    assert resultat == str(tmp_path / ".config" / "systemd" / "user")


def test_user_unit_manager_unit_path_suit_xdg_config_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``unit_path`` d'un gestionnaire concret suit ``XDG_CONFIG_HOME``."""
    # Arrange
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))

    # Act
    manager = LinuxUserServiceUnitManager(MagicMock(), MagicMock())

    # Assert
    assert manager.unit_path == str(tmp_path / "systemd" / "user")


def test_user_unit_manager_ecrit_dans_le_dossier_xdg(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """L'unité installée est écrite sous ``XDG_CONFIG_HOME``."""
    # Arrange
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    manager = LinuxUserServiceUnitManager(MagicMock(), MagicMock())
    config = ServiceConfig(description="Test", exec_start="/usr/bin/test")

    # Act
    resultat = manager.install_service_unit_with_name("mon-outil", config)

    # Assert
    assert resultat is True
    fichier = tmp_path / "systemd" / "user" / "mon-outil.service"
    assert fichier.exists()

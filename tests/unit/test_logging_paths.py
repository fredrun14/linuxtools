"""Tests de ``linuxtools.logging.paths``."""

import os
from pathlib import Path

import pytest

from linuxtools.logging.paths import default_log_dir


def test_default_log_dir_utilisateur_suit_xdg_state_home(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Utilisateur non root : le dossier suit ``XDG_STATE_HOME``."""
    # Arrange
    monkeypatch.setattr(os, "geteuid", lambda: 1000)
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))

    # Act
    resultat = default_log_dir("mon-app")

    # Assert
    assert resultat == tmp_path / "mon-app"


def test_default_log_dir_utilisateur_sans_xdg(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Sans ``XDG_STATE_HOME`` : repli sous ``~/.local/state``."""
    # Arrange
    monkeypatch.setattr(os, "geteuid", lambda: 1000)
    monkeypatch.delenv("XDG_STATE_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))

    # Act
    resultat = default_log_dir("mon-app")

    # Assert
    assert resultat == tmp_path / ".local" / "state" / "mon-app"


def test_default_log_dir_root_utilise_var_log(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Sous root : ``/var/log/<app>`` (FHS)."""
    # Arrange
    monkeypatch.setattr(os, "geteuid", lambda: 0)

    # Act
    resultat = default_log_dir("mon-app")

    # Assert
    assert resultat == Path("/var/log/mon-app")


def test_default_log_dir_ne_cree_pas_le_dossier(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Le dossier retourné n'est pas créé."""
    # Arrange
    monkeypatch.setattr(os, "geteuid", lambda: 1000)
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))

    # Act
    resultat = default_log_dir("mon-app")

    # Assert
    assert not resultat.exists()


def test_default_log_dir_exporte_par_linuxtools_logging() -> None:
    """``default_log_dir`` est importable depuis ``linuxtools.logging``."""
    # Arrange / Act
    import linuxtools.logging as logging_pkg

    # Assert
    assert "default_log_dir" in logging_pkg.__all__
    assert logging_pkg.default_log_dir is default_log_dir

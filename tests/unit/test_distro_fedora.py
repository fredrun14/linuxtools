"""Tests pour le module distro.fedora."""

from unittest.mock import MagicMock

from linuxtools.commands.base import CommandExecutor, CommandResult
from linuxtools.distro.fedora import fedora_version


def _make_executor(
    return_code: int = 0, stdout: str = ""
) -> MagicMock:
    """Crée un mock de CommandExecutor pour fedora_version()."""
    mock = MagicMock(spec=CommandExecutor)
    mock.probe.return_value = CommandResult(
        command=("rpm", "--eval", "%fedora"),
        return_code=return_code,
        stdout=stdout,
        stderr="",
        success=return_code == 0,
        duration=0.0,
    )
    return mock


class TestFedoraVersion:
    """Tests pour fedora_version()."""

    def test_nominal_retourne_la_version(self) -> None:
        """Cas nominal : retourne la version stdout sans le \\n."""
        # Arrange
        executor = _make_executor(return_code=0, stdout="44\n")

        # Act
        version = fedora_version(executor)

        # Assert
        assert version == "44"

    def test_utilise_probe_et_pas_run(self) -> None:
        """fedora_version() sonde via executor.probe(), pas run()."""
        # Arrange
        executor = _make_executor(return_code=0, stdout="44")

        # Act
        fedora_version(executor)

        # Assert
        executor.probe.assert_called_once_with(
            ["rpm", "--eval", "%fedora"]
        )
        executor.run.assert_not_called()

    def test_code_retour_non_nul_retourne_chaine_vide(self) -> None:
        """Code retour non nul → chaîne vide (variante défensive)."""
        # Arrange
        executor = _make_executor(
            return_code=1, stdout="erreur rpm"
        )

        # Act
        version = fedora_version(executor)

        # Assert
        assert version == ""

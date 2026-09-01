"""Tests pour `_write_unit_content_remote` (systemd/base.py).

Écriture distante d'un fichier d'unité systemd via
`install -m 644 -T /dev/stdin <dest>` (une seule commande, cf.
correctif de sécurité « fenêtre de permissions / suivi de symlink »).
Cette fonction n'avait aucun test avant ce plan.
"""

from unittest.mock import MagicMock

from linuxtools.commands.base import CommandResult
from linuxtools.systemd.base import _write_unit_content_remote
from linuxtools.systemd.executor import SystemdExecutor


def _result(success: bool = True, stderr: str = "") -> CommandResult:
    """Construit un CommandResult scripté pour les tests."""
    return CommandResult(
        command=(),
        return_code=0 if success else 1,
        stdout="",
        stderr=stderr,
        success=success,
        duration=0.01,
    )


class TestWriteUnitContentRemote:
    """Tests de `_write_unit_content_remote` (executor.run_raw)."""

    def test_ecriture_distante_emet_install_avec_mode_et_no_target_directory(
        self,
    ) -> None:
        """Un seul appel `install -m 644 -T /dev/stdin <dest>` : `-T`
        empêche `install` de suivre un symlink ou de créer un fichier
        fantôme si la destination est un répertoire (A01)."""
        # Arrange
        unit_path = "/etc/systemd/system/mon-service.service"
        executor = MagicMock(spec=SystemdExecutor)
        executor.run_raw.return_value = _result(True)
        logger = MagicMock()

        # Act
        result = _write_unit_content_remote(
            unit_path, "[Unit]\n", executor, logger
        )

        # Assert
        assert result is True
        executor.run_raw.assert_called_once_with(
            ["install", "-m", "644", "-T", "/dev/stdin", unit_path],
            stdin="[Unit]\n",
        )

    def test_ecriture_distante_passe_le_contenu_par_stdin(self) -> None:
        """Le contenu de l'unité transite par stdin, jamais par argv
        (A09 : pas d'exposition du contenu via `ps`)."""
        # Arrange
        unit_path = "/etc/systemd/system/mon-service.service"
        executor = MagicMock(spec=SystemdExecutor)
        executor.run_raw.return_value = _result(True)
        logger = MagicMock()
        contenu = "[Service]\nExecStart=/usr/bin/mon-binaire\n"

        # Act
        _write_unit_content_remote(unit_path, contenu, executor, logger)

        # Assert
        install_call = executor.run_raw.call_args
        assert contenu not in install_call.args[0]
        assert install_call.args[0][-1] == unit_path
        assert install_call.kwargs["stdin"] == contenu

    def test_ecriture_distante_echec_retourne_false_et_logue(self) -> None:
        """Échec d'`install` -> False, une seule erreur loguée, pas de
        second mode d'échec (plus de `chmod` séparé)."""
        # Arrange
        unit_path = "/etc/systemd/system/mon-service.service"
        executor = MagicMock(spec=SystemdExecutor)
        executor.run_raw.return_value = _result(
            False, stderr="permission denied"
        )
        logger = MagicMock()

        # Act
        result = _write_unit_content_remote(
            unit_path, "[Unit]\n", executor, logger
        )

        # Assert
        assert result is False
        executor.run_raw.assert_called_once()
        logger.log_error.assert_called_once()
        logger.log_info.assert_not_called()
        assert "permission denied" in logger.log_error.call_args.args[0]

    def test_ecriture_distante_succes_logue_le_chemin(self) -> None:
        """Succès -> True, un seul log d'information mentionnant le
        chemin de destination."""
        # Arrange
        unit_path = "/etc/systemd/system/mon-service.service"
        executor = MagicMock(spec=SystemdExecutor)
        executor.run_raw.return_value = _result(True)
        logger = MagicMock()

        # Act
        result = _write_unit_content_remote(
            unit_path, "[Unit]\n", executor, logger
        )

        # Assert
        assert result is True
        logger.log_info.assert_called_once()
        assert unit_path in logger.log_info.call_args.args[0]
        logger.log_error.assert_not_called()

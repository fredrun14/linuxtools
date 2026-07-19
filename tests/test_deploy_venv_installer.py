"""Tests pour le module deploy.venv_installer."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from linuxtools.commands.base import CommandExecutor, CommandResult
from linuxtools.deploy.exceptions import DeployError
from linuxtools.deploy.venv_installer import VenvInstaller
from linuxtools.logging.base import Logger


def _result(
    success: bool = True, stdout: str = "", stderr: str = ""
) -> CommandResult:
    """Construit un CommandResult scripté pour les tests."""
    return CommandResult(
        command=(),
        return_code=0 if success else 1,
        stdout=stdout,
        stderr=stderr,
        success=success,
        duration=0.01,
    )


def _make_executor() -> MagicMock:
    """Crée un mock de CommandExecutor cible."""
    return MagicMock(spec=CommandExecutor)


class TestVenvInstallerBackupVenv:
    """Tests pour VenvInstaller.backup_venv()."""

    def test_retourne_none_si_venv_absent(self):
        """Retourne None (rien à sauver) si le venv n'existe pas."""
        executor = _make_executor()
        executor.run.return_value = _result(success=False)
        installer = VenvInstaller(executor)

        backup = installer.backup_venv(Path("/opt/app/venv"))

        assert backup is None
        executor.run.assert_called_once_with(
            ["test", "-d", "/opt/app/venv"]
        )

    def test_retourne_le_chemin_de_backup_si_succes(self):
        """Retourne un Path .bak-<timestamp> si cp réussit."""
        executor = _make_executor()
        executor.run.side_effect = [
            _result(success=True),  # test -d
            _result(success=True),  # cp -a
        ]
        logger = MagicMock(spec=Logger)
        installer = VenvInstaller(executor, logger=logger)

        with patch(
            "linuxtools.deploy.venv_installer.datetime"
        ) as mock_dt:
            mock_dt.now.return_value.strftime.return_value = (
                "20260719-165500"
            )
            backup = installer.backup_venv(Path("/opt/app/venv"))

        assert backup == Path("/opt/app/venv.bak-20260719-165500")
        logger.log_info.assert_called_once()

    def test_leve_deploy_error_si_cp_echoue(self):
        """Lève DeployError si la copie de sauvegarde échoue.

        Cœur du besoin (plan §Points d'attention 3) : on n'installe
        jamais sans filet de rollback.
        """
        executor = _make_executor()
        executor.run.side_effect = [
            _result(success=True),  # test -d
            _result(success=False, stderr="cp: permission denied"),
        ]
        installer = VenvInstaller(executor)

        with pytest.raises(DeployError, match="Backup"):
            installer.backup_venv(Path("/opt/app/venv"))

    def test_logue_erreur_si_backup_echoue(self):
        """Le logger reçoit l'erreur avant la levée de DeployError."""
        executor = _make_executor()
        executor.run.side_effect = [
            _result(success=True),
            _result(success=False, stderr="boom"),
        ]
        logger = MagicMock(spec=Logger)
        installer = VenvInstaller(executor, logger=logger)

        with pytest.raises(DeployError):
            installer.backup_venv(Path("/opt/app/venv"))

        logger.log_error.assert_called_once()


class TestVenvInstallerInstall:
    """Tests pour VenvInstaller.install()."""

    def test_utilise_toujours_le_pip_du_venv(self):
        """Verrou PEP 668 : jamais python3 -m pip système.

        Fedora 41+ lève externally-managed-environment si on invoque
        le pip système ; seul <venv>/bin/pip est protégé.
        """
        executor = _make_executor()
        executor.run.return_value = _result(success=True)
        installer = VenvInstaller(executor)

        installer.install(Path("/opt/app/venv"), Path("/opt/app/src"))

        command = executor.run.call_args.args[0]
        assert command[0] == "/opt/app/venv/bin/pip"
        assert "python3" not in command
        assert "-m" not in command

    def test_commande_pip_force_reinstall(self):
        """La commande pip utilise --force-reinstall (idempotence)."""
        executor = _make_executor()
        executor.run.return_value = _result(success=True)
        installer = VenvInstaller(executor)

        installer.install(Path("/opt/app/venv"), Path("/opt/app/src"))

        command = executor.run.call_args.args[0]
        assert command == [
            "/opt/app/venv/bin/pip",
            "install",
            "--force-reinstall",
            "/opt/app/src",
        ]

    def test_timeout_genereux(self):
        """Le timeout pip est généreux (deps git potentiellement longues)."""
        executor = _make_executor()
        executor.run.return_value = _result(success=True)
        installer = VenvInstaller(executor)

        installer.install(Path("/opt/app/venv"), Path("/opt/app/src"))

        assert executor.run.call_args.kwargs["timeout"] >= 300

    def test_retourne_le_resultat_pip(self):
        """install() retourne le CommandResult de pip."""
        executor = _make_executor()
        executor.run.return_value = _result(
            success=False, stderr="pip error"
        )
        installer = VenvInstaller(executor)

        result = installer.install(
            Path("/opt/app/venv"), Path("/opt/app/src")
        )

        assert result.success is False
        assert result.stderr == "pip error"

    def test_recreate_supprime_puis_recree_le_venv(self):
        """recreate=True : rm -rf puis python3 -m venv avant pip."""
        executor = _make_executor()
        executor.run.side_effect = [
            _result(success=True, stdout="Python 3.11.9"),  # version
            _result(success=True),  # rm -rf
            _result(success=True),  # python3 -m venv
            _result(success=True),  # pip install
        ]
        installer = VenvInstaller(executor)

        installer.install(
            Path("/opt/app/venv"),
            Path("/opt/app/src"),
            recreate=True,
        )

        calls = [c.args[0] for c in executor.run.call_args_list]
        assert calls[0] == ["python3", "--version"]
        assert calls[1] == ["rm", "-rf", "/opt/app/venv"]
        assert calls[2] == ["python3", "-m", "venv", "/opt/app/venv"]
        assert calls[3][0] == "/opt/app/venv/bin/pip"

    def test_recreate_arrete_si_rm_echoue(self):
        """Si rm -rf échoue en mode recreate, pip n'est pas appelé."""
        executor = _make_executor()
        executor.run.side_effect = [
            _result(success=True, stdout="Python 3.11.9"),
            _result(success=False, stderr="rm error"),
        ]
        installer = VenvInstaller(executor)

        result = installer.install(
            Path("/opt/app/venv"),
            Path("/opt/app/src"),
            recreate=True,
        )

        assert result.success is False
        assert executor.run.call_count == 2

    def test_recreate_arrete_si_creation_venv_echoue(self):
        """Si python3 -m venv échoue, pip n'est pas appelé."""
        executor = _make_executor()
        executor.run.side_effect = [
            _result(success=True, stdout="Python 3.11.9"),
            _result(success=True),
            _result(success=False, stderr="venv error"),
        ]
        installer = VenvInstaller(executor)

        result = installer.install(
            Path("/opt/app/venv"),
            Path("/opt/app/src"),
            recreate=True,
        )

        assert result.success is False
        assert executor.run.call_count == 3


class TestVenvInstallerRestoreVenv:
    """Tests pour VenvInstaller.restore_venv()."""

    def test_restaure_avec_succes(self):
        """rm -rf puis mv réussissent : restore_venv retourne True."""
        executor = _make_executor()
        executor.run.side_effect = [
            _result(success=True),  # rm -rf
            _result(success=True),  # mv
        ]
        installer = VenvInstaller(executor)

        ok = installer.restore_venv(
            Path("/opt/app/venv"),
            Path("/opt/app/venv.bak-20260719"),
        )

        assert ok is True

    def test_retourne_false_si_rm_echoue(self):
        """rm -rf échoue : restore_venv retourne False sans mv."""
        executor = _make_executor()
        executor.run.return_value = _result(success=False)
        installer = VenvInstaller(executor)

        ok = installer.restore_venv(
            Path("/opt/app/venv"),
            Path("/opt/app/venv.bak-20260719"),
        )

        assert ok is False
        assert executor.run.call_count == 1

    def test_retourne_false_si_mv_echoue(self):
        """mv échoue après un rm -rf réussi : retourne False."""
        executor = _make_executor()
        executor.run.side_effect = [
            _result(success=True),
            _result(success=False, stderr="mv error"),
        ]
        installer = VenvInstaller(executor)

        ok = installer.restore_venv(
            Path("/opt/app/venv"),
            Path("/opt/app/venv.bak-20260719"),
        )

        assert ok is False


class TestVenvInstallerPruneBackup:
    """Tests pour VenvInstaller.prune_backup()."""

    def test_supprime_le_backup(self):
        """prune_backup exécute rm -rf sur le chemin du backup."""
        executor = _make_executor()
        executor.run.return_value = _result(success=True)
        installer = VenvInstaller(executor)

        installer.prune_backup(Path("/opt/app/venv.bak-20260719"))

        executor.run.assert_called_once_with(
            ["rm", "-rf", "/opt/app/venv.bak-20260719"]
        )

    def test_best_effort_ne_leve_pas_si_echec(self):
        """Un échec de suppression du backup ne lève pas d'exception."""
        executor = _make_executor()
        executor.run.return_value = _result(
            success=False, stderr="rm error"
        )
        logger = MagicMock(spec=Logger)
        installer = VenvInstaller(executor, logger=logger)

        installer.prune_backup(Path("/opt/app/venv.bak-20260719"))

        logger.log_error.assert_called_once()

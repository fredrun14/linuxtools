"""Tests pour le module deploy.config_deployer."""

import tomllib
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from linuxtools.commands.base import CommandExecutor, CommandResult
from linuxtools.deploy.config_deployer import ConfigDeployer
from linuxtools.deploy.models import ConfigDeploySpec, DeployTarget


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


class TestConfigDeployerDeployLocal:
    """Tests du dépôt de config en local."""

    def test_deploy_local_nominal_ecrit_le_toml_effectif(
        self, tmp_path: Path
    ) -> None:
        """Cas nominal : le TOML de spec.data est déposé sur disque."""
        # Arrange
        dest_path = tmp_path / "config.toml"
        spec = ConfigDeploySpec(
            data={"service": {"port": 8080, "enabled": True}},
            dest_path=dest_path,
            mode=0o640,
        )
        target = DeployTarget()
        executor = MagicMock(spec=CommandExecutor)
        deployer = ConfigDeployer()

        # Act
        result = deployer.deploy(spec, target, executor)

        # Assert
        assert result is True
        written = tomllib.loads(dest_path.read_text(encoding="utf-8"))
        assert written == {"service": {"port": 8080, "enabled": True}}
        executor.run.assert_not_called()

    def test_deploy_local_utilise_le_mode_par_defaut(
        self, tmp_path: Path
    ) -> None:
        """Cas limite : mode non renseigné -> 0o644 (défaut du spec)."""
        import os

        dest_path = tmp_path / "config.toml"
        spec = ConfigDeploySpec(data={"a": 1}, dest_path=dest_path)
        deployer = ConfigDeployer()

        result = deployer.deploy(
            spec, DeployTarget(), MagicMock(spec=CommandExecutor)
        )

        assert result is True
        assert oct(os.stat(dest_path).st_mode)[-3:] == "644"

    def test_deploy_local_dossier_parent_inexistant_leve_oserror(
        self, tmp_path: Path
    ) -> None:
        """Cas d'erreur : parent inexistant -> OSError propagée
        (write_text_secure ne crée pas les dossiers)."""
        dest_path = tmp_path / "inexistant" / "config.toml"
        spec = ConfigDeploySpec(data={"a": 1}, dest_path=dest_path)
        deployer = ConfigDeployer()

        with pytest.raises(OSError):
            deployer.deploy(
                spec, DeployTarget(), MagicMock(spec=CommandExecutor)
            )


class TestConfigDeployerDeployRemote:
    """Tests du dépôt de config à distance."""

    def test_deploy_remote_nominal_ecrit_via_tee_puis_chmod(self) -> None:
        """Cas nominal distant : tee (stdin=TOML) puis chmod réussissent."""
        # Arrange
        dest_path = Path("/etc/app/config.toml")
        spec = ConfigDeploySpec(
            data={"a": 1}, dest_path=dest_path, mode=0o600
        )
        target = DeployTarget(host="srv01")
        executor = MagicMock(spec=CommandExecutor)
        executor.run.side_effect = [_result(True), _result(True)]
        deployer = ConfigDeployer()

        # Act
        result = deployer.deploy(spec, target, executor)

        # Assert
        assert result is True
        tee_call = executor.run.call_args_list[0]
        assert tee_call.args[0] == ["tee", str(dest_path)]
        assert 'a = 1' in tee_call.kwargs["stdin"]
        chmod_call = executor.run.call_args_list[1]
        assert chmod_call.args[0] == ["chmod", "600", str(dest_path)]

    def test_deploy_remote_echec_tee_retourne_false(self) -> None:
        """Cas d'erreur distant : échec de tee -> False."""
        spec = ConfigDeploySpec(
            data={"a": 1}, dest_path=Path("/etc/app/config.toml")
        )
        target = DeployTarget(host="srv01")
        executor = MagicMock(spec=CommandExecutor)
        executor.run.return_value = _result(False, stderr="no space left")
        deployer = ConfigDeployer()

        result = deployer.deploy(spec, target, executor)

        assert result is False

    def test_deploy_remote_echec_chmod_retourne_false(self) -> None:
        """Cas d'erreur distant : tee ok mais chmod échoue -> False."""
        spec = ConfigDeploySpec(
            data={"a": 1}, dest_path=Path("/etc/app/config.toml")
        )
        target = DeployTarget(host="srv01")
        executor = MagicMock(spec=CommandExecutor)
        executor.run.side_effect = [
            _result(True),
            _result(False, stderr="not permitted"),
        ]
        deployer = ConfigDeployer()

        result = deployer.deploy(spec, target, executor)

        assert result is False


class TestConfigDeployerAvecLogger:
    """Tests avec logger injecté (ne doit jamais planter)."""

    def test_deploy_avec_logger_ne_leve_pas(self, tmp_path: Path) -> None:
        """Un logger injecté à la construction n'entraîne aucune
        exception, que la config soit utilisée ou non en interne."""
        dest_path = tmp_path / "config.toml"
        spec = ConfigDeploySpec(data={"a": 1}, dest_path=dest_path)
        logger = MagicMock()
        deployer = ConfigDeployer(logger=logger)

        result = deployer.deploy(
            spec, DeployTarget(), MagicMock(spec=CommandExecutor)
        )

        assert result is True

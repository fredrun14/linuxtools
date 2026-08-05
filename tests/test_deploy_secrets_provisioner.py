"""Tests pour le module deploy.secrets_provisioner.

Attention particulière (CDC Q-01, OWASP A02/A09) : aucune valeur de
secret ne doit jamais transiter par le logger, y compris en cas
d'échec partiel. Chaque test qui touche au logger vérifie
explicitement l'absence des valeurs résolues dans les arguments des
appels mockés.
"""

import os
from pathlib import Path
from unittest.mock import MagicMock, call

import pytest

from linuxtools.commands.base import CommandExecutor, CommandResult
from linuxtools.credentials.exceptions import CredentialNotFoundError
from linuxtools.credentials.manager import CredentialManager
from linuxtools.deploy.models import DeployTarget, SecretsSpec
from linuxtools.deploy.secrets_provisioner import SecretsProvisioner


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


def _assert_no_secret_leaked(logger: MagicMock, *secret_values: str) -> None:
    """Vérifie qu'aucune valeur secrète n'apparaît dans les appels
    du logger mocké (arguments positionnels et nommés confondus)."""
    for mock_call in logger.mock_calls:
        rendered = str(mock_call)
        for value in secret_values:
            assert value not in rendered, (
                f"Valeur secrète {value!r} trouvée dans un appel "
                f"logger : {rendered}"
            )


class TestSecretsProvisionerProvisionLocal:
    """Tests du provisioning local (écriture directe TOCTOU-safe)."""

    def test_provision_local_nominal_ecrit_env_file(
        self, tmp_path: Path
    ) -> None:
        """Cas nominal : toutes les clés résolues, fichier KEY=value
        déposé avec le mode attendu, aucun secret loggué."""
        # Arrange
        dest_path = tmp_path / "secrets.env"
        secret_values = {"GOTIFY_TOKEN": "tok-abc123", "API_KEY": "key-xyz"}
        credentials = MagicMock(spec=CredentialManager)
        credentials.require.side_effect = lambda key: secret_values[key]
        spec = SecretsSpec(
            service="pihole",
            keys=("GOTIFY_TOKEN", "API_KEY"),
            dest_path=dest_path,
            mode=0o600,
        )
        logger = MagicMock()
        provisioner = SecretsProvisioner(credentials, logger)

        # Act
        result = provisioner.provision(
            spec, DeployTarget(), MagicMock(spec=CommandExecutor)
        )

        # Assert
        assert result is True
        assert dest_path.read_text(encoding="utf-8") == (
            "GOTIFY_TOKEN=tok-abc123\nAPI_KEY=key-xyz\n"
        )
        assert oct(os.stat(dest_path).st_mode)[-3:] == "600"
        assert credentials.require.call_args_list == [
            call("GOTIFY_TOKEN"),
            call("API_KEY"),
        ]
        _assert_no_secret_leaked(logger, *secret_values.values())

    def test_provision_local_aucune_cle_ecrit_fichier_vide(
        self, tmp_path: Path
    ) -> None:
        """Cas limite : keys=() -> fichier vide, mais dépôt réussi."""
        dest_path = tmp_path / "secrets.env"
        credentials = MagicMock(spec=CredentialManager)
        spec = SecretsSpec(
            service="svc", keys=(), dest_path=dest_path
        )
        provisioner = SecretsProvisioner(credentials)

        result = provisioner.provision(
            spec, DeployTarget(), MagicMock(spec=CommandExecutor)
        )

        assert result is True
        assert dest_path.read_text(encoding="utf-8") == ""
        credentials.require.assert_not_called()

    def test_provision_local_credential_introuvable_abandonne_sans_depot(
        self, tmp_path: Path
    ) -> None:
        """Cas d'erreur : une clé introuvable abandonne sans dépôt
        partiel — même les clés déjà résolues ne sont pas écrites."""
        # Arrange
        dest_path = tmp_path / "secrets.env"
        credentials = MagicMock(spec=CredentialManager)
        credentials.require.side_effect = [
            "tok-abc123",
            CredentialNotFoundError("absent du keyring"),
        ]
        spec = SecretsSpec(
            service="pihole",
            keys=("GOTIFY_TOKEN", "MISSING_KEY"),
            dest_path=dest_path,
        )
        logger = MagicMock()
        provisioner = SecretsProvisioner(credentials, logger)

        # Act
        result = provisioner.provision(
            spec, DeployTarget(), MagicMock(spec=CommandExecutor)
        )

        # Assert
        assert result is False
        assert not dest_path.exists()
        logger.log_error.assert_called_once()
        error_message = logger.log_error.call_args.args[0]
        assert "MISSING_KEY" in error_message
        _assert_no_secret_leaked(logger, "tok-abc123")

    def test_provision_local_valeur_avec_saut_de_ligne_refusee(
        self, tmp_path: Path
    ) -> None:
        """Cas d'erreur : une valeur contenant '\\n' est refusée sans
        dépôt, et n'apparaît jamais dans le message de log."""
        dest_path = tmp_path / "secrets.env"
        malicious_value = "ligne1\nEVIL=injected"
        credentials = MagicMock(spec=CredentialManager)
        credentials.require.return_value = malicious_value
        spec = SecretsSpec(
            service="svc", keys=("PAYLOAD",), dest_path=dest_path
        )
        logger = MagicMock()
        provisioner = SecretsProvisioner(credentials, logger)

        result = provisioner.provision(
            spec, DeployTarget(), MagicMock(spec=CommandExecutor)
        )

        assert result is False
        assert not dest_path.exists()
        logger.log_error.assert_called_once()
        error_message = logger.log_error.call_args.args[0]
        assert "PAYLOAD" in error_message
        _assert_no_secret_leaked(logger, malicious_value)

    def test_provision_local_sans_logger_ne_leve_pas(
        self, tmp_path: Path
    ) -> None:
        """Cas limite : logger=None, échec silencieux sans exception."""
        dest_path = tmp_path / "secrets.env"
        credentials = MagicMock(spec=CredentialManager)
        credentials.require.side_effect = CredentialNotFoundError("x")
        spec = SecretsSpec(
            service="svc", keys=("K",), dest_path=dest_path
        )
        provisioner = SecretsProvisioner(credentials)

        result = provisioner.provision(
            spec, DeployTarget(), MagicMock(spec=CommandExecutor)
        )

        assert result is False
        assert not dest_path.exists()


class TestSecretsProvisionerProvisionRemote:
    """Tests du provisioning distant (executor.run tee + chmod)."""

    def test_provision_remote_nominal_deposit_via_executor(self) -> None:
        """Cas nominal distant : le contenu KEY=value est envoyé en
        stdin, jamais en argument de commande (pas d'exposition via
        ps)."""
        # Arrange
        dest_path = Path("/etc/app/secrets.env")
        credentials = MagicMock(spec=CredentialManager)
        credentials.require.return_value = "s3cr3t-val"
        spec = SecretsSpec(
            service="svc", keys=("TOKEN",), dest_path=dest_path
        )
        executor = MagicMock(spec=CommandExecutor)
        executor.run.side_effect = [_result(True), _result(True)]
        logger = MagicMock()
        provisioner = SecretsProvisioner(credentials, logger)

        # Act
        result = provisioner.provision(
            spec, DeployTarget(host="srv01"), executor
        )

        # Assert
        assert result is True
        tee_call = executor.run.call_args_list[0]
        assert tee_call.args[0] == ["tee", str(dest_path)]
        assert tee_call.kwargs["stdin"] == "TOKEN=s3cr3t-val\n"
        chmod_call = executor.run.call_args_list[1]
        assert chmod_call.args[0] == ["chmod", "600", str(dest_path)]
        # Le secret n'apparaît jamais dans les logs (mais transite
        # légitimement par executor.run — non concerné par l'assertion).
        _assert_no_secret_leaked(logger, "s3cr3t-val")

    def test_provision_remote_echec_depot_retourne_false(self) -> None:
        """Cas d'erreur distant : échec de tee -> False, secret absent
        du message d'erreur (stderr générique de la commande)."""
        dest_path = Path("/etc/app/secrets.env")
        credentials = MagicMock(spec=CredentialManager)
        credentials.require.return_value = "s3cr3t-val"
        spec = SecretsSpec(
            service="svc", keys=("TOKEN",), dest_path=dest_path
        )
        executor = MagicMock(spec=CommandExecutor)
        executor.run.return_value = _result(False, stderr="disk full")
        logger = MagicMock()
        provisioner = SecretsProvisioner(credentials, logger)

        result = provisioner.provision(
            spec, DeployTarget(host="srv01"), executor
        )

        assert result is False
        logger.log_error.assert_called_once()
        _assert_no_secret_leaked(logger, "s3cr3t-val")

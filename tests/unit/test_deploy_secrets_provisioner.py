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
from linuxtools.deploy.models import DeployTarget, PhaseOutcome, SecretsSpec
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


def _result_code(code: int) -> CommandResult:
    """CommandResult avec un code de retour précis."""
    return CommandResult(
        command=(),
        return_code=code,
        stdout="",
        stderr="",
        success=code == 0,
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
            keys=(("pihole", "GOTIFY_TOKEN"), ("pihole", "API_KEY")),
            dest_path=dest_path,
            mode=0o600,
        )
        logger = MagicMock()
        provisioner = SecretsProvisioner(lambda service: credentials, logger)

        # Act
        result = provisioner.provision(
            spec, DeployTarget(), MagicMock(spec=CommandExecutor)
        )

        # Assert
        assert result.success is True
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
        spec = SecretsSpec(keys=(), dest_path=dest_path)
        provisioner = SecretsProvisioner(lambda service: credentials)

        result = provisioner.provision(
            spec, DeployTarget(), MagicMock(spec=CommandExecutor)
        )

        assert result.success is True
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
            keys=(("pihole", "GOTIFY_TOKEN"), ("pihole", "MISSING_KEY")),
            dest_path=dest_path,
        )
        logger = MagicMock()
        provisioner = SecretsProvisioner(lambda service: credentials, logger)

        # Act
        result = provisioner.provision(
            spec, DeployTarget(), MagicMock(spec=CommandExecutor)
        )

        # Assert
        assert result.success is False
        assert not dest_path.exists()
        logger.log_error.assert_called_once()
        error_message = logger.log_error.call_args.args[0]
        assert "pihole/MISSING_KEY" in error_message
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
        spec = SecretsSpec(keys=(("svc", "PAYLOAD"),), dest_path=dest_path)
        logger = MagicMock()
        provisioner = SecretsProvisioner(lambda service: credentials, logger)

        result = provisioner.provision(
            spec, DeployTarget(), MagicMock(spec=CommandExecutor)
        )

        assert result.success is False
        assert not dest_path.exists()
        logger.log_error.assert_called_once()
        error_message = logger.log_error.call_args.args[0]
        assert "svc/PAYLOAD" in error_message
        _assert_no_secret_leaked(logger, malicious_value)

    def test_provision_local_sans_logger_ne_leve_pas(
        self, tmp_path: Path
    ) -> None:
        """Cas limite : logger=None, échec silencieux sans exception."""
        dest_path = tmp_path / "secrets.env"
        credentials = MagicMock(spec=CredentialManager)
        credentials.require.side_effect = CredentialNotFoundError("x")
        spec = SecretsSpec(keys=(("svc", "K"),), dest_path=dest_path)
        provisioner = SecretsProvisioner(lambda service: credentials)

        result = provisioner.provision(
            spec, DeployTarget(), MagicMock(spec=CommandExecutor)
        )

        assert result.success is False
        assert not dest_path.exists()


class TestSecretsProvisionerMultiServices:
    """Tests du provisioning multi-services (résolution par service,
    cache de la factory) — cf. CDC F-03."""

    def test_provision_local_deux_services_resout_via_le_bon_manager(
        self, tmp_path: Path
    ) -> None:
        """Deux services distincts : chaque clé est résolue via le
        manager de son propre service, sans fuite croisée."""
        # Arrange
        dest_path = tmp_path / "secrets.env"
        pihole_manager = MagicMock(spec=CredentialManager)
        pihole_manager.require.side_effect = lambda key: {
            "APP_PASSWORD": "pw-pihole"
        }[key]
        gotify_manager = MagicMock(spec=CredentialManager)
        gotify_manager.require.side_effect = lambda key: {
            "GOTIFY_TOKEN": "tok-gotify"
        }[key]
        managers = {"pihole": pihole_manager, "gotify": gotify_manager}
        spec = SecretsSpec(
            keys=(
                ("pihole", "APP_PASSWORD"),
                ("gotify", "GOTIFY_TOKEN"),
            ),
            dest_path=dest_path,
        )
        provisioner = SecretsProvisioner(lambda service: managers[service])

        # Act
        result = provisioner.provision(
            spec, DeployTarget(), MagicMock(spec=CommandExecutor)
        )

        # Assert
        assert result.success is True
        content = dest_path.read_text(encoding="utf-8")
        assert "APP_PASSWORD=pw-pihole" in content
        assert "GOTIFY_TOKEN=tok-gotify" in content
        pihole_manager.require.assert_called_once_with("APP_PASSWORD")
        gotify_manager.require.assert_called_once_with("GOTIFY_TOKEN")

    def test_provision_local_meme_service_reutilise_le_manager_deja_construit(
        self, tmp_path: Path
    ) -> None:
        """Deux clés du même service : la factory n'est appelée
        qu'une seule fois (cache local à provision())."""
        # Arrange
        dest_path = tmp_path / "secrets.env"
        credentials = MagicMock(spec=CredentialManager)
        credentials.require.side_effect = lambda key: {"A": "va", "B": "vb"}[
            key
        ]
        factory = MagicMock(side_effect=lambda service: credentials)
        spec = SecretsSpec(
            keys=(("pihole", "A"), ("pihole", "B")),
            dest_path=dest_path,
        )
        provisioner = SecretsProvisioner(factory)

        # Act
        result = provisioner.provision(
            spec, DeployTarget(), MagicMock(spec=CommandExecutor)
        )

        # Assert
        assert result.success is True
        assert factory.call_count == 1

    def test_provision_local_echec_reproduit_le_cas_pihole_schedule(
        self, tmp_path: Path
    ) -> None:
        """Cas concret ayant motivé le CDC : 2 clés pihole résolues,
        1 clé gotify introuvable -> échec sans dépôt partiel, message
        nommant service+clé."""
        # Arrange
        dest_path = tmp_path / "secrets.env"
        pihole_manager = MagicMock(spec=CredentialManager)
        pihole_manager.require.side_effect = lambda key: {
            "PIHOLE_CT100_APP_PASSWORD": "pw-ct100",
            "PIHOLE_RPI3_APP_PASSWORD": "pw-rpi3",
        }[key]
        gotify_manager = MagicMock(spec=CredentialManager)
        gotify_manager.require.side_effect = CredentialNotFoundError(
            "absent du keyring"
        )
        managers = {"pihole": pihole_manager, "gotify": gotify_manager}
        spec = SecretsSpec(
            keys=(
                ("pihole", "PIHOLE_CT100_APP_PASSWORD"),
                ("pihole", "PIHOLE_RPI3_APP_PASSWORD"),
                ("gotify", "GOTIFY_PIHOLE_SCHEDULE_TOKEN"),
            ),
            dest_path=dest_path,
        )
        logger = MagicMock()
        provisioner = SecretsProvisioner(
            lambda service: managers[service], logger
        )

        # Act
        result = provisioner.provision(
            spec, DeployTarget(), MagicMock(spec=CommandExecutor)
        )

        # Assert
        assert result.success is False
        assert not dest_path.exists()
        logger.log_error.assert_called_once()
        error_message = logger.log_error.call_args.args[0]
        assert "gotify/GOTIFY_PIHOLE_SCHEDULE_TOKEN" in error_message
        _assert_no_secret_leaked(logger, "pw-ct100", "pw-rpi3")


class TestSecretsProvisionerProvisionRemote:
    """Tests du provisioning distant (executor.run install -m -T)."""

    def test_provision_remote_nominal_deposit_via_executor(self) -> None:
        """Cas nominal distant : le contenu KEY=value est envoyé en
        stdin, jamais en argument de commande (pas d'exposition via
        ps). `-m` vaut `600` : c'est ce qui prouve que le secret
        n'est plus exposé par une fenêtre de permissions permissive."""
        # Arrange
        dest_path = Path("/etc/app/secrets.env")
        credentials = MagicMock(spec=CredentialManager)
        credentials.require.return_value = "s3cr3t-val"
        spec = SecretsSpec(keys=(("svc", "TOKEN"),), dest_path=dest_path)
        executor = MagicMock(spec=CommandExecutor)
        executor.run.side_effect = [_result(True), _result(True)]
        logger = MagicMock()
        provisioner = SecretsProvisioner(lambda service: credentials, logger)

        # Act
        result = provisioner.provision(
            spec, DeployTarget(host="srv01"), executor
        )

        # Assert
        assert result.success is True
        install_call = executor.run.call_args_list[1]
        assert install_call.args[0] == [
            "install",
            "-m",
            "600",
            "-T",
            "/dev/stdin",
            str(dest_path),
        ]
        assert install_call.kwargs["stdin"] == "TOKEN=s3cr3t-val\n"
        # Le secret n'apparaît jamais dans les logs (mais transite
        # légitimement par executor.run — non concerné par l'assertion).
        _assert_no_secret_leaked(logger, "s3cr3t-val")

    def test_provision_remote_echec_depot_retourne_false(self) -> None:
        """Cas d'erreur distant : échec d'`install` -> False, secret
        absent du message d'erreur (stderr générique de la commande)."""
        dest_path = Path("/etc/app/secrets.env")
        credentials = MagicMock(spec=CredentialManager)
        credentials.require.return_value = "s3cr3t-val"
        spec = SecretsSpec(keys=(("svc", "TOKEN"),), dest_path=dest_path)
        executor = MagicMock(spec=CommandExecutor)
        executor.run.return_value = _result(False, stderr="disk full")
        logger = MagicMock()
        provisioner = SecretsProvisioner(lambda service: credentials, logger)

        result = provisioner.provision(
            spec, DeployTarget(host="srv01"), executor
        )

        assert result.success is False
        logger.log_error.assert_called_once()
        _assert_no_secret_leaked(logger, "s3cr3t-val")


_SENTINELLE = "SENTINELLE-secret-poste-source-9f3a"


def _factory_piegee(service: str) -> CredentialManager:
    """Factory qui échoue si le mode « target » la sollicite."""
    raise AssertionError(f"factory appelée pour {service!r}")


class TestSecretsProvisionerModeTarget:
    """Mode ``values_from="target"`` : squelette sans valeur."""

    def test_provision_target_ne_lit_aucune_valeur_sentinelle(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """F-05 : aucune valeur du poste source ne fuit (env, .env)."""
        # Arrange : sentinelle dans l'environnement et dans un .env
        monkeypatch.setenv("GOTIFY_TOKEN", _SENTINELLE)
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".env").write_text(
            f"GOTIFY_TOKEN={_SENTINELLE}\n", encoding="utf-8"
        )
        dest_local = tmp_path / "cible" / "secrets.env"
        dest_local.parent.mkdir()
        spec = SecretsSpec(
            keys=(("bpm", "GOTIFY_TOKEN"),),
            dest_path=dest_local,
            values_from="target",
        )
        logger = MagicMock()
        provisioner = SecretsProvisioner(_factory_piegee, logger)
        executor_distant = MagicMock(spec=CommandExecutor)
        executor_distant.run.side_effect = [
            _result_code(1),
            _result(True),
            _result(True),
            _result(True),
            _result(True),
        ]

        # Act
        local = provisioner.provision(
            spec, DeployTarget(), MagicMock(spec=CommandExecutor)
        )
        distant = provisioner.provision(
            spec, DeployTarget(host="srv"), executor_distant
        )

        # Assert
        assert local.success is True
        assert distant.success is True
        rendu = (
            dest_local.read_text(encoding="utf-8")
            + str(local.messages)
            + str(distant.messages)
            + str(logger.mock_calls)
            + str(executor_distant.run.mock_calls)
        )
        assert _SENTINELLE not in rendu

    def test_provision_target_cree_squelette_0600_sans_valeur(
        self, tmp_path: Path
    ) -> None:
        """A-07 : CLE= par clé dédoublonnée, mode 0600, sans valeur."""
        dest = tmp_path / "secrets.env"
        spec = SecretsSpec(
            keys=(("a", "TOKEN"), ("b", "TOKEN"), ("a", "PASS")),
            dest_path=dest,
            values_from="target",
        )

        outcome = SecretsProvisioner().provision(
            spec, DeployTarget(), MagicMock(spec=CommandExecutor)
        )

        assert outcome.success is True
        lignes = dest.read_text(encoding="utf-8").splitlines()
        assert [ligne for ligne in lignes if not ligne.startswith("#")] == [
            "TOKEN=",
            "PASS=",
        ]
        assert oct(os.stat(dest).st_mode)[-3:] == "600"

    def test_provision_target_fichier_existant_non_modifie(
        self, tmp_path: Path
    ) -> None:
        """F-07 / A-06 : contenu, mode et mtime intacts."""
        dest = tmp_path / "secrets.env"
        dest.write_text("TOKEN=reel\n", encoding="utf-8")
        os.chmod(dest, 0o640)
        os.utime(dest, (1_000_000, 1_000_000))
        spec = SecretsSpec(
            keys=(("a", "TOKEN"),), dest_path=dest, values_from="target"
        )

        outcome = SecretsProvisioner().provision(
            spec, DeployTarget(), MagicMock(spec=CommandExecutor)
        )

        assert outcome.success is True
        assert "déjà présent" in outcome.messages[0]
        assert dest.read_text(encoding="utf-8") == "TOKEN=reel\n"
        assert oct(os.stat(dest).st_mode)[-3:] == "640"
        assert os.stat(dest).st_mtime == 1_000_000

    def test_provision_target_message_liste_les_cles_sans_valeur(
        self, tmp_path: Path
    ) -> None:
        """Le message de création cite chemin, mode et noms de clés."""
        dest = tmp_path / "secrets.env"
        spec = SecretsSpec(
            keys=(("a", "TOKEN"), ("a", "PASS")),
            dest_path=dest,
            values_from="target",
        )

        outcome = SecretsProvisioner().provision(
            spec, DeployTarget(), MagicMock(spec=CommandExecutor)
        )

        assert outcome.messages == (
            f"Fichier de secrets créé (0600) : {dest} — valeurs à "
            "renseigner sur ce poste : TOKEN, PASS",
        )

    def test_provision_target_echec_ecriture_retourne_echec(self) -> None:
        """Écriture distante refusée -> PhaseOutcome(False) + log."""
        spec = SecretsSpec(
            keys=(("a", "TOKEN"),),
            dest_path=Path("/etc/app/secrets.env"),
            values_from="target",
        )
        executor = MagicMock(spec=CommandExecutor)
        executor.run.return_value = _result_code(255)
        logger = MagicMock()

        outcome = SecretsProvisioner(None, logger).provision(
            spec, DeployTarget(host="srv"), executor
        )

        assert outcome.success is False
        logger.log_error.assert_called_once()


class TestSecretsProvisionerSansFactory:
    """Mode « source » sans factory : échec fermé."""

    def test_provision_source_sans_factory_echoue_ferme(
        self, tmp_path: Path
    ) -> None:
        """Pas de factory -> échec, rien n'est écrit, erreur loguée."""
        dest = tmp_path / "secrets.env"
        spec = SecretsSpec(keys=(("a", "TOKEN"),), dest_path=dest)
        logger = MagicMock()

        outcome = SecretsProvisioner(None, logger).provision(
            spec, DeployTarget(), MagicMock(spec=CommandExecutor)
        )

        assert outcome == PhaseOutcome(False)
        assert not dest.exists()
        logger.log_error.assert_called_once()

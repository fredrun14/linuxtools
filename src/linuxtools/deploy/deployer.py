"""Orchestrateur du déploiement : point d'entrée API principal.

Deployer enchaîne les 4 phases (transport → backup → install →
verify) et déclenche un rollback automatique si l'installation ou
la vérification échoue et qu'un backup est disponible. C'est le
seul composant du module qui connaît l'ordre des phases — chaque
phase elle-même est déléguée à un collaborateur injecté (Transport,
VenvInstaller, InstallVerifier).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from linuxtools.cli.dry_run import DryRunContext
from linuxtools.commands.runner import LinuxCommandExecutor
from linuxtools.deploy.config_deployer import ConfigDeployer
from linuxtools.deploy.discovery import find_project_source
from linuxtools.deploy.exceptions import DeployError
from linuxtools.deploy.models import (
    DeployConfig,
    DeployPhase,
    DeployReport,
    DeployTarget,
)
from linuxtools.deploy.secrets_provisioner import SecretsProvisioner
from linuxtools.deploy.ssh_executor import SshCommandExecutor
from linuxtools.deploy.timer_deployer import TimerDeployer
from linuxtools.deploy.transport import RsyncTransport, Transport
from linuxtools.deploy.venv_installer import VenvInstaller
from linuxtools.deploy.verifier import InstallVerifier

if TYPE_CHECKING:
    from pathlib import Path

    from linuxtools.commands.base import CommandExecutor
    from linuxtools.credentials.manager import CredentialManager
    from linuxtools.deploy.models import CheckResult
    from linuxtools.logging.base import Logger


class Deployer:
    """Orchestre transport → install → vérif → rollback.

    Attributes:
        _transport: Acheminement du source.
        _installer: VenvInstaller (backup/install/restore).
        _verifier: InstallVerifier.
        _logger: Logger optionnel.
        _dry_run: Si True, simule sans effet de bord (F-11).
        _config_deployer: ConfigDeployer optionnel (phase CONFIG).
        _secrets_provisioner: SecretsProvisioner optionnel (phase
            SECRETS).
        _timer_deployer: TimerDeployer optionnel (phase TIMER).
        _target_executor: CommandExecutor ciblant l'hôte, requis par
            les 3 phases ci-dessus.
    """

    def __init__(
        self,
        transport: Transport,
        installer: VenvInstaller,
        verifier: InstallVerifier,
        logger: Logger | None = None,
        dry_run: bool = False,
        config_deployer: ConfigDeployer | None = None,
        secrets_provisioner: SecretsProvisioner | None = None,
        timer_deployer: TimerDeployer | None = None,
        target_executor: CommandExecutor | None = None,
    ) -> None:
        """Initialise l'orchestrateur avec ses collaborateurs.

        Args:
            transport: Acheminement du source vers la cible.
            installer: Gestion backup/install/restore du venv.
            verifier: Vérifications post-install déclaratives.
            logger: Logger optionnel.
            dry_run: Si True, simule le déploiement sans effet de
                bord.
            config_deployer: Déployeur de config TOML optionnel. Si
                None, la phase CONFIG échoue proprement si
                `config.config_deploy` est renseigné.
            secrets_provisioner: Provisionneur de secrets optionnel.
                Si None, la phase SECRETS échoue proprement si
                `config.secrets` est renseigné.
            timer_deployer: Déployeur de service+timer optionnel. Si
                None, la phase TIMER échoue proprement si
                `config.timer_deploy` est renseigné.
            target_executor: Exécuteur de commandes ciblant l'hôte,
                requis par les 3 phases ci-dessus (même objet que
                celui injecté dans `installer`/`verifier`). Si None
                et qu'une de ces phases est configurée, elle échoue
                proprement plutôt que de lever une AttributeError.
        """
        self._transport = transport
        self._installer = installer
        self._verifier = verifier
        self._logger = logger
        self._dry_run = dry_run
        self._config_deployer = config_deployer
        self._secrets_provisioner = secrets_provisioner
        self._timer_deployer = timer_deployer
        self._target_executor = target_executor

    def _log(self, message: str) -> None:
        """Envoie un message d'information au logger si disponible."""
        if self._logger:
            self._logger.log_info(message)

    @staticmethod
    def _destination_label(config: DeployConfig) -> str:
        """Décrit la destination du transport pour les logs/dry-run.

        Args:
            config: Configuration du déploiement.

        Returns:
            Libellé lisible de la destination (locale ou distante).
        """
        if config.target.is_remote:
            dest = config.target.ssh_destination
            return f"{dest}:{config.remote_source_dir}"
        return str(config.remote_source_dir)

    def _resolve_source_dir(
        self, config: DeployConfig
    ) -> tuple[Path | None, str | None]:
        """Résout le répertoire source, avec auto-détection (V1).

        Valide l'existence du répertoire dans les deux cas
        (explicite ou auto-détecté) : un source_dir explicite
        inexistant ne doit jamais laisser `transfer()` lever
        FileNotFoundError, mais produire un échec de rapport normal.

        Args:
            config: Configuration du déploiement.

        Returns:
            Tuple (source_dir, message) : si source_dir est None,
            message contient la raison de l'échec.
        """
        if config.source_dir is not None:
            source_dir = config.source_dir
            if not source_dir.is_dir():
                return None, f"source_dir inexistant : {source_dir}"
            return source_dir, None

        detected = find_project_source()
        if detected is None:
            return None, (
                "source_dir introuvable : aucun pyproject.toml "
                "en remontant depuis le cwd"
            )
        if not detected.is_dir():
            return None, f"source_dir inexistant : {detected}"

        self._log(f"Source auto-détecté : {detected}")
        return detected, f"Source auto-détecté : {detected}"

    def _deploy_dry_run(
        self,
        config: DeployConfig,
        source_dir: Path,
        messages: tuple[str, ...],
    ) -> DeployReport:
        """Simule un déploiement complet sans effet de bord.

        Args:
            config: Configuration du déploiement.
            source_dir: Répertoire source résolu.
            messages: Messages déjà accumulés (ex. auto-détection).

        Returns:
            DeployReport de simulation, toujours en succès.
        """
        ctx = DryRunContext(dry_run=True)
        ctx.would_run_command(
            f"rsync {source_dir}/ -> {self._destination_label(config)}"
        )
        ctx.would_run_command(
            f"backup du venv {config.venv_path}"
        )
        if config.recreate_venv:
            ctx.would_run_command(f"rm -rf {config.venv_path}")
            ctx.would_run_command(
                f"python3 -m venv {config.venv_path}"
            )
        ctx.would_run_command(
            f"{config.venv_path}/bin/pip install --force-reinstall "
            f"{config.remote_source_dir}"
        )
        ctx.would_run_command(
            "vérifications post-install (imports, sous-commandes, "
            "non-régression)"
        )
        if config.config_deploy is not None:
            ctx.would_run_command(
                f"dépôt config -> {config.config_deploy.dest_path}"
            )
        if config.secrets is not None:
            ctx.would_run_command(
                f"provisioning secrets -> {config.secrets.dest_path}"
            )
        if config.timer_deploy is not None:
            ctx.would_run_command(
                "installation service+timer "
                f"{config.timer_deploy.unit_name}"
            )
        return DeployReport(
            success=True,
            phase_reached=DeployPhase.DONE,
            messages=messages + ("Dry-run : aucune action réelle.",),
        )

    def _rollback_if_possible(
        self, config: DeployConfig, backup_path: Path | None
    ) -> bool:
        """Restaure le backup si disponible.

        Args:
            config: Configuration du déploiement.
            backup_path: Chemin du backup, ou None si aucun.

        Returns:
            True si un rollback a été effectué avec succès.
        """
        if backup_path is None:
            return False
        return self._installer.restore_venv(
            config.venv_path, backup_path
        )

    @staticmethod
    def _rollback_failure_messages(
        backup_path: Path | None, rolled_back: bool
    ) -> tuple[str, ...]:
        """Message d'alerte si un rollback attendu a échoué.

        Un rapport honnête ne doit jamais taire un rollback tenté et
        raté : le backup reste alors sur disque mais le venv en
        place peut être dans un état non fonctionnel.

        Args:
            backup_path: Chemin du backup, ou None si aucun
                rollback n'a été tenté.
            rolled_back: True si le rollback a réussi.

        Returns:
            Tuple à un élément avec le message d'alerte si un
            rollback a été tenté (backup_path non None) et a
            échoué, tuple vide sinon.
        """
        if backup_path is not None and not rolled_back:
            return (
                "⚠ Rollback ÉCHOUÉ — venv laissé en l'état, "
                f"backup conservé : {backup_path}",
            )
        return ()

    def _run_config_phase(
        self,
        config: DeployConfig,
        checks: tuple[CheckResult, ...],
        messages: tuple[str, ...],
    ) -> DeployReport | None:
        """Exécute la phase de dépôt de config, si configurée.

        Args:
            config: Configuration du déploiement.
            checks: Résultats de vérification déjà accumulés.
            messages: Messages déjà accumulés.

        Returns:
            None si la phase a réussi (continuer), sinon un
            DeployReport d'échec prêt à renvoyer tel quel.
        """
        if self._target_executor is None:
            return DeployReport(
                success=False,
                phase_reached=DeployPhase.CONFIG,
                checks=checks,
                messages=messages + (
                    "target_executor non configuré alors que "
                    "config.config_deploy est renseigné.",
                ),
            )
        if self._config_deployer is None:
            return DeployReport(
                success=False,
                phase_reached=DeployPhase.CONFIG,
                checks=checks,
                messages=messages + (
                    "ConfigDeployer non configuré alors que "
                    "config.config_deploy est renseigné.",
                ),
            )
        assert config.config_deploy is not None
        ok = self._config_deployer.deploy(
            config.config_deploy, config.target, self._target_executor
        )
        if not ok:
            return DeployReport(
                success=False,
                phase_reached=DeployPhase.CONFIG,
                checks=checks,
                messages=messages + ("Dépôt de la config échoué.",),
            )
        return None

    def _run_secrets_phase(
        self,
        config: DeployConfig,
        checks: tuple[CheckResult, ...],
        messages: tuple[str, ...],
    ) -> DeployReport | None:
        """Exécute la phase de provisioning de secrets, si configurée.

        Args:
            config: Configuration du déploiement.
            checks: Résultats de vérification déjà accumulés.
            messages: Messages déjà accumulés.

        Returns:
            None si la phase a réussi (continuer), sinon un
            DeployReport d'échec prêt à renvoyer tel quel.
        """
        if self._target_executor is None:
            return DeployReport(
                success=False,
                phase_reached=DeployPhase.SECRETS,
                checks=checks,
                messages=messages + (
                    "target_executor non configuré alors que "
                    "config.secrets est renseigné.",
                ),
            )
        if self._secrets_provisioner is None:
            return DeployReport(
                success=False,
                phase_reached=DeployPhase.SECRETS,
                checks=checks,
                messages=messages + (
                    "SecretsProvisioner non configuré alors que "
                    "config.secrets est renseigné.",
                ),
            )
        assert config.secrets is not None
        ok = self._secrets_provisioner.provision(
            config.secrets, config.target, self._target_executor
        )
        if not ok:
            return DeployReport(
                success=False,
                phase_reached=DeployPhase.SECRETS,
                checks=checks,
                messages=messages + (
                    "Provisioning des secrets échoué.",
                ),
            )
        return None

    def _run_timer_phase(
        self,
        config: DeployConfig,
        checks: tuple[CheckResult, ...],
        messages: tuple[str, ...],
    ) -> DeployReport | None:
        """Exécute la phase d'installation du service+timer, si configurée.

        Args:
            config: Configuration du déploiement.
            checks: Résultats de vérification déjà accumulés.
            messages: Messages déjà accumulés.

        Returns:
            None si la phase a réussi (continuer), sinon un
            DeployReport d'échec prêt à renvoyer tel quel.
        """
        if self._target_executor is None:
            return DeployReport(
                success=False,
                phase_reached=DeployPhase.TIMER,
                checks=checks,
                messages=messages + (
                    "target_executor non configuré alors que "
                    "config.timer_deploy est renseigné.",
                ),
            )
        if self._timer_deployer is None:
            return DeployReport(
                success=False,
                phase_reached=DeployPhase.TIMER,
                checks=checks,
                messages=messages + (
                    "TimerDeployer non configuré alors que "
                    "config.timer_deploy est renseigné.",
                ),
            )
        assert config.timer_deploy is not None
        ok = self._timer_deployer.deploy(
            config.timer_deploy, config.target, self._target_executor
        )
        if not ok:
            return DeployReport(
                success=False,
                phase_reached=DeployPhase.TIMER,
                checks=checks,
                messages=messages + (
                    "Installation du service+timer échouée.",
                ),
            )
        return None

    def deploy(self, config: DeployConfig) -> DeployReport:
        """Exécute le déploiement complet selon config.

        Args:
            config: Configuration du déploiement/màj.

        Returns:
            Compte rendu complet, avec rollback automatique si
            l'installation ou la vérification échoue et qu'un
            backup était disponible.
        """
        source_dir, source_message = self._resolve_source_dir(config)
        if source_dir is None:
            return DeployReport(
                success=False,
                phase_reached=DeployPhase.TRANSPORT,
                messages=(source_message or "",),
            )
        messages: tuple[str, ...] = (
            (source_message,) if source_message else ()
        )

        if self._dry_run:
            return self._deploy_dry_run(config, source_dir, messages)

        transport_result = self._transport.transfer(
            source_dir, config.remote_source_dir, config.target
        )
        if not transport_result.success:
            return DeployReport(
                success=False,
                phase_reached=DeployPhase.TRANSPORT,
                messages=messages + (
                    f"Transport échoué : {transport_result.stderr}",
                ),
            )

        try:
            backup_path = self._installer.backup_venv(
                config.venv_path
            )
        except DeployError as exc:
            return DeployReport(
                success=False,
                phase_reached=DeployPhase.BACKUP,
                messages=messages + (str(exc),),
            )

        install_result = self._installer.install(
            config.venv_path,
            config.remote_source_dir,
            config.recreate_venv,
        )
        if not install_result.success:
            rolled_back = self._rollback_if_possible(
                config, backup_path
            )
            phase = (
                DeployPhase.ROLLBACK
                if rolled_back
                else DeployPhase.INSTALL
            )
            return DeployReport(
                success=False,
                phase_reached=phase,
                rolled_back=rolled_back,
                backup_path=backup_path,
                messages=messages + (
                    f"Installation échouée : {install_result.stderr}",
                ) + self._rollback_failure_messages(
                    backup_path, rolled_back
                ),
            )

        checks = tuple(
            self._verifier.verify(
                config.venv_path, config.verification, config.cli_bin
            )
        )
        if not all(check.ok for check in checks):
            rolled_back = self._rollback_if_possible(
                config, backup_path
            )
            phase = (
                DeployPhase.ROLLBACK
                if rolled_back
                else DeployPhase.VERIFY
            )
            return DeployReport(
                success=False,
                phase_reached=phase,
                checks=checks,
                rolled_back=rolled_back,
                backup_path=backup_path,
                messages=messages + (
                    "Vérification post-install échouée",
                ) + self._rollback_failure_messages(
                    backup_path, rolled_back
                ),
            )

        if config.config_deploy is not None:
            report = self._run_config_phase(config, checks, messages)
            if report is not None:
                return report
            messages = messages + ("Config déployée.",)

        if config.secrets is not None:
            report = self._run_secrets_phase(config, checks, messages)
            if report is not None:
                return report
            messages = messages + ("Secrets provisionnés.",)

        if config.timer_deploy is not None:
            report = self._run_timer_phase(config, checks, messages)
            if report is not None:
                return report
            messages = messages + ("Service+timer installés.",)

        if backup_path is not None:
            self._installer.prune_backup(backup_path)

        return DeployReport(
            success=True,
            phase_reached=DeployPhase.DONE,
            checks=checks,
            messages=messages,
        )

    @classmethod
    def for_target(
        cls,
        target: DeployTarget,
        logger: Logger | None = None,
        dry_run: bool = False,
        credential_manager: CredentialManager | None = None,
    ) -> Deployer:
        """Fabrique un Deployer complet pour une cible donnée.

        Construit les collaborateurs standards : LinuxCommandExecutor
        local, SshCommandExecutor si la cible est distante,
        RsyncTransport (toujours local), VenvInstaller et
        InstallVerifier ciblant l'hôte, ainsi que ConfigDeployer et
        TimerDeployer (toujours construits) et SecretsProvisioner
        (uniquement si `credential_manager` est fourni, pour ne pas
        forcer la dépendance optionnelle `credentials`).

        Args:
            target: Description de l'hôte cible (local ou distant).
            logger: Logger optionnel, propagé à tous les
                collaborateurs.
            dry_run: Si True, le Deployer simule sans effet de bord.
            credential_manager: CredentialManager optionnel pour la
                résolution des secrets. Si None, la phase SECRETS
                échoue proprement si elle est configurée.

        Returns:
            Deployer prêt à l'emploi pour target.
        """
        local_exec = LinuxCommandExecutor(logger=logger)
        target_exec: CommandExecutor = (
            SshCommandExecutor(target, local_exec, logger)
            if target.is_remote
            else local_exec
        )
        transport = RsyncTransport(local_exec, logger)
        installer = VenvInstaller(target_exec, logger)
        verifier = InstallVerifier(target_exec, logger)
        config_deployer = ConfigDeployer(logger)
        timer_deployer = TimerDeployer(logger)
        secrets_provisioner = (
            SecretsProvisioner(credential_manager, logger)
            if credential_manager is not None
            else None
        )
        return cls(
            transport,
            installer,
            verifier,
            logger,
            dry_run,
            config_deployer,
            secrets_provisioner,
            timer_deployer,
            target_exec,
        )

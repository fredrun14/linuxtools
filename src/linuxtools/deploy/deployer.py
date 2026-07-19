"""Orchestrateur du déploiement : point d'entrée API principal.

Deployer enchaîne les 4 phases (transport → backup → install →
verify) et déclenche un rollback automatique si l'installation ou
la vérification échoue et qu'un backup est disponible. C'est le
seul composant du module qui connaît l'ordre des phases — chaque
phase elle-même est déléguée à un collaborateur injecté (Transport,
VenvInstaller, InstallVerifier).
"""

from __future__ import annotations

from pathlib import Path

from linuxtools.cli.dry_run import DryRunContext
from linuxtools.commands.base import CommandExecutor
from linuxtools.commands.runner import LinuxCommandExecutor
from linuxtools.deploy.discovery import find_project_source
from linuxtools.deploy.exceptions import DeployError
from linuxtools.deploy.models import (
    DeployConfig,
    DeployPhase,
    DeployReport,
    DeployTarget,
)
from linuxtools.deploy.ssh_executor import SshCommandExecutor
from linuxtools.deploy.transport import RsyncTransport, Transport
from linuxtools.deploy.venv_installer import VenvInstaller
from linuxtools.deploy.verifier import InstallVerifier
from linuxtools.logging.base import Logger


class Deployer:
    """Orchestre transport → install → vérif → rollback.

    Attributes:
        _transport: Acheminement du source.
        _installer: VenvInstaller (backup/install/restore).
        _verifier: InstallVerifier.
        _logger: Logger optionnel.
        _dry_run: Si True, simule sans effet de bord (F-11).
    """

    def __init__(
        self,
        transport: Transport,
        installer: VenvInstaller,
        verifier: InstallVerifier,
        logger: Logger | None = None,
        dry_run: bool = False,
    ) -> None:
        """Initialise l'orchestrateur avec ses collaborateurs.

        Args:
            transport: Acheminement du source vers la cible.
            installer: Gestion backup/install/restore du venv.
            verifier: Vérifications post-install déclaratives.
            logger: Logger optionnel.
            dry_run: Si True, simule le déploiement sans effet de
                bord.
        """
        self._transport = transport
        self._installer = installer
        self._verifier = verifier
        self._logger = logger
        self._dry_run = dry_run

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

        Args:
            config: Configuration du déploiement.

        Returns:
            Tuple (source_dir, message) : si source_dir est None,
            message contient la raison de l'échec.
        """
        if config.source_dir is not None:
            return config.source_dir, None

        source_dir = find_project_source()
        if source_dir is None:
            return None, (
                "source_dir introuvable : aucun pyproject.toml "
                "en remontant depuis le cwd"
            )

        self._log(f"Source auto-détecté : {source_dir}")
        return source_dir, f"Source auto-détecté : {source_dir}"

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
        ctx.would_run_command(
            f"{config.venv_path}/bin/pip install --force-reinstall "
            f"{config.remote_source_dir}"
        )
        ctx.would_run_command(
            "vérifications post-install (imports, sous-commandes, "
            "non-régression)"
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
        messages = (source_message,) if source_message else ()

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
                ),
            )

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
    ) -> Deployer:
        """Fabrique un Deployer complet pour une cible donnée.

        Construit les collaborateurs standards : LinuxCommandExecutor
        local, SshCommandExecutor si la cible est distante,
        RsyncTransport (toujours local), VenvInstaller et
        InstallVerifier ciblant l'hôte.

        Args:
            target: Description de l'hôte cible (local ou distant).
            logger: Logger optionnel, propagé à tous les
                collaborateurs.
            dry_run: Si True, le Deployer simule sans effet de bord.

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
        return cls(transport, installer, verifier, logger, dry_run)

"""Acheminement du source local vers l'hôte cible.

Ce module fournit l'interface Transport (ABC) et son implémentation
V1 RsyncTransport. Le transport prend toujours son propre
LinuxCommandExecutor *local* : rsync est une commande locale qui
pousse vers l'hôte, contrairement à l'installation ou aux
vérifications qui s'exécutent, elles, sur l'hôte cible.
"""

from __future__ import annotations

import shlex
from abc import ABC, abstractmethod
from pathlib import Path

from linuxtools.commands.base import CommandExecutor, CommandResult
from linuxtools.commands.builder import CommandBuilder
from linuxtools.commands.runner import LinuxCommandExecutor
from linuxtools.deploy.models import DeployTarget
from linuxtools.logging.base import Logger


class Transport(ABC):
    """Interface d'acheminement du source vers l'hôte cible."""

    @abstractmethod
    def transfer(
        self,
        source_dir: Path,
        dest_dir: Path,
        target: DeployTarget,
    ) -> CommandResult:
        """Transfère source_dir vers dest_dir sur target.

        Args:
            source_dir: Répertoire source local.
            dest_dir: Répertoire de destination sur la cible.
            target: Description de l'hôte cible.

        Returns:
            CommandResult de l'opération de transport.
        """
        ...


class RsyncTransport(Transport):
    """Transport via rsync (local → hôte, local → local).

    Attributes:
        _local: LinuxCommandExecutor local (rsync tourne toujours
            en local, même vers une cible distante).
        _logger: Logger optionnel.
        _extra_options: Options rsync additionnelles.
        _timeout: Timeout en secondes pour l'appel rsync.
    """

    def __init__(
        self,
        local_executor: CommandExecutor | None = None,
        logger: Logger | None = None,
        extra_options: tuple[str, ...] = ("-a", "--delete"),
        timeout: int | None = 300,
    ) -> None:
        """Initialise le transport rsync.

        Args:
            local_executor: Exécuteur local pour lancer rsync. Si
                None, un LinuxCommandExecutor est créé.
            logger: Logger optionnel.
            extra_options: Options rsync additionnelles (défaut :
                archive + suppression des fichiers orphelins).
            timeout: Timeout en secondes pour l'appel rsync.
        """
        self._local = local_executor or LinuxCommandExecutor(
            logger=logger
        )
        self._logger = logger
        self._extra_options = extra_options
        self._timeout = timeout

    def _log(self, message: str) -> None:
        """Envoie un message d'information au logger si disponible."""
        if self._logger:
            self._logger.log_info(message)

    @staticmethod
    def _build_destination(
        dest_dir: Path, target: DeployTarget
    ) -> str:
        """Construit la destination rsync (locale ou distante).

        Args:
            dest_dir: Répertoire de destination.
            target: Description de l'hôte cible.

        Returns:
            Destination formatée pour rsync.
        """
        if target.is_remote:
            return f"{target.ssh_destination}:{dest_dir}"
        return str(dest_dir)

    def _build_command(
        self, src: str, dest: str, target: DeployTarget
    ) -> list[str]:
        """Assemble la commande rsync via CommandBuilder.

        Args:
            src: Chemin source (avec slash final).
            dest: Destination formatée.
            target: Description de l'hôte cible.

        Returns:
            Commande rsync sous forme de liste.
        """
        builder = CommandBuilder("rsync").with_options(
            list(self._extra_options)
        )
        if target.is_remote and target.ssh_options:
            ssh_cmd = shlex.join(["ssh", *target.ssh_options])
            builder = builder.with_options(["-e", ssh_cmd])
        builder = builder.with_args([src, dest])
        return builder.build()

    def transfer(
        self,
        source_dir: Path,
        dest_dir: Path,
        target: DeployTarget,
    ) -> CommandResult:
        """Transfère source_dir vers dest_dir sur target via rsync.

        Args:
            source_dir: Répertoire source local.
            dest_dir: Répertoire de destination sur la cible.
            target: Description de l'hôte cible.

        Returns:
            CommandResult de l'exécution rsync (locale).

        Raises:
            FileNotFoundError: Si source_dir n'existe pas.
        """
        if not source_dir.is_dir():
            raise FileNotFoundError(
                f"Répertoire source introuvable : {source_dir}"
            )

        src = f"{source_dir}/"
        dest = self._build_destination(dest_dir, target)
        command = self._build_command(src, dest, target)

        self._log(f"Transport rsync : {src} -> {dest}")
        result = self._local.run(command, timeout=self._timeout)
        if result.success:
            self._log("Transport rsync terminé avec succès.")
        return result

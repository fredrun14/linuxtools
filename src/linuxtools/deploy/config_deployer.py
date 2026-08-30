"""Dépôt de configuration TOML sur la cible d'un déploiement."""

from __future__ import annotations

from typing import TYPE_CHECKING

from linuxtools.deploy.toml_sink import (
    LocalDestination,
    RemoteDestination,
    TomlSink,
)

if TYPE_CHECKING:
    from linuxtools.commands.base import CommandExecutor
    from linuxtools.deploy.models import ConfigDeploySpec, DeployTarget
    from linuxtools.logging.base import Logger


class ConfigDeployer:
    """Dépose un fichier de config TOML sur la cible d'un déploiement.

    Attributes:
        _logger: Logger optionnel.
    """

    def __init__(self, logger: Logger | None = None) -> None:
        """Initialise le déployeur de config.

        Args:
            logger: Logger optionnel.
        """
        self._logger = logger

    def deploy(
        self,
        spec: ConfigDeploySpec,
        target: DeployTarget,
        executor: CommandExecutor,
    ) -> bool:
        """Dépose la config TOML de `spec` sur la cible.

        Args:
            spec: Spécification du dépôt (données, chemin, permissions).
            target: Cible du déploiement (détermine local vs distant).
            executor: Exécuteur de commandes ciblant `target`.

        Returns:
            True si le dépôt a réussi, False sinon.
        """
        destination = (
            RemoteDestination(executor)
            if target.is_remote
            else LocalDestination()
        )
        sink = TomlSink(destination, logger=self._logger)
        return sink.write(spec.dest_path, spec.data, mode=spec.mode)

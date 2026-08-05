"""Dépôt de configuration TOML sur la cible d'un déploiement."""

from __future__ import annotations

from typing import TYPE_CHECKING

from linuxtools.config.manager import ConfigurationManager

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
        manager = ConfigurationManager(
            default_config=spec.data, logger=self._logger
        )
        return manager.deploy_via(
            executor,
            spec.dest_path,
            is_remote=target.is_remote,
            mode=spec.mode,
        )

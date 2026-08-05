"""Installation d'un couple service+timer systemd sur la cible."""

from __future__ import annotations

from typing import TYPE_CHECKING

from linuxtools.logging.console_logger import ConsoleLogger
from linuxtools.systemd.executor import SystemdExecutor
from linuxtools.systemd.service import LinuxServiceUnitManager
from linuxtools.systemd.service_timer_installer import (
    SystemdServiceTimerInstaller,
)
from linuxtools.systemd.timer import LinuxTimerUnitManager

if TYPE_CHECKING:
    from linuxtools.commands.base import CommandExecutor
    from linuxtools.deploy.models import DeployTarget, TimerDeploySpec
    from linuxtools.logging.base import Logger


class TimerDeployer:
    """Installe un couple service+timer systemd sur la cible.

    Attributes:
        _logger: Logger optionnel.
    """

    def __init__(self, logger: Logger | None = None) -> None:
        """Initialise le déployeur de timer.

        Args:
            logger: Logger optionnel.
        """
        self._logger = logger

    def deploy(
        self,
        spec: TimerDeploySpec,
        target: DeployTarget,
        executor: CommandExecutor,
    ) -> bool:
        """Installe et active le service+timer de `spec` sur la cible.

        Args:
            spec: Spécification de l'unité (nom, ServiceConfig,
                TimerConfig).
            target: Cible du déploiement (détermine local vs
                distant).
            executor: Exécuteur de commandes ciblant `target`.

        Returns:
            True si l'installation et l'activation ont réussi.
        """
        logger = self._logger or ConsoleLogger()
        systemd_executor = SystemdExecutor(logger, executor)
        service_manager = LinuxServiceUnitManager(
            logger, systemd_executor, remote_write=target.is_remote
        )
        timer_manager = LinuxTimerUnitManager(
            logger, systemd_executor, remote_write=target.is_remote
        )
        installer = SystemdServiceTimerInstaller(
            logger, service_manager, timer_manager
        )
        return installer.install(
            spec.unit_name, spec.service_config, spec.timer_config
        )

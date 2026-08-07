"""Installation d'un couple service+timer systemd sur la cible."""

from __future__ import annotations

from typing import TYPE_CHECKING

from linuxtools.logging.console_logger import ConsoleLogger
from linuxtools.systemd.executor import SystemdExecutor, UserSystemdExecutor
from linuxtools.systemd.service import LinuxServiceUnitManager
from linuxtools.systemd.service_timer_installer import (
    SystemdServiceTimerInstaller,
)
from linuxtools.systemd.timer import LinuxTimerUnitManager
from linuxtools.systemd.user_service import LinuxUserServiceUnitManager
from linuxtools.systemd.user_timer import LinuxUserTimerUnitManager

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

        Le scope (`spec.scope`) détermine le chemin d'installation :
        "system" (défaut, /etc/systemd/system/, nécessite root) ou
        "user" (~/.config/systemd/user/, systemctl --user, sans
        élévation de privilèges).

        Args:
            spec: Spécification de l'unité (nom, ServiceConfig,
                TimerConfig, scope).
            target: Cible du déploiement (détermine local vs
                distant).
            executor: Exécuteur de commandes ciblant `target`.

        Returns:
            True si l'installation et l'activation ont réussi.
        """
        logger = self._logger or ConsoleLogger()
        if spec.scope == "user":
            return self._deploy_user(spec, target, executor, logger)
        return self._deploy_system(spec, target, executor, logger)

    def _deploy_system(
        self,
        spec: TimerDeploySpec,
        target: DeployTarget,
        executor: CommandExecutor,
        logger: Logger,
    ) -> bool:
        """Installe le service+timer en mode système (comportement
        historique, inchangé).

        Args:
            spec: Spécification de l'unité.
            target: Cible du déploiement.
            executor: Exécuteur de commandes ciblant `target`.
            logger: Logger déjà résolu (jamais None ici).

        Returns:
            True si l'installation et l'activation ont réussi.
        """
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

    def _deploy_user(
        self,
        spec: TimerDeploySpec,
        target: DeployTarget,
        executor: CommandExecutor,
        logger: Logger,
    ) -> bool:
        """Installe le service+timer en mode utilisateur (systemctl
        --user), sans élévation de privilèges.

        N'utilise volontairement pas `SystemdServiceTimerInstaller`
        (typé pour les ABCs système, incompatible mypy --strict avec
        les managers utilisateur) : orchestre directement les 3 appels
        dans le même ordre que `ServiceTimerInstaller.install()`
        (service -> timer -> enable).

        Args:
            spec: Spécification de l'unité.
            target: Cible du déploiement.
            executor: Exécuteur de commandes ciblant `target`.
            logger: Logger déjà résolu (jamais None ici).

        Returns:
            True si toutes les étapes ont réussi, False sinon.
        """
        systemd_executor = UserSystemdExecutor(logger, executor)
        service_manager = LinuxUserServiceUnitManager(
            logger, systemd_executor, remote_write=target.is_remote
        )
        timer_manager = LinuxUserTimerUnitManager(
            logger, systemd_executor, remote_write=target.is_remote
        )

        if not service_manager.install_service_unit_with_name(
            spec.unit_name, spec.service_config
        ):
            logger.log_error(
                f"Échec de l'installation du service utilisateur "
                f"{spec.unit_name}.service"
            )
            return False

        if not timer_manager.install_timer_unit(spec.timer_config):
            logger.log_error(
                f"Échec de l'installation du timer utilisateur "
                f"{spec.unit_name}.timer"
            )
            return False

        if not timer_manager.enable_timer(spec.unit_name):
            logger.log_error(
                f"Échec de l'activation du timer utilisateur "
                f"{spec.unit_name}.timer"
            )
            return False

        logger.log_info(
            f"Unités utilisateur {spec.unit_name}.service/.timer "
            "installées avec succès."
        )
        return True

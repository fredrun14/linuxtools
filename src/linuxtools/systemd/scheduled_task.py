"""Installation de tâches planifiées via systemd.

Ce module fournit une classe pour installer des tâches planifiées
complètes incluant script, service et timer systemd.

Example:
    Installation d'une tâche planifiée:

        installer = SystemdScheduledTaskInstaller(
            logger, script_installer, service_manager, timer_manager
        )
        installer.install(
            task_name="backup",
            script_path="/usr/local/bin/backup.sh",
            script_config=script_config,
            service_config=service_config,
            timer_config=timer_config,
        )
"""

from abc import ABC, abstractmethod

from linuxtools.logging import Logger
from linuxtools.scripts import BashScriptInstaller, BashScriptConfig
from linuxtools.systemd.base import (
    ServiceConfig,
    ServiceUnitManager,
    TimerConfig,
    TimerUnitManager,
)


class ScheduledTaskInstaller(ABC):
    """Interface abstraite pour l'installation de tâches planifiées.

    Cette classe définit le contrat pour toute implémentation
    d'installateur de tâches planifiées.
    """

    @abstractmethod
    def install(
        self,
        task_name: str,
        script_path: str,
        script_config: BashScriptConfig,
        service_config: ServiceConfig,
        timer_config: TimerConfig,
    ) -> bool:
        """Installe une tâche planifiée complète.

        Args:
            task_name: Nom de la tâche (utilisé pour service et timer).
            script_path: Chemin du script à créer.
            script_config: Configuration du script bash.
            service_config: Configuration du service systemd.
            timer_config: Configuration du timer systemd.

        Returns:
            True si l'installation a réussi, False sinon.
        """
        pass


class SystemdScheduledTaskInstaller(ScheduledTaskInstaller):
    """Installe une tâche planifiée complète via systemd.

    Cette classe orchestre l'installation d'une tâche planifiée
    incluant :
    - Le script bash (via BashScriptInstaller)
    - Le service systemd (via LinuxServiceUnitManager)
    - Le timer systemd (via LinuxTimerUnitManager)
    - L'activation du timer

    Attributes:
        logger: Instance de Logger pour la journalisation.
        script_installer: Installateur de scripts bash.
        service_manager: Gestionnaire d'unités .service (ServiceUnitManager).
        timer_manager: Gestionnaire d'unités .timer (TimerUnitManager).

    Example:
        >>> installer = SystemdScheduledTaskInstaller(
        ...     logger, script_installer, service_manager, timer_manager
        ... )
        >>> installer.install("backup", "/usr/local/bin/backup.sh", ...)
        True
    """

    def __init__(
        self,
        logger: Logger,
        script_installer: BashScriptInstaller,
        service_manager: ServiceUnitManager,
        timer_manager: TimerUnitManager,
    ) -> None:
        """Initialise l'installateur avec ses dépendances.

        Args:
            logger: Instance de Logger pour la journalisation.
            script_installer: Installateur de scripts bash.
            service_manager: Gestionnaire d'unités .service systemd.
            timer_manager: Gestionnaire d'unités .timer systemd.
        """
        self._logger: Logger = logger
        self._script_installer: BashScriptInstaller = script_installer
        self._service_manager: ServiceUnitManager = service_manager
        self._timer_manager: TimerUnitManager = timer_manager

    def install(
        self,
        task_name: str,
        script_path: str,
        script_config: BashScriptConfig,
        service_config: ServiceConfig,
        timer_config: TimerConfig,
    ) -> bool:
        """Installe une tâche planifiée complète.

        Exécute dans l'ordre :
        1. Installation du script bash
        2. Installation du service systemd
        3. Installation du timer systemd
        4. Activation du timer

        Args:
            task_name: Nom de la tâche (utilisé pour service et timer).
            script_path: Chemin du script à créer.
            script_config: Configuration du script bash.
            service_config: Configuration du service systemd.
            timer_config: Configuration du timer systemd.

        Returns:
            True si toutes les étapes ont réussi, False sinon.
        """
        if not self._install_script(script_path, script_config):
            return False

        if not self._install_service(task_name, service_config):
            return False

        if not self._install_timer(timer_config):
            return False

        if not self._enable_timer(task_name):
            return False

        self._logger.log_info(
            f"Tâche planifiée '{task_name}' installée avec succès."
        )
        return True

    def _install_script(
        self,
        script_path: str,
        script_config: BashScriptConfig
    ) -> bool:
        """Installe le script bash.

        Args:
            script_path: Chemin du script.
            script_config: Configuration du script.

        Returns:
            True si l'installation a réussi, False sinon.
        """
        if not self._script_installer.install(script_path, script_config):
            self._logger.log_error(
                f"Échec de l'installation du script {script_path}"
            )
            return False
        return True

    def _install_service(
        self,
        task_name: str,
        service_config: ServiceConfig
    ) -> bool:
        """Installe le service systemd.

        Args:
            task_name: Nom de la tâche.
            service_config: Configuration du service.

        Returns:
            True si l'installation a réussi, False sinon.
        """
        if not self._service_manager.install_service_unit_with_name(
            task_name, service_config
        ):
            self._logger.log_error(
                f"Échec de l'installation du service {task_name}.service"
            )
            return False
        return True

    def _install_timer(self, timer_config: TimerConfig) -> bool:
        """Installe le timer systemd.

        Args:
            timer_config: Configuration du timer.

        Returns:
            True si l'installation a réussi, False sinon.
        """
        if not self._timer_manager.install_timer_unit(timer_config):
            self._logger.log_error(
                f"Échec de l'installation du timer {timer_config.timer_name}"
            )
            return False
        return True

    def _enable_timer(self, task_name: str) -> bool:
        """Active le timer systemd.

        Args:
            task_name: Nom de la tâche.

        Returns:
            True si l'activation a réussi, False sinon.
        """
        if not self._timer_manager.enable_timer(task_name):
            self._logger.log_error(
                f"Échec de l'activation du timer {task_name}.timer"
            )
            return False
        return True

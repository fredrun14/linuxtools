"""Installation d'un couple service + timer systemd.

Ce module fournit un orchestrateur pour installer un service et son
timer systemd, soit à partir de dataclasses de configuration déjà
construites (``install``), soit depuis un fichier TOML unique
(``install_from_toml``).

Contrairement à :class:`SystemdScheduledTaskInstaller`, aucun script
bash n'est installé : le service doit pointer vers un exécutable
existant via son champ ``exec_start``. C'est le cas typique d'un binaire
déjà déployé (CLI installé dans ``/usr/local/bin``).

Le service peut être durci si la configuration renseigne les champs de
durcissement de :class:`ServiceConfig` (``no_new_privileges``,
``protect_system``, etc.) — aucune logique conditionnelle ici, le
durcissement est porté par la dataclass.

Example:
    Installation depuis un fichier TOML:

        installer = SystemdServiceTimerInstaller(
            logger, service_manager, timer_manager
        )
        installer.install_from_toml("backup", "config/backup.toml")

    Installation à partir de configs construites en Python:

        installer.install("backup", service_config, timer_config)
"""

from abc import ABC, abstractmethod
from pathlib import Path

from linuxtools.config import ConfigLoader
from linuxtools.logging import Logger
from linuxtools.systemd.base import (
    ServiceConfig,
    ServiceUnitManager,
    TimerConfig,
    TimerUnitManager,
)
from linuxtools.systemd.config_loaders import (
    ServiceConfigLoader,
    TimerConfigLoader,
)


class ServiceTimerInstaller(ABC):
    """Interface abstraite pour l'installation service + timer.

    Cette classe définit le contrat pour tout installateur de couple
    service/timer systemd, avec ou sans fichier de configuration.
    """

    @abstractmethod
    def install(
        self,
        unit_name: str,
        service_config: ServiceConfig,
        timer_config: TimerConfig,
    ) -> bool:
        """Installe et active un service et son timer déjà configurés.

        Args:
            unit_name: Nom de l'unité (service et timer, sans extension).
            service_config: Configuration du service (éventuellement
                durcie).
            timer_config: Configuration du timer.

        Returns:
            True si l'installation et l'activation ont réussi.
        """

    @abstractmethod
    def install_from_toml(
        self,
        unit_name: str,
        toml_path: str | Path,
        config_loader: ConfigLoader | None = None,
    ) -> bool:
        """Installe et active un service et son timer depuis un TOML.

        Args:
            unit_name: Nom de l'unité (service et timer, sans extension).
            toml_path: Fichier TOML avec les sections [service] et
                [timer].
            config_loader: Chargeur injectable (DIP/tests). Si None,
                utilise le chargeur de fichier par défaut.

        Returns:
            True si l'installation et l'activation ont réussi.

        Raises:
            FileNotFoundError: Si le fichier TOML n'existe pas.
            KeyError: Si une section requise est absente.
            ValueError: Si une configuration est invalide.
        """


class SystemdServiceTimerInstaller(ServiceTimerInstaller):
    """Installe un service et son timer systemd, avec ou sans TOML.

    Cette classe orchestre l'installation d'un service et de son timer
    associé sans installer de script. Le service doit pointer vers un
    exécutable existant via ``exec_start``. Le durcissement éventuel est
    porté par :class:`ServiceConfig`, aucune logique dédiée ici.

    Attributes:
        logger: Instance de Logger pour la journalisation.
        service_manager: Gestionnaire d'unités .service.
        timer_manager: Gestionnaire d'unités .timer.

    Example:
        >>> installer = SystemdServiceTimerInstaller(
        ...     logger, service_manager, timer_manager
        ... )
        >>> installer.install_from_toml("backup", "config/backup.toml")
        True
    """

    def __init__(
        self,
        logger: Logger,
        service_manager: ServiceUnitManager,
        timer_manager: TimerUnitManager,
    ) -> None:
        """Initialise l'installateur avec ses dépendances injectées.

        Args:
            logger: Instance de Logger pour la journalisation.
            service_manager: Gestionnaire d'unités .service systemd.
            timer_manager: Gestionnaire d'unités .timer systemd.
        """
        self._logger: Logger = logger
        self._service_manager: ServiceUnitManager = service_manager
        self._timer_manager: TimerUnitManager = timer_manager

    def install(
        self,
        unit_name: str,
        service_config: ServiceConfig,
        timer_config: TimerConfig,
    ) -> bool:
        """Installe et active un service et son timer déjà configurés.

        Exécute dans l'ordre :
        1. Installation du service
        2. Installation du timer
        3. Activation du timer

        Args:
            unit_name: Nom de l'unité (service et timer, sans extension).
            service_config: Configuration du service.
            timer_config: Configuration du timer.

        Returns:
            True si toutes les étapes ont réussi, False sinon.
        """
        if not self._service_manager.install_service_unit_with_name(
            unit_name, service_config
        ):
            self._logger.log_error(
                f"Échec de l'installation du service {unit_name}.service"
            )
            return False

        if not self._timer_manager.install_timer_unit(timer_config):
            self._logger.log_error(
                f"Échec de l'installation du timer {unit_name}.timer"
            )
            return False

        if not self._timer_manager.enable_timer(unit_name):
            self._logger.log_error(
                f"Échec de l'activation du timer {unit_name}.timer"
            )
            return False

        self._logger.log_info(
            f"Unités {unit_name}.service/.timer installées avec succès."
        )
        return True

    def install_from_toml(
        self,
        unit_name: str,
        toml_path: str | Path,
        config_loader: ConfigLoader | None = None,
    ) -> bool:
        """Charge les configs depuis un TOML puis délègue à install().

        Args:
            unit_name: Nom de l'unité (service et timer, sans extension).
            toml_path: Fichier TOML avec les sections [service] et
                [timer].
            config_loader: Chargeur injectable (DIP/tests).

        Returns:
            True si l'installation et l'activation ont réussi, False
            sinon.

        Raises:
            FileNotFoundError: Si le fichier TOML n'existe pas.
            KeyError: Si une section requise est absente.
            ValueError: Si une configuration est invalide.
        """
        service_config = ServiceConfigLoader(
            toml_path, config_loader
        ).load()
        timer_config = TimerConfigLoader(
            toml_path, config_loader
        ).load_for_service(unit_name)

        return self.install(unit_name, service_config, timer_config)

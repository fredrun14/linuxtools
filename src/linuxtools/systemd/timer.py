"""Implémentation Linux de la gestion des unités timer systemd."""

from linuxtools.logging.base import Logger
from linuxtools.systemd.base import (
    _TimerOperationsMixin,
    TimerUnitManager,
)
from linuxtools.systemd.executor import SystemdExecutor


class LinuxTimerUnitManager(_TimerOperationsMixin, TimerUnitManager):
    """Implémentation Linux de la gestion des unités .timer systemd.

    Génère et installe des fichiers unit systemd pour la planification
    de tâches récurrentes ou ponctuelles.

    Attributes:
        logger: Instance de Logger pour le logging.
        executor: Instance de SystemdExecutor pour les opérations systemctl.
        SYSTEMD_UNIT_PATH: Chemin du répertoire des unités systemd.
    """

    def __init__(
        self,
        logger: Logger,
        executor: SystemdExecutor
    ) -> None:
        """
        Initialise le gestionnaire d'unités timer.

        Args:
            logger: Instance de Logger pour le logging
            executor: Instance de SystemdExecutor pour les opérations systemctl
        """
        super().__init__(logger, executor)

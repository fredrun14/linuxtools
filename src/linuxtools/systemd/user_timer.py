"""Implémentation Linux de la gestion des unités timer utilisateur."""

from linuxtools.logging.base import Logger
from linuxtools.systemd.base import (
    _TimerOperationsMixin,
    UserTimerUnitManager,
)
from linuxtools.systemd.executor import UserSystemdExecutor


class LinuxUserTimerUnitManager(_TimerOperationsMixin, UserTimerUnitManager):
    """Implémentation Linux de la gestion des unités .timer utilisateur.

    Génère et installe des fichiers unit systemd pour la planification
    de tâches récurrentes ou ponctuelles dans l'espace utilisateur.

    Les unités sont stockées dans ~/.config/systemd/user/ et ne
    nécessitent pas de privilèges root.

    Attributes:
        logger: Instance de Logger pour le logging.
        executor: Instance de UserSystemdExecutor pour les opérations.
        SYSTEMD_USER_UNIT_PATH: Chemin du répertoire des unités utilisateur.
    """

    _timer_label = "Timer utilisateur"

    def __init__(
        self,
        logger: Logger,
        executor: UserSystemdExecutor
    ) -> None:
        """
        Initialise le gestionnaire d'unités timer utilisateur.

        Args:
            logger: Instance de Logger pour le logging
            executor: Instance de UserSystemdExecutor pour les opérations
        """
        super().__init__(logger, executor)

"""Implémentation Linux de la gestion des unités timer utilisateur."""

from linuxtools.logging.base import Logger
from linuxtools.systemd.base import (
    UserTimerUnitManager,
    _TimerOperationsMixin,
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
        executor: UserSystemdExecutor,
        remote_write: bool = False,
    ) -> None:
        """
        Initialise le gestionnaire d'unités timer utilisateur.

        Args:
            logger: Instance de Logger pour le logging
            executor: Instance de UserSystemdExecutor pour les opérations
            remote_write: Si True, écrit les fichiers d'unité via l'executor
                (cible distante) au lieu de l'écriture locale TOCTOU-safe.
        """
        super().__init__(logger, executor, remote_write)

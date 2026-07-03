"""Implémentation Linux de la gestion des unités service utilisateur."""

from linuxtools.logging.base import Logger
from linuxtools.systemd.base import (
    _ServiceOperationsMixin,
    UserServiceUnitManager,
)
from linuxtools.systemd.executor import UserSystemdExecutor


class LinuxUserServiceUnitManager(
    _ServiceOperationsMixin, UserServiceUnitManager
):
    """Implémentation Linux de la gestion des unités .service utilisateur.

    Génère et installe des fichiers unit systemd pour les services
    utilisateur (scripts, applications de fond, etc.).

    Les unités sont stockées dans ~/.config/systemd/user/ et ne
    nécessitent pas de privilèges root.

    Attributes:
        logger: Instance de Logger pour le logging.
        executor: Instance de UserSystemdExecutor pour les opérations.
        SYSTEMD_USER_UNIT_PATH: Chemin du répertoire des unités utilisateur.
    """

    _service_label = "Service utilisateur"

    def __init__(
        self,
        logger: Logger,
        executor: UserSystemdExecutor
    ) -> None:
        """
        Initialise le gestionnaire d'unités service utilisateur.

        Args:
            logger: Instance de Logger pour le logging
            executor: Instance de UserSystemdExecutor pour les opérations
        """
        super().__init__(logger, executor)

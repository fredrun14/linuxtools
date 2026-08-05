"""Implémentation Linux de la gestion des unités service utilisateur."""

from linuxtools.logging.base import Logger
from linuxtools.systemd.base import (
    UserServiceUnitManager,
    _ServiceOperationsMixin,
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
        executor: UserSystemdExecutor,
        remote_write: bool = False,
    ) -> None:
        """
        Initialise le gestionnaire d'unités service utilisateur.

        Args:
            logger: Instance de Logger pour le logging
            executor: Instance de UserSystemdExecutor pour les opérations
            remote_write: Si True, écrit les fichiers d'unité via l'executor
                (cible distante) au lieu de l'écriture locale TOCTOU-safe.
        """
        super().__init__(logger, executor, remote_write)

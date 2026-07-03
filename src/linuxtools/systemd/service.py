"""Implémentation Linux de la gestion des unités service systemd."""

from linuxtools.logging.base import Logger
from linuxtools.systemd.base import (
    _ServiceOperationsMixin,
    ServiceUnitManager,
)
from linuxtools.systemd.executor import SystemdExecutor


class LinuxServiceUnitManager(_ServiceOperationsMixin, ServiceUnitManager):
    """Implémentation Linux de la gestion des unités .service systemd.

    Génère et installe des fichiers unit systemd pour les services
    (démons, scripts de démarrage, etc.).

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
        Initialise le gestionnaire d'unités service.

        Args:
            logger: Instance de Logger pour le logging
            executor: Instance de SystemdExecutor pour les opérations systemctl
        """
        super().__init__(logger, executor)

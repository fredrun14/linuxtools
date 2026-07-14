"""Installation d'unités .mount et .automount systemd.

Ce module fournit un orchestrateur pour installer une unité .mount (et
optionnellement .automount), soit à partir d'un MountConfig déjà
construit (``install``), soit depuis un fichier TOML unique
(``install_from_toml``).

L'orchestrateur est générique par rapport au type de montage : le champ
``type`` de la configuration (nfs, cifs, sshfs, ...) pilote le
comportement, aucune classe dédiée n'est nécessaire pour NFS.

Example:
    Installation d'un montage NFS avec automount depuis un TOML:

        installer = SystemdAutomountInstaller(logger, mount_manager)
        installer.install_from_toml("config/nas.toml")

    Fichier TOML attendu:

        [mount]
        description = "Partage NAS"
        what = "192.168.1.10:/share"
        where = "/media/nas"
        type = "nfs"
        options = "rw,soft"
        with_automount = true
        automount_timeout_sec = 600
"""

from abc import ABC, abstractmethod
from pathlib import Path

from linuxtools.config import ConfigLoader
from linuxtools.logging import Logger
from linuxtools.systemd.base import MountConfig, MountUnitManager
from linuxtools.systemd.config_loaders import MountConfigLoader


class AutomountInstaller(ABC):
    """Interface abstraite pour l'installation mount + automount.

    Cette classe définit le contrat pour tout installateur d'unités
    .mount/.automount systemd, avec ou sans fichier de configuration.
    """

    @abstractmethod
    def install(
        self,
        config: MountConfig,
        with_automount: bool = False,
        automount_timeout_sec: int = 0,
    ) -> bool:
        """Installe et active un montage (et son automount) configuré.

        Args:
            config: Configuration du montage.
            with_automount: Créer aussi une unité .automount.
            automount_timeout_sec: Délai d'inactivité avant démontage
                (secondes).

        Returns:
            True si l'installation et l'activation ont réussi.
        """

    @abstractmethod
    def install_from_toml(
        self,
        toml_path: str | Path,
        config_loader: ConfigLoader | None = None,
    ) -> bool:
        """Installe et active un montage depuis un TOML.

        Args:
            toml_path: Fichier TOML avec la section [mount] (et
                éventuellement 'with_automount' /
                'automount_timeout_sec').
            config_loader: Chargeur injectable (DIP/tests). Si None,
                utilise le chargeur de fichier par défaut.

        Returns:
            True si l'installation et l'activation ont réussi.

        Raises:
            FileNotFoundError: Si le fichier TOML n'existe pas.
            KeyError: Si la section [mount] est absente.
        """


class SystemdAutomountInstaller(AutomountInstaller):
    """Installe une unité .mount (et .automount) systemd, avec ou sans TOML.

    Cette classe orchestre l'installation d'un montage et de son
    automount optionnel. Générique par rapport au type de montage (nfs,
    cifs, sshfs, ...) : le champ ``type`` du MountConfig pilote le
    comportement, aucune classe dédiée NFS.

    Attributes:
        logger: Instance de Logger pour la journalisation.
        mount_manager: Gestionnaire d'unités .mount/.automount.

    Example:
        >>> installer = SystemdAutomountInstaller(logger, mount_manager)
        >>> installer.install_from_toml("config/nas.toml")
        True
    """

    def __init__(
        self,
        logger: Logger,
        mount_manager: MountUnitManager,
    ) -> None:
        """Initialise l'installateur avec ses dépendances injectées.

        Args:
            logger: Instance de Logger pour la journalisation.
            mount_manager: Gestionnaire d'unités .mount/.automount.
        """
        self._logger: Logger = logger
        self._mount_manager: MountUnitManager = mount_manager

    def install(
        self,
        config: MountConfig,
        with_automount: bool = False,
        automount_timeout_sec: int = 0,
    ) -> bool:
        """Installe et active un montage (et son automount) configuré.

        Exécute dans l'ordre :
        1. Installation de l'unité .mount (et .automount si demandé)
        2. Activation du montage

        Args:
            config: Configuration du montage.
            with_automount: Créer aussi une unité .automount.
            automount_timeout_sec: Délai d'inactivité avant démontage.

        Returns:
            True si toutes les étapes ont réussi, False sinon.
        """
        if not self._mount_manager.install_mount_unit(
            config,
            with_automount=with_automount,
            automount_timeout=automount_timeout_sec,
        ):
            self._logger.log_error(
                f"Échec de l'installation du montage {config.where}"
            )
            return False

        if not self._mount_manager.enable_mount(
            config.where, with_automount=with_automount
        ):
            self._logger.log_error(
                f"Échec de l'activation du montage {config.where}"
            )
            return False

        self._logger.log_info(
            f"Montage {config.where} installé avec succès "
            f"(automount={with_automount})."
        )
        return True

    def install_from_toml(
        self,
        toml_path: str | Path,
        config_loader: ConfigLoader | None = None,
    ) -> bool:
        """Charge la config depuis un TOML puis délègue à install().

        Args:
            toml_path: Fichier TOML avec la section [mount].
            config_loader: Chargeur injectable (DIP/tests).

        Returns:
            True si l'installation et l'activation ont réussi, False
            sinon.

        Raises:
            FileNotFoundError: Si le fichier TOML n'existe pas.
            KeyError: Si la section [mount] est absente.
        """
        settings = MountConfigLoader(
            toml_path, config_loader
        ).load_with_automount()

        return self.install(
            settings.config,
            with_automount=settings.with_automount,
            automount_timeout_sec=settings.timeout_sec,
        )

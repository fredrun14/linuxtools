"""Implémentation Linux de la gestion des unités mount/automount systemd."""

from pathlib import Path

from linuxtools.logging.base import Logger
from linuxtools.systemd.base import (
    MountUnitManager,
    MountConfig,
    AutomountConfig
)
from linuxtools.systemd.executor import SystemdExecutor


class LinuxMountUnitManager(MountUnitManager):
    """Implémentation Linux de la gestion des unités .mount et .automount.

    Génère et installe des fichiers unit systemd pour le montage
    de systèmes de fichiers (NFS, CIFS, SSHFS, etc.).

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
        Initialise le gestionnaire d'unités mount.

        Args:
            logger: Instance de Logger pour le logging
            executor: Instance de SystemdExecutor pour les opérations systemctl
        """
        super().__init__(logger, executor)

    def _ensure_mount_point(self, path: str) -> bool:
        """
        Crée le point de montage s'il n'existe pas.

        Args:
            path: Chemin du point de montage

        Returns:
            True si le répertoire existe ou a été créé, False sinon
        """
        try:
            mount_path = Path(path)
            already_exists = mount_path.exists()
            mount_path.mkdir(parents=True, exist_ok=True)
            if not already_exists:
                self.logger.log_info(f"Point de montage créé: {path}")
            return True
        except PermissionError:
            self.logger.log_error(
                f"Permission refusée pour créer {path}. "
                "Exécution en tant que root requise."
            )
            return False
        except OSError as e:
            self.logger.log_error(
                f"Erreur lors de la création du point de montage {path}: {e}"
            )
            return False

    def install_mount_unit(
        self,
        config: MountConfig,
        with_automount: bool = False,
        automount_timeout: int = 0
    ) -> bool:
        """
        Installe une unité .mount (et optionnellement .automount).

        Args:
            config: Configuration du montage
            with_automount: Créer aussi une unité .automount
            automount_timeout: Délai d'inactivité avant démontage (secondes)

        Returns:
            True si succès, False sinon
        """
        # Créer le point de montage
        if not self._ensure_mount_point(config.where):
            return False

        # Générer et écrire le fichier .mount
        mount_content = config.to_unit_file()
        mount_file = f"{config.unit_name}.mount"
        if not self._write_unit_file(mount_file, mount_content):
            return False

        # Optionnellement créer le fichier .automount
        if with_automount:
            automount_config = AutomountConfig(
                description=config.description,
                where=config.where,
                timeout_idle_sec=automount_timeout
            )
            automount_content = automount_config.to_unit_file()
            if not self._write_unit_file(
                f"{automount_config.unit_name}.automount",
                automount_content
            ):
                return False

        # Recharger systemd
        if not self.reload_systemd():
            return False

        self.logger.log_info(
            f"Unité de montage installée pour {config.where}"
        )
        return True

    def enable_mount(
        self,
        mount_path: str,
        with_automount: bool = False
    ) -> bool:
        """
        Active une unité .mount (ou .automount si spécifié).

        Args:
            mount_path: Chemin du point de montage
            with_automount: Activer l'unité .automount au lieu de .mount

        Returns:
            True si succès, False sinon
        """
        unit_name = self.path_to_unit_name(mount_path)

        if with_automount:
            unit = f"{unit_name}.automount"
        else:
            unit = f"{unit_name}.mount"

        return self.enable(unit)

    def disable_mount(self, mount_path: str) -> bool:
        """
        Désactive et arrête les unités .mount et .automount.

        Args:
            mount_path: Chemin du point de montage

        Returns:
            True si succès, False sinon
        """
        unit_name = self.path_to_unit_name(mount_path)

        # Désactiver d'abord l'automount s'il existe (ignorer erreurs)
        automount_unit = f"{unit_name}.automount"
        self.disable(automount_unit, ignore_errors=True)

        # Désactiver le mount
        mount_unit = f"{unit_name}.mount"
        return self.disable(mount_unit)

    def remove_mount_unit(self, mount_path: str) -> bool:
        """
        Supprime les fichiers .mount et .automount.

        Args:
            mount_path: Chemin du point de montage

        Returns:
            True si succès, False sinon
        """
        unit_name = self.path_to_unit_name(mount_path)

        # D'abord désactiver les unités
        if not self.disable_mount(mount_path):
            self.logger.log_warning(
                f"disable_mount échoué pour {mount_path!r} "
                "(montage peut-être déjà inactif) — "
                "suppression des fichiers unit quand même"
            )

        # Supprimer les fichiers
        success = True
        if not self._remove_unit_file(f"{unit_name}.mount"):
            success = False
        if not self._remove_unit_file(f"{unit_name}.automount"):
            success = False

        # Recharger systemd
        if success:
            self.reload_systemd()
            self.logger.log_info(
                f"Unités de montage supprimées pour {mount_path}"
            )

        return success

    def get_mount_status(self, mount_path: str) -> str | None:
        """
        Récupère le statut d'une unité .mount.

        Args:
            mount_path: Chemin du point de montage

        Returns:
            Statut de l'unité ou None si erreur
        """
        unit_name = self.path_to_unit_name(mount_path)
        return self.get_status(f"{unit_name}.mount")

    def is_mounted(self, mount_path: str) -> bool:
        """
        Vérifie si un point de montage est actif.

        Args:
            mount_path: Chemin du point de montage

        Returns:
            True si monté, False sinon
        """
        return self.get_mount_status(mount_path) == "active"

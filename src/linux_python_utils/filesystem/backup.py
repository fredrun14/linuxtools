"""Gestion des sauvegardes de fichiers."""

import os
from abc import ABC, abstractmethod
from pathlib import Path

from linux_python_utils.filesystem.linux import _open_secure
from linux_python_utils.logging.base import Logger

_CHUNK = 65536  # taille de bloc pour la copie binaire (64 Ko)


def _copy_secure(src: str | Path, dst: str | Path) -> None:
    """Copie src vers dst en binaire sans suivre les symlinks.

    Copie le contenu uniquement — les métadonnées (timestamps, ACL,
    attributs étendus) ne sont pas préservées. Permissions forcées à
    0o644 sur dst via fchmod.

    Args:
        src: Chemin source (ne doit pas être un symlink).
        dst: Chemin destination (ne doit pas être un symlink).

    Raises:
        OSError: Si src ou dst est un symlink, ou erreur d'E/S.
    """
    src_fd = _open_secure(src, os.O_RDONLY, 0o000)
    try:
        dst_fd = _open_secure(
            dst, os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o644
        )
        try:
            os.fchmod(dst_fd, 0o644)
            while chunk := os.read(src_fd, _CHUNK):
                os.write(dst_fd, chunk)
        finally:
            os.close(dst_fd)
    finally:
        os.close(src_fd)


class FileBackup(ABC):
    """Interface pour la gestion des sauvegardes de fichiers."""

    @abstractmethod
    def backup(self, file_path: str | Path, backup_path: str | Path) -> bool:
        """Crée une sauvegarde d'un fichier.

        Args:
            file_path: Chemin du fichier à sauvegarder.
            backup_path: Chemin de la sauvegarde.

        Returns:
            True si succès, False si la source est absente.
        """

    @abstractmethod
    def restore(
        self, file_path: str | Path, backup_path: str | Path
    ) -> None:
        """Restaure un fichier depuis sa sauvegarde.

        Args:
            file_path: Chemin du fichier à restaurer.
            backup_path: Chemin de la sauvegarde.
        """


class LinuxFileBackup(FileBackup):
    """Implémentation Linux de la sauvegarde de fichiers.

    Utilise O_NOFOLLOW pour éviter toute attaque par substitution de symlink.
    """

    def __init__(self, logger: Logger | None = None) -> None:
        """Initialise le gestionnaire de sauvegarde.

        Args:
            logger: Instance de Logger pour le logging.
        """
        self._logger = logger

    def backup(
        self, file_path: str | Path, backup_path: str | Path
    ) -> bool:
        """Sauvegarde un fichier. Retourne False si la source est absente.

        Copie le contenu uniquement — les métadonnées (timestamps, ACL)
        ne sont pas préservées.

        Args:
            file_path: Chemin du fichier à sauvegarder.
            backup_path: Chemin de la sauvegarde.

        Returns:
            True si la sauvegarde réussit, False si la source est absente.

        Raises:
            OSError: Si file_path ou backup_path est un symlink,
                ou erreur d'E/S.
        """
        if not Path(file_path).exists():
            if self._logger:
                self._logger.log_warning(
                    f"Source absente, aucune sauvegarde : {file_path}"
                )
            return False
        try:
            _copy_secure(file_path, backup_path)
            if self._logger:
                self._logger.log_info(
                    f"Sauvegarde de {file_path} vers {backup_path}"
                )
            return True
        except OSError as exc:
            if self._logger:
                self._logger.log_error(
                    f"Erreur lors de la sauvegarde de {file_path}: {exc}"
                )
            raise

    def restore(
        self, file_path: str | Path, backup_path: str | Path
    ) -> None:
        """Restaure un fichier depuis sa sauvegarde.

        Args:
            file_path: Chemin du fichier à restaurer.
            backup_path: Chemin de la sauvegarde.

        Raises:
            FileNotFoundError: Si la sauvegarde n'existe pas.
            OSError: Si file_path est un symlink ou erreur d'E/S.
        """
        try:
            _copy_secure(backup_path, file_path)
            if self._logger:
                self._logger.log_info(
                    f"Restauration de {file_path} depuis {backup_path}"
                )
        except FileNotFoundError as exc:
            msg = f"Aucune sauvegarde disponible: {backup_path}"
            if self._logger:
                self._logger.log_error(msg)
            raise FileNotFoundError(msg) from exc
        except OSError as exc:
            if self._logger:
                self._logger.log_error(
                    f"Erreur lors de la restauration de"
                    f" {file_path}: {exc}"
                )
            raise

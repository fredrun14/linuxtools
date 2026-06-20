"""Implémentation Linux de la gestion des fichiers."""

import os
from pathlib import Path

from linux_python_utils.filesystem.base import FileManager
from linux_python_utils.logging.base import Logger


def _open_secure(
    path: str | Path,
    flags: int,
    mode: int = 0o644,
) -> int:
    """Ouvre un chemin avec O_NOFOLLOW garanti.

    Primitive partagée par write_text_secure et _copy_secure pour
    centraliser la protection anti-substitution de symlink.

    Args:
        path: Chemin cible.
        flags: Flags os.open — O_NOFOLLOW est ajouté automatiquement.
        mode: Permissions POSIX initiales (appliquées séparément via fchmod).

    Returns:
        Descripteur de fichier ouvert.

    Raises:
        OSError: Si la cible est un symlink ou en cas d'erreur d'E/S.
    """
    return os.open(str(path), flags | os.O_NOFOLLOW, mode)


def write_text_secure(
    path: str | Path,
    content: str,
    mode: int = 0o644,
    *,
    encoding: str = "utf-8",
) -> None:
    """Écrit un fichier texte sans suivre les symlinks.

    Utilise O_NOFOLLOW + fchmod pour garantir que :
    - la cible n'est pas un lien symbolique (lève OSError sinon) ;
    - les permissions sont appliquées indépendamment de l'umask.

    Args:
        path: Chemin cible.
        content: Contenu texte à écrire.
        mode: Permissions POSIX (défaut 0o644).
        encoding: Encodage du fichier (défaut UTF-8).

    Raises:
        OSError: Si la cible est un symlink ou en cas d'erreur d'E/S.
    """
    fd = _open_secure(path, os.O_CREAT | os.O_WRONLY | os.O_TRUNC, mode)
    try:
        os.fchmod(fd, mode)
        f = os.fdopen(fd, "w", encoding=encoding)
    except BaseException:
        os.close(fd)
        raise
    with f:
        f.write(content)


class LinuxFileManager(FileManager):
    """
    Implémentation Linux de la gestion des fichiers.

    Toutes les opérations sont loggées via l'instance Logger.
    """

    def __init__(self, logger: Logger | None = None) -> None:
        """
        Initialise le gestionnaire de fichiers.

        Args:
            logger: Instance de Logger pour le logging.
        """
        self._logger = logger

    def create_file(self, file_path: str | Path, content: str) -> bool:
        """
        Crée un fichier avec le contenu spécifié.

        Args:
            file_path: Chemin du fichier à créer
            content: Contenu du fichier

        Returns:
            True si succès, False sinon
        """
        try:
            write_text_secure(file_path, content)
            if self._logger:
                self._logger.log_info(
                    f"Fichier {file_path} créé avec succès."
                )
            return True
        except OSError as exc:
            if self._logger:
                self._logger.log_error(
                    f"Erreur lors de la création du fichier"
                    f" {file_path}: {exc}"
                )
            return False

    def file_exists(self, file_path: str | Path) -> bool:
        """
        Vérifie si un fichier existe.

        Args:
            file_path: Chemin du fichier

        Returns:
            True si le fichier existe, False sinon
        """
        return Path(file_path).exists()

    def read_file(self, file_path: str | Path) -> str:
        """
        Lit le contenu d'un fichier.

        Args:
            file_path: Chemin du fichier

        Returns:
            Contenu du fichier

        Raises:
            OSError: Si le fichier est inaccessible.

        Note:
            Contrairement à create_file, suit les symlinks.
            Lecture seule — risque TOCTOU limité et accepté.
        """
        try:
            with open(file_path, encoding="utf-8") as f:
                content = f.read()
            if self._logger:
                self._logger.log_info(
                    f"Fichier {file_path} lu avec succès."
                )
            return content
        except OSError as exc:
            if self._logger:
                self._logger.log_error(
                    f"Erreur lors de la lecture du fichier"
                    f" {file_path}: {exc}"
                )
            raise

    def delete_file(self, file_path: str | Path) -> bool:
        """
        Supprime un fichier.

        Args:
            file_path: Chemin du fichier

        Returns:
            True si succès, False sinon
        """
        try:
            Path(file_path).unlink()
            if self._logger:
                self._logger.log_info(
                    f"Fichier {file_path} supprimé avec succès."
                )
            return True
        except OSError as exc:
            if self._logger:
                self._logger.log_error(
                    f"Erreur lors de la suppression du"
                    f" fichier {file_path}: {exc}"
                )
            return False

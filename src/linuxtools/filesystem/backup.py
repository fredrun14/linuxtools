"""Gestion des sauvegardes de fichiers."""

import os
from abc import ABC, abstractmethod
from collections.abc import Callable
from pathlib import Path

from linuxtools.filesystem.linux import _open_secure
from linuxtools.logging.base import Logger

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


def copytree_secure(
    src: str | Path,
    dst: str | Path,
    *,
    dirs_exist_ok: bool = False,
    ignore: Callable[[str, list[str]], set[str]] | None = None,
    follow_symlinks: bool = False,
) -> Path:
    """Copie récursive d'un répertoire avec protection symlink.

    Parcourt src récursivement. Les fichiers sont copiés via
    _copy_secure (O_NOFOLLOW, permissions 0o644). Les répertoires
    sont créés avec permissions 0o755.

    Par défaut les symlinks sont ignorés silencieusement. Avec
    follow_symlinks=True, les symlinks sont résolus et leur cible
    est copiée (fichier) ou parcourue récursivement (répertoire).
    L'O_NOFOLLOW reste actif côté destination.

    Args:
        src: Répertoire source.
        dst: Répertoire destination.
        dirs_exist_ok: Si True, ne lève pas d'erreur si dst
            existe déjà.
        ignore: Callable compatible shutil.ignore_patterns.
            Reçoit (dirpath, entries) et retourne un set de
            noms à ignorer.
        follow_symlinks: Si True, résout les symlinks source
            et copie leur cible. Si False (défaut), les ignore.

    Returns:
        Path de la destination.

    Raises:
        FileNotFoundError: Si src n'existe pas.
        FileExistsError: Si dst existe et dirs_exist_ok=False.
        NotADirectoryError: Si src n'est pas un répertoire.
        OSError: Si src est un symlink, ou erreur d'E/S.
    """
    src = Path(src)
    dst = Path(dst)

    if not src.exists():
        raise FileNotFoundError(f"Source absente : {src}")
    if src.is_symlink():
        raise OSError(f"Source est un symlink : {src}")
    if not src.is_dir():
        raise NotADirectoryError(f"Source n'est pas un répertoire : {src}")
    if dst.exists() and not dirs_exist_ok:
        raise FileExistsError(f"Destination existe déjà : {dst}")

    dst.mkdir(parents=True, exist_ok=dirs_exist_ok)
    os.chmod(dst, 0o755)

    entries = sorted(src.iterdir())
    names = [e.name for e in entries]
    ignored = ignore(str(src), names) if ignore else set()

    for entry in entries:
        if entry.name in ignored:
            continue
        if entry.is_symlink():
            if not follow_symlinks:
                continue
            resolved = entry.resolve()
            dest_entry = dst / entry.name
            if resolved.is_dir():
                copytree_secure(
                    resolved, dest_entry,
                    dirs_exist_ok=dirs_exist_ok,
                    ignore=ignore,
                    follow_symlinks=follow_symlinks,
                )
            elif resolved.is_file():
                _copy_secure(resolved, dest_entry)
            continue
        dest_entry = dst / entry.name
        if entry.is_dir():
            copytree_secure(
                entry, dest_entry,
                dirs_exist_ok=dirs_exist_ok,
                ignore=ignore,
                follow_symlinks=follow_symlinks,
            )
        elif entry.is_file():
            _copy_secure(entry, dest_entry)

    return dst


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

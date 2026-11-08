"""Rétention des fichiers de logs : purge par âge dans un dossier."""

from __future__ import annotations

import fnmatch
import os
import stat
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

DEFAULT_RETENTION_DAYS = 90
_SECONDS_PER_DAY = 86_400


def purge_old_logs(
    log_dir: Path,
    pattern: str,
    *,
    max_age_days: int = DEFAULT_RETENTION_DAYS,
    keep: Path | None = None,
    dry_run: bool = False,
) -> list[Path]:
    """Supprime les anciens fichiers de logs d'un dossier.

    Ne touche que les fichiers réguliers de ``log_dir`` dont le nom
    correspond à ``pattern`` et dont la date de modification dépasse
    ``max_age_days`` jours. Les liens symboliques, les sous-dossiers et
    les fichiers hors motif sont conservés. Best-effort : aucune
    ``OSError`` n'est propagée (dossier absent, fichier non supprimable).

    Args:
        log_dir: Dossier de logs de l'application (non suivi s'il est un
            lien symbolique).
        pattern: Motif comparé au nom des fichiers (``fnmatch``, ex.
            ``"deploy_*.log"``), sans séparateur de chemin. Attention :
            ``"*"`` et ``"**"`` visent tous les fichiers du dossier, jamais
            ceux d'un sous-dossier.
        max_age_days: Âge minimal, en jours, avant suppression (>= 1).
        keep: Fichier à ne jamais supprimer (log du run en cours). Un lien
            symbolique est suivi : sa cible est protégée.
        dry_run: Si True, liste sans supprimer.

    Returns:
        Fichiers supprimés (ou qui le seraient en dry-run), triés.

    Raises:
        ValueError: ``pattern`` vide ou contenant un séparateur de
            chemin, ou ``max_age_days`` inférieur à 1.
    """
    # Validation avant tout accès disque
    if not pattern or "/" in pattern or "\\" in pattern:
        raise ValueError(
            "Motif invalide : non vide et sans séparateur de chemin"
        )
    if max_age_days < 1:
        raise ValueError("max_age_days doit être supérieur ou égal à 1")

    # Ouverture sans suivre de lien : absent, non dossier, lien symbolique
    # (ELOOP) ou non traversable -> rien à purger. Le parcours se fait
    # ensuite par descripteur, à l'abri d'un remplacement du dossier.
    try:
        fd = os.open(log_dir, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    except OSError:
        return []

    try:
        try:
            with os.scandir(fd) as entries:
                names = [entry.name for entry in entries]
        except OSError:
            # Listage impossible : rien n'a été traité
            return []
        return _purge_names(
            fd, log_dir, names, pattern, max_age_days, keep, dry_run
        )
    finally:
        os.close(fd)


def _purge_names(
    fd: int,
    log_dir: Path,
    names: list[str],
    pattern: str,
    max_age_days: int,
    keep: Path | None,
    dry_run: bool,
) -> list[Path]:
    """Supprime, relativement au descripteur ``fd``, les noms éligibles.

    Args:
        fd: Descripteur ouvert du dossier de logs.
        log_dir: Chemin du dossier, pour construire les chemins rendus.
        names: Noms des entrées du dossier.
        pattern: Motif ``fnmatch`` appliqué au nom.
        max_age_days: Âge minimal, en jours, avant suppression.
        keep: Fichier à ne jamais supprimer.
        dry_run: Si True, liste sans supprimer.

    Returns:
        Fichiers supprimés (ou qui le seraient en dry-run), triés.
    """
    cutoff = time.time() - max_age_days * _SECONDS_PER_DAY
    # Identité du fichier à garder (lien suivi), insensible à l'écriture
    keep_id: tuple[int, int] | None = None
    if keep is not None:
        try:
            keep_info = os.stat(keep)
            keep_id = (keep_info.st_dev, keep_info.st_ino)
        except OSError:
            keep_id = None

    removed: list[Path] = []
    for name in names:
        if not fnmatch.fnmatchcase(name, pattern):
            continue
        try:
            info = os.stat(name, dir_fd=fd, follow_symlinks=False)
        except OSError:
            continue
        # Fichiers réguliers seulement (ni lien, ni dossier)
        if not stat.S_ISREG(info.st_mode):
            continue
        if keep_id == (info.st_dev, info.st_ino):
            continue
        if info.st_mtime >= cutoff:
            continue
        if not dry_run:
            try:
                os.unlink(name, dir_fd=fd)
            except OSError:
                continue
        removed.append(log_dir / name)
    return sorted(removed)

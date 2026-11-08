"""Rétention des fichiers de logs : purge par âge dans un dossier."""

from __future__ import annotations

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
        pattern: Motif glob de noms de fichiers (ex. ``"deploy_*.log"``),
            sans séparateur de chemin. Attention : ``"*"`` viserait tous
            les fichiers du dossier.
        max_age_days: Âge minimal, en jours, avant suppression (>= 1).
        keep: Fichier à ne jamais supprimer (log du run en cours).
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

    # Un dossier absent, non dossier ou lien symbolique n'est pas parcouru
    if log_dir.is_symlink() or not log_dir.is_dir():
        return []

    removed: list[Path] = []
    cutoff = time.time() - max_age_days * _SECONDS_PER_DAY
    try:
        for path in log_dir.glob(pattern):
            try:
                info = path.lstat()
            except OSError:
                continue
            # Fichiers réguliers seulement (ni lien, ni dossier)
            if not stat.S_ISREG(info.st_mode):
                continue
            if keep is not None and path == keep:
                continue
            if info.st_mtime >= cutoff:
                continue
            if not dry_run:
                try:
                    path.unlink()
                except OSError:
                    continue
            removed.append(path)
    except OSError:
        # Listage impossible : on rend ce qui est déjà traité
        pass
    return sorted(removed)

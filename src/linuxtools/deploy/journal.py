"""Journal de déploiement : console + fichier, sans aucun secret.

Le module ne reçoit ni valeur de secret ni gestionnaire de credentials :
rien de sensible ne peut donc y entrer par construction. Les messages
des phases ne citent que des chemins et des noms de clés.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from linuxtools.logging.console_logger import ConsoleLogger
from linuxtools.logging.file_logger import FileLogger
from linuxtools.logging.paths import default_log_dir
from linuxtools.logging.retention import DEFAULT_RETENTION_DAYS, purge_old_logs
from linuxtools.systemd.validators import validate_service_name

if TYPE_CHECKING:
    from pathlib import Path

    from linuxtools.logging.base import Logger


@dataclass(frozen=True)
class DeployJournal:
    """Journal ouvert pour un déploiement.

    Attributes:
        logger: Logger à injecter dans ``Deployer.for_target``.
        path: Fichier du journal, ``None`` en dry-run.
    """

    logger: Logger
    path: Path | None


def _refuse_symlink(path: Path) -> None:
    """Refuse un dossier de journal qui serait un lien symbolique.

    Args:
        path: Dossier à contrôler.

    Raises:
        OSError: Si ``path`` est un lien symbolique.
    """
    if path.is_symlink():
        raise OSError(f"Dossier de journal refusé (lien symbolique) : {path}")


def open_deploy_journal(
    app_name: str,
    label: str,
    *,
    dry_run: bool,
    log_dir: Path | None = None,
    retention_days: int | None = DEFAULT_RETENTION_DAYS,
) -> DeployJournal:
    """Ouvre le journal d'un déploiement (console + fichier).

    Le fichier est ``<log_dir>/deploy/deploy_<label>_<AAAAMMJJ_HHMMSS>Z.log``
    (horodatage en UTC, d'où le suffixe ``Z`` ; dossier en 0700, fichier
    en clair 0600 ouvert sans suivre les liens symboliques). En dry-run,
    rien n'est créé sur disque. À l'ouverture, les anciens journaux
    (``deploy_*.log``) du dossier sont purgés (best-effort).

    Args:
        app_name: Nom de l'application (kebab-case), pour le dossier par
            défaut.
        label: Nom de la cible, repris dans le nom du fichier.
        dry_run: Si True, journal console seul, ``path`` vaut ``None``.
        log_dir: Dossier de logs de l'application ; défaut
            ``default_log_dir(app_name)``.
        retention_days: Âge, en jours, au-delà duquel les journaux de
            déploiement (``deploy_*.log``) du dossier sont supprimés à
            l'ouverture ; ``None`` désactive la purge. Sans effet en
            dry-run.

    Returns:
        Le journal ouvert (logger à injecter et chemin du fichier).

    Raises:
        ValueError: ``label`` ou ``app_name`` invalide, ou
            ``retention_days`` inférieur à 1.
        OSError: Dossier du journal lien symbolique ou inaccessible.
    """
    validate_service_name(app_name)
    validate_service_name(label)
    if retention_days is not None and retention_days < 1:
        raise ValueError("retention_days doit être supérieur ou égal à 1")
    if dry_run:
        return DeployJournal(ConsoleLogger(), None)

    parent = log_dir or default_log_dir(app_name)
    base = parent / "deploy"
    _refuse_symlink(parent)
    _refuse_symlink(base)
    existed = base.exists()
    base.mkdir(mode=0o700, parents=True, exist_ok=True)
    if existed:
        os.chmod(base, 0o700)

    stamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%SZ")
    path = base / f"deploy_{label}_{stamp}.log"
    logger = FileLogger(path, console_output=True, colored_console=True)
    if retention_days is not None:
        # Le nouveau journal est passé en keep : jamais purgé
        removed = purge_old_logs(
            base, "deploy_*.log", max_age_days=retention_days, keep=path
        )
        if removed:
            logger.log_info(
                f"Rétention : {len(removed)} ancien(s) journal(aux) "
                f"supprimé(s) (> {retention_days} j)"
            )
    return DeployJournal(logger, path)

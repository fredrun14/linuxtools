"""Dépôt de contenu texte sur une cible locale ou distante.

Primitive partagée par ConfigDeployer et SecretsProvisioner — écrit du
contenu généré en mémoire sur la cible, en TOCTOU-safe local ou via
l'executor injecté à distance.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from linuxtools.filesystem.linux import write_text_secure

if TYPE_CHECKING:
    from pathlib import Path

    from linuxtools.commands.base import CommandExecutor
    from linuxtools.logging.base import Logger


def deposit_content(
    executor: CommandExecutor,
    content: str,
    dest_path: Path,
    mode: int,
    *,
    is_remote: bool,
    logger: Logger | None = None,
) -> bool:
    """Dépose du contenu texte sur une cible (locale ou SSH).

    Args:
        executor: Exécuteur de commandes ciblant l'hôte. Utilisé
            uniquement quand `is_remote` est True.
        content: Contenu à écrire.
        dest_path: Chemin de destination sur la cible.
        mode: Permissions POSIX du fichier déposé.
        is_remote: True si `dest_path` désigne un chemin distant
            (choix explicite de l'appelant — jamais deviné).
        logger: Logger optionnel.

    Returns:
        True si le dépôt a réussi, False sinon.
    """
    if not is_remote:
        write_text_secure(dest_path, content, mode=mode)
        if logger is not None:
            logger.log_info(f"Contenu déposé (local) : {dest_path}")
        return True

    write_result = executor.run(["tee", str(dest_path)], stdin=content)
    if not write_result.success:
        if logger is not None:
            logger.log_error(
                f"Échec du dépôt distant de {dest_path} : "
                f"{write_result.stderr}"
            )
        return False

    chmod_result = executor.run(["chmod", format(mode, "03o"), str(dest_path)])
    if not chmod_result.success:
        if logger is not None:
            logger.log_error(
                f"Échec du chmod distant de {dest_path} : "
                f"{chmod_result.stderr}"
            )
        return False

    if logger is not None:
        logger.log_info(f"Contenu déposé (distant) : {dest_path}")
    return True

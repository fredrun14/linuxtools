"""ACL de répertoire partagé (groupe propriétaire, setgid, ACL par défaut)."""

import grp
import os
import stat
from pathlib import Path

from linuxtools.commands import CommandBuilder, LinuxCommandExecutor
from linuxtools.commands.base import CommandExecutor
from linuxtools.identity.base import _valider_nom
from linuxtools.logging import Logger


def ensure_shared_group_directory(
    path: str | Path,
    group: str,
    *,
    mode: int = 0o2770,
    executor: CommandExecutor | None = None,
    logger: Logger | None = None,
) -> None:
    """Garantit qu'un répertoire partagé appartient au groupe donné,
    porte le bit setgid et une ACL par défaut donnant rwx au groupe.

    Idempotent : ne change rien si le répertoire est déjà conforme.

    Note:
        Fenêtre TOCTOU résiduelle entre le chown/chmod par descripteur
        (sécurisé, ``O_NOFOLLOW``) et l'appel à ``setfacl`` (par
        chemin, sans équivalent par descripteur) : entre les deux,
        ``path`` pourrait en théorie être remplacé par un lien
        symbolique. Risque jugé faible (répertoire déjà possédé par
        root, opération root-only) et assumé, pas traité.

    Args:
        path: Répertoire cible (doit déjà exister).
        group: Nom du groupe Unix propriétaire (doit déjà exister —
            cf. ``LinuxGroupManager.ensure_group``).
        mode: Permissions POSIX à appliquer, bit setgid (0o2000) déjà
            inclus dans la valeur par défaut.
        executor: Exécuteur de commandes optionnel (pour ``setfacl``).
        logger: Logger optionnel.

    Raises:
        ValueError: Si ``group`` ne respecte pas la convention Unix.
        FileNotFoundError: Si ``path`` n'existe pas.
        OSError: Si ``path`` est un lien symbolique (protection
            anti-substitution), ou si chown/chmod échoue.
        KeyError: Si ``group`` est inconnu du système.
    """
    _valider_nom(group)
    gid = grp.getgrnam(group).gr_gid

    # Partie TOCTOU-safe (chown + setgid) : fd ouvert avec O_NOFOLLOW,
    # chown/chmod appliqués par descripteur — même modèle que
    # _open_secure dans filesystem/linux.py.
    fd = os.open(str(path), os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        current = os.fstat(fd)
        if current.st_gid != gid:
            os.fchown(fd, -1, gid)
        target_mode = stat.S_IMODE(mode) | stat.S_ISGID
        if stat.S_IMODE(current.st_mode) != target_mode:
            os.fchmod(fd, target_mode)
    finally:
        os.close(fd)

    # Partie ACL best-effort (par chemin — voir la note TOCTOU ci-dessus).
    # NFSv4 ne transporte pas les ACL POSIX classiques : setfacl échoue
    # systématiquement sur ce type de montage. On retombe alors sur
    # nfs4_setfacl (ACL natives NFSv4) ; si les deux échouent (serveur
    # NFS sans support ACL sur l'export, ext4 sans setfacl installé,
    # etc.), on se contente d'un avertissement — le groupe et le setgid
    # posés ci-dessus couvrent déjà l'essentiel du besoin.
    exec_ = executor or LinuxCommandExecutor(logger=logger)

    if _try_default_acl(exec_, path, group, tool="setfacl"):
        if logger:
            logger.log_info(
                f"[ensure_shared_group_directory] '{path}' : groupe "
                f"'{group}', setgid et ACL par défaut (POSIX) appliqués"
            )
        return

    if _try_default_acl(exec_, path, group, tool="nfs4_setfacl"):
        if logger:
            logger.log_info(
                f"[ensure_shared_group_directory] '{path}' : groupe "
                f"'{group}', setgid et ACL par défaut (NFSv4) appliqués"
            )
        return

    if logger:
        logger.log_warning(
            f"[ensure_shared_group_directory] Aucune ACL par défaut "
            f"applicable sur '{path}' (ni POSIX ni NFSv4 — serveur/fs non "
            f"compatible). Le groupe '{group}' et le setgid sont posés ; "
            f"les droits d'écriture des nouveaux fichiers pour ce groupe "
            f"dépendent désormais de l'umask du poste créateur."
        )


def _try_default_acl(
    executor: CommandExecutor,
    path: str | Path,
    group: str,
    *,
    tool: str,
) -> bool:
    """Tente de poser une ACL par défaut, sans jamais lever d'exception."""
    if tool == "setfacl":
        cmd = (
            CommandBuilder("setfacl")
            .with_options(["-d", "-m", f"g:{group}:rwx"])
            .with_args([str(path)])
            .build()
        )
    else:  # nfs4_setfacl
        cmd = (
            CommandBuilder("nfs4_setfacl")
            .with_options(["-a", f"A:fdig:{group}:RWX"])
            .with_args([str(path)])
            .build()
        )
    result = executor.run(cmd)
    return result.success

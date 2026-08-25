"""Audit en lecture seule des identités Unix (détection d'écart)."""

import grp
import pwd


def group_gid_drift(name: str, expected_gid: int) -> int | None:
    """Compare le GID réel d'un groupe existant au GID attendu.

    Args:
        name: Nom du groupe à vérifier.
        expected_gid: GID attendu (référence).

    Returns:
        Le GID réel si le groupe existe avec un GID différent de
        ``expected_gid``. ``None`` si le groupe est conforme ou absent
        (l'absence n'est pas un écart : c'est un cas de création, à
        traiter via ``LinuxGroupManager.ensure_group``).
    """
    try:
        existing = grp.getgrnam(name)
    except KeyError:
        return None
    if existing.gr_gid != expected_gid:
        return existing.gr_gid
    return None


def user_uid_drift(name: str, expected_uid: int) -> int | None:
    """Compare l'UID réel d'un utilisateur existant à l'UID attendu.

    Args:
        name: Nom d'utilisateur à vérifier.
        expected_uid: UID attendu (référence).

    Returns:
        L'UID réel si l'utilisateur existe avec un UID différent de
        ``expected_uid``. ``None`` si conforme ou absent.
    """
    try:
        existing = pwd.getpwnam(name)
    except KeyError:
        return None
    if existing.pw_uid != expected_uid:
        return existing.pw_uid
    return None

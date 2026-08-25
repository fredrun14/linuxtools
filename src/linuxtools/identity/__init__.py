"""Gestion idempotente des groupes et utilisateurs Unix.

Provisionne des comptes de service via ``groupadd``/``usermod`` en ne
rejouant que la commande nécessaire à la convergence — jamais de
suppression, jamais d'élévation de privilèges implicite.

Groupes:
- GroupManagerBase: Interface abstraite (ensure_group)
- LinuxGroupManager: Implémentation Linux via groupadd/groupmod

Utilisateurs:
- UserManagerBase: Interface abstraite (ensure_user, ensure_user_groups)
- LinuxUserManager: Implémentation Linux via useradd/usermod

Audit (lecture seule):
- group_gid_drift: Détecte un écart de GID sur un groupe existant
- user_uid_drift: Détecte un écart d'UID sur un utilisateur existant

Exemple d'utilisation:
    from linuxtools import FileLogger
    from linuxtools.identity import LinuxGroupManager, LinuxUserManager

    logger = FileLogger("/var/log/provision.log")
    LinuxGroupManager(logger=logger).ensure_group("appsvc", gid=1500)
    LinuxUserManager(logger=logger).ensure_user(
        name="appsvc", uid=1500, shell="/sbin/nologin",
        comment="Compte de service applicatif", create_home=False,
    )

Exemple d'utilisation (audit d'écart, LAN/NFS) :
    from linuxtools.identity import group_gid_drift

    drift = group_gid_drift("appsvc", expected_gid=1500)
    if drift is not None:
        print(f"GID réel {drift} != attendu 1500 — correction requise")
"""

from linuxtools.identity.audit import group_gid_drift, user_uid_drift
from linuxtools.identity.base import GroupManagerBase, UserManagerBase
from linuxtools.identity.group import LinuxGroupManager
from linuxtools.identity.user import LinuxUserManager

__all__ = [
    "group_gid_drift",
    "GroupManagerBase",
    "LinuxGroupManager",
    "LinuxUserManager",
    "user_uid_drift",
    "UserManagerBase",
]

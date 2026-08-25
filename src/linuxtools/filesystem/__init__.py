"""Module de gestion des fichiers, TOCTOU-safe.

Fournit la lecture/écriture/suppression de fichiers, la sauvegarde
simple et la copie récursive, avec pour référence de sécurité le
pattern ``O_NOFOLLOW`` + ``os.fchmod(fd)`` : ouvrir sans suivre les
symlinks puis fixer les permissions sur le descripteur déjà ouvert,
plutôt qu'en deux temps sur un chemin (fenêtre de substitution).

Fichiers:
- FileManager: Interface abstraite (create_file, read_file, delete_file)
- LinuxFileManager: Implémentation Linux, TOCTOU-safe
- write_text_secure: Fonction bas niveau — écriture sécurisée d'un fichier

Sauvegarde:
- FileBackup: Interface abstraite (backup, restore)
- LinuxFileBackup: Implémentation Linux, TOCTOU-safe (O_NOFOLLOW)

Copie récursive:
- copytree_secure: Copie un arbre de fichiers avec protection par fichier
  (la création des répertoires suit les symlinks, contrairement à la
  copie des fichiers eux-mêmes — voir la note du module)

ACL de répertoire partagé:
- ensure_shared_group_directory: Pose le groupe propriétaire, le bit
  setgid et une ACL par défaut (``g:<group>:rwx``) sur un répertoire
  déjà existant — TOCTOU-safe pour le chown/chmod (par descripteur),
  ``setfacl`` restant par chemin (voir la note de la fonction)

Exemple d'utilisation:
    from linuxtools import FileLogger
    from linuxtools.filesystem import LinuxFileManager, LinuxFileBackup

    logger = FileLogger("/var/log/app.log")
    manager = LinuxFileManager(logger=logger)
    manager.create_file(
        "/etc/mon-outil/config.toml", "[log]\\nlevel = 'INFO'\\n"
    )

    backup = LinuxFileBackup(logger=logger)
    backup.backup(
        "/etc/mon-outil/config.toml", "/etc/mon-outil/config.toml.bak"
    )

Exemple d'utilisation (copie récursive):
    from linuxtools.filesystem import copytree_secure

    copytree_secure("/etc/mon-outil", "/etc/mon-outil.bak")

Exemple d'utilisation (ACL de répertoire partagé):
    from linuxtools.filesystem import ensure_shared_group_directory

    ensure_shared_group_directory("/srv/partage", "partage-lan")
"""

from linuxtools.filesystem.acl import ensure_shared_group_directory
from linuxtools.filesystem.backup import (
    FileBackup,
    LinuxFileBackup,
    copytree_secure,
)
from linuxtools.filesystem.base import FileManager
from linuxtools.filesystem.linux import (
    LinuxFileManager,
    write_text_secure,
)

__all__ = [
    "FileManager",
    "LinuxFileManager",
    "write_text_secure",
    "FileBackup",
    "LinuxFileBackup",
    "copytree_secure",
    "ensure_shared_group_directory",
]

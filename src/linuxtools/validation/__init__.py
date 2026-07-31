"""Module de validation de préconditions système.

Chaque validateur vérifie une précondition avant une opération risquée
(écriture, installation) et lève une exception standard (ValueError,
PermissionError) plutôt qu'une exception métier — au consommateur de
wrapper vers ses propres exceptions si besoin.

Interface:
- Validator: Contrat commun (validate)

Chemins de fichiers:
- PathChecker: Vérifie que les répertoires parents existent
  (résout les chemins pour prévenir les traversées — OWASP A03)
- PathCheckerPermission: Vérifie les permissions d'un chemin
- PathCheckerWorldWritable: Détecte un chemin accessible en écriture
  par tous (world-writable)
- PathCheckerGroupAccess: Vérifie l'appartenance de groupe d'un chemin
- PathCheckerMountPoint: Vérifie qu'un chemin est un point de montage

Commandes système:
- SystemCommandValidator: Vérifie la présence de commandes requises
  dans le PATH (shutil.which), lève MissingDependencyError sinon

Exemple d'utilisation:
    from linuxtools.validation import PathChecker, SystemCommandValidator

    PathChecker(["/etc/mon-outil/config.toml"]).validate()
    SystemCommandValidator({
        "borg": "sudo dnf install borgbackup",
        "rsync": "sudo dnf install rsync",
    }).validate()
"""

from linuxtools.validation.base import Validator
from linuxtools.validation.path_checker_exist import PathChecker
from linuxtools.validation.path_checker_group_access import (
    PathCheckerGroupAccess,
)
from linuxtools.validation.path_checker_mount_point import (
    PathCheckerMountPoint,
)
from linuxtools.validation.path_checker_permission import (
    PathCheckerPermission,
)
from linuxtools.validation.path_checker_world_writable import (
    PathCheckerWorldWritable,
)
from linuxtools.validation.system import SystemCommandValidator

__all__ = [
    "PathChecker",
    "PathCheckerMountPoint",
    "PathCheckerPermission",
    "PathCheckerWorldWritable",
    "PathCheckerGroupAccess",
    "SystemCommandValidator",
    "Validator",
]

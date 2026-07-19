"""Exceptions pour le module deploy.

Ce module définit les exceptions métier levées lors d'un
déploiement/màj d'outil Python sur hôte. DeployError hérite
d'ApplicationError pour s'intégrer dans la chaîne d'error
handlers (ConsoleErrorHandler, LoggerErrorHandler).
"""

from linuxtools.errors.exceptions import ApplicationError


class DeployError(ApplicationError):
    """Levée quand une phase de déploiement échoue sans filet.

    Cas d'usage principal : échec de la sauvegarde du venv avant
    installation. On ne poursuit jamais l'installation sans backup
    valide — perdre le filet de rollback casserait le besoin
    fondamental du module (cf. CDC §1, robustesse).
    """

"""Validateur de présence de commandes système."""

# stdlib
import shutil

# local
from linuxtools.errors.exceptions import MissingDependencyError
from linuxtools.validation.base import Validator


class SystemCommandValidator(Validator):
    """Vérifie la présence de commandes système requises.

    Utilise shutil.which() pour tester la disponibilité de chaque
    commande dans le PATH courant. Lève MissingDependencyError avec
    les instructions d'installation si des commandes sont absentes.

    Attributes:
        _requirements: Dictionnaire commande → instruction d'installation.

    Example:
        >>> validator = SystemCommandValidator({
        ...     "borg": "sudo dnf install borgbackup",
        ...     "rsync": "sudo dnf install rsync",
        ... })
        >>> validator.validate()
    """

    def __init__(self, requirements: dict[str, str]) -> None:
        """Initialise le validateur avec les dépendances requises.

        Args:
            requirements: Dictionnaire {commande: instruction}.
                La commande est le nom de l'exécutable (ex: 'borg').
                L'instruction est le message d'aide à afficher
                (ex: 'sudo dnf install borgbackup').
        """
        self._requirements = requirements

    def validate(self) -> None:
        """Vérifie que toutes les commandes requises sont disponibles.

        Raises:
            MissingDependencyError: Si une ou plusieurs commandes
                sont introuvables dans le PATH.
        """
        missing = self.missing_commands()
        if not missing:
            return
        lines = ["Commandes système manquantes :"]
        for cmd in missing:
            lines.append(f"  - {self._requirements[cmd]}")
        raise MissingDependencyError("\n".join(lines))

    def missing_commands(self) -> list[str]:
        """Retourne la liste des commandes absentes du PATH.

        Returns:
            Liste des noms de commandes non trouvées.
            Liste vide si toutes sont présentes.
        """
        return [
            cmd
            for cmd in self._requirements
            if shutil.which(cmd) is None
        ]

"""ConsoleErrorHandler (générique, configurable)."""
import sys

from linux_python_utils.errors.base import ErrorHandler
from linux_python_utils.errors.exceptions import (
    ApplicationError,
    ConfigurationError,
    MissingDependencyError,
    InstallationError,
    AppPermissionError,
)

# Solutions par défaut : surchargeables à l'instanciation
_SOLUTIONS_PAR_DEFAUT: dict[type[Exception], str] = {
    MissingDependencyError: (
        "\n🔧 Solution : Installez les dépendances manquantes comme indiqué."
    ),
    AppPermissionError: (
        "\n🔧 Solution : Exécutez avec sudo ou vérifiez les permissions."
    ),
    ConfigurationError: (
        "\n🔧 Solution : Vérifiez votre fichier de configuration."
    ),
    InstallationError: (
        "\n🔧 Solution : Consultez les logs pour plus de détails."
    ),
}


class ConsoleErrorHandler(ErrorHandler):
    """Handler pour afficher les erreurs dans la console.

    Distingue les erreurs connues (isinstance de base_error_type)
    des erreurs inattendues. Affiche sur stderr un message de solution
    extrait du dictionnaire injecté via correspondance isinstance.
    """

    def __init__(
        self,
        base_error_type: type[Exception] = ApplicationError,
        solutions: dict[type[Exception], str] | None = None,
    ) -> None:
        """Initialise le handler console.

        Args:
            base_error_type: Classe de base pour distinguer erreurs
                connues des erreurs inconnues
                (défaut: ApplicationError).
            solutions: Dictionnaire {TypeException: "message solution"}.
                Les projets passent leurs propres mappings à
                l'instanciation. Si None, les solutions par défaut
                sont utilisées.
        """
        self.base_error_type = base_error_type
        self.solutions = (
            solutions if solutions is not None else dict(_SOLUTIONS_PAR_DEFAUT)
        )

    def handle(self, error: Exception) -> None:
        """Affiche l'erreur dans la console avec des messages utilisateur.

        Args:
            error: L'exception à afficher.
        """
        if isinstance(error, self.base_error_type):
            self._handle_known_error(error)
        else:
            self._handle_unknown_error(error)

    def _handle_known_error(self, error: Exception) -> None:
        """Gère les erreurs connues.

        Affiche le type et le message de l'erreur, suivi de la solution
        extraite du dictionnaire injecté (correspondance isinstance).

        Args:
            error: L'exception métier à traiter.
        """
        print(f"\n🛑 {type(error).__name__}: {str(error)}", file=sys.stderr)
        solution = next(
            (
                msg
                for exc_type, msg in self.solutions.items()
                if isinstance(error, exc_type)
            ),
            None,
        )
        if solution:
            print(solution, file=sys.stderr)
        else:
            print(
                "\n🔧 Solution : Voir les suggestions ci-dessus.",
                file=sys.stderr,
            )

    def _handle_unknown_error(self, error: Exception) -> None:
        """Gère les erreurs inattendues.

        Args:
            error: L'exception non prévue à afficher.
        """
        print(f"\n💥 Erreur inattendue: {str(error)}", file=sys.stderr)
        print(f"Type: {type(error).__name__}", file=sys.stderr)
        print(
            "\n📋 Cela peut être un bug."
            " Veuillez ouvrir une issue avec ces informations.",
            file=sys.stderr,
        )

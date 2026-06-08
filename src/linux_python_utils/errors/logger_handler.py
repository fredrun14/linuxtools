"""LoggerErrorHandler."""
from linux_python_utils.errors.base import ErrorHandler
from linux_python_utils.errors.exceptions import ApplicationError
from linux_python_utils.logging.base import Logger


class LoggerErrorHandler(ErrorHandler):
    """Handler pour logger les erreurs.

    Enregistre les erreurs dans le fichier de log via le Logger
    injecté au constructeur.
    """

    def __init__(
        self,
        logger: Logger,
        base_error_type: type[Exception] = ApplicationError,
    ) -> None:
        """Initialise le handler avec un logger.

        Args:
            logger: Instance de Logger pour l'enregistrement des erreurs.
            base_error_type: Classe de base pour distinguer erreurs
                connues des erreurs inconnues (défaut: ApplicationError).
        """
        self._logger = logger
        self._base_error_type = base_error_type

    def handle(self, error: Exception) -> None:
        """Log l'erreur avec un préfixe indiquant si elle est attendue.

        Args:
            error: L'exception à logger.
        """
        detail = f"{type(error).__name__}: {error}"
        if isinstance(error, self._base_error_type):
            self._logger.log_error(detail)
        else:
            self._logger.log_error(f"Erreur inattendue: {detail}")

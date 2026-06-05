from collections.abc import Callable

from linux_python_utils import Logger
from linux_python_utils.errors.exceptions import RollbackError


class ErrorContext:
    """Contexte pour la gestion des erreurs avec rollback.

    Maintient une liste d'actions de rollback à exécuter en cas
    d'erreur pendant l'installation.
    """

    def __init__(self, logger: Logger) -> None:
        """Initialise le contexte de rollback.

        Args:
            logger: Instance de Logger pour tracer les opérations de rollback.
        """
        self.logger = logger
        self.rollback_actions: list[tuple[Callable, str]] = []

    def add_rollback_action(self, action: Callable, label: str) -> None:
        """Ajoute une action de rollback avec un libellé descriptif.

        Args:
            action: Callable à exécuter lors du rollback.
            label: Description de l'action pour les logs.
        """
        self.rollback_actions.append((action, label))

    def execute_rollback(self) -> None:
        """Exécute toutes les actions de rollback en ordre inverse.

        Toutes les actions sont tentées même si certaines échouent.

        Raises:
            RollbackError: Si une ou plusieurs actions de rollback échouent.
        """
        self.logger.log_info("Début du rollback...")

        rollback_errors: list[str] = []
        for action, label in reversed(self.rollback_actions):
            try:
                action()
                self.logger.log_info(f"Rollback réussi: {label}")
            except Exception as e:
                rollback_errors.append(str(e))
                self.logger.log_error(f"Échec du rollback ({label}): {e}")

        if rollback_errors:
            self.logger.log_warning(
                f"Rollback partiel."
                f" {len(rollback_errors)} erreurs lors du rollback."
            )
            raise RollbackError(
                f"Rollback partiel : {len(rollback_errors)} action(s) en échec"
            )
        else:
            self.logger.log_info("Rollback terminé avec succès.")

    def handle_error_with_rollback(self, error: Exception) -> None:
        """Gère une erreur et exécute le rollback.

        Le RollbackError éventuel est capturé car déjà loggé
        dans execute_rollback.

        Args:
            error: L'exception ayant déclenché le rollback.
        """
        self.logger.log_error(f"Erreur nécessitant rollback: {str(error)}")

        if self.rollback_actions:
            try:
                self.execute_rollback()
            except RollbackError:
                pass  # Déjà loggé dans execute_rollback
        else:
            self.logger.log_info("Aucune action de rollback nécessaire.")

    def clear_rollback_actions(self) -> None:
        """Efface toutes les actions de rollback enregistrées."""
        self.rollback_actions.clear()

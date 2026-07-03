"""Interface abstraite pour le logging."""

from abc import ABC, abstractmethod


class Logger(ABC):
    """Interface pour le système de logging."""

    @abstractmethod
    def log_info(self, message: str) -> None:
        """Log un message d'information."""
        ...

    @abstractmethod
    def log_warning(self, message: str) -> None:
        """Log un avertissement."""
        ...

    @abstractmethod
    def log_error(self, message: str) -> None:
        """Log une erreur."""
        ...

    def log_success(self, message: str) -> None:
        """Log un message de succès (défaut : délègue à log_info)."""
        self.log_info(message)

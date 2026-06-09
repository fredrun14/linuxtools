"""Interfaces abstraites et structures de données pour l'exécution
de commandes système.

Ce module définit :
    - CommandResult : Résultat immuable d'une exécution de commande.
    - CommandExecutor : Interface abstraite pour les exécuteurs.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class CommandResult:
    """Résultat de l'exécution d'une commande système.

    Attributes:
        command: Commande exécutée sous forme de tuple immuable.
        return_code: Code de retour du processus.
        stdout: Sortie standard capturée.
        stderr: Sortie d'erreur capturée.
        success: True si la commande a réussi (code 0).
        duration: Durée d'exécution en secondes.
        executed_as_root: True si la commande a été exécutée en root.
    """

    command: tuple[str, ...]
    return_code: int
    stdout: str
    stderr: str
    success: bool
    duration: float
    executed_as_root: bool = False

    def __post_init__(self) -> None:
        """Convertit la commande en tuple pour l'immutabilité."""
        object.__setattr__(self, "command", tuple(self.command))


class CommandExecutor(ABC):
    """Interface abstraite pour l'exécution de commandes système."""

    @abstractmethod
    def run(
        self,
        command: list[str],
        env: dict[str, str] | None = None,
        cwd: str | None = None,
        timeout: int | None = None,
    ) -> CommandResult:
        """Exécute une commande et retourne le résultat.

        Args:
            command: Commande sous forme de liste.
            env: Variables d'environnement supplémentaires.
            cwd: Répertoire de travail.
            timeout: Timeout en secondes.

        Returns:
            Résultat de l'exécution.
        """
        pass

    @abstractmethod
    def run_streaming(
        self,
        command: list[str],
        env: dict[str, str] | None = None,
        cwd: str | None = None,
        timeout: int | None = None,
        merge_stderr: bool = False,
    ) -> CommandResult:
        """Exécute une commande avec sortie en temps réel.

        Args:
            command: Commande sous forme de liste.
            env: Variables d'environnement supplémentaires.
            cwd: Répertoire de travail.
            timeout: Timeout en secondes.
            merge_stderr: Si True, fusionne stderr dans stdout via
                subprocess.STDOUT — élimine le risque de deadlock
                causé par un pipe stderr plein, au prix de la
                séparation stdout/stderr dans le résultat.

        Returns:
            Résultat de l'exécution.
        """
        pass

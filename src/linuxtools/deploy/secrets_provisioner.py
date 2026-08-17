"""Provisioning de secrets vers la cible d'un déploiement."""

from __future__ import annotations

from typing import TYPE_CHECKING

from linuxtools.credentials.exceptions import CredentialNotFoundError
from linuxtools.deploy.content_writer import deposit_content

if TYPE_CHECKING:
    from linuxtools.commands.base import CommandExecutor
    from linuxtools.credentials.manager import CredentialManager
    from linuxtools.deploy.models import DeployTarget, SecretsSpec
    from linuxtools.logging.base import Logger


class SecretsProvisioner:
    """Provisionne des secrets vers la cible d'un déploiement.

    Résout les valeurs via un CredentialManager injecté (jamais lues
    depuis DeployConfig — cf. CDC Q-01) et les écrit sous forme de
    fichier EnvironmentFile= (KEY=value par ligne).

    Attributes:
        _credentials: CredentialManager injecté pour la résolution.
        _logger: Logger optionnel.
    """

    def __init__(
        self,
        credentials: CredentialManager,
        logger: Logger | None = None,
    ) -> None:
        """Initialise le provisionneur de secrets.

        Args:
            credentials: CredentialManager injecté (résolution
                locale, jamais sur la cible).
            logger: Logger optionnel.
        """
        self._credentials = credentials
        self._logger = logger

    def provision(
        self,
        spec: SecretsSpec,
        target: DeployTarget,
        executor: CommandExecutor,
    ) -> bool:
        """Résout et dépose les secrets de `spec` sur la cible.

        Args:
            spec: Spécification du provisioning (service, clés,
                chemin).
            target: Cible du déploiement (détermine local vs
                distant).
            executor: Exécuteur de commandes ciblant `target`.

        Returns:
            True si le provisioning a réussi, False si une clé est
            introuvable ou si le dépôt échoue.
        """
        resolved: dict[str, str] = {}
        for key in spec.keys:
            try:
                value = self._credentials.require(key)
            except CredentialNotFoundError as exc:
                self._log_error(f"Secret introuvable : {key} ({exc})")
                return False
            if "\n" in value:
                self._log_error(
                    f"Valeur invalide pour la clé {key} : "
                    "retour à la ligne interdit"
                )
                return False
            resolved[key] = value

        content = (
            "\n".join(f"{key}={value}" for key, value in resolved.items())
            + "\n"
            if resolved
            else ""
        )

        return deposit_content(
            executor,
            content,
            spec.dest_path,
            spec.mode,
            is_remote=target.is_remote,
            logger=self._logger,
        )

    def _log_error(self, message: str) -> None:
        """Logue une erreur si un logger est configuré.

        Args:
            message: Message à logguer — ne doit jamais contenir de
                valeur de secret.
        """
        if self._logger is not None:
            self._logger.log_error(message)

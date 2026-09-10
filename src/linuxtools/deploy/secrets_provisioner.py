"""Provisioning de secrets vers la cible d'un déploiement."""

from __future__ import annotations

from typing import TYPE_CHECKING

from linuxtools.credentials.exceptions import CredentialNotFoundError
from linuxtools.deploy.destinations import destination_for
from linuxtools.deploy.sinks import ContentSink

if TYPE_CHECKING:
    from collections.abc import Callable

    from linuxtools.commands.base import CommandExecutor
    from linuxtools.credentials.manager import CredentialManager
    from linuxtools.deploy.models import DeployTarget, SecretsSpec
    from linuxtools.logging.base import Logger


class SecretsProvisioner:
    """Provisionne des secrets vers la cible d'un déploiement.

    Résout les valeurs via une factory de CredentialManager injectée,
    un manager par service (jamais lues depuis DeployConfig — cf.
    CDC Q-01), et les écrit sous forme de fichier EnvironmentFile=
    (KEY=value par ligne).

    Attributes:
        _credential_manager_factory: Factory injectée pour la
            résolution, un CredentialManager par service.
        _logger: Logger optionnel.
    """

    def __init__(
        self,
        credential_manager_factory: Callable[[str], CredentialManager],
        logger: Logger | None = None,
    ) -> None:
        """Initialise le provisionneur de secrets.

        Args:
            credential_manager_factory: Factory résolvant un
                CredentialManager pour un nom de service donné (ex.
                CredentialManager.from_dotenv). Appelée une fois par
                service distinct rencontré dans une SecretsSpec.
            logger: Logger optionnel.
        """
        self._credential_manager_factory = credential_manager_factory
        self._logger = logger

    def provision(
        self,
        spec: SecretsSpec,
        target: DeployTarget,
        executor: CommandExecutor,
    ) -> bool:
        """Résout et dépose les secrets de `spec` sur la cible.

        Args:
            spec: Spécification du provisioning (paires service/clé,
                chemin).
            target: Cible du déploiement (détermine local vs
                distant).
            executor: Exécuteur de commandes ciblant `target`.

        Returns:
            True si le provisioning a réussi, False si une clé est
            introuvable ou si le dépôt échoue.
        """
        managers: dict[str, CredentialManager] = {}
        resolved: dict[str, str] = {}
        for service, key in spec.keys:
            if service not in managers:
                managers[service] = self._credential_manager_factory(service)
            try:
                value = managers[service].require(key)
            except CredentialNotFoundError as exc:
                self._log_error(
                    f"Secret introuvable : {service}/{key} ({exc})"
                )
                return False
            if "\n" in value:
                self._log_error(
                    f"Valeur invalide pour {service}/{key} : "
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

        sink = ContentSink(
            destination_for(target, executor), logger=self._logger
        )
        return sink.write(spec.dest_path, content, mode=spec.mode)

    def _log_error(self, message: str) -> None:
        """Logue une erreur si un logger est configuré.

        Args:
            message: Message à logguer — ne doit jamais contenir de
                valeur de secret.
        """
        if self._logger is not None:
            self._logger.log_error(message)

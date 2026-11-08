"""Provisioning de secrets vers la cible d'un déploiement."""

from __future__ import annotations

from typing import TYPE_CHECKING

from linuxtools.credentials.exceptions import CredentialNotFoundError
from linuxtools.deploy.destinations import destination_for
from linuxtools.deploy.models import PhaseOutcome
from linuxtools.deploy.sinks import ContentSink

if TYPE_CHECKING:
    from collections.abc import Callable

    from linuxtools.commands.base import CommandExecutor
    from linuxtools.credentials.manager import CredentialManager
    from linuxtools.deploy.models import DeployTarget, SecretsSpec
    from linuxtools.logging.base import Logger

_SKELETON_HEADER = (
    "# Fichier d'environnement du service.\n"
    "# Renseigner les valeurs sur ce poste : elles ne sont jamais "
    "copiées d'un autre poste.\n"
)


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
        credential_manager_factory: (
            Callable[[str], CredentialManager] | None
        ) = None,
        logger: Logger | None = None,
    ) -> None:
        """Initialise le provisionneur de secrets.

        Args:
            credential_manager_factory: Factory résolvant un
                CredentialManager pour un nom de service donné (ex.
                CredentialManager.from_dotenv). Appelée une fois par
                service distinct rencontré dans une SecretsSpec.
                Optionnelle : requise seulement en mode ``"source"``.
            logger: Logger optionnel.
        """
        self._credential_manager_factory = credential_manager_factory
        self._logger = logger

    def provision(
        self,
        spec: SecretsSpec,
        target: DeployTarget,
        executor: CommandExecutor,
    ) -> PhaseOutcome:
        """Dépose les secrets de `spec` sur la cible selon `values_from`.

        Args:
            spec: Spécification du provisioning (paires service/clé,
                chemin).
            target: Cible du déploiement (détermine local vs
                distant).
            executor: Exécuteur de commandes ciblant `target`.

        Returns:
            `PhaseOutcome(True)` si le provisioning a réussi (mode
            ``"target"`` : avec un message de rapport sur le fichier créé
            ou déjà présent), `PhaseOutcome(False)` si une clé est
            introuvable ou si le dépôt échoue.
        """
        if spec.values_from == "target":
            return self._provision_skeleton(spec, target, executor)
        return self._provision_from_source(spec, target, executor)

    def _provision_from_source(
        self,
        spec: SecretsSpec,
        target: DeployTarget,
        executor: CommandExecutor,
    ) -> PhaseOutcome:
        """Résout les valeurs sur le poste source et les dépose.

        Args:
            spec: Spécification du provisioning.
            target: Cible du déploiement.
            executor: Exécuteur ciblant `target`.

        Returns:
            `PhaseOutcome(True)` si le dépôt a réussi, sinon
            `PhaseOutcome(False)`.
        """
        factory = self._credential_manager_factory
        if factory is None:
            self._log_error(
                "Provisioning impossible : factory de CredentialManager "
                "requise en mode 'source'."
            )
            return PhaseOutcome(False)
        managers: dict[str, CredentialManager] = {}
        resolved: dict[str, str] = {}
        for service, key in spec.keys:
            if service not in managers:
                managers[service] = factory(service)
            try:
                value = managers[service].require(key)
            except CredentialNotFoundError as exc:
                self._log_error(
                    f"Secret introuvable : {service}/{key} ({exc})"
                )
                return PhaseOutcome(False)
            if "\n" in value:
                self._log_error(
                    f"Valeur invalide pour {service}/{key} : "
                    "retour à la ligne interdit"
                )
                return PhaseOutcome(False)
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
        return PhaseOutcome(
            sink.write(spec.dest_path, content, mode=spec.mode)
        )

    def _provision_skeleton(
        self,
        spec: SecretsSpec,
        target: DeployTarget,
        executor: CommandExecutor,
    ) -> PhaseOutcome:
        """Crée un squelette ``CLE=`` sans valeur, sans jamais écraser.

        N'appelle pas la factory et ne lit ni l'environnement ni aucun
        fichier : aucun secret du poste source ne peut être copié. Le
        fichier n'est créé que s'il est absent (``if_exists="keep"``).

        Args:
            spec: Spécification du provisioning.
            target: Cible du déploiement.
            executor: Exécuteur ciblant `target`.

        Returns:
            `PhaseOutcome(True, (message,))` (créé ou déjà présent), ou
            `PhaseOutcome(False, ...)` si l'écriture échoue.
        """
        keys = tuple(dict.fromkeys(key for _service, key in spec.keys))
        content = _SKELETON_HEADER + "".join(f"{key}=\n" for key in keys)
        outcome = destination_for(target, executor, self._logger).write(
            spec.dest_path, content, spec.mode, if_exists="keep"
        )
        if not outcome.success:
            self._log_error(outcome.detail)
            return PhaseOutcome(False, ("Provisioning des secrets échoué.",))
        names = ", ".join(keys)
        if outcome.kept:
            return PhaseOutcome(
                True,
                (
                    f"Fichier de secrets déjà présent, non modifié : "
                    f"{spec.dest_path} (clés attendues : {names})",
                ),
            )
        return PhaseOutcome(
            True,
            (
                f"Fichier de secrets créé ({spec.mode:04o}) : "
                f"{spec.dest_path} — valeurs à renseigner sur ce poste : "
                f"{names}",
            ),
        )

    def _log_error(self, message: str) -> None:
        """Logue une erreur si un logger est configuré.

        Args:
            message: Message à logguer — ne doit jamais contenir de
                valeur de secret.
        """
        if self._logger is not None:
            self._logger.log_error(message)

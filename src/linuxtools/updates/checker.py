"""Vérification de mise à jour disponible via les releases Forgejo.

Fonction réutilisable par toute application CLI du homelab : compare sa
version installée à la dernière release publiée sur son dépôt Forgejo.
Ne déclenche jamais de mise à jour — informe seulement (même principe
que linuxtools.deploy.check_target_version).
"""

from __future__ import annotations

from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version
from typing import TYPE_CHECKING

from webapitools.core.exceptions import ApiError

from linuxtools.updates.version_compare import is_newer

if TYPE_CHECKING:
    from webapitools.apps.forgejo import ForgejoClient

    from linuxtools.logging.base import Logger


@dataclass(frozen=True)
class UpdateCheckResult:
    """Résultat d'une vérification de mise à jour.

    Attributes:
        package: Nom du paquet vérifié (distribution installée).
        current_version: Version actuellement installée.
        latest_version: Dernière version publiée sur Forgejo, ou None
            si non déterminable (réseau, pas de release, format).
        update_available: True si une version plus récente existe.
            Toujours False si checked est False.
        checked: True si la comparaison a pu être menée à son terme.
        detail: Message explicatif (raison si checked=False, résumé
            lisible sinon) — jamais vide, toujours affichable tel quel.
    """

    package: str
    current_version: str
    latest_version: str | None
    update_available: bool
    checked: bool
    detail: str


def check_for_update(
    package: str,
    owner: str,
    repo: str,
    client: ForgejoClient,
    logger: Logger | None = None,
) -> UpdateCheckResult:
    """Compare la version installée à la dernière release Forgejo.

    Ne lève jamais d'exception pour un cas attendu (réseau injoignable,
    aucune release, format de version non reconnu, paquet non
    installé) — le résultat porte toujours l'information, la fonction
    ne fait jamais planter l'appelant.

    Args:
        package: Nom de distribution du paquet appelant (celui utilisé
            à l'installation, ex. "backup-py-manager" — pas
            nécessairement le nom du module importable).
        owner: Propriétaire du dépôt sur Forgejo.
        repo: Nom du dépôt sur Forgejo.
        client: Client Forgejo déjà authentifié (construit par
            l'appelant, ex. via ForgejoClient.from_credentials(...)).
        logger: Logger optionnel (linuxtools.logging.base.Logger) pour
            tracer les cas dégradés en warning.

    Returns:
        UpdateCheckResult toujours renseigné.
    """
    try:
        current_version = version(package)
    except PackageNotFoundError:
        return UpdateCheckResult(
            package=package,
            current_version="0.0.0+unknown",
            latest_version=None,
            update_available=False,
            checked=False,
            detail=f"paquet {package!r} non installé localement",
        )

    try:
        release = client.get_latest_release(owner, repo)
    except ApiError as exc:
        message = f"Forgejo {owner}/{repo} injoignable : {exc}"
        if logger:
            logger.log_warning(message)
        return UpdateCheckResult(
            package=package,
            current_version=current_version,
            latest_version=None,
            update_available=False,
            checked=False,
            detail=message,
        )

    if release is None:
        detail = f"aucune release publiée sur {owner}/{repo}"
        if logger:
            logger.log_warning(detail)
        return UpdateCheckResult(
            package=package,
            current_version=current_version,
            latest_version=None,
            update_available=False,
            checked=False,
            detail=detail,
        )

    latest_version = release.get("tag_name", "")

    comparison = is_newer(latest_version, current_version)
    if comparison is None:
        detail = (
            f"format de version non reconnu : "
            f"installé={current_version!r} "
            f"forgejo={latest_version!r}"
        )
        if logger:
            logger.log_warning(detail)
        return UpdateCheckResult(
            package=package,
            current_version=current_version,
            latest_version=latest_version,
            update_available=False,
            checked=False,
            detail=detail,
        )

    detail = (
        f"{package} {current_version} -> {latest_version} disponible"
        if comparison
        else f"{package} {current_version} déjà à jour"
    )
    if logger:
        logger.log_info(detail)
    return UpdateCheckResult(
        package=package,
        current_version=current_version,
        latest_version=latest_version,
        update_available=comparison,
        checked=True,
        detail=detail,
    )


def format_update_notice(result: UpdateCheckResult) -> str | None:
    """Formate un message d'invite à la mise à jour, prêt à afficher.

    Args:
        result: Résultat d'un appel à check_for_update.

    Returns:
        Message à afficher (ex. sur stdout au démarrage d'une CLI) si
        une mise à jour est disponible, None sinon (y compris si
        checked est False — pas de bruit sur un échec de vérification).
    """
    if not result.checked or not result.update_available:
        return None

    return (
        f"Une nouvelle version de {result.package} est disponible : "
        f"{result.current_version} -> {result.latest_version}"
    )

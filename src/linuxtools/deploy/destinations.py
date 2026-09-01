"""Destinations d'écriture typées — où écrire, locale ou distante.

Rend l'incohérence executor/cible irreprésentable : `LocalDestination`
et `RemoteDestination(executor)` sont solidaires de leur exécuteur, il
n'existe plus de booléen `is_remote` circulant séparément (cf.
invariant projet dans `CONTEXT.md`).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar, Protocol

from linuxtools.filesystem.linux import write_text_secure

if TYPE_CHECKING:
    from pathlib import Path

    from linuxtools.commands.base import CommandExecutor
    from linuxtools.deploy.models import DeployTarget


@dataclass(frozen=True)
class WriteOutcome:
    """Résultat d'une écriture sur une destination.

    Attributes:
        success: True si l'écriture a réussi.
        detail: Message d'erreur préformaté si échec, vide sinon.
    """

    success: bool
    detail: str = ""


class WriteDestination(Protocol):
    """Cible d'écriture d'un contenu texte — locale ou distante.

    Rend l'incohérence executor/cible irreprésentable : il n'y a pas de
    booléen `is_remote` séparé à désynchroniser d'un executor — on
    construit `LocalDestination()` ou `RemoteDestination(executor)`.
    """

    @property
    def label(self) -> str:
        """Nom court de la destination (ex. `"local"`, `"distant"`)."""
        ...  # pragma: no cover

    def write(self, path: str | Path, content: str, mode: int) -> WriteOutcome:
        """Écrit `content` sur `path` avec les permissions `mode`.

        Args:
            path: Chemin de destination.
            content: Contenu à écrire.
            mode: Permissions POSIX du fichier.

        Returns:
            Résultat de l'écriture (succès + détail d'erreur éventuel).
        """
        ...  # pragma: no cover


@dataclass(frozen=True)
class LocalDestination:
    """Cible locale — écriture directe, TOCTOU-safe."""

    label: ClassVar[str] = "local"

    def write(self, path: str | Path, content: str, mode: int) -> WriteOutcome:
        """Écrit localement via `write_text_secure`.

        Args:
            path: Chemin de destination.
            content: Contenu à écrire.
            mode: Permissions POSIX du fichier.

        Returns:
            `WriteOutcome(True)` — les erreurs d'écriture locale
            (ex. symlink détecté) propagent l'`OSError` de
            `write_text_secure`, comme avant cette extraction.
        """
        write_text_secure(path, content, mode=mode)
        return WriteOutcome(True)


@dataclass(frozen=True)
class RemoteDestination:
    """Cible distante — écriture via `tee` puis `chmod` sur l'executor.

    Attributes:
        executor: Exécuteur de commandes ciblant l'hôte distant.
    """

    executor: CommandExecutor
    label: ClassVar[str] = "distant"

    def write(self, path: str | Path, content: str, mode: int) -> WriteOutcome:
        """Écrit à distance via `tee` (stdin) puis `chmod`.

        Args:
            path: Chemin de destination sur l'hôte cible.
            content: Contenu à écrire.
            mode: Permissions POSIX du fichier.

        Returns:
            `WriteOutcome(True)` si `tee` et `chmod` réussissent,
            `WriteOutcome(False, detail=...)` sinon.
        """
        dest = str(path)
        write_result = self.executor.run(["tee", dest], stdin=content)
        if not write_result.success:
            return WriteOutcome(
                False,
                f"Échec du dépôt distant de {dest} : {write_result.stderr}",
            )
        chmod_result = self.executor.run(["chmod", format(mode, "03o"), dest])
        if not chmod_result.success:
            return WriteOutcome(
                False,
                f"Échec du chmod distant de {dest} : {chmod_result.stderr}",
            )
        return WriteOutcome(True)


def destination_for(
    target: DeployTarget,
    executor: CommandExecutor,
) -> WriteDestination:
    """Construit la destination correspondant à une cible de déploiement.

    Point unique de lecture de `target.is_remote` : au-delà de cette
    fabrique, la cible et son exécuteur ne circulent plus que sous
    forme solidaire (cf. invariant projet dans `CONTEXT.md`).

    Args:
        target: Cible du déploiement.
        executor: Exécuteur de commandes ciblant `target`.

    Returns:
        `RemoteDestination(executor)` si `target.is_remote`,
        `LocalDestination()` sinon.
    """
    if target.is_remote:
        return RemoteDestination(executor)
    return LocalDestination()

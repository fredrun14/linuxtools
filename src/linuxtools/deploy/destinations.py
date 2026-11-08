"""Destinations d'écriture typées — où écrire, locale ou distante.

Rend l'incohérence executor/cible irreprésentable : `LocalDestination`
et `RemoteDestination(executor)` sont solidaires de leur exécuteur, il
n'existe plus de booléen `is_remote` circulant séparément (cf.
invariant projet dans `CONTEXT.md`).
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import TYPE_CHECKING, ClassVar, Literal, Protocol

from linuxtools.commands.remote_write import (
    build_remote_exists_command,
    build_remote_is_dir_command,
    build_remote_link_command,
    build_remote_write_command,
)
from linuxtools.filesystem.linux import write_text_secure

if TYPE_CHECKING:
    from pathlib import Path

    from linuxtools.commands.base import CommandExecutor
    from linuxtools.deploy.models import DeployTarget
    from linuxtools.logging.base import Logger


@dataclass(frozen=True)
class WriteOutcome:
    """Résultat d'une écriture sur une destination.

    Attributes:
        success: True si l'écriture a réussi.
        detail: Message d'erreur préformaté si échec, vide sinon.
        kept: True si le fichier existait déjà et a été laissé intact
            (``if_exists="keep"``).
    """

    success: bool
    detail: str = ""
    kept: bool = False


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

    def write(
        self,
        path: str | Path,
        content: str,
        mode: int,
        *,
        if_exists: Literal["replace", "keep"] = "replace",
    ) -> WriteOutcome:
        """Écrit `content` sur `path` avec les permissions `mode`.

        Args:
            path: Chemin de destination.
            content: Contenu à écrire.
            mode: Permissions POSIX du fichier.
            if_exists: ``"replace"`` (défaut) remplace le fichier ;
                ``"keep"`` ne modifie jamais un fichier existant
                (``WriteOutcome.kept``).

        Returns:
            Résultat de l'écriture (succès + détail d'erreur éventuel).
        """
        ...  # pragma: no cover


@dataclass(frozen=True)
class LocalDestination:
    """Cible locale — écriture directe, TOCTOU-safe."""

    label: ClassVar[str] = "local"

    def write(
        self,
        path: str | Path,
        content: str,
        mode: int,
        *,
        if_exists: Literal["replace", "keep"] = "replace",
    ) -> WriteOutcome:
        """Écrit localement via `write_text_secure`.

        Args:
            path: Chemin de destination.
            content: Contenu à écrire.
            mode: Permissions POSIX du fichier.
            if_exists: ``"replace"`` (défaut) ou ``"keep"`` (création
                exclusive : un fichier existant reste intact).

        Returns:
            `WriteOutcome(True)` ; `WriteOutcome(True, kept=True)` si
            ``keep`` et que le fichier existe déjà. Les autres erreurs
            d'écriture locale (ex. symlink détecté) propagent l'`OSError`
            de `write_text_secure`, comme avant cette extraction.
        """
        if if_exists == "keep":
            try:
                write_text_secure(path, content, mode=mode, exclusive=True)
            except FileExistsError:
                return WriteOutcome(True, kept=True)
            return WriteOutcome(True)
        write_text_secure(path, content, mode=mode)
        return WriteOutcome(True)


@dataclass(frozen=True)
class RemoteDestination:
    """Cible distante — écriture via `install` (stdin) sur l'executor.

    Attributes:
        executor: Exécuteur de commandes ciblant l'hôte distant.
        logger: Logger optionnel, pour signaler un nettoyage incomplet
            (temporaire distant non supprimé).
    """

    executor: CommandExecutor
    logger: Logger | None = None
    label: ClassVar[str] = "distant"

    def write(
        self,
        path: str | Path,
        content: str,
        mode: int,
        *,
        if_exists: Literal["replace", "keep"] = "replace",
    ) -> WriteOutcome:
        """Écrit à distance via `install -m <mode> -T /dev/stdin <dest>`.

        Le répertoire parent de `dest` est créé au préalable (`mkdir -p`,
        idempotent, sans mode explicite : héritage de l'umask root
        standard) : `install` sans `-D` échoue si ce parent n'existe pas
        encore sur l'hôte cible. Puis une seule commande `install` : le
        mode est appliqué dès la création du fichier (pas de fenêtre de
        permissions permissive) et `-T` empêche `install` de suivre un
        éventuel symlink en position de destination (le lien est
        remplacé, pas traversé).

        Args:
            path: Chemin de destination sur l'hôte cible.
            content: Contenu à écrire.
            mode: Permissions POSIX du fichier.
            if_exists: ``"keep"`` : création exclusive (sonde
                d'existence, écriture temporaire puis ``ln``) ; un fichier
                existant n'est jamais modifié (``kept=True``).

        Returns:
            `WriteOutcome(True)` si `mkdir -p` et `install` réussissent,
            `WriteOutcome(False, detail=...)` si l'un des deux échoue
            (`install` n'est pas tenté si `mkdir -p` échoue).
        """
        dest = str(path)
        if if_exists == "keep":
            return self._write_exclusive(dest, content, mode)
        parent = str(PurePosixPath(dest).parent)
        mkdir_result = self.executor.run(["mkdir", "-p", "--", parent])
        if not mkdir_result.success:
            return WriteOutcome(
                False,
                f"Échec de la création du répertoire distant {parent} : "
                f"{mkdir_result.stderr}",
            )
        write_result = self.executor.run(
            build_remote_write_command(mode, dest),
            stdin=content,
        )
        if not write_result.success:
            return WriteOutcome(
                False,
                f"Échec du dépôt distant de {dest} : {write_result.stderr}",
            )
        return WriteOutcome(True)

    def _write_exclusive(
        self, dest: str, content: str, mode: int
    ) -> WriteOutcome:
        """Crée `dest` seulement s'il n'existe pas (sonde, tmp, ``ln``).

        Étapes : sonde d'existence (code 0 = présent -> ``kept``, sauf
        dossier = échec explicite ; 1 = absent, autre = échec fermé),
        ``mkdir -p`` du parent, écriture d'un temporaire (contenu par
        stdin), publication par ``ln -T`` (échoue si `dest` est apparu
        entre-temps), puis ``rm -f`` du temporaire dans tous les cas.

        Args:
            dest: Chemin de destination sur l'hôte distant.
            content: Contenu à écrire (jamais en argv).
            mode: Permissions POSIX du fichier.

        Returns:
            `WriteOutcome(True, kept=True)` si présent, `WriteOutcome(True)`
            si créé, `WriteOutcome(False, detail=...)` sinon.
        """
        probe = self.executor.run(build_remote_exists_command(dest))
        if probe.return_code == 0:
            if self.executor.run(build_remote_is_dir_command(dest)).success:
                return WriteOutcome(
                    False,
                    f"{dest} est un dossier : fichier de secrets attendu",
                )
            return WriteOutcome(True, kept=True)
        if probe.return_code != 1:
            return WriteOutcome(
                False,
                f"Sonde d'existence ambiguë pour {dest} : "
                f"code {probe.return_code}",
            )
        parent = str(PurePosixPath(dest).parent)
        mkdir_result = self.executor.run(["mkdir", "-p", "--", parent])
        if not mkdir_result.success:
            return WriteOutcome(
                False,
                f"Échec de la création du répertoire distant {parent} : "
                f"{mkdir_result.stderr}",
            )
        tmp = f"{dest}.{secrets.token_hex(8)}.tmp"
        try:
            write_result = self.executor.run(
                build_remote_write_command(mode, tmp), stdin=content
            )
            if not write_result.success:
                return WriteOutcome(
                    False,
                    f"Échec du dépôt distant de {tmp} : {write_result.stderr}",
                )
            link_result = self.executor.run(
                build_remote_link_command(tmp, dest)
            )
            if not link_result.success:
                return WriteOutcome(
                    False,
                    f"Création de {dest} impossible (existe déjà ?) : "
                    f"{link_result.stderr}",
                )
        finally:
            rm_result = self.executor.run(["rm", "-f", "--", tmp])
            if not rm_result.success and self.logger is not None:
                self.logger.log_warning(
                    f"Fichier temporaire distant non supprimé : {tmp} "
                    f"({rm_result.stderr})"
                )
        return WriteOutcome(True)


def destination_for(
    target: DeployTarget,
    executor: CommandExecutor,
    logger: Logger | None = None,
) -> WriteDestination:
    """Construit la destination correspondant à une cible de déploiement.

    Point unique de lecture de `target.is_remote` : au-delà de cette
    fabrique, la cible et son exécuteur ne circulent plus que sous
    forme solidaire (cf. invariant projet dans `CONTEXT.md`).

    Args:
        target: Cible du déploiement.
        executor: Exécuteur de commandes ciblant `target`.
        logger: Logger optionnel transmis à la destination distante.

    Returns:
        `RemoteDestination(executor, logger)` si `target.is_remote`,
        `LocalDestination()` sinon.
    """
    if target.is_remote:
        return RemoteDestination(executor, logger)
    return LocalDestination()

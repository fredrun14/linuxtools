"""Dépôt d'un contenu TOML sur une destination locale ou distante."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar, Protocol

from linuxtools.dotconf.conf_toml_exporter import ConfTomlExporter
from linuxtools.filesystem.linux import write_text_secure

if TYPE_CHECKING:
    from pathlib import Path

    from linuxtools.commands.base import CommandExecutor
    from linuxtools.logging.base import Logger


@dataclass(frozen=True)
class WriteOutcome:
    """Résultat d'une écriture sur une destination TOML.

    Attributes:
        success: True si l'écriture a réussi.
        detail: Message d'erreur préformaté si échec, vide sinon.
    """

    success: bool
    detail: str = ""


class TomlDestination(Protocol):
    """Cible d'écriture d'un contenu TOML — locale ou distante.

    Rend l'incohérence executor/cible irreprésentable : il n'y a plus de
    booléen `is_remote` séparé à désynchroniser d'un executor — on
    construit `LocalDestination()` ou `RemoteDestination(executor)`.
    """

    @property
    def label(self) -> str:
        """Nom court de la destination (ex. `"local"`, `"distant"`)."""
        ...

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


class TomlSink:
    """Rend un dict en TOML et le dépose via une `TomlDestination`."""

    def __init__(
        self,
        destination: TomlDestination,
        logger: Logger | None = None,
    ) -> None:
        """Initialise le dépôt TOML.

        Args:
            destination: Cible d'écriture (locale ou distante).
            logger: Logger optionnel pour tracer succès/échecs.
        """
        self._destination = destination
        self._logger = logger

    def write(
        self,
        path: str | Path,
        data: dict[str, Any],
        mode: int = 0o644,
    ) -> bool:
        """Rend `data` en TOML et le dépose sur `path`.

        Args:
            path: Chemin de destination.
            data: Données à sérialiser en TOML.
            mode: Permissions POSIX du fichier déposé (défaut 0o644).

        Returns:
            True si le dépôt a réussi, False sinon.
        """
        content = ConfTomlExporter().export_mapping(data) + "\n"
        outcome = self._destination.write(path, content, mode)

        if outcome.success:
            self._log_info(
                f"Configuration déposée ({self._destination.label}) : {path}"
            )
        else:
            self._log_warning(outcome.detail)

        return outcome.success

    def _log_info(self, message: str) -> None:
        """Logue un message informatif si un logger est configuré."""
        if self._logger:
            self._logger.log_info(message)

    def _log_warning(self, message: str) -> None:
        """Logue un avertissement si un logger est configuré."""
        if self._logger:
            self._logger.log_warning(message)

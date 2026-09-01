"""Dépôt de contenu — quoi écrire, texte brut ou TOML rendu.

`ContentSink` dépose un texte déjà rendu sur une `WriteDestination`
(cf. `deploy/destinations.py`) et trace succès/échec. `TomlSink` rend
un mapping en TOML puis délègue tout le reste à `ContentSink`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from linuxtools.dotconf.conf_toml_exporter import ConfTomlExporter

if TYPE_CHECKING:
    from pathlib import Path

    from linuxtools.deploy.destinations import WriteDestination
    from linuxtools.logging.base import Logger


class ContentSink:
    """Dépose un contenu texte déjà rendu sur une `WriteDestination`."""

    def __init__(
        self,
        destination: WriteDestination,
        logger: Logger | None = None,
    ) -> None:
        """Initialise le dépôt de contenu.

        Args:
            destination: Cible d'écriture (locale ou distante).
            logger: Logger optionnel pour tracer succès/échecs.
        """
        self._destination = destination
        self._logger = logger

    def write(
        self,
        path: str | Path,
        content: str,
        mode: int = 0o644,
    ) -> bool:
        """Dépose `content` sur `path`.

        Args:
            path: Chemin de destination.
            content: Contenu texte à écrire.
            mode: Permissions POSIX du fichier déposé (défaut 0o644).

        Returns:
            True si le dépôt a réussi, False sinon.
        """
        outcome = self._destination.write(path, content, mode)

        if outcome.success:
            self._log_info(
                f"Contenu déposé ({self._destination.label}) : {path}"
            )
        else:
            self._log_error(outcome.detail)

        return outcome.success

    def _log_info(self, message: str) -> None:
        """Logue un message informatif si un logger est configuré."""
        if self._logger is not None:
            self._logger.log_info(message)

    def _log_error(self, message: str) -> None:
        """Logue une erreur si un logger est configuré."""
        if self._logger is not None:
            self._logger.log_error(message)


class TomlSink:
    """Rend un mapping en TOML et le dépose via un `ContentSink`."""

    def __init__(
        self,
        destination: WriteDestination,
        logger: Logger | None = None,
    ) -> None:
        """Initialise le dépôt TOML.

        Args:
            destination: Cible d'écriture (locale ou distante).
            logger: Logger optionnel pour tracer succès/échecs.
        """
        self._sink = ContentSink(destination, logger=logger)

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
        return self._sink.write(path, content, mode=mode)

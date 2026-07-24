"""Logger avec rotation automatique des fichiers de log par taille."""

import logging
import logging.handlers
import os
from io import TextIOWrapper
from pathlib import Path
from typing import Any, TextIO

from linuxtools.logging.file_logger import (
    _BaseFileLogger,
    _ColoredFormatter,
    _NIVEAUX,
    _resolve_config,
    _SupportsGet,
)

_FLAGS_SECURE = os.O_CREAT | os.O_WRONLY | os.O_APPEND | os.O_NOFOLLOW


class _SecureRotatingHandler(logging.handlers.RotatingFileHandler):
    """RotatingFileHandler qui ouvre chaque fd via O_NOFOLLOW (0o600).

    Surcharge ``_open()`` pour remplacer le ``open()`` builtin par
    ``os.open()`` avec ``O_NOFOLLOW``, ce qui empêche l'écriture dans un
    lien symbolique (attaque TOCTOU). La surcharge est héritée par
    ``doRollover()`` — chaque nouveau fichier post-rotation bénéficie du
    même traitement.
    """

    def _open(self) -> TextIOWrapper:
        """Ouvre le fichier courant avec O_NOFOLLOW et 0o600."""
        fd = os.open(self.baseFilename, _FLAGS_SECURE, 0o600)
        return os.fdopen(fd, "a", encoding=self.encoding or "utf-8")


class RotatingFileLogger(_BaseFileLogger):
    """Logger qui fait pivoter le fichier de log quand il dépasse la taille.

    Caractéristiques :
    - Rotation par taille avec conservation de ``backup_count`` archives
    - Ouverture sécurisée (O_NOFOLLOW, 0o600) sur chaque nouveau fichier
    - API identique à ``FileLogger`` (héritée de ``_BaseFileLogger``)
    - Sortie console colorée optionnelle

    Exemple ::

        logger = RotatingFileLogger(
            "/var/log/mon_app/run.log",
            max_bytes=5_242_880,   # 5 Mo
            backup_count=3,
        )
        logger.log_info("démarrage")
        # produit run.log, run.log.1, run.log.2, run.log.3
    """

    def __init__(
        self,
        log_file: str | Path,
        max_bytes: int = 10_485_760,
        backup_count: int = 5,
        config: dict[str, Any] | _SupportsGet | None = None,
        console_output: bool = False,
        colored_console: bool = False,
    ) -> None:
        """Initialise le logger avec rotation.

        Args:
            log_file: Chemin du fichier de log (str ou Path).
            max_bytes: Taille maximale en octets avant rotation (défaut 10 Mo).
                0 désactive la rotation (fichier illimité).
            backup_count: Nombre d'archives à conserver (défaut 5).
            config: Configuration optionnelle (dict ou ConfigurationManager).
                Clés supportées : logging.level, logging.format.
            console_output: Activer la sortie console en plus du fichier.
            colored_console: Coloriser la sortie console par niveau de log.
                Sans effet si ``console_output`` est False.
        """
        _path = Path(log_file)
        self.log_file = str(_path)
        _path.parent.mkdir(parents=True, exist_ok=True)

        log_level_str, log_format = _resolve_config(config)
        niveau = log_level_str.upper()
        if niveau not in _NIVEAUX:
            raise ValueError(f"Niveau de log invalide : {log_level_str!r}")
        log_level = getattr(logging, niveau)

        self.logger = logging.getLogger(f"rotating:{self.log_file}")
        self.logger.setLevel(log_level)

        if not self.logger.handlers:
            self.handler = _SecureRotatingHandler(
                self.log_file,
                maxBytes=max_bytes,
                backupCount=backup_count,
                encoding="utf-8",
                delay=False,
            )
            self.handler.setLevel(log_level)
            self.handler.setFormatter(logging.Formatter(log_format))
            self.logger.addHandler(self.handler)

            if console_output:
                console: logging.StreamHandler[TextIO] = (
                    logging.StreamHandler()
                )
                console.setLevel(log_level)
                console.setFormatter(
                    _ColoredFormatter(log_format)
                    if colored_console
                    else logging.Formatter(log_format)
                )
                self.logger.addHandler(console)
        else:
            self.handler = self.logger.handlers[0]  # type: ignore[assignment]

        self.logger.propagate = False

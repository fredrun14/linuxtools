"""Implémentation concrète du logger avec fichier."""

# stdlib
import logging
import os
from datetime import UTC, datetime
from io import TextIOWrapper
from pathlib import Path
from typing import Any, TextIO

# local
from linuxtools.logging.ansi_colors import AnsiColors
from linuxtools.logging.base import Logger

_NIVEAUX = frozenset({"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"})

_DEFAULT_FORMAT = "%(asctime)s - %(levelname)s - %(message)s"


def _open_secure(path: str) -> int:
    """Ouvre le log avec O_NOFOLLOW/0o600 (anti-symlink, anti-lecture)."""
    flags = os.O_CREAT | os.O_WRONLY | os.O_APPEND | os.O_NOFOLLOW
    return os.open(path, flags, 0o600)


def _resolve_config(
    config: Any,
) -> tuple[str, str]:
    """Extrait le niveau et le format depuis une config dict ou objet.

    Accepte trois formes de config :
    - None : valeurs par défaut.
    - Dict ``{"logging": {"level": ..., "format": ...}}``.
    - Objet avec ``get(key, default)`` à notation pointée
      (ex. ConfigurationManager).

    Args:
        config: Configuration optionnelle (None, dict ou objet).

    Returns:
        Tuple (level_str, format_str) prêt à l'emploi.
    """
    if config is None:
        return "INFO", _DEFAULT_FORMAT
    if isinstance(config, dict):
        logging_cfg = config.get("logging", {})
        return (
            logging_cfg.get("level", "INFO"),
            logging_cfg.get("format", _DEFAULT_FORMAT),
        )
    if hasattr(config, "get") and callable(config.get):
        try:
            return (
                config.get("logging.level", "INFO"),
                config.get("logging.format", _DEFAULT_FORMAT),
            )
        except TypeError:
            # Objet sans support de la notation pointée → accès dict-style
            logging_cfg = config.get("logging", {})
            return (
                logging_cfg.get("level", "INFO"),
                logging_cfg.get("format", _DEFAULT_FORMAT),
            )
    return "INFO", _DEFAULT_FORMAT


_LEVEL_COLORS = {
    logging.DEBUG: AnsiColors.BLUE,
    logging.INFO: AnsiColors.BLUE,
    logging.WARNING: AnsiColors.ORANGE,
    logging.ERROR: AnsiColors.RED,
    logging.CRITICAL: AnsiColors.RED,
}


class _ColoredFormatter(logging.Formatter):
    """Formateur qui préfixe chaque message d'un code ANSI selon le niveau."""

    def format(self, record: logging.LogRecord) -> str:
        """Formate le message avec la couleur du niveau de log.

        Args:
            record: Enregistrement de log à formater.

        Returns:
            Message formaté entouré des codes ANSI correspondants.
        """
        color = _LEVEL_COLORS.get(record.levelno, AnsiColors.RESET)
        return f"{color}{super().format(record)}{AnsiColors.RESET}"


class _BaseFileLogger(Logger):
    """Base commune pour les loggers avec fichier (Template Method).

    Factorise la mécanique de log partagée par ``FileLogger`` et
    ``RotatingFileLogger`` : dispatch par niveau, flush immédiat,
    écriture brute. Les sous-classes fournissent uniquement la
    construction du handler via leur ``__init__``.

    Attributes:
        log_file: Chemin du fichier de log (str).
        logger: Logger stdlib sous-jacent.
        handler: Handler principal (fichier ou rotating).
    """

    log_file: str
    logger: logging.Logger
    handler: logging.StreamHandler[Any]

    def _flush(self) -> None:
        """Force l'écriture immédiate sur le disque."""
        self.handler.flush()

    def _log(self, level: int, message: str) -> None:
        """Émet un log au niveau donné et force le flush."""
        self.logger.log(level, message)
        self._flush()

    def log_info(self, message: str) -> None:
        """Log un message d'information."""
        self._log(logging.INFO, message)

    def log_warning(self, message: str) -> None:
        """Log un avertissement."""
        self._log(logging.WARNING, message)

    def log_error(self, message: str) -> None:
        """Log une erreur."""
        self._log(logging.ERROR, message)

    def log_success(self, message: str) -> None:
        """Log un message de succès (niveau INFO avec préfixe SUCCESS).

        Args:
            message: Message de succès à enregistrer.
        """
        self._log(logging.INFO, f"SUCCESS: {message}")

    def log_to_file(self, message: str) -> None:
        """Écrit directement dans le fichier via le handler existant.

        Utile pour les logs bruts sans formatage.

        Args:
            message: Message brut à écrire dans le fichier.
        """
        timestamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
        self.handler.stream.write(f"{timestamp} - {message}\n")
        self.handler.stream.flush()


class FileLogger(_BaseFileLogger):
    """Logger qui écrit dans un fichier avec option console.

    Caractéristiques :
    - Logger unique par instance (évite les conflits)
    - Encodage UTF-8 explicite
    - Flush immédiat après chaque log
    - Pas de propagation (évite les logs en double)
    - Support optionnel de la sortie console colorée
    """

    def __init__(
        self,
        log_file: str | Path,
        config: dict[str, Any] | None = None,
        console_output: bool = False,
        colored_console: bool = False,
    ) -> None:
        """Initialise le logger.

        Args:
            log_file: Chemin du fichier de log (str ou Path).
            config: Configuration optionnelle (dict ou ConfigurationManager).
                Clés supportées : logging.level, logging.format.
            console_output: Activer la sortie console en plus du fichier.
            colored_console: Coloriser la sortie console par niveau de log.
                Sans effet si console_output est False.
                Le fichier log reste toujours en plain-text.
        """
        _path = Path(log_file)
        self.log_file = str(_path)
        self._ensure_log_dir(_path)

        log_level_str, log_format = _resolve_config(config)
        niveau = log_level_str.upper()
        if niveau not in _NIVEAUX:
            raise ValueError(f"Niveau de log invalide : {log_level_str!r}")
        log_level = getattr(logging, niveau)

        self.logger = logging.getLogger(self.log_file)
        self.logger.setLevel(log_level)
        self.handler: logging.StreamHandler[Any]

        if not self.logger.handlers:
            self.handler = self._make_file_handler(
                self.log_file, log_level, log_format
            )
            self.logger.addHandler(self.handler)
            if console_output:
                self.logger.addHandler(
                    self._make_console_handler(
                        log_level, log_format, colored_console
                    )
                )
        else:
            self.handler = self.logger.handlers[0]  # type: ignore[assignment]

        self.logger.propagate = False

    @staticmethod
    def _ensure_log_dir(log_file: Path) -> None:
        """Crée le répertoire parent du fichier log si absent.

        Args:
            log_file: Chemin complet du fichier de log.
        """
        log_file.parent.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _make_file_handler(
        log_file: str,
        log_level: int,
        log_format: str,
    ) -> logging.StreamHandler[TextIOWrapper]:
        """Crée le handler fichier sécurisé (O_NOFOLLOW, 0o600).

        Args:
            log_file: Chemin du fichier de log.
            log_level: Niveau de log (constante ``logging.*``).
            log_format: Chaîne de format du message.

        Returns:
            StreamHandler configuré sur le fd sécurisé.
        """
        fd = _open_secure(log_file)
        handler: logging.StreamHandler[TextIOWrapper] = logging.StreamHandler(
            os.fdopen(fd, "a", encoding="utf-8")
        )
        handler.setLevel(log_level)
        handler.setFormatter(logging.Formatter(log_format))
        return handler

    @staticmethod
    def _make_console_handler(
        log_level: int,
        log_format: str,
        colored: bool,
    ) -> logging.StreamHandler[TextIO]:
        """Crée le handler console optionnel.

        Args:
            log_level: Niveau de log (constante ``logging.*``).
            log_format: Chaîne de format du message.
            colored: Active la colorisation ANSI par niveau.

        Returns:
            StreamHandler configuré pour la console.
        """
        handler: logging.StreamHandler[TextIO] = logging.StreamHandler()
        handler.setLevel(log_level)
        formatter = (
            _ColoredFormatter(log_format)
            if colored
            else logging.Formatter(log_format)
        )
        handler.setFormatter(formatter)
        return handler

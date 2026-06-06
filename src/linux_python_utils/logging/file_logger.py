"""Implémentation concrète du logger avec fichier."""

# stdlib
import logging
import os
from datetime import datetime
from typing import Any

# local
from linux_python_utils.logging.ansi_colors import AnsiColors
from linux_python_utils.logging.base import Logger

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
    - Objet avec ``get(key, default)`` à notation pointée
      (ex. ConfigurationManager).
    - Dict ``{"logging": {"level": ..., "format": ...}}``.

    Args:
        config: Configuration optionnelle (None, dict ou objet).

    Returns:
        Tuple (level_str, format_str) prêt à l'emploi.
    """
    if config is None:
        return "INFO", _DEFAULT_FORMAT

    if hasattr(config, "get") and callable(config.get):
        try:
            level_str = config.get("logging.level", "INFO")
            fmt = config.get("logging.format", _DEFAULT_FORMAT)
            return level_str, fmt
        except TypeError:
            # Dict standard : get() ne gère pas la notation pointée
            logging_cfg = config.get("logging", {})
            return (
                logging_cfg.get("level", "INFO"),
                logging_cfg.get("format", _DEFAULT_FORMAT),
            )

    return "INFO", _DEFAULT_FORMAT


_LEVEL_COLORS = {
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


class FileLogger(Logger):
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
        log_file: str,
        config: dict[str, Any] | None = None,
        console_output: bool = False,
        colored_console: bool = False,
    ) -> None:
        """Initialise le logger.

        Args:
            log_file: Chemin du fichier de log.
            config: Configuration optionnelle (dict ou ConfigurationManager).
                Clés supportées : logging.level, logging.format.
            console_output: Activer la sortie console en plus du fichier.
            colored_console: Coloriser la sortie console par niveau de log.
                Sans effet si console_output est False.
                Le fichier log reste toujours en plain-text.
        """
        self.log_file = log_file
        self._ensure_log_dir(log_file)

        log_level_str, log_format = _resolve_config(config)
        niveau = log_level_str.upper()
        if niveau not in _NIVEAUX:
            raise ValueError(f"Niveau de log invalide : {log_level_str!r}")
        log_level = getattr(logging, niveau)

        self.logger = logging.getLogger(log_file)
        self.logger.setLevel(log_level)
        self.handler: logging.Handler

        if not self.logger.handlers:
            self.handler = self._make_file_handler(
                log_file, log_level, log_format
            )
            self.logger.addHandler(self.handler)
            if console_output:
                self.logger.addHandler(
                    self._make_console_handler(
                        log_level, log_format, colored_console
                    )
                )
        else:
            self.handler = self.logger.handlers[0]

        self.logger.propagate = False

    @staticmethod
    def _ensure_log_dir(log_file: str) -> None:
        """Crée le répertoire parent du fichier log si absent.

        Args:
            log_file: Chemin complet du fichier de log.
        """
        log_dir = os.path.dirname(log_file)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir, exist_ok=True)

    @staticmethod
    def _make_file_handler(
        log_file: str,
        log_level: int,
        log_format: str,
    ) -> logging.StreamHandler:  # type: ignore[type-arg]
        """Crée le handler fichier sécurisé (O_NOFOLLOW, 0o600).

        Args:
            log_file: Chemin du fichier de log.
            log_level: Niveau de log (constante ``logging.*``).
            log_format: Chaîne de format du message.

        Returns:
            StreamHandler configuré sur le fd sécurisé.
        """
        fd = _open_secure(log_file)
        handler: logging.StreamHandler = logging.StreamHandler(  # type: ignore[type-arg]
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
    ) -> logging.StreamHandler:  # type: ignore[type-arg]
        """Crée le handler console optionnel.

        Args:
            log_level: Niveau de log (constante ``logging.*``).
            log_format: Chaîne de format du message.
            colored: Active la colorisation ANSI par niveau.

        Returns:
            StreamHandler configuré pour la console.
        """
        handler: logging.StreamHandler = logging.StreamHandler()  # type: ignore[type-arg]
        handler.setLevel(log_level)
        formatter = (
            _ColoredFormatter(log_format)
            if colored
            else logging.Formatter(log_format)
        )
        handler.setFormatter(formatter)
        return handler

    def _flush(self) -> None:
        """Force l'écriture immédiate sur le disque."""
        self.handler.flush()

    def log_info(self, message: str) -> None:
        """Log un message d'information."""
        self.logger.info(message)
        self._flush()

    def log_warning(self, message: str) -> None:
        """Log un avertissement."""
        self.logger.warning(message)
        self._flush()

    def log_error(self, message: str) -> None:
        """Log une erreur."""
        self.logger.error(message)
        self._flush()

    def log_to_file(self, message: str) -> None:
        """Écrit directement dans le fichier (sans passer par logging).

        Utile pour les logs bruts sans formatage.

        Args:
            message: Message brut à écrire dans le fichier.
        """
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        fd = _open_secure(self.log_file)
        with os.fdopen(fd, "a", encoding="utf-8") as f:
            f.write(f"{timestamp} - {message}\n")

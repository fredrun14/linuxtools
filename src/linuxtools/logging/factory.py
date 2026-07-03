"""Factory de création de Logger depuis la configuration."""

from pathlib import Path
from typing import Any

from linuxtools.logging.base import Logger
from linuxtools.logging.console_logger import ConsoleLogger
from linuxtools.logging.file_logger import FileLogger
from linuxtools.logging.rotating_file_logger import RotatingFileLogger

_TYPES_VALIDES = frozenset({"file", "console", "rotating"})


def build_logger(config: dict[str, Any] | None = None) -> Logger:
    """Instancie le Logger correspondant à la section ``[logging]``.

    Accepte la section ``[logging]`` extraite d'un fichier TOML ou d'un
    ``ConfigurationManager``. Le code appelant reste découplé des classes
    concrètes (``FileLogger``, ``RotatingFileLogger``, ``ConsoleLogger``).

    Args:
        config: Section ``[logging]`` sous forme de dict (ou None pour les
            valeurs par défaut). Clés reconnues :

            - ``type`` (str) : ``"file"`` | ``"console"`` | ``"rotating"``
              (défaut : ``"console"``)
            - ``file`` (str|Path) : chemin du fichier ; obligatoire pour
              ``"file"`` et ``"rotating"``
            - ``level`` (str) : niveau de log (défaut : ``"INFO"``)
            - ``format`` (str) : format du message (défaut stdlib)
            - ``max_bytes`` (int) : taille max avant rotation en octets
              (défaut : 10 485 760 = 10 Mo) ; ignoré pour ``"file"``
            - ``backup_count`` (int) : archives à conserver (défaut : 5) ;
              ignoré pour ``"file"``
            - ``console_output`` (bool) : sortie console parallèle au
              fichier (défaut : ``False``) ; ignoré pour ``"console"``
            - ``colored_console`` (bool) : colorisation ANSI de la sortie
              console (défaut : ``False``) ; ignoré pour ``"console"``

    Returns:
        Instance de ``Logger`` configurée.

    Raises:
        ValueError: Si ``type`` est inconnu ou si ``file`` est absent pour
            un type nécessitant un chemin.

    Exemple TOML ::

        [logging]
        type = "rotating"
        file = "/var/log/mon_app/run.log"
        level = "WARNING"
        max_bytes = 5242880
        backup_count = 3
        console_output = true

    Utilisation avec ``ConfigurationManager`` ::

        from linuxtools.config import ConfigurationManager
        from linuxtools.logging import build_logger

        cfg = ConfigurationManager("app.toml")
        logger = build_logger(cfg.get_section("logging"))
        logger.log_info("démarrage")
    """
    cfg: dict[str, Any] = config or {}

    logger_type = cfg.get("type", "console")
    if logger_type not in _TYPES_VALIDES:
        raise ValueError(
            f"Type de logger inconnu : {logger_type!r}. "
            f"Valeurs acceptées : {sorted(_TYPES_VALIDES)}"
        )

    if logger_type == "console":
        return ConsoleLogger()

    log_file: str | Path | None = cfg.get("file")
    if not log_file:
        raise ValueError(
            f"La clé 'file' est obligatoire pour le type {logger_type!r}."
        )

    # Reconstruit un dict compatible avec _resolve_config
    inner: dict[str, Any] = {"level": cfg.get("level", "INFO")}
    if "format" in cfg:
        inner["format"] = cfg["format"]
    resolve_cfg: dict[str, Any] = {"logging": inner}

    console_output: bool = cfg.get("console_output", False)
    colored_console: bool = cfg.get("colored_console", False)

    if logger_type == "file":
        return FileLogger(
            log_file=log_file,
            config=resolve_cfg,
            console_output=console_output,
            colored_console=colored_console,
        )

    return RotatingFileLogger(
        log_file=log_file,
        max_bytes=cfg.get("max_bytes", 10_485_760),
        backup_count=cfg.get("backup_count", 5),
        config=resolve_cfg,
        console_output=console_output,
        colored_console=colored_console,
    )

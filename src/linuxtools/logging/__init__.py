"""Module de logging.

Fournit une interface Logger unique injectée dans tout le package
(``Logger`` = point d'extension DIP), ses implémentations fichier/
console, une factory de construction depuis une section TOML, et un
logger de sécurité qui masque les clés sensibles avant journalisation.

Interface et implémentations:
- Logger: Interface abstraite (log_info, log_warning, log_error, ...)
- FileLogger: Écrit dans un fichier
- RotatingFileLogger: Écrit dans un fichier avec rotation par taille
- ConsoleLogger: Écrit sur stdout/stderr, coloration ANSI optionnelle
- build_logger: Factory — instancie le Logger depuis une section ``[logging]``

Utilitaires:
- AnsiColors: Codes couleur ANSI utilisés par ConsoleLogger
- TeeStream: Duplique un flux texte vers un fichier de log en parallèle

Journalisation d'événements de sécurité:
- SecurityLogger: Formate un SecurityEvent en JSON, masque les clés
  sensibles (mot de passe, token, ...) avant transmission au Logger
- SecurityEvent, SecurityEventType: Structure et typologie d'un événement

Exemple d'utilisation:
    from linuxtools.logging import FileLogger, RotatingFileLogger

    logger = FileLogger("/var/log/app.log")
    logger.log_info("Démarrage")

    logger = RotatingFileLogger(
        "/var/log/app.log", max_bytes=10_485_760, backup_count=5,
        console_output=True, colored_console=True,
    )

Exemple d'utilisation (événement de sécurité):
    from linuxtools.logging import (
        SecurityLogger, SecurityEvent, SecurityEventType,
    )

    sec_logger = SecurityLogger(logger)
    sec_logger.log_event(SecurityEvent(
        event_type=SecurityEventType.CONFIG_CHANGE,
        resource="/etc/dnf/dnf.conf",
        details={"section": "main", "keys": ["fastestmirror"]},
        severity="warning",
    ))
"""

from linuxtools.logging.ansi_colors import AnsiColors
from linuxtools.logging.base import Logger
from linuxtools.logging.console_logger import ConsoleLogger
from linuxtools.logging.factory import build_logger
from linuxtools.logging.file_logger import FileLogger
from linuxtools.logging.rotating_file_logger import RotatingFileLogger
from linuxtools.logging.security_logger import (
    SecurityEvent,
    SecurityEventType,
    SecurityLogger,
)
from linuxtools.logging.tee_stream import TeeStream

__all__ = [
    "AnsiColors",
    "build_logger",
    "ConsoleLogger",
    "FileLogger",
    "Logger",
    "RotatingFileLogger",
    "SecurityEvent",
    "SecurityEventType",
    "SecurityLogger",
    "TeeStream",
]

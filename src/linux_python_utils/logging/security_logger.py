"""Logging structuré des événements de sécurité.

Ce module fournit les primitives pour tracer les événements de sécurité
(modifications de configuration, accès refusés, élévations de privilèges)
via une interface typée et une sortie JSON structurée.

Respecte le principe DIP : SecurityLogger dépend de l'abstraction Logger,
non d'une implémentation concrète.
"""

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from linux_python_utils.logging.base import Logger


class SecurityEventType(StrEnum):
    """Types d'événements de sécurité traçables."""

    AUTH_SUCCESS = "auth.success"
    AUTH_FAILURE = "auth.failure"
    AUTH_LOCKOUT = "auth.lockout"
    ACCESS_DENIED = "access.denied"
    ACCESS_ELEVATED = "access.elevated"
    DATA_EXPORT = "data.export"
    DATA_MODIFICATION = "data.modification"
    CONFIG_CHANGE = "config.change"
    RATE_LIMIT_HIT = "rate_limit.hit"
    SUSPICIOUS_ACTIVITY = "suspicious.activity"


@dataclass(frozen=True)
class SecurityEvent:
    """Événement de sécurité structuré pour audit trail.

    Attributes:
        event_type: Type d'événement (SecurityEventType).
        resource: Ressource concernée (chemin, endpoint, etc.).
        details: Contexte additionnel de l'événement.
        severity: Niveau de sévérité (info, warning, error, critical).
        user_id: Identifiant de l'utilisateur à l'origine de l'action.
        timestamp: Horodatage ISO 8601 UTC (auto-généré).
    """

    event_type: SecurityEventType
    resource: str | None = None
    details: dict[str, Any] = field(default_factory=dict)
    severity: str = "info"
    user_id: str | None = None
    timestamp: str = field(
        default_factory=lambda: datetime.now(UTC).isoformat()
    )


_CLES_SENSIBLES = frozenset({
    "password", "passwd", "token", "secret",
    "key", "authorization", "api_key",
})

_SEVERITY_DISPATCH: dict[str, str] = {
    "debug":    "log_info",
    "info":     "log_info",
    "warning":  "log_warning",
    "error":    "log_error",
    "critical": "log_error",
}


def _masquer(details: dict[str, Any]) -> dict[str, Any]:
    """Remplace la valeur des clés sensibles par '***'."""
    return {
        k: ("***" if k.lower() in _CLES_SENSIBLES else v)
        for k, v in details.items()
    }


class SecurityLogger:
    """Logger spécialisé pour les événements de sécurité.

    Formate chaque événement en JSON structuré et le transmet
    au Logger injecté selon le niveau de sévérité.

    Utilisation :
        sec_logger = SecurityLogger(file_logger)
        sec_logger.log_event(SecurityEvent(
            event_type=SecurityEventType.CONFIG_CHANGE,
            resource="/etc/dnf/dnf.conf",
            details={"section": "main", "keys": ["fastestmirror"]},
            severity="warning",
        ))
    """

    def __init__(self, logger: Logger) -> None:
        """Initialise le logger de sécurité.

        Args:
            logger: Instance de Logger pour l'émission des messages.
        """
        self._logger = logger

    def log_event(self, event: SecurityEvent) -> None:
        """Enregistre un événement de sécurité en JSON structuré.

        Le message JSON inclut : event_type, timestamp, resource,
        details, severity et user_id (si renseigné).

        Args:
            event: Événement de sécurité à journaliser.
        """
        payload: dict[str, Any] = {
            "security_event": str(event.event_type),
            "timestamp": event.timestamp,
            "resource": event.resource,
            "severity": event.severity,
            "details": _masquer(event.details),
        }
        if event.user_id is not None:
            payload["user_id"] = event.user_id

        message = json.dumps(payload, ensure_ascii=False, default=str)

        methode = _SEVERITY_DISPATCH.get(event.severity, "log_info")
        getattr(self._logger, methode)(message)

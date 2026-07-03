"""Modeles de donnees pour les peripheriques reseau.

Ce module definit la dataclass immuable NetworkDevice qui
represente un peripherique decouvert sur le reseau local.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from linuxtools.network.validators import (
    validate_ipv4,
    validate_mac,
)


@dataclass(frozen=True)
class NetworkDevice:
    """Peripherique reseau decouvert.

    Attributes:
        ip: Adresse IPv4 du peripherique.
        mac: Adresse MAC du peripherique.
        hostname: Nom d'hote.
        vendor: Fabricant identifie par OUI MAC.
        device_type: Type de peripherique.
        is_known: Peripherique connu/attendu.
        fixed_ip: Adresse IP fixe assignee.
        dns_name: Nom DNS local.
        first_seen: Date de premiere decouverte.
        last_seen: Date de derniere observation.
        notes: Notes libres.
    """

    ip: str
    mac: str
    hostname: str = ""
    vendor: str = ""
    device_type: str = "unknown"
    is_known: bool = False
    fixed_ip: str | None = None
    dns_name: str | None = None
    first_seen: datetime = field(default_factory=datetime.now)
    last_seen: datetime = field(default_factory=datetime.now)
    notes: str = ""

    def __post_init__(self) -> None:
        """Valide les champs apres initialisation."""
        if self.ip:
            validate_ipv4(self.ip)
        normalized_mac = validate_mac(self.mac)
        if normalized_mac != self.mac:
            object.__setattr__(self, "mac", normalized_mac)
        if self.fixed_ip is not None:
            validate_ipv4(self.fixed_ip)

    def to_dict(self) -> dict[str, Any]:
        """Serialise le peripherique en dictionnaire.

        Les datetimes sont converties au format ISO 8601.

        Returns:
            Dictionnaire representant le peripherique.
        """
        return {
            "ip": self.ip,
            "mac": self.mac,
            "hostname": self.hostname,
            "vendor": self.vendor,
            "device_type": self.device_type,
            "is_known": self.is_known,
            "fixed_ip": self.fixed_ip,
            "dns_name": self.dns_name,
            "first_seen": self.first_seen.isoformat(),
            "last_seen": self.last_seen.isoformat(),
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "NetworkDevice":
        """Reconstruit un peripherique depuis un dictionnaire.

        Args:
            data: Dictionnaire avec les donnees du peripherique.

        Returns:
            Instance de NetworkDevice.
        """
        data = dict(data)
        if "first_seen" in data and isinstance(
            data["first_seen"], str
        ):
            data["first_seen"] = datetime.fromisoformat(
                data["first_seen"]
            )
        if "last_seen" in data and isinstance(
            data["last_seen"], str
        ):
            data["last_seen"] = datetime.fromisoformat(
                data["last_seen"]
            )
        return cls(**data)

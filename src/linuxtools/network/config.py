"""Classes de configuration pour le module reseau.

Ce module definit les dataclasses immuables pour la configuration
du reseau, de la plage DHCP et du DNS local.
"""

from dataclasses import dataclass, field
from typing import Optional

from linuxtools.network.validators import (
    validate_cidr,
    validate_ipv4,
)


@dataclass(frozen=True)
class DhcpRange:
    """Plage d'adresses IP pour l'allocation DHCP.

    Attributes:
        start: Adresse IP de debut de plage.
        end: Adresse IP de fin de plage.
    """

    start: str
    end: str

    def __post_init__(self) -> None:
        """Valide les adresses et l'ordre de la plage."""
        validate_ipv4(self.start)
        validate_ipv4(self.end)
        start_parts = [int(o) for o in self.start.split(".")]
        end_parts = [int(o) for o in self.end.split(".")]
        if start_parts > end_parts:
            raise ValueError(
                f"Plage DHCP inversee : {self.start} > {self.end}"
            )


@dataclass(frozen=True)
class DnsConfig:
    """Configuration DNS locale.

    Attributes:
        domain: Domaine local.
        hosts_file: Chemin du fichier hosts.
        dnsmasq_conf: Chemin de la config dnsmasq.
    """

    domain: str = "maison.local"
    hosts_file: str = "/etc/hosts"
    dnsmasq_conf: str = ""


@dataclass(frozen=True)
class NetworkConfig:
    """Configuration reseau principale.

    Attributes:
        cidr: Reseau en notation CIDR.
        interface: Interface reseau (vide = auto-detection).
        dhcp_range: Plage DHCP optionnelle.
        dns: Configuration DNS.
        inventory_path: Chemin du fichier d'inventaire.
        scan_timeout: Timeout du scan en secondes.
        scan_bandwidth: Debit max arp-scan en bits/s.
    """

    cidr: str
    interface: str = ""
    dhcp_range: DhcpRange | None = None
    dns: DnsConfig = field(default_factory=DnsConfig)
    inventory_path: str = "devices.json"
    scan_timeout: int = 30
    scan_bandwidth: int = 256000

    def __post_init__(self) -> None:
        """Valide la notation CIDR et le debit.

        Raises:
            ValueError: Si le CIDR ou le debit est invalide.
        """
        validate_cidr(self.cidr)
        if self.scan_bandwidth <= 0:
            raise ValueError(
                f"scan_bandwidth invalide : "
                f"{self.scan_bandwidth}"
            )

"""Intention DHCP et confrontation à l'état d'un routeur.

Ce module ne fait QUE représenter l'intention et comparer : il ne lit
ni n'écrit rien (ni fichier, ni routeur, ni réseau). Il n'importe
volontairement rien de ``linuxtools.network.router`` (cycle de
dépendance avec webapitools).
"""

from collections.abc import Sequence
from dataclasses import dataclass
from ipaddress import IPv4Network, IPv6Network, ip_address

from linuxtools.network.clients import LanClient
from linuxtools.network.models import NetworkDevice


def _in_subnet(ip: str, subnet: IPv4Network | IPv6Network) -> bool:
    """Indique si une IP appartient au subnet.

    Args:
        ip: IP sous forme de chaîne.
        subnet: Réseau de référence.

    Returns:
        True si l'IP est valide et dans le subnet ; False sinon (y
        compris IP illisible ou de famille différente).
    """
    try:
        return ip_address(ip) in subnet
    except ValueError:
        return False


def _check_no_duplicate_ip(
    active: Sequence[NetworkDevice], disabled: Sequence[LanClient]
) -> None:
    """Refuse deux entrées portant la même IP épinglée.

    Les clients désactivés comptent : réactiver l'un d'eux créerait
    sinon un conflit.

    Args:
        active: Réservations actives.
        disabled: Clients désactivés.

    Raises:
        ValueError: Si une IP est portée deux fois (message : l'IP et
            les deux noms, jamais de MAC).
    """
    seen: dict[str, str] = {}
    entries = [(d.fixed_ip, d.hostname) for d in active]
    entries += [(c.pinned_ip, c.name or "") for c in disabled]
    for ip, name in entries:
        if ip is None:
            continue
        if ip in seen:
            raise ValueError(
                f"IP {ip} en double : {seen[ip] or '(sans nom)'} et "
                f"{name or '(sans nom)'}"
            )
        seen[ip] = name


@dataclass(frozen=True)
class DhcpIntent:
    """Intention DHCP déclarée, répartie par statut.

    Attributes:
        active: Réservations à porter par le routeur.
        disabled: Clients retirés volontairement (ne doivent pas
            figurer sur le routeur).
        ignored: Clients actifs sans IP épinglée ou hors du subnet.
    """

    active: tuple[NetworkDevice, ...]
    disabled: tuple[LanClient, ...]
    ignored: tuple[LanClient, ...]

    @classmethod
    def from_clients(
        cls,
        clients: Sequence[LanClient],
        subnet: IPv4Network | IPv6Network,
    ) -> "DhcpIntent":
        """Construit l'intention à partir des clients déclarés.

        Args:
            clients: Clients LAN déclarés (actifs et désactivés).
            subnet: Réseau dans lequel une IP épinglée est admise.

        Returns:
            L'intention répartie en actifs, désactivés et ignorés.
        """
        active: list[NetworkDevice] = []
        disabled: list[LanClient] = []
        ignored: list[LanClient] = []
        for client in clients:
            if not client.enabled:
                disabled.append(client)
                continue
            if client.pinned_ip is None or not _in_subnet(
                client.pinned_ip, subnet
            ):
                ignored.append(client)
                continue
            active.append(
                NetworkDevice(
                    ip=client.pinned_ip,
                    mac=client.mac.lower(),
                    hostname=client.name or "",
                    fixed_ip=client.pinned_ip,
                )
            )
        _check_no_duplicate_ip(active, disabled)
        return cls(
            active=tuple(active),
            disabled=tuple(disabled),
            ignored=tuple(ignored),
        )

    def target(
        self, actual: Sequence[NetworkDevice]
    ) -> tuple[NetworkDevice, ...]:
        """Calcule la liste complète à écrire en bloc sur le routeur.

        Args:
            actual: Réservations actuellement lues sur le routeur.

        Returns:
            Les réservations actives, suivies des réservations du
            routeur non déclarées (conservées, F-17).
        """
        declared = {d.mac for d in self.active}
        declared |= {c.mac.lower() for c in self.disabled}
        kept: dict[str, NetworkDevice] = {}
        for device in self.active:
            kept.setdefault(device.mac.lower(), device)
        for device in actual:
            mac = device.mac.lower()
            if mac not in declared:
                kept.setdefault(mac, device)
        return tuple(kept.values())

"""Intention DHCP et confrontation à l'état d'un routeur.

Ce module ne fait QUE représenter l'intention et comparer : il ne lit
ni n'écrit rien (ni fichier, ni routeur, ni réseau). Il n'importe
volontairement rien de ``linuxtools.network.router`` (cycle de
dépendance avec webapitools).
"""

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from ipaddress import IPv4Network, ip_address

from linuxtools.network.clients import LanClient
from linuxtools.network.models import NetworkDevice


class DriftKind(StrEnum):
    """Nature d'un écart entre l'intention et l'état du routeur."""

    # déclarée active, absente du routeur
    MISSING = "missing"
    # présente sur le routeur, mais sur une autre IP
    IP_MISMATCH = "ip_mismatch"
    # enabled = false, mais encore présente sur le routeur
    STALE_DISABLED = "stale"
    # présente sur le routeur, absente du TOML
    UNDECLARED = "undeclared"


# Ordre d'affichage : ce qui exige une action d'abord,
# l'informatif ensuite.
_SEVERITY: dict[DriftKind, int] = {
    DriftKind.MISSING: 0,
    DriftKind.IP_MISMATCH: 1,
    DriftKind.STALE_DISABLED: 2,
    DriftKind.UNDECLARED: 3,
}


@dataclass(frozen=True)
class DriftItem:
    """Un écart constaté.

    Attributes:
        kind: Nature de l'écart.
        mac: MAC concernée (minuscules).
        name: Libellé connu, ou "" si l'appareil n'est pas déclaré.
        expected_ip: IP attendue par l'intention, ou None.
        actual_ip: IP réellement portée par le routeur, ou None.
        out_of_scope: Pour UNDECLARED : le client est déclaré dans le
            TOML mais ignoré (IP absente, illisible ou hors subnet) ;
            sa réservation routeur est conservée. Un drapeau plutôt
            qu'un nouveau DriftKind : ``actionable`` et le tri par
            gravité restent inchangés.
    """

    kind: DriftKind
    mac: str
    name: str = ""
    expected_ip: str | None = None
    actual_ip: str | None = None
    out_of_scope: bool = False


@dataclass(frozen=True)
class DriftReport:
    """Résultat de la confrontation intention <-> routeur.

    Attributes:
        items: Écarts constatés, par ordre de gravité.
        declared: Nombre de réservations actives déclarées.
        on_router: Nombre de réservations lues sur le routeur.
    """

    items: tuple[DriftItem, ...] = ()
    declared: int = 0
    on_router: int = 0

    @property
    def has_drift(self) -> bool:
        """Retourne True si au moins un écart a été constaté."""
        return bool(self.items)

    @property
    def actionable(self) -> bool:
        """Retourne True si un écart exige une action.

        Une réservation non déclarée (UNDECLARED) est informative :
        elle est conservée, jamais effacée.
        """
        return any(i.kind is not DriftKind.UNDECLARED for i in self.items)

    def format_summary(self) -> str:
        """Retourne un résumé textuel lisible du rapport.

        Ne porte que MAC, IP et libellés : la donnée métier du LAN,
        jamais un secret.

        Returns:
            Chaîne multiligne : verdict, volumétrie, puis le détail
            des écarts par ordre de gravité.
        """
        if self.has_drift:
            header = (
                f"{len(self.items)} ecart(s) — "
                f"{self.declared} declaree(s) active(s), "
                f"{self.on_router} sur le routeur"
            )
        else:
            header = (
                f"Conforme — {self.declared} reservation(s) "
                f"active(s), {self.on_router} sur le routeur"
            )
        lines = [header]
        lines.extend(f"  {_describe(item)}" for item in self.items)
        return "\n".join(lines)


def _describe(item: DriftItem) -> str:
    """Rend un écart en une ligne lisible.

    Args:
        item: L'écart à décrire.

    Returns:
        Ligne prête à afficher, avec la MAC, le libellé et l'action
        attendue.
    """
    label = item.name or "(sans libelle)"
    if item.kind is DriftKind.MISSING:
        return (
            f"MANQUANTE   {item.mac}  {label} — attendue en "
            f"{item.expected_ip}, absente du routeur"
        )
    if item.kind is DriftKind.IP_MISMATCH:
        return (
            f"IP DIVERGE  {item.mac}  {label} — attendue "
            f"{item.expected_ip}, routeur {item.actual_ip}"
        )
    if item.kind is DriftKind.STALE_DISABLED:
        return (
            f"RESURGENTE  {item.mac}  {label} — retiree "
            f"volontairement, encore presente en {item.actual_ip}"
        )
    if item.out_of_scope:
        return (
            f"DECLAREE HORS PERIMETRE DHCP {item.mac}  {label} — "
            f"presente en {item.actual_ip} sur le routeur, IP epinglee "
            "absente, invalide ou hors subnet (conservee)"
        )
    return (
        f"NON DECLAREE {item.mac}  {label} — presente en "
        f"{item.actual_ip}, absente du TOML (conservee)"
    )


def _index_by_mac(
    actual: Sequence[NetworkDevice],
) -> dict[str, NetworkDevice]:
    """Indexe les réservations du routeur par MAC (minuscules).

    Args:
        actual: Réservations lues sur le routeur.

    Returns:
        Dictionnaire MAC minuscules -> réservation, dans l'ordre de
        lecture.

    Raises:
        ValueError: Si une MAC est présente deux fois (message : IP et
            noms, jamais la MAC).
    """
    seen: dict[str, NetworkDevice] = {}
    for device in actual:
        mac = device.mac.lower()
        if mac in seen:
            first = seen[mac]
            raise ValueError(
                "MAC en double sur le routeur : "
                f"{first.fixed_ip or '(sans IP)'} "
                f"({first.hostname or 'sans nom'}) "
                f"et {device.fixed_ip or '(sans IP)'} "
                f"({device.hostname or 'sans nom'})"
            )
        seen[mac] = device
    return seen


def compare_reservations(
    intent: "DhcpIntent", actual: Sequence[NetworkDevice]
) -> DriftReport:
    """Confronte l'intention déclarée à l'état du routeur.

    Fonction pure : aucune E/S, aucun accès réseau.

    Args:
        intent: Intention DHCP déclarée.
        actual: Réservations lues sur le routeur.

    Returns:
        DriftReport listant tous les écarts.

    Raises:
        ValueError: Si ``actual`` contient deux fois la même MAC (état
            routeur incohérent : refusé, jamais deviné ; message : IP et
            noms, jamais la MAC).
    """
    by_mac_router = _index_by_mac(actual)
    items: list[DriftItem] = []
    for wanted in intent.active:
        device = by_mac_router.get(wanted.mac)
        if device is None:
            items.append(
                DriftItem(
                    kind=DriftKind.MISSING,
                    mac=wanted.mac,
                    name=wanted.hostname,
                    expected_ip=wanted.fixed_ip,
                )
            )
        elif device.fixed_ip != wanted.fixed_ip:
            items.append(
                DriftItem(
                    kind=DriftKind.IP_MISMATCH,
                    mac=wanted.mac,
                    name=wanted.hostname,
                    expected_ip=wanted.fixed_ip,
                    actual_ip=device.fixed_ip,
                )
            )
    # Logique inversée pour les désactivées : leur PRÉSENCE est
    # anormale, leur absence est l'état attendu.
    for off in intent.disabled:
        device = by_mac_router.get(off.mac.lower())
        if device is not None:
            items.append(
                DriftItem(
                    kind=DriftKind.STALE_DISABLED,
                    mac=off.mac.lower(),
                    name=off.name or "",
                    actual_ip=device.fixed_ip,
                )
            )
    # Présentes sur le routeur mais absentes de l'intention :
    # signalées, JAMAIS supprimées (F-17).
    declared = {d.mac for d in intent.active}
    declared |= {c.mac.lower() for c in intent.disabled}
    ignored = {c.mac.lower(): c for c in intent.ignored}
    for device in actual:
        mac = device.mac.lower()
        if mac in declared:
            continue
        client = ignored.get(mac)
        items.append(
            DriftItem(
                kind=DriftKind.UNDECLARED,
                mac=mac,
                name=(client.name if client else None) or device.hostname,
                actual_ip=device.fixed_ip,
                out_of_scope=client is not None,
            )
        )
    items.sort(key=lambda i: (_SEVERITY[i.kind], i.mac))
    return DriftReport(
        items=tuple(items),
        declared=len(intent.active),
        on_router=len(actual),
    )


def _in_subnet(ip: str, subnet: IPv4Network) -> bool:
    """Indique si une IP appartient au subnet.

    Args:
        ip: IP sous forme de chaîne.
        subnet: Réseau de référence.

    Returns:
        True si l'IP est valide et dans le subnet ; False sinon (y
        compris IP illisible ou IPv6).
    """
    try:
        return ip_address(ip.strip()) in subnet
    except ValueError:
        return False


def _normalize_ip(ip: str) -> str:
    """Normalise une IP pour la comparer (espaces, forme canonique).

    Args:
        ip: IP sous forme de chaîne.

    Returns:
        La forme canonique si l'IP est lisible, sinon la chaîne
        débarrassée de ses espaces.
    """
    try:
        return str(ip_address(ip.strip()))
    except ValueError:
        return ip.strip()


def _check_no_duplicate_ip(active: Sequence[NetworkDevice]) -> None:
    """Refuse deux réservations actives portant la même IP épinglée.

    Seules les réservations actives sont contrôlées : un client
    désactivé n'est jamais poussé au routeur, donc il ne peut pas être
    en conflit (cas du remplacement d'un appareil sur la même IP).
    Réactiver un client est une édition explicite : il devient alors
    actif et ce contrôle le refuse à ce moment-là s'il entre en
    collision.

    Args:
        active: Réservations actives.

    Raises:
        ValueError: Si une IP est portée deux fois (message : l'IP et
            les deux noms, jamais de MAC).
    """
    seen: dict[str, str] = {}
    for device in active:
        if device.fixed_ip is None:
            continue
        ip = _normalize_ip(device.fixed_ip)
        name = device.hostname
        if ip in seen:
            raise ValueError(
                f"IP {ip} en double : {seen[ip] or '(sans nom)'} et "
                f"{name or '(sans nom)'}"
            )
        seen[ip] = name


def _check_no_duplicate_mac(clients: Sequence[LanClient]) -> None:
    """Refuse deux clients portant la même MAC (casse ignorée).

    Args:
        clients: Tous les clients déclarés, quel que soit leur statut.

    Raises:
        ValueError: Si une MAC est portée deux fois (message : les deux
            noms, jamais la MAC).
    """
    seen: dict[str, str] = {}
    for client in clients:
        mac = client.mac.lower()
        name = client.name or "(sans nom)"
        if mac in seen:
            raise ValueError(
                f"MAC en double dans l'intention : {seen[mac]} et {name}"
            )
        seen[mac] = name


@dataclass(frozen=True)
class DhcpIntent:
    """Intention DHCP déclarée, répartie par statut.

    Attributes:
        active: Réservations à porter par le routeur (MAC déjà en
            minuscules : invariant garanti par ``from_clients``).
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
        subnet: IPv4Network,
    ) -> "DhcpIntent":
        """Construit l'intention à partir des clients déclarés.

        Args:
            clients: Clients LAN déclarés (actifs et désactivés).
            subnet: Réseau IPv4 dans lequel une IP épinglée est admise
                (NetworkDevice ne porte que de l'IPv4).

        Returns:
            L'intention répartie en actifs, désactivés et ignorés.

        Raises:
            ValueError: Si une MAC est déclarée deux fois (désactivés
                compris) ou si deux clients actifs portent la même IP
                épinglée. Un client désactivé ne compte pas dans le
                contrôle d'IP.
        """
        _check_no_duplicate_mac(clients)
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
            pinned = client.pinned_ip.strip()
            active.append(
                NetworkDevice(
                    ip=pinned,
                    mac=client.mac.lower(),
                    hostname=client.name or "",
                    fixed_ip=pinned,
                )
            )
        _check_no_duplicate_ip(active)
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

        Raises:
            ValueError: Si ``actual`` contient deux fois la même MAC,
                ou si une réservation conservée partage l'IP d'une
                réservation active (messages : IP et noms, jamais la
                MAC).
        """
        seen = _index_by_mac(actual)
        declared = {d.mac for d in self.active}
        declared |= {c.mac.lower() for c in self.disabled}
        kept = [d for m, d in seen.items() if m not in declared]
        self._check_kept_ips(kept)
        return (*self.active, *kept)

    def _check_kept_ips(self, kept: Sequence[NetworkDevice]) -> None:
        """Refuse une réservation conservée sur l'IP d'un actif.

        Args:
            kept: Réservations du routeur non déclarées (conservées).

        Raises:
            ValueError: Si l'une partage l'IP d'une réservation active
                (message : l'IP et les deux noms, jamais de MAC).
        """
        owners = {
            _normalize_ip(d.fixed_ip): d.hostname
            for d in self.active
            if d.fixed_ip is not None
        }
        for device in kept:
            if device.fixed_ip is None:
                continue
            ip = _normalize_ip(device.fixed_ip)
            if ip in owners:
                raise ValueError(
                    f"IP {ip} en double : "
                    f"{owners[ip] or '(sans nom)'} et "
                    f"{device.hostname or '(sans nom)'}"
                )

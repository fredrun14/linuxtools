"""Tests de l'intention DHCP et du comparateur de réservations."""

from ipaddress import IPv4Network, IPv6Network

import pytest

from linuxtools.network.clients import LanClient
from linuxtools.network.models import NetworkDevice
from linuxtools.network.reservations import DhcpIntent

_SUBNET = IPv4Network("192.168.50.0/24")


def test_from_clients_actif_en_minuscules_avec_ip_fixe() -> None:
    """Un client actif épinglé devient un NetworkDevice MAC minuscules."""
    client = LanClient(
        mac="00:00:5E:00:53:03", name="shield", pinned_ip="192.168.50.3"
    )

    intent = DhcpIntent.from_clients([client], _SUBNET)

    assert len(intent.active) == 1
    device = intent.active[0]
    assert device.mac == "00:00:5e:00:53:03"
    assert device.fixed_ip == "192.168.50.3"
    assert device.ip == "192.168.50.3"
    assert device.hostname == "shield"
    assert intent.disabled == ()
    assert intent.ignored == ()


def test_from_clients_separe_les_desactives() -> None:
    """Un client enabled=False va dans disabled, jamais dans active."""
    off = LanClient(
        mac="00:00:5E:00:53:22",
        name="msiwifi",
        pinned_ip="192.168.50.22",
        enabled=False,
    )

    intent = DhcpIntent.from_clients([off], _SUBNET)

    assert intent.active == ()
    assert intent.disabled == (off,)


def test_from_clients_ignore_ip_hors_subnet() -> None:
    """Une IP épinglée hors du subnet rend le client ignoré (F-07)."""
    hors = LanClient(
        mac="00:00:5E:00:53:40", name="dehors", pinned_ip="10.0.0.5"
    )

    intent = DhcpIntent.from_clients([hors], _SUBNET)

    assert intent.active == ()
    assert intent.ignored == (hors,)


def test_from_clients_ignore_client_actif_sans_ip() -> None:
    """Un client actif sans IP épinglée est ignoré, pas actif."""
    sans = LanClient(mac="00:00:5E:00:53:41", name="dhcp-pur")

    intent = DhcpIntent.from_clients([sans], _SUBNET)

    assert intent.active == ()
    assert intent.ignored == (sans,)


def test_from_clients_ip_en_double_avec_desactive_leve_valueerror() -> None:
    """Deux clients, désactivés compris, sur la même IP : ValueError.

    Le message nomme l'IP et les deux noms, jamais une MAC.
    """
    actif = LanClient(
        mac="00:00:5E:00:53:03", name="shield", pinned_ip="192.168.50.3"
    )
    off = LanClient(
        mac="00:00:5E:00:53:22",
        name="msiwifi",
        pinned_ip="192.168.50.3",
        enabled=False,
    )

    with pytest.raises(ValueError) as exc:
        DhcpIntent.from_clients([actif, off], _SUBNET)

    message = str(exc.value)
    assert "192.168.50.3" in message
    assert "shield" in message
    assert "msiwifi" in message
    assert "00:00:5" not in message.lower()


def test_from_clients_subnet_ipv6_ignore_les_ip_v4() -> None:
    """Avec un subnet IPv6, une IP v4 épinglée est ignorée sans erreur."""
    client = LanClient(
        mac="00:00:5E:00:53:03", name="shield", pinned_ip="192.168.50.3"
    )

    intent = DhcpIntent.from_clients([client], IPv6Network("fd00::/64"))

    assert intent.active == ()
    assert intent.ignored == (client,)


def _dev(mac: str, ip: str, name: str = "") -> NetworkDevice:
    """Construit une réservation observée sur le routeur."""
    return NetworkDevice(ip=ip, mac=mac, hostname=name, fixed_ip=ip)


def test_target_conserve_les_reservations_non_declarees() -> None:
    """Une réservation du routeur absente du TOML survit (F-17)."""
    shield = LanClient(
        mac="00:00:5E:00:53:03", name="shield", pinned_ip="192.168.50.3"
    )
    intent = DhcpIntent.from_clients([shield], _SUBNET)
    tierce = _dev("AA:BB:CC:DD:EE:01", "192.168.50.99", "invite")

    cible = intent.target([tierce])

    assert [d.mac for d in cible] == [
        "00:00:5e:00:53:03",
        "aa:bb:cc:dd:ee:01",
    ]
    assert cible[1].fixed_ip == "192.168.50.99"


def test_target_exclut_les_desactivees_presentes_sur_le_routeur() -> None:
    """Une désactivée encore sur le routeur disparaît de la cible."""
    off = LanClient(
        mac="00:00:5E:00:53:22",
        name="msiwifi",
        pinned_ip="192.168.50.22",
        enabled=False,
    )
    intent = DhcpIntent.from_clients([off], _SUBNET)
    actual = [
        _dev("00:00:5E:00:53:22", "192.168.50.22", "msiwifi"),
        _dev("AA:BB:CC:DD:EE:01", "192.168.50.99"),
    ]

    cible = intent.target(actual)

    assert [d.mac for d in cible] == ["aa:bb:cc:dd:ee:01"]


def test_target_ne_contient_aucune_mac_en_double() -> None:
    """Ni une MAC déclarée, ni une non-déclarée lue deux fois, ne double."""
    shield = LanClient(
        mac="00:00:5E:00:53:03", name="shield", pinned_ip="192.168.50.3"
    )
    intent = DhcpIntent.from_clients([shield], _SUBNET)
    actual = [
        _dev("00:00:5e:00:53:03", "192.168.50.143", "shield"),
        _dev("AA:BB:CC:DD:EE:01", "192.168.50.99"),
        _dev("aa:bb:cc:dd:ee:01", "192.168.50.98"),
    ]

    cible = intent.target(actual)

    macs = [d.mac for d in cible]
    assert macs == ["00:00:5e:00:53:03", "aa:bb:cc:dd:ee:01"]
    # l'intention l'emporte sur l'IP lue pour une MAC déclarée
    assert cible[0].fixed_ip == "192.168.50.3"
    # la première occurrence lue est conservée
    assert cible[1].fixed_ip == "192.168.50.99"


def test_target_dedoublonne_une_mac_declaree_deux_fois() -> None:
    """Deux clients de même MAC (casse différente) : un seul élément."""
    a = LanClient(mac="AA:BB:CC:DD:EE:01", name="a", pinned_ip="192.168.50.10")
    b = LanClient(mac="aa:bb:cc:dd:ee:01", name="b", pinned_ip="192.168.50.11")
    intent = DhcpIntent.from_clients([a, b], _SUBNET)

    cible = intent.target([])

    assert [d.mac for d in cible] == ["aa:bb:cc:dd:ee:01"]
    assert cible[0].fixed_ip == "192.168.50.10"

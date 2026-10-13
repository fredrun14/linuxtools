"""Tests de l'intention DHCP et du comparateur de réservations."""

from ipaddress import IPv4Network, IPv6Network

import pytest

from linuxtools.network.clients import LanClient
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

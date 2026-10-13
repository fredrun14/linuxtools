"""Tests de l'intention DHCP et du comparateur de réservations."""

from ipaddress import IPv4Network
from typing import get_type_hints

import pytest

from linuxtools.network.clients import LanClient
from linuxtools.network.models import NetworkDevice
from linuxtools.network.reservations import (
    DhcpIntent,
    DriftKind,
    DriftReport,
    compare_reservations,
)

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


def test_from_clients_n_accepte_qu_un_subnet_ipv4() -> None:
    """La signature restreint subnet à IPv4Network (NetworkDevice IPv4)."""
    hints = get_type_hints(DhcpIntent.from_clients)

    assert hints["subnet"] is IPv4Network


def test_from_clients_ip_en_double_malgre_espaces_leve_valueerror() -> None:
    """Une IP désactivée écrite avec des espaces reste un doublon (F07)."""
    actif = LanClient(
        mac="00:00:5E:00:53:06", name="tv", pinned_ip="192.168.50.6"
    )
    off = LanClient(
        mac="00:00:5E:00:53:07",
        name="box",
        pinned_ip=" 192.168.50.6 ",
        enabled=False,
    )

    with pytest.raises(ValueError, match="en double"):
        DhcpIntent.from_clients([actif, off], _SUBNET)


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


def test_target_l_intention_l_emporte_sur_l_ip_lue_du_routeur() -> None:
    """Pour une MAC déclarée, l'IP de l'intention remplace celle lue."""
    shield = LanClient(
        mac="00:00:5E:00:53:03", name="shield", pinned_ip="192.168.50.3"
    )
    intent = DhcpIntent.from_clients([shield], _SUBNET)
    actual = [
        _dev("00:00:5e:00:53:03", "192.168.50.143", "shield"),
        _dev("AA:BB:CC:DD:EE:01", "192.168.50.99"),
    ]

    cible = intent.target(actual)

    assert [d.mac for d in cible] == [
        "00:00:5e:00:53:03",
        "aa:bb:cc:dd:ee:01",
    ]
    assert cible[0].fixed_ip == "192.168.50.3"
    assert cible[1].fixed_ip == "192.168.50.99"


def test_target_ip_actif_prise_par_conservee_leve_valueerror() -> None:
    """Une non-déclarée conservée sur l'IP d'un actif : refus d'écrire.

    Le message cite l'IP et les deux noms, jamais une MAC.
    """
    shield = LanClient(
        mac="00:00:5E:00:53:03", name="shield", pinned_ip="192.168.50.3"
    )
    intent = DhcpIntent.from_clients([shield], _SUBNET)
    actual = [_dev("AA:BB:CC:DD:EE:01", "192.168.50.3", "invite")]

    with pytest.raises(ValueError) as exc:
        intent.target(actual)

    assert str(exc.value) == "IP 192.168.50.3 en double : shield et invite"


def test_target_mac_en_double_sur_le_routeur_leve_valueerror() -> None:
    """Deux fois la même MAC lue (casse différente) : refus (F-17).

    Aucune perte silencieuse ; le message cite IP et noms, jamais la MAC.
    """
    intent = DhcpIntent.from_clients([], _SUBNET)
    actual = [
        _dev("AA:BB:CC:DD:EE:01", "192.168.50.99", "invite"),
        _dev("aa:bb:cc:dd:ee:01", "192.168.50.98"),
    ]

    with pytest.raises(ValueError) as exc:
        intent.target(actual)

    assert str(exc.value) == (
        "MAC en double sur le routeur : 192.168.50.99 (invite) et "
        "192.168.50.98 (sans nom)"
    )


def test_from_clients_mac_en_double_casse_comprise_leve_valueerror() -> None:
    """Deux clients de même MAC (casse différente) : ValueError.

    Le message nomme les deux clients, jamais la MAC.
    """
    a = LanClient(mac="AA:BB:CC:DD:EE:01", name="a", pinned_ip="192.168.50.10")
    b = LanClient(
        mac="aa:bb:cc:dd:ee:01",
        name="b",
        pinned_ip="192.168.50.11",
        enabled=False,
    )

    with pytest.raises(ValueError) as exc:
        DhcpIntent.from_clients([a, b], _SUBNET)

    assert str(exc.value) == "MAC en double dans l'intention : a et b"


def _client(mac: str, ip: str, name: str, enabled: bool = True) -> LanClient:
    """Construit un client déclaré pour les tests de comparaison."""
    return LanClient(mac=mac, name=name, pinned_ip=ip, enabled=enabled)


def _intent(*clients: LanClient) -> DhcpIntent:
    """Construit l'intention d'un jeu de clients (subnet de test)."""
    return DhcpIntent.from_clients(clients, _SUBNET)


def test_compare_sans_ecart_retourne_rapport_conforme() -> None:
    """Intention et routeur alignés : aucun écart."""
    intent = _intent(
        _client("00:00:5E:00:53:03", "192.168.50.3", "shield"),
        _client("00:00:5E:00:53:10", "192.168.50.10", "nas"),
    )

    report = compare_reservations(intent, list(intent.active))

    assert report.items == ()
    assert report.has_drift is False
    assert report.actionable is False
    assert report.declared == 2
    assert report.on_router == 2


def test_compare_detecte_reservation_manquante() -> None:
    """Une entrée active absente du routeur est un MISSING."""
    intent = _intent(
        _client("00:00:5E:00:53:03", "192.168.50.3", "shield"),
        _client("00:00:5E:00:53:10", "192.168.50.10", "nas"),
    )

    report = compare_reservations(intent, [intent.active[0]])

    assert len(report.items) == 1
    item = report.items[0]
    assert item.kind is DriftKind.MISSING
    assert item.mac == "00:00:5e:00:53:10"
    assert item.name == "nas"
    assert item.expected_ip == "192.168.50.10"
    assert item.actual_ip is None
    assert report.actionable is True


def test_compare_detecte_ip_divergente() -> None:
    """Même MAC, autre IP sur le routeur : IP_MISMATCH."""
    intent = _intent(_client("00:00:5E:00:53:24", "192.168.50.24", "xps15"))
    actual = [_dev("00:00:5E:00:53:24", "192.168.50.143", "xps15")]

    report = compare_reservations(intent, actual)

    assert len(report.items) == 1
    item = report.items[0]
    assert item.kind is DriftKind.IP_MISMATCH
    assert item.name == "xps15"
    assert item.expected_ip == "192.168.50.24"
    assert item.actual_ip == "192.168.50.143"


def test_compare_signale_reservation_non_declaree() -> None:
    """Une réservation tierce est signalée en UNDECLARED, pas actionable."""
    intent = _intent(_client("00:00:5E:00:53:03", "192.168.50.3", "shield"))
    actual = [
        intent.active[0],
        _dev("AA:BB:CC:DD:EE:01", "192.168.50.99", "invite-inconnu"),
    ]

    report = compare_reservations(intent, actual)

    assert len(report.items) == 1
    item = report.items[0]
    assert item.kind is DriftKind.UNDECLARED
    assert item.mac == "aa:bb:cc:dd:ee:01"
    assert item.name == "invite-inconnu"
    assert item.actual_ip == "192.168.50.99"
    assert item.expected_ip is None
    assert report.has_drift is True
    assert report.actionable is False


def test_compare_ignore_entree_desactivee_absente() -> None:
    """Une entrée enabled=false absente du routeur est l'état attendu."""
    intent = _intent(
        _client("00:00:5E:00:53:03", "192.168.50.3", "shield"),
        _client("00:00:5E:00:53:22", "192.168.50.22", "msiwifi", False),
    )

    report = compare_reservations(intent, [intent.active[0]])

    assert report.items == ()
    assert report.has_drift is False
    assert report.declared == 1


def test_compare_signale_entree_desactivee_encore_presente() -> None:
    """Une entrée retirée qui réapparaît est un STALE_DISABLED."""
    intent = _intent(
        _client("00:00:5E:00:53:22", "192.168.50.22", "msiwifi", False)
    )
    actual = [_dev("00:00:5E:00:53:22", "192.168.50.22", "msiwifi")]

    report = compare_reservations(intent, actual)

    assert len(report.items) == 1
    item = report.items[0]
    assert item.kind is DriftKind.STALE_DISABLED
    assert item.name == "msiwifi"
    assert item.actual_ip == "192.168.50.22"
    assert report.actionable is True


def test_compare_ordonne_les_ecarts_par_gravite() -> None:
    """MISSING, IP_MISMATCH, STALE_DISABLED puis UNDECLARED.

    Les entrées sont fournies dans l'ordre inverse pour exercer le tri.
    """
    intent = _intent(
        _client("00:00:5E:00:53:22", "192.168.50.22", "msiwifi", False),
        _client("00:00:5E:00:53:24", "192.168.50.24", "xps15"),
        _client("00:00:5E:00:53:32", "192.168.50.32", "tab2018"),
    )
    actual = [
        _dev("AA:BB:CC:DD:EE:01", "192.168.50.99", "inconnu"),
        _dev("00:00:5E:00:53:22", "192.168.50.22"),
        _dev("00:00:5E:00:53:24", "192.168.50.143"),
    ]

    report = compare_reservations(intent, actual)

    assert [item.kind for item in report.items] == [
        DriftKind.MISSING,
        DriftKind.IP_MISMATCH,
        DriftKind.STALE_DISABLED,
        DriftKind.UNDECLARED,
    ]


def test_format_summary_decrit_les_quatre_natures_d_ecart() -> None:
    """Le texte est identique à celui de scanNetHome (littéral exact)."""
    intent = _intent(
        _client("00:00:5E:00:53:22", "192.168.50.22", "msiwifi", False),
        _client("00:00:5E:00:53:24", "192.168.50.24", "xps15"),
        _client("00:00:5E:00:53:32", "192.168.50.32", "tab2018"),
    )
    actual = [
        _dev("AA:BB:CC:DD:EE:01", "192.168.50.99"),
        _dev("00:00:5E:00:53:22", "192.168.50.22"),
        _dev("00:00:5E:00:53:24", "192.168.50.143"),
    ]

    resume = compare_reservations(intent, actual).format_summary()

    assert resume == (
        "4 ecart(s) — 2 declaree(s) active(s), 3 sur le routeur\n"
        "  MANQUANTE   00:00:5e:00:53:32  tab2018 — attendue en "
        "192.168.50.32, absente du routeur\n"
        "  IP DIVERGE  00:00:5e:00:53:24  xps15 — attendue "
        "192.168.50.24, routeur 192.168.50.143\n"
        "  RESURGENTE  00:00:5e:00:53:22  msiwifi — retiree "
        "volontairement, encore presente en 192.168.50.22\n"
        "  NON DECLAREE aa:bb:cc:dd:ee:01  (sans libelle) — presente "
        "en 192.168.50.99, absente du TOML (conservee)"
    )


def test_format_summary_conforme_ne_parle_pas_d_ecart() -> None:
    """Le résumé d'un état conforme le dit explicitement."""
    resume = DriftReport(declared=17, on_router=17).format_summary()

    assert resume == (
        "Conforme — 17 reservation(s) active(s), 17 sur le routeur"
    )


def test_from_clients_ignore_ip_illisible() -> None:
    """Une IP épinglée illisible est ignorée, sans lever d'erreur."""
    client = LanClient(
        mac="00:00:5E:00:53:03", name="x", pinned_ip="pas-une-ip"
    )

    intent = DhcpIntent.from_clients([client], _SUBNET)

    assert intent.ignored == (client,)


def test_from_clients_desactive_sans_ip_ne_compte_pas_comme_doublon() -> None:
    """Deux désactivés sans IP épinglée ne sont pas un doublon d'IP."""
    a = LanClient(mac="00:00:5E:00:53:01", name="a", enabled=False)
    b = LanClient(mac="00:00:5E:00:53:02", name="b", enabled=False)

    intent = DhcpIntent.from_clients([a, b], _SUBNET)

    assert intent.disabled == (a, b)


def test_compare_client_ignore_avec_reservation_est_hors_perimetre() -> None:
    """R-4 : un client déclaré mais ignoré n'est pas « non déclaré ».

    Libellé distinct, non actionnable, et la réservation reste dans la
    cible (conservée).
    """
    dehors = _client("00:00:5E:00:53:40", "10.0.0.5", "dehors")
    intent = _intent(dehors)
    actual = [_dev("00:00:5E:00:53:40", "192.168.50.40", "dehors")]

    report = compare_reservations(intent, actual)

    assert report.actionable is False
    assert report.format_summary() == (
        "1 ecart(s) — 0 declaree(s) active(s), 1 sur le routeur\n"
        "  DECLAREE HORS PERIMETRE DHCP 00:00:5e:00:53:40  dehors — "
        "presente en 192.168.50.40 sur le routeur, IP epinglee absente, "
        "invalide ou hors subnet (conservee)"
    )
    assert [d.mac for d in intent.target(actual)] == ["00:00:5e:00:53:40"]


def test_compare_routeur_vide_ne_produit_que_des_manquantes() -> None:
    """Sans aucune réservation lue, chaque actif est MISSING."""
    intent = _intent(
        _client("00:00:5E:00:53:03", "192.168.50.3", "shield"),
        _client("00:00:5E:00:53:10", "192.168.50.10", "nas"),
        _client("00:00:5E:00:53:22", "192.168.50.22", "msiwifi", False),
    )

    report = compare_reservations(intent, [])

    assert [i.kind for i in report.items] == [DriftKind.MISSING] * 2
    assert report.on_router == 0
    assert report.actionable is True


def test_compare_mac_majuscule_declaree_face_a_routeur_minuscule() -> None:
    """Un vrai LanClient en majuscules est conforme à un routeur minuscule."""
    intent = _intent(_client("00:00:5E:00:53:03", "192.168.50.3", "shield"))
    actual = [_dev("00:00:5e:00:53:03", "192.168.50.3", "shield")]

    report = compare_reservations(intent, actual)

    assert report.items == ()


def test_from_clients_deux_actifs_meme_ip_leve_valueerror() -> None:
    """Deux actifs sur la même IP : ValueError, noms cités."""
    a = _client("00:00:5E:00:53:03", "192.168.50.3", "shield")
    b = _client("00:00:5E:00:53:04", "192.168.50.3", "nas")

    with pytest.raises(ValueError) as exc:
        DhcpIntent.from_clients([a, b], _SUBNET)

    assert str(exc.value) == "IP 192.168.50.3 en double : shield et nas"


def test_from_clients_deux_desactives_meme_ip_leve_valueerror() -> None:
    """Deux désactivés sur la même IP : ValueError (réactivation sûre)."""
    a = _client("00:00:5E:00:53:03", "192.168.50.3", "shield", False)
    b = _client("00:00:5E:00:53:04", "192.168.50.3", "nas", False)

    with pytest.raises(ValueError) as exc:
        DhcpIntent.from_clients([a, b], _SUBNET)

    assert str(exc.value) == "IP 192.168.50.3 en double : shield et nas"


def test_from_clients_doublon_sans_nom_dit_sans_nom_et_pas_de_mac() -> None:
    """Noms vides : « (sans nom) », et aucune MAC dans les messages."""
    a = LanClient(mac="00:00:5E:00:53:03", pinned_ip="192.168.50.3")
    b = LanClient(mac="00:00:5E:00:53:04", pinned_ip="192.168.50.3")
    c = LanClient(mac="00:00:5E:00:53:05")
    d = LanClient(mac="00:00:5E:00:53:05")

    with pytest.raises(ValueError) as ip_exc:
        DhcpIntent.from_clients([a, b], _SUBNET)
    with pytest.raises(ValueError) as mac_exc:
        DhcpIntent.from_clients([c, d], _SUBNET)

    assert str(ip_exc.value) == (
        "IP 192.168.50.3 en double : (sans nom) et (sans nom)"
    )
    assert str(mac_exc.value) == (
        "MAC en double dans l'intention : (sans nom) et (sans nom)"
    )

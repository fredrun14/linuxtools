"""Tests de comportement complémentaires pour le module network.

Aucun accès réseau réel : routeur, ARP et nmap sont simulés.
"""

import os
import socket
from datetime import datetime
from ipaddress import IPv4Network
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from webapitools.core.exceptions import AuthError

from linuxtools.logging.base import Logger
from linuxtools.network.clients import LanClient
from linuxtools.network.config import DhcpRange, NetworkConfig
from linuxtools.network.models import NetworkDevice
from linuxtools.network.repository import JsonDeviceRepository
from linuxtools.network.reservations import DhcpIntent
from linuxtools.network.router import (
    AsusRouterClient,
    AsusRouterDhcpManager,
    AsusRouterMacFilterManager,
    AsusRouterScanner,
    RouterAuthError,
    RouterConfig,
)
from linuxtools.network.scanner import LinuxArpScanner, LinuxNmapScanner
from tests.unit.couverture_helpers import cmd_result, descripteurs_ouverts

MAC = "aa:bb:cc:dd:ee:ff"


@pytest.fixture
def routeur() -> RouterConfig:
    """Configuration de routeur de test."""
    return RouterConfig(url="http://192.168.50.1", password="x")


@pytest.fixture
def client() -> MagicMock:
    """Client routeur simulé."""
    return MagicMock(spec=AsusRouterClient)


@pytest.fixture
def reseau() -> NetworkConfig:
    """Configuration réseau de test."""
    return NetworkConfig(
        cidr="192.168.50.0/24",
        interface="eth0",
        dhcp_range=DhcpRange(start="192.168.50.100", end="192.168.50.254"),
    )


# --- config / models / repository ---


def test_debit_de_scan_nul_est_refuse() -> None:
    """Un débit de scan nul ou négatif est refusé."""
    with pytest.raises(ValueError, match="scan_bandwidth invalide : 0"):
        NetworkConfig(cidr="192.168.1.0/24", scan_bandwidth=0)


def test_from_dict_garde_les_dates_deja_typees() -> None:
    """Des datetimes déjà construits sont conservés tels quels."""
    premiere = datetime(2026, 1, 2, 3, 4, 5)
    derniere = datetime(2026, 6, 7, 8, 9, 10)

    appareil = NetworkDevice.from_dict(
        {"ip": "10.0.0.1", "mac": MAC, "first_seen": premiere, "last_seen": derniere}
    )

    assert (appareil.first_seen, appareil.last_seen) == (premiere, derniere)


def test_from_dict_sans_dates_en_attribue_par_defaut() -> None:
    """Sans dates fournies, l'appareil reçoit des dates à l'instant courant."""
    avant = datetime.now()  # noqa: DTZ005 — le modèle produit des dates naïves

    appareil = NetworkDevice.from_dict({"ip": "10.0.0.1", "mac": MAC})

    assert avant <= appareil.first_seen <= datetime.now()  # noqa: DTZ005 — idem
    assert avant <= appareil.last_seen <= datetime.now()  # noqa: DTZ005 — idem


def test_save_en_echec_ne_laisse_aucun_fichier_temporaire(tmp_path: Path) -> None:
    """Si le remplacement échoue, l'exception remonte et le temporaire est supprimé."""
    cible = tmp_path / "devices.json"
    cible.mkdir()  # un dossier à la place du fichier : le remplacement échoue
    depot = JsonDeviceRepository(str(cible))

    with pytest.raises(OSError, match=r"devices\.json"):
        depot.save([NetworkDevice(ip="10.0.0.1", mac=MAC)])

    assert sorted(p.name for p in tmp_path.iterdir()) == ["devices.json"]


def test_save_echec_tardif_de_fdopen_propage_l_erreur_d_origine(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Échec réel de fdopen après prise du fd : erreur d'origine, ni fuite ni résidu."""
    vrai_fdopen = os.fdopen

    def _fdopen_encodage_invalide(fd: int, mode: str, **_: Any) -> Any:
        # io.open prend le fd puis échoue sur l'encodage, et ferme le fd lui-même
        return vrai_fdopen(fd, mode, encoding="encodage-inexistant")

    monkeypatch.setattr(os, "fdopen", _fdopen_encodage_invalide)
    depot = JsonDeviceRepository(str(tmp_path / "devices.json"))
    avant = descripteurs_ouverts()

    with pytest.raises(LookupError, match="encodage-inexistant"):
        depot.save([NetworkDevice(ip="10.0.0.1", mac=MAC)])

    assert descripteurs_ouverts() == avant
    assert list(tmp_path.iterdir()) == []


# --- reservations ---


def test_deux_clients_actifs_sur_la_meme_ip_sont_refuses() -> None:
    """Deux clients actifs épinglés sur la même IP lèvent une ValueError."""
    clients = [
        LanClient(mac="AA:BB:CC:DD:EE:01", name="a", pinned_ip="192.168.50.10"),
        LanClient(mac="AA:BB:CC:DD:EE:02", name="b", pinned_ip="192.168.50.10"),
    ]

    with pytest.raises(ValueError, match=r"IP 192\.168\.50\.10 en double : a et b"):
        DhcpIntent.from_clients(clients, IPv4Network("192.168.50.0/24"))


# --- router.client ---


def test_url_de_routeur_sans_hostname_est_refusee() -> None:
    """Une URL http sans hôte est refusée."""
    with pytest.raises(ValueError, match="sans hostname"):
        RouterConfig(url="http://")


def test_hostname_dont_une_resolution_est_illisible_est_ignoree_puis_controlee() -> (
    None
):
    """Une adresse illisible est sautée ; les suivantes restent contrôlées."""
    reponse = [
        (socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("pas-une-ip", 0, 0, 0)),
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 0)),
    ]

    with (
        patch(
            "linuxtools.network.router.client.socket.getaddrinfo", return_value=reponse
        ),
        pytest.raises(ValueError, match=r"non-LAN : '8\.8\.8\.8'"),
    ):
        RouterConfig(url="http://nom-local")


# --- router.dhcp ---


@pytest.mark.filterwarnings("ignore:AsusRouterDhcpManager:DeprecationWarning")
def test_generation_de_reservations_sans_logger(
    reseau: NetworkConfig, routeur: RouterConfig, client: MagicMock
) -> None:
    """Sans logger, la première IP libre de la plage est attribuée."""
    gestionnaire = AsusRouterDhcpManager(reseau, routeur, client=client)

    resultat = gestionnaire.generate_reservations(
        [NetworkDevice(ip="192.168.50.20", mac=MAC)]
    )

    assert [d.fixed_ip for d in resultat] == ["192.168.50.100"]


@pytest.mark.filterwarnings("ignore:AsusRouterDhcpManager:DeprecationWarning")
def test_application_de_reservations_sans_logger(
    reseau: NetworkConfig, routeur: RouterConfig, client: MagicMock
) -> None:
    """Sans logger, les réservations sont poussées puis la session fermée."""
    client.get_nvram.return_value = {}
    gestionnaire = AsusRouterDhcpManager(reseau, routeur, client=client)

    gestionnaire.apply_reservations(
        [
            NetworkDevice(
                ip="192.168.50.20",
                mac=MAC,
                hostname="nas",
                fixed_ip="192.168.50.20",
            )
        ]
    )

    client.set_static_reservations.assert_called_once_with(
        "<AA:BB:CC:DD:EE:FF>192.168.50.20", "<AA:BB:CC:DD:EE:FF>nas", {}
    )
    client.logout.assert_called_once_with()


@pytest.mark.filterwarnings("ignore:AsusRouterDhcpManager:DeprecationWarning")
def test_lecture_de_reservations_echoue_si_l_authentification_echoue(
    reseau: NetworkConfig, routeur: RouterConfig, client: MagicMock
) -> None:
    """Un échec de login est traduit en RouterAuthError, sans lecture NVRAM."""
    client.login.side_effect = AuthError("refusé")
    gestionnaire = AsusRouterDhcpManager(reseau, routeur, client=client)

    with pytest.raises(RouterAuthError, match="refusé"):
        gestionnaire.read_reservations()

    client.get_nvram.assert_not_called()


@pytest.mark.filterwarnings("ignore:AsusRouterDhcpManager:DeprecationWarning")
def test_lecture_de_reservations_ignore_les_entrees_sans_ip(
    reseau: NetworkConfig, routeur: RouterConfig, client: MagicMock
) -> None:
    """Une entrée NVRAM sans IP est ignorée, les autres sont lues."""
    client.get_nvram.return_value = {
        "dhcp_staticlist": "<AA:BB:CC:DD:EE:01>>><AA:BB:CC:DD:EE:02>192.168.50.5",
        "dhcp_hostnames": "",
    }
    gestionnaire = AsusRouterDhcpManager(reseau, routeur, client=client)

    resultat = gestionnaire.read_reservations()

    assert [(d.mac, d.fixed_ip) for d in resultat] == [
        ("aa:bb:cc:dd:ee:02", "192.168.50.5")
    ]


# --- router.mac_filter ---


def test_application_du_filtre_mac_sans_logger(
    routeur: RouterConfig, client: MagicMock
) -> None:
    """Sans logger, le filtre est appliqué avec les MAC des appareils."""
    gestionnaire = AsusRouterMacFilterManager(routeur, client=client)

    gestionnaire.apply_mac_filter([NetworkDevice(ip="10.0.0.1", mac=MAC)], "allow", [0])

    client.set_mac_filter.assert_called_once_with("allow", [MAC], [0])
    client.logout.assert_called_once_with()


def test_lecture_du_filtre_mac_echoue_si_l_authentification_echoue(
    routeur: RouterConfig, client: MagicMock
) -> None:
    """Un échec de login est traduit en RouterAuthError, sans lecture NVRAM."""
    client.login.side_effect = AuthError("refusé")
    gestionnaire = AsusRouterMacFilterManager(routeur, client=client)

    with pytest.raises(RouterAuthError, match="refusé"):
        gestionnaire.read_mac_filter([0])

    client.get_nvram.assert_not_called()


# --- router.scanner ---


def test_scan_routeur_ignore_un_client_a_l_ip_invalide(
    routeur: RouterConfig, client: MagicMock, reseau: NetworkConfig
) -> None:
    """Un client dont l'IP est invalide est écarté, le client valide est gardé."""
    brut: list[dict[str, Any]] = [
        {"mac": "AA:BB:CC:DD:EE:01", "ip": "999.1.1.1", "name": "casse"},
        {"mac": "AA:BB:CC:DD:EE:02", "ip": "192.168.50.7", "name": "bon"},
    ]
    client.get_clients.return_value = brut
    client.get_dhcp_leases.return_value = {}
    client.get_nvram.return_value = {}

    appareils = AsusRouterScanner(routeur, client=client).scan(reseau)

    assert [(d.mac, d.ip) for d in appareils] == [("aa:bb:cc:dd:ee:02", "192.168.50.7")]


# --- scanner.py (arp-scan / nmap simulés) ---


def _executeur(sortie: str, executeur: MagicMock) -> MagicMock:
    """Configure l'exécuteur simulé pour renvoyer ``sortie``."""
    executeur.run.return_value = cmd_result(stdout=sortie)
    return executeur


def test_arp_scan_ignore_les_lignes_de_synthese_a_tabulation(
    reseau: NetworkConfig, executeur: MagicMock
) -> None:
    """Une ligne de synthèse contenant une tabulation n'est pas un appareil."""
    sortie = (
        f"192.168.50.1\t{MAC}\tVendor\n"
        "192.168.50.9\taa:bb:cc:dd:ee:01\t3 packets received\n"
    )

    appareils = LinuxArpScanner(executor=_executeur(sortie, executeur)).scan(reseau)

    assert [(d.ip, d.mac, d.vendor) for d in appareils] == [
        ("192.168.50.1", MAC, "Vendor")
    ]


def test_nmap_sans_interface_ni_logger_n_ajoute_pas_l_option_e(
    executeur: MagicMock,
) -> None:
    """Sans interface détectée, la commande nmap n'a pas d'option -e."""
    config = NetworkConfig(cidr="192.168.50.0/24")
    xml = (
        "<nmaprun><host><status state='up'/>"
        "<address addr='192.168.50.1' addrtype='ipv4'/>"
        f"<address addr='{MAC}' addrtype='mac' vendor='V'/>"
        "<hostnames/></host></nmaprun>"
    )

    with patch("linuxtools.network.scanner._detect_interface", return_value=""):
        appareils = LinuxNmapScanner(executor=_executeur(xml, executeur)).scan(config)

    commande = executeur.run.call_args.args[0]
    assert commande == ["sudo", "nmap", "-sn", "-oX", "-", "192.168.50.0/24"]
    assert [d.ip for d in appareils] == ["192.168.50.1"]


def test_nmap_sans_element_hostnames_donne_un_nom_vide(
    reseau: NetworkConfig, executeur: MagicMock
) -> None:
    """Un hôte nmap sans élément hostnames donne un appareil au nom vide."""
    xml = (
        "<nmaprun><host><status state='up'/>"
        "<address addr='192.168.50.1' addrtype='ipv4'/>"
        f"<address addr='{MAC}' addrtype='mac'/>"
        "</host></nmaprun>"
    )

    appareils = LinuxNmapScanner(executor=_executeur(xml, executeur)).scan(reseau)

    assert [d.hostname for d in appareils] == [""]


def test_scan_nmap_avec_logger_trace_le_nombre_d_appareils(
    reseau: NetworkConfig, executeur: MagicMock
) -> None:
    """Avec logger, le nombre d'appareils découverts est tracé."""
    logger = MagicMock(spec=Logger)

    LinuxNmapScanner(logger, _executeur("<nmaprun/>", executeur)).scan(reseau)

    logger.log_info.assert_called_once_with("nmap : 0 peripherique(s) decouvert(s)")

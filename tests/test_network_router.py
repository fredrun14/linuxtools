"""Tests pour le module router (AsusRouterClient et AsusRouterScanner).

Valide en particulier que les appareils offline (isOnline==0)
sont bien inclus dans les resultats du scan.

``AsusRouterClient`` est desormais fourni par ``webapitools`` (temps
2/3 du chantier cross-repo) : les tests de son transport HTTP bas
niveau (login/logout/get_nvram/set_mac_filter, contexte SSL, urllib)
vivent cote ``webapitools`` (``test_asus_router.py``), pas ici. Ce
fichier ne teste plus que les 3 adaptateurs metier de linuxtools, en
injectant un ``AsusRouterClient`` mocke.
"""

import socket
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from webapitools.core.exceptions import AuthError

from linuxtools.network.config import DhcpRange, NetworkConfig
from linuxtools.network.ip_utils import (
    _int_to_ip,
    _ip_to_int,
    _next_available_ip,
)
from linuxtools.network.models import MacFilterStatus, NetworkDevice
from linuxtools.network.router import (
    AsusRouterClient,
    AsusRouterDhcpManager,
    AsusRouterMacFilterManager,
    AsusRouterScanner,
    RouterAuthError,
    RouterConfig,
)
from linuxtools.network.router._nvram import (
    _parse_custom_clientlist,
    _parse_nvram_reservations,
)
from linuxtools.network.vendors import _infer_type_from_vendor

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def router_config() -> RouterConfig:
    """Configuration routeur de test."""
    return RouterConfig(
        url="http://192.168.50.1",
        timeout=10,
        username="admin",
        password="secret",
    )


@pytest.fixture
def network_config() -> NetworkConfig:
    """Configuration reseau de test."""
    return NetworkConfig(
        cidr="192.168.50.0/24",
        dhcp_range=DhcpRange(
            start="192.168.50.100",
            end="192.168.50.254",
        ),
    )


@pytest.fixture
def mock_client() -> MagicMock:
    """Client HTTP mocke (spec sur webapitools.AsusRouterClient)."""
    return MagicMock(spec=AsusRouterClient)


@pytest.fixture
def scanner(
    router_config: RouterConfig,
    mock_client: MagicMock,
) -> AsusRouterScanner:
    """Scanner avec client HTTP mocke."""
    return AsusRouterScanner(
        router_config, client=mock_client
    )


# ---------------------------------------------------------------------------
# Tests : _parse_custom_clientlist
# ---------------------------------------------------------------------------

class TestParseCustomClientlist:
    """Tests pour _parse_custom_clientlist."""

    def test_parse_entree_simple(self) -> None:
        """Une entree valide est correctement parsee."""
        raw = "<Shield>48:B0:2D:03:1E:EA>5>"
        result = _parse_custom_clientlist(raw)
        assert result == {"48:b0:2d:03:1e:ea": "Shield"}

    def test_parse_multiple_entrees(self) -> None:
        """Plusieurs entrees sont toutes parsees."""
        raw = (
            "<Shield>48:B0:2D:03:1E:EA>5>"
            "<Thermomix>58:16:D7:F1:77:6E>9>"
            "<NanouIphone>E2:B7:BE:2B:BD:2F>5>"
        )
        result = _parse_custom_clientlist(raw)
        assert len(result) == 3
        assert result["48:b0:2d:03:1e:ea"] == "Shield"
        assert result["58:16:d7:f1:77:6e"] == "Thermomix"
        assert result["e2:b7:be:2b:bd:2f"] == "NanouIphone"

    def test_mac_normalise_en_minuscules(self) -> None:
        """Les MACs sont normalises en minuscules."""
        raw = "<Test>AA:BB:CC:DD:EE:FF>0>"
        result = _parse_custom_clientlist(raw)
        assert "aa:bb:cc:dd:ee:ff" in result

    def test_entree_sans_nickname_ignoree(self) -> None:
        """Une entree avec nickname vide est ignoree."""
        raw = "<>48:B0:2D:03:1E:EA>5>"
        result = _parse_custom_clientlist(raw)
        assert result == {}

    def test_chaine_vide_retourne_dict_vide(self) -> None:
        """Une chaine vide retourne un dict vide."""
        result = _parse_custom_clientlist("")
        assert result == {}

    def test_mac_invalide_ignoree(self) -> None:
        """Une entree avec MAC invalide est ignoree."""
        raw = "<Test>GG:HH:II:JJ:KK:LL>0>"
        result = _parse_custom_clientlist(raw)
        assert result == {}

    def test_entites_html_decodees(self) -> None:
        """Les entites HTML &#60 et &#62 sont decodees."""
        raw = (
            "&#60print&#627C:4D:8F:4C:A4:66&#620&#62"
            "&#60REXCam&#6290:6A:94:4B:AD:2B&#620&#62"
        )
        result = _parse_custom_clientlist(raw)
        assert "7c:4d:8f:4c:a4:66" in result
        assert result["7c:4d:8f:4c:a4:66"] == "print"
        assert "90:6a:94:4b:ad:2b" in result
        assert result["90:6a:94:4b:ad:2b"] == "REXCam"


# ---------------------------------------------------------------------------
# Tests : _parse_nvram_reservations
# ---------------------------------------------------------------------------

class TestParseNvramReservations:
    """Tests pour _parse_nvram_reservations."""

    def test_parse_nvram_reservations_decode_entites_html(
        self,
    ) -> None:
        """Les entites HTML &#60 et &#62 sont decodees (cas reel)."""
        static_list = (
            "&#6028:73:F6:FE:30:3E&#62192.168.50.41"
            "&#60A8:CA:77:5E:EC:A0&#62192.168.50.42"
        )
        result = _parse_nvram_reservations(static_list, "")
        assert result["28:73:f6:fe:30:3e"] == (
            "192.168.50.41", ""
        )
        assert result["a8:ca:77:5e:ec:a0"] == (
            "192.168.50.42", ""
        )

    def test_parse_nvram_reservations_format_non_encode_toujours_ok(
        self,
    ) -> None:
        """Le format non encode (ancien firmware) reste supporte."""
        static_list = (
            "<28:73:F6:FE:30:3E>192.168.50.41"
            "<A8:CA:77:5E:EC:A0>192.168.50.42"
        )
        result = _parse_nvram_reservations(static_list, "")
        assert result["28:73:f6:fe:30:3e"] == (
            "192.168.50.41", ""
        )
        assert result["a8:ca:77:5e:ec:a0"] == (
            "192.168.50.42", ""
        )

    def test_parse_nvram_reservations_hostnames_encodes(
        self,
    ) -> None:
        """Le decodage HTML s'applique aussi a dhcp_hostnames."""
        static_list = "<28:73:F6:FE:30:3E>192.168.50.41"
        hostnames_str = "&#6028:73:F6:FE:30:3E&#62Shield"
        result = _parse_nvram_reservations(
            static_list, hostnames_str
        )
        assert result["28:73:f6:fe:30:3e"] == (
            "192.168.50.41", "Shield"
        )


# ---------------------------------------------------------------------------
# Tests : AsusRouterScanner._merge_offline_clients
# ---------------------------------------------------------------------------

class TestMergeOfflineClients:
    """Tests pour _merge_offline_clients."""

    def test_client_online_non_duplique(
        self, scanner: AsusRouterScanner
    ) -> None:
        """Un client online n'est pas ajoute en double."""
        raw = [
            {
                "mac": "48:b0:2d:03:1e:ea",
                "ip": "192.168.50.3",
                "isOnline": "1",
                "nickName": "Shield",
            }
        ]
        custom = {"48:b0:2d:03:1e:ea": "Shield"}
        leases: dict[str, str] = {}
        reservations: dict[str, tuple[str, str]] = {}
        result = scanner._merge_offline_clients(
            raw, custom, leases, reservations
        )
        assert len(result) == 1

    def test_client_offline_ajoute_si_bail_connu(
        self, scanner: AsusRouterScanner
    ) -> None:
        """Client offline avec bail DHCP actif est ajoute."""
        raw: list[dict[str, Any]] = []
        custom = {"58:16:d7:f1:77:6e": "Thermomix"}
        leases = {"58:16:d7:f1:77:6e": "192.168.50.7"}
        reservations: dict[str, tuple[str, str]] = {}
        result = scanner._merge_offline_clients(
            raw, custom, leases, reservations
        )
        assert len(result) == 1
        assert result[0]["mac"] == "58:16:d7:f1:77:6e"
        assert result[0]["ip"] == "192.168.50.7"
        assert result[0]["isOnline"] == "0"
        assert result[0]["nickName"] == "Thermomix"

    def test_client_offline_ajoute_si_reservation_statique(
        self, scanner: AsusRouterScanner
    ) -> None:
        """Client offline avec reservation DHCP est ajoute."""
        raw: list[dict[str, Any]] = []
        custom = {"7c:4d:8f:4c:a4:66": "print"}
        leases: dict[str, str] = {}
        reservations = {
            "7c:4d:8f:4c:a4:66": ("192.168.50.20", ""),
        }
        result = scanner._merge_offline_clients(
            raw, custom, leases, reservations
        )
        assert len(result) == 1
        assert result[0]["ip"] == "192.168.50.20"
        assert result[0]["ipMethod"] == "Manual"

    def test_client_offline_inclus_sans_ip(
        self, scanner: AsusRouterScanner
    ) -> None:
        """Client offline sans IP est inclus avec ip=''."""
        raw: list[dict[str, Any]] = []
        custom = {"aa:bb:cc:dd:ee:ff": "Inconnu"}
        leases: dict[str, str] = {}
        reservations: dict[str, tuple[str, str]] = {}
        result = scanner._merge_offline_clients(
            raw, custom, leases, reservations
        )
        assert len(result) == 1
        assert result[0]["ip"] == ""
        assert result[0]["isOnline"] == "0"

    def test_fusion_online_et_offline(
        self, scanner: AsusRouterScanner
    ) -> None:
        """Online et offline sont fusionnes correctement."""
        raw = [
            {
                "mac": "48:b0:2d:03:1e:ea",
                "ip": "192.168.50.3",
                "isOnline": "1",
                "nickName": "Shield",
            }
        ]
        custom = {
            "48:b0:2d:03:1e:ea": "Shield",
            "58:16:d7:f1:77:6e": "Thermomix",
        }
        leases = {"58:16:d7:f1:77:6e": "192.168.50.7"}
        reservations: dict[str, tuple[str, str]] = {}
        result = scanner._merge_offline_clients(
            raw, custom, leases, reservations
        )
        assert len(result) == 2


# ---------------------------------------------------------------------------
# Tests : AsusRouterScanner._parse_clients
# ---------------------------------------------------------------------------

class TestAsusRouterScannerParseClients:
    """Tests pour _parse_clients avec cas offline."""

    def test_appareil_online_ip_directe(
        self, scanner: AsusRouterScanner
    ) -> None:
        """Appareil online : IP issue du champ ip."""
        raw = [
            {
                "mac": "48:b0:2d:03:1e:ea",
                "ip": "192.168.50.3",
                "isOnline": "1",
                "nickName": "Shield",
                "vendor": "NVIDIA",
                "dpiDevice": "AndroidTV",
                "ipMethod": "Manual",
            }
        ]
        result = scanner._parse_clients(raw, {}, {})
        assert len(result) == 1
        assert result[0].ip == "192.168.50.3"
        assert result[0].hostname == "Shield"

    def test_appareil_offline_avec_ip_connue(
        self, scanner: AsusRouterScanner
    ) -> None:
        """Appareil offline dont le routeur connait la derniere IP."""
        raw = [
            {
                "mac": "58:16:d7:f1:77:6e",
                "ip": "192.168.50.7",
                "isOnline": "0",
                "nickName": "Thermomix",
                "vendor": "Vorwerk",
                "dpiDevice": "",
                "ipMethod": "Manual",
            }
        ]
        result = scanner._parse_clients(raw, {}, {})
        assert len(result) == 1
        assert result[0].ip == "192.168.50.7"
        assert result[0].hostname == "Thermomix"

    def test_appareil_offline_ip_zero_fallback_bail_dhcp(
        self, scanner: AsusRouterScanner
    ) -> None:
        """IP=0.0.0.0 → fallback sur le bail DHCP actif."""
        raw = [
            {
                "mac": "dc:46:28:2f:ae:f4",
                "ip": "0.0.0.0",
                "isOnline": "0",
                "nickName": "Asustuf5G",
                "vendor": "ASUSTeK",
                "dpiDevice": "",
                "ipMethod": "",
            }
        ]
        leases = {"dc:46:28:2f:ae:f4": "192.168.50.18"}
        result = scanner._parse_clients(raw, leases, {})
        assert len(result) == 1
        assert result[0].ip == "192.168.50.18"

    def test_appareil_offline_ip_zero_fallback_reservation_statique(
        self, scanner: AsusRouterScanner
    ) -> None:
        """IP=0.0.0.0 et pas de bail → fallback reservation statique."""
        raw = [
            {
                "mac": "7c:4d:8f:4c:a4:66",
                "ip": "0.0.0.0",
                "isOnline": "0",
                "nickName": "print",
                "vendor": "HP",
                "dpiDevice": "",
                "ipMethod": "Manual",
            }
        ]
        reservations = {
            "7c:4d:8f:4c:a4:66": ("192.168.50.20", ""),
        }
        result = scanner._parse_clients(raw, {}, reservations)
        assert len(result) == 1
        assert result[0].ip == "192.168.50.20"

    def test_appareil_sans_ip_aucun_fallback_cree_avec_ip_vide(
        self, scanner: AsusRouterScanner
    ) -> None:
        """Appareil sans IP, sans bail, sans reservation : ip=''."""
        raw = [
            {
                "mac": "aa:bb:cc:dd:ee:ff",
                "ip": "0.0.0.0",
                "isOnline": "0",
                "nickName": "Inconnu",
                "vendor": "",
                "dpiDevice": "",
                "ipMethod": "",
            }
        ]
        result = scanner._parse_clients(raw, {}, {})
        assert len(result) == 1
        assert result[0].ip == ""
        assert result[0].hostname == "Inconnu"

    def test_mac_invalide_ignore(
        self, scanner: AsusRouterScanner
    ) -> None:
        """MAC de mauvaise longueur est ignoree."""
        raw = [
            {
                "mac": "invalid-mac",
                "ip": "192.168.50.99",
                "isOnline": "1",
                "nickName": "Test",
                "vendor": "",
                "dpiDevice": "",
                "ipMethod": "",
            }
        ]
        result = scanner._parse_clients(raw, {}, {})
        assert result == []

    def test_nickname_prioritaire_sur_name(
        self, scanner: AsusRouterScanner
    ) -> None:
        """nickName est utilise en priorite sur name."""
        raw = [
            {
                "mac": "48:b0:2d:03:1e:ea",
                "ip": "192.168.50.3",
                "isOnline": "1",
                "nickName": "Shield",
                "name": "android-device",
                "vendor": "NVIDIA",
                "dpiDevice": "",
                "ipMethod": "",
            }
        ]
        result = scanner._parse_clients(raw, {}, {})
        assert result[0].hostname == "Shield"

    def test_name_utilise_si_pas_de_nickname(
        self, scanner: AsusRouterScanner
    ) -> None:
        """name est utilise si nickName est absent."""
        raw = [
            {
                "mac": "48:b0:2d:03:1e:ea",
                "ip": "192.168.50.3",
                "isOnline": "1",
                "nickName": "",
                "name": "android-device",
                "vendor": "NVIDIA",
                "dpiDevice": "",
                "ipMethod": "",
            }
        ]
        result = scanner._parse_clients(raw, {}, {})
        assert result[0].hostname == "android-device"


# ---------------------------------------------------------------------------
# Tests : AsusRouterScanner.scan (integration)
# ---------------------------------------------------------------------------

class TestAsusRouterScannerScan:
    """Tests d'integration pour scan() avec appareils offline."""

    def test_scan_retourne_client_online(
        self,
        scanner: AsusRouterScanner,
        mock_client: MagicMock,
        network_config: NetworkConfig,
    ) -> None:
        """scan() retourne les appareils online depuis get_clientlist."""
        mock_client.get_clients.return_value = [
            {
                "mac": "48:b0:2d:03:1e:ea",
                "ip": "192.168.50.3",
                "isOnline": "1",
                "nickName": "Shield",
                "vendor": "NVIDIA",
                "dpiDevice": "AndroidTV",
                "ipMethod": "Manual",
            },
        ]
        mock_client.get_dhcp_leases.return_value = {}
        mock_client.get_nvram.return_value = {
            "dhcp_staticlist": "",
            "dhcp_hostnames": "",
            "custom_clientlist": (
                "<Shield>48:B0:2D:03:1E:EA>5>"
            ),
        }

        result = scanner.scan(network_config)

        assert len(result) == 1
        assert result[0].mac == "48:b0:2d:03:1e:ea"

    def test_scan_inclut_client_offline_via_custom_clientlist(
        self,
        scanner: AsusRouterScanner,
        mock_client: MagicMock,
        network_config: NetworkConfig,
    ) -> None:
        """Appareil offline dans custom_clientlist + bail DHCP est inclus."""
        mock_client.get_clients.return_value = [
            {
                "mac": "48:b0:2d:03:1e:ea",
                "ip": "192.168.50.3",
                "isOnline": "1",
                "nickName": "Shield",
                "vendor": "NVIDIA",
                "dpiDevice": "AndroidTV",
                "ipMethod": "Manual",
            },
        ]
        mock_client.get_dhcp_leases.return_value = {
            "58:16:d7:f1:77:6e": "192.168.50.7",
        }
        mock_client.get_nvram.return_value = {
            "dhcp_staticlist": "",
            "dhcp_hostnames": "",
            "custom_clientlist": (
                "<Shield>48:B0:2D:03:1E:EA>5>"
                "<Thermomix>58:16:D7:F1:77:6E>9>"
            ),
        }

        result = scanner.scan(network_config)

        assert len(result) == 2
        macs = {d.mac for d in result}
        assert "48:b0:2d:03:1e:ea" in macs
        assert "58:16:d7:f1:77:6e" in macs
        thermo = next(
            d for d in result if d.mac == "58:16:d7:f1:77:6e"
        )
        assert thermo.hostname == "Thermomix"
        assert thermo.ip == "192.168.50.7"

    def test_scan_offline_utilise_reservation_statique(
        self,
        scanner: AsusRouterScanner,
        mock_client: MagicMock,
        network_config: NetworkConfig,
    ) -> None:
        """Appareil offline sans bail DHCP utilise la reservation NVRAM."""
        mock_client.get_clients.return_value = []
        mock_client.get_dhcp_leases.return_value = {}
        mock_client.get_nvram.return_value = {
            "dhcp_staticlist": (
                "<7C:4D:8F:4C:A4:66>192.168.50.20"
            ),
            "dhcp_hostnames": "",
            "custom_clientlist": (
                "<print>7C:4D:8F:4C:A4:66>1>"
            ),
        }

        result = scanner.scan(network_config)

        assert len(result) == 1
        assert result[0].ip == "192.168.50.20"
        assert result[0].fixed_ip == "192.168.50.20"
        assert result[0].hostname == "print"

    def test_scan_appelle_login_sans_argument(
        self,
        scanner: AsusRouterScanner,
        mock_client: MagicMock,
        network_config: NetworkConfig,
    ) -> None:
        """scan() appelle login() sans argument.

        Les credentials sont passes au constructeur du client
        webapitools, pas a login().
        """
        mock_client.get_clients.return_value = []
        mock_client.get_dhcp_leases.return_value = {}
        mock_client.get_nvram.return_value = {
            "dhcp_staticlist": "",
            "dhcp_hostnames": "",
            "custom_clientlist": "",
        }

        scanner.scan(network_config)

        mock_client.login.assert_called_once_with()

    def test_scan_appelle_logout_meme_en_cas_erreur(
        self,
        scanner: AsusRouterScanner,
        mock_client: MagicMock,
        network_config: NetworkConfig,
    ) -> None:
        """logout() est appele meme si get_clients() leve une exception."""
        mock_client.get_clients.side_effect = RuntimeError(
            "Erreur reseau"
        )

        with pytest.raises(RuntimeError):
            scanner.scan(network_config)

        mock_client.logout.assert_called_once()


# ---------------------------------------------------------------------------
# Tests : RouterConfig validation
# ---------------------------------------------------------------------------

class TestRouterConfigValidation:
    """Tests pour la validation de RouterConfig."""

    def test_url_invalide_leve_value_error(self) -> None:
        """URL avec scheme invalide lève ValueError."""
        with pytest.raises(ValueError, match="Scheme"):
            RouterConfig(url="ftp://192.168.1.1", timeout=10)

    def test_timeout_negatif_leve_value_error(self) -> None:
        """Timeout <= 0 lève ValueError."""
        with pytest.raises(ValueError, match="Timeout invalide"):
            RouterConfig(url="http://192.168.1.1", timeout=0)

    def test_config_valide_acceptee(self) -> None:
        """Configuration valide est acceptée sans exception."""
        config = RouterConfig(
            url="https://192.168.50.1",
            timeout=15,
            username="admin",
            password="secret"
        )
        assert config.url == "https://192.168.50.1"
        assert config.timeout == 15

    def test_router_config_verify_tls_defaut_false(self) -> None:
        """verify_tls vaut False par defaut (certificat auto-signe)."""
        assert RouterConfig().verify_tls is False


# ---------------------------------------------------------------------------
# Tests : helpers ip
# ---------------------------------------------------------------------------

class TestIpHelpers:
    """Tests pour _ip_to_int, _int_to_ip, _next_available_ip."""

    def test_ip_to_int(self) -> None:
        """_ip_to_int() convertit correctement une IP."""
        assert _ip_to_int("192.168.50.1") == (
            (192 << 24) + (168 << 16) + (50 << 8) + 1
        )

    def test_int_to_ip(self) -> None:
        """_int_to_ip() convertit correctement un entier."""
        result = _int_to_ip((192 << 24) + (168 << 16) + (50 << 8) + 1)
        assert result == "192.168.50.1"

    def test_next_available_ip_premier_libre(self) -> None:
        """_next_available_ip() retourne la première IP libre."""
        dhcp_range = DhcpRange(start="192.168.50.100", end="192.168.50.110")
        used = {"192.168.50.100", "192.168.50.101"}
        ip = _next_available_ip(dhcp_range, used)
        assert ip == "192.168.50.102"

    def test_next_available_ip_plage_epuisee(self) -> None:
        """_next_available_ip() retourne None si plage épuisée."""
        dhcp_range = DhcpRange(start="192.168.50.100", end="192.168.50.102")
        used = {
            "192.168.50.100",
            "192.168.50.101",
            "192.168.50.102",
        }
        result = _next_available_ip(dhcp_range, used)
        assert result is None

    def test_infer_type_from_vendor(self) -> None:
        """_infer_type_from_vendor() infère le type depuis le fabricant."""
        assert _infer_type_from_vendor("NVIDIA Corporation") == "Media Player"
        assert _infer_type_from_vendor("Apple Inc") == "Apple"
        assert _infer_type_from_vendor("Unknown Corp") == "unknown"
        assert _infer_type_from_vendor("Raspberry Pi Foundation") == "Raspberry Pi"


# ---------------------------------------------------------------------------
# Tests : AsusRouterScanner avec logger
# ---------------------------------------------------------------------------

class TestAsusRouterScannerAvecLogger:
    """Tests pour AsusRouterScanner avec logger actif."""

    def test_scan_avec_logger_logge_decouverte(
        self,
        router_config: RouterConfig,
        network_config: NetworkConfig,
    ) -> None:
        """scan() logge le nombre de périphériques découverts."""
        logger = MagicMock()
        mock_client = MagicMock(spec=AsusRouterClient)
        mock_client.get_clients.return_value = [
            {
                "mac": "48:b0:2d:03:1e:ea",
                "ip": "192.168.50.3",
                "isOnline": "1",
                "nickName": "Shield",
                "vendor": "NVIDIA",
                "dpiDevice": "AndroidTV",
                "ipMethod": "Manual",
            }
        ]
        mock_client.get_dhcp_leases.return_value = {}
        mock_client.get_nvram.return_value = {
            "dhcp_staticlist": "",
            "dhcp_hostnames": "",
            "custom_clientlist": "<Shield>48:B0:2D:03:1E:EA>5>",
        }
        scanner = AsusRouterScanner(
            router_config, logger=logger, client=mock_client
        )
        result = scanner.scan(network_config)
        assert len(result) == 1
        logger.log_info.assert_called_once()


# ---------------------------------------------------------------------------
# Tests : AsusRouterDhcpManager
# ---------------------------------------------------------------------------

class TestAsusRouterDhcpManager:
    """Tests pour AsusRouterDhcpManager."""

    def _make_manager(
        self, router_config: RouterConfig, network_config: NetworkConfig
    ) -> tuple[AsusRouterDhcpManager, MagicMock, MagicMock]:
        """Crée un gestionnaire DHCP avec client mocké."""
        mock_client = MagicMock(spec=AsusRouterClient)
        logger = MagicMock()
        manager = AsusRouterDhcpManager(
            config=network_config,
            router_config=router_config,
            logger=logger,
            client=mock_client,
        )
        return manager, mock_client, logger

    def test_init_avec_client_injecte(
        self, router_config: RouterConfig, network_config: NetworkConfig
    ) -> None:
        """AsusRouterDhcpManager s'initialise avec un client injecté."""
        manager, mock_client, _ = self._make_manager(
            router_config, network_config
        )
        assert manager._client is mock_client

    def test_generate_reservations_alloue_ips(
        self, router_config: RouterConfig, network_config: NetworkConfig
    ) -> None:
        """generate_reservations() alloue des IP fixes depuis la plage DHCP."""
        manager, _, _ = self._make_manager(router_config, network_config)
        devices = [
            NetworkDevice(
                ip="192.168.50.3",
                mac="48:b0:2d:03:1e:ea",
                hostname="Shield",
            )
        ]
        result = manager.generate_reservations(devices)
        assert len(result) == 1
        assert result[0].fixed_ip is not None

    def test_generate_reservations_conserve_ip_fixe(
        self, router_config: RouterConfig, network_config: NetworkConfig
    ) -> None:
        """generate_reservations() conserve les IP déjà fixées."""
        manager, _, _ = self._make_manager(router_config, network_config)
        devices = [
            NetworkDevice(
                ip="192.168.50.10",
                mac="48:b0:2d:03:1e:ea",
                hostname="Shield",
                fixed_ip="192.168.50.10"
            )
        ]
        result = manager.generate_reservations(devices)
        assert result[0].fixed_ip == "192.168.50.10"

    def test_generate_reservations_sans_plage_dhcp(
        self, router_config: RouterConfig
    ) -> None:
        """generate_reservations() lève ValueError si pas de plage DHCP."""
        config_sans_dhcp = NetworkConfig(cidr="192.168.50.0/24")
        mock_client = MagicMock(spec=AsusRouterClient)
        manager = AsusRouterDhcpManager(
            config=config_sans_dhcp,
            router_config=router_config,
            client=mock_client,
        )
        with pytest.raises(ValueError, match="Plage DHCP non configuree"):
            manager.generate_reservations([])

    def test_export_reservations_format_nvram(
        self, router_config: RouterConfig, network_config: NetworkConfig
    ) -> None:
        """export_reservations() génère le format NVRAM ASUS."""
        manager, _, _ = self._make_manager(router_config, network_config)
        devices = [
            NetworkDevice(
                ip="192.168.50.10",
                mac="48:b0:2d:03:1e:ea",
                hostname="Shield",
                fixed_ip="192.168.50.10"
            )
        ]
        result = manager.export_reservations(devices)
        assert "48:B0:2D:03:1E:EA" in result
        assert "192.168.50.10" in result

    def test_export_reservations_ignore_sans_ip_fixe(
        self, router_config: RouterConfig, network_config: NetworkConfig
    ) -> None:
        """export_reservations() ignore les appareils sans fixed_ip."""
        manager, _, _ = self._make_manager(router_config, network_config)
        devices = [
            NetworkDevice(
                ip="192.168.50.3",
                mac="48:b0:2d:03:1e:ea",
                hostname="Shield",
            )
        ]
        result = manager.export_reservations(devices)
        assert result == ""

    def test_apply_reservations_appelle_login_logout(
        self, router_config: RouterConfig, network_config: NetworkConfig
    ) -> None:
        """apply_reservations() appelle login() (sans argument) et logout()."""
        manager, mock_client, logger = self._make_manager(
            router_config, network_config
        )
        mock_client.get_nvram.return_value = {
            "dhcp_enable_x": "1",
            "dhcp_start": "192.168.50.100",
            "dhcp_end": "192.168.50.254",
            "dhcp_lease": "86400",
            "dhcp_static_x": "1",
        }
        devices = [
            NetworkDevice(
                ip="192.168.50.10",
                mac="48:b0:2d:03:1e:ea",
                hostname="Shield",
                fixed_ip="192.168.50.10"
            )
        ]
        manager.apply_reservations(devices)
        mock_client.login.assert_called_once_with()
        mock_client.logout.assert_called_once()
        logger.log_info.assert_called_once()

    def test_read_reservations_retourne_liste(
        self, router_config: RouterConfig, network_config: NetworkConfig
    ) -> None:
        """read_reservations() retourne les réservations du routeur."""
        manager, mock_client, _ = self._make_manager(
            router_config, network_config
        )
        mock_client.get_nvram.return_value = {
            "dhcp_staticlist": "<48:B0:2D:03:1E:EA>192.168.50.10",
            "dhcp_hostnames": "",
        }
        result = manager.read_reservations()
        assert len(result) == 1
        assert result[0].fixed_ip == "192.168.50.10"
        mock_client.login.assert_called_once_with()
        mock_client.logout.assert_called_once()

    def test_read_reservations_decode_entites_html(
        self, router_config: RouterConfig, network_config: NetworkConfig
    ) -> None:
        """read_reservations() decode dhcp_staticlist encode HTML.

        Cas reel constate : le firmware encode < et > en
        &#60/&#62 sans point-virgule terminal, ce qui faisait
        remonter 0 reservation avant correctif (faux negatif).
        """
        manager, mock_client, _ = self._make_manager(
            router_config, network_config
        )
        mock_client.get_nvram.return_value = {
            "dhcp_staticlist": (
                "&#6028:73:F6:FE:30:3E&#62192.168.50.41"
                "&#60A8:CA:77:5E:EC:A0&#62192.168.50.42"
            ),
            "dhcp_hostnames": "",
        }
        result = manager.read_reservations()
        assert len(result) == 2
        fixed_ips = {device.fixed_ip for device in result}
        assert fixed_ips == {
            "192.168.50.41", "192.168.50.42"
        }
        mock_client.login.assert_called_once_with()
        mock_client.logout.assert_called_once()


class TestAsusRouterDhcpManagerEdgeCases:
    """Tests pour les cas limites d'AsusRouterDhcpManager."""

    def test_generate_reservations_plage_epuisee(
        self, router_config: RouterConfig, network_config: NetworkConfig
    ) -> None:
        """generate_reservations() leve ValueError si plage epuisee."""

        small_config = NetworkConfig(
            cidr="192.168.50.0/24",
            dhcp_range=DhcpRange(start="192.168.50.100", end="192.168.50.100"),
        )
        mgr = AsusRouterDhcpManager(small_config, router_config)
        devices = [
            NetworkDevice(ip="192.168.50.1", mac="aa:bb:cc:dd:ee:01"),
            NetworkDevice(ip="192.168.50.2", mac="aa:bb:cc:dd:ee:02"),
        ]
        with pytest.raises(ValueError, match="epuisee"):
            mgr.generate_reservations(devices)

    def test_build_nvram_strings_skip_sans_fixed_ip(
        self, router_config: RouterConfig, network_config: NetworkConfig
    ) -> None:
        """_build_nvram_strings() ignore les devices sans fixed_ip."""

        mgr = AsusRouterDhcpManager(network_config, router_config)
        devices = [
            NetworkDevice(ip="192.168.50.1", mac="aa:bb:cc:dd:ee:01"),
            NetworkDevice(ip="192.168.50.2", mac="aa:bb:cc:dd:ee:02", fixed_ip="192.168.50.2"),
        ]
        static_list, hostnames = mgr._build_nvram_strings(devices)
        assert "AA:BB:CC:DD:EE:01" not in static_list
        assert "AA:BB:CC:DD:EE:02" in static_list

    def test_parse_nvram_staticlist_value_error(
        self, router_config: RouterConfig, network_config: NetworkConfig
    ) -> None:
        """_parse_nvram_staticlist() ignore les entrees avec MAC invalide."""

        mgr = AsusRouterDhcpManager(network_config, router_config)
        with patch(
            "linuxtools.network.router.dhcp.NetworkDevice",
            side_effect=ValueError("bad mac")
        ):
            result = mgr._parse_nvram_staticlist(
                "<AA:BB:CC:DD:EE:01>192.168.50.1",
                ""
            )
        assert result == []


class TestSecuriteRouter:
    """Tests des corrections de securite dans router.py.

    Le transport HTTP (login/logout/get_nvram/set_mac_filter bas
    niveau) vit desormais cote webapitools : seuls les helpers
    restes dans linuxtools (RouterConfig, _validate_router_url,
    _ip_to_int) sont testes ici.
    """

    # --- _ip_to_int ---

    def test_ip_to_int_ip_valide(self) -> None:
        """_ip_to_int() convertit correctement une IP valide."""
        assert _ip_to_int("192.168.1.1") == 3232235777

    def test_ip_to_int_ip_invalide_leve_valueerror(self) -> None:
        """_ip_to_int() leve ValueError pour une IP hors plage."""
        with pytest.raises(ValueError, match="IPv4"):
            _ip_to_int("256.0.0.1")

    def test_ip_to_int_chaine_vide_leve_valueerror(self) -> None:
        """_ip_to_int() leve ValueError pour une chaine vide."""
        with pytest.raises(ValueError):
            _ip_to_int("")

    def test_ip_to_int_format_invalide_leve_valueerror(self) -> None:
        """_ip_to_int() leve ValueError pour un format non-IP."""
        with pytest.raises(ValueError):
            _ip_to_int("not.an.ip.addr")

    # --- RouterConfig URL ---

    def test_router_config_url_loopback_refusee(self) -> None:
        """RouterConfig rejette les adresses loopback."""
        with pytest.raises(ValueError):
            RouterConfig(url="http://127.0.0.1")

    def test_router_config_url_link_local_refusee(self) -> None:
        """RouterConfig rejette les adresses link-local (SSRF)."""
        with pytest.raises(ValueError):
            RouterConfig(url="http://169.254.169.254")

    def test_router_config_url_lan_acceptee(self) -> None:
        """RouterConfig accepte les adresses LAN privees."""
        cfg = RouterConfig(url="http://192.168.1.1")
        assert cfg.url == "http://192.168.1.1"

    def test_router_config_url_scheme_invalide(self) -> None:
        """RouterConfig rejette les schemes non http/https."""
        with pytest.raises(ValueError, match="Scheme"):
            RouterConfig(url="ftp://192.168.1.1")

    def test_router_config_url_hostname_dns_accepte(self) -> None:
        """RouterConfig accepte les noms de domaine."""
        cfg = RouterConfig(url="http://router.local")
        assert cfg.url == "http://router.local"

    # --- SSRF : résolution DNS ---

    def test_router_config_url_hostname_resolu_lan_accepte(
        self,
    ) -> None:
        """Hostname résolu en IP LAN → accepté."""
        with patch(
            "socket.getaddrinfo",
            return_value=[(None, None, None, None, ("192.168.1.1", 0))],
        ):
            cfg = RouterConfig(url="http://routeur.local")
        assert cfg.url == "http://routeur.local"

    def test_router_config_url_hostname_resolu_public_rejete(
        self,
    ) -> None:
        """Hostname résolu en IP publique → ValueError (SSRF)."""
        with patch(
            "socket.getaddrinfo",
            return_value=[(None, None, None, None, ("1.2.3.4", 0))],
        ):
            with pytest.raises(ValueError, match="non-LAN"):
                RouterConfig(url="http://evil.example.com")

    def test_router_config_url_hostname_non_resolvable_accepte(
        self,
    ) -> None:
        """Hostname non résolvable (gaierror) → accepté (mDNS)."""
        with patch(
            "socket.getaddrinfo",
            side_effect=socket.gaierror("no address"),
        ):
            cfg = RouterConfig(url="http://router.lan")
        assert cfg.url == "http://router.lan"


# ---------------------------------------------------------------------------
# Tests : AsusRouterMacFilterManager
# ---------------------------------------------------------------------------

class TestAsusRouterMacFilterManager:
    """Tests pour AsusRouterMacFilterManager."""

    def _make_manager(
        self, router_config: RouterConfig
    ) -> tuple[AsusRouterMacFilterManager, MagicMock, MagicMock]:
        """Cree un gestionnaire de filtre MAC avec client mocke."""
        mock_client = MagicMock(spec=AsusRouterClient)
        logger = MagicMock()
        manager = AsusRouterMacFilterManager(
            router_config=router_config,
            logger=logger,
            client=mock_client,
        )
        return manager, mock_client, logger

    def test_asus_router_mac_filter_manager_apply_appelle_login_logout(
        self, router_config: RouterConfig
    ) -> None:
        """apply_mac_filter() appelle login() (sans argument) puis logout()."""
        manager, mock_client, _ = self._make_manager(
            router_config
        )
        devices = [
            NetworkDevice(
                ip="192.168.50.3", mac="aa:bb:cc:dd:ee:ff"
            ),
        ]
        manager.apply_mac_filter(devices, "allow", [0])
        mock_client.login.assert_called_once_with()
        mock_client.logout.assert_called_once()

    def test_asus_router_mac_filter_manager_apply_extrait_macs_devices(
        self, router_config: RouterConfig
    ) -> None:
        """apply_mac_filter() extrait les MAC des devices fournis."""
        manager, mock_client, _ = self._make_manager(
            router_config
        )
        devices = [
            NetworkDevice(
                ip="192.168.50.3", mac="aa:bb:cc:dd:ee:ff"
            ),
            NetworkDevice(
                ip="192.168.50.4", mac="11:22:33:44:55:66"
            ),
        ]
        manager.apply_mac_filter(devices, "deny", [0, 1])
        mock_client.set_mac_filter.assert_called_once_with(
            "deny",
            ["aa:bb:cc:dd:ee:ff", "11:22:33:44:55:66"],
            [0, 1],
        )

    def test_asus_router_mac_filter_manager_read_retourne_liste_status(
        self, router_config: RouterConfig
    ) -> None:
        """read_mac_filter() retourne une liste de MacFilterStatus."""
        manager, mock_client, _ = self._make_manager(
            router_config
        )
        mock_client.get_nvram.return_value = {
            "wl0_macmode": "allow",
            "wl0_maclist_x": (
                "AA:BB:CC:DD:EE:FF 11:22:33:44:55:66"
            ),
        }
        result = manager.read_mac_filter([0])
        assert result == [
            MacFilterStatus(
                band=0,
                mode="allow",
                macs=(
                    "aa:bb:cc:dd:ee:ff",
                    "11:22:33:44:55:66",
                ),
            )
        ]

    def test_asus_router_mac_filter_manager_read_appelle_login_logout(
        self, router_config: RouterConfig
    ) -> None:
        """read_mac_filter() appelle login() (sans argument) puis logout()."""
        manager, mock_client, _ = self._make_manager(
            router_config
        )
        mock_client.get_nvram.return_value = {}
        manager.read_mac_filter([0, 1])
        mock_client.login.assert_called_once_with()
        mock_client.logout.assert_called_once()


# ---------------------------------------------------------------------------
# Tests : traduction AuthError (webapitools) -> RouterAuthError
#
# Point trouve en verification independante du temps 1 (webapitools) :
# webapitools.AsusRouterClient.login() leve AuthError, pas
# RouterAuthError, alors que ce dernier fait partie du contrat
# documente sur les ABC (network/base.py). Chaque adaptateur doit
# traduire l'exception a la frontiere.
# ---------------------------------------------------------------------------

class TestTraductionRouterAuthError:
    """Verifie la traduction AuthError -> RouterAuthError par adaptateur."""

    def test_scanner_traduit_autherror_en_routerautherror(
        self,
        scanner: AsusRouterScanner,
        mock_client: MagicMock,
        network_config: NetworkConfig,
    ) -> None:
        """AsusRouterScanner.scan() traduit AuthError en RouterAuthError."""
        mock_client.login.side_effect = AuthError(
            "Authentification refusee"
        )
        with pytest.raises(
            RouterAuthError, match="Authentification refusee"
        ):
            scanner.scan(network_config)

    def test_dhcp_manager_traduit_autherror_en_routerautherror(
        self, router_config: RouterConfig, network_config: NetworkConfig
    ) -> None:
        """AsusRouterDhcpManager.apply_reservations() traduit AuthError."""
        mock_client = MagicMock(spec=AsusRouterClient)
        mock_client.login.side_effect = AuthError(
            "Authentification refusee"
        )
        manager = AsusRouterDhcpManager(
            config=network_config,
            router_config=router_config,
            client=mock_client,
        )
        with pytest.raises(
            RouterAuthError, match="Authentification refusee"
        ):
            manager.apply_reservations([])

    def test_mac_filter_manager_traduit_autherror_en_routerautherror(
        self, router_config: RouterConfig
    ) -> None:
        """AsusRouterMacFilterManager.apply_mac_filter() traduit AuthError."""
        mock_client = MagicMock(spec=AsusRouterClient)
        mock_client.login.side_effect = AuthError(
            "Authentification refusee"
        )
        manager = AsusRouterMacFilterManager(
            router_config=router_config,
            client=mock_client,
        )
        with pytest.raises(
            RouterAuthError, match="Authentification refusee"
        ):
            manager.apply_mac_filter([], "allow", [0])


# ---------------------------------------------------------------------------
# Tests : non-regression Q-03 (re-export AsusRouterClient)
# ---------------------------------------------------------------------------

class TestReexportAsusRouterClient:
    """Verifie le contrat Q-03 : re-export d'AsusRouterClient.

    AsusRouterClient reste importable depuis
    linuxtools.network(.router) et pointe vers la classe webapitools
    (aucun changement pour les consommateurs existants, ex.
    scanNetHome, temps 3/3 du chantier cross-repo).
    """

    def test_import_depuis_network_router(self) -> None:
        """from linuxtools.network.router import AsusRouterClient."""
        import webapitools

        from linuxtools.network.router import (
            AsusRouterClient as AsusRouterClientDepuisRouter,
        )

        assert (
            AsusRouterClientDepuisRouter is webapitools.AsusRouterClient
        )

    def test_import_depuis_network(self) -> None:
        """from linuxtools.network import AsusRouterClient."""
        import webapitools

        from linuxtools.network import (
            AsusRouterClient as AsusRouterClientDepuisNetwork,
        )

        assert (
            AsusRouterClientDepuisNetwork is webapitools.AsusRouterClient
        )

    def test_les_deux_formes_importent_la_meme_classe(self) -> None:
        """Les deux chemins d'import retournent bien la meme classe."""
        from linuxtools.network import (
            AsusRouterClient as AsusRouterClientDepuisNetwork,
        )
        from linuxtools.network.router import (
            AsusRouterClient as AsusRouterClientDepuisRouter,
        )

        assert (
            AsusRouterClientDepuisNetwork is AsusRouterClientDepuisRouter
        )

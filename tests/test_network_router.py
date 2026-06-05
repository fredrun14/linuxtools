"""Tests pour le module router (AsusRouterClient et AsusRouterScanner).

Valide en particulier que les appareils offline (isOnline==0)
sont bien inclus dans les resultats du scan.
"""

from unittest.mock import MagicMock, patch

import pytest

from linux_python_utils.network.config import NetworkConfig, DhcpRange
from linux_python_utils.network.router import (
    AsusRouterClient,
    AsusRouterScanner,
    RouterConfig,
    _ip_to_int,
    _parse_custom_clientlist,
    _parse_nvram_reservations,
)


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
    """Client HTTP mocke."""
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
# Donnees de test
# ---------------------------------------------------------------------------

_CLIENTS_ONLINE_ONLY = {
    "48:b0:2d:03:1e:ea": {
        "ip": "192.168.50.3",
        "isOnline": "1",
        "nickName": "Shield",
        "vendor": "NVIDIA Corporation",
        "dpiDevice": "AndroidTV",
        "ipMethod": "Manual",
    },
}

_CLIENTS_MIXED = {
    "48:b0:2d:03:1e:ea": {
        "ip": "192.168.50.3",
        "isOnline": "1",
        "nickName": "Shield",
        "vendor": "NVIDIA Corporation",
        "dpiDevice": "AndroidTV",
        "ipMethod": "Manual",
    },
    "58:16:d7:f1:77:6e": {
        "ip": "192.168.50.7",
        "isOnline": "0",
        "nickName": "Thermomix",
        "vendor": "Vorwerk",
        "dpiDevice": "",
        "ipMethod": "Manual",
    },
    "e2:b7:be:2b:bd:2f": {
        "ip": "192.168.50.15",
        "isOnline": "0",
        "nickName": "NanouIphone",
        "vendor": "Apple",
        "dpiDevice": "iPhone",
        "ipMethod": "",
    },
}

_CLIENTS_OFFLINE_NO_IP = {
    "dc:46:28:2f:ae:f4": {
        "ip": "0.0.0.0",
        "isOnline": "0",
        "nickName": "Asustuf5G",
        "vendor": "ASUSTeK",
        "dpiDevice": "",
        "ipMethod": "Manual",
    },
}

_CLIENTS_OFFLINE_STATIC_ONLY = {
    "7c:4d:8f:4c:a4:66": {
        "ip": "0.0.0.0",
        "isOnline": "0",
        "nickName": "print",
        "vendor": "HP",
        "dpiDevice": "",
        "ipMethod": "Manual",
    },
}


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
        leases: dict = {}
        reservations: dict = {}
        result = scanner._merge_offline_clients(
            raw, custom, leases, reservations
        )
        assert len(result) == 1

    def test_client_offline_ajoute_si_bail_connu(
        self, scanner: AsusRouterScanner
    ) -> None:
        """Client offline avec bail DHCP actif est ajoute."""
        raw: list = []
        custom = {"58:16:d7:f1:77:6e": "Thermomix"}
        leases = {"58:16:d7:f1:77:6e": "192.168.50.7"}
        reservations: dict = {}
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
        raw: list = []
        custom = {"7c:4d:8f:4c:a4:66": "print"}
        leases: dict = {}
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
        raw: list = []
        custom = {"aa:bb:cc:dd:ee:ff": "Inconnu"}
        leases: dict = {}
        reservations: dict = {}
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
        reservations: dict = {}
        result = scanner._merge_offline_clients(
            raw, custom, leases, reservations
        )
        assert len(result) == 2


# ---------------------------------------------------------------------------
# Tests : AsusRouterClient.get_clients
# ---------------------------------------------------------------------------

class TestAsusRouterClientGetClients:
    """Tests pour get_clients() sans filtre isOnline."""

    def _make_client(
        self, router_config: RouterConfig, raw_data: dict
    ) -> AsusRouterClient:
        """Cree un client avec _hook mocke."""
        client = AsusRouterClient(router_config)
        client._token = "fake-token"
        client._hook = MagicMock(
            return_value={"get_clientlist": raw_data}
        )
        return client

    def test_retourne_appareils_online(
        self, router_config: RouterConfig
    ) -> None:
        """Les appareils isOnline==1 sont toujours retournes."""
        client = self._make_client(
            router_config, _CLIENTS_ONLINE_ONLY
        )
        result = client.get_clients()
        assert len(result) == 1
        assert result[0]["mac"] == "48:b0:2d:03:1e:ea"

    def test_retourne_appareils_offline(
        self, router_config: RouterConfig
    ) -> None:
        """Les appareils isOnline==0 sont desormais inclus."""
        client = self._make_client(
            router_config, _CLIENTS_MIXED
        )
        result = client.get_clients()
        macs = {r["mac"] for r in result}
        assert "58:16:d7:f1:77:6e" in macs
        assert "e2:b7:be:2b:bd:2f" in macs

    def test_retourne_online_et_offline(
        self, router_config: RouterConfig
    ) -> None:
        """Online et offline sont retournes ensemble."""
        client = self._make_client(
            router_config, _CLIENTS_MIXED
        )
        result = client.get_clients()
        assert len(result) == 3

    def test_exclut_mac_invalide(
        self, router_config: RouterConfig
    ) -> None:
        """Les entrees avec MAC de mauvaise longueur sont ignorees."""
        data = {
            "INVALID": {"ip": "1.2.3.4", "isOnline": "0"},
            **_CLIENTS_ONLINE_ONLY,
        }
        client = self._make_client(router_config, data)
        result = client.get_clients()
        assert all(
            len(r["mac"]) == 17 for r in result
        )

    def test_exclut_valeur_non_dict(
        self, router_config: RouterConfig
    ) -> None:
        """Les valeurs non-dict sont ignorees."""
        data = {
            "48:b0:2d:03:1e:ea": "not-a-dict",
            "58:16:d7:f1:77:6e": {
                "ip": "192.168.50.7",
                "isOnline": "0",
                "nickName": "Thermomix",
            },
        }
        client = self._make_client(router_config, data)
        result = client.get_clients()
        assert len(result) == 1

    def test_hook_retourne_non_dict_retourne_vide(
        self, router_config: RouterConfig
    ) -> None:
        """Si le hook retourne une valeur invalide, liste vide."""
        client = AsusRouterClient(router_config)
        client._token = "fake-token"
        client._hook = MagicMock(
            return_value={"get_clientlist": "invalid"}
        )
        result = client.get_clients()
        assert result == []


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

    def test_scan_utilise_credentials_du_routerconfig(
        self,
        scanner: AsusRouterScanner,
        mock_client: MagicMock,
        network_config: NetworkConfig,
    ) -> None:
        """scan() utilise directement les credentials de RouterConfig."""
        mock_client.get_clients.return_value = []
        mock_client.get_dhcp_leases.return_value = {}
        mock_client.get_nvram.return_value = {
            "dhcp_staticlist": "",
            "dhcp_hostnames": "",
            "custom_clientlist": "",
        }

        scanner.scan(network_config)

        mock_client.login.assert_called_once_with(
            "admin", "secret"
        )

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
        from linux_python_utils.network.router import RouterConfig, RouterAuthError
        with pytest.raises(ValueError, match="Scheme"):
            RouterConfig(url="ftp://192.168.1.1", timeout=10)

    def test_timeout_negatif_leve_value_error(self) -> None:
        """Timeout <= 0 lève ValueError."""
        from linux_python_utils.network.router import RouterConfig
        with pytest.raises(ValueError, match="Timeout invalide"):
            RouterConfig(url="http://192.168.1.1", timeout=0)

    def test_config_valide_acceptee(self) -> None:
        """Configuration valide est acceptée sans exception."""
        from linux_python_utils.network.router import RouterConfig
        config = RouterConfig(
            url="https://192.168.50.1",
            timeout=15,
            username="admin",
            password="secret"
        )
        assert config.url == "https://192.168.50.1"
        assert config.timeout == 15


# ---------------------------------------------------------------------------
# Tests : helpers ip
# ---------------------------------------------------------------------------

class TestIpHelpers:
    """Tests pour _ip_to_int, _int_to_ip, _next_available_ip."""

    def test_ip_to_int(self) -> None:
        """_ip_to_int() convertit correctement une IP."""
        from linux_python_utils.network.router import _ip_to_int
        assert _ip_to_int("192.168.50.1") == (
            (192 << 24) + (168 << 16) + (50 << 8) + 1
        )

    def test_int_to_ip(self) -> None:
        """_int_to_ip() convertit correctement un entier."""
        from linux_python_utils.network.router import _int_to_ip
        result = _int_to_ip((192 << 24) + (168 << 16) + (50 << 8) + 1)
        assert result == "192.168.50.1"

    def test_next_available_ip_premier_libre(self) -> None:
        """_next_available_ip() retourne la première IP libre."""
        from linux_python_utils.network.router import _next_available_ip
        from linux_python_utils.network.config import DhcpRange
        dhcp_range = DhcpRange(start="192.168.50.100", end="192.168.50.110")
        used = {"192.168.50.100", "192.168.50.101"}
        ip = _next_available_ip(dhcp_range, used)
        assert ip == "192.168.50.102"

    def test_next_available_ip_plage_epuisee(self) -> None:
        """_next_available_ip() retourne None si plage épuisée."""
        from linux_python_utils.network.router import _next_available_ip
        from linux_python_utils.network.config import DhcpRange
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
        from linux_python_utils.network.router import _infer_type_from_vendor
        assert _infer_type_from_vendor("NVIDIA Corporation") == "Media Player"
        assert _infer_type_from_vendor("Apple Inc") == "Apple"
        assert _infer_type_from_vendor("Unknown Corp") == "unknown"
        assert _infer_type_from_vendor("Raspberry Pi Foundation") == "Raspberry Pi"


# ---------------------------------------------------------------------------
# Tests : AsusRouterClient - login / logout / _require_token
# ---------------------------------------------------------------------------

class TestAsusRouterClientMocked:
    """Tests pour AsusRouterClient avec urllib mocké."""

    def _make_client(self, router_config):
        """Crée un client avec logger mocké."""
        from linux_python_utils.network.router import AsusRouterClient
        logger = MagicMock()
        return AsusRouterClient(router_config, logger=logger), logger

    def test_require_token_sans_token_leve_erreur(
        self, router_config: RouterConfig
    ) -> None:
        """_require_token() lève RouterAuthError si non authentifié."""
        from linux_python_utils.network.router import (
            AsusRouterClient, RouterAuthError
        )
        client = AsusRouterClient(router_config)
        with pytest.raises(RouterAuthError, match="login"):
            client._require_token()

    def test_login_succes(self, router_config: RouterConfig) -> None:
        """login() définit le token en cas de succès."""
        from unittest.mock import patch, MagicMock
        import json
        from linux_python_utils.network.router import AsusRouterClient
        client, logger = self._make_client(router_config)

        mock_resp = MagicMock()
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_resp.read.return_value = json.dumps(
            {"asus_token": "tok123"}
        ).encode("utf-8")

        with patch("urllib.request.urlopen", return_value=mock_resp):
            client.login("admin", "secret")

        assert client._token == "tok123"
        logger.log_info.assert_called_once()

    def test_login_echec_connexion(self, router_config: RouterConfig) -> None:
        """login() lève RouterAuthError en cas d'erreur réseau."""
        from unittest.mock import patch
        from linux_python_utils.network.router import (
            AsusRouterClient, RouterAuthError
        )
        client, _ = self._make_client(router_config)
        with patch(
            "urllib.request.urlopen",
            side_effect=Exception("Connexion refusée")
        ):
            with pytest.raises(RouterAuthError, match="Connexion echouee"):
                client.login("admin", "secret")

    def test_login_token_absent_leve_erreur(
        self, router_config: RouterConfig
    ) -> None:
        """login() lève RouterAuthError si token absent de la réponse."""
        from unittest.mock import patch, MagicMock
        import json
        from linux_python_utils.network.router import (
            AsusRouterClient, RouterAuthError
        )
        client, _ = self._make_client(router_config)
        mock_resp = MagicMock()
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_resp.read.return_value = json.dumps({}).encode("utf-8")
        with patch("urllib.request.urlopen", return_value=mock_resp):
            with pytest.raises(RouterAuthError, match="Token absent"):
                client.login("admin", "secret")

    def test_logout_sans_token_ne_fait_rien(
        self, router_config: RouterConfig
    ) -> None:
        """logout() ne fait rien si non authentifié."""
        from linux_python_utils.network.router import AsusRouterClient
        client = AsusRouterClient(router_config)
        client.logout()  # Ne doit pas lever d'exception

    def test_logout_avec_token(self, router_config: RouterConfig) -> None:
        """logout() efface le token après déconnexion."""
        from unittest.mock import patch, MagicMock
        from linux_python_utils.network.router import AsusRouterClient
        client = AsusRouterClient(router_config)
        client._token = "tok123"
        mock_resp = MagicMock()
        with patch("urllib.request.urlopen", return_value=mock_resp):
            client.logout()
        assert client._token is None

    def test_logout_ignore_exception_reseau(
        self, router_config: RouterConfig
    ) -> None:
        """logout() ignore les erreurs réseau."""
        from unittest.mock import patch
        from linux_python_utils.network.router import AsusRouterClient
        client = AsusRouterClient(router_config)
        client._token = "tok123"
        with patch(
            "urllib.request.urlopen",
            side_effect=Exception("timeout")
        ):
            client.logout()  # Ne doit pas lever d'exception
        assert client._token is None

    def test_get_dhcp_leases_parse_format_dnsmasq(
        self, router_config: RouterConfig
    ) -> None:
        """get_dhcp_leases() parse le format dnsmasq correctement."""
        from linux_python_utils.network.router import AsusRouterClient
        client = AsusRouterClient(router_config)
        client._token = "fake-token"
        leases_str = (
            "1234567890 48:b0:2d:03:1e:ea 192.168.50.3 Shield *\n"
            "1234567891 58:16:d7:f1:77:6e 192.168.50.7 Thermomix *\n"
        )
        client._hook = MagicMock(
            return_value={"dhcpLeaseMacList": leases_str}
        )
        result = client.get_dhcp_leases()
        assert result["48:b0:2d:03:1e:ea"] == "192.168.50.3"
        assert result["58:16:d7:f1:77:6e"] == "192.168.50.7"

    def test_get_dhcp_leases_ignore_ip_etoile(
        self, router_config: RouterConfig
    ) -> None:
        """get_dhcp_leases() ignore les lignes avec ip='*'."""
        from linux_python_utils.network.router import AsusRouterClient
        client = AsusRouterClient(router_config)
        client._token = "fake-token"
        leases_str = "123 48:b0:2d:03:1e:ea * Shield *\n"
        client._hook = MagicMock(
            return_value={"dhcpLeaseMacList": leases_str}
        )
        result = client.get_dhcp_leases()
        assert result == {}

    def test_get_nvram_retourne_dict(
        self, router_config: RouterConfig
    ) -> None:
        """get_nvram() retourne le dictionnaire de variables NVRAM."""
        from linux_python_utils.network.router import AsusRouterClient
        client = AsusRouterClient(router_config)
        client._token = "fake-token"
        client._hook = MagicMock(
            return_value={
                "dhcp_staticlist": "<AA:BB:CC:DD:EE:FF>192.168.50.10",
                "dhcp_hostnames": ""
            }
        )
        result = client.get_nvram("dhcp_staticlist", "dhcp_hostnames")
        assert "dhcp_staticlist" in result


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

    def _make_manager(self, router_config, network_config):
        """Crée un gestionnaire DHCP avec client mocké."""
        from linux_python_utils.network.router import AsusRouterDhcpManager
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
        from linux_python_utils.network.models import NetworkDevice
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
        from linux_python_utils.network.models import NetworkDevice
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
        from linux_python_utils.network.config import NetworkConfig
        from linux_python_utils.network.router import AsusRouterDhcpManager
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
        from linux_python_utils.network.models import NetworkDevice
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
        from linux_python_utils.network.models import NetworkDevice
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
        """apply_reservations() appelle login et logout."""
        from linux_python_utils.network.models import NetworkDevice
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
        mock_client.login.assert_called_once()
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
        mock_client.login.assert_called_once()
        mock_client.logout.assert_called_once()


class TestAsusRouterClientHook:
    """Tests pour AsusRouterClient._hook() avec urllib mocke."""

    def test_hook_succes_retourne_json(
        self, router_config: RouterConfig
    ) -> None:
        """_hook() retourne le JSON parse depuis la reponse."""
        import json
        from unittest.mock import patch, MagicMock
        client = AsusRouterClient(router_config)
        client._token = "fake-token"

        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(
            {"get_clientlist": {}}
        ).encode("utf-8")
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch(
            "linux_python_utils.network.router.urllib.request.urlopen",
            return_value=mock_resp
        ):
            result = client._hook("get_clientlist(appobj)")
        assert "get_clientlist" in result

    def test_hook_erreur_leve_runtime_error(
        self, router_config: RouterConfig
    ) -> None:
        """_hook() leve RuntimeError en cas d'erreur urllib."""
        from unittest.mock import patch
        client = AsusRouterClient(router_config)
        client._token = "fake-token"

        with patch(
            "linux_python_utils.network.router.urllib.request.urlopen",
            side_effect=Exception("network error")
        ):
            with pytest.raises(RuntimeError, match="hook"):
                client._hook("get_clientlist(appobj)")

    def test_require_token_retourne_token(
        self, router_config: RouterConfig
    ) -> None:
        """_require_token() retourne le token si present."""
        client = AsusRouterClient(router_config)
        client._token = "my-token"
        token = client._require_token()
        assert token == "my-token"


class TestAsusRouterDhcpManagerEdgeCases:
    """Tests pour les cas limites d'AsusRouterDhcpManager."""

    def test_generate_reservations_plage_epuisee(
        self, router_config: RouterConfig, network_config: NetworkConfig
    ) -> None:
        """generate_reservations() leve ValueError si plage epuisee."""
        from linux_python_utils.network.router import AsusRouterDhcpManager
        from linux_python_utils.network.config import DhcpRange
        from linux_python_utils.network.models import NetworkDevice

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
        from linux_python_utils.network.router import AsusRouterDhcpManager
        from linux_python_utils.network.models import NetworkDevice

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
        from linux_python_utils.network.router import AsusRouterDhcpManager
        from unittest.mock import patch

        mgr = AsusRouterDhcpManager(network_config, router_config)
        with patch(
            "linux_python_utils.network.router.NetworkDevice",
            side_effect=ValueError("bad mac")
        ):
            result = mgr._parse_nvram_staticlist(
                "<AA:BB:CC:DD:EE:01>192.168.50.1",
                ""
            )
        assert result == []


class TestSecuriteRouter:
    """Tests des corrections de securite dans router.py."""

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

    # --- get_nvram ---

    def test_get_nvram_cle_valide(
        self, router_config: RouterConfig
    ) -> None:
        """get_nvram() accepte une cle NVRAM valide."""
        from unittest.mock import patch
        client = AsusRouterClient(router_config)
        client._token = "tok"
        with patch.object(
            client, "_hook", return_value={}
        ) as mock:
            client.get_nvram("dhcp_start")
            mock.assert_called_once_with(
                "nvram_get(dhcp_start)"
            )

    def test_get_nvram_cle_invalide_leve_valueerror(
        self, router_config: RouterConfig
    ) -> None:
        """get_nvram() leve ValueError pour une cle NVRAM invalide."""
        client = AsusRouterClient(router_config)
        client._token = "tok"
        with pytest.raises(ValueError, match="NVRAM"):
            client.get_nvram("dhcp_start);evil(")

    def test_get_nvram_cle_avec_point_invalide(
        self, router_config: RouterConfig
    ) -> None:
        """get_nvram() refuse les cles avec des points."""
        client = AsusRouterClient(router_config)
        client._token = "tok"
        with pytest.raises(ValueError, match="NVRAM"):
            client.get_nvram("cle.invalide")

    # --- login ---

    def test_login_username_avec_colon_leve_valueerror(
        self, router_config: RouterConfig
    ) -> None:
        """login() leve ValueError si username contient ':'."""
        client = AsusRouterClient(router_config)
        with pytest.raises(ValueError, match=":"):
            client.login("admin:evil", "password")

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

    def test_login_echec_logue_erreur(
        self, router_config: RouterConfig
    ) -> None:
        """login() log l'erreur via logger si connexion echoue."""
        from unittest.mock import MagicMock, patch
        from linux_python_utils.network.router import (
            RouterAuthError,
        )
        logger = MagicMock()
        client = AsusRouterClient(router_config, logger=logger)
        with patch(
            "urllib.request.urlopen",
            side_effect=OSError("connexion refusee"),
        ):
            with pytest.raises(RouterAuthError):
                client.login("admin", "password")
        logger.log_error.assert_called_once()

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
        import socket
        with patch(
            "socket.getaddrinfo",
            side_effect=socket.gaierror("no address"),
        ):
            cfg = RouterConfig(url="http://router.lan")
        assert cfg.url == "http://router.lan"

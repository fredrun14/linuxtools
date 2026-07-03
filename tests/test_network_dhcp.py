"""Tests pour la gestion DHCP."""

import pytest

from linuxtools.network.config import (
    DhcpRange,
    NetworkConfig,
)
from linuxtools.network.dhcp import (
    LinuxDhcpReservationManager,
)
from linuxtools.network.ip_utils import (
    _int_to_ip,
    _ip_to_int,
)
from linuxtools.network.models import NetworkDevice


def _config(
    start: str = "192.168.1.100",
    end: str = "192.168.1.254",
) -> NetworkConfig:
    """Cree une config avec plage DHCP."""
    return NetworkConfig(
        cidr="192.168.1.0/24",
        dhcp_range=DhcpRange(start=start, end=end),
    )


def _device(
    ip: str = "192.168.1.1",
    mac: str = "aa:bb:cc:dd:ee:ff",
    **kwargs,
) -> NetworkDevice:
    """Cree un NetworkDevice pour les tests."""
    return NetworkDevice(ip=ip, mac=mac, **kwargs)


class TestLinuxDhcpReservationManager:
    """Tests pour LinuxDhcpReservationManager."""

    def test_assigner_ip_depuis_plage(self) -> None:
        """Device sans fixed_ip recoit une IP."""
        mgr = LinuxDhcpReservationManager(_config())
        devices = [_device()]
        result = mgr.generate_reservations(devices)
        assert result[0].fixed_ip == "192.168.1.100"

    def test_garder_ip_existante(self) -> None:
        """Device avec fixed_ip garde son IP."""
        mgr = LinuxDhcpReservationManager(_config())
        devices = [
            _device(fixed_ip="192.168.1.50")
        ]
        result = mgr.generate_reservations(devices)
        assert result[0].fixed_ip == "192.168.1.50"

    def test_plusieurs_devices(self) -> None:
        """IPs incrementales pour plusieurs devices."""
        mgr = LinuxDhcpReservationManager(_config())
        devices = [
            _device("192.168.1.1", "aa:bb:cc:dd:ee:01"),
            _device("192.168.1.2", "aa:bb:cc:dd:ee:02"),
            _device("192.168.1.3", "aa:bb:cc:dd:ee:03"),
        ]
        result = mgr.generate_reservations(devices)
        assert result[0].fixed_ip == "192.168.1.100"
        assert result[1].fixed_ip == "192.168.1.101"
        assert result[2].fixed_ip == "192.168.1.102"

    def test_plage_epuisee(self) -> None:
        """Plage trop petite leve ValueError."""
        mgr = LinuxDhcpReservationManager(
            _config(
                start="192.168.1.100",
                end="192.168.1.100",
            )
        )
        devices = [
            _device("192.168.1.1", "aa:bb:cc:dd:ee:01"),
            _device("192.168.1.2", "aa:bb:cc:dd:ee:02"),
        ]
        with pytest.raises(ValueError, match="epuisee"):
            mgr.generate_reservations(devices)

    def test_config_sans_dhcp_range(self) -> None:
        """Config sans plage DHCP leve ValueError."""
        config = NetworkConfig(cidr="192.168.1.0/24")
        mgr = LinuxDhcpReservationManager(config)
        with pytest.raises(ValueError, match="configuree"):
            mgr.generate_reservations([_device()])

    def test_export_format_dnsmasq(self) -> None:
        """Format dnsmasq correct."""
        mgr = LinuxDhcpReservationManager(_config())
        devices = [
            _device(
                fixed_ip="192.168.1.100",
                hostname="nas",
            )
        ]
        output = mgr.export_reservations(devices)
        assert "dhcp-host=aa:bb:cc:dd:ee:ff" in output
        assert "192.168.1.100" in output
        assert ",nas" in output

    def test_export_sans_hostname(self) -> None:
        """Export sans hostname n'a pas de 3e champ."""
        mgr = LinuxDhcpReservationManager(_config())
        devices = [
            _device(fixed_ip="192.168.1.100")
        ]
        output = mgr.export_reservations(devices)
        line = [
            l for l in output.split("\n")
            if "dhcp-host" in l
        ][0]
        assert line.count(",") == 1

    def test_export_liste_vide(self) -> None:
        """Liste vide retourne en-tete uniquement."""
        mgr = LinuxDhcpReservationManager(_config())
        output = mgr.export_reservations([])
        assert "Reservations DHCP" in output
        assert "dhcp-host" not in output

    def test_ip_to_int(self) -> None:
        """Conversion IP vers entier."""
        result = _ip_to_int("192.168.1.100")
        assert result == 3232235876

    def test_int_to_ip(self) -> None:
        """Conversion entier vers IP."""
        result = _int_to_ip(3232235876)
        assert result == "192.168.1.100"

    def test_ip_to_int_roundtrip(self) -> None:
        """Roundtrip ip_to_int puis int_to_ip."""
        ip = "192.168.1.100"
        result = _int_to_ip(_ip_to_int(ip))
        assert result == ip

    def test_eviter_collision_ip(self) -> None:
        """IP deja utilisee est sautee."""
        mgr = LinuxDhcpReservationManager(_config())
        devices = [
            _device(
                "192.168.1.1",
                "aa:bb:cc:dd:ee:01",
                fixed_ip="192.168.1.100",
            ),
            _device("192.168.1.2", "aa:bb:cc:dd:ee:02"),
        ]
        result = mgr.generate_reservations(devices)
        assert result[1].fixed_ip == "192.168.1.101"


class TestLinuxDhcpReservationManagerAvecLogger:
    """Tests avec logger pour LinuxDhcpReservationManager."""

    def test_generate_reservations_avec_logger(self) -> None:
        """generate_reservations() appelle logger.log_info si logger present."""
        from unittest.mock import MagicMock
        logger = MagicMock()
        mgr = LinuxDhcpReservationManager(_config(), logger=logger)
        devices = [_device()]
        mgr.generate_reservations(devices)
        logger.log_info.assert_called_once()

    def test_export_reservations_skip_sans_fixed_ip(self) -> None:
        """export_reservations() ignore les devices sans fixed_ip."""
        mgr = LinuxDhcpReservationManager(_config())
        devices = [
            _device(),                           # sans fixed_ip
            _device("192.168.1.2", "bb:cc:dd:ee:ff:00", fixed_ip="192.168.1.2"),
        ]
        output = mgr.export_reservations(devices)
        assert "dhcp-host=aa:bb:cc:dd:ee:ff" not in output
        assert "dhcp-host=bb:cc:dd:ee:ff:00" in output


class TestIpToIntValidation:
    """Tests de validation IPv4 dans _ip_to_int."""

    def test_ip_to_int_valide(self) -> None:
        """_ip_to_int() retourne l'entier correct pour une IP valide."""
        assert _ip_to_int("192.168.1.1") == 3232235777

    def test_ip_to_int_invalide_leve_valueerror(self) -> None:
        """_ip_to_int() leve ValueError pour une IP invalide."""
        import pytest
        with pytest.raises(ValueError, match="IPv4"):
            _ip_to_int("256.0.0.1")

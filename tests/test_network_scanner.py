"""Tests pour les scanners reseau."""

from unittest.mock import MagicMock, patch

import pytest

from linux_python_utils.commands.base import (
    CommandExecutor,
    CommandResult,
)
from linux_python_utils.network.config import NetworkConfig
from linux_python_utils.network.scanner import (
    LinuxArpScanner,
    LinuxNmapScanner,
)

ARP_OUTPUT = (
    "Interface: eth0, type: EN10MB, "
    "MAC: 00:11:22:33:44:55\n"
    "192.168.1.1\t00:11:22:33:44:55\tASUSTek COMPUTER\n"
    "192.168.1.100\taa:bb:cc:dd:ee:ff\tApple, Inc.\n"
    "\n"
    "2 packets received by filter, "
    "0 packets dropped by kernel\n"
    "Ending arp-scan: 256 hosts scanned. "
    "2 responded.\n"
)

NMAP_XML = """\
<?xml version="1.0"?>
<nmaprun>
  <host>
    <status state="up"/>
    <address addr="192.168.1.1" addrtype="ipv4"/>
    <address addr="00:11:22:33:44:55" addrtype="mac" \
vendor="ASUSTek"/>
    <hostnames><hostname name="router"/></hostnames>
  </host>
  <host>
    <status state="up"/>
    <address addr="192.168.1.100" addrtype="ipv4"/>
    <address addr="aa:bb:cc:dd:ee:ff" addrtype="mac" \
vendor="Apple"/>
    <hostnames/>
  </host>
  <host>
    <status state="up"/>
    <address addr="192.168.1.50" addrtype="ipv4"/>
  </host>
  <host>
    <status state="down"/>
    <address addr="192.168.1.200" addrtype="ipv4"/>
    <address addr="bb:cc:dd:ee:ff:00" addrtype="mac"/>
  </host>
</nmaprun>"""


def _make_result(
    stdout: str = "",
    success: bool = True,
    stderr: str = "",
) -> CommandResult:
    """Cree un CommandResult pour les tests."""
    return CommandResult(
        command=["test"],
        return_code=0 if success else 1,
        stdout=stdout,
        stderr=stderr,
        success=success,
        duration=0.5,
    )


class TestLinuxArpScanner:
    """Tests pour LinuxArpScanner."""

    def _make_scanner(
        self,
    ) -> tuple[LinuxArpScanner, MagicMock]:
        """Cree un scanner avec executor mocke."""
        executor = MagicMock(spec=CommandExecutor)
        scanner = LinuxArpScanner(executor=executor)
        return scanner, executor

    def test_build_command_avec_interface(self) -> None:
        """Commande avec option --interface."""
        scanner, _ = self._make_scanner()
        config = NetworkConfig(
            cidr="192.168.1.0/24", interface="eth0"
        )
        cmd = scanner._build_command(config)
        assert "sudo" in cmd
        assert "arp-scan" in cmd
        assert "--interface" in cmd
        assert "eth0" in cmd
        assert "192.168.1.0/24" in cmd

    def test_build_command_sans_interface(self) -> None:
        """Commande sans option --interface quand aucune interface disponible."""
        scanner, _ = self._make_scanner()
        config = NetworkConfig(cidr="192.168.1.0/24")
        with patch(
            "linux_python_utils.network.scanner._detect_interface",
            return_value="",
        ):
            cmd = scanner._build_command(config)
        assert "--interface" not in cmd

    def test_parse_output_deux_devices(self) -> None:
        """Parse 2 peripheriques depuis la sortie arp-scan."""
        scanner, _ = self._make_scanner()
        devices = scanner._parse_output(ARP_OUTPUT)
        assert len(devices) == 2
        assert devices[0].ip == "192.168.1.1"
        assert devices[0].mac == "00:11:22:33:44:55"
        assert devices[1].ip == "192.168.1.100"
        assert devices[1].mac == "aa:bb:cc:dd:ee:ff"

    def test_parse_output_vide(self) -> None:
        """Sortie sans peripheriques retourne liste vide."""
        scanner, _ = self._make_scanner()
        output = (
            "Interface: eth0\n\n"
            "0 packets received\n"
            "Ending arp-scan\n"
        )
        devices = scanner._parse_output(output)
        assert devices == []

    def test_scan_echec_commande(self) -> None:
        """Echec de commande leve RuntimeError."""
        scanner, executor = self._make_scanner()
        executor.run.return_value = _make_result(
            success=False, stderr="permission denied"
        )
        config = NetworkConfig(cidr="192.168.1.0/24")
        with pytest.raises(RuntimeError):
            scanner.scan(config)

    def test_scan_appelle_executor(self) -> None:
        """Verifie que executor.run est appele."""
        scanner, executor = self._make_scanner()
        executor.run.return_value = _make_result(
            stdout=ARP_OUTPUT
        )
        config = NetworkConfig(cidr="192.168.1.0/24")
        scanner.scan(config)
        executor.run.assert_called_once()

    def test_vendor_extrait(self) -> None:
        """Vendor correctement capture."""
        scanner, _ = self._make_scanner()
        devices = scanner._parse_output(ARP_OUTPUT)
        assert devices[0].vendor == "ASUSTek COMPUTER"
        assert devices[1].vendor == "Apple, Inc."


class TestLinuxNmapScanner:
    """Tests pour LinuxNmapScanner."""

    def _make_scanner(
        self,
    ) -> tuple[LinuxNmapScanner, MagicMock]:
        """Cree un scanner nmap avec executor mocke."""
        executor = MagicMock(spec=CommandExecutor)
        scanner = LinuxNmapScanner(executor=executor)
        return scanner, executor

    def test_build_command(self) -> None:
        """Commande nmap correcte."""
        scanner, _ = self._make_scanner()
        config = NetworkConfig(cidr="192.168.1.0/24")
        cmd = scanner._build_command(config)
        assert "sudo" in cmd
        assert "nmap" in cmd
        assert "-sn" in cmd
        assert "-oX" in cmd
        assert "-" in cmd
        assert "192.168.1.0/24" in cmd

    def test_parse_xml_deux_hosts(self) -> None:
        """Parse 2 hosts up avec MAC."""
        scanner, _ = self._make_scanner()
        devices = scanner._parse_xml_output(NMAP_XML)
        assert len(devices) == 2
        assert devices[0].ip == "192.168.1.1"
        assert devices[0].mac == "00:11:22:33:44:55"
        assert devices[0].vendor == "ASUSTek"
        assert devices[0].hostname == "router"

    def test_parse_xml_ignore_host_sans_mac(self) -> None:
        """Host sans MAC (local) est ignore."""
        scanner, _ = self._make_scanner()
        devices = scanner._parse_xml_output(NMAP_XML)
        ips = [d.ip for d in devices]
        assert "192.168.1.50" not in ips

    def test_parse_xml_host_down(self) -> None:
        """Host avec status down est ignore."""
        scanner, _ = self._make_scanner()
        devices = scanner._parse_xml_output(NMAP_XML)
        ips = [d.ip for d in devices]
        assert "192.168.1.200" not in ips

    def test_parse_xml_sans_hostname(self) -> None:
        """Host sans hostname a un hostname vide."""
        scanner, _ = self._make_scanner()
        devices = scanner._parse_xml_output(NMAP_XML)
        apple = [
            d for d in devices if d.ip == "192.168.1.100"
        ][0]
        assert apple.hostname == ""

    def test_scan_echec_commande(self) -> None:
        """Echec de commande leve RuntimeError."""
        scanner, executor = self._make_scanner()
        executor.run.return_value = _make_result(
            success=False, stderr="error"
        )
        config = NetworkConfig(cidr="192.168.1.0/24")
        with pytest.raises(RuntimeError):
            scanner.scan(config)



class TestDetectInterface:
    """Tests pour _detect_interface()."""

    def test_no_sys_net_returns_empty(self) -> None:
        """Retourne "" si /sys/class/net n'existe pas."""
        from unittest.mock import patch
        from linux_python_utils.network.scanner import _detect_interface
        with patch("linux_python_utils.network.scanner.Path") as mock_path:
            mock_net = mock_path.return_value
            mock_net.exists.return_value = False
            result = _detect_interface()
        assert result == ""

    def test_oserror_reading_operstate(self, tmp_path) -> None:
        """Ignore les interfaces dont operstate leve OSError."""
        from unittest.mock import patch, MagicMock
        from linux_python_utils.network.scanner import _detect_interface

        mock_iface = MagicMock()
        mock_iface.name = "eth99"
        op_file = MagicMock()
        op_file.read_text.side_effect = OSError("no access")
        mock_iface.__truediv__ = lambda self, x: op_file

        with patch("linux_python_utils.network.scanner.Path") as mock_path:
            mock_net = mock_path.return_value
            mock_net.exists.return_value = True
            mock_net.iterdir.return_value = [mock_iface]
            result = _detect_interface()
        assert result == ""

    def test_state_not_up_ignored(self, tmp_path) -> None:
        """Ignore les interfaces dont l'etat n'est pas 'up'."""
        from unittest.mock import patch, MagicMock
        from linux_python_utils.network.scanner import _detect_interface

        mock_iface = MagicMock()
        mock_iface.name = "eth99"
        op_file = MagicMock()
        op_file.read_text.return_value = "down"
        mock_iface.__truediv__ = lambda self, x: op_file

        with patch("linux_python_utils.network.scanner.Path") as mock_path:
            mock_net = mock_path.return_value
            mock_net.exists.return_value = True
            mock_net.iterdir.return_value = [mock_iface]
            result = _detect_interface()
        assert result == ""


class TestLinuxArpScannerAvecLogger:
    """Tests pour LinuxArpScanner avec logger."""

    def test_scan_avec_logger_log_info(self) -> None:
        """scan() avec logger appelle log_info apres succes."""
        from unittest.mock import MagicMock
        logger = MagicMock()
        executor = MagicMock(spec=CommandExecutor)
        executor.run.return_value = _make_result(stdout=ARP_OUTPUT)
        scanner = LinuxArpScanner(logger=logger, executor=executor)
        config = NetworkConfig(cidr="192.168.1.0/24")
        devices = scanner.scan(config)
        assert len(devices) == 2
        logger.log_info.assert_called_once()

    def test_arp_parse_value_error_ignore(self) -> None:
        """_parse_output() ignore les entrees qui levent ValueError."""
        from unittest.mock import MagicMock, patch
        scanner = LinuxArpScanner()
        output = "bad-ip\t00:11:22:33:44:55\tVendor\n"
        with patch(
            "linux_python_utils.network.scanner.NetworkDevice",
            side_effect=ValueError("bad ip")
        ):
            devices = scanner._parse_output(output)
        assert devices == []


class TestLinuxNmapScannerAvecLogger:
    """Tests pour LinuxNmapScanner avec logger."""

    def test_scan_avec_logger_log_info(self) -> None:
        """scan() avec logger appelle log_info apres succes."""
        from unittest.mock import MagicMock
        logger = MagicMock()
        executor = MagicMock(spec=CommandExecutor)
        executor.run.return_value = _make_result(stdout=NMAP_XML)
        scanner = LinuxNmapScanner(logger=logger, executor=executor)
        config = NetworkConfig(cidr="192.168.1.0/24")
        devices = scanner.scan(config)
        assert len(devices) == 2
        logger.log_info.assert_called_once()

    def test_nmap_parse_value_error_ignore(self) -> None:
        """_parse_xml_output() ignore les hotes qui levent ValueError."""
        from unittest.mock import MagicMock, patch
        scanner = LinuxNmapScanner()
        with patch(
            "linux_python_utils.network.scanner.NetworkDevice",
            side_effect=ValueError("bad")
        ):
            devices = scanner._parse_xml_output(NMAP_XML)
        assert devices == []

    def test_scanner_xml_nmap_invalide(self) -> None:
        """Sortie nmap non-XML retourne liste vide."""
        scanner = LinuxNmapScanner()
        devices = scanner._parse_xml_output("pas du xml {{{{")
        assert devices == []

    def test_scanner_xml_nmap_invalide_logue_warning(
        self,
    ) -> None:
        """ParseError sur sortie nmap logue un warning si logger présent."""
        from unittest.mock import MagicMock
        logger = MagicMock()
        scanner = LinuxNmapScanner(logger=logger)
        scanner._parse_xml_output("pas du xml {{{{")
        logger.log_warning.assert_called_once()

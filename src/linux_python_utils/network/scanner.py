"""Scanners reseau pour la decouverte de peripheriques.

Ce module fournit des implementations de NetworkScanner
utilisant arp-scan et nmap.
"""

import xml.etree.ElementTree as ET  # nosec B405
from pathlib import Path
from typing import List, Optional

from linux_python_utils.commands.base import (
    CommandExecutor,
    CommandResult,
)
from linux_python_utils.commands.builder import CommandBuilder
from linux_python_utils.commands.runner import (
    LinuxCommandExecutor,
)
from linux_python_utils.logging.base import Logger
from linux_python_utils.network.base import NetworkScanner
from linux_python_utils.network.config import NetworkConfig
from linux_python_utils.network.models import NetworkDevice


def _detect_interface() -> str:
    """Detecte l'interface reseau active.

    Parcourt /sys/class/net/ et retourne la premiere
    interface filaire active (operstate=up), sinon la
    premiere interface WiFi active, sinon chaine vide.

    Les interfaces virtuelles (loopback, docker, bridge,
    veth, tun, tap) sont ignorees.

    Returns:
        Nom de l'interface (ex: 'enp4s0', 'wlan0') ou ''.
    """
    net_dir = Path("/sys/class/net")
    if not net_dir.exists():
        return ""

    _SKIP_PREFIXES = (
        "lo", "docker", "br-", "virbr",
        "veth", "tun", "tap",
    )

    wired: List[str] = []
    wireless: List[str] = []

    for iface_path in sorted(net_dir.iterdir()):
        iface = iface_path.name
        if any(iface.startswith(p) for p in _SKIP_PREFIXES):
            continue
        try:
            state = (
                iface_path / "operstate"
            ).read_text().strip()
        except OSError:
            continue
        if state != "up":
            continue
        is_wireless = (
            (iface_path / "wireless").exists()
            or (iface_path / "phy80211").exists()
        )
        if is_wireless:
            wireless.append(iface)
        else:
            wired.append(iface)

    return (wired or wireless or [""])[0]


_VENDOR_TYPES: tuple = (
    ("synology", "NAS"),
    ("nvidia", "Media Player"),
    ("nintendo", "Console"),
    ("apple", "Apple"),
    ("oneplus", "Smartphone"),
    ("samsung", "Smartphone"),
    ("huawei", "Smartphone"),
    ("xiaomi", "Smartphone"),
    ("asustek", "Routeur"),
    ("philips light", "Eclairage"),
    ("philips hue", "Eclairage"),
    ("hangzhou", "Camera/IoT"),
    ("hikvision", "Camera"),
    ("amazon", "Amazon"),
    ("raspberry", "Raspberry Pi"),
    ("sonos", "Audio"),
    ("espressif", "IoT"),
    ("intel", "PC/Laptop"),
    ("realtek", "PC/Laptop"),
)


def _infer_type_from_vendor(vendor: str) -> str:
    """Infere le type d'appareil depuis le fabricant.

    Args:
        vendor: Nom du fabricant (OUI).

    Returns:
        Type infere ou 'unknown'.
    """
    v = vendor.lower()
    for keyword, device_type in _VENDOR_TYPES:
        if keyword in v:
            return device_type
    return "unknown"


class LinuxArpScanner(NetworkScanner):
    """Scanner reseau utilisant arp-scan.

    Attributes:
        _logger: Logger optionnel.
        _executor: Executeur de commandes.
    """

    def __init__(
        self,
        logger: Optional[Logger] = None,
        executor: Optional[CommandExecutor] = None,
    ) -> None:
        """Initialise le scanner arp-scan.

        Args:
            logger: Logger optionnel.
            executor: Executeur de commandes optionnel.
        """
        self._logger = logger
        self._executor = executor or LinuxCommandExecutor(
            logger=logger
        )

    def scan(
        self, config: NetworkConfig
    ) -> List[NetworkDevice]:
        """Scanne le reseau via arp-scan.

        Args:
            config: Configuration reseau.

        Returns:
            Liste des peripheriques decouverts.

        Raises:
            RuntimeError: Si la commande echoue.
        """
        command = self._build_command(config)
        result: CommandResult = self._executor.run(
            command, timeout=config.scan_timeout
        )
        if not result.success:
            raise RuntimeError(
                f"Echec arp-scan : {result.stderr}"
            )
        devices = self._parse_output(result.stdout)
        if self._logger:
            self._logger.log_info(
                f"arp-scan : {len(devices)} peripherique(s) "
                f"decouvert(s)"
            )
        return devices

    def _build_command(
        self, config: NetworkConfig
    ) -> List[str]:
        """Construit la commande arp-scan.

        Args:
            config: Configuration reseau.

        Returns:
            Commande sous forme de liste.
        """
        interface = config.interface or _detect_interface()
        args = [
            "arp-scan",
            "--retry=3",
            f"--bandwidth={config.scan_bandwidth}",
        ]
        if interface:
            args += ["--interface", interface]
        args.append(config.cidr)
        return CommandBuilder("sudo").with_args(args).build()

    def _parse_output(
        self, stdout: str
    ) -> List[NetworkDevice]:
        """Parse la sortie d'arp-scan.

        Args:
            stdout: Sortie standard d'arp-scan.

        Returns:
            Liste des peripheriques parses.
        """
        devices: List[NetworkDevice] = []
        for line in stdout.strip().split("\n"):
            if not line or "\t" not in line:
                continue
            if any(
                mot in line.lower()
                for mot in ["packets", "ending", "interface:"]
            ):
                continue
            parts = line.split("\t")
            if len(parts) < 2:
                continue
            ip = parts[0].strip()
            mac = parts[1].strip()
            vendor = parts[2].strip() if len(parts) > 2 else ""
            try:
                devices.append(
                    NetworkDevice(
                        ip=ip,
                        mac=mac,
                        vendor=vendor,
                        device_type=_infer_type_from_vendor(
                            vendor
                        ),
                    )
                )
            except ValueError:
                continue
        return devices


class LinuxNmapScanner(NetworkScanner):
    """Scanner reseau utilisant nmap.

    Attributes:
        _logger: Logger optionnel.
        _executor: Executeur de commandes.
    """

    def __init__(
        self,
        logger: Optional[Logger] = None,
        executor: Optional[CommandExecutor] = None,
    ) -> None:
        """Initialise le scanner nmap.

        Args:
            logger: Logger optionnel.
            executor: Executeur de commandes optionnel.
        """
        self._logger = logger
        self._executor = executor or LinuxCommandExecutor(
            logger=logger
        )

    def scan(
        self, config: NetworkConfig
    ) -> List[NetworkDevice]:
        """Scanne le reseau via nmap.

        Args:
            config: Configuration reseau.

        Returns:
            Liste des peripheriques decouverts.

        Raises:
            RuntimeError: Si la commande echoue.
        """
        command = self._build_command(config)
        result: CommandResult = self._executor.run(
            command, timeout=config.scan_timeout
        )
        if not result.success:
            raise RuntimeError(
                f"Echec nmap : {result.stderr}"
            )
        devices = self._parse_xml_output(result.stdout)
        if self._logger:
            self._logger.log_info(
                f"nmap : {len(devices)} peripherique(s) "
                f"decouvert(s)"
            )
        return devices

    def _build_command(
        self, config: NetworkConfig
    ) -> List[str]:
        """Construit la commande nmap.

        Args:
            config: Configuration reseau.

        Returns:
            Commande sous forme de liste.
        """
        interface = config.interface or _detect_interface()
        args = ["nmap", "-sn", "-oX", "-"]
        if interface:
            args += ["-e", interface]
        args.append(config.cidr)
        return CommandBuilder("sudo").with_args(args).build()

    def _parse_xml_output(
        self, stdout: str
    ) -> List[NetworkDevice]:
        """Parse la sortie XML de nmap.

        Args:
            stdout: Sortie XML de nmap.

        Returns:
            Liste des peripheriques parses.
        """
        devices: List[NetworkDevice] = []
        try:
            root = ET.fromstring(stdout)  # nosec B314
        except ET.ParseError as exc:
            if self._logger:
                self._logger.log_warning(
                    f"Sortie nmap invalide : {exc}"
                )
            return devices
        for host in root.findall("host"):
            status = host.find("status")
            if (
                status is None
                or status.get("state") != "up"
            ):
                continue
            ip_elem = host.find(
                "address[@addrtype='ipv4']"
            )
            mac_elem = host.find(
                "address[@addrtype='mac']"
            )
            if ip_elem is None or mac_elem is None:
                continue
            ip = ip_elem.get("addr", "")
            mac = mac_elem.get("addr", "")
            vendor = mac_elem.get("vendor", "")
            hostname = ""
            hostnames = host.find("hostnames")
            if hostnames is not None:
                hn = hostnames.find("hostname")
                if hn is not None:
                    hostname = hn.get("name", "")
            try:
                devices.append(
                    NetworkDevice(
                        ip=ip,
                        mac=mac,
                        vendor=vendor,
                        hostname=hostname,
                        device_type=_infer_type_from_vendor(
                            vendor
                        ),
                    )
                )
            except ValueError:
                continue
        return devices

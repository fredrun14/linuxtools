"""Tests pour la gestion DNS locale."""

from linuxtools.network.config import (
    DnsConfig,
    NetworkConfig,
)
from linuxtools.network.dns import (
    LinuxDnsmasqConfigGenerator,
    LinuxHostsFileManager,
)
from linuxtools.network.models import NetworkDevice


def _config(domain: str = "maison.local") -> NetworkConfig:
    """Cree une config reseau pour les tests."""
    return NetworkConfig(
        cidr="192.168.1.0/24",
        dns=DnsConfig(domain=domain),
    )


def _device(
    ip: str = "192.168.1.100",
    mac: str = "aa:bb:cc:dd:ee:ff",
    **kwargs,
) -> NetworkDevice:
    """Cree un NetworkDevice pour les tests."""
    return NetworkDevice(ip=ip, mac=mac, **kwargs)


class TestLinuxHostsFileManager:
    """Tests pour LinuxHostsFileManager."""

    def test_generer_dns_name_depuis_hostname(
        self,
    ) -> None:
        """Hostname 'nas' donne 'nas.maison.local'."""
        mgr = LinuxHostsFileManager(_config())
        devices = [_device(hostname="nas")]
        result = mgr.generate_dns_names(devices)
        assert result[0].dns_name == "nas.maison.local"

    def test_generer_dns_name_garde_existant(
        self,
    ) -> None:
        """dns_name existant preserve."""
        mgr = LinuxHostsFileManager(_config())
        devices = [
            _device(dns_name="custom.maison.local")
        ]
        result = mgr.generate_dns_names(devices)
        assert (
            result[0].dns_name == "custom.maison.local"
        )

    def test_generer_dns_name_sans_hostname(
        self,
    ) -> None:
        """Sans hostname, genere depuis vendor."""
        mgr = LinuxHostsFileManager(_config())
        devices = [
            _device(
                ip="192.168.1.42",
                vendor="ASUSTek",
            )
        ]
        result = mgr.generate_dns_names(devices)
        assert "asustek-42" in result[0].dns_name

    def test_generer_dns_name_sans_rien(self) -> None:
        """Sans hostname ni vendor, depuis device_type."""
        mgr = LinuxHostsFileManager(_config())
        devices = [_device(ip="192.168.1.42")]
        result = mgr.generate_dns_names(devices)
        assert "unknown-42" in result[0].dns_name

    def test_hosts_entries_format(self) -> None:
        """Format 'IP    fqdn alias'."""
        mgr = LinuxHostsFileManager(_config())
        devices = [
            _device(dns_name="nas.maison.local")
        ]
        output = mgr.generate_hosts_entries(devices)
        assert (
            "192.168.1.100    nas.maison.local nas"
            in output
        )

    def test_hosts_entries_utilise_fixed_ip(
        self,
    ) -> None:
        """Prefere fixed_ip a ip."""
        mgr = LinuxHostsFileManager(_config())
        devices = [
            _device(
                ip="192.168.1.200",
                fixed_ip="192.168.1.10",
                dns_name="nas.maison.local",
            )
        ]
        output = mgr.generate_hosts_entries(devices)
        assert "192.168.1.10" in output
        assert "192.168.1.200" not in output

    def test_hosts_entries_entete(self) -> None:
        """En-tete contient domaine et date."""
        mgr = LinuxHostsFileManager(_config())
        output = mgr.generate_hosts_entries([])
        assert "maison.local" in output
        assert "Genere le" in output

    def test_hosts_entries_liste_vide(self) -> None:
        """Liste vide retourne en-tete uniquement."""
        mgr = LinuxHostsFileManager(_config())
        output = mgr.generate_hosts_entries([])
        assert "Reseau local" in output
        lines = [
            l for l in output.strip().split("\n")
            if not l.startswith("#")
        ]
        assert lines == []


class TestLinuxDnsmasqConfigGenerator:
    """Tests pour LinuxDnsmasqConfigGenerator."""

    def test_generate_format_address(self) -> None:
        """Format 'address=/name/ip'."""
        mgr = LinuxDnsmasqConfigGenerator(_config())
        devices = [
            _device(dns_name="nas.maison.local")
        ]
        output = mgr.generate_hosts_entries(devices)
        assert (
            "address=/nas.maison.local/192.168.1.100"
            in output
        )

    def test_generate_entete(self) -> None:
        """Commentaire de section present."""
        mgr = LinuxDnsmasqConfigGenerator(_config())
        output = mgr.generate_hosts_entries([])
        assert "Configuration DNS locale" in output
        assert "maison.local" in output

    def test_generate_liste_vide(self) -> None:
        """Liste vide retourne en-tete uniquement."""
        mgr = LinuxDnsmasqConfigGenerator(_config())
        output = mgr.generate_hosts_entries([])
        assert "address=" not in output



class TestLinuxHostsFileManagerEdgeCases:
    """Tests pour les cas limites de LinuxHostsFileManager."""

    def test_hosts_entries_device_sans_dns_name(self) -> None:
        """Device sans dns_name est ignore dans generate_hosts_entries."""
        mgr = LinuxHostsFileManager(_config())
        devices = [_device()]  # pas de dns_name
        output = mgr.generate_hosts_entries(devices)
        assert "192.168.1.100" not in output

    def test_hosts_entries_fqdn_sans_point(self) -> None:
        """FQDN sans point genere une ligne sans alias."""
        mgr = LinuxHostsFileManager(_config())
        devices = [_device(dns_name="nas")]
        output = mgr.generate_hosts_entries(devices)
        assert "192.168.1.100    nas" in output
        # il ne doit pas y avoir d'alias
        lines = [ln for ln in output.split("\n") if "nas" in ln]
        assert any("nas" in ln for ln in lines)


class TestLinuxDnsmasqConfigGeneratorEdgeCases:
    """Tests pour les cas limites de LinuxDnsmasqConfigGenerator."""

    def test_generate_dns_names_sans_nom_existant(self) -> None:
        """generate_dns_names() genere le nom si dns_name absent."""
        mgr = LinuxDnsmasqConfigGenerator(_config())
        devices = [
            _device(ip="192.168.1.42", hostname="mynas"),
        ]
        result = mgr.generate_dns_names(devices)
        assert result[0].dns_name == "mynas.maison.local"

    def test_generate_dns_names_garde_nom_existant(self) -> None:
        """generate_dns_names() conserve le dns_name existant."""
        mgr = LinuxDnsmasqConfigGenerator(_config())
        devices = [_device(dns_name="existing.maison.local")]
        result = mgr.generate_dns_names(devices)
        assert result[0].dns_name == "existing.maison.local"

    def test_generate_hosts_entries_skip_sans_dns_name(self) -> None:
        """generate_hosts_entries() ignore les devices sans dns_name."""
        mgr = LinuxDnsmasqConfigGenerator(_config())
        devices = [_device()]  # pas de dns_name
        output = mgr.generate_hosts_entries(devices)
        assert "address=" not in output

    def test_generate_hosts_entries_utilise_fixed_ip(self) -> None:
        """generate_hosts_entries() utilise fixed_ip si disponible."""
        mgr = LinuxDnsmasqConfigGenerator(_config())
        devices = [
            _device(
                ip="192.168.1.200",
                fixed_ip="192.168.1.10",
                dns_name="nas.maison.local",
            )
        ]
        output = mgr.generate_hosts_entries(devices)
        assert "192.168.1.10" in output
        assert "192.168.1.200" not in output

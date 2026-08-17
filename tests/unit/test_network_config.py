"""Tests pour les classes de configuration reseau."""

import dataclasses

import pytest

from linuxtools.network.config import (
    DhcpRange,
    DnsConfig,
    NetworkConfig,
)


class TestDhcpRange:
    """Tests pour DhcpRange."""

    def test_plage_valide(self) -> None:
        """Plage valide acceptee."""
        r = DhcpRange(start="192.168.1.100", end="192.168.1.254")
        assert r.start == "192.168.1.100"
        assert r.end == "192.168.1.254"

    def test_plage_ip_unique(self) -> None:
        """start == end accepte."""
        r = DhcpRange(start="192.168.1.100", end="192.168.1.100")
        assert r.start == r.end

    def test_plage_inversee(self) -> None:
        """start > end leve ValueError."""
        with pytest.raises(ValueError):
            DhcpRange(start="192.168.1.254", end="192.168.1.100")

    def test_start_invalide(self) -> None:
        """Start invalide leve ValueError."""
        with pytest.raises(ValueError):
            DhcpRange(start="999.1.1.1", end="192.168.1.254")

    def test_end_invalide(self) -> None:
        """End invalide leve ValueError."""
        with pytest.raises(ValueError):
            DhcpRange(start="192.168.1.100", end="999.1.1.1")


class TestDnsConfig:
    """Tests pour DnsConfig."""

    def test_defauts(self) -> None:
        """Valeurs par defaut correctes."""
        dns = DnsConfig()
        assert dns.domain == "maison.local"
        assert dns.hosts_file == "/etc/hosts"
        assert dns.dnsmasq_conf == ""

    def test_personnalise(self) -> None:
        """Valeurs personnalisees."""
        dns = DnsConfig(
            domain="home.local",
            hosts_file="/tmp/hosts",
            dnsmasq_conf="/etc/dnsmasq.d/local.conf",
        )
        assert dns.domain == "home.local"
        assert dns.hosts_file == "/tmp/hosts"

    def test_frozen(self) -> None:
        """Modification leve FrozenInstanceError."""
        dns = DnsConfig()
        with pytest.raises(dataclasses.FrozenInstanceError):
            dns.domain = "autre"  # type: ignore[misc]


class TestNetworkConfig:
    """Tests pour NetworkConfig."""

    def test_creation_minimale(self) -> None:
        """Creation avec cidr uniquement."""
        config = NetworkConfig(cidr="192.168.1.0/24")
        assert config.cidr == "192.168.1.0/24"

    def test_creation_complete(self) -> None:
        """Creation avec tous les champs."""
        config = NetworkConfig(
            cidr="192.168.1.0/24",
            interface="eth0",
            dhcp_range=DhcpRange(
                start="192.168.1.100", end="192.168.1.254"
            ),
            dns=DnsConfig(domain="home.local"),
            inventory_path="inv.json",
            scan_timeout=60,
        )
        assert config.interface == "eth0"
        assert config.scan_timeout == 60
        assert config.inventory_path == "inv.json"

    def test_cidr_invalide(self) -> None:
        """CIDR invalide leve ValueError."""
        with pytest.raises(ValueError):
            NetworkConfig(cidr="invalid")

    def test_defauts(self) -> None:
        """Valeurs par defaut correctes."""
        config = NetworkConfig(cidr="192.168.1.0/24")
        assert config.interface == ""
        assert config.dhcp_range is None
        assert config.dns.domain == "maison.local"
        assert config.inventory_path == "devices.json"
        assert config.scan_timeout == 30

    def test_avec_dhcp_range(self) -> None:
        """DhcpRange integre."""
        dhcp = DhcpRange(
            start="192.168.1.100", end="192.168.1.200"
        )
        config = NetworkConfig(
            cidr="192.168.1.0/24", dhcp_range=dhcp
        )
        assert config.dhcp_range is not None
        assert config.dhcp_range.start == "192.168.1.100"

    def test_avec_dns_config(self) -> None:
        """DnsConfig integre."""
        dns = DnsConfig(domain="test.local")
        config = NetworkConfig(
            cidr="192.168.1.0/24", dns=dns
        )
        assert config.dns.domain == "test.local"

    def test_frozen(self) -> None:
        """Modification leve FrozenInstanceError."""
        config = NetworkConfig(cidr="192.168.1.0/24")
        with pytest.raises(dataclasses.FrozenInstanceError):
            config.cidr = "10.0.0.0/8"  # type: ignore[misc]

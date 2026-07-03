"""Tests pour le modele NetworkDevice."""

import dataclasses
from datetime import datetime

import pytest

from linuxtools.network.models import NetworkDevice


class TestNetworkDevice:
    """Tests pour NetworkDevice."""

    def test_creation_minimale(self) -> None:
        """Creation avec ip et mac uniquement."""
        device = NetworkDevice(
            ip="192.168.1.1", mac="aa:bb:cc:dd:ee:ff"
        )
        assert device.ip == "192.168.1.1"
        assert device.mac == "aa:bb:cc:dd:ee:ff"

    def test_creation_complete(self) -> None:
        """Creation avec tous les champs."""
        now = datetime.now()
        device = NetworkDevice(
            ip="192.168.1.1",
            mac="aa:bb:cc:dd:ee:ff",
            hostname="nas",
            vendor="Synology",
            device_type="nas",
            is_known=True,
            fixed_ip="192.168.1.100",
            dns_name="nas.maison.local",
            first_seen=now,
            last_seen=now,
            notes="NAS principal",
        )
        assert device.hostname == "nas"
        assert device.vendor == "Synology"
        assert device.device_type == "nas"
        assert device.is_known is True
        assert device.fixed_ip == "192.168.1.100"
        assert device.dns_name == "nas.maison.local"
        assert device.notes == "NAS principal"

    def test_frozen(self) -> None:
        """Modification leve FrozenInstanceError."""
        device = NetworkDevice(
            ip="192.168.1.1", mac="aa:bb:cc:dd:ee:ff"
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            device.ip = "192.168.1.2"  # type: ignore[misc]

    def test_ip_invalide(self) -> None:
        """IP invalide leve ValueError."""
        with pytest.raises(ValueError):
            NetworkDevice(ip="999.1.1.1", mac="aa:bb:cc:dd:ee:ff")

    def test_mac_invalide(self) -> None:
        """MAC invalide leve ValueError."""
        with pytest.raises(ValueError):
            NetworkDevice(ip="192.168.1.1", mac="invalid")

    def test_mac_normalisee(self) -> None:
        """MAC majuscules normalisee en minuscules."""
        device = NetworkDevice(
            ip="192.168.1.1", mac="AA:BB:CC:DD:EE:FF"
        )
        assert device.mac == "aa:bb:cc:dd:ee:ff"

    def test_fixed_ip_invalide(self) -> None:
        """fixed_ip invalide leve ValueError."""
        with pytest.raises(ValueError):
            NetworkDevice(
                ip="192.168.1.1",
                mac="aa:bb:cc:dd:ee:ff",
                fixed_ip="999.1.1.1",
            )

    def test_fixed_ip_none(self) -> None:
        """fixed_ip None est accepte."""
        device = NetworkDevice(
            ip="192.168.1.1",
            mac="aa:bb:cc:dd:ee:ff",
            fixed_ip=None,
        )
        assert device.fixed_ip is None

    def test_to_dict(self) -> None:
        """Serialisation en dict avec datetime ISO."""
        now = datetime(2026, 1, 15, 10, 30, 0)
        device = NetworkDevice(
            ip="192.168.1.1",
            mac="aa:bb:cc:dd:ee:ff",
            hostname="nas",
            first_seen=now,
            last_seen=now,
        )
        d = device.to_dict()
        assert d["ip"] == "192.168.1.1"
        assert d["mac"] == "aa:bb:cc:dd:ee:ff"
        assert d["hostname"] == "nas"
        assert d["first_seen"] == "2026-01-15T10:30:00"
        assert d["last_seen"] == "2026-01-15T10:30:00"

    def test_from_dict(self) -> None:
        """Reconstruction depuis dict."""
        data = {
            "ip": "192.168.1.1",
            "mac": "aa:bb:cc:dd:ee:ff",
            "hostname": "nas",
            "vendor": "Synology",
            "device_type": "nas",
            "is_known": True,
            "fixed_ip": "192.168.1.100",
            "dns_name": "nas.local",
            "first_seen": "2026-01-15T10:30:00",
            "last_seen": "2026-01-15T10:30:00",
            "notes": "test",
        }
        device = NetworkDevice.from_dict(data)
        assert device.ip == "192.168.1.1"
        assert device.hostname == "nas"
        assert device.first_seen == datetime(2026, 1, 15, 10, 30)

    def test_to_dict_from_dict_roundtrip(self) -> None:
        """to_dict puis from_dict donne un objet identique."""
        now = datetime(2026, 1, 15, 10, 30, 0)
        device = NetworkDevice(
            ip="192.168.1.1",
            mac="aa:bb:cc:dd:ee:ff",
            hostname="nas",
            vendor="Synology",
            device_type="nas",
            is_known=True,
            fixed_ip="192.168.1.100",
            dns_name="nas.local",
            first_seen=now,
            last_seen=now,
            notes="test",
        )
        restored = NetworkDevice.from_dict(device.to_dict())
        assert device == restored

    def test_defauts(self) -> None:
        """Valeurs par defaut correctes."""
        device = NetworkDevice(
            ip="192.168.1.1", mac="aa:bb:cc:dd:ee:ff"
        )
        assert device.hostname == ""
        assert device.vendor == ""
        assert device.device_type == "unknown"
        assert device.is_known is False
        assert device.fixed_ip is None
        assert device.dns_name is None
        assert device.notes == ""

    def test_ip_vide_acceptee(self) -> None:
        """IP vide acceptee pour les appareils hors ligne."""
        device = NetworkDevice(
            ip="", mac="aa:bb:cc:dd:ee:ff"
        )
        assert device.ip == ""

    def test_ip_invalide_leve_erreur(self) -> None:
        """IP non vide et invalide leve ValueError."""
        with pytest.raises(ValueError):
            NetworkDevice(
                ip="999.1.1.1", mac="aa:bb:cc:dd:ee:ff"
            )

    def test_roundtrip_ip_vide(self) -> None:
        """to_dict / from_dict conserve ip vide."""
        now = datetime(2026, 1, 15, 10, 30, 0)
        device = NetworkDevice(
            ip="",
            mac="aa:bb:cc:dd:ee:ff",
            hostname="Thermomix",
            first_seen=now,
            last_seen=now,
        )
        restored = NetworkDevice.from_dict(device.to_dict())
        assert restored.ip == ""
        assert restored.hostname == "Thermomix"

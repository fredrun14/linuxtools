"""Tests pour le repository JSON de peripheriques."""

from datetime import datetime

import pytest

from linux_python_utils.network.models import NetworkDevice
from linux_python_utils.network.repository import (
    JsonDeviceRepository,
)


def _device(
    ip: str = "192.168.1.1",
    mac: str = "aa:bb:cc:dd:ee:ff",
    **kwargs,
) -> NetworkDevice:
    """Cree un NetworkDevice pour les tests."""
    return NetworkDevice(ip=ip, mac=mac, **kwargs)


class TestJsonDeviceRepository:
    """Tests pour JsonDeviceRepository."""

    def test_save_puis_load(self, tmp_path) -> None:
        """Sauvegarder puis recharger 3 peripheriques."""
        path = tmp_path / "devices.json"
        repo = JsonDeviceRepository(str(path))
        devices = [
            _device("192.168.1.1", "aa:bb:cc:dd:ee:01"),
            _device("192.168.1.2", "aa:bb:cc:dd:ee:02"),
            _device("192.168.1.3", "aa:bb:cc:dd:ee:03"),
        ]
        repo.save(devices)
        loaded = repo.load()
        assert len(loaded) == 3
        assert loaded[0].ip == "192.168.1.1"
        assert loaded[2].mac == "aa:bb:cc:dd:ee:03"

    def test_load_fichier_inexistant(
        self, tmp_path
    ) -> None:
        """Fichier inexistant retourne liste vide."""
        path = tmp_path / "absent.json"
        repo = JsonDeviceRepository(str(path))
        assert repo.load() == []

    def test_load_fichier_vide(self, tmp_path) -> None:
        """Fichier vide retourne liste vide."""
        path = tmp_path / "empty.json"
        path.write_text("")
        repo = JsonDeviceRepository(str(path))
        assert repo.load() == []

    def test_find_by_mac_existant(
        self, tmp_path
    ) -> None:
        """Trouve un peripherique par MAC."""
        path = tmp_path / "devices.json"
        repo = JsonDeviceRepository(str(path))
        repo.save([
            _device("192.168.1.1", "aa:bb:cc:dd:ee:01"),
            _device("192.168.1.2", "aa:bb:cc:dd:ee:02"),
        ])
        found = repo.find_by_mac("aa:bb:cc:dd:ee:02")
        assert found is not None
        assert found.ip == "192.168.1.2"

    def test_find_by_mac_inexistant(
        self, tmp_path
    ) -> None:
        """MAC inexistante retourne None."""
        path = tmp_path / "devices.json"
        repo = JsonDeviceRepository(str(path))
        repo.save([_device()])
        assert repo.find_by_mac("ff:ff:ff:ff:ff:ff") is None

    def test_find_by_mac_normalise(
        self, tmp_path
    ) -> None:
        """Recherche MAC insensible a la casse."""
        path = tmp_path / "devices.json"
        repo = JsonDeviceRepository(str(path))
        repo.save([_device(mac="aa:bb:cc:dd:ee:ff")])
        found = repo.find_by_mac("AA:BB:CC:DD:EE:FF")
        assert found is not None

    def test_find_by_ip_existant(
        self, tmp_path
    ) -> None:
        """Trouve un peripherique par IP."""
        path = tmp_path / "devices.json"
        repo = JsonDeviceRepository(str(path))
        repo.save([_device("192.168.1.42", "aa:bb:cc:dd:ee:ff")])
        found = repo.find_by_ip("192.168.1.42")
        assert found is not None
        assert found.mac == "aa:bb:cc:dd:ee:ff"

    def test_find_by_ip_inexistant(
        self, tmp_path
    ) -> None:
        """IP inexistante retourne None."""
        path = tmp_path / "devices.json"
        repo = JsonDeviceRepository(str(path))
        repo.save([_device()])
        assert repo.find_by_ip("10.0.0.1") is None

    def test_merge_nouveau_peripherique(self) -> None:
        """MAC inconnue apparait dans new_devices."""
        repo = JsonDeviceRepository("dummy.json")
        existing = [
            _device("192.168.1.1", "aa:bb:cc:dd:ee:01")
        ]
        scanned = [
            _device("192.168.1.1", "aa:bb:cc:dd:ee:01"),
            _device("192.168.1.2", "aa:bb:cc:dd:ee:02"),
        ]
        merged, new, disappeared = repo.merge_scan_results(
            existing, scanned
        )
        assert len(new) == 1
        assert new[0].mac == "aa:bb:cc:dd:ee:02"

    def test_merge_peripherique_existant(self) -> None:
        """MAC connue a son last_seen mis a jour."""
        repo = JsonDeviceRepository("dummy.json")
        old_time = datetime(2020, 1, 1)
        existing = [
            _device(
                "192.168.1.1",
                "aa:bb:cc:dd:ee:01",
                last_seen=old_time,
            )
        ]
        scanned = [
            _device("192.168.1.1", "aa:bb:cc:dd:ee:01")
        ]
        merged, _, _ = repo.merge_scan_results(
            existing, scanned
        )
        assert merged[0].last_seen > old_time

    def test_merge_peripherique_disparu(self) -> None:
        """Peripherique absent du scan dans disappeared."""
        repo = JsonDeviceRepository("dummy.json")
        existing = [
            _device("192.168.1.1", "aa:bb:cc:dd:ee:01"),
            _device("192.168.1.2", "aa:bb:cc:dd:ee:02"),
        ]
        scanned = [
            _device("192.168.1.1", "aa:bb:cc:dd:ee:01")
        ]
        _, _, disappeared = repo.merge_scan_results(
            existing, scanned
        )
        assert len(disappeared) == 1
        assert disappeared[0].mac == "aa:bb:cc:dd:ee:02"

    def test_merge_conserve_metadata(self) -> None:
        """is_known, fixed_ip, dns_name, notes preserves."""
        repo = JsonDeviceRepository("dummy.json")
        existing = [
            _device(
                "192.168.1.1",
                "aa:bb:cc:dd:ee:01",
                is_known=True,
                fixed_ip="192.168.1.10",
                dns_name="nas.local",
                notes="NAS",
            )
        ]
        scanned = [
            _device("192.168.1.1", "aa:bb:cc:dd:ee:01")
        ]
        merged, _, _ = repo.merge_scan_results(
            existing, scanned
        )
        assert merged[0].is_known is True
        assert merged[0].fixed_ip == "192.168.1.10"
        assert merged[0].dns_name == "nas.local"
        assert merged[0].notes == "NAS"

    def test_merge_ip_changee(self) -> None:
        """Device avec nouvelle IP a son IP mise a jour."""
        repo = JsonDeviceRepository("dummy.json")
        existing = [
            _device("192.168.1.1", "aa:bb:cc:dd:ee:01")
        ]
        scanned = [
            _device("192.168.1.99", "aa:bb:cc:dd:ee:01")
        ]
        merged, _, _ = repo.merge_scan_results(
            existing, scanned
        )
        assert merged[0].ip == "192.168.1.99"

    def test_merge_ip_vide_preserve_ancienne_ip(
        self,
    ) -> None:
        """Appareil rescanne sans IP conserve l'ancienne IP."""
        repo = JsonDeviceRepository("dummy.json")
        existing = [
            _device("192.168.1.7", "aa:bb:cc:dd:ee:01")
        ]
        scanned = [
            _device("", "aa:bb:cc:dd:ee:01",
                    hostname="Thermomix")
        ]
        merged, _, _ = repo.merge_scan_results(
            existing, scanned
        )
        assert merged[0].ip == "192.168.1.7"

    def test_json_encoding_utf8(self, tmp_path) -> None:
        """Caracteres accentues preserves."""
        path = tmp_path / "devices.json"
        repo = JsonDeviceRepository(str(path))
        repo.save([
            _device(notes="Peripherique reseau accentue")
        ])
        content = path.read_text(encoding="utf-8")
        assert "accentue" in content
        assert "\\u" not in content

    def test_json_datetime_iso(self, tmp_path) -> None:
        """Datetimes au format ISO 8601."""
        path = tmp_path / "devices.json"
        repo = JsonDeviceRepository(str(path))
        now = datetime(2026, 1, 15, 10, 30, 0)
        repo.save([
            _device(first_seen=now, last_seen=now)
        ])
        content = path.read_text(encoding="utf-8")
        assert "2026-01-15T10:30:00" in content


class TestJsonDeviceRepositoryAvecLogger:
    """Tests avec logger pour JsonDeviceRepository."""

    def test_load_avec_logger(self, tmp_path) -> None:
        """load() appelle logger.log_info si logger present."""
        from unittest.mock import MagicMock
        path = tmp_path / "devices.json"
        repo_sans_logger = JsonDeviceRepository(str(path))
        devices = [_device("192.168.1.1", "aa:bb:cc:dd:ee:01")]
        repo_sans_logger.save(devices)

        logger = MagicMock()
        repo = JsonDeviceRepository(str(path), logger=logger)
        result = repo.load()
        assert len(result) == 1
        logger.log_info.assert_called_once()

    def test_save_avec_logger(self, tmp_path) -> None:
        """save() appelle logger.log_info si logger present."""
        from unittest.mock import MagicMock
        path = tmp_path / "devices.json"
        logger = MagicMock()
        repo = JsonDeviceRepository(str(path), logger=logger)
        devices = [_device()]
        repo.save(devices)
        logger.log_info.assert_called_once()


class TestJsonDeviceRepositoryRobustesse:
    """Tests robustesse : écriture atomique et lecture tolérante."""

    def test_save_inventaire_atomique(
        self, tmp_path
    ) -> None:
        """save() écrit de façon atomique (aucun tmp après succès)."""
        path = tmp_path / "devices.json"
        repo = JsonDeviceRepository(str(path))
        repo.save([_device()])
        assert path.exists()
        tmps = list(tmp_path.glob("*.tmp"))
        assert tmps == []

    def test_load_json_corrompu_retourne_liste_vide(
        self, tmp_path
    ) -> None:
        """Fichier JSON corrompu retourne une liste vide."""
        path = tmp_path / "corrupt.json"
        path.write_text("{invalide json{{", encoding="utf-8")
        repo = JsonDeviceRepository(str(path))
        assert repo.load() == []

    def test_load_json_corrompu_logue_warning(
        self, tmp_path
    ) -> None:
        """Fichier JSON corrompu logue un warning si logger présent."""
        from unittest.mock import MagicMock
        path = tmp_path / "corrupt.json"
        path.write_text("{invalide json{{", encoding="utf-8")
        logger = MagicMock()
        repo = JsonDeviceRepository(str(path), logger=logger)
        repo.load()
        logger.log_warning.assert_called_once()

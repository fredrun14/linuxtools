"""Tests pour le module systemd.automount_installer."""

import unittest
from unittest.mock import Mock

from linuxtools import (
    Logger,
    MountConfig,
    SystemdAutomountInstaller,
)
from linuxtools.config import ConfigLoader


class MockConfigLoader(ConfigLoader):
    """Mock du ConfigLoader retournant un dictionnaire fixe."""

    def __init__(self, config: dict):
        self._config = config

    def load(self, config_path, schema=None):
        return self._config


class TestSystemdAutomountInstallerInstall(unittest.TestCase):
    """Tests pour la méthode install (config déjà construite)."""

    def setUp(self):
        """Crée les mocks et la configuration nécessaires."""
        self.mock_logger = Mock(spec=Logger)
        self.mock_mount_manager = Mock()

        self.installer = SystemdAutomountInstaller(
            logger=self.mock_logger,
            mount_manager=self.mock_mount_manager,
        )

        self.config = MountConfig(
            description="NAS Share",
            what="192.168.1.10:/share",
            where="/media/nas",
            type="nfs",
            options="rw,soft",
        )

    def _setup_all_success(self):
        """Configure tous les mocks pour retourner True."""
        self.mock_mount_manager.install_mount_unit.return_value = True
        self.mock_mount_manager.enable_mount.return_value = True

    def test_install_installs_mount_then_enables(self):
        """Vérifie l'orchestration complète en cas de succès."""
        self._setup_all_success()

        result = self.installer.install(self.config)

        self.assertTrue(result)
        self.mock_mount_manager.install_mount_unit.assert_called_once()
        self.mock_mount_manager.enable_mount.assert_called_once()

    def test_install_passes_with_automount_and_timeout(self):
        """Vérifie la transmission des réglages automount."""
        self._setup_all_success()

        self.installer.install(
            self.config, with_automount=True, automount_timeout_sec=600
        )

        install_kwargs = (
            self.mock_mount_manager.install_mount_unit.call_args.kwargs
        )
        self.assertTrue(install_kwargs["with_automount"])
        self.assertEqual(install_kwargs["automount_timeout"], 600)

        enable_kwargs = (
            self.mock_mount_manager.enable_mount.call_args.kwargs
        )
        self.assertTrue(enable_kwargs["with_automount"])

    def test_install_returns_false_if_install_mount_fails(self):
        """Vérifie l'arrêt si l'installation du montage échoue."""
        self.mock_mount_manager.install_mount_unit.return_value = False

        result = self.installer.install(self.config)

        self.assertFalse(result)
        self.mock_mount_manager.enable_mount.assert_not_called()
        self.mock_logger.log_error.assert_called_once()

    def test_install_returns_false_if_enable_mount_fails(self):
        """Vérifie l'échec si l'activation du montage échoue."""
        self._setup_all_success()
        self.mock_mount_manager.enable_mount.return_value = False

        result = self.installer.install(self.config)

        self.assertFalse(result)
        self.mock_logger.log_error.assert_called_once()


class TestSystemdAutomountInstallerFromToml(unittest.TestCase):
    """Tests pour la méthode install_from_toml (chargement TOML)."""

    def setUp(self):
        """Crée les mocks nécessaires."""
        self.mock_logger = Mock(spec=Logger)
        self.mock_mount_manager = Mock()
        self.mock_mount_manager.install_mount_unit.return_value = True
        self.mock_mount_manager.enable_mount.return_value = True

        self.installer = SystemdAutomountInstaller(
            logger=self.mock_logger,
            mount_manager=self.mock_mount_manager,
        )

    def test_install_from_toml_reads_automount_settings(self):
        """Vérifie le chargement des réglages automount depuis le TOML."""
        config = {
            "mount": {
                "description": "NAS",
                "what": "192.168.1.10:/share",
                "where": "/media/nas",
                "type": "nfs",
                "with_automount": True,
                "automount_timeout_sec": 600,
            }
        }
        loader = MockConfigLoader(config)

        result = self.installer.install_from_toml("/fake/path.toml", loader)

        self.assertTrue(result)
        install_args = self.mock_mount_manager.install_mount_unit.call_args
        self.assertEqual(install_args.args[0].where, "/media/nas")
        self.assertTrue(install_args.kwargs["with_automount"])
        self.assertEqual(install_args.kwargs["automount_timeout"], 600)

    def test_install_from_toml_defaults_automount_false_when_absent(self):
        """Vérifie l'absence d'automount quand les clés manquent."""
        config = {
            "mount": {
                "description": "NAS",
                "what": "192.168.1.10:/share",
                "where": "/media/nas",
                "type": "nfs",
            }
        }
        loader = MockConfigLoader(config)

        self.installer.install_from_toml("/fake/path.toml", loader)

        install_kwargs = (
            self.mock_mount_manager.install_mount_unit.call_args.kwargs
        )
        self.assertFalse(install_kwargs["with_automount"])
        self.assertEqual(install_kwargs["automount_timeout"], 0)


if __name__ == "__main__":
    unittest.main()

"""Tests pour le module systemd.service_timer_installer."""

import unittest
from unittest.mock import Mock

from linuxtools import (
    Logger,
    ServiceConfig,
    SystemdServiceTimerInstaller,
    TimerConfig,
)
from linuxtools.config import ConfigLoader


class MockConfigLoader(ConfigLoader):
    """Mock du ConfigLoader retournant un dictionnaire fixe."""

    def __init__(self, config: dict):
        self._config = config

    def load(self, config_path, schema=None):
        return self._config


class TestSystemdServiceTimerInstallerInstall(unittest.TestCase):
    """Tests pour la méthode install (configs déjà construites)."""

    def setUp(self):
        """Crée les mocks et configurations nécessaires."""
        self.mock_logger = Mock(spec=Logger)
        self.mock_service_manager = Mock()
        self.mock_timer_manager = Mock()

        self.installer = SystemdServiceTimerInstaller(
            logger=self.mock_logger,
            service_manager=self.mock_service_manager,
            timer_manager=self.mock_timer_manager,
        )

        self.unit_name = "backup"
        self.service_config = ServiceConfig(
            description="Backup Service",
            exec_start="/usr/local/bin/backup run",
            type="oneshot",
        )
        self.timer_config = TimerConfig(
            description="Backup Timer",
            unit="backup.service",
            on_calendar="daily",
            persistent=True,
        )

    def _setup_all_success(self):
        """Configure tous les mocks pour retourner True."""
        self.mock_service_manager.install_service_unit_with_name \
            .return_value = True
        self.mock_timer_manager.install_timer_unit.return_value = True
        self.mock_timer_manager.enable_timer.return_value = True

    def _install(self):
        """Raccourci pour appeler install avec les configs de test."""
        return self.installer.install(
            self.unit_name, self.service_config, self.timer_config
        )

    def test_install_installs_service_then_timer_then_enables(self):
        """Vérifie l'orchestration complète en cas de succès."""
        self._setup_all_success()

        result = self._install()

        self.assertTrue(result)
        self.mock_service_manager.install_service_unit_with_name \
            .assert_called_once_with(self.unit_name, self.service_config)
        self.mock_timer_manager.install_timer_unit \
            .assert_called_once_with(self.timer_config)
        self.mock_timer_manager.enable_timer \
            .assert_called_once_with(self.unit_name)

    def test_install_returns_false_if_service_install_fails(self):
        """Vérifie l'arrêt si l'installation du service échoue."""
        self.mock_service_manager.install_service_unit_with_name \
            .return_value = False

        result = self._install()

        self.assertFalse(result)
        self.mock_timer_manager.install_timer_unit.assert_not_called()
        self.mock_logger.log_error.assert_called_once()

    def test_install_returns_false_if_timer_install_fails(self):
        """Vérifie l'arrêt si l'installation du timer échoue."""
        self._setup_all_success()
        self.mock_timer_manager.install_timer_unit.return_value = False

        result = self._install()

        self.assertFalse(result)
        self.mock_timer_manager.enable_timer.assert_not_called()

    def test_install_returns_false_if_enable_fails(self):
        """Vérifie l'échec si l'activation du timer échoue."""
        self._setup_all_success()
        self.mock_timer_manager.enable_timer.return_value = False

        result = self._install()

        self.assertFalse(result)
        self.mock_logger.log_error.assert_called_once()


class TestSystemdServiceTimerInstallerFromToml(unittest.TestCase):
    """Tests pour la méthode install_from_toml (chargement TOML)."""

    def setUp(self):
        """Crée les mocks et le contenu TOML simulé."""
        self.mock_logger = Mock(spec=Logger)
        self.mock_service_manager = Mock()
        self.mock_service_manager.install_service_unit_with_name \
            .return_value = True
        self.mock_timer_manager = Mock()
        self.mock_timer_manager.install_timer_unit.return_value = True
        self.mock_timer_manager.enable_timer.return_value = True

        self.installer = SystemdServiceTimerInstaller(
            logger=self.mock_logger,
            service_manager=self.mock_service_manager,
            timer_manager=self.mock_timer_manager,
        )

        self.config = {
            "service": {
                "description": "Backup durci",
                "exec_start": "/usr/local/bin/backup run",
                "type": "oneshot",
                "no_new_privileges": True,
                "protect_system": "full",
                "read_write_paths": ["/var/lib/backup"],
            },
            "timer": {
                "description": "Backup Timer",
                "unit": "ignoré.service",
                "on_calendar": "daily",
                "persistent": True,
            },
        }
        self.mock_config_loader = MockConfigLoader(self.config)

    def test_install_from_toml_loads_configs_and_delegates(self):
        """Vérifie le chargement puis la délégation à install."""
        result = self.installer.install_from_toml(
            "backup", "/fake/path.toml", self.mock_config_loader
        )

        self.assertTrue(result)
        service_config = (
            self.mock_service_manager.install_service_unit_with_name
            .call_args.args[1]
        )
        self.assertTrue(service_config.no_new_privileges)
        self.assertEqual(
            service_config.read_write_paths, ("/var/lib/backup",)
        )

    def test_install_from_toml_uses_unit_name_for_timer_unit(self):
        """Vérifie que le timer cible bien <unit_name>.service."""
        self.installer.install_from_toml(
            "backup", "/fake/path.toml", self.mock_config_loader
        )

        timer_config = (
            self.mock_timer_manager.install_timer_unit.call_args.args[0]
        )
        self.assertEqual(timer_config.unit, "backup.service")


if __name__ == "__main__":
    unittest.main()

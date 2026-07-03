"""Tests pour les chargeurs de configuration systemd."""

import unittest
from unittest.mock import Mock

from linuxtools import (
    BashScriptConfig,
    MountConfig,
    NotificationConfig,
    ServiceConfig,
    TimerConfig,
)
from linuxtools.config import ConfigLoader, ConfigFileLoader
from linuxtools.systemd.config_loaders import (
    BashScriptConfigLoader,
    MountConfigLoader,
    ServiceConfigLoader,
    TimerConfigLoader,
)


class MockConfigLoader(ConfigLoader):
    """Mock du ConfigLoader pour les tests."""

    def __init__(self, config: dict):
        self._config = config

    def load(self, config_path, schema=None):
        return self._config


class TestServiceConfigLoader(unittest.TestCase):
    """Tests pour ServiceConfigLoader."""

    def test_load_returns_service_config(self):
        """Vérifie que load retourne un ServiceConfig."""
        config = {
            "service": {
                "description": "Test Service",
                "exec_start": "/usr/bin/test",
                "type": "oneshot",
            }
        }
        mock_loader = MockConfigLoader(config)
        loader = ServiceConfigLoader("/fake/path.toml", mock_loader)

        result = loader.load()

        self.assertIsInstance(result, ServiceConfig)
        self.assertEqual(result.description, "Test Service")
        self.assertEqual(result.exec_start, "/usr/bin/test")
        self.assertEqual(result.type, "oneshot")

    def test_load_uses_defaults(self):
        """Vérifie que load utilise les valeurs par défaut."""
        config = {
            "service": {
                "description": "Test",
                "exec_start": "/usr/bin/test",
            }
        }
        mock_loader = MockConfigLoader(config)
        loader = ServiceConfigLoader("/fake/path.toml", mock_loader)

        result = loader.load()

        self.assertEqual(result.type, "simple")
        self.assertEqual(result.restart, "no")
        self.assertEqual(result.wanted_by, "multi-user.target")

    def test_load_custom_section(self):
        """Vérifie le chargement depuis une section personnalisée."""
        config = {
            "my_service": {
                "description": "Custom Service",
                "exec_start": "/usr/bin/custom",
            }
        }
        mock_loader = MockConfigLoader(config)
        loader = ServiceConfigLoader("/fake/path.toml", mock_loader)

        result = loader.load(section="my_service")

        self.assertEqual(result.description, "Custom Service")

    def test_load_raises_key_error_on_missing_section(self):
        """Vérifie que load lève KeyError si la section manque."""
        config = {"other": {}}
        mock_loader = MockConfigLoader(config)
        loader = ServiceConfigLoader("/fake/path.toml", mock_loader)

        with self.assertRaises(KeyError) as context:
            loader.load()

        self.assertIn("service", str(context.exception))

    def test_load_with_exec_override(self):
        """Vérifie load_with_exec_override."""
        config = {
            "service": {
                "description": "Test",
                "exec_start": "/usr/bin/original",
            }
        }
        mock_loader = MockConfigLoader(config)
        loader = ServiceConfigLoader("/fake/path.toml", mock_loader)

        result = loader.load_with_exec_override("/usr/bin/override")

        self.assertEqual(result.exec_start, "/usr/bin/override")

    def test_load_all_service_fields(self):
        """Vérifie le chargement de tous les champs ServiceConfig."""
        config = {
            "service": {
                "description": "Full Service",
                "exec_start": "/usr/bin/app",
                "type": "forking",
                "user": "appuser",
                "group": "appgroup",
                "working_directory": "/var/lib/app",
                "environment": {"VAR1": "value1"},
                "restart": "on-failure",
                "restart_sec": 5,
                "wanted_by": "graphical.target",
            }
        }
        mock_loader = MockConfigLoader(config)
        loader = ServiceConfigLoader("/fake/path.toml", mock_loader)

        result = loader.load()

        self.assertEqual(result.user, "appuser")
        self.assertEqual(result.group, "appgroup")
        self.assertEqual(result.working_directory, "/var/lib/app")
        self.assertEqual(result.environment, {"VAR1": "value1"})
        self.assertEqual(result.restart, "on-failure")
        self.assertEqual(result.restart_sec, 5)
        self.assertEqual(result.wanted_by, "graphical.target")

    def test_load_from_json_path(self):
        """Vérifie que le loader accepte un chemin JSON."""
        config = {
            "service": {
                "description": "JSON Service",
                "exec_start": "/usr/bin/json-app",
            }
        }
        mock_loader = MockConfigLoader(config)
        loader = ServiceConfigLoader("/fake/path.json", mock_loader)

        result = loader.load()

        self.assertEqual(result.description, "JSON Service")


class TestTimerConfigLoader(unittest.TestCase):
    """Tests pour TimerConfigLoader."""

    def test_load_returns_timer_config(self):
        """Vérifie que load retourne un TimerConfig."""
        config = {
            "timer": {
                "description": "Test Timer",
                "unit": "test.service",
                "on_calendar": "daily",
                "persistent": True,
            }
        }
        mock_loader = MockConfigLoader(config)
        loader = TimerConfigLoader("/fake/path.toml", mock_loader)

        result = loader.load()

        self.assertIsInstance(result, TimerConfig)
        self.assertEqual(result.description, "Test Timer")
        self.assertEqual(result.unit, "test.service")
        self.assertEqual(result.on_calendar, "daily")
        self.assertTrue(result.persistent)

    def test_load_uses_defaults(self):
        """Vérifie que load utilise les valeurs par défaut."""
        config = {
            "timer": {
                "description": "Test",
                "unit": "test.service",
            }
        }
        mock_loader = MockConfigLoader(config)
        loader = TimerConfigLoader("/fake/path.toml", mock_loader)

        result = loader.load()

        self.assertEqual(result.on_calendar, "")
        self.assertFalse(result.persistent)

    def test_load_for_service(self):
        """Vérifie load_for_service."""
        config = {
            "timer": {
                "description": "Test Timer",
                "unit": "original.service",
                "on_calendar": "daily",
            }
        }
        mock_loader = MockConfigLoader(config)
        loader = TimerConfigLoader("/fake/path.toml", mock_loader)

        result = loader.load_for_service("my-service")

        self.assertEqual(result.unit, "my-service.service")

    def test_load_for_service_with_extension(self):
        """Vérifie load_for_service avec extension déjà présente."""
        config = {
            "timer": {
                "description": "Test",
                "unit": "original.service",
            }
        }
        mock_loader = MockConfigLoader(config)
        loader = TimerConfigLoader("/fake/path.toml", mock_loader)

        result = loader.load_for_service("my-service.service")

        self.assertEqual(result.unit, "my-service.service")

    def test_load_all_timer_fields(self):
        """Vérifie le chargement de tous les champs TimerConfig."""
        config = {
            "timer": {
                "description": "Full Timer",
                "unit": "app.service",
                "on_calendar": "*-*-* 03:00:00",
                "on_boot_sec": "5min",
                "on_unit_active_sec": "1h",
                "persistent": True,
                "randomized_delay_sec": "30min",
            }
        }
        mock_loader = MockConfigLoader(config)
        loader = TimerConfigLoader("/fake/path.toml", mock_loader)

        result = loader.load()

        self.assertEqual(result.on_boot_sec, "5min")
        self.assertEqual(result.on_unit_active_sec, "1h")
        self.assertEqual(result.randomized_delay_sec, "30min")


class TestMountConfigLoader(unittest.TestCase):
    """Tests pour MountConfigLoader."""

    def test_load_returns_mount_config(self):
        """Vérifie que load retourne un MountConfig."""
        config = {
            "mount": {
                "description": "NAS Share",
                "what": "192.168.1.10:/share",
                "where": "/media/nas",
                "type": "nfs",
            }
        }
        mock_loader = MockConfigLoader(config)
        loader = MountConfigLoader("/fake/path.toml", mock_loader)

        result = loader.load()

        self.assertIsInstance(result, MountConfig)
        self.assertEqual(result.description, "NAS Share")
        self.assertEqual(result.what, "192.168.1.10:/share")
        self.assertEqual(result.where, "/media/nas")
        self.assertEqual(result.type, "nfs")

    def test_load_with_options(self):
        """Vérifie le chargement avec options."""
        config = {
            "mount": {
                "description": "NAS",
                "what": "//server/share",
                "where": "/media/share",
                "type": "cifs",
                "options": "username=user,password=pass",
            }
        }
        mock_loader = MockConfigLoader(config)
        loader = MountConfigLoader("/fake/path.toml", mock_loader)

        result = loader.load()

        self.assertEqual(result.options, "username=user,password=pass")

    def test_load_multiple(self):
        """Vérifie load_multiple avec une liste de montages."""
        config = {
            "mounts": [
                {
                    "description": "NAS 1",
                    "what": "192.168.1.10:/share1",
                    "where": "/media/nas1",
                    "type": "nfs",
                },
                {
                    "description": "NAS 2",
                    "what": "192.168.1.11:/share2",
                    "where": "/media/nas2",
                    "type": "nfs",
                    "options": "ro",
                },
            ]
        }
        mock_loader = MockConfigLoader(config)
        loader = MountConfigLoader("/fake/path.toml", mock_loader)

        results = loader.load_multiple()

        self.assertEqual(len(results), 2)
        self.assertEqual(results[0].where, "/media/nas1")
        self.assertEqual(results[1].where, "/media/nas2")
        self.assertEqual(results[1].options, "ro")

    def test_load_multiple_raises_type_error_if_not_list(self):
        """Vérifie que load_multiple lève TypeError si pas une liste."""
        config = {
            "mounts": {
                "description": "Not a list",
                "what": "server:/share",
                "where": "/media/share",
                "type": "nfs",
            }
        }
        mock_loader = MockConfigLoader(config)
        loader = MountConfigLoader("/fake/path.toml", mock_loader)

        with self.assertRaises(TypeError) as context:
            loader.load_multiple()

        self.assertIn("doit être une liste", str(context.exception))
        self.assertIn("mounts", str(context.exception))

    def test_load_multiple_message_contient_nom_section(self):
        """Vérifie que le nom de section est interpolé dans le message."""
        config = {"custom_mounts": {"not": "a list"}}
        mock_loader = MockConfigLoader(config)
        loader = MountConfigLoader("/fake/path.toml", mock_loader)

        with self.assertRaises(TypeError) as context:
            loader.load_multiple(section="custom_mounts")

        self.assertIn("custom_mounts", str(context.exception))


class TestBashScriptConfigLoader(unittest.TestCase):
    """Tests pour BashScriptConfigLoader."""

    def test_load_returns_bash_script_config(self):
        """Vérifie que load retourne un BashScriptConfig."""
        config = {
            "service": {
                "exec_command": "/usr/bin/flatpak update -y",
            }
        }
        mock_loader = MockConfigLoader(config)
        loader = BashScriptConfigLoader("/fake/path.toml", mock_loader)

        result = loader.load()

        self.assertIsInstance(result, BashScriptConfig)
        self.assertEqual(result.exec_command, "/usr/bin/flatpak update -y")

    def test_load_with_exec_start_fallback(self):
        """Vérifie que load utilise exec_start si exec_command absent."""
        config = {
            "service": {
                "exec_start": "/usr/bin/app",
            }
        }
        mock_loader = MockConfigLoader(config)
        loader = BashScriptConfigLoader("/fake/path.toml", mock_loader)

        result = loader.load()

        self.assertEqual(result.exec_command, "/usr/bin/app")

    def test_load_without_notification(self):
        """Vérifie le chargement sans notification."""
        config = {
            "service": {
                "exec_command": "/usr/bin/test",
            }
        }
        mock_loader = MockConfigLoader(config)
        loader = BashScriptConfigLoader("/fake/path.toml", mock_loader)

        result = loader.load()

        self.assertIsNone(result.notification)

    def test_load_with_notification_disabled(self):
        """Vérifie que notification disabled = pas de notification."""
        config = {
            "service": {"exec_command": "/usr/bin/test"},
            "notification": {"enabled": False},
        }
        mock_loader = MockConfigLoader(config)
        loader = BashScriptConfigLoader("/fake/path.toml", mock_loader)

        result = loader.load()

        self.assertIsNone(result.notification)

    def test_load_with_notification_enabled(self):
        """Vérifie le chargement avec notification activée."""
        config = {
            "service": {"exec_command": "/usr/bin/test"},
            "notification": {
                "enabled": True,
                "title": "Test Notification",
                "message_success": "Success!",
                "message_failure": "Failed!",
                "icon_success": "test-ok",
                "icon_failure": "test-error",
            },
        }
        mock_loader = MockConfigLoader(config)
        loader = BashScriptConfigLoader("/fake/path.toml", mock_loader)

        result = loader.load()

        self.assertIsInstance(result.notification, NotificationConfig)
        self.assertEqual(result.notification.title, "Test Notification")
        self.assertEqual(result.notification.message_success, "Success!")
        self.assertEqual(result.notification.icon_success, "test-ok")

    def test_load_with_notification_defaults(self):
        """Vérifie les valeurs par défaut des notifications."""
        config = {
            "service": {"exec_command": "/usr/bin/test"},
            "notification": {"enabled": True},
        }
        mock_loader = MockConfigLoader(config)
        loader = BashScriptConfigLoader("/fake/path.toml", mock_loader)

        result = loader.load()

        self.assertEqual(result.notification.title, "Task Update")
        self.assertEqual(
            result.notification.message_success, "Task completed successfully."
        )

    def test_load_without_notification_method(self):
        """Vérifie load_without_notification."""
        config = {
            "service": {"exec_command": "/usr/bin/test"},
            "notification": {"enabled": True, "title": "Test"},
        }
        mock_loader = MockConfigLoader(config)
        loader = BashScriptConfigLoader("/fake/path.toml", mock_loader)

        result = loader.load_without_notification()

        self.assertIsNone(result.notification)

    def test_has_notification_returns_true(self):
        """Vérifie has_notification retourne True si activé."""
        config = {
            "service": {"exec_command": "/usr/bin/test"},
            "notification": {"enabled": True},
        }
        mock_loader = MockConfigLoader(config)
        loader = BashScriptConfigLoader("/fake/path.toml", mock_loader)

        self.assertTrue(loader.has_notification())

    def test_has_notification_returns_false(self):
        """Vérifie has_notification retourne False si désactivé."""
        config = {
            "service": {"exec_command": "/usr/bin/test"},
            "notification": {"enabled": False},
        }
        mock_loader = MockConfigLoader(config)
        loader = BashScriptConfigLoader("/fake/path.toml", mock_loader)

        self.assertFalse(loader.has_notification())

    def test_load_raises_key_error_if_no_command(self):
        """Vérifie que load lève KeyError si pas de commande."""
        config = {
            "service": {"description": "No command"},
        }
        mock_loader = MockConfigLoader(config)
        loader = BashScriptConfigLoader("/fake/path.toml", mock_loader)

        with self.assertRaises(KeyError) as context:
            loader.load()

        self.assertIn("exec_command", str(context.exception))


class TestConfigFileLoaderBase(unittest.TestCase):
    """Tests pour les méthodes de base de ConfigFileLoader."""

    def test_config_property(self):
        """Vérifie la propriété config."""
        config = {"key": "value"}
        mock_loader = MockConfigLoader(config)
        loader = ServiceConfigLoader("/fake/path.toml", mock_loader)

        self.assertEqual(loader.config, config)

    def test_get_nested_value(self):
        """Vérifie _get_nested_value."""
        config = {
            "paths": {
                "log_file": "/var/log/app.log",
            },
            "service": {
                "description": "Test",
                "exec_start": "/usr/bin/test",
            },
        }
        mock_loader = MockConfigLoader(config)
        loader = ServiceConfigLoader("/fake/path.toml", mock_loader)

        result = loader._get_nested_value("paths", "log_file")

        self.assertEqual(result, "/var/log/app.log")

    def test_get_nested_value_with_default(self):
        """Vérifie _get_nested_value avec valeur par défaut."""
        config = {
            "service": {
                "description": "Test",
                "exec_start": "/usr/bin/test",
            }
        }
        mock_loader = MockConfigLoader(config)
        loader = ServiceConfigLoader("/fake/path.toml", mock_loader)

        result = loader._get_nested_value(
            "paths", "missing", default="/default/path"
        )

        self.assertEqual(result, "/default/path")

    def test_inherits_from_config_file_loader(self):
        """Vérifie que les loaders héritent de ConfigFileLoader."""
        config = {
            "service": {
                "description": "Test",
                "exec_start": "/usr/bin/test",
            }
        }
        mock_loader = MockConfigLoader(config)
        loader = ServiceConfigLoader("/fake/path.toml", mock_loader)

        self.assertIsInstance(loader, ConfigFileLoader)


if __name__ == "__main__":
    unittest.main()


class TestConfigLoadersBaseImport:
    """Vérifie que les loaders spécialisés sont importables depuis le paquet."""

    def test_import_service_loader(self) -> None:
        """ServiceConfigLoader est importable depuis config_loaders."""
        from linuxtools.systemd.config_loaders import (  # noqa: F401
            ServiceConfigLoader,
        )

    def test_import_mount_loader(self) -> None:
        """MountConfigLoader est importable depuis config_loaders."""
        from linuxtools.systemd.config_loaders import (  # noqa: F401
            MountConfigLoader,
        )

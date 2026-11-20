"""Tests pour les chargeurs de configuration systemd."""

import unittest
from pathlib import Path
from typing import Any, TypeVar, overload

import pytest

from linuxtools import (
    BashScriptConfig,
    MountConfig,
    NotificationConfig,
    ServiceConfig,
    TimerConfig,
)
from linuxtools.config import ConfigFileLoader, ConfigLoader
from linuxtools.systemd.config_loaders import (
    BashScriptConfigLoader,
    MountConfigLoader,
    ServiceConfigLoader,
    TimerConfigLoader,
)

# ConfigLoader.load() est désormais surchargé (schema=None -> dict,
# schema=type[_T] -> _T). mypy --strict exige que ce Mock reproduise
# le même triplet @overload/implémentation (erreur [override] sinon) :
# une signature unique, même large, n'est pas reconnue comme
# compatible avec une base surchargée par le vérificateur de
# surcharge de mypy.
_TSchema = TypeVar("_TSchema")


class MockConfigLoader(ConfigLoader):
    """Mock du ConfigLoader pour les tests."""

    def __init__(self, config: dict[str, Any]):
        self._config = config

    @overload
    def load(
        self,
        config_path: str | Path,
        schema: None = None,
    ) -> dict[str, Any]: ...

    @overload
    def load(
        self,
        config_path: str | Path,
        schema: type[_TSchema],
    ) -> _TSchema: ...

    def load(
        self,
        config_path: str | Path,
        schema: type | None = None,
    ) -> dict[str, Any] | Any:
        return self._config


class TestServiceConfigLoader(unittest.TestCase):
    """Tests pour ServiceConfigLoader."""

    def test_load_returns_service_config(self) -> None:
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

        assert isinstance(result, ServiceConfig)
        assert result.description == "Test Service"
        assert result.exec_start == "/usr/bin/test"
        assert result.type == "oneshot"

    def test_load_uses_defaults(self) -> None:
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

        assert result.type == "simple"
        assert result.restart == "no"
        assert result.wanted_by == "multi-user.target"

    def test_load_custom_section(self) -> None:
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

        assert result.description == "Custom Service"

    def test_load_raises_key_error_on_missing_section(self) -> None:
        """Vérifie que load lève KeyError si la section manque."""
        config: dict[str, Any] = {"other": {}}
        mock_loader = MockConfigLoader(config)
        loader = ServiceConfigLoader("/fake/path.toml", mock_loader)

        with pytest.raises(KeyError) as context:
            loader.load()

        assert "service" in str(context.value)

    def test_load_with_exec_override(self) -> None:
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

        assert result.exec_start == "/usr/bin/override"

    def test_load_all_service_fields(self) -> None:
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

        assert result.user == "appuser"
        assert result.group == "appgroup"
        assert result.working_directory == "/var/lib/app"
        assert result.environment == {"VAR1": "value1"}
        assert result.restart == "on-failure"
        assert result.restart_sec == 5
        assert result.wanted_by == "graphical.target"

    def test_load_from_json_path(self) -> None:
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

        assert result.description == "JSON Service"

    def test_load_reads_hardening_fields_from_toml(self) -> None:
        """Vérifie que load lit les champs de durcissement."""
        config = {
            "service": {
                "description": "Service durci",
                "exec_start": "/usr/local/bin/app report",
                "type": "oneshot",
                "no_new_privileges": True,
                "protect_system": "full",
                "protect_home": True,
                "private_tmp": True,
                "read_write_paths": ["/var/lib/app"],
            }
        }
        mock_loader = MockConfigLoader(config)
        loader = ServiceConfigLoader("/fake/path.toml", mock_loader)

        result = loader.load()

        assert result.no_new_privileges
        assert result.protect_system == "full"
        assert result.protect_home
        assert result.private_tmp
        assert result.read_write_paths == ("/var/lib/app",)

    def test_load_defaults_hardening_fields_when_absent(self) -> None:
        """Vérifie les valeurs par défaut du durcissement."""
        config = {
            "service": {
                "description": "Service simple",
                "exec_start": "/usr/bin/app",
            }
        }
        mock_loader = MockConfigLoader(config)
        loader = ServiceConfigLoader("/fake/path.toml", mock_loader)

        result = loader.load()

        assert not result.no_new_privileges
        assert result.protect_system == ""
        assert not result.protect_home
        assert not result.private_tmp
        assert result.read_write_paths == ()

    def test_load_with_exec_override_also_reads_hardening_fields(self) -> None:
        """Vérifie que l'override exec_start lit aussi le durcissement."""
        config = {
            "service": {
                "description": "Service durci",
                "exec_start": "/ignoré",
                "type": "oneshot",
                "no_new_privileges": True,
                "read_write_paths": ["/var/lib/app"],
            }
        }
        mock_loader = MockConfigLoader(config)
        loader = ServiceConfigLoader("/fake/path.toml", mock_loader)

        result = loader.load_with_exec_override("/usr/local/bin/app run")

        assert result.exec_start == "/usr/local/bin/app run"
        assert result.no_new_privileges
        assert result.read_write_paths == ("/var/lib/app",)


class TestTimerConfigLoader(unittest.TestCase):
    """Tests pour TimerConfigLoader."""

    def test_load_returns_timer_config(self) -> None:
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

        assert isinstance(result, TimerConfig)
        assert result.description == "Test Timer"
        assert result.unit == "test.service"
        assert result.on_calendar == "daily"
        assert result.persistent

    def test_load_uses_defaults(self) -> None:
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

        assert result.on_calendar == ""
        assert not result.persistent

    def test_load_for_service(self) -> None:
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

        assert result.unit == "my-service.service"

    def test_load_for_service_with_extension(self) -> None:
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

        assert result.unit == "my-service.service"

    def test_load_all_timer_fields(self) -> None:
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

        assert result.on_boot_sec == "5min"
        assert result.on_unit_active_sec == "1h"
        assert result.randomized_delay_sec == "30min"


class TestMountConfigLoader(unittest.TestCase):
    """Tests pour MountConfigLoader."""

    def test_load_returns_mount_config(self) -> None:
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

        assert isinstance(result, MountConfig)
        assert result.description == "NAS Share"
        assert result.what == "192.168.1.10:/share"
        assert result.where == "/media/nas"
        assert result.type == "nfs"

    def test_load_with_options(self) -> None:
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

        assert result.options == "username=user,password=pass"

    def test_load_multiple(self) -> None:
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

        assert len(results) == 2
        assert results[0].where == "/media/nas1"
        assert results[1].where == "/media/nas2"
        assert results[1].options == "ro"

    def test_load_multiple_raises_type_error_if_not_list(self) -> None:
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

        with pytest.raises(TypeError) as context:
            loader.load_multiple()

        assert "doit être une liste" in str(context.value)
        assert "mounts" in str(context.value)

    def test_load_multiple_message_contient_nom_section(self) -> None:
        """Vérifie que le nom de section est interpolé dans le message."""
        config = {"custom_mounts": {"not": "a list"}}
        mock_loader = MockConfigLoader(config)
        loader = MountConfigLoader("/fake/path.toml", mock_loader)

        with pytest.raises(TypeError) as context:
            loader.load_multiple(section="custom_mounts")

        assert "custom_mounts" in str(context.value)

    def test_load_with_automount_returns_settings_from_toml(self) -> None:
        """Vérifie que load_with_automount lit config et réglages."""
        config = {
            "mount": {
                "description": "NAS Share",
                "what": "192.168.1.10:/share",
                "where": "/media/nas",
                "type": "nfs",
                "options": "rw,soft",
                "with_automount": True,
                "automount_timeout_sec": 600,
            }
        }
        mock_loader = MockConfigLoader(config)
        loader = MountConfigLoader("/fake/path.toml", mock_loader)

        settings = loader.load_with_automount()

        assert isinstance(settings.config, MountConfig)
        assert settings.config.where == "/media/nas"
        assert settings.with_automount
        assert settings.timeout_sec == 600

    def test_load_with_automount_defaults_false_and_zero_when_absent(self) -> None:
        """Vérifie les défauts automount quand les clés sont absentes."""
        config = {
            "mount": {
                "description": "NAS",
                "what": "192.168.1.10:/share",
                "where": "/media/nas",
                "type": "nfs",
            }
        }
        mock_loader = MockConfigLoader(config)
        loader = MountConfigLoader("/fake/path.toml", mock_loader)

        settings = loader.load_with_automount()

        assert not settings.with_automount
        assert settings.timeout_sec == 0


class TestBashScriptConfigLoader(unittest.TestCase):
    """Tests pour BashScriptConfigLoader."""

    def test_load_returns_bash_script_config(self) -> None:
        """Vérifie que load retourne un BashScriptConfig."""
        config = {
            "service": {
                "exec_command": "/usr/bin/flatpak update -y",
            }
        }
        mock_loader = MockConfigLoader(config)
        loader = BashScriptConfigLoader("/fake/path.toml", mock_loader)

        result = loader.load()

        assert isinstance(result, BashScriptConfig)
        assert result.exec_command == "/usr/bin/flatpak update -y"

    def test_load_with_exec_start_fallback(self) -> None:
        """Vérifie que load utilise exec_start si exec_command absent."""
        config = {
            "service": {
                "exec_start": "/usr/bin/app",
            }
        }
        mock_loader = MockConfigLoader(config)
        loader = BashScriptConfigLoader("/fake/path.toml", mock_loader)

        result = loader.load()

        assert result.exec_command == "/usr/bin/app"

    def test_load_without_notification(self) -> None:
        """Vérifie le chargement sans notification."""
        config = {
            "service": {
                "exec_command": "/usr/bin/test",
            }
        }
        mock_loader = MockConfigLoader(config)
        loader = BashScriptConfigLoader("/fake/path.toml", mock_loader)

        result = loader.load()

        assert result.notification is None

    def test_load_with_notification_disabled(self) -> None:
        """Vérifie que notification disabled = pas de notification."""
        config = {
            "service": {"exec_command": "/usr/bin/test"},
            "notification": {"enabled": False},
        }
        mock_loader = MockConfigLoader(config)
        loader = BashScriptConfigLoader("/fake/path.toml", mock_loader)

        result = loader.load()

        assert result.notification is None

    def test_load_with_notification_enabled(self) -> None:
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

        assert isinstance(result.notification, NotificationConfig)
        assert result.notification.title == "Test Notification"
        assert result.notification.message_success == "Success!"
        assert result.notification.icon_success == "test-ok"

    def test_load_with_notification_defaults(self) -> None:
        """Vérifie les valeurs par défaut des notifications."""
        config = {
            "service": {"exec_command": "/usr/bin/test"},
            "notification": {"enabled": True},
        }
        mock_loader = MockConfigLoader(config)
        loader = BashScriptConfigLoader("/fake/path.toml", mock_loader)

        result = loader.load()

        assert isinstance(result.notification, NotificationConfig)
        assert result.notification.title == "Task Update"
        assert result.notification.message_success == "Task completed successfully."

    def test_load_without_notification_method(self) -> None:
        """Vérifie load_without_notification."""
        config = {
            "service": {"exec_command": "/usr/bin/test"},
            "notification": {"enabled": True, "title": "Test"},
        }
        mock_loader = MockConfigLoader(config)
        loader = BashScriptConfigLoader("/fake/path.toml", mock_loader)

        result = loader.load_without_notification()

        assert result.notification is None

    def test_has_notification_returns_true(self) -> None:
        """Vérifie has_notification retourne True si activé."""
        config = {
            "service": {"exec_command": "/usr/bin/test"},
            "notification": {"enabled": True},
        }
        mock_loader = MockConfigLoader(config)
        loader = BashScriptConfigLoader("/fake/path.toml", mock_loader)

        assert loader.has_notification()

    def test_has_notification_returns_false(self) -> None:
        """Vérifie has_notification retourne False si désactivé."""
        config = {
            "service": {"exec_command": "/usr/bin/test"},
            "notification": {"enabled": False},
        }
        mock_loader = MockConfigLoader(config)
        loader = BashScriptConfigLoader("/fake/path.toml", mock_loader)

        assert not loader.has_notification()

    def test_load_raises_key_error_if_no_command(self) -> None:
        """Vérifie que load lève KeyError si pas de commande."""
        config = {
            "service": {"description": "No command"},
        }
        mock_loader = MockConfigLoader(config)
        loader = BashScriptConfigLoader("/fake/path.toml", mock_loader)

        with pytest.raises(KeyError) as context:
            loader.load()

        assert "exec_command" in str(context.value)


class TestConfigFileLoaderBase(unittest.TestCase):
    """Tests pour les méthodes de base de ConfigFileLoader."""

    def test_config_property(self) -> None:
        """Vérifie la propriété config."""
        config = {"key": "value"}
        mock_loader = MockConfigLoader(config)
        loader = ServiceConfigLoader("/fake/path.toml", mock_loader)

        assert loader.config == config

    def test_get_nested_value(self) -> None:
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

        assert result == "/var/log/app.log"

    def test_get_nested_value_with_default(self) -> None:
        """Vérifie _get_nested_value avec valeur par défaut."""
        config = {
            "service": {
                "description": "Test",
                "exec_start": "/usr/bin/test",
            }
        }
        mock_loader = MockConfigLoader(config)
        loader = ServiceConfigLoader("/fake/path.toml", mock_loader)

        result = loader._get_nested_value("paths", "missing", default="/default/path")

        assert result == "/default/path"

    def test_inherits_from_config_file_loader(self) -> None:
        """Vérifie que les loaders héritent de ConfigFileLoader."""
        config = {
            "service": {
                "description": "Test",
                "exec_start": "/usr/bin/test",
            }
        }
        mock_loader = MockConfigLoader(config)
        loader = ServiceConfigLoader("/fake/path.toml", mock_loader)

        assert isinstance(loader, ConfigFileLoader)


if __name__ == "__main__":
    unittest.main()


class TestConfigLoadersBaseImport:
    """Vérifie que les loaders spécialisés sont importables depuis le paquet."""

    def test_import_service_loader(self) -> None:
        """ServiceConfigLoader est importable depuis config_loaders."""
        # import pour vérifier l'exportation, jamais utilisé
        from linuxtools.systemd.config_loaders import (  # noqa: F401
            ServiceConfigLoader,
        )

    def test_import_mount_loader(self) -> None:
        """MountConfigLoader est importable depuis config_loaders."""
        # import pour vérifier l'exportation, jamais utilisé
        from linuxtools.systemd.config_loaders import (  # noqa: F401
            MountConfigLoader,
        )

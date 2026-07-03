"""Tests pour le module systemd.scheduled_task."""

import unittest
from unittest.mock import Mock

from linuxtools import (
    BashScriptConfig,
    Logger,
    SystemdScheduledTaskInstaller,
)
from linuxtools.systemd import ServiceConfig, TimerConfig


class TestSystemdScheduledTaskInstaller(unittest.TestCase):
    """Tests pour la classe SystemdScheduledTaskInstaller."""

    def setUp(self):
        """Crée les mocks et configurations nécessaires."""
        self.mock_logger = Mock(spec=Logger)
        self.mock_script_installer = Mock()
        self.mock_service_manager = Mock()
        self.mock_timer_manager = Mock()

        self.installer = SystemdScheduledTaskInstaller(
            logger=self.mock_logger,
            script_installer=self.mock_script_installer,
            service_manager=self.mock_service_manager,
            timer_manager=self.mock_timer_manager,
        )

        self.task_name = "test-task"
        self.script_path = "/usr/local/bin/test.sh"
        self.script_config = BashScriptConfig(exec_command="echo test")
        self.service_config = ServiceConfig(
            description="Test Service",
            exec_start=self.script_path,
            type="oneshot",
        )
        self.timer_config = TimerConfig(
            description="Test Timer",
            unit="test-task.service",
            on_calendar="daily",
            persistent=True,
        )

    def _setup_all_success(self):
        """Configure tous les mocks pour retourner True."""
        self.mock_script_installer.install.return_value = True
        self.mock_service_manager.install_service_unit_with_name \
            .return_value = True
        self.mock_timer_manager.install_timer_unit.return_value = True
        self.mock_timer_manager.enable_timer.return_value = True

    def test_install_calls_script_installer(self):
        """Vérifie que install appelle le script_installer."""
        self._setup_all_success()

        self.installer.install(
            self.task_name,
            self.script_path,
            self.script_config,
            self.service_config,
            self.timer_config,
        )

        self.mock_script_installer.install.assert_called_once_with(
            self.script_path, self.script_config
        )

    def test_install_calls_service_manager(self):
        """Vérifie que install appelle le service_manager."""
        self._setup_all_success()

        self.installer.install(
            self.task_name,
            self.script_path,
            self.script_config,
            self.service_config,
            self.timer_config,
        )

        self.mock_service_manager.install_service_unit_with_name \
            .assert_called_once_with(self.task_name, self.service_config)

    def test_install_calls_timer_manager_install(self):
        """Vérifie que install appelle timer_manager.install_timer_unit."""
        self._setup_all_success()

        self.installer.install(
            self.task_name,
            self.script_path,
            self.script_config,
            self.service_config,
            self.timer_config,
        )

        self.mock_timer_manager.install_timer_unit.assert_called_once_with(
            self.timer_config
        )

    def test_install_calls_timer_manager_enable(self):
        """Vérifie que install appelle timer_manager.enable_timer."""
        self._setup_all_success()

        self.installer.install(
            self.task_name,
            self.script_path,
            self.script_config,
            self.service_config,
            self.timer_config,
        )

        self.mock_timer_manager.enable_timer.assert_called_once_with(
            self.task_name
        )

    def test_install_returns_true_on_success(self):
        """Vérifie que install retourne True en cas de succès."""
        self._setup_all_success()

        result = self.installer.install(
            self.task_name,
            self.script_path,
            self.script_config,
            self.service_config,
            self.timer_config,
        )

        self.assertTrue(result)

    def test_install_logs_success(self):
        """Vérifie que install log le succès."""
        self._setup_all_success()

        self.installer.install(
            self.task_name,
            self.script_path,
            self.script_config,
            self.service_config,
            self.timer_config,
        )

        self.mock_logger.log_info.assert_called()

    def test_install_fails_on_script_error(self):
        """Vérifie que install échoue si le script échoue."""
        self.mock_script_installer.install.return_value = False

        result = self.installer.install(
            self.task_name,
            self.script_path,
            self.script_config,
            self.service_config,
            self.timer_config,
        )

        self.assertFalse(result)
        self.mock_service_manager.install_service_unit_with_name \
            .assert_not_called()

    def test_install_fails_on_service_error(self):
        """Vérifie que install échoue si le service échoue."""
        self.mock_script_installer.install.return_value = True
        self.mock_service_manager.install_service_unit_with_name \
            .return_value = False

        result = self.installer.install(
            self.task_name,
            self.script_path,
            self.script_config,
            self.service_config,
            self.timer_config,
        )

        self.assertFalse(result)
        self.mock_timer_manager.install_timer_unit.assert_not_called()

    def test_install_fails_on_timer_install_error(self):
        """Vérifie que install échoue si l'installation du timer échoue."""
        self.mock_script_installer.install.return_value = True
        self.mock_service_manager.install_service_unit_with_name \
            .return_value = True
        self.mock_timer_manager.install_timer_unit.return_value = False

        result = self.installer.install(
            self.task_name,
            self.script_path,
            self.script_config,
            self.service_config,
            self.timer_config,
        )

        self.assertFalse(result)
        self.mock_timer_manager.enable_timer.assert_not_called()

    def test_install_fails_on_timer_enable_error(self):
        """Vérifie que install échoue si l'activation du timer échoue."""
        self.mock_script_installer.install.return_value = True
        self.mock_service_manager.install_service_unit_with_name \
            .return_value = True
        self.mock_timer_manager.install_timer_unit.return_value = True
        self.mock_timer_manager.enable_timer.return_value = False

        result = self.installer.install(
            self.task_name,
            self.script_path,
            self.script_config,
            self.service_config,
            self.timer_config,
        )

        self.assertFalse(result)

    def test_install_logs_error_on_script_failure(self):
        """Vérifie que install log l'erreur si le script échoue."""
        self.mock_script_installer.install.return_value = False

        self.installer.install(
            self.task_name,
            self.script_path,
            self.script_config,
            self.service_config,
            self.timer_config,
        )

        self.mock_logger.log_error.assert_called()

    def test_install_logs_error_on_service_failure(self):
        """Vérifie que install log l'erreur si le service échoue."""
        self.mock_script_installer.install.return_value = True
        self.mock_service_manager.install_service_unit_with_name \
            .return_value = False

        self.installer.install(
            self.task_name,
            self.script_path,
            self.script_config,
            self.service_config,
            self.timer_config,
        )

        self.mock_logger.log_error.assert_called()


if __name__ == "__main__":
    unittest.main()

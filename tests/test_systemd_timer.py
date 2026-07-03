"""Tests pour le module systemd.timer."""

import json
from unittest.mock import MagicMock

import pytest

from linuxtools.systemd.base import TimerConfig
from linuxtools.systemd.timer import LinuxTimerUnitManager
from linuxtools.systemd.user_timer import LinuxUserTimerUnitManager


class TestTimerConfig:
    """Tests pour la dataclass TimerConfig."""

    def test_timer_name_extracts_from_service(self):
        """Vérifie l'extraction du nom du timer depuis l'unité cible."""
        config = TimerConfig(
            description="Test",
            unit="backup.service"
        )
        assert config.timer_name == "backup"

    def test_timer_name_handles_complex_unit_names(self):
        """Vérifie l'extraction avec des noms d'unités complexes."""
        config = TimerConfig(
            description="Test",
            unit="my-backup-task.service"
        )
        assert config.timer_name == "my-backup-task"

    def test_post_init_raises_on_empty_unit(self):
        """Vérifie que __post_init__ lève une erreur si unit est vide."""
        with pytest.raises(ValueError, match="'unit' est requis"):
            TimerConfig(description="Test", unit="")


class TestTimerConfigToUnitFile:
    """Tests pour TimerConfig.to_unit_file()."""

    def test_basic_timer_contains_required_sections(self):
        """Vérifie que le fichier .timer contient toutes les sections."""
        config = TimerConfig(
            description="Sauvegarde quotidienne",
            unit="backup.service",
            on_calendar="daily"
        )

        result = config.to_unit_file()

        assert "[Unit]" in result
        assert "Description=Sauvegarde quotidienne" in result
        assert "[Timer]" in result
        assert "Unit=backup.service" in result
        assert "OnCalendar=daily" in result
        assert "[Install]" in result
        assert "WantedBy=timers.target" in result

    def test_timer_with_on_boot_sec(self):
        """Vérifie l'inclusion de OnBootSec."""
        config = TimerConfig(
            description="Démarrage différé",
            unit="startup-task.service",
            on_boot_sec="5min"
        )

        result = config.to_unit_file()

        assert "OnBootSec=5min" in result

    def test_timer_with_on_unit_active_sec(self):
        """Vérifie l'inclusion de OnUnitActiveSec."""
        config = TimerConfig(
            description="Tâche récurrente",
            unit="recurring.service",
            on_unit_active_sec="1h"
        )

        result = config.to_unit_file()

        assert "OnUnitActiveSec=1h" in result

    def test_timer_with_persistent_true(self):
        """Vérifie l'inclusion de Persistent=true."""
        config = TimerConfig(
            description="Timer persistant",
            unit="persistent.service",
            on_calendar="weekly",
            persistent=True
        )

        result = config.to_unit_file()

        assert "Persistent=true" in result

    def test_timer_with_persistent_false_omits_line(self):
        """Vérifie l'absence de Persistent quand False."""
        config = TimerConfig(
            description="Timer non persistant",
            unit="non-persistent.service",
            on_calendar="daily",
            persistent=False
        )

        result = config.to_unit_file()

        assert "Persistent" not in result

    def test_timer_with_randomized_delay(self):
        """Vérifie l'inclusion de RandomizedDelaySec."""
        config = TimerConfig(
            description="Timer avec délai aléatoire",
            unit="random.service",
            on_calendar="hourly",
            randomized_delay_sec="15min"
        )

        result = config.to_unit_file()

        assert "RandomizedDelaySec=15min" in result

    def test_timer_without_optional_fields_omits_them(self):
        """Vérifie l'absence des champs optionnels non définis."""
        config = TimerConfig(
            description="Timer minimal",
            unit="minimal.service"
        )

        result = config.to_unit_file()

        assert "OnCalendar=" not in result
        assert "OnBootSec=" not in result
        assert "OnUnitActiveSec=" not in result
        assert "Persistent" not in result
        assert "RandomizedDelaySec=" not in result

    def test_timer_with_all_options(self):
        """Vérifie un timer avec toutes les options."""
        config = TimerConfig(
            description="Timer complet",
            unit="complete.service",
            on_calendar="*-*-* 06:00:00",
            on_boot_sec="10min",
            on_unit_active_sec="30min",
            persistent=True,
            randomized_delay_sec="5min"
        )

        result = config.to_unit_file()

        assert "OnCalendar=*-*-* 06:00:00" in result
        assert "OnBootSec=10min" in result
        assert "OnUnitActiveSec=30min" in result
        assert "Persistent=true" in result
        assert "RandomizedDelaySec=5min" in result


class TestLinuxTimerListTimers:
    """Tests pour LinuxTimerUnitManager.list_timers."""

    def _make_manager(self) -> LinuxTimerUnitManager:
        """Crée un manager avec des mocks."""
        logger = MagicMock()
        executor = MagicMock()
        return LinuxTimerUnitManager(logger, executor)

    def test_list_timers_json_valide(self):
        """Vérifie le parsing d'une réponse JSON valide."""
        data = [
            {"unit": "backup.timer", "activates": "backup.service",
             "next": "Mon 2026-01-01", "left": "1h",
             "last": "Sun 2025-12-31", "passed": "23h"}
        ]
        manager = self._make_manager()
        manager.executor._run_systemctl.return_value = MagicMock(
            returncode=0, stdout=json.dumps(data), stderr=""
        )
        result = manager.list_timers()
        assert len(result) == 1
        assert result[0]["unit"] == "backup.timer"
        assert result[0]["activates"] == "backup.service"

    def test_list_timers_json_vide(self):
        """Vérifie le parsing d'une liste JSON vide."""
        manager = self._make_manager()
        manager.executor._run_systemctl.return_value = MagicMock(
            returncode=0, stdout="[]", stderr=""
        )
        result = manager.list_timers()
        assert result == []

    def test_list_timers_fallback_texte(self):
        """Vérifie le fallback texte si JSON non supporté."""
        fail_result = MagicMock(
            returncode=1, stdout="",
            stderr="unknown option '--output=json'"
        )
        text_output = (
            "NEXT LEFT LAST PASSED UNIT ACTIVATES\n"
            "Mon 2026-01-01 1h ago Sun backup.timer backup.service\n"
        )
        text_result = MagicMock(returncode=0, stdout=text_output, stderr="")
        manager = self._make_manager()
        manager.executor._run_systemctl.side_effect = [
            fail_result, text_result
        ]
        result = manager.list_timers()
        assert len(result) == 1
        assert result[0]["unit"] == "backup.timer"

    def test_list_timers_erreur_subprocess(self):
        """Vérifie que RuntimeError est levée sur erreur."""
        manager = self._make_manager()
        manager.executor._run_systemctl.return_value = MagicMock(
            returncode=1, stdout="", stderr="Failed to connect to bus"
        )
        with pytest.raises(RuntimeError, match="Erreur systemctl"):
            manager.list_timers()

    def test_list_timers_systemctl_introuvable(self):
        """Vérifie RuntimeError si systemctl n'existe pas."""
        manager = self._make_manager()
        manager.executor._run_systemctl.side_effect = FileNotFoundError(
            "systemctl"
        )
        with pytest.raises(RuntimeError, match="Impossible"):
            manager.list_timers()

    def test_list_timers_os_error(self):
        """Vérifie RuntimeError sur OSError."""
        manager = self._make_manager()
        manager.executor._run_systemctl.side_effect = OSError(
            "permission denied"
        )
        with pytest.raises(RuntimeError, match="Impossible"):
            manager.list_timers()


class TestLinuxUserTimerListTimers:
    """Tests pour LinuxUserTimerUnitManager.list_timers."""

    def _make_manager(self) -> LinuxUserTimerUnitManager:
        """Crée un manager utilisateur avec des mocks."""
        logger = MagicMock()
        executor = MagicMock()
        return LinuxUserTimerUnitManager(logger, executor)

    def test_list_timers_json_valide(self):
        """Vérifie le parsing d'une réponse JSON valide."""
        data = [
            {"unit": "backup.timer", "activates": "backup.service",
             "next": "", "left": "", "last": "", "passed": ""}
        ]
        manager = self._make_manager()
        manager.executor._run_systemctl.return_value = MagicMock(
            returncode=0, stdout=json.dumps(data), stderr=""
        )
        result = manager.list_timers()
        assert len(result) == 1
        assert result[0]["unit"] == "backup.timer"

    def test_list_timers_json_vide(self):
        """Vérifie le parsing d'une liste JSON vide."""
        manager = self._make_manager()
        manager.executor._run_systemctl.return_value = MagicMock(
            returncode=0, stdout="[]", stderr=""
        )
        result = manager.list_timers()
        assert result == []

    def test_list_timers_fallback_texte(self):
        """Vérifie le fallback texte si JSON non supporté."""
        fail_result = MagicMock(
            returncode=1, stdout="",
            stderr="unknown option '--output=json'"
        )
        text_output = (
            "NEXT LEFT LAST PASSED UNIT ACTIVATES\n"
            "Mon 2026-01-01 1h ago Sun user.timer user.service\n"
        )
        text_result = MagicMock(returncode=0, stdout=text_output, stderr="")
        manager = self._make_manager()
        manager.executor._run_systemctl.side_effect = [
            fail_result, text_result
        ]
        result = manager.list_timers()
        assert len(result) == 1
        assert result[0]["unit"] == "user.timer"

    def test_list_timers_erreur_subprocess(self):
        """Vérifie que RuntimeError est levée sur erreur."""
        manager = self._make_manager()
        manager.executor._run_systemctl.return_value = MagicMock(
            returncode=1, stdout="", stderr="Failed to connect to bus"
        )
        with pytest.raises(RuntimeError, match="Erreur systemctl"):
            manager.list_timers()

    def test_list_timers_systemctl_introuvable(self):
        """Vérifie RuntimeError si systemctl n'existe pas."""
        manager = self._make_manager()
        manager.executor._run_systemctl.side_effect = FileNotFoundError(
            "systemctl"
        )
        with pytest.raises(RuntimeError, match="Impossible"):
            manager.list_timers()

    def test_list_timers_os_error(self):
        """Vérifie RuntimeError sur OSError."""
        manager = self._make_manager()
        manager.executor._run_systemctl.side_effect = OSError(
            "permission denied"
        )
        with pytest.raises(RuntimeError, match="Impossible"):
            manager.list_timers()


class TestLinuxTimerUnitManagerSuccessPaths:
    """Tests pour les chemins succès de LinuxTimerUnitManager."""

    def _make_manager(self, tmp_path):
        """Crée un manager avec mocks et répertoire temporaire."""
        logger = MagicMock()
        executor = MagicMock()
        executor.reload_systemd.return_value = True
        executor.enable_unit.return_value = True
        executor.disable_unit.return_value = True
        executor.get_status.return_value = "active"
        manager = LinuxTimerUnitManager(logger, executor)
        manager.SYSTEMD_UNIT_PATH = str(tmp_path)
        return manager, logger, executor

    def test_install_timer_unit_succes(self, tmp_path):
        """install_timer_unit() retourne True en cas de succès."""
        manager, logger, _ = self._make_manager(tmp_path)
        config = TimerConfig(
            description="Sauvegarde quotidienne",
            unit="backup.service",
            on_calendar="daily"
        )
        result = manager.install_timer_unit(config)
        assert result is True
        logger.log_info.assert_called()

    def test_install_timer_unit_reload_echoue(self, tmp_path):
        """install_timer_unit() retourne False si reload_systemd échoue."""
        manager, _, executor = self._make_manager(tmp_path)
        executor.reload_systemd.return_value = False
        config = TimerConfig(
            description="Test",
            unit="backup.service",
            on_calendar="daily"
        )
        result = manager.install_timer_unit(config)
        assert result is False

    def test_enable_timer_appelle_executor(self, tmp_path):
        """enable_timer() appelle executor.enable_unit()."""
        manager, _, executor = self._make_manager(tmp_path)
        result = manager.enable_timer("backup")
        assert result is True
        executor.enable_unit.assert_called_once_with("backup.timer")

    def test_disable_timer_appelle_executor(self, tmp_path):
        """disable_timer() appelle executor.disable_unit()."""
        manager, _, executor = self._make_manager(tmp_path)
        result = manager.disable_timer("backup")
        assert result is True
        executor.disable_unit.assert_called_once_with(
            "backup.timer", ignore_errors=False
        )

    def test_remove_timer_unit_succes(self, tmp_path):
        """remove_timer_unit() retourne True en cas de succès."""
        timer_file = tmp_path / "backup.timer"
        timer_file.write_text("[Unit]\n")
        manager, logger, _ = self._make_manager(tmp_path)
        result = manager.remove_timer_unit("backup")
        assert result is True
        logger.log_info.assert_called()

    def test_get_timer_status_retourne_statut(self, tmp_path):
        """get_timer_status() retourne le statut via l'executor."""
        manager, _, executor = self._make_manager(tmp_path)
        status = manager.get_timer_status("backup")
        assert status == "active"
        executor.get_status.assert_called_once_with("backup.timer")

    def test_is_timer_active_retourne_true(self, tmp_path):
        """is_timer_active() retourne True si statut == 'active'."""
        manager, _, executor = self._make_manager(tmp_path)
        executor.get_status.return_value = "active"
        assert manager.is_timer_active("backup") is True

    def test_is_timer_active_retourne_false(self, tmp_path):
        """is_timer_active() retourne False si inactif."""
        manager, _, executor = self._make_manager(tmp_path)
        executor.get_status.return_value = "inactive"
        assert manager.is_timer_active("backup") is False

    def test_list_timers_json_invalide_fallback(self):
        """list_timers() fallback texte si JSON invalide."""
        json_fail = MagicMock(returncode=0, stdout="invalid-json", stderr="")
        text_output = (
            "NEXT LEFT LAST PASSED UNIT ACTIVATES\n"
            "Mon 2026 1h ago Sun cron.timer cron.service\n"
        )
        text_result = MagicMock(returncode=0, stdout=text_output, stderr="")
        executor = MagicMock()
        executor._run_systemctl.side_effect = [json_fail, text_result]
        manager = LinuxTimerUnitManager(MagicMock(), executor)
        result = manager.list_timers()
        assert len(result) == 1
        assert result[0]["unit"] == "cron.timer"

    def test_list_timers_fallback_texte_os_error(self):
        """_list_timers_text_fallback lève RuntimeError si OSError."""
        fail_result = MagicMock(
            returncode=1, stdout="", stderr="unknown option '--output=json'"
        )
        executor = MagicMock()
        executor._run_systemctl.side_effect = [
            fail_result, OSError("permission denied")
        ]
        manager = LinuxTimerUnitManager(MagicMock(), executor)
        with pytest.raises(RuntimeError, match="Impossible"):
            manager.list_timers()

    def test_list_timers_fallback_texte_returncode_nonzero(self):
        """_list_timers_text_fallback lève RuntimeError si returncode != 0."""
        fail_result = MagicMock(
            returncode=1, stdout="", stderr="unknown option '--output=json'"
        )
        text_fail = MagicMock(
            returncode=1, stdout="", stderr="Failed to connect"
        )
        executor = MagicMock()
        executor._run_systemctl.side_effect = [fail_result, text_fail]
        manager = LinuxTimerUnitManager(MagicMock(), executor)
        with pytest.raises(RuntimeError, match="Erreur systemctl"):
            manager.list_timers()


class TestLinuxUserTimerUnitManagerSuccessPaths:
    """Tests pour les chemins succès de LinuxUserTimerUnitManager."""

    def _make_manager(self, tmp_path):
        """Crée un manager utilisateur avec mocks."""
        logger = MagicMock()
        executor = MagicMock()
        executor.reload_systemd.return_value = True
        executor.enable_unit.return_value = True
        executor.disable_unit.return_value = True
        executor.get_status.return_value = "active"
        manager = LinuxUserTimerUnitManager(logger, executor)
        manager._unit_path = str(tmp_path)
        return manager, logger, executor

    def test_install_timer_unit_rejette_caractere_controle(self, tmp_path):
        """install_timer_unit() lève ValueError si description contient \\n."""
        manager, _, _ = self._make_manager(tmp_path)
        config = TimerConfig(
            description="Timer\nUnit=evil.service",
            unit="backup.service",
            on_calendar="daily"
        )
        with pytest.raises(ValueError, match="contrôle"):
            manager.install_timer_unit(config)

    def test_install_timer_unit_succes(self, tmp_path):
        """install_timer_unit() retourne True en cas de succès."""
        manager, logger, _ = self._make_manager(tmp_path)
        config = TimerConfig(
            description="Timer test",
            unit="backup.service",
            on_calendar="weekly"
        )
        result = manager.install_timer_unit(config)
        assert result is True
        logger.log_info.assert_called()

    def test_install_timer_unit_reload_echoue(self, tmp_path):
        """install_timer_unit() retourne False si reload_systemd échoue."""
        manager, _, executor = self._make_manager(tmp_path)
        executor.reload_systemd.return_value = False
        config = TimerConfig(
            description="Test",
            unit="backup.service"
        )
        result = manager.install_timer_unit(config)
        assert result is False

    def test_enable_timer_appelle_executor(self, tmp_path):
        """enable_timer() appelle executor.enable_unit()."""
        manager, _, executor = self._make_manager(tmp_path)
        result = manager.enable_timer("backup")
        assert result is True
        executor.enable_unit.assert_called_once_with("backup.timer")

    def test_disable_timer_appelle_executor(self, tmp_path):
        """disable_timer() appelle executor.disable_unit()."""
        manager, _, executor = self._make_manager(tmp_path)
        result = manager.disable_timer("backup")
        assert result is True
        executor.disable_unit.assert_called_once_with(
            "backup.timer", ignore_errors=False
        )

    def test_remove_timer_unit_succes(self, tmp_path):
        """remove_timer_unit() retourne True en cas de succès."""
        timer_file = tmp_path / "backup.timer"
        timer_file.write_text("[Unit]\n")
        manager, logger, _ = self._make_manager(tmp_path)
        result = manager.remove_timer_unit("backup")
        assert result is True
        logger.log_info.assert_called()

    def test_get_timer_status_retourne_statut(self, tmp_path):
        """get_timer_status() retourne le statut via l'executor."""
        manager, _, executor = self._make_manager(tmp_path)
        status = manager.get_timer_status("backup")
        assert status == "active"
        executor.get_status.assert_called_once_with("backup.timer")

    def test_is_timer_active_retourne_true(self, tmp_path):
        """is_timer_active() retourne True si actif."""
        manager, _, executor = self._make_manager(tmp_path)
        executor.get_status.return_value = "active"
        assert manager.is_timer_active("backup") is True

    def test_is_timer_active_retourne_false(self, tmp_path):
        """is_timer_active() retourne False si inactif."""
        manager, _, executor = self._make_manager(tmp_path)
        executor.get_status.return_value = "inactive"
        assert manager.is_timer_active("backup") is False

    def test_list_timers_json_invalide_fallback(self):
        """list_timers() fallback texte si JSON invalide."""
        json_fail = MagicMock(returncode=0, stdout="not-json", stderr="")
        text_output = (
            "NEXT LEFT LAST PASSED UNIT ACTIVATES\n"
            "Mon 2026 1h ago Sun user.timer user.service\n"
        )
        text_result = MagicMock(returncode=0, stdout=text_output, stderr="")
        executor = MagicMock()
        executor._run_systemctl.side_effect = [json_fail, text_result]
        manager = LinuxUserTimerUnitManager(MagicMock(), executor)
        result = manager.list_timers()
        assert len(result) == 1
        assert result[0]["unit"] == "user.timer"

    def test_list_timers_fallback_texte_os_error(self):
        """_list_timers_text_fallback lève RuntimeError si OSError."""
        fail_result = MagicMock(
            returncode=1, stdout="", stderr="unknown option '--output=json'"
        )
        executor = MagicMock()
        executor._run_systemctl.side_effect = [
            fail_result, OSError("permission denied")
        ]
        manager = LinuxUserTimerUnitManager(MagicMock(), executor)
        with pytest.raises(RuntimeError, match="Impossible"):
            manager.list_timers()

    def test_list_timers_fallback_texte_returncode_nonzero(self):
        """_list_timers_text_fallback lève RuntimeError si returncode != 0."""
        fail_result = MagicMock(
            returncode=1, stdout="", stderr="unknown option '--output=json'"
        )
        text_fail = MagicMock(
            returncode=1, stdout="", stderr="Failed to connect"
        )
        executor = MagicMock()
        executor._run_systemctl.side_effect = [fail_result, text_fail]
        manager = LinuxUserTimerUnitManager(MagicMock(), executor)
        with pytest.raises(RuntimeError, match="Erreur systemctl"):
            manager.list_timers()


class TestRemoveTimerLogWarning:
    """Tests pour log_warning dans remove_timer_unit() si disable échoue."""

    def _make_manager(self, tmp_path):
        """Crée un manager avec mocks."""
        logger = MagicMock()
        executor = MagicMock()
        executor.reload_systemd.return_value = True
        executor.disable_unit.return_value = True
        manager = LinuxTimerUnitManager(logger, executor)
        manager.SYSTEMD_UNIT_PATH = str(tmp_path)
        return manager, logger, executor

    def _make_user_manager(self, tmp_path):
        """Crée un manager utilisateur avec mocks."""
        logger = MagicMock()
        executor = MagicMock()
        executor.reload_systemd.return_value = True
        executor.disable_unit.return_value = True
        manager = LinuxUserTimerUnitManager(logger, executor)
        manager._unit_path = str(tmp_path)
        return manager, logger, executor

    def test_remove_timer_unit_logue_warning_si_disable_echoue(
        self, tmp_path
    ):
        """remove_timer_unit() logue un warning si disable échoue."""
        manager, logger, executor = self._make_manager(tmp_path)
        executor.disable_unit.return_value = False
        timer_file = tmp_path / "backup.timer"
        timer_file.write_text("[Unit]\n")

        result = manager.remove_timer_unit("backup")

        assert result is True
        logger.log_warning.assert_called_once()
        assert "backup" in logger.log_warning.call_args[0][0]

    def test_remove_timer_unit_pas_de_warning_si_disable_reussit(
        self, tmp_path
    ):
        """remove_timer_unit() ne logue pas de warning si disable réussit."""
        manager, logger, executor = self._make_manager(tmp_path)
        executor.disable_unit.return_value = True
        timer_file = tmp_path / "backup.timer"
        timer_file.write_text("[Unit]\n")

        manager.remove_timer_unit("backup")

        logger.log_warning.assert_not_called()

    def test_user_remove_timer_unit_logue_warning_si_disable_echoue(
        self, tmp_path
    ):
        """LinuxUserTimerUnitManager: log_warning si disable échoue."""
        manager, logger, executor = self._make_user_manager(tmp_path)
        executor.disable_unit.return_value = False
        timer_file = tmp_path / "backup.timer"
        timer_file.write_text("[Unit]\n")

        result = manager.remove_timer_unit("backup")

        assert result is True
        logger.log_warning.assert_called_once()

    def test_user_remove_timer_unit_pas_de_warning_si_disable_reussit(
        self, tmp_path
    ):
        """LinuxUserTimerUnitManager: pas de warning si disable réussit."""
        manager, logger, executor = self._make_user_manager(tmp_path)
        executor.disable_unit.return_value = True
        timer_file = tmp_path / "backup.timer"
        timer_file.write_text("[Unit]\n")

        manager.remove_timer_unit("backup")

        logger.log_warning.assert_not_called()


class TestTimerToUnitFileSecurite:
    """Tests de sécurité : rejet des caractères de contrôle dans TimerConfig."""

    def test_rejette_newline_dans_description(self):
        """to_unit_file lève ValueError si description contient \\n."""
        from linuxtools.systemd.base import TimerConfig
        config = TimerConfig(
            description="timer\nExecStart=/bin/evil",
            unit="backup.service",
            on_calendar="daily",
        )
        with pytest.raises(ValueError, match="contrôle"):
            config.to_unit_file()

    def test_rejette_newline_dans_on_calendar(self):
        """to_unit_file lève ValueError si on_calendar contient \\n."""
        from linuxtools.systemd.base import TimerConfig
        config = TimerConfig(
            description="timer",
            unit="backup.service",
            on_calendar="daily\nExecStart=/bin/evil",
        )
        with pytest.raises(ValueError, match="contrôle"):
            config.to_unit_file()

    def test_rejette_newline_dans_unit(self):
        """to_unit_file lève ValueError si unit contient \\n."""
        from linuxtools.systemd.base import TimerConfig
        config = TimerConfig(
            description="timer",
            unit="backup.service\nExecStart=/bin/evil",
            on_calendar="daily",
        )
        with pytest.raises(ValueError, match="contrôle"):
            config.to_unit_file()

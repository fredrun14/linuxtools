"""Tests pour le module systemd.service."""

import os
import shutil
import tempfile
from unittest.mock import MagicMock

import pytest

from linuxtools.systemd.base import ServiceConfig
from linuxtools.systemd.service import LinuxServiceUnitManager
from linuxtools.systemd.user_service import LinuxUserServiceUnitManager


class TestServiceConfig:
    """Tests pour la dataclass ServiceConfig."""

    def test_post_init_raises_on_empty_exec_start(self):
        """Vérifie que __post_init__ lève une erreur si exec_start est vide."""
        with pytest.raises(ValueError, match="'exec_start' est requis"):
            ServiceConfig(description="Test", exec_start="")

    def test_default_values(self):
        """Vérifie les valeurs par défaut."""
        config = ServiceConfig(
            description="Test",
            exec_start="/usr/bin/test"
        )

        assert config.type == "simple"
        assert config.user == ""
        assert config.group == ""
        assert config.working_directory == ""
        assert config.environment == {}
        assert config.restart == "no"
        assert config.restart_sec == 0
        assert config.wanted_by == "multi-user.target"


class TestServiceConfigToUnitFile:
    """Tests pour ServiceConfig.to_unit_file()."""

    def test_basic_service_contains_required_sections(self):
        """Vérifie que le fichier .service contient toutes les sections."""
        config = ServiceConfig(
            description="Mon service",
            exec_start="/usr/bin/my-daemon"
        )

        result = config.to_unit_file()

        assert "[Unit]" in result
        assert "Description=Mon service" in result
        assert "[Service]" in result
        assert "Type=simple" in result
        assert "ExecStart=/usr/bin/my-daemon" in result
        assert "[Install]" in result
        assert "WantedBy=multi-user.target" in result

    def test_service_with_user_and_group(self):
        """Vérifie l'inclusion de User et Group."""
        config = ServiceConfig(
            description="Service avec utilisateur",
            exec_start="/usr/bin/daemon",
            user="www-data",
            group="www-data"
        )

        result = config.to_unit_file()

        assert "User=www-data" in result
        assert "Group=www-data" in result

    def test_service_with_working_directory(self):
        """Vérifie l'inclusion de WorkingDirectory."""
        config = ServiceConfig(
            description="Service avec répertoire",
            exec_start="/usr/bin/daemon",
            working_directory="/var/lib/myapp"
        )

        result = config.to_unit_file()

        assert "WorkingDirectory=/var/lib/myapp" in result

    def test_service_with_environment_variables(self):
        """Vérifie l'inclusion des variables d'environnement."""
        config = ServiceConfig(
            description="Service avec env",
            exec_start="/usr/bin/daemon",
            environment={"HOME": "/var/lib/myapp", "PATH": "/usr/bin"}
        )

        result = config.to_unit_file()

        assert "Environment=HOME=/var/lib/myapp" in result
        assert "Environment=PATH=/usr/bin" in result

    def test_service_with_restart_policy(self):
        """Vérifie l'inclusion de Restart."""
        config = ServiceConfig(
            description="Service avec redémarrage",
            exec_start="/usr/bin/daemon",
            restart="on-failure"
        )

        result = config.to_unit_file()

        assert "Restart=on-failure" in result

    def test_service_with_restart_sec(self):
        """Vérifie l'inclusion de RestartSec."""
        config = ServiceConfig(
            description="Service avec délai",
            exec_start="/usr/bin/daemon",
            restart="always",
            restart_sec=10
        )

        result = config.to_unit_file()

        assert "Restart=always" in result
        assert "RestartSec=10" in result

    def test_service_restart_no_omits_restart_lines(self):
        """Vérifie l'absence de Restart quand restart='no'."""
        config = ServiceConfig(
            description="Service sans redémarrage",
            exec_start="/usr/bin/daemon",
            restart="no",
            restart_sec=10
        )

        result = config.to_unit_file()

        assert "Restart=" not in result
        assert "RestartSec=" not in result

    def test_service_with_custom_wanted_by(self):
        """Vérifie l'utilisation d'un WantedBy personnalisé."""
        config = ServiceConfig(
            description="Service graphique",
            exec_start="/usr/bin/gui-app",
            wanted_by="graphical.target"
        )

        result = config.to_unit_file()

        assert "WantedBy=graphical.target" in result

    def test_service_type_oneshot(self):
        """Vérifie un service de type oneshot."""
        config = ServiceConfig(
            description="Script ponctuel",
            exec_start="/usr/local/bin/backup.sh",
            type="oneshot"
        )

        result = config.to_unit_file()

        assert "Type=oneshot" in result

    def test_service_without_optional_fields_omits_them(self):
        """Vérifie l'absence des champs optionnels non définis."""
        config = ServiceConfig(
            description="Service minimal",
            exec_start="/usr/bin/minimal"
        )

        result = config.to_unit_file()

        assert "User=" not in result
        assert "Group=" not in result
        assert "WorkingDirectory=" not in result
        assert "Environment=" not in result
        assert "Restart=" not in result
        assert "RestartSec=" not in result

    def test_service_with_all_options(self):
        """Vérifie un service avec toutes les options."""
        config = ServiceConfig(
            description="Service complet",
            exec_start="/usr/bin/complete-daemon --config /etc/app.conf",
            type="forking",
            user="appuser",
            group="appgroup",
            working_directory="/var/lib/app",
            environment={"CONFIG": "/etc/app.conf"},
            restart="on-failure",
            restart_sec=5,
            wanted_by="multi-user.target"
        )

        result = config.to_unit_file()

        assert "Description=Service complet" in result
        assert "Type=forking" in result
        assert "ExecStart=/usr/bin/complete-daemon --config /etc/app.conf" \
            in result
        assert "User=appuser" in result
        assert "Group=appgroup" in result
        assert "WorkingDirectory=/var/lib/app" in result
        assert "Environment=CONFIG=/etc/app.conf" in result
        assert "Restart=on-failure" in result
        assert "RestartSec=5" in result


class TestServiceNameValidation:
    """Tests pour la validation des noms de service."""

    def test_rejet_caracteres_speciaux_dans_exec_start(self):
        """Vérifie le rejet de caractères spéciaux dans le nom extrait."""
        logger = MagicMock()
        executor = MagicMock()
        manager = LinuxServiceUnitManager(logger, executor)
        config = ServiceConfig(
            description="Test",
            exec_start="/usr/bin/cmd;evil"
        )
        result = manager.install_service_unit(config)
        assert result is False
        logger.log_error.assert_called_once()

    def test_rejet_nom_invalide_install_with_name(self):
        """Vérifie le rejet d'un nom invalide."""
        logger = MagicMock()
        executor = MagicMock()
        manager = LinuxServiceUnitManager(logger, executor)
        config = ServiceConfig(
            description="Test",
            exec_start="/usr/bin/test"
        )
        result = manager.install_service_unit_with_name(
            "../etc/passwd", config
        )
        assert result is False
        logger.log_error.assert_called_once()

    def test_rejet_nom_invalide_user_service(self):
        """Vérifie le rejet dans LinuxUserServiceUnitManager."""
        logger = MagicMock()
        executor = MagicMock()
        executor.reload_systemd.return_value = True
        manager = LinuxUserServiceUnitManager(logger, executor)
        config = ServiceConfig(
            description="Test",
            exec_start="/usr/bin/bad;name"
        )
        result = manager.install_service_unit(config)
        assert result is False
        logger.log_error.assert_called_once()

    def test_validation_start_service(self):
        """Vérifie la validation dans start_service."""
        logger = MagicMock()
        executor = MagicMock()
        manager = LinuxServiceUnitManager(logger, executor)
        with pytest.raises(ValueError, match="invalide"):
            manager.start_service("../evil")

    def test_validation_stop_service(self):
        """Vérifie la validation dans stop_service."""
        logger = MagicMock()
        executor = MagicMock()
        manager = LinuxServiceUnitManager(logger, executor)
        with pytest.raises(ValueError, match="invalide"):
            manager.stop_service("bad;name")

    def test_validation_enable_service(self):
        """Vérifie la validation dans enable_service."""
        logger = MagicMock()
        executor = MagicMock()
        manager = LinuxServiceUnitManager(logger, executor)
        with pytest.raises(ValueError, match="invalide"):
            manager.enable_service("$injection")


class TestServiceConfigValidation:
    """Tests pour la validation de ServiceConfig."""

    def test_rejet_type_invalide(self):
        """Vérifie le rejet d'un type de service inconnu."""
        with pytest.raises(ValueError, match="Type de service invalide"):
            ServiceConfig(
                description="Test",
                exec_start="/usr/bin/test",
                type="badtype"
            )

    @pytest.mark.parametrize("svc_type", [
        "simple", "exec", "forking", "oneshot",
        "dbus", "notify", "idle",
    ])
    def test_types_valides_acceptes(self, svc_type: str):
        """Vérifie l'acceptation de tous les types systemd valides."""
        config = ServiceConfig(
            description="Test",
            exec_start="/usr/bin/test",
            type=svc_type
        )
        assert config.type == svc_type

    def test_rejet_restart_invalide(self):
        """Vérifie le rejet d'une politique de redémarrage inconnue."""
        with pytest.raises(ValueError, match="redémarrage invalide"):
            ServiceConfig(
                description="Test",
                exec_start="/usr/bin/test",
                restart="bad-policy"
            )

    @pytest.mark.parametrize("restart", [
        "no", "always", "on-success", "on-failure",
        "on-abnormal", "on-abort", "on-watchdog",
    ])
    def test_restart_valides_acceptes(self, restart: str):
        """Vérifie l'acceptation de toutes les politiques de redémarrage."""
        config = ServiceConfig(
            description="Test",
            exec_start="/usr/bin/test",
            restart=restart
        )
        assert config.restart == restart

    def test_rejet_env_cle_avec_newline(self):
        """Vérifie le rejet d'une clé d'environnement avec newline."""
        with pytest.raises(ValueError, match="Clé d'environnement"):
            ServiceConfig(
                description="Test",
                exec_start="/usr/bin/test",
                environment={"BAD\nKEY": "value"}
            )

    def test_rejet_env_cle_avec_egal(self):
        """Vérifie le rejet d'une clé d'environnement avec '='."""
        with pytest.raises(ValueError, match="Clé d'environnement"):
            ServiceConfig(
                description="Test",
                exec_start="/usr/bin/test",
                environment={"BAD=KEY": "value"}
            )

    def test_rejet_env_valeur_avec_newline(self):
        """Vérifie le rejet d'une valeur d'environnement avec newline."""
        with pytest.raises(ValueError, match="retour à la ligne"):
            ServiceConfig(
                description="Test",
                exec_start="/usr/bin/test",
                environment={"KEY": "val\nue"}
            )


class TestWriteUnitFileAntiSymlink:
    """Tests pour la protection anti-symlink TOCTOU de _write_unit_file."""

    def test_write_refuse_lien_symbolique(self):
        """Vérifie que _write_unit_file refuse d'écrire sur un symlink."""
        temp_dir = tempfile.mkdtemp()
        try:
            logger = MagicMock()
            executor = MagicMock()
            manager = LinuxServiceUnitManager(logger, executor)
            manager.SYSTEMD_UNIT_PATH = temp_dir

            # Créer un symlink
            target = os.path.join(temp_dir, "target.txt")
            with open(target, "w") as f:
                f.write("original")
            link = os.path.join(temp_dir, "test.service")
            os.symlink(target, link)

            result = manager._write_unit_file(
                "test.service", "[Unit]\n"
            )

            assert result is False
            logger.log_error.assert_called_once()
            assert "symbolique" in logger.log_error.call_args[0][0]
        finally:
            shutil.rmtree(temp_dir)

    def test_write_cree_fichier_avec_permissions_644(self):
        """Vérifie que _write_unit_file crée le fichier en 0o644."""
        temp_dir = tempfile.mkdtemp()
        try:
            logger = MagicMock()
            executor = MagicMock()
            manager = LinuxServiceUnitManager(logger, executor)
            manager.SYSTEMD_UNIT_PATH = temp_dir

            result = manager._write_unit_file(
                "test.service", "[Unit]\nDescription=Test\n"
            )

            assert result is True
            path = os.path.join(temp_dir, "test.service")
            mode = os.stat(path).st_mode & 0o777
            assert mode == 0o644
            with open(path) as f:
                assert f.read() == "[Unit]\nDescription=Test\n"
        finally:
            shutil.rmtree(temp_dir)

    def test_remove_fichier_inexistant_succeeds(self):
        """Vérifie que _remove_unit_file réussit sur fichier inexistant."""
        temp_dir = tempfile.mkdtemp()
        try:
            logger = MagicMock()
            executor = MagicMock()
            manager = LinuxServiceUnitManager(logger, executor)
            manager.SYSTEMD_UNIT_PATH = temp_dir

            result = manager._remove_unit_file("nonexistent.service")
            assert result is True
        finally:
            shutil.rmtree(temp_dir)


class TestLinuxServiceUnitManagerSuccessPaths:
    """Tests pour les chemins succès de LinuxServiceUnitManager."""

    def _make_manager(self, tmp_path):
        """Crée un manager avec mocks et répertoire temporaire."""
        logger = MagicMock()
        executor = MagicMock()
        executor.reload_systemd.return_value = True
        executor.start_unit.return_value = True
        executor.stop_unit.return_value = True
        executor.restart_unit.return_value = True
        executor.enable_unit.return_value = True
        executor.disable_unit.return_value = True
        executor.get_status.return_value = "active"
        executor.is_enabled.return_value = True
        manager = LinuxServiceUnitManager(logger, executor)
        manager.SYSTEMD_UNIT_PATH = str(tmp_path)
        return manager, logger, executor

    def test_install_service_unit_succes(self, tmp_path):
        """install_service_unit() retourne True en cas de succès."""
        manager, logger, _ = self._make_manager(tmp_path)
        config = ServiceConfig(
            description="Service de test",
            exec_start="/usr/bin/test-daemon"
        )
        result = manager.install_service_unit(config)
        assert result is True
        logger.log_info.assert_called()

    def test_install_service_unit_rechargement_echoue(self, tmp_path):
        """install_service_unit() retourne False si reload_systemd échoue."""
        manager, _, executor = self._make_manager(tmp_path)
        executor.reload_systemd.return_value = False
        config = ServiceConfig(
            description="Test",
            exec_start="/usr/bin/test-daemon"
        )
        result = manager.install_service_unit(config)
        assert result is False

    def test_install_service_unit_with_name_succes(self, tmp_path):
        """install_service_unit_with_name() retourne True en cas de succès."""
        manager, logger, _ = self._make_manager(tmp_path)
        config = ServiceConfig(
            description="Test",
            exec_start="/usr/bin/test-daemon"
        )
        result = manager.install_service_unit_with_name("my-service", config)
        assert result is True
        logger.log_info.assert_called()

    def test_install_service_unit_with_name_reload_echoue(self, tmp_path):
        """install_service_unit_with_name() retourne False si reload échoue."""
        manager, _, executor = self._make_manager(tmp_path)
        executor.reload_systemd.return_value = False
        config = ServiceConfig(
            description="Test",
            exec_start="/usr/bin/test-daemon"
        )
        result = manager.install_service_unit_with_name("my-service", config)
        assert result is False

    def test_start_service_appelle_executor(self, tmp_path):
        """start_service() appelle executor.start_unit()."""
        manager, _, executor = self._make_manager(tmp_path)
        result = manager.start_service("my-service")
        assert result is True
        executor.start_unit.assert_called_once_with("my-service.service")

    def test_stop_service_appelle_executor(self, tmp_path):
        """stop_service() appelle executor.stop_unit()."""
        manager, _, executor = self._make_manager(tmp_path)
        result = manager.stop_service("my-service")
        assert result is True
        executor.stop_unit.assert_called_once_with("my-service.service")

    def test_restart_service_appelle_executor(self, tmp_path):
        """restart_service() appelle executor.restart_unit()."""
        manager, _, executor = self._make_manager(tmp_path)
        result = manager.restart_service("my-service")
        assert result is True
        executor.restart_unit.assert_called_once_with("my-service.service")

    def test_enable_service_appelle_executor(self, tmp_path):
        """enable_service() appelle executor.enable_unit()."""
        manager, _, executor = self._make_manager(tmp_path)
        result = manager.enable_service("my-service")
        assert result is True
        executor.enable_unit.assert_called_once_with("my-service.service")

    def test_disable_service_appelle_executor(self, tmp_path):
        """disable_service() appelle executor.disable_unit()."""
        manager, _, executor = self._make_manager(tmp_path)
        result = manager.disable_service("my-service")
        assert result is True
        executor.disable_unit.assert_called_with(
            "my-service.service", ignore_errors=False
        )

    def test_remove_service_unit_succes(self, tmp_path):
        """remove_service_unit() retourne True en cas de succès."""
        service_file = tmp_path / "my-service.service"
        service_file.write_text("[Unit]\nDescription=Test\n")
        manager, logger, _ = self._make_manager(tmp_path)
        result = manager.remove_service_unit("my-service")
        assert result is True
        logger.log_info.assert_called()

    def test_get_service_status_retourne_statut(self, tmp_path):
        """get_service_status() retourne le statut via l'executor."""
        manager, _, executor = self._make_manager(tmp_path)
        status = manager.get_service_status("my-service")
        assert status == "active"
        executor.get_status.assert_called_once_with("my-service.service")

    def test_is_service_active_retourne_true(self, tmp_path):
        """is_service_active() retourne True si statut == 'active'."""
        manager, _, executor = self._make_manager(tmp_path)
        executor.get_status.return_value = "active"
        assert manager.is_service_active("my-service") is True

    def test_is_service_active_retourne_false(self, tmp_path):
        """is_service_active() retourne False si inactif."""
        manager, _, executor = self._make_manager(tmp_path)
        executor.get_status.return_value = "inactive"
        assert manager.is_service_active("my-service") is False

    def test_is_service_enabled_retourne_true(self, tmp_path):
        """is_service_enabled() retourne True si activé."""
        manager, _, executor = self._make_manager(tmp_path)
        assert manager.is_service_enabled("my-service") is True
        executor.is_enabled.assert_called_once_with("my-service.service")

    def test_is_service_enabled_retourne_false(self, tmp_path):
        """is_service_enabled() retourne False si non activé."""
        manager, _, executor = self._make_manager(tmp_path)
        executor.is_enabled.return_value = False
        assert manager.is_service_enabled("my-service") is False


class TestLinuxUserServiceUnitManagerSuccessPaths:
    """Tests pour les chemins succès de LinuxUserServiceUnitManager."""

    def _make_manager(self, tmp_path):
        """Crée un manager utilisateur avec mocks."""
        logger = MagicMock()
        executor = MagicMock()
        executor.reload_systemd.return_value = True
        executor.start_unit.return_value = True
        executor.stop_unit.return_value = True
        executor.restart_unit.return_value = True
        executor.enable_unit.return_value = True
        executor.disable_unit.return_value = True
        executor.get_status.return_value = "active"
        executor.is_enabled.return_value = True
        manager = LinuxUserServiceUnitManager(logger, executor)
        manager._unit_path = str(tmp_path)
        return manager, logger, executor

    def test_install_service_unit_rejette_caractere_controle(self, tmp_path):
        """install_service_unit() lève ValueError si description contient \\n."""
        manager, _, _ = self._make_manager(tmp_path)
        config = ServiceConfig(
            description="Service\nExecStart=/bin/evil",
            exec_start="/usr/bin/my-app"
        )
        with pytest.raises(ValueError, match="contrôle"):
            manager.install_service_unit(config)

    def test_install_service_unit_with_name_rejette_caractere_controle(
        self, tmp_path
    ):
        """install_service_unit_with_name() lève ValueError sur \\n dans exec_start."""
        manager, _, _ = self._make_manager(tmp_path)
        config = ServiceConfig(
            description="Service test",
            exec_start="/usr/bin/app\nExecStart=/bin/evil"
        )
        with pytest.raises(ValueError, match="contrôle"):
            manager.install_service_unit_with_name("mon-service", config)

    def test_install_service_unit_succes(self, tmp_path):
        """install_service_unit() retourne True en cas de succès."""
        manager, logger, _ = self._make_manager(tmp_path)
        config = ServiceConfig(
            description="Service test",
            exec_start="/usr/bin/test-app"
        )
        result = manager.install_service_unit(config)
        assert result is True
        logger.log_info.assert_called()

    def test_install_service_unit_with_name_succes(self, tmp_path):
        """install_service_unit_with_name() retourne True en cas de succès."""
        manager, logger, _ = self._make_manager(tmp_path)
        config = ServiceConfig(
            description="Test",
            exec_start="/usr/bin/test-app"
        )
        result = manager.install_service_unit_with_name(
            "user-service", config
        )
        assert result is True
        logger.log_info.assert_called()

    def test_install_service_unit_with_name_nom_invalide(self, tmp_path):
        """install_service_unit_with_name() retourne False si nom invalide."""
        manager, logger, _ = self._make_manager(tmp_path)
        config = ServiceConfig(
            description="Test",
            exec_start="/usr/bin/test-app"
        )
        result = manager.install_service_unit_with_name(
            "../etc/passwd", config
        )
        assert result is False
        logger.log_error.assert_called_once()

    def test_start_service_appelle_executor(self, tmp_path):
        """start_service() appelle executor.start_unit()."""
        manager, _, executor = self._make_manager(tmp_path)
        result = manager.start_service("user-service")
        assert result is True
        executor.start_unit.assert_called_once_with("user-service.service")

    def test_stop_service_appelle_executor(self, tmp_path):
        """stop_service() appelle executor.stop_unit()."""
        manager, _, executor = self._make_manager(tmp_path)
        result = manager.stop_service("user-service")
        assert result is True
        executor.stop_unit.assert_called_once_with("user-service.service")

    def test_restart_service_appelle_executor(self, tmp_path):
        """restart_service() appelle executor.restart_unit()."""
        manager, _, executor = self._make_manager(tmp_path)
        result = manager.restart_service("user-service")
        assert result is True
        executor.restart_unit.assert_called_once_with("user-service.service")

    def test_enable_service_appelle_executor(self, tmp_path):
        """enable_service() appelle executor.enable_unit()."""
        manager, _, executor = self._make_manager(tmp_path)
        result = manager.enable_service("user-service")
        assert result is True
        executor.enable_unit.assert_called_once_with("user-service.service")

    def test_disable_service_appelle_executor(self, tmp_path):
        """disable_service() appelle executor.disable_unit()."""
        manager, _, executor = self._make_manager(tmp_path)
        result = manager.disable_service("user-service")
        assert result is True
        executor.disable_unit.assert_called_with(
            "user-service.service", ignore_errors=False
        )

    def test_remove_service_unit_succes(self, tmp_path):
        """remove_service_unit() retourne True en cas de succès."""
        service_file = tmp_path / "user-service.service"
        service_file.write_text("[Unit]\n")
        manager, logger, _ = self._make_manager(tmp_path)
        result = manager.remove_service_unit("user-service")
        assert result is True
        logger.log_info.assert_called()

    def test_get_service_status_retourne_statut(self, tmp_path):
        """get_service_status() retourne le statut via l'executor."""
        manager, _, executor = self._make_manager(tmp_path)
        status = manager.get_service_status("user-service")
        assert status == "active"
        executor.get_status.assert_called_once_with("user-service.service")

    def test_is_service_active_retourne_true(self, tmp_path):
        """is_service_active() retourne True si actif."""
        manager, _, executor = self._make_manager(tmp_path)
        executor.get_status.return_value = "active"
        assert manager.is_service_active("user-service") is True

    def test_is_service_active_retourne_false(self, tmp_path):
        """is_service_active() retourne False si inactif."""
        manager, _, executor = self._make_manager(tmp_path)
        executor.get_status.return_value = "inactive"
        assert manager.is_service_active("user-service") is False

    def test_is_service_enabled_retourne_resultat(self, tmp_path):
        """is_service_enabled() délègue à l'executor."""
        manager, _, executor = self._make_manager(tmp_path)
        assert manager.is_service_enabled("user-service") is True
        executor.is_enabled.assert_called_once_with("user-service.service")


class TestUnitManagerErrorPaths:
    """Tests pour les chemins d'erreur de _write_unit_file et _remove_unit_file."""

    def test_write_unit_permission_error(self, tmp_path):
        """_write_unit_file retourne False sur PermissionError."""
        from unittest.mock import patch
        logger = MagicMock()
        executor = MagicMock()
        manager = LinuxServiceUnitManager(logger, executor)
        manager.SYSTEMD_UNIT_PATH = str(tmp_path)
        with patch(
            "linuxtools.systemd.base.os.open",
            side_effect=PermissionError("Permission refusée")
        ):
            result = manager._write_unit_file("test.service", "[Unit]\n")
        assert result is False
        logger.log_error.assert_called_once()
        assert "root" in logger.log_error.call_args[0][0].lower() or \
               "permission" in logger.log_error.call_args[0][0].lower()

    def test_write_unit_generic_os_error(self, tmp_path):
        """_write_unit_file retourne False sur OSError générique."""
        from unittest.mock import patch
        import errno
        logger = MagicMock()
        executor = MagicMock()
        manager = LinuxServiceUnitManager(logger, executor)
        manager.SYSTEMD_UNIT_PATH = str(tmp_path)
        err = OSError(errno.EIO, "IO error")
        with patch(
            "linuxtools.systemd.base.os.open",
            side_effect=err
        ):
            result = manager._write_unit_file("test.service", "[Unit]\n")
        assert result is False
        logger.log_error.assert_called_once()

    def test_remove_unit_permission_error(self, tmp_path):
        """_remove_unit_file retourne False sur PermissionError."""
        from unittest.mock import patch
        logger = MagicMock()
        executor = MagicMock()
        manager = LinuxServiceUnitManager(logger, executor)
        manager.SYSTEMD_UNIT_PATH = str(tmp_path)
        with patch(
            "linuxtools.systemd.base.os.remove",
            side_effect=PermissionError("Permission refusée")
        ):
            result = manager._remove_unit_file("test.service")
        assert result is False
        logger.log_error.assert_called_once()

    def test_remove_unit_generic_os_error(self, tmp_path):
        """_remove_unit_file retourne False sur OSError générique."""
        from unittest.mock import patch
        import errno
        logger = MagicMock()
        executor = MagicMock()
        manager = LinuxServiceUnitManager(logger, executor)
        manager.SYSTEMD_UNIT_PATH = str(tmp_path)
        err = OSError(errno.EIO, "IO error")
        with patch(
            "linuxtools.systemd.base.os.remove",
            side_effect=err
        ):
            result = manager._remove_unit_file("test.service")
        assert result is False
        logger.log_error.assert_called_once()



class TestUnitFileWriteErrorPaths:
    """Tests pour les chemins d'erreur lies a l'ecriture des fichiers unit."""

    def _make_manager(self, tmp_path):
        """Cree un manager avec mocks."""
        logger = MagicMock()
        executor = MagicMock()
        executor.reload_systemd.return_value = True
        manager = LinuxServiceUnitManager(logger, executor)
        manager.SYSTEMD_UNIT_PATH = str(tmp_path)
        return manager, logger, executor

    def _make_user_manager(self, tmp_path):
        """Cree un manager utilisateur avec mocks."""
        logger = MagicMock()
        executor = MagicMock()
        executor.reload_systemd.return_value = True
        executor.disable_unit.return_value = True
        manager = LinuxUserServiceUnitManager(logger, executor)
        manager._unit_path = str(tmp_path)
        return manager, logger, executor

    def test_install_service_write_echoue(self, tmp_path):
        """install_service_unit() retourne False si ecriture echoue."""
        from unittest.mock import patch
        manager, _, _ = self._make_manager(tmp_path)
        config = ServiceConfig(
            description="Test",
            exec_start="/usr/bin/test-daemon"
        )
        with patch(
            "linuxtools.systemd.base.os.open",
            side_effect=PermissionError("no write")
        ):
            result = manager.install_service_unit(config)
        assert result is False

    def test_install_service_with_name_write_echoue(self, tmp_path):
        """install_service_unit_with_name() retourne False si ecriture echoue."""
        from unittest.mock import patch
        manager, _, _ = self._make_manager(tmp_path)
        config = ServiceConfig(
            description="Test",
            exec_start="/usr/bin/test-daemon"
        )
        with patch(
            "linuxtools.systemd.base.os.open",
            side_effect=PermissionError("no write")
        ):
            result = manager.install_service_unit_with_name("my-service", config)
        assert result is False

    def test_remove_service_echec_suppression(self, tmp_path):
        """remove_service_unit() retourne False si suppression echoue."""
        from unittest.mock import patch
        manager, _, executor = self._make_manager(tmp_path)
        executor.disable_unit.return_value = True
        executor.stop_unit.return_value = True
        service_file = tmp_path / "my-service.service"
        service_file.write_text("[Unit]\n")
        with patch(
            "linuxtools.systemd.base.os.remove",
            side_effect=PermissionError("no remove")
        ):
            result = manager.remove_service_unit("my-service")
        assert result is False

    def test_user_install_service_write_echoue(self, tmp_path):
        """LinuxUserServiceUnitManager: install retourne False si ecriture echoue."""
        from unittest.mock import patch
        manager, _, _ = self._make_user_manager(tmp_path)
        config = ServiceConfig(
            description="Test",
            exec_start="/usr/bin/test-app"
        )
        with patch(
            "linuxtools.systemd.base.os.open",
            side_effect=PermissionError("no write")
        ):
            result = manager.install_service_unit(config)
        assert result is False

    def test_user_install_service_reload_echoue(self, tmp_path):
        """LinuxUserServiceUnitManager: install retourne False si reload echoue."""
        manager, _, executor = self._make_user_manager(tmp_path)
        executor.reload_systemd.return_value = False
        config = ServiceConfig(
            description="Test",
            exec_start="/usr/bin/test-app"
        )
        result = manager.install_service_unit(config)
        assert result is False

    def test_user_install_with_name_write_echoue(self, tmp_path):
        """LinuxUserServiceUnitManager: install_with_name retourne False si ecriture echoue."""
        from unittest.mock import patch
        manager, _, _ = self._make_user_manager(tmp_path)
        config = ServiceConfig(
            description="Test",
            exec_start="/usr/bin/test-app"
        )
        with patch(
            "linuxtools.systemd.base.os.open",
            side_effect=PermissionError("no write")
        ):
            result = manager.install_service_unit_with_name("user-svc", config)
        assert result is False

    def test_user_remove_service_echec_suppression(self, tmp_path):
        """LinuxUserServiceUnitManager: remove retourne False si suppression echoue."""
        from unittest.mock import patch
        manager, _, executor = self._make_user_manager(tmp_path)
        executor.disable_unit.return_value = True
        executor.stop_unit.return_value = True
        service_file = tmp_path / "user-svc.service"
        service_file.write_text("[Unit]\n")
        with patch(
            "linuxtools.systemd.base.os.remove",
            side_effect=PermissionError("no remove")
        ):
            result = manager.remove_service_unit("user-svc")
        assert result is False


class TestRemoveServiceLogWarning:
    """Tests pour log_warning dans remove_service_unit() si disable échoue."""

    def _make_manager(self, tmp_path):
        """Crée un manager avec mocks."""
        logger = MagicMock()
        executor = MagicMock()
        executor.reload_systemd.return_value = True
        executor.disable_unit.return_value = True
        manager = LinuxServiceUnitManager(logger, executor)
        manager.SYSTEMD_UNIT_PATH = str(tmp_path)
        return manager, logger, executor

    def _make_user_manager(self, tmp_path):
        """Crée un manager utilisateur avec mocks."""
        logger = MagicMock()
        executor = MagicMock()
        executor.reload_systemd.return_value = True
        executor.disable_unit.return_value = True
        manager = LinuxUserServiceUnitManager(logger, executor)
        manager._unit_path = str(tmp_path)
        return manager, logger, executor

    def test_remove_service_unit_logue_warning_si_disable_echoue(
        self, tmp_path
    ):
        """remove_service_unit() logue un warning si disable échoue."""
        manager, logger, executor = self._make_manager(tmp_path)
        executor.disable_unit.return_value = False
        service_file = tmp_path / "my-service.service"
        service_file.write_text("[Unit]\n")

        result = manager.remove_service_unit("my-service")

        assert result is True
        logger.log_warning.assert_called_once()
        assert "my-service" in logger.log_warning.call_args[0][0]

    def test_remove_service_unit_pas_de_warning_si_disable_reussit(
        self, tmp_path
    ):
        """remove_service_unit() ne logue pas de warning si disable réussit."""
        manager, logger, executor = self._make_manager(tmp_path)
        executor.disable_unit.return_value = True
        service_file = tmp_path / "my-service.service"
        service_file.write_text("[Unit]\n")

        manager.remove_service_unit("my-service")

        logger.log_warning.assert_not_called()

    def test_user_remove_service_unit_logue_warning_si_disable_echoue(
        self, tmp_path
    ):
        """LinuxUserServiceUnitManager: log_warning si disable échoue."""
        manager, logger, executor = self._make_user_manager(tmp_path)
        executor.disable_unit.return_value = False
        service_file = tmp_path / "user-svc.service"
        service_file.write_text("[Unit]\n")

        result = manager.remove_service_unit("user-svc")

        assert result is True
        logger.log_warning.assert_called_once()

    def test_user_remove_service_unit_pas_de_warning_si_disable_reussit(
        self, tmp_path
    ):
        """LinuxUserServiceUnitManager: pas de warning si disable réussit."""
        manager, logger, executor = self._make_user_manager(tmp_path)
        executor.disable_unit.return_value = True
        service_file = tmp_path / "user-svc.service"
        service_file.write_text("[Unit]\n")

        manager.remove_service_unit("user-svc")

        logger.log_warning.assert_not_called()


class TestServiceToUnitFileSecurite:
    """Tests de sécurité : rejet des caractères de contrôle dans ServiceConfig."""

    def test_rejette_newline_dans_description(self):
        """to_unit_file lève ValueError si description contient \\n."""
        from linuxtools.systemd.base import ServiceConfig
        config = ServiceConfig(
            description="desc\nExecStart=/bin/evil",
            exec_start="/usr/bin/foo",
        )
        with pytest.raises(ValueError, match="contrôle"):
            config.to_unit_file()

    def test_rejette_newline_dans_exec_start(self):
        """to_unit_file lève ValueError si exec_start contient \\n."""
        from linuxtools.systemd.base import ServiceConfig
        config = ServiceConfig(
            description="service légitime",
            exec_start="/usr/bin/foo\nExecStart=/bin/evil",
        )
        with pytest.raises(ValueError, match="contrôle"):
            config.to_unit_file()

    def test_rejette_newline_dans_user(self):
        """to_unit_file lève ValueError si user contient \\n."""
        from linuxtools.systemd.base import ServiceConfig
        config = ServiceConfig(
            description="svc",
            exec_start="/usr/bin/foo",
            user="nobody\nUser=root",
        )
        with pytest.raises(ValueError, match="contrôle"):
            config.to_unit_file()


class TestServiceConfigHardening:
    """Tests pour les directives de durcissement systemd."""

    def _config(self, **kwargs):
        """Construit un ServiceConfig minimal avec surcharges."""
        return ServiceConfig(
            description="svc durci",
            exec_start="/usr/bin/foo",
            **kwargs,
        )

    def test_sans_durcissement_rend_fichier_inchange(self):
        """Sans champ durci, aucune directive de durcissement n'est rendue."""
        result = self._config().to_unit_file()

        assert "NoNewPrivileges" not in result
        assert "ProtectSystem" not in result
        assert "ProtectHome" not in result
        assert "PrivateTmp" not in result
        assert "ReadWritePaths" not in result

    def test_no_new_privileges_rend_directive(self):
        """no_new_privileges=True ajoute NoNewPrivileges=true."""
        result = self._config(no_new_privileges=True).to_unit_file()

        assert "NoNewPrivileges=true" in result

    def test_protect_system_full_rend_directive(self):
        """protect_system='full' ajoute ProtectSystem=full."""
        result = self._config(protect_system="full").to_unit_file()

        assert "ProtectSystem=full" in result

    def test_protect_home_et_private_tmp_rendent_directives(self):
        """protect_home et private_tmp ajoutent leurs directives."""
        result = self._config(
            protect_home=True,
            private_tmp=True,
        ).to_unit_file()

        assert "ProtectHome=true" in result
        assert "PrivateTmp=true" in result

    def test_read_write_paths_multiples_joints_par_espace(self):
        """read_write_paths rend un ReadWritePaths espacé."""
        result = self._config(
            read_write_paths=("/var/lib/app", "/var/cache/app"),
        ).to_unit_file()

        assert "ReadWritePaths=/var/lib/app /var/cache/app" in result

    def test_durcissement_rendu_entre_service_et_install(self):
        """Les directives se placent dans [Service], avant [Install]."""
        result = self._config(no_new_privileges=True).to_unit_file()

        assert result.index("NoNewPrivileges") < result.index("[Install]")
        assert result.index("[Service]") < result.index("NoNewPrivileges")

    def test_protect_system_invalide_leve_value_error(self):
        """Une valeur protect_system inconnue lève ValueError."""
        with pytest.raises(ValueError, match="protect_system invalide"):
            self._config(protect_system="bogus")

    def test_read_write_paths_caractere_controle_leve_value_error(self):
        """Un chemin RW avec \\n est rejeté au rendu."""
        config = self._config(
            read_write_paths=("/var/lib/app\nReadWritePaths=/etc",),
        )
        with pytest.raises(ValueError, match="contrôle"):
            config.to_unit_file()

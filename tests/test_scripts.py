"""Tests pour le module scripts."""

import importlib.metadata
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from linux_python_utils.notification import NotificationConfig
from linux_python_utils.scripts import (
    BashScriptConfig,
    BashScriptInstaller,
    PythonCliConfig,
    ScriptPaths,
    LinuxScriptChecker,
    InstallReport,
    MissingDependency,
    LinuxCliInstaller,
)


class TestBashScriptConfig:
    """Tests pour la dataclass BashScriptConfig."""

    def test_creation_with_command_only(self):
        """Vérifie la création avec uniquement la commande."""
        config = BashScriptConfig(exec_command="echo 'Hello'")
        assert config.exec_command == "echo 'Hello'"
        assert config.notification is None

    def test_creation_with_notification(self):
        """Vérifie la création avec notification."""
        notif = NotificationConfig(
            title="Test",
            message_success="OK",
            message_failure="KO"
        )
        config = BashScriptConfig(
            exec_command="ls -la",
            notification=notif
        )
        assert config.exec_command == "ls -la"
        assert config.notification is notif

    def test_raises_on_empty_exec_command(self):
        """Vérifie l'erreur si exec_command est vide."""
        with pytest.raises(ValueError, match="exec_command est requis"):
            BashScriptConfig(exec_command="")

    def test_is_frozen(self):
        """Vérifie que la dataclass est immutable."""
        config = BashScriptConfig(exec_command="echo test")
        with pytest.raises(AttributeError):
            config.exec_command = "autre commande"


class TestBashScriptConfigToBashScript:
    """Tests pour BashScriptConfig.to_bash_script()."""

    def test_simple_script_starts_with_shebang(self):
        """Vérifie que le script simple commence par le shebang."""
        config = BashScriptConfig(exec_command="echo 'Hello'")
        result = config.to_bash_script()
        assert result.startswith("#!/bin/bash")

    def test_simple_script_contains_command(self):
        """Vérifie que le script simple contient la commande."""
        config = BashScriptConfig(exec_command="/usr/bin/flatpak update -y")
        result = config.to_bash_script()
        assert "/usr/bin/flatpak update -y" in result

    def test_simple_script_is_minimal(self):
        """Vérifie que le script simple est minimal (pas de notification)."""
        config = BashScriptConfig(exec_command="echo test")
        result = config.to_bash_script()
        assert "send_notification" not in result
        assert "exit_code" not in result

    def test_script_with_notification_contains_function(self):
        """Vérifie la présence de send_notification avec notification."""
        notif = NotificationConfig(
            title="Test",
            message_success="OK",
            message_failure="KO"
        )
        config = BashScriptConfig(
            exec_command="echo test",
            notification=notif
        )
        result = config.to_bash_script()
        assert "send_notification()" in result

    def test_script_with_notification_captures_exit_code(self):
        """Vérifie la capture du code de retour."""
        notif = NotificationConfig(
            title="Test",
            message_success="OK",
            message_failure="KO"
        )
        config = BashScriptConfig(
            exec_command="echo test",
            notification=notif
        )
        result = config.to_bash_script()
        assert "exit_code=$?" in result
        assert "exit $exit_code" in result

    def test_script_with_notification_has_conditional(self):
        """Vérifie la présence de la condition if/else."""
        notif = NotificationConfig(
            title="Test",
            message_success="OK",
            message_failure="KO"
        )
        config = BashScriptConfig(
            exec_command="echo test",
            notification=notif
        )
        result = config.to_bash_script()
        assert "if [ $exit_code -eq 0 ]" in result
        assert "else" in result
        assert "fi" in result

    def test_script_with_notification_uses_config_values(self):
        """Vérifie l'utilisation des valeurs de configuration."""
        notif = NotificationConfig(
            title="Flatpak Update",
            message_success="Mise à jour réussie",
            message_failure="Échec de la mise à jour",
            icon_success="emblem-ok",
            icon_failure="emblem-error"
        )
        config = BashScriptConfig(
            exec_command="/usr/bin/flatpak update -y",
            notification=notif
        )
        result = config.to_bash_script()
        assert "Flatpak Update" in result
        assert "Mise à jour réussie" in result
        assert "Échec de la mise à jour" in result
        assert "emblem-ok" in result
        assert "emblem-error" in result


class TestBashScriptInstaller:
    """Tests pour la classe BashScriptInstaller."""

    def setup_method(self):
        """Initialise les mocks pour chaque test."""
        self.mock_logger = MagicMock()
        self.mock_file_manager = MagicMock()
        self.installer = BashScriptInstaller(
            self.mock_logger,
            self.mock_file_manager
        )
        self.config = BashScriptConfig(exec_command="echo 'test'")

    def test_install_creates_file_when_not_exists(self):
        """Vérifie que le fichier est créé s'il n'existe pas."""
        self.mock_file_manager.file_exists.return_value = False
        self.mock_file_manager.create_file.return_value = True

        with patch("os.open", return_value=3), \
                patch("os.fchmod"), patch("os.close"):
            result = self.installer.install("/tmp/test.sh", self.config)

        assert result is True
        self.mock_file_manager.create_file.assert_called_once()

    def test_install_skips_existing_file(self):
        """Vérifie que l'installation est ignorée si le fichier existe."""
        self.mock_file_manager.file_exists.return_value = True

        result = self.installer.install("/tmp/test.sh", self.config)

        assert result is True
        self.mock_file_manager.create_file.assert_not_called()
        self.mock_logger.log_info.assert_called()

    def test_install_returns_false_on_create_failure(self):
        """Vérifie le retour False si la création échoue."""
        self.mock_file_manager.file_exists.return_value = False
        self.mock_file_manager.create_file.return_value = False

        result = self.installer.install("/tmp/test.sh", self.config)

        assert result is False
        self.mock_logger.log_error.assert_called()

    def test_install_sets_executable_permission(self):
        """Vérifie que le script est rendu exécutable (fd-safe)."""
        self.mock_file_manager.file_exists.return_value = False
        self.mock_file_manager.create_file.return_value = True

        with patch("os.open", return_value=3) as mock_os_open, \
                patch("os.fchmod") as mock_fchmod, \
                patch("os.close"):
            self.installer.install("/tmp/test.sh", self.config)
            mock_os_open.assert_called_once_with(
                "/tmp/test.sh", os.O_RDONLY | os.O_NOFOLLOW, 0
            )
            mock_fchmod.assert_called_once_with(3, 0o755)

    def test_install_returns_false_on_chmod_failure(self):
        """Vérifie le retour False si les permissions ne peuvent pas être appliquées."""
        self.mock_file_manager.file_exists.return_value = False
        self.mock_file_manager.create_file.return_value = True

        with patch("os.open", side_effect=OSError("Permission denied")):
            result = self.installer.install("/tmp/test.sh", self.config)

        assert result is False
        self.mock_logger.log_error.assert_called()

    def test_install_generates_correct_content(self):
        """Vérifie que le contenu généré est correct."""
        self.mock_file_manager.file_exists.return_value = False
        self.mock_file_manager.create_file.return_value = True

        with patch("os.open", return_value=3), \
                patch("os.fchmod"), patch("os.close"):
            self.installer.install("/tmp/test.sh", self.config)

        call_args = self.mock_file_manager.create_file.call_args
        content = call_args[0][1]
        assert "#!/bin/bash" in content
        assert "echo 'test'" in content

    def test_exists_delegates_to_file_manager(self):
        """Vérifie que exists() délègue au file_manager."""
        self.mock_file_manager.file_exists.return_value = True

        result = self.installer.exists("/tmp/test.sh")

        assert result is True
        self.mock_file_manager.file_exists.assert_called_once_with(
            "/tmp/test.sh"
        )

    def test_custom_default_mode(self):
        """Vérifie l'utilisation d'un mode personnalisé."""
        installer = BashScriptInstaller(
            self.mock_logger,
            self.mock_file_manager,
            default_mode=0o700
        )
        self.mock_file_manager.file_exists.return_value = False
        self.mock_file_manager.create_file.return_value = True

        with patch("os.open", return_value=3), \
                patch("os.fchmod") as mock_fchmod, \
                patch("os.close"):
            installer.install("/tmp/test.sh", self.config)
            mock_fchmod.assert_called_once_with(3, 0o700)


class TestSetExecutableFdSafe:
    """Tests TOCTOU-safe pour BashScriptInstaller._set_executable()."""

    def setup_method(self):
        """Initialise les mocks avant chaque test."""
        self.mock_logger = MagicMock()
        self.mock_file_manager = MagicMock()
        self.installer = BashScriptInstaller(
            self.mock_logger,
            self.mock_file_manager
        )

    def test_set_executable_refuse_les_symlinks(self, tmp_path):
        """_set_executable() retourne False et logue si le chemin est un symlink."""
        real_file = tmp_path / "target.sh"
        real_file.write_text("#!/bin/bash\n")
        symlink = tmp_path / "link.sh"
        symlink.symlink_to(real_file)

        result = self.installer._set_executable(str(symlink))

        assert result is False
        self.mock_logger.log_error.assert_called_once()

    def test_set_executable_applique_le_mode_correct(self, tmp_path):
        """_set_executable() applique le mode 0o755 sur un fichier réel."""
        script = tmp_path / "script.sh"
        script.write_text("#!/bin/bash\n")

        result = self.installer._set_executable(str(script))

        assert result is True
        assert oct(script.stat().st_mode & 0o777) == oct(0o755)


# ---------------------------------------------------------------------------
# PythonCliConfig
# ---------------------------------------------------------------------------

class TestPythonCliConfig:
    """Tests pour la dataclass PythonCliConfig."""

    def test_valid_user_config_creates_instance(self, tmp_path):
        """Vérifie la création avec un type user valide."""
        config = PythonCliConfig(
            name="mon-app",
            deploy_type="user",
            source_dir=tmp_path,
        )
        assert config.name == "mon-app"
        assert config.deploy_type == "user"
        assert config.venv_path is None
        assert config.check_extras == []
        assert config.generate_wrapper is True

    def test_valid_system_config_creates_instance(self, tmp_path):
        """Vérifie la création avec un type system valide."""
        config = PythonCliConfig(
            name="svc",
            deploy_type="system",
            source_dir=tmp_path,
        )
        assert config.deploy_type == "system"

    def test_empty_name_raises_value_error(self, tmp_path):
        """Vérifie l'erreur si name est vide."""
        with pytest.raises(ValueError, match="name est requis"):
            PythonCliConfig(
                name="",
                deploy_type="user",
                source_dir=tmp_path,
            )

    def test_whitespace_name_raises_value_error(self, tmp_path):
        """Vérifie l'erreur si name ne contient que des espaces."""
        with pytest.raises(ValueError, match="name est requis"):
            PythonCliConfig(
                name="   ",
                deploy_type="user",
                source_dir=tmp_path,
            )

    def test_invalid_deploy_type_raises_value_error(self, tmp_path):
        """Vérifie l'erreur si deploy_type est invalide."""
        with pytest.raises(ValueError, match="deploy_type invalide"):
            PythonCliConfig(
                name="app",
                deploy_type="global",  # type: ignore[arg-type]
                source_dir=tmp_path,
            )

    def test_config_name_traversal_leve_valueerror(self, tmp_path):
        """Un nom de traversal path-traversal lève ValueError."""
        with pytest.raises(ValueError, match="name invalide"):
            PythonCliConfig(
                name="../../etc/cron.d/x",
                deploy_type="user",
                source_dir=tmp_path,
            )

    def test_config_name_caracteres_interdits_leve_valueerror(
        self, tmp_path
    ):
        """Un name avec slash ou espace lève ValueError."""
        for bad in ("/etc/passwd", "my app", "app;rm -rf /"):
            with pytest.raises(ValueError, match="name invalide"):
                PythonCliConfig(
                    name=bad,
                    deploy_type="user",
                    source_dir=tmp_path,
                )

    def test_config_is_frozen(self, tmp_path):
        """Vérifie que la dataclass est immutable."""
        config = PythonCliConfig(
            name="app",
            deploy_type="user",
            source_dir=tmp_path,
        )
        with pytest.raises((AttributeError, TypeError)):
            config.name = "autre"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# InstallReport
# ---------------------------------------------------------------------------

class TestInstallReport:
    """Tests pour la dataclass InstallReport."""

    def _make_report(self, **kwargs) -> InstallReport:
        defaults = {
            "success": True,
            "app_name": "app",
            "deploy_type": "user",
            "install_path": Path("/home/user/.local/bin/app"),
        }
        defaults.update(kwargs)
        return InstallReport(**defaults)

    def test_deps_satisfied_true_when_no_missing(self):
        """Vérifie deps_satisfied quand aucune dépendance manque."""
        report = self._make_report(total_deps=3)
        assert report.deps_satisfied is True

    def test_deps_satisfied_false_when_missing(self):
        """Vérifie deps_satisfied quand des dépendances manquent."""
        report = self._make_report(
            missing_deps=[MissingDependency("requests", ">=2.0")]
        )
        assert report.deps_satisfied is False

    def test_format_summary_success_contains_app_name(self):
        """Vérifie que le résumé contient le nom de l'app."""
        report = self._make_report()
        summary = report.format_summary()
        assert "app" in summary
        assert "✓" in summary

    def test_format_summary_failure_shows_echec(self):
        """Vérifie que le résumé indique l'échec."""
        report = self._make_report(success=False)
        assert "✗" in report.format_summary()

    def test_format_summary_includes_missing_deps(self):
        """Vérifie que les dépendances manquantes apparaissent."""
        report = self._make_report(
            total_deps=2,
            missing_deps=[MissingDependency("requests", ">=2.0")],
        )
        summary = report.format_summary()
        assert "requests" in summary
        assert ">=2.0" in summary

    def test_format_summary_includes_install_command(self):
        """Vérifie que la commande d'installation apparaît."""
        report = self._make_report(
            total_deps=1,
            missing_deps=[MissingDependency("click", ">=8.0")],
            install_command="pip3 install -e '/app'",
        )
        assert "pip3 install" in report.format_summary()

    def test_format_summary_includes_warnings(self):
        """Vérifie que les warnings apparaissent dans le résumé."""
        report = self._make_report(warnings=["Venv inaccessible"])
        assert "Venv inaccessible" in report.format_summary()


# ---------------------------------------------------------------------------
# ScriptPaths
# ---------------------------------------------------------------------------

class TestScriptPaths:
    """Tests pour ScriptPaths (chemins FHS via platformdirs)."""

    def test_user_data_dir_ends_with_app_name(self):
        """Vérifie que data_dir se termine par le nom de l'app (user)."""
        with patch(
            "linux_python_utils.scripts.paths.user_data_dir",
            return_value="/home/user/.local/share/mon-app",
        ):
            paths = ScriptPaths("mon-app", "user")
            assert paths.data_dir == Path("/home/user/.local/share/mon-app")

    def test_system_data_dir_returns_usr_local_share(self):
        """Vérifie que data_dir pointe vers /usr/local/share (system)."""
        with patch(
            "linux_python_utils.scripts.paths.site_data_dir",
            return_value="/usr/local/share/mon-app",
        ):
            paths = ScriptPaths("mon-app", "system")
            assert paths.data_dir == Path("/usr/local/share/mon-app")

    def test_user_bin_path_returns_local_bin(self):
        """Vérifie que bin_path est dans ~/.local/bin (user)."""
        with patch(
            "linux_python_utils.scripts.paths.Path.home",
            return_value=Path("/home/user"),
        ):
            paths = ScriptPaths("mon-app", "user")
            assert paths.bin_path == Path("/home/user/.local/bin/mon-app")

    def test_system_bin_path_returns_usr_local_bin(self):
        """Vérifie que bin_path est dans /usr/local/bin (system)."""
        with patch(
            "linux_python_utils.scripts.paths.site_data_dir",
            return_value="/usr/local/share/mon-app",
        ):
            paths = ScriptPaths("mon-app", "system")
            assert paths.bin_path == Path("/usr/local/bin/mon-app")

    def test_venv_dir_is_inside_data_dir(self):
        """Vérifie que venv_dir est un sous-répertoire de data_dir."""
        with patch(
            "linux_python_utils.scripts.paths.user_data_dir",
            return_value="/home/user/.local/share/app",
        ):
            paths = ScriptPaths("app", "user")
            assert paths.venv_dir == paths.data_dir / "venv"

    def test_wrapper_path_equals_bin_path(self):
        """Vérifie que wrapper_path est un alias de bin_path."""
        with patch(
            "linux_python_utils.scripts.paths.user_data_dir",
            return_value="/home/user/.local/share/app",
        ):
            paths = ScriptPaths("app", "user")
            assert paths.wrapper_path == paths.bin_path

    def test_user_config_dir_returns_dot_config(self):
        """Vérifie config_dir pour user."""
        with patch(
            "linux_python_utils.scripts.paths.user_data_dir",
            return_value="/home/user/.local/share/app",
        ):
            paths = ScriptPaths("app", "user")
            assert ".config" in str(paths.config_dir)
            assert "app" in str(paths.config_dir)

    def test_system_config_dir_returns_etc(self):
        """Vérifie config_dir pour system."""
        with patch(
            "linux_python_utils.scripts.paths.site_data_dir",
            return_value="/usr/local/share/app",
        ):
            paths = ScriptPaths("app", "system")
            assert paths.config_dir == Path("/etc/app")


# ---------------------------------------------------------------------------
# LinuxScriptChecker
# ---------------------------------------------------------------------------

class TestLinuxScriptCheckerPython:
    """Tests pour LinuxScriptChecker.check_python()."""

    def setup_method(self):
        self.logger = MagicMock()
        self.checker = LinuxScriptChecker(self.logger)

    def test_returns_true_when_python_available(self):
        """Vérifie True si python3 est disponible et sans version requise."""
        with patch("pathlib.Path.exists", return_value=True), \
             patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0, stdout="Python 3.11.2\n", stderr=""
            )
            assert self.checker.check_python() is True

    def test_returns_false_when_exec_missing(self):
        """Vérifie False si /usr/bin/python3 n'existe pas."""
        with patch("pathlib.Path.exists", return_value=False):
            assert self.checker.check_python() is False
        self.logger.log_error.assert_called()

    def test_returns_false_when_version_too_old(self):
        """Vérifie False si la version est insuffisante."""
        with patch("pathlib.Path.exists", return_value=True), \
             patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0, stdout="Python 3.10.0\n", stderr=""
            )
            assert self.checker.check_python("3.11") is False
        self.logger.log_error.assert_called()

    def test_returns_true_when_version_satisfied(self):
        """Vérifie True si la version satisfait le minimum requis."""
        with patch("pathlib.Path.exists", return_value=True), \
             patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0, stdout="Python 3.12.1\n", stderr=""
            )
            assert self.checker.check_python("3.11") is True

    def test_returns_true_when_version_illisible(self):
        """Retourne True et logue si version Python illisible."""
        with patch("pathlib.Path.exists", return_value=True), \
             patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0, stdout="Python\n", stderr=""
            )
            assert self.checker.check_python("3.11") is True
        self.logger.log_info.assert_called()


class TestLinuxScriptCheckerScript:
    """Tests pour LinuxScriptChecker.check_script_syntax()."""

    def setup_method(self):
        self.logger = MagicMock()
        self.checker = LinuxScriptChecker(self.logger)

    def test_returns_true_for_valid_script(self, tmp_path):
        """Vérifie True pour un script syntaxiquement correct."""
        script = tmp_path / "main.py"
        script.write_text("print('hello')\n")
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stderr="")
            assert self.checker.check_script_syntax(script) is True

    def test_returns_false_when_not_found(self, tmp_path):
        """Vérifie False si le script n'existe pas."""
        assert self.checker.check_script_syntax(
            tmp_path / "missing.py"
        ) is False
        self.logger.log_error.assert_called()

    def test_returns_false_when_syntax_error(self, tmp_path):
        """Vérifie False si py_compile détecte une erreur."""
        script = tmp_path / "bad.py"
        script.write_text("def f(\n")
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1, stderr="SyntaxError"
            )
            assert self.checker.check_script_syntax(script) is False
        self.logger.log_error.assert_called()


class TestLinuxScriptCheckerVenv:
    """Tests pour LinuxScriptChecker.check_venv()."""

    def setup_method(self):
        self.logger = MagicMock()
        self.checker = LinuxScriptChecker(self.logger)

    def test_returns_true_when_venv_valid(self, tmp_path):
        """Vérifie True si le venv est fonctionnel."""
        python_bin = tmp_path / "bin" / "python"
        python_bin.parent.mkdir()
        python_bin.touch()
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            assert self.checker.check_venv(tmp_path) is True

    def test_returns_false_when_venv_missing(self, tmp_path):
        """Vérifie False si le répertoire venv n'existe pas."""
        assert self.checker.check_venv(tmp_path / "novenv") is False
        self.logger.log_error.assert_called()

    def test_returns_false_when_python_bin_missing(self, tmp_path):
        """Vérifie False si l'interpréteur est absent."""
        (tmp_path / "bin").mkdir()
        assert self.checker.check_venv(tmp_path) is False
        self.logger.log_error.assert_called()

    def test_returns_false_when_venv_interpreter_nonfonctionnel(
        self, tmp_path
    ):
        """Retourne False et logue si l'interpréteur venv ne répond pas."""
        python_bin = tmp_path / "bin" / "python"
        python_bin.parent.mkdir()
        python_bin.touch()
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1)
            assert self.checker.check_venv(tmp_path) is False
        self.logger.log_error.assert_called()


class TestLinuxScriptCheckerPyproject:
    """Tests pour LinuxScriptChecker.read_pyproject()."""

    def setup_method(self):
        self.logger = MagicMock()
        self.checker = LinuxScriptChecker(self.logger)

    def test_returns_data_when_valid(self, tmp_path):
        """Vérifie le retour d'un dict valide."""
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_bytes(
            b'[project]\nname = "app"\nversion = "1.0"\n'
            b'dependencies = ["requests>=2.0"]\n'
        )
        data = self.checker.read_pyproject(pyproject)
        assert data["name"] == "app"
        assert data["version"] == "1.0"
        assert "requests>=2.0" in data["dependencies"]  # type: ignore[operator]

    def test_raises_file_not_found_when_missing(self, tmp_path):
        """Vérifie FileNotFoundError si le fichier n'existe pas."""
        with pytest.raises(FileNotFoundError):
            self.checker.read_pyproject(tmp_path / "missing.toml")

    def test_raises_value_error_missing_project_section(self, tmp_path):
        """Vérifie ValueError si [project] est absent."""
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_bytes(b'[build-system]\nrequires = []\n')
        with pytest.raises(ValueError, match="Section \\[project\\]"):
            self.checker.read_pyproject(pyproject)

    def test_returns_scripts_dict_when_present(self, tmp_path):
        """Vérifie la présence de la clé scripts dans le retour."""
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_bytes(
            b'[project]\nname = "app"\n'
            b'[project.scripts]\napp = "app.main:main"\n'
        )
        data = self.checker.read_pyproject(pyproject)
        assert data["scripts"] == {"app": "app.main:main"}


class TestLinuxScriptCheckerDeps:
    """Tests pour LinuxScriptChecker.check_dependencies()."""

    def setup_method(self):
        self.logger = MagicMock()
        self.checker = LinuxScriptChecker(self.logger)

    def _make_pyproject(self, tmp_path: Path, deps: list[str]) -> Path:
        pyproject = tmp_path / "pyproject.toml"
        deps_toml = "\n".join(f'  "{d}",' for d in deps)
        content = (
            f'[project]\nname = "app"\ndependencies = [\n{deps_toml}\n]\n'
        ).encode()
        pyproject.write_bytes(content)
        return pyproject

    def test_all_installed_returns_empty_missing(self, tmp_path):
        """Vérifie liste vide si toutes les deps sont installées."""
        pyproject = self._make_pyproject(tmp_path, ["requests>=2.0"])
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            missing, installed, total, _ = self.checker.check_dependencies(
                pyproject, None, []
            )
        assert missing == []
        assert len(installed) == 1
        assert total == 1

    def test_missing_package_in_report(self, tmp_path):
        """Vérifie que le paquet manquant apparaît dans missing."""
        pyproject = self._make_pyproject(tmp_path, ["click>=8.0"])
        # _is_installed sonde importlib.metadata avant pip : forcer
        # PackageNotFoundError pour simuler un paquet absent.
        with patch(
            "importlib.metadata.distribution",
            side_effect=importlib.metadata.PackageNotFoundError,
        ), patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1)
            missing, _installed, total, _ = self.checker.check_dependencies(
                pyproject, None, []
            )
        assert len(missing) == 1
        assert missing[0].package == "click"

    def test_checker_venv_cible_ignore_process_courant(
        self, tmp_path
    ):
        """check_dependencies n'appelle pas importlib.metadata si venv_path fourni."""
        pyproject = self._make_pyproject(tmp_path, ["requests>=2.0"])
        with patch(
            "importlib.metadata.distribution"
        ) as mock_dist, patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="")
            self.checker.check_dependencies(
                pyproject, tmp_path / "venv", []
            )
        mock_dist.assert_not_called()

    def test_extras_are_included(self, tmp_path):
        """Vérifie que les extras sont inclus dans la vérification."""
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_bytes(
            b'[project]\nname = "app"\ndependencies = []\n'
            b'[project.optional-dependencies]\n'
            b'dev = ["pytest>=7.0"]\n'
        )
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            _, _installed, total, _ = self.checker.check_dependencies(
                pyproject, None, ["dev"]
            )
        assert total == 1


# ---------------------------------------------------------------------------
# LinuxCliInstaller
# ---------------------------------------------------------------------------

class TestLinuxCliInstaller:
    """Tests pour LinuxCliInstaller.install()."""

    def setup_method(self):
        self.logger = MagicMock()
        self.checker = MagicMock()
        self.installer = LinuxCliInstaller(self.logger, self.checker)

    def _user_config(self, tmp_path: Path) -> PythonCliConfig:
        return PythonCliConfig(
            name="app",
            deploy_type="user",
            source_dir=tmp_path,
        )

    def _patch_paths(self, tmp_path: Path):
        """Retourne un patch de ScriptPaths avec des chemins tmp."""
        mock_paths = MagicMock()
        mock_paths.bin_path = tmp_path / "bin" / "app"
        mock_paths.data_dir = tmp_path / "data"
        return mock_paths

    def test_returns_failure_when_python_check_fails(self, tmp_path):
        """Vérifie InstallReport(success=False) si python3 absent."""
        self.checker.check_python.return_value = False
        config = self._user_config(tmp_path)
        with patch(
            "linux_python_utils.scripts.installer.ScriptPaths"
        ) as mock_cls:
            mock_cls.return_value = self._patch_paths(tmp_path)
            report = self.installer.install(config, confirm_wrapper=False)
        assert report.success is False

    def test_returns_failure_when_pyproject_missing(self, tmp_path):
        """Vérifie InstallReport(success=False) si pyproject.toml absent."""
        self.checker.check_python.return_value = True
        self.checker.read_pyproject.side_effect = FileNotFoundError(
            "pyproject.toml introuvable"
        )
        config = self._user_config(tmp_path)
        with patch(
            "linux_python_utils.scripts.installer.ScriptPaths"
        ) as mock_cls:
            mock_cls.return_value = self._patch_paths(tmp_path)
            report = self.installer.install(config, confirm_wrapper=False)
        assert report.success is False

    def test_returns_failure_when_uv_fails(self, tmp_path):
        """Vérifie InstallReport(success=False) si uv échoue."""
        self.checker.check_python.return_value = True
        self.checker.read_pyproject.return_value = {
            "name": "app", "version": "1.0",
            "requires_python": None, "dependencies": [],
            "optional_dependencies": {}, "scripts": {"app": "app:main"},
        }
        self.checker.check_dependencies.return_value = ([], [], 0, "")
        config = self._user_config(tmp_path)
        with patch(
            "linux_python_utils.scripts.installer.ScriptPaths"
        ) as mock_cls, \
             patch("subprocess.run") as mock_run:
            mock_cls.return_value = self._patch_paths(tmp_path)
            mock_run.return_value = MagicMock(
                returncode=1, stderr="uv error"
            )
            report = self.installer.install(config, confirm_wrapper=False)
        assert report.success is False

    def test_skips_wrapper_when_scripts_entry_exists(self, tmp_path):
        """Vérifie qu'aucun wrapper n'est généré si [project.scripts] existe."""
        self.checker.check_python.return_value = True
        self.checker.read_pyproject.return_value = {
            "name": "app", "version": "1.0",
            "requires_python": None, "dependencies": [],
            "optional_dependencies": {}, "scripts": {"app": "app:main"},
        }
        self.checker.check_dependencies.return_value = ([], [], 0, "")
        config = self._user_config(tmp_path)
        with patch(
            "linux_python_utils.scripts.installer.ScriptPaths"
        ) as mock_cls, \
             patch("subprocess.run") as mock_run, \
             patch.object(
                 self.installer, "_write_wrapper"
             ) as mock_write:
            mock_cls.return_value = self._patch_paths(tmp_path)
            mock_run.return_value = MagicMock(returncode=0, stderr="")
            self.installer.install(config, confirm_wrapper=False)
        mock_write.assert_not_called()

    def test_generates_wrapper_when_no_scripts_entry(self, tmp_path):
        """Vérifie que le wrapper est généré si [project.scripts] absent."""
        self.checker.check_python.return_value = True
        self.checker.read_pyproject.return_value = {
            "name": "app", "version": "1.0",
            "requires_python": None, "dependencies": [],
            "optional_dependencies": {}, "scripts": {},
        }
        self.checker.check_dependencies.return_value = ([], [], 0, "")
        config = self._user_config(tmp_path)
        with patch(
            "linux_python_utils.scripts.installer.ScriptPaths"
        ) as mock_cls, \
             patch("subprocess.run") as mock_run, \
             patch.object(
                 self.installer, "_write_wrapper"
             ) as mock_write:
            mock_cls.return_value = self._patch_paths(tmp_path)
            mock_run.return_value = MagicMock(returncode=0, stderr="")
            self.installer.install(config, confirm_wrapper=False)
        mock_write.assert_called_once()

    def _run_system_install_cmd(self, tmp_path, euid):
        """Lance un install system mocké et retourne la commande uv.

        Args:
            tmp_path: Répertoire temporaire pytest.
            euid: Valeur simulée de os.geteuid().

        Returns:
            La liste d'arguments passée à subprocess.run.
        """
        self.checker.check_python.return_value = True
        self.checker.read_pyproject.return_value = {
            "name": "app", "version": "1.0",
            "requires_python": None, "dependencies": [],
            "optional_dependencies": {}, "scripts": {"app": "app:main"},
        }
        self.checker.check_dependencies.return_value = ([], [], 0, "")
        config = PythonCliConfig(
            name="app", deploy_type="system", source_dir=tmp_path
        )
        with patch(
            "linux_python_utils.scripts.installer.ScriptPaths"
        ) as mock_cls, \
             patch("subprocess.run") as mock_run, \
             patch(
                 "linux_python_utils.scripts.installer.shutil.which",
                 return_value="/usr/bin/uv",
             ), \
             patch(
                 "linux_python_utils.scripts.installer.os.geteuid",
                 return_value=euid,
             ):
            mock_cls.return_value = self._patch_paths(tmp_path)
            mock_run.return_value = MagicMock(returncode=0, stderr="")
            self.installer.install(config, confirm_wrapper=False)
            return mock_run.call_args[0][0]

    def test_system_avec_sudo_si_non_root(self, tmp_path):
        """sudo présent dans la commande system si euid != 0."""
        cmd = self._run_system_install_cmd(tmp_path, euid=1000)
        assert cmd[0] == "sudo"

    def test_system_sans_sudo_si_root(self, tmp_path):
        """sudo absent de la commande system si déjà root (euid == 0)."""
        cmd = self._run_system_install_cmd(tmp_path, euid=0)
        assert "sudo" not in cmd
        assert cmd[0] == "env"

    def test_missing_deps_recorded_in_report(self, tmp_path):
        """Vérifie que les deps manquantes sont dans le rapport."""
        self.checker.check_python.return_value = True
        self.checker.read_pyproject.return_value = {
            "name": "app", "version": "1.0",
            "requires_python": None, "dependencies": ["requests>=2.0"],
            "optional_dependencies": {}, "scripts": {"app": "app:main"},
        }
        missing_dep = MissingDependency("requests", ">=2.0")
        self.checker.check_dependencies.return_value = (
            [missing_dep], [], 1, "pip3 install -e '/app'"
        )
        config = self._user_config(tmp_path)
        with patch(
            "linux_python_utils.scripts.installer.ScriptPaths"
        ) as mock_cls, \
             patch("subprocess.run") as mock_run:
            mock_cls.return_value = self._patch_paths(tmp_path)
            mock_run.return_value = MagicMock(returncode=0, stderr="")
            report = self.installer.install(config, confirm_wrapper=False)
        assert len(report.missing_deps) == 1
        assert report.success is True

    def test_find_uv_prefere_le_path(self, tmp_path):
        """_find_uv retourne le résultat de shutil.which en priorité."""
        with patch(
            "linux_python_utils.scripts.installer.shutil.which",
            return_value="/usr/bin/uv",
        ):
            assert self.installer._find_uv() == "/usr/bin/uv"

    def test_find_uv_repli_local_bin(self, tmp_path):
        """_find_uv trouve uv dans ~/.local/bin si absent du PATH."""
        fake_uv = tmp_path / ".local" / "bin" / "uv"
        fake_uv.parent.mkdir(parents=True)
        fake_uv.write_text("#!/bin/sh\n")
        fake_uv.chmod(0o755)
        with patch(
            "linux_python_utils.scripts.installer.shutil.which",
            return_value=None,
        ), patch(
            "linux_python_utils.scripts.installer.Path.home",
            return_value=tmp_path,
        ), patch.dict(
            "linux_python_utils.scripts.installer.os.environ", {}, clear=True
        ):
            assert self.installer._find_uv() == str(fake_uv)

    def test_find_uv_repli_sudo_user(self, tmp_path):
        """_find_uv sonde le home de $SUDO_USER (cas sudo/root)."""
        sudo_home = tmp_path / "fredhome"
        fake_uv = sudo_home / ".local" / "bin" / "uv"
        fake_uv.parent.mkdir(parents=True)
        fake_uv.write_text("#!/bin/sh\n")
        fake_uv.chmod(0o755)
        pw = MagicMock()
        pw.pw_dir = str(sudo_home)
        with patch(
            "linux_python_utils.scripts.installer.shutil.which",
            return_value=None,
        ), patch(
            "linux_python_utils.scripts.installer.Path.home",
            return_value=tmp_path / "roothome",
        ), patch.dict(
            "linux_python_utils.scripts.installer.os.environ",
            {"SUDO_USER": "fred"},
            clear=True,
        ), patch(
            "linux_python_utils.scripts.installer.pwd.getpwnam",
            return_value=pw,
        ):
            assert self.installer._find_uv() == str(fake_uv)

    def test_find_uv_introuvable_retourne_none(self, tmp_path):
        """_find_uv retourne None si uv n'est nulle part."""
        with patch(
            "linux_python_utils.scripts.installer.shutil.which",
            return_value=None,
        ), patch(
            "linux_python_utils.scripts.installer.Path.home",
            return_value=tmp_path / "empty",
        ), patch.dict(
            "linux_python_utils.scripts.installer.os.environ", {}, clear=True
        ):
            assert self.installer._find_uv() is None


class TestLinuxCliInstallerWrapper:
    """Tests pour les méthodes privées de génération du wrapper."""

    def setup_method(self):
        self.logger = MagicMock()
        self.checker = MagicMock()
        self.installer = LinuxCliInstaller(self.logger, self.checker)

    def test_strip_venv_block_removes_activate_block(self):
        """Vérifie la suppression du bloc d'activation du venv."""
        content = (
            "#!/bin/bash\n"
            'if [ -f "${APP_DIR}/venv/bin/activate" ]; then\n'
            '    source "${APP_DIR}/venv/bin/activate"\n'
            "fi\n"
            "exec python main.py\n"
        )
        result = LinuxCliInstaller._strip_venv_block(content)
        assert "activate" not in result
        assert "exec python main.py" in result

    def test_strip_venv_block_keeps_content_without_venv(self):
        """Vérifie que le contenu sans bloc venv reste intact."""
        content = "#!/bin/bash\nexec python main.py\n"
        result = LinuxCliInstaller._strip_venv_block(content)
        assert result == content

    def test_write_wrapper_creates_executable_file(self, tmp_path):
        """Vérifie que _write_wrapper crée un fichier exécutable."""
        target = tmp_path / "bin" / "app"
        self.installer._write_wrapper("#!/bin/bash\n", target)
        assert target.exists()
        assert target.stat().st_mode & 0o111  # au moins un bit exécutable

    def test_wrapper_refuse_symlink(self, tmp_path):
        """_write_wrapper lève OSError si target_path est un symlink."""
        real_file = tmp_path / "real.sh"
        real_file.write_text("#!/bin/bash\n")
        symlink = tmp_path / "link.sh"
        symlink.symlink_to(real_file)

        with pytest.raises(OSError):
            self.installer._write_wrapper("#!/bin/bash\n", symlink)

    def test_write_wrapper_oserror_retourne_rapport_echec(
        self, tmp_path
    ):
        """install() retourne InstallReport(success=False) si wrapper échoue."""
        self.checker.check_python.return_value = True
        self.checker.read_pyproject.return_value = {
            "name": "app",
            "version": "1.0",
            "requires_python": None,
            "dependencies": [],
            "optional_dependencies": {},
            "scripts": {},
        }
        self.checker.check_dependencies.return_value = ([], [], 0, "")
        config = PythonCliConfig(
            name="app", deploy_type="user", source_dir=tmp_path
        )
        with patch(
            "linux_python_utils.scripts.installer.ScriptPaths"
        ) as mock_cls, patch.object(
            self.installer,
            "_write_wrapper",
            side_effect=OSError("Permission denied"),
        ):
            mock_paths = MagicMock()
            mock_paths.bin_path = tmp_path / "bin" / "app"
            mock_cls.return_value = mock_paths
            report = self.installer.install(
                config, confirm_wrapper=False
            )
        assert report.success is False
        assert any(
            "Wrapper" in w or "Permission" in w
            for w in report.warnings
        )

    def test_generate_wrapper_user_sans_venv(self, tmp_path):
        """Wrapper user sans venv : pas de bloc activate."""
        config = PythonCliConfig(
            name="app", deploy_type="user", source_dir=tmp_path
        )
        paths = MagicMock()
        paths.data_dir = tmp_path / "data"
        content = self.installer._generate_wrapper_content(config, paths)
        assert "APP_DIR" in content
        assert "HOME" in content
        assert "activate" not in content

    def test_generate_wrapper_user_avec_venv(self, tmp_path):
        """Wrapper user avec venv : le bloc activate est présent."""
        venv = tmp_path / "venv"
        config = PythonCliConfig(
            name="app", deploy_type="user",
            source_dir=tmp_path, venv_path=venv,
        )
        paths = MagicMock()
        paths.data_dir = tmp_path / "data"
        content = self.installer._generate_wrapper_content(config, paths)
        assert "activate" in content

    def test_generate_wrapper_system_sans_venv(self, tmp_path):
        """Wrapper system sans venv : chemin /usr/local/share."""
        config = PythonCliConfig(
            name="app", deploy_type="system", source_dir=tmp_path
        )
        paths = MagicMock()
        content = self.installer._generate_wrapper_content(config, paths)
        assert "/usr/local/share/app" in content
        assert "activate" not in content

    def test_generate_wrapper_system_avec_venv(self, tmp_path):
        """Wrapper system avec venv : bloc activate présent."""
        venv = tmp_path / "venv"
        config = PythonCliConfig(
            name="app", deploy_type="system",
            source_dir=tmp_path, venv_path=venv,
        )
        paths = MagicMock()
        content = self.installer._generate_wrapper_content(config, paths)
        assert "/usr/local/share/app" in content
        assert "activate" in content


# ---------------------------------------------------------------------------
# Branches non couvertes — no-logger + edge cases
# ---------------------------------------------------------------------------

class TestBashScriptInstallerNoLogger:
    """Chemins sans logger dans BashScriptInstaller."""

    def _make_installer(self):
        file_manager = MagicMock()
        return BashScriptInstaller(None, file_manager), file_manager

    def test_install_skip_existing_sans_logger(self, tmp_path):
        """install() retourne True sur un script existant sans logger."""
        installer, fm = self._make_installer()
        fm.file_exists.return_value = True
        assert installer.install(str(tmp_path / "s.sh"), BashScriptConfig(
            exec_command="echo x"
        )) is True

    def test_install_create_fails_sans_logger(self, tmp_path):
        """install() retourne False si create_file échoue sans logger."""
        installer, fm = self._make_installer()
        fm.file_exists.return_value = False
        fm.create_file.return_value = False
        assert installer.install(str(tmp_path / "s.sh"), BashScriptConfig(
            exec_command="echo x"
        )) is False

    def test_set_executable_fails_sans_logger(self, tmp_path):
        """_set_executable retourne False sur OSError sans logger."""
        installer, _ = self._make_installer()
        with patch("os.open", side_effect=OSError("denied")):
            assert installer._set_executable(str(tmp_path / "f.sh")) is False

    def test_install_success_logue_info_sans_logger(self, tmp_path):
        """install() retourne True sans lever d'erreur quand logger=None."""
        installer, fm = self._make_installer()
        fm.file_exists.return_value = False
        fm.create_file.return_value = True
        script = tmp_path / "s.sh"
        script.write_text("#!/bin/bash\n")
        result = installer.install(str(script), BashScriptConfig(
            exec_command="echo x"
        ))
        assert result is True


class TestLinuxScriptCheckerSansLogger:
    """Branches sans logger dans LinuxScriptChecker."""

    def setup_method(self):
        self.checker = LinuxScriptChecker()

    def test_check_python_exec_manquant(self):
        """Retourne False si python3 absent sans logger."""
        with patch("pathlib.Path.exists", return_value=False):
            assert self.checker.check_python() is False

    def test_check_python_subprocess_echec(self):
        """Retourne False si subprocess python3 --version échoue sans logger."""
        with patch("pathlib.Path.exists", return_value=True), \
             patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="")
            assert self.checker.check_python() is False

    def test_check_python_version_insuffisante(self):
        """Retourne False si version trop ancienne sans logger."""
        with patch("pathlib.Path.exists", return_value=True), \
             patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0, stdout="Python 3.10.0\n", stderr=""
            )
            assert self.checker.check_python("3.11") is False

    def test_check_python_version_ok(self):
        """Retourne True si version satisfaite sans logger."""
        with patch("pathlib.Path.exists", return_value=True), \
             patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0, stdout="Python 3.12.0\n", stderr=""
            )
            assert self.checker.check_python("3.11") is True

    def test_check_script_syntax_introuvable(self, tmp_path):
        """Retourne False si script absent sans logger."""
        assert self.checker.check_script_syntax(
            tmp_path / "missing.py"
        ) is False

    def test_check_script_syntax_erreur(self, tmp_path):
        """Retourne False si syntaxe incorrecte sans logger."""
        script = tmp_path / "bad.py"
        script.write_text("def f(\n")
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stderr="err")
            assert self.checker.check_script_syntax(script) is False

    def test_check_script_syntax_ok(self, tmp_path):
        """Retourne True si syntaxe correcte sans logger."""
        script = tmp_path / "ok.py"
        script.write_text("print('ok')\n")
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stderr="")
            assert self.checker.check_script_syntax(script) is True

    def test_check_venv_absent(self, tmp_path):
        """Retourne False si venv absent sans logger."""
        assert self.checker.check_venv(tmp_path / "novenv") is False

    def test_check_venv_python_absent(self, tmp_path):
        """Retourne False si interpréteur absent sans logger."""
        (tmp_path / "bin").mkdir()
        assert self.checker.check_venv(tmp_path) is False

    def test_check_venv_subprocess_echec(self, tmp_path):
        """Retourne False si subprocess venv échoue sans logger."""
        python_bin = tmp_path / "bin" / "python"
        python_bin.parent.mkdir()
        python_bin.touch()
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1)
            assert self.checker.check_venv(tmp_path) is False

    def test_check_venv_ok(self, tmp_path):
        """Retourne True si venv fonctionnel sans logger."""
        python_bin = tmp_path / "bin" / "python"
        python_bin.parent.mkdir()
        python_bin.touch()
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            assert self.checker.check_venv(tmp_path) is True

    def test_check_python_version_illisible(self):
        """Retourne True si version Python illisible (sans logger)."""
        with patch("pathlib.Path.exists", return_value=True), \
             patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0, stdout="Python\n", stderr=""
            )
            assert self.checker.check_python("3.11") is True


class TestLinuxScriptCheckerEdgeCases:
    """Branches non couvertes de LinuxScriptChecker."""

    def setup_method(self):
        self.logger = MagicMock()
        self.checker = LinuxScriptChecker(self.logger)

    def test_check_python_subprocess_fails(self):
        """Retourne False si subprocess python3 --version retourne != 0."""
        with patch("pathlib.Path.exists", return_value=True), \
             patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="")
            assert self.checker.check_python() is False
        self.logger.log_error.assert_called()

    def test_check_python_version_ok_logue_info(self):
        """Logue log_info quand la version satisfait le minimum."""
        with patch("pathlib.Path.exists", return_value=True), \
             patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0, stdout="Python 3.12.0\n", stderr=""
            )
            assert self.checker.check_python("3.11") is True
        self.logger.log_info.assert_called()

    def test_check_extras_inconnu_ignore(self, tmp_path):
        """Un extra inexistant dans opt-deps n'ajoute pas de dépendances."""
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_bytes(
            b'[project]\nname = "app"\ndependencies = []\n'
        )
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            _, _, total, _ = self.checker.check_dependencies(
                pyproject, None, ["inexistant"]
            )
        assert total == 0

    def test_is_installed_direct_url_file(self):
        """_is_installed retourne le chemin depuis direct_url.json file://."""
        import json as _json
        direct_url_data = _json.dumps({"url": "file:///home/user/proj"})
        mock_dist = MagicMock()
        mock_dist.read_text.return_value = direct_url_data
        with patch(
            "importlib.metadata.distribution",
            return_value=mock_dist,
        ):
            result = LinuxScriptChecker._is_installed(
                "myapp", "pip3", use_importlib=True
            )
        assert result == "/home/user/proj"

    def test_is_installed_pip_show_sans_location(self):
        """_is_installed retourne 'installé' si pip show OK mais pas de Location."""
        with patch(
            "importlib.metadata.distribution",
            side_effect=importlib.metadata.PackageNotFoundError,
        ), patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0, stdout="Name: pkg\nVersion: 1.0\n"
            )
            result = LinuxScriptChecker._is_installed(
                "pkg", "pip3", use_importlib=True
            )
        assert result == "installé"

    def test_is_installed_direct_url_non_file(self):
        """_is_installed utilise locate_file si URL n'est pas file://."""
        import json as _json
        direct_url_data = _json.dumps({"url": "https://example.com/pkg"})
        mock_dist = MagicMock()
        mock_dist.read_text.return_value = direct_url_data
        mock_dist.locate_file.return_value = Path("/site-packages")
        with patch(
            "importlib.metadata.distribution",
            return_value=mock_dist,
        ):
            result = LinuxScriptChecker._is_installed(
                "myapp", "pip3", use_importlib=True
            )
        assert result == "/site-packages"

    def test_is_installed_pip_show_avec_location(self):
        """_is_installed retourne le chemin si pip show contient Location."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="Name: pkg\nLocation: /usr/lib/python3.11\n",
            )
            result = LinuxScriptChecker._is_installed(
                "pkg", "pip3", use_importlib=False
            )
        assert result == "/usr/lib/python3.11"


class TestLinuxCliInstallerEdgeCases:
    """Branches non couvertes de LinuxCliInstaller."""

    def setup_method(self):
        self.checker = MagicMock()
        self.installer = LinuxCliInstaller(None, self.checker)

    def _patch_paths(self, tmp_path):
        mock_paths = MagicMock()
        mock_paths.bin_path = tmp_path / "bin" / "app"
        return mock_paths

    def _user_config(self, tmp_path):
        return PythonCliConfig(
            name="app", deploy_type="user", source_dir=tmp_path
        )

    def test_install_success_sans_logger(self, tmp_path):
        """install() réussit sans logger injecté."""
        self.checker.check_python.return_value = True
        self.checker.read_pyproject.return_value = {
            "name": "app", "version": "1.0",
            "requires_python": None, "dependencies": [],
            "optional_dependencies": {}, "scripts": {"app": "app:main"},
        }
        self.checker.check_dependencies.return_value = ([], [], 0, "")
        config = self._user_config(tmp_path)
        with patch(
            "linux_python_utils.scripts.installer.ScriptPaths"
        ) as mock_cls, patch("subprocess.run") as mock_run, \
             patch(
                 "linux_python_utils.scripts.installer.shutil.which",
                 return_value="/usr/bin/uv",
             ):
            mock_cls.return_value = self._patch_paths(tmp_path)
            mock_run.return_value = MagicMock(returncode=0, stderr="")
            report = self.installer.install(config, confirm_wrapper=False)
        assert report.success is True

    def test_install_venv_inaccessible_sans_logger(self, tmp_path):
        """venv inaccessible enregistre un warning sans logger."""
        venv = tmp_path / "missing_venv"
        self.checker.check_python.return_value = True
        self.checker.read_pyproject.return_value = {
            "name": "app", "version": "1.0",
            "requires_python": None, "dependencies": [],
            "optional_dependencies": {}, "scripts": {"app": "app:main"},
        }
        self.checker.check_dependencies.return_value = ([], [], 0, "")
        self.checker.check_venv.return_value = False
        config = PythonCliConfig(
            name="app", deploy_type="user",
            source_dir=tmp_path, venv_path=venv,
        )
        with patch(
            "linux_python_utils.scripts.installer.ScriptPaths"
        ) as mock_cls, patch("subprocess.run") as mock_run, \
             patch(
                 "linux_python_utils.scripts.installer.shutil.which",
                 return_value="/usr/bin/uv",
             ):
            mock_cls.return_value = self._patch_paths(tmp_path)
            mock_run.return_value = MagicMock(returncode=0, stderr="")
            report = self.installer.install(config, confirm_wrapper=False)
        assert any("Venv" in w for w in report.warnings)

    def test_handle_wrapper_tty_desactive_confirmation(self, tmp_path):
        """confirm_wrapper=True basculé sur False si stdin non-TTY."""
        self.checker.check_python.return_value = True
        self.checker.read_pyproject.return_value = {
            "name": "app", "version": "1.0",
            "requires_python": None, "dependencies": [],
            "optional_dependencies": {}, "scripts": {},
        }
        self.checker.check_dependencies.return_value = ([], [], 0, "")
        config = self._user_config(tmp_path)
        with patch(
            "linux_python_utils.scripts.installer.ScriptPaths"
        ) as mock_cls, patch("subprocess.run") as mock_run, \
             patch(
                 "linux_python_utils.scripts.installer.shutil.which",
                 return_value="/usr/bin/uv",
             ), patch(
                 "linux_python_utils.scripts.installer.sys.stdin.isatty",
                 return_value=False,
             ), patch.object(
                 self.installer, "_write_wrapper"
             ) as mock_write:
            mock_cls.return_value = self._patch_paths(tmp_path)
            mock_run.return_value = MagicMock(returncode=0, stderr="")
            # confirm_wrapper=True mais stdin non-TTY → auto False
            self.installer.install(config, confirm_wrapper=True)
        mock_write.assert_called_once()

    def test_handle_wrapper_refuse_interactif(self, tmp_path):
        """Wrapper refusé interactivement → InstallReport(success=False)."""
        self.checker.check_python.return_value = True
        self.checker.read_pyproject.return_value = {
            "name": "app", "version": "1.0",
            "requires_python": None, "dependencies": [],
            "optional_dependencies": {}, "scripts": {},
        }
        self.checker.check_dependencies.return_value = ([], [], 0, "")
        config = self._user_config(tmp_path)
        with patch(
            "linux_python_utils.scripts.installer.ScriptPaths"
        ) as mock_cls, patch(
            "linux_python_utils.scripts.installer.sys.stdin.isatty",
            return_value=True,
        ), patch("builtins.input", return_value="n"), \
             patch("builtins.print"):
            mock_cls.return_value = self._patch_paths(tmp_path)
            report = self.installer.install(config, confirm_wrapper=True)
        assert report.success is False
        assert any("refusé" in w for w in report.warnings)

    def test_candidate_homes_sudo_user_keyerror(self):
        """_candidate_homes ignore KeyError si SUDO_USER est invalide."""
        with patch.dict(
            "linux_python_utils.scripts.installer.os.environ",
            {"SUDO_USER": "ghost"},
        ), patch(
            "linux_python_utils.scripts.installer.pwd.getpwnam",
            side_effect=KeyError("ghost"),
        ):
            homes = self.installer._candidate_homes()
        assert len(homes) == 1  # seulement Path.home()

    def test_run_uv_install_file_not_found(self, tmp_path):
        """_run_uv_install retourne False si uv binaire non trouvé."""
        config = self._user_config(tmp_path)
        with patch(
            "linux_python_utils.scripts.installer.shutil.which",
            return_value="/fake/uv",
        ), patch(
            "subprocess.run", side_effect=FileNotFoundError
        ):
            assert self.installer._run_uv_install(config) is False

    def test_run_uv_install_returncode_nonzero_sans_logger(
        self, tmp_path
    ):
        """_run_uv_install retourne False sur returncode != 0 sans logger."""
        config = self._user_config(tmp_path)
        with patch(
            "linux_python_utils.scripts.installer.shutil.which",
            return_value="/usr/bin/uv",
        ), patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1, stderr="uv error"
            )
            assert self.installer._run_uv_install(config) is False

    def test_run_uv_introuvable_sans_logger(self, tmp_path):
        """_run_uv_install retourne False si uv introuvable sans logger."""
        config = self._user_config(tmp_path)
        with patch(
            "linux_python_utils.scripts.installer.shutil.which",
            return_value=None,
        ), patch(
            "linux_python_utils.scripts.installer.Path.home",
            return_value=tmp_path / "empty",
        ), patch.dict(
            "linux_python_utils.scripts.installer.os.environ", {}, clear=True
        ):
            assert self.installer._run_uv_install(config) is False

    def test_write_wrapper_sans_logger(self, tmp_path):
        """_write_wrapper crée le fichier sans logger."""
        target = tmp_path / "bin" / "app"
        installer = LinuxCliInstaller(None, MagicMock())
        installer._write_wrapper("#!/bin/bash\n", target)
        assert target.exists()

    def test_preconditions_valueerror_sans_logger(self, tmp_path):
        """_check_preconditions retourne échec sur ValueError sans logger."""
        self.checker.check_python.return_value = True
        self.checker.read_pyproject.side_effect = ValueError(
            "Section [project] manquante"
        )
        config = self._user_config(tmp_path)
        with patch(
            "linux_python_utils.scripts.installer.ScriptPaths"
        ) as mock_cls:
            mock_cls.return_value = self._patch_paths(tmp_path)
            report = self.installer.install(config, confirm_wrapper=False)
        assert report.success is False

    def test_venv_ok_ne_cree_pas_warning(self, tmp_path):
        """Aucun warning venv si check_venv retourne True."""
        venv = tmp_path / "venv"
        self.checker.check_python.return_value = True
        self.checker.read_pyproject.return_value = {
            "name": "app", "version": "1.0",
            "requires_python": None, "dependencies": [],
            "optional_dependencies": {}, "scripts": {"app": "app:main"},
        }
        self.checker.check_dependencies.return_value = ([], [], 0, "")
        self.checker.check_venv.return_value = True
        config = PythonCliConfig(
            name="app", deploy_type="user",
            source_dir=tmp_path, venv_path=venv,
        )
        with patch(
            "linux_python_utils.scripts.installer.ScriptPaths"
        ) as mock_cls, patch("subprocess.run") as mock_run, \
             patch(
                 "linux_python_utils.scripts.installer.shutil.which",
                 return_value="/usr/bin/uv",
             ):
            mock_cls.return_value = self._patch_paths(tmp_path)
            mock_run.return_value = MagicMock(returncode=0, stderr="")
            report = self.installer.install(config, confirm_wrapper=False)
        assert all("Venv" not in w for w in report.warnings)

    def test_handle_wrapper_refuse_interactif_accepte(self, tmp_path):
        """Wrapper accepté interactivement (réponse 'o')."""
        logger = MagicMock()
        checker = MagicMock()
        installer = LinuxCliInstaller(logger, checker)
        checker.check_python.return_value = True
        checker.read_pyproject.return_value = {
            "name": "app", "version": "1.0",
            "requires_python": None, "dependencies": [],
            "optional_dependencies": {}, "scripts": {},
        }
        checker.check_dependencies.return_value = ([], [], 0, "")
        config = self._user_config(tmp_path)
        with patch(
            "linux_python_utils.scripts.installer.ScriptPaths"
        ) as mock_cls, patch(
            "linux_python_utils.scripts.installer.sys.stdin.isatty",
            return_value=True,
        ), patch("builtins.input", return_value="o"), \
             patch("builtins.print"), patch.object(
                 installer, "_write_wrapper"
             ) as mock_write, patch("subprocess.run") as mock_run, \
             patch(
                 "linux_python_utils.scripts.installer.shutil.which",
                 return_value="/usr/bin/uv",
             ):
            mock_cls.return_value = self._patch_paths(tmp_path)
            mock_run.return_value = MagicMock(returncode=0, stderr="")
            report = installer.install(config, confirm_wrapper=True)
        mock_write.assert_called_once()
        assert report.success is True

    def test_wrapper_echec_oserror_sans_logger(self, tmp_path):
        """Wrapper OSError sans logger → rapport d'échec."""
        self.checker.check_python.return_value = True
        self.checker.read_pyproject.return_value = {
            "name": "app", "version": "1.0",
            "requires_python": None, "dependencies": [],
            "optional_dependencies": {}, "scripts": {},
        }
        self.checker.check_dependencies.return_value = ([], [], 0, "")
        config = self._user_config(tmp_path)
        with patch(
            "linux_python_utils.scripts.installer.ScriptPaths"
        ) as mock_cls, patch.object(
            self.installer,
            "_write_wrapper",
            side_effect=OSError("perm"),
        ):
            mock_paths = MagicMock()
            mock_paths.bin_path = tmp_path / "bin" / "app"
            mock_cls.return_value = mock_paths
            report = self.installer.install(config, confirm_wrapper=False)
        assert report.success is False

    def test_run_uv_intro_uvable_avec_logger(self, tmp_path):
        """_run_uv_install retourne False et logue si uv introuvable (avec logger)."""
        logger = MagicMock()
        installer = LinuxCliInstaller(logger, MagicMock())
        config = self._user_config(tmp_path)
        with patch(
            "linux_python_utils.scripts.installer.shutil.which",
            return_value=None,
        ), patch(
            "linux_python_utils.scripts.installer.Path.home",
            return_value=tmp_path / "empty",
        ), patch.dict(
            "linux_python_utils.scripts.installer.os.environ", {}, clear=True
        ):
            assert installer._run_uv_install(config) is False
        logger.log_error.assert_called()

    def test_run_uv_file_not_found_avec_logger(self, tmp_path):
        """_run_uv_install logue si FileNotFoundError avec logger."""
        logger = MagicMock()
        installer = LinuxCliInstaller(logger, MagicMock())
        config = self._user_config(tmp_path)
        with patch(
            "linux_python_utils.scripts.installer.shutil.which",
            return_value="/fake/uv",
        ), patch("subprocess.run", side_effect=FileNotFoundError):
            assert installer._run_uv_install(config) is False
        logger.log_error.assert_called()

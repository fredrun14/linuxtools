"""Tests pour le module scripts."""

import os
import tomllib
from pathlib import Path
from unittest.mock import MagicMock, patch, mock_open
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

        with patch("os.open", return_value=3) as mock_open, \
                patch("os.fchmod") as mock_fchmod, \
                patch("os.close"):
            self.installer.install("/tmp/test.sh", self.config)
            mock_open.assert_called_once_with(
                "/tmp/test.sh", os.O_RDONLY | os.O_NOFOLLOW
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
        defaults = dict(
            success=True,
            app_name="app",
            deploy_type="user",
            install_path=Path("/home/user/.local/bin/app"),
        )
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
            "linux_python_utils.scripts.paths.user_data_dir",
            return_value="/home/user/.local/share/mon-app",
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
            missing, total, _ = self.checker.check_dependencies(
                pyproject, None, []
            )
        assert missing == []
        assert total == 1

    def test_missing_package_in_report(self, tmp_path):
        """Vérifie que le paquet manquant apparaît dans missing."""
        pyproject = self._make_pyproject(tmp_path, ["click>=8.0"])
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1)
            missing, total, _ = self.checker.check_dependencies(
                pyproject, None, []
            )
        assert len(missing) == 1
        assert missing[0].package == "click"

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
            _, total, _ = self.checker.check_dependencies(
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
        self.checker.check_dependencies.return_value = ([], 0, "")
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
        self.checker.check_dependencies.return_value = ([], 0, "")
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
        self.checker.check_dependencies.return_value = ([], 0, "")
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

    def test_system_type_uses_sudo_in_command(self, tmp_path):
        """Vérifie que sudo est inclus dans la commande uv pour system."""
        self.checker.check_python.return_value = True
        self.checker.read_pyproject.return_value = {
            "name": "app", "version": "1.0",
            "requires_python": None, "dependencies": [],
            "optional_dependencies": {}, "scripts": {"app": "app:main"},
        }
        self.checker.check_dependencies.return_value = ([], 0, "")
        config = PythonCliConfig(
            name="app", deploy_type="system", source_dir=tmp_path
        )
        with patch(
            "linux_python_utils.scripts.installer.ScriptPaths"
        ) as mock_cls, \
             patch("subprocess.run") as mock_run:
            mock_cls.return_value = self._patch_paths(tmp_path)
            mock_run.return_value = MagicMock(returncode=0, stderr="")
            self.installer.install(config, confirm_wrapper=False)
            cmd = mock_run.call_args[0][0]
        assert "sudo" in cmd

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
            [missing_dep], 1, "pip3 install -e '/app'"
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

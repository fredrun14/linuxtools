"""Tests pour le module scripts."""

import os
from pathlib import Path
from typing import Any, Callable
from unittest.mock import MagicMock, patch

import pytest

from linuxtools.commands.base import CommandExecutor, CommandResult
from linuxtools.notification import NotificationConfig
from linuxtools.scripts import (
    BashScriptConfig,
    BashScriptInstaller,
    PythonCliConfig,
    ScriptPaths,
    LinuxScriptChecker,
    InstallReport,
    MissingDependency,
    LinuxCliInstaller,
)


def _result(
    success: bool = True,
    stdout: str = "",
    stderr: str = "",
    return_code: int | None = None,
) -> CommandResult:
    """Construit un CommandResult scripté pour les tests.

    Args:
        success: Statut de réussite simulé.
        stdout: Sortie standard simulée.
        stderr: Sortie d'erreur simulée.
        return_code: Code retour explicite (déduit de success si None).

    Returns:
        CommandResult immuable prêt à être retourné par un mock.
    """
    return CommandResult(
        command=(),
        return_code=(
            return_code if return_code is not None else (0 if success else 1)
        ),
        stdout=stdout,
        stderr=stderr,
        success=success,
        duration=0.0,
    )


def _make_executor() -> MagicMock:
    """Crée un mock de CommandExecutor respectant l'ABC (spec)."""
    return MagicMock(spec=CommandExecutor)


def _probe_dispatch(
    uv_found: str | None = "/usr/bin/uv",
    uid: str = "1000",
    home: str = "/home/user",
    sudo_user: str = "",
) -> Callable[..., CommandResult]:
    """Fabrique une fonction de dispatch pour ``executor.probe``.

    Route chaque appel de sonde (``command -v uv``, ``id -u``,
    ``echo $HOME``, ``echo $SUDO_USER``) vers un CommandResult
    scripté selon la commande passée, pour simuler _find_uv,
    _candidate_homes et _is_target_root sans dépendre de l'hôte
    réel qui exécute les tests.

    Args:
        uv_found: Chemin de uv retourné par ``command -v uv``, ou
            None pour simuler son absence du PATH.
        uid: UID cible retourné par ``id -u``.
        home: Home retourné par ``echo $HOME``.
        sudo_user: Valeur de ``$SUDO_USER`` (vide = absent).

    Returns:
        Fonction utilisable comme ``side_effect`` de ``probe``.
    """

    def _dispatch(command: list[str], *args: Any, **kwargs: Any) -> CommandResult:
        if command == ["sh", "-c", "command -v uv"]:
            if uv_found:
                return _result(success=True, stdout=f"{uv_found}\n")
            return _result(success=False)
        if command == ["id", "-u"]:
            return _result(success=True, stdout=f"{uid}\n")
        if command == ["sh", "-c", "echo $HOME"]:
            return _result(success=True, stdout=f"{home}\n")
        if command == ["sh", "-c", "echo $SUDO_USER"]:
            return _result(success=True, stdout=f"{sudo_user}\n")
        return _result(success=False)

    return _dispatch


class TestBashScriptConfig:
    """Tests pour la dataclass BashScriptConfig."""

    def test_creation_with_command_only(self) -> None:
        """Vérifie la création avec uniquement la commande."""
        config = BashScriptConfig(exec_command="echo 'Hello'")
        assert config.exec_command == "echo 'Hello'"
        assert config.notification is None

    def test_creation_with_notification(self) -> None:
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

    def test_raises_on_empty_exec_command(self) -> None:
        """Vérifie l'erreur si exec_command est vide."""
        with pytest.raises(ValueError, match="exec_command est requis"):
            BashScriptConfig(exec_command="")

    def test_is_frozen(self) -> None:
        """Vérifie que la dataclass est immutable."""
        config = BashScriptConfig(exec_command="echo test")
        with pytest.raises(AttributeError):
            # Test d'immutabilité intentionnel : l'erreur mypy confirme
            # le contrat testé (dataclass frozen).
            config.exec_command = "autre commande"  # type: ignore[misc]


class TestBashScriptConfigToBashScript:
    """Tests pour BashScriptConfig.to_bash_script()."""

    def test_simple_script_starts_with_shebang(self) -> None:
        """Vérifie que le script simple commence par le shebang."""
        config = BashScriptConfig(exec_command="echo 'Hello'")
        result = config.to_bash_script()
        assert result.startswith("#!/bin/bash")

    def test_simple_script_contains_command(self) -> None:
        """Vérifie que le script simple contient la commande."""
        config = BashScriptConfig(exec_command="/usr/bin/flatpak update -y")
        result = config.to_bash_script()
        assert "/usr/bin/flatpak update -y" in result

    def test_simple_script_is_minimal(self) -> None:
        """Vérifie que le script simple est minimal (pas de notification)."""
        config = BashScriptConfig(exec_command="echo test")
        result = config.to_bash_script()
        assert "send_notification" not in result
        assert "exit_code" not in result

    def test_script_with_notification_contains_function(self) -> None:
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

    def test_script_with_notification_captures_exit_code(self) -> None:
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

    def test_script_with_notification_has_conditional(self) -> None:
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

    def test_script_with_notification_uses_config_values(self) -> None:
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

    def setup_method(self) -> None:
        """Initialise les mocks pour chaque test."""
        self.mock_logger = MagicMock()
        self.mock_file_manager = MagicMock()
        self.installer = BashScriptInstaller(
            self.mock_logger,
            self.mock_file_manager
        )
        self.config = BashScriptConfig(exec_command="echo 'test'")

    def test_install_creates_file_when_not_exists(self) -> None:
        """Vérifie que le fichier est créé s'il n'existe pas."""
        self.mock_file_manager.file_exists.return_value = False
        self.mock_file_manager.create_file.return_value = True

        with patch("os.open", return_value=3), \
                patch("os.fchmod"), patch("os.close"):
            result = self.installer.install("/tmp/test.sh", self.config)

        assert result is True
        self.mock_file_manager.create_file.assert_called_once()

    def test_install_skips_existing_file(self) -> None:
        """Vérifie que l'installation est ignorée si le fichier existe."""
        self.mock_file_manager.file_exists.return_value = True

        result = self.installer.install("/tmp/test.sh", self.config)

        assert result is True
        self.mock_file_manager.create_file.assert_not_called()
        self.mock_logger.log_info.assert_called()

    def test_install_returns_false_on_create_failure(self) -> None:
        """Vérifie le retour False si la création échoue."""
        self.mock_file_manager.file_exists.return_value = False
        self.mock_file_manager.create_file.return_value = False

        result = self.installer.install("/tmp/test.sh", self.config)

        assert result is False
        self.mock_logger.log_error.assert_called()

    def test_install_sets_executable_permission(self) -> None:
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

    def test_install_returns_false_on_chmod_failure(self) -> None:
        """Vérifie le retour False si les permissions ne peuvent pas être appliquées."""
        self.mock_file_manager.file_exists.return_value = False
        self.mock_file_manager.create_file.return_value = True

        with patch("os.open", side_effect=OSError("Permission denied")):
            result = self.installer.install("/tmp/test.sh", self.config)

        assert result is False
        self.mock_logger.log_error.assert_called()

    def test_install_generates_correct_content(self) -> None:
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

    def test_exists_delegates_to_file_manager(self) -> None:
        """Vérifie que exists() délègue au file_manager."""
        self.mock_file_manager.file_exists.return_value = True

        result = self.installer.exists("/tmp/test.sh")

        assert result is True
        self.mock_file_manager.file_exists.assert_called_once_with(
            "/tmp/test.sh"
        )

    def test_custom_default_mode(self) -> None:
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

    def setup_method(self) -> None:
        """Initialise les mocks avant chaque test."""
        self.mock_logger = MagicMock()
        self.mock_file_manager = MagicMock()
        self.installer = BashScriptInstaller(
            self.mock_logger,
            self.mock_file_manager
        )

    def test_set_executable_refuse_les_symlinks(self, tmp_path: Path) -> None:
        """_set_executable() retourne False et logue si le chemin est un symlink."""
        real_file = tmp_path / "target.sh"
        real_file.write_text("#!/bin/bash\n")
        symlink = tmp_path / "link.sh"
        symlink.symlink_to(real_file)

        result = self.installer._set_executable(str(symlink))

        assert result is False
        self.mock_logger.log_error.assert_called_once()

    def test_set_executable_applique_le_mode_correct(self, tmp_path: Path) -> None:
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

    def test_valid_user_config_creates_instance(self, tmp_path: Path) -> None:
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

    def test_valid_system_config_creates_instance(self, tmp_path: Path) -> None:
        """Vérifie la création avec un type system valide."""
        config = PythonCliConfig(
            name="svc",
            deploy_type="system",
            source_dir=tmp_path,
        )
        assert config.deploy_type == "system"

    def test_empty_name_raises_value_error(self, tmp_path: Path) -> None:
        """Vérifie l'erreur si name est vide."""
        with pytest.raises(ValueError, match="name est requis"):
            PythonCliConfig(
                name="",
                deploy_type="user",
                source_dir=tmp_path,
            )

    def test_whitespace_name_raises_value_error(self, tmp_path: Path) -> None:
        """Vérifie l'erreur si name ne contient que des espaces."""
        with pytest.raises(ValueError, match="name est requis"):
            PythonCliConfig(
                name="   ",
                deploy_type="user",
                source_dir=tmp_path,
            )

    def test_invalid_deploy_type_raises_value_error(self, tmp_path: Path) -> None:
        """Vérifie l'erreur si deploy_type est invalide."""
        with pytest.raises(ValueError, match="deploy_type invalide"):
            PythonCliConfig(
                name="app",
                deploy_type="global",  # type: ignore[arg-type]
                source_dir=tmp_path,
            )

    def test_config_name_traversal_leve_valueerror(self, tmp_path: Path) -> None:
        """Un nom de traversal path-traversal lève ValueError."""
        with pytest.raises(ValueError, match="name invalide"):
            PythonCliConfig(
                name="../../etc/cron.d/x",
                deploy_type="user",
                source_dir=tmp_path,
            )

    def test_config_name_caracteres_interdits_leve_valueerror(
        self, tmp_path: Path
    ) -> None:
        """Un name avec slash ou espace lève ValueError."""
        for bad in ("/etc/passwd", "my app", "app;rm -rf /"):
            with pytest.raises(ValueError, match="name invalide"):
                PythonCliConfig(
                    name=bad,
                    deploy_type="user",
                    source_dir=tmp_path,
                )

    def test_config_is_frozen(self, tmp_path: Path) -> None:
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

    def _make_report(self, **kwargs: Any) -> InstallReport:
        defaults: dict[str, Any] = {
            "success": True,
            "app_name": "app",
            "deploy_type": "user",
            "install_path": Path("/home/user/.local/bin/app"),
        }
        defaults.update(kwargs)
        return InstallReport(**defaults)

    def test_deps_satisfied_true_when_no_missing(self) -> None:
        """Vérifie deps_satisfied quand aucune dépendance manque."""
        report = self._make_report(total_deps=3)
        assert report.deps_satisfied is True

    def test_deps_satisfied_false_when_missing(self) -> None:
        """Vérifie deps_satisfied quand des dépendances manquent."""
        report = self._make_report(
            missing_deps=[MissingDependency("requests", ">=2.0")]
        )
        assert report.deps_satisfied is False

    def test_format_summary_success_contains_app_name(self) -> None:
        """Vérifie que le résumé contient le nom de l'app."""
        report = self._make_report()
        summary = report.format_summary()
        assert "app" in summary
        assert "✓" in summary

    def test_format_summary_failure_shows_echec(self) -> None:
        """Vérifie que le résumé indique l'échec."""
        report = self._make_report(success=False)
        assert "✗" in report.format_summary()

    def test_format_summary_includes_missing_deps(self) -> None:
        """Vérifie que les dépendances manquantes apparaissent."""
        report = self._make_report(
            total_deps=2,
            missing_deps=[MissingDependency("requests", ">=2.0")],
        )
        summary = report.format_summary()
        assert "requests" in summary
        assert ">=2.0" in summary

    def test_format_summary_includes_install_command(self) -> None:
        """Vérifie que la commande d'installation apparaît."""
        report = self._make_report(
            total_deps=1,
            missing_deps=[MissingDependency("click", ">=8.0")],
            install_command="pip3 install -e '/app'",
        )
        assert "pip3 install" in report.format_summary()

    def test_format_summary_includes_warnings(self) -> None:
        """Vérifie que les warnings apparaissent dans le résumé."""
        report = self._make_report(warnings=["Venv inaccessible"])
        assert "Venv inaccessible" in report.format_summary()


# ---------------------------------------------------------------------------
# ScriptPaths
# ---------------------------------------------------------------------------

class TestScriptPaths:
    """Tests pour ScriptPaths (chemins FHS via platformdirs)."""

    def test_user_data_dir_ends_with_app_name(self) -> None:
        """Vérifie que data_dir se termine par le nom de l'app (user)."""
        with patch(
            "linuxtools.scripts.paths.user_data_dir",
            return_value="/home/user/.local/share/mon-app",
        ):
            paths = ScriptPaths("mon-app", "user")
            assert paths.data_dir == Path("/home/user/.local/share/mon-app")

    def test_system_data_dir_returns_usr_local_share(self) -> None:
        """Vérifie que data_dir pointe vers /usr/local/share (system)."""
        with patch(
            "linuxtools.scripts.paths.site_data_dir",
            return_value="/usr/local/share/mon-app",
        ):
            paths = ScriptPaths("mon-app", "system")
            assert paths.data_dir == Path("/usr/local/share/mon-app")

    def test_user_bin_path_returns_local_bin(self) -> None:
        """Vérifie que bin_path est dans ~/.local/bin (user)."""
        with patch(
            "linuxtools.scripts.paths.Path.home",
            return_value=Path("/home/user"),
        ):
            paths = ScriptPaths("mon-app", "user")
            assert paths.bin_path == Path("/home/user/.local/bin/mon-app")

    def test_system_bin_path_returns_usr_local_bin(self) -> None:
        """Vérifie que bin_path est dans /usr/local/bin (system)."""
        with patch(
            "linuxtools.scripts.paths.site_data_dir",
            return_value="/usr/local/share/mon-app",
        ):
            paths = ScriptPaths("mon-app", "system")
            assert paths.bin_path == Path("/usr/local/bin/mon-app")

    def test_venv_dir_is_inside_data_dir(self) -> None:
        """Vérifie que venv_dir est un sous-répertoire de data_dir."""
        with patch(
            "linuxtools.scripts.paths.user_data_dir",
            return_value="/home/user/.local/share/app",
        ):
            paths = ScriptPaths("app", "user")
            assert paths.venv_dir == paths.data_dir / "venv"

    def test_wrapper_path_equals_bin_path(self) -> None:
        """Vérifie que wrapper_path est un alias de bin_path."""
        with patch(
            "linuxtools.scripts.paths.user_data_dir",
            return_value="/home/user/.local/share/app",
        ):
            paths = ScriptPaths("app", "user")
            assert paths.wrapper_path == paths.bin_path

    def test_user_config_dir_returns_dot_config(self) -> None:
        """Vérifie config_dir pour user."""
        with patch(
            "linuxtools.scripts.paths.user_data_dir",
            return_value="/home/user/.local/share/app",
        ):
            paths = ScriptPaths("app", "user")
            assert ".config" in str(paths.config_dir)
            assert "app" in str(paths.config_dir)

    def test_system_config_dir_returns_etc(self) -> None:
        """Vérifie config_dir pour system."""
        with patch(
            "linuxtools.scripts.paths.site_data_dir",
            return_value="/usr/local/share/app",
        ):
            paths = ScriptPaths("app", "system")
            assert paths.config_dir == Path("/etc/app")


# ---------------------------------------------------------------------------
# LinuxScriptChecker
# ---------------------------------------------------------------------------

class TestLinuxScriptCheckerPython:
    """Tests pour LinuxScriptChecker.check_python()."""

    def setup_method(self) -> None:
        self.logger = MagicMock()
        self.executor = _make_executor()
        self.checker = LinuxScriptChecker(self.executor, self.logger)

    def test_returns_true_when_python_available(self) -> None:
        """Vérifie True si python3 est disponible et sans version requise."""
        self.executor.probe.side_effect = [
            _result(success=True),
            _result(success=True, stdout="Python 3.11.2\n"),
        ]
        assert self.checker.check_python() is True

    def test_returns_false_when_exec_missing(self) -> None:
        """Vérifie False si /usr/bin/python3 n'existe pas."""
        self.executor.probe.return_value = _result(success=False)
        assert self.checker.check_python() is False
        self.logger.log_error.assert_called()

    def test_returns_false_when_version_too_old(self) -> None:
        """Vérifie False si la version est insuffisante."""
        self.executor.probe.side_effect = [
            _result(success=True),
            _result(success=True, stdout="Python 3.10.0\n"),
        ]
        assert self.checker.check_python("3.11") is False
        self.logger.log_error.assert_called()

    def test_returns_true_when_version_satisfied(self) -> None:
        """Vérifie True si la version satisfait le minimum requis."""
        self.executor.probe.side_effect = [
            _result(success=True),
            _result(success=True, stdout="Python 3.12.1\n"),
        ]
        assert self.checker.check_python("3.11") is True

    def test_returns_true_when_version_illisible(self) -> None:
        """Retourne True et logue si version Python illisible."""
        self.executor.probe.side_effect = [
            _result(success=True),
            _result(success=True, stdout="Python\n"),
        ]
        assert self.checker.check_python("3.11") is True
        self.logger.log_info.assert_called()


class TestLinuxScriptCheckerScript:
    """Tests pour LinuxScriptChecker.check_script_syntax()."""

    def setup_method(self) -> None:
        self.logger = MagicMock()
        self.executor = _make_executor()
        self.checker = LinuxScriptChecker(self.executor, self.logger)

    def test_returns_true_for_valid_script(self, tmp_path: Path) -> None:
        """Vérifie True pour un script syntaxiquement correct."""
        script = tmp_path / "main.py"
        self.executor.probe.return_value = _result(success=True)
        self.executor.run.return_value = _result(success=True)
        assert self.checker.check_script_syntax(script) is True
        self.executor.run.assert_called_once_with(
            ["/usr/bin/python3", "-m", "py_compile", str(script)],
            timeout=60,
        )

    def test_returns_false_when_not_found(self, tmp_path: Path) -> None:
        """Vérifie False si le script n'existe pas."""
        self.executor.probe.return_value = _result(success=False)
        assert self.checker.check_script_syntax(
            tmp_path / "missing.py"
        ) is False
        self.logger.log_error.assert_called()

    def test_returns_false_when_syntax_error(self, tmp_path: Path) -> None:
        """Vérifie False si py_compile détecte une erreur."""
        script = tmp_path / "bad.py"
        self.executor.probe.return_value = _result(success=True)
        self.executor.run.return_value = _result(
            success=False, stderr="SyntaxError"
        )
        assert self.checker.check_script_syntax(script) is False
        self.logger.log_error.assert_called()


class TestLinuxScriptCheckerVenv:
    """Tests pour LinuxScriptChecker.check_venv()."""

    def setup_method(self) -> None:
        self.logger = MagicMock()
        self.executor = _make_executor()
        self.checker = LinuxScriptChecker(self.executor, self.logger)

    def test_returns_true_when_venv_valid(self, tmp_path: Path) -> None:
        """Vérifie True si le venv est fonctionnel."""
        self.executor.probe.side_effect = [
            _result(success=True),  # test -d
            _result(success=True),  # test -f python_bin
            _result(success=True),  # --version
        ]
        assert self.checker.check_venv(tmp_path) is True

    def test_returns_false_when_venv_missing(self, tmp_path: Path) -> None:
        """Vérifie False si le répertoire venv n'existe pas."""
        self.executor.probe.return_value = _result(success=False)
        assert self.checker.check_venv(tmp_path / "novenv") is False
        self.logger.log_error.assert_called()

    def test_returns_false_when_python_bin_missing(self, tmp_path: Path) -> None:
        """Vérifie False si l'interpréteur est absent."""
        self.executor.probe.side_effect = [
            _result(success=True),
            _result(success=False),
        ]
        assert self.checker.check_venv(tmp_path) is False
        self.logger.log_error.assert_called()

    def test_returns_false_when_venv_interpreter_nonfonctionnel(
        self, tmp_path: Path
    ) -> None:
        """Retourne False et logue si l'interpréteur venv ne répond pas."""
        self.executor.probe.side_effect = [
            _result(success=True),
            _result(success=True),
            _result(success=False),
        ]
        assert self.checker.check_venv(tmp_path) is False
        self.logger.log_error.assert_called()


class TestLinuxScriptCheckerPyproject:
    """Tests pour LinuxScriptChecker.read_pyproject()."""

    def setup_method(self) -> None:
        self.logger = MagicMock()
        self.executor = _make_executor()
        self.checker = LinuxScriptChecker(self.executor, self.logger)

    def test_returns_data_when_valid(self, tmp_path: Path) -> None:
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

    def test_raises_file_not_found_when_missing(self, tmp_path: Path) -> None:
        """Vérifie FileNotFoundError si le fichier n'existe pas."""
        with pytest.raises(FileNotFoundError):
            self.checker.read_pyproject(tmp_path / "missing.toml")

    def test_raises_value_error_missing_project_section(self, tmp_path: Path) -> None:
        """Vérifie ValueError si [project] est absent."""
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_bytes(b'[build-system]\nrequires = []\n')
        with pytest.raises(ValueError, match="Section \\[project\\]"):
            self.checker.read_pyproject(pyproject)

    def test_returns_scripts_dict_when_present(self, tmp_path: Path) -> None:
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

    def setup_method(self) -> None:
        self.logger = MagicMock()
        self.executor = _make_executor()
        self.checker = LinuxScriptChecker(self.executor, self.logger)

    def _make_pyproject(self, tmp_path: Path, deps: list[str]) -> Path:
        pyproject = tmp_path / "pyproject.toml"
        deps_toml = "\n".join(f'  "{d}",' for d in deps)
        content = (
            f'[project]\nname = "app"\ndependencies = [\n{deps_toml}\n]\n'
        ).encode()
        pyproject.write_bytes(content)
        return pyproject

    def test_all_installed_returns_empty_missing(self, tmp_path: Path) -> None:
        """Vérifie liste vide si toutes les deps sont installées."""
        pyproject = self._make_pyproject(tmp_path, ["requests>=2.0"])
        self.executor.probe.return_value = _result(
            success=True, stdout="Location: /usr/lib/python3.11\n"
        )
        missing, installed, total, _ = self.checker.check_dependencies(
            pyproject, None, []
        )
        assert missing == []
        assert len(installed) == 1
        assert total == 1

    def test_missing_package_in_report(self, tmp_path: Path) -> None:
        """Vérifie que le paquet manquant apparaît dans missing."""
        pyproject = self._make_pyproject(tmp_path, ["click>=8.0"])
        self.executor.probe.return_value = _result(success=False)
        missing, _installed, total, _ = self.checker.check_dependencies(
            pyproject, None, []
        )
        assert len(missing) == 1
        assert missing[0].package == "click"

    def test_checker_venv_cible_utilise_pip_du_venv(
        self, tmp_path: Path
    ) -> None:
        """check_dependencies interroge le pip du venv cible fourni."""
        pyproject = self._make_pyproject(tmp_path, ["requests>=2.0"])
        self.executor.probe.return_value = _result(
            success=True, stdout="Location: /venv/lib\n"
        )
        venv_path = tmp_path / "venv"
        self.checker.check_dependencies(pyproject, venv_path, [])
        called_cmd = self.executor.probe.call_args[0][0]
        assert called_cmd[0] == str(venv_path / "bin" / "pip")

    def test_extras_are_included(self, tmp_path: Path) -> None:
        """Vérifie que les extras sont inclus dans la vérification."""
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_bytes(
            b'[project]\nname = "app"\ndependencies = []\n'
            b'[project.optional-dependencies]\n'
            b'dev = ["pytest>=7.0"]\n'
        )
        self.executor.probe.return_value = _result(success=True)
        _, _installed, total, _ = self.checker.check_dependencies(
            pyproject, None, ["dev"]
        )
        assert total == 1


# ---------------------------------------------------------------------------
# LinuxCliInstaller
# ---------------------------------------------------------------------------

class TestLinuxCliInstaller:
    """Tests pour LinuxCliInstaller.install()."""

    def setup_method(self) -> None:
        self.logger = MagicMock()
        self.checker = MagicMock()
        self.executor = _make_executor()
        self.installer = LinuxCliInstaller(
            checker=self.checker, executor=self.executor, logger=self.logger
        )

    def _user_config(self, tmp_path: Path) -> PythonCliConfig:
        return PythonCliConfig(
            name="app",
            deploy_type="user",
            source_dir=tmp_path,
        )

    def _patch_paths(self, tmp_path: Path) -> MagicMock:
        """Retourne un patch de ScriptPaths avec des chemins tmp."""
        mock_paths = MagicMock()
        mock_paths.bin_path = tmp_path / "bin" / "app"
        mock_paths.data_dir = tmp_path / "data"
        return mock_paths

    def test_returns_failure_when_python_check_fails(self, tmp_path: Path) -> None:
        """Vérifie InstallReport(success=False) si python3 absent."""
        self.checker.check_python.return_value = False
        config = self._user_config(tmp_path)
        with patch(
            "linuxtools.scripts.installer.ScriptPaths"
        ) as mock_cls:
            mock_cls.return_value = self._patch_paths(tmp_path)
            report = self.installer.install(config, confirm_wrapper=False)
        assert report.success is False

    def test_returns_failure_when_pyproject_missing(self, tmp_path: Path) -> None:
        """Vérifie InstallReport(success=False) si pyproject.toml absent."""
        self.checker.check_python.return_value = True
        self.checker.read_pyproject.side_effect = FileNotFoundError(
            "pyproject.toml introuvable"
        )
        config = self._user_config(tmp_path)
        with patch(
            "linuxtools.scripts.installer.ScriptPaths"
        ) as mock_cls:
            mock_cls.return_value = self._patch_paths(tmp_path)
            report = self.installer.install(config, confirm_wrapper=False)
        assert report.success is False

    def test_returns_failure_when_uv_fails(self, tmp_path: Path) -> None:
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
            "linuxtools.scripts.installer.ScriptPaths"
        ) as mock_cls:
            mock_cls.return_value = self._patch_paths(tmp_path)
            self.executor.probe.side_effect = _probe_dispatch()
            self.executor.run.return_value = _result(
                success=False, stderr="uv error"
            )
            report = self.installer.install(config, confirm_wrapper=False)
        assert report.success is False

    def test_skips_wrapper_when_scripts_entry_exists(self, tmp_path: Path) -> None:
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
            "linuxtools.scripts.installer.ScriptPaths"
        ) as mock_cls, patch.object(
            self.installer, "_write_wrapper"
        ) as mock_write:
            mock_cls.return_value = self._patch_paths(tmp_path)
            self.executor.probe.side_effect = _probe_dispatch()
            self.executor.run.return_value = _result(success=True)
            self.installer.install(config, confirm_wrapper=False)
        mock_write.assert_not_called()

    def test_generates_wrapper_when_no_scripts_entry(self, tmp_path: Path) -> None:
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
            "linuxtools.scripts.installer.ScriptPaths"
        ) as mock_cls, patch.object(
            self.installer, "_write_wrapper"
        ) as mock_write:
            mock_cls.return_value = self._patch_paths(tmp_path)
            self.executor.probe.side_effect = _probe_dispatch()
            self.executor.run.return_value = _result(success=True)
            self.installer.install(config, confirm_wrapper=False)
        mock_write.assert_called_once()

    def _run_system_install_cmd(
        self, tmp_path: Path, target_uid: str
    ) -> list[str]:
        """Lance un install system mocké et retourne la commande uv.

        Args:
            tmp_path: Répertoire temporaire pytest.
            target_uid: UID cible simulé (retour de ``id -u``).

        Returns:
            La liste d'arguments passée à ``executor.run``.
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
            "linuxtools.scripts.installer.ScriptPaths"
        ) as mock_cls:
            mock_cls.return_value = self._patch_paths(tmp_path)
            self.executor.probe.side_effect = _probe_dispatch(
                uid=target_uid
            )
            self.executor.run.return_value = _result(success=True)
            self.installer.install(config, confirm_wrapper=False)
            return list(self.executor.run.call_args[0][0])

    def test_system_avec_sudo_si_non_root(self, tmp_path: Path) -> None:
        """sudo présent dans la commande system si la cible n'est pas root."""
        cmd = self._run_system_install_cmd(tmp_path, target_uid="1000")
        assert cmd[0] == "sudo"

    def test_system_sans_sudo_si_root(self, tmp_path: Path) -> None:
        """sudo absent de la commande system si la cible est déjà root."""
        cmd = self._run_system_install_cmd(tmp_path, target_uid="0")
        assert "sudo" not in cmd
        assert cmd[0] == "env"

    def test_missing_deps_recorded_in_report(self, tmp_path: Path) -> None:
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
            "linuxtools.scripts.installer.ScriptPaths"
        ) as mock_cls:
            mock_cls.return_value = self._patch_paths(tmp_path)
            self.executor.probe.side_effect = _probe_dispatch()
            self.executor.run.return_value = _result(success=True)
            report = self.installer.install(config, confirm_wrapper=False)
        assert len(report.missing_deps) == 1
        assert report.success is True

    def test_find_uv_prefere_le_path(self) -> None:
        """_find_uv retourne le résultat de ``command -v uv`` en priorité."""
        self.executor.probe.side_effect = _probe_dispatch(
            uv_found="/usr/bin/uv"
        )
        assert self.installer._find_uv() == "/usr/bin/uv"

    def test_find_uv_repli_local_bin(self) -> None:
        """_find_uv trouve uv dans ~/.local/bin si absent du PATH."""

        def dispatch(command: list[str], *a: Any, **kw: Any) -> CommandResult:
            if command == ["sh", "-c", "command -v uv"]:
                return _result(success=False)
            if command == ["sh", "-c", "echo $HOME"]:
                return _result(success=True, stdout="/home/user\n")
            if command == ["sh", "-c", "echo $SUDO_USER"]:
                return _result(success=True, stdout="\n")
            if command == ["test", "-x", "/home/user/.local/bin/uv"]:
                return _result(success=True)
            return _result(success=False)

        self.executor.probe.side_effect = dispatch
        assert self.installer._find_uv() == "/home/user/.local/bin/uv"

    def test_find_uv_repli_sudo_user(self) -> None:
        """_find_uv sonde le home de $SUDO_USER (cas sudo/root)."""

        def dispatch(command: list[str], *a: Any, **kw: Any) -> CommandResult:
            if command == ["sh", "-c", "command -v uv"]:
                return _result(success=False)
            if command == ["sh", "-c", "echo $HOME"]:
                return _result(success=True, stdout="/root\n")
            if command == ["sh", "-c", "echo $SUDO_USER"]:
                return _result(success=True, stdout="fred\n")
            if command == ["getent", "passwd", "fred"]:
                return _result(
                    success=True,
                    stdout="fred:x:1000:1000:Fred:/home/fred:/bin/bash\n",
                )
            if command == ["test", "-x", "/home/fred/.local/bin/uv"]:
                return _result(success=True)
            return _result(success=False)

        self.executor.probe.side_effect = dispatch
        assert self.installer._find_uv() == "/home/fred/.local/bin/uv"

    def test_find_uv_introuvable_retourne_none(self) -> None:
        """_find_uv retourne None si uv n'est nulle part."""
        self.executor.probe.side_effect = _probe_dispatch(uv_found=None)
        assert self.installer._find_uv() is None

    def test_candidate_homes_sudo_user_introuvable(self) -> None:
        """_candidate_homes ignore un $SUDO_USER dont getent échoue."""

        def dispatch(command: list[str], *a: Any, **kw: Any) -> CommandResult:
            if command == ["sh", "-c", "echo $HOME"]:
                return _result(success=True, stdout="/home/user\n")
            if command == ["sh", "-c", "echo $SUDO_USER"]:
                return _result(success=True, stdout="ghost\n")
            if command == ["getent", "passwd", "ghost"]:
                return _result(success=False)
            return _result(success=False)

        self.executor.probe.side_effect = dispatch
        homes = self.installer._candidate_homes()
        assert homes == ["/home/user"]

    def test_candidate_homes_home_probe_echoue(self) -> None:
        """_candidate_homes n'ajoute rien si la sonde $HOME échoue."""

        def dispatch(command: list[str], *a: Any, **kw: Any) -> CommandResult:
            if command == ["sh", "-c", "echo $HOME"]:
                return _result(success=False)
            if command == ["sh", "-c", "echo $SUDO_USER"]:
                return _result(success=True, stdout="\n")
            return _result(success=False)

        self.executor.probe.side_effect = dispatch
        homes = self.installer._candidate_homes()
        assert homes == []

    def test_candidate_homes_getent_ligne_malformee(self) -> None:
        """_candidate_homes ignore une ligne getent avec moins de 6 champs."""

        def dispatch(command: list[str], *a: Any, **kw: Any) -> CommandResult:
            if command == ["sh", "-c", "echo $HOME"]:
                return _result(success=True, stdout="/home/user\n")
            if command == ["sh", "-c", "echo $SUDO_USER"]:
                return _result(success=True, stdout="fred\n")
            if command == ["getent", "passwd", "fred"]:
                return _result(success=True, stdout="fred:x:1000\n")
            return _result(success=False)

        self.executor.probe.side_effect = dispatch
        homes = self.installer._candidate_homes()
        assert homes == ["/home/user"]


class TestLinuxCliInstallerWrapper:
    """Tests pour les méthodes privées de génération du wrapper."""

    def setup_method(self) -> None:
        self.logger = MagicMock()
        self.checker = MagicMock()
        self.executor = _make_executor()
        self.installer = LinuxCliInstaller(
            checker=self.checker, executor=self.executor, logger=self.logger
        )

    def test_strip_venv_block_removes_activate_block(self) -> None:
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

    def test_strip_venv_block_keeps_content_without_venv(self) -> None:
        """Vérifie que le contenu sans bloc venv reste intact."""
        content = "#!/bin/bash\nexec python main.py\n"
        result = LinuxCliInstaller._strip_venv_block(content)
        assert result == content

    def test_write_wrapper_sequence_appels_mockee(self, tmp_path: Path) -> None:
        """_write_wrapper enchaîne mkdir, mktemp, tee, chmod, test -L, mv."""
        target = tmp_path / "bin" / "app"
        tmp_file = str(tmp_path / "bin" / ".app.XXXXXX")
        self.executor.run.side_effect = [
            _result(success=True),  # mkdir -p
            _result(success=True, stdout=f"{tmp_file}\n"),  # mktemp
            _result(success=True),  # tee
            _result(success=True),  # chmod
            _result(success=True),  # mv
        ]
        self.executor.probe.return_value = _result(success=False)  # test -L

        self.installer._write_wrapper("#!/bin/bash\n", target)

        calls = self.executor.run.call_args_list
        assert calls[0][0][0] == ["mkdir", "-p", str(tmp_path / "bin")]
        assert calls[1][0][0][0] == "mktemp"
        assert calls[2][0][0] == ["tee", tmp_file]
        assert calls[2][1]["stdin"] == "#!/bin/bash\n"
        assert calls[3][0][0] == ["chmod", "0755", tmp_file]
        assert calls[4][0][0] == ["mv", tmp_file, str(target)]
        self.executor.probe.assert_called_once_with(
            ["test", "-L", str(target)]
        )
        self.logger.log_info.assert_called()

    def test_wrapper_refuse_symlink(self, tmp_path: Path) -> None:
        """_write_wrapper lève OSError et nettoie si target_path est un lien."""
        target = tmp_path / "link.sh"
        tmp_file = str(tmp_path / ".link.sh.XXXXXX")
        self.executor.run.side_effect = [
            _result(success=True),  # mkdir -p
            _result(success=True, stdout=f"{tmp_file}\n"),  # mktemp
            _result(success=True),  # tee
            _result(success=True),  # chmod
            _result(success=True),  # rm -f cleanup
        ]
        self.executor.probe.return_value = _result(success=True)  # test -L

        with pytest.raises(OSError, match="lien symbolique"):
            self.installer._write_wrapper("#!/bin/bash\n", target)

        last_call = self.executor.run.call_args_list[-1]
        assert last_call[0][0] == ["rm", "-f", tmp_file]

    def test_write_wrapper_mktemp_echoue(self, tmp_path: Path) -> None:
        """_write_wrapper lève OSError si mktemp échoue (pas de cleanup)."""
        target = tmp_path / "app"
        self.executor.run.side_effect = [
            _result(success=True),  # mkdir -p
            _result(success=False, stderr="mktemp: permission denied"),
        ]
        with pytest.raises(OSError, match="mktemp"):
            self.installer._write_wrapper("content", target)
        assert self.executor.run.call_count == 2

    def test_write_wrapper_tee_echoue_nettoie(self, tmp_path: Path) -> None:
        """_write_wrapper lève OSError et nettoie si tee échoue."""
        target = tmp_path / "app"
        tmp_file = str(tmp_path / ".app.XXXXXX")
        self.executor.run.side_effect = [
            _result(success=True),  # mkdir -p
            _result(success=True, stdout=f"{tmp_file}\n"),  # mktemp
            _result(success=False, stderr="disk full"),  # tee
            _result(success=True),  # rm -f
        ]
        with pytest.raises(OSError, match="écriture"):
            self.installer._write_wrapper("content", target)
        assert self.executor.run.call_args_list[-1][0][0] == [
            "rm", "-f", tmp_file
        ]

    def test_write_wrapper_chmod_echoue_nettoie(self, tmp_path: Path) -> None:
        """_write_wrapper lève OSError et nettoie si chmod échoue."""
        target = tmp_path / "app"
        tmp_file = str(tmp_path / ".app.XXXXXX")
        self.executor.run.side_effect = [
            _result(success=True),  # mkdir -p
            _result(success=True, stdout=f"{tmp_file}\n"),  # mktemp
            _result(success=True),  # tee
            _result(success=False, stderr="chmod refuse"),  # chmod
            _result(success=True),  # rm -f
        ]
        with pytest.raises(OSError, match="chmod"):
            self.installer._write_wrapper("content", target)
        assert self.executor.run.call_args_list[-1][0][0] == [
            "rm", "-f", tmp_file
        ]

    def test_write_wrapper_mv_echoue_nettoie(self, tmp_path: Path) -> None:
        """_write_wrapper lève OSError et nettoie si mv échoue."""
        target = tmp_path / "app"
        tmp_file = str(tmp_path / ".app.XXXXXX")
        self.executor.run.side_effect = [
            _result(success=True),  # mkdir -p
            _result(success=True, stdout=f"{tmp_file}\n"),  # mktemp
            _result(success=True),  # tee
            _result(success=True),  # chmod
            _result(success=False, stderr="mv: cross-device"),  # mv
            _result(success=True),  # rm -f
        ]
        self.executor.probe.return_value = _result(success=False)  # test -L
        with pytest.raises(OSError, match="déplacement"):
            self.installer._write_wrapper("content", target)
        assert self.executor.run.call_args_list[-1][0][0] == [
            "rm", "-f", tmp_file
        ]

    def test_write_wrapper_integration_reel(self, tmp_path: Path) -> None:
        """Non-régression : écrit un fichier réel, exécutable 0755."""
        from linuxtools.commands import LinuxCommandExecutor

        real_executor = LinuxCommandExecutor(logger=MagicMock())
        installer = LinuxCliInstaller(
            checker=MagicMock(), executor=real_executor, logger=MagicMock()
        )
        target = tmp_path / "bin" / "app"

        installer._write_wrapper("#!/bin/bash\necho hi\n", target)

        assert target.exists()
        assert target.read_text() == "#!/bin/bash\necho hi\n"
        assert oct(target.stat().st_mode & 0o777) == oct(0o755)

    def test_write_wrapper_integration_refuse_symlink_reel(
        self, tmp_path: Path
    ) -> None:
        """Non-régression : refuse un vrai symlink réel en position cible."""
        from linuxtools.commands import LinuxCommandExecutor

        real_executor = LinuxCommandExecutor(logger=MagicMock())
        installer = LinuxCliInstaller(
            checker=MagicMock(), executor=real_executor, logger=MagicMock()
        )
        real_file = tmp_path / "real.sh"
        real_file.write_text("#!/bin/bash\n")
        symlink = tmp_path / "link.sh"
        symlink.symlink_to(real_file)

        with pytest.raises(OSError, match="lien symbolique"):
            installer._write_wrapper("#!/bin/bash\n", symlink)
        assert real_file.read_text() == "#!/bin/bash\n"

    def test_write_wrapper_oserror_retourne_rapport_echec(
        self, tmp_path: Path
    ) -> None:
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
            "linuxtools.scripts.installer.ScriptPaths"
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

    def test_generate_wrapper_user_sans_venv(self, tmp_path: Path) -> None:
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

    def test_generate_wrapper_user_avec_venv(self, tmp_path: Path) -> None:
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

    def test_generate_wrapper_system_sans_venv(self, tmp_path: Path) -> None:
        """Wrapper system sans venv : chemin /usr/local/share."""
        config = PythonCliConfig(
            name="app", deploy_type="system", source_dir=tmp_path
        )
        paths = MagicMock()
        content = self.installer._generate_wrapper_content(config, paths)
        assert "/usr/local/share/app" in content
        assert "activate" not in content

    def test_generate_wrapper_system_avec_venv(self, tmp_path: Path) -> None:
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

    def _make_installer(self) -> tuple[BashScriptInstaller, MagicMock]:
        file_manager = MagicMock()
        return BashScriptInstaller(None, file_manager), file_manager

    def test_install_skip_existing_sans_logger(self, tmp_path: Path) -> None:
        """install() retourne True sur un script existant sans logger."""
        installer, fm = self._make_installer()
        fm.file_exists.return_value = True
        assert installer.install(str(tmp_path / "s.sh"), BashScriptConfig(
            exec_command="echo x"
        )) is True

    def test_install_create_fails_sans_logger(self, tmp_path: Path) -> None:
        """install() retourne False si create_file échoue sans logger."""
        installer, fm = self._make_installer()
        fm.file_exists.return_value = False
        fm.create_file.return_value = False
        assert installer.install(str(tmp_path / "s.sh"), BashScriptConfig(
            exec_command="echo x"
        )) is False

    def test_set_executable_fails_sans_logger(self, tmp_path: Path) -> None:
        """_set_executable retourne False sur OSError sans logger."""
        installer, _ = self._make_installer()
        with patch("os.open", side_effect=OSError("denied")):
            assert installer._set_executable(str(tmp_path / "f.sh")) is False

    def test_install_success_logue_info_sans_logger(self, tmp_path: Path) -> None:
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

    def setup_method(self) -> None:
        self.executor = _make_executor()
        self.checker = LinuxScriptChecker(self.executor)

    def test_check_python_exec_manquant(self) -> None:
        """Retourne False si python3 absent sans logger."""
        self.executor.probe.return_value = _result(success=False)
        assert self.checker.check_python() is False

    def test_check_python_probe_echec(self) -> None:
        """Retourne False si la sonde --version échoue sans logger."""
        self.executor.probe.side_effect = [
            _result(success=True),
            _result(success=False),
        ]
        assert self.checker.check_python() is False

    def test_check_python_version_insuffisante(self) -> None:
        """Retourne False si version trop ancienne sans logger."""
        self.executor.probe.side_effect = [
            _result(success=True),
            _result(success=True, stdout="Python 3.10.0\n"),
        ]
        assert self.checker.check_python("3.11") is False

    def test_check_python_version_ok(self) -> None:
        """Retourne True si version satisfaite sans logger."""
        self.executor.probe.side_effect = [
            _result(success=True),
            _result(success=True, stdout="Python 3.12.0\n"),
        ]
        assert self.checker.check_python("3.11") is True

    def test_check_script_syntax_introuvable(self, tmp_path: Path) -> None:
        """Retourne False si script absent sans logger."""
        self.executor.probe.return_value = _result(success=False)
        assert self.checker.check_script_syntax(
            tmp_path / "missing.py"
        ) is False

    def test_check_script_syntax_erreur(self, tmp_path: Path) -> None:
        """Retourne False si syntaxe incorrecte sans logger."""
        script = tmp_path / "bad.py"
        self.executor.probe.return_value = _result(success=True)
        self.executor.run.return_value = _result(
            success=False, stderr="err"
        )
        assert self.checker.check_script_syntax(script) is False

    def test_check_script_syntax_ok(self, tmp_path: Path) -> None:
        """Retourne True si syntaxe correcte sans logger."""
        script = tmp_path / "ok.py"
        self.executor.probe.return_value = _result(success=True)
        self.executor.run.return_value = _result(success=True)
        assert self.checker.check_script_syntax(script) is True

    def test_check_venv_absent(self, tmp_path: Path) -> None:
        """Retourne False si venv absent sans logger."""
        self.executor.probe.return_value = _result(success=False)
        assert self.checker.check_venv(tmp_path / "novenv") is False

    def test_check_venv_python_absent(self, tmp_path: Path) -> None:
        """Retourne False si interpréteur absent sans logger."""
        self.executor.probe.side_effect = [
            _result(success=True),
            _result(success=False),
        ]
        assert self.checker.check_venv(tmp_path) is False

    def test_check_venv_subprocess_echec(self, tmp_path: Path) -> None:
        """Retourne False si la sonde venv échoue sans logger."""
        self.executor.probe.side_effect = [
            _result(success=True),
            _result(success=True),
            _result(success=False),
        ]
        assert self.checker.check_venv(tmp_path) is False

    def test_check_venv_ok(self, tmp_path: Path) -> None:
        """Retourne True si venv fonctionnel sans logger."""
        self.executor.probe.side_effect = [
            _result(success=True),
            _result(success=True),
            _result(success=True),
        ]
        assert self.checker.check_venv(tmp_path) is True

    def test_check_python_version_illisible(self) -> None:
        """Retourne True si version Python illisible (sans logger)."""
        self.executor.probe.side_effect = [
            _result(success=True),
            _result(success=True, stdout="Python\n"),
        ]
        assert self.checker.check_python("3.11") is True


class TestLinuxScriptCheckerEdgeCases:
    """Branches non couvertes de LinuxScriptChecker."""

    def setup_method(self) -> None:
        self.logger = MagicMock()
        self.executor = _make_executor()
        self.checker = LinuxScriptChecker(self.executor, self.logger)

    def test_check_python_probe_echec(self) -> None:
        """Retourne False si la sonde --version retourne un échec."""
        self.executor.probe.side_effect = [
            _result(success=True),
            _result(success=False),
        ]
        assert self.checker.check_python() is False
        self.logger.log_error.assert_called()

    def test_check_python_version_ok_logue_info(self) -> None:
        """Logue log_info quand la version satisfait le minimum."""
        self.executor.probe.side_effect = [
            _result(success=True),
            _result(success=True, stdout="Python 3.12.0\n"),
        ]
        assert self.checker.check_python("3.11") is True
        self.logger.log_info.assert_called()

    def test_check_extras_inconnu_ignore(self, tmp_path: Path) -> None:
        """Un extra inexistant dans opt-deps n'ajoute pas de dépendances."""
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_bytes(
            b'[project]\nname = "app"\ndependencies = []\n'
        )
        self.executor.probe.return_value = _result(success=True)
        _, _, total, _ = self.checker.check_dependencies(
            pyproject, None, ["inexistant"]
        )
        assert total == 0

    def test_is_installed_pip_show_sans_location(self) -> None:
        """_is_installed retourne 'installé' si pip show OK mais pas de Location."""
        self.executor.probe.return_value = _result(
            success=True, stdout="Name: pkg\nVersion: 1.0\n"
        )
        result = self.checker._is_installed("pkg", "pip3")
        assert result == "installé"

    def test_is_installed_pip_show_avec_location(self) -> None:
        """_is_installed retourne le chemin si pip show contient Location."""
        self.executor.probe.return_value = _result(
            success=True,
            stdout="Name: pkg\nLocation: /usr/lib/python3.11\n",
        )
        result = self.checker._is_installed("pkg", "pip3")
        assert result == "/usr/lib/python3.11"

    def test_is_installed_pip_show_echec(self) -> None:
        """_is_installed retourne None si pip show échoue."""
        self.executor.probe.return_value = _result(success=False)
        result = self.checker._is_installed("pkg", "pip3")
        assert result is None


class TestLinuxCliInstallerEdgeCases:
    """Branches non couvertes de LinuxCliInstaller."""

    def setup_method(self) -> None:
        self.checker = MagicMock()
        self.executor = _make_executor()
        self.installer = LinuxCliInstaller(
            checker=self.checker, executor=self.executor, logger=None
        )

    def _patch_paths(self, tmp_path: Path) -> MagicMock:
        mock_paths = MagicMock()
        mock_paths.bin_path = tmp_path / "bin" / "app"
        return mock_paths

    def _user_config(self, tmp_path: Path) -> PythonCliConfig:
        return PythonCliConfig(
            name="app", deploy_type="user", source_dir=tmp_path
        )

    def test_install_success_sans_logger(self, tmp_path: Path) -> None:
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
            "linuxtools.scripts.installer.ScriptPaths"
        ) as mock_cls:
            mock_cls.return_value = self._patch_paths(tmp_path)
            self.executor.probe.side_effect = _probe_dispatch()
            self.executor.run.return_value = _result(success=True)
            report = self.installer.install(config, confirm_wrapper=False)
        assert report.success is True

    def test_install_venv_inaccessible_sans_logger(self, tmp_path: Path) -> None:
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
            "linuxtools.scripts.installer.ScriptPaths"
        ) as mock_cls:
            mock_cls.return_value = self._patch_paths(tmp_path)
            self.executor.probe.side_effect = _probe_dispatch()
            self.executor.run.return_value = _result(success=True)
            report = self.installer.install(config, confirm_wrapper=False)
        assert any("Venv" in w for w in report.warnings)

    def test_handle_wrapper_tty_desactive_confirmation(self, tmp_path: Path) -> None:
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
            "linuxtools.scripts.installer.ScriptPaths"
        ) as mock_cls, patch(
            "linuxtools.scripts.installer.sys.stdin.isatty",
            return_value=False,
        ), patch.object(
            self.installer, "_write_wrapper"
        ) as mock_write:
            mock_cls.return_value = self._patch_paths(tmp_path)
            self.executor.probe.side_effect = _probe_dispatch()
            self.executor.run.return_value = _result(success=True)
            # confirm_wrapper=True mais stdin non-TTY → auto False
            self.installer.install(config, confirm_wrapper=True)
        mock_write.assert_called_once()

    def test_handle_wrapper_refuse_interactif(self, tmp_path: Path) -> None:
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
            "linuxtools.scripts.installer.ScriptPaths"
        ) as mock_cls, patch(
            "linuxtools.scripts.installer.sys.stdin.isatty",
            return_value=True,
        ), patch("builtins.input", return_value="n"), \
             patch("builtins.print"):
            mock_cls.return_value = self._patch_paths(tmp_path)
            report = self.installer.install(config, confirm_wrapper=True)
        assert report.success is False
        assert any("refusé" in w for w in report.warnings)

    def test_run_uv_install_uv_introuvable(self, tmp_path: Path) -> None:
        """_run_uv_install retourne False si uv est introuvable."""
        config = self._user_config(tmp_path)
        self.executor.probe.side_effect = _probe_dispatch(uv_found=None)
        assert self.installer._run_uv_install(config) is False

    def test_run_uv_install_returncode_nonzero_sans_logger(
        self, tmp_path: Path
    ) -> None:
        """_run_uv_install retourne False si uv échoue sans logger."""
        config = self._user_config(tmp_path)
        self.executor.probe.side_effect = _probe_dispatch()
        self.executor.run.return_value = _result(
            success=False, stderr="uv error"
        )
        assert self.installer._run_uv_install(config) is False

    def test_write_wrapper_sans_logger(self, tmp_path: Path) -> None:
        """_write_wrapper crée le fichier sans logger (executor mocké)."""
        target = tmp_path / "bin" / "app"
        tmp_file = str(tmp_path / "bin" / ".app.XXXXXX")
        installer = LinuxCliInstaller(
            checker=MagicMock(), executor=self.executor, logger=None
        )
        self.executor.run.side_effect = [
            _result(success=True),
            _result(success=True, stdout=f"{tmp_file}\n"),
            _result(success=True),
            _result(success=True),
            _result(success=True),
        ]
        self.executor.probe.return_value = _result(success=False)
        installer._write_wrapper("#!/bin/bash\n", target)
        assert self.executor.run.call_args_list[-1][0][0] == [
            "mv", tmp_file, str(target)
        ]

    def test_preconditions_valueerror_sans_logger(self, tmp_path: Path) -> None:
        """_check_preconditions retourne échec sur ValueError sans logger."""
        self.checker.check_python.return_value = True
        self.checker.read_pyproject.side_effect = ValueError(
            "Section [project] manquante"
        )
        config = self._user_config(tmp_path)
        with patch(
            "linuxtools.scripts.installer.ScriptPaths"
        ) as mock_cls:
            mock_cls.return_value = self._patch_paths(tmp_path)
            report = self.installer.install(config, confirm_wrapper=False)
        assert report.success is False

    def test_venv_ok_ne_cree_pas_warning(self, tmp_path: Path) -> None:
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
            "linuxtools.scripts.installer.ScriptPaths"
        ) as mock_cls:
            mock_cls.return_value = self._patch_paths(tmp_path)
            self.executor.probe.side_effect = _probe_dispatch()
            self.executor.run.return_value = _result(success=True)
            report = self.installer.install(config, confirm_wrapper=False)
        assert all("Venv" not in w for w in report.warnings)

    def test_handle_wrapper_refuse_interactif_accepte(self, tmp_path: Path) -> None:
        """Wrapper accepté interactivement (réponse 'o')."""
        logger = MagicMock()
        checker = MagicMock()
        executor = _make_executor()
        installer = LinuxCliInstaller(
            checker=checker, executor=executor, logger=logger
        )
        checker.check_python.return_value = True
        checker.read_pyproject.return_value = {
            "name": "app", "version": "1.0",
            "requires_python": None, "dependencies": [],
            "optional_dependencies": {}, "scripts": {},
        }
        checker.check_dependencies.return_value = ([], [], 0, "")
        config = self._user_config(tmp_path)
        with patch(
            "linuxtools.scripts.installer.ScriptPaths"
        ) as mock_cls, patch(
            "linuxtools.scripts.installer.sys.stdin.isatty",
            return_value=True,
        ), patch("builtins.input", return_value="o"), \
             patch("builtins.print"), patch.object(
                 installer, "_write_wrapper"
             ) as mock_write:
            mock_cls.return_value = self._patch_paths(tmp_path)
            executor.probe.side_effect = _probe_dispatch()
            executor.run.return_value = _result(success=True)
            report = installer.install(config, confirm_wrapper=True)
        mock_write.assert_called_once()
        assert report.success is True

    def test_wrapper_echec_oserror_sans_logger(self, tmp_path: Path) -> None:
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
            "linuxtools.scripts.installer.ScriptPaths"
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

    def test_run_uv_introuvable_avec_logger(self, tmp_path: Path) -> None:
        """_run_uv_install retourne False et logue si uv introuvable (avec logger)."""
        logger = MagicMock()
        executor = _make_executor()
        installer = LinuxCliInstaller(
            checker=MagicMock(), executor=executor, logger=logger
        )
        config = self._user_config(tmp_path)
        executor.probe.side_effect = _probe_dispatch(uv_found=None)
        assert installer._run_uv_install(config) is False
        logger.log_error.assert_called()

    def test_run_uv_echec_avec_logger(self, tmp_path: Path) -> None:
        """_run_uv_install logue une erreur si uv tool install échoue."""
        logger = MagicMock()
        executor = _make_executor()
        installer = LinuxCliInstaller(
            checker=MagicMock(), executor=executor, logger=logger
        )
        config = self._user_config(tmp_path)
        executor.probe.side_effect = _probe_dispatch()
        executor.run.return_value = _result(
            success=False, stderr="uv error"
        )
        assert installer._run_uv_install(config) is False
        logger.log_error.assert_called()

    def test_is_target_root_probe_echoue(self) -> None:
        """_is_target_root retourne False sans crash si id -u échoue."""
        logger = MagicMock()
        executor = _make_executor()
        installer = LinuxCliInstaller(
            checker=MagicMock(), executor=executor, logger=logger
        )
        executor.probe.return_value = _result(success=False)
        assert installer._is_target_root() is False
        logger.log_warning.assert_called()

    def test_is_target_root_probe_echoue_sans_logger(self) -> None:
        """_is_target_root retourne False sans logger si id -u échoue."""
        self.executor.probe.return_value = _result(success=False)
        assert self.installer._is_target_root() is False

    def test_is_target_root_uid_zero(self) -> None:
        """_is_target_root retourne True si la cible répond uid 0."""
        executor = _make_executor()
        installer = LinuxCliInstaller(
            checker=MagicMock(), executor=executor, logger=None
        )
        executor.probe.return_value = _result(success=True, stdout="0\n")
        assert installer._is_target_root() is True


# ---------------------------------------------------------------------------
# Abstraction CommandExecutor — pas de supposition sur le type concret
# ---------------------------------------------------------------------------

class TestExecutorAbstractionRespectee:
    """Prouve l'absence de supposition sur le type concret de l'exécuteur.

    Un simple mock respectant l'ABC ``CommandExecutor`` (pas
    spécifiquement ``LinuxCommandExecutor``) doit suffire à faire
    fonctionner LinuxScriptChecker et LinuxCliInstaller — aucune
    branche ne doit dépendre d'un attribut ou d'un isinstance
    spécifique à l'implémentation locale.
    """

    def test_checker_fonctionne_avec_executeur_generique(self) -> None:
        """LinuxScriptChecker n'utilise que l'API CommandExecutor."""
        generic_executor = _make_executor()
        generic_executor.probe.side_effect = [
            _result(success=True),
            _result(success=True, stdout="Python 3.12.0\n"),
        ]
        checker = LinuxScriptChecker(generic_executor)
        assert checker.check_python("3.11") is True
        assert not hasattr(generic_executor, "_is_root")

    def test_installer_fonctionne_avec_executeur_generique(
        self, tmp_path: Path
    ) -> None:
        """LinuxCliInstaller n'utilise que l'API CommandExecutor."""
        generic_executor = _make_executor()
        generic_executor.probe.side_effect = _probe_dispatch()
        generic_executor.run.return_value = _result(success=True)
        checker = MagicMock()
        checker.check_python.return_value = True
        checker.read_pyproject.return_value = {
            "name": "app", "version": "1.0",
            "requires_python": None, "dependencies": [],
            "optional_dependencies": {}, "scripts": {"app": "app:main"},
        }
        checker.check_dependencies.return_value = ([], [], 0, "")
        installer = LinuxCliInstaller(
            checker=checker, executor=generic_executor, logger=None
        )
        config = PythonCliConfig(
            name="app", deploy_type="user", source_dir=tmp_path
        )
        with patch(
            "linuxtools.scripts.installer.ScriptPaths"
        ) as mock_cls:
            mock_paths = MagicMock()
            mock_paths.bin_path = tmp_path / "bin" / "app"
            mock_cls.return_value = mock_paths
            report = installer.install(config, confirm_wrapper=False)
        assert report.success is True

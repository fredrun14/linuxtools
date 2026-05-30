"""Tests pour le module commands."""

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from linux_python_utils.commands import (
    AnsiCommandFormatter,
    CommandBuilder,
    CommandFormatter,
    CommandResult,
    LinuxCommandExecutor,
    PlainCommandFormatter,
)
from linux_python_utils.logging.base import Logger


def _setup_popen(mock_popen, returncode=0, stdout="", stderr=""):
    """Configure un mock subprocess.Popen utilisé en context manager.

    LinuxCommandExecutor.run() fait ``with subprocess.Popen(...) as p``
    puis ``p.communicate()`` et lit ``p.returncode``.

    Args:
        mock_popen: Mock retourné par @patch(...Popen).
        returncode: Code retour simulé du process.
        stdout: Sortie standard simulée.
        stderr: Sortie d'erreur simulée.

    Returns:
        Le mock du process (proc) pour assertions éventuelles.
    """
    proc = MagicMock()
    proc.communicate.return_value = (stdout, stderr)
    proc.returncode = returncode
    mock_popen.return_value.__enter__.return_value = proc
    return proc


# --- Tests CommandResult ---


class TestCommandResult:
    """Tests pour la dataclass CommandResult."""

    def test_creation_avec_tous_les_champs(self):
        """Test de la création avec tous les champs."""
        result = CommandResult(
            command=["ls", "-la"],
            return_code=0,
            stdout="fichier.txt",
            stderr="",
            success=True,
            duration=0.5,
        )
        assert result.command == ["ls", "-la"]
        assert result.return_code == 0
        assert result.stdout == "fichier.txt"
        assert result.stderr == ""
        assert result.success is True
        assert result.duration == 0.5

    def test_frozen(self):
        """Test que la dataclass est immuable."""
        result = CommandResult(
            command=["ls"],
            return_code=0,
            stdout="",
            stderr="",
            success=True,
            duration=0.0,
        )
        with pytest.raises(AttributeError):
            result.return_code = 1

    def test_success_true_quand_code_zero(self):
        """Test success=True quand return_code est 0."""
        result = CommandResult(
            command=["echo"],
            return_code=0,
            stdout="",
            stderr="",
            success=True,
            duration=0.1,
        )
        assert result.success is True

    def test_success_false_quand_code_non_zero(self):
        """Test success=False quand return_code est non-zéro."""
        result = CommandResult(
            command=["false"],
            return_code=1,
            stdout="",
            stderr="erreur",
            success=False,
            duration=0.1,
        )
        assert result.success is False
        assert result.return_code == 1


# --- Tests CommandBuilder ---


class TestCommandBuilder:
    """Tests pour le constructeur fluent CommandBuilder."""

    def test_build_programme_seul(self):
        """Test de build avec le programme seul."""
        cmd = CommandBuilder("ls").build()
        assert cmd == ["ls"]

    def test_with_flag(self):
        """Test d'ajout d'un flag simple."""
        cmd = (
            CommandBuilder("ls")
            .with_flag("-l")
            .build()
        )
        assert cmd == ["ls", "-l"]

    def test_with_options(self):
        """Test d'ajout d'une liste d'options."""
        cmd = (
            CommandBuilder("rsync")
            .with_options(["-av", "--delete"])
            .build()
        )
        assert cmd == ["rsync", "-av", "--delete"]

    def test_with_option_cle_valeur(self):
        """Test d'ajout d'une option clé=valeur."""
        cmd = (
            CommandBuilder("borg")
            .with_option("--compression", "lz4")
            .build()
        )
        assert cmd == ["borg", "--compression=lz4"]

    def test_with_option_if_condition_vraie(self):
        """Test d'ajout conditionnel avec condition vraie."""
        cmd = (
            CommandBuilder("rsync")
            .with_option_if(
                "--exclude-from", "/tmp/exclude",
                condition=True,
            )
            .build()
        )
        assert cmd == [
            "rsync", "--exclude-from=/tmp/exclude"
        ]

    def test_with_option_if_condition_fausse(self):
        """Test d'ajout conditionnel avec condition fausse."""
        cmd = (
            CommandBuilder("rsync")
            .with_option_if(
                "--exclude-from", "/tmp/exclude",
                condition=False,
            )
            .build()
        )
        assert cmd == ["rsync"]

    def test_with_option_if_valeur_none(self):
        """Test d'ajout conditionnel avec valeur None."""
        cmd = (
            CommandBuilder("rsync")
            .with_option_if(
                "--exclude-from", None,
                condition=True,
            )
            .build()
        )
        assert cmd == ["rsync"]

    def test_with_args(self):
        """Test d'ajout d'arguments positionnels."""
        cmd = (
            CommandBuilder("cp")
            .with_args(["/src", "/dest"])
            .build()
        )
        assert cmd == ["cp", "/src", "/dest"]

    def test_chainage_complet(self):
        """Test du chaînage fluent complet."""
        cmd = (
            CommandBuilder("rsync")
            .with_options(["-av", "--delete"])
            .with_option("--compress-level", "3")
            .with_flag("--stats")
            .with_args(["/src/", "/dest/"])
            .build()
        )
        assert cmd == [
            "rsync", "-av", "--delete",
            "--compress-level=3", "--stats",
            "/src/", "/dest/",
        ]

    def test_programme_vide_leve_erreur(self):
        """Test qu'un programme vide lève ValueError."""
        with pytest.raises(ValueError):
            CommandBuilder("")

    def test_programme_espaces_leve_erreur(self):
        """Test qu'un programme d'espaces lève ValueError."""
        with pytest.raises(ValueError):
            CommandBuilder("   ")


# --- Tests LinuxCommandExecutor.run ---


class TestLinuxCommandExecutorRun:
    """Tests pour la méthode run() de LinuxCommandExecutor."""

    def setup_method(self):
        """Initialise les mocks pour chaque test."""
        self.mock_logger = MagicMock(spec=Logger)
        self.executor = LinuxCommandExecutor(
            logger=self.mock_logger,
        )

    @patch(
        "linux_python_utils.commands.runner.subprocess.Popen"
    )
    def test_run_commande_reussie(self, mock_popen):
        """Test d'une commande réussie."""
        _setup_popen(mock_popen, returncode=0, stdout="sortie", stderr="")
        result = self.executor.run(["echo", "test"])

        assert result.success is True
        assert result.return_code == 0
        assert result.stdout == "sortie"
        assert result.stderr == ""
        assert result.command == ["echo", "test"]
        assert result.duration >= 0

    @patch(
        "linux_python_utils.commands.runner.subprocess.Popen"
    )
    def test_run_commande_echouee(self, mock_popen):
        """Test d'une commande échouée."""
        _setup_popen(mock_popen, returncode=1, stdout="", stderr="erreur")
        result = self.executor.run(["false"])

        assert result.success is False
        assert result.return_code == 1
        assert result.stderr == "erreur"

    @patch(
        "linux_python_utils.commands.runner.subprocess.run"
    )
    def test_run_timeout(self, mock_run):
        """Test du timeout lors de l'exécution."""
        mock_run.side_effect = subprocess.TimeoutExpired(
            cmd=["sleep", "100"], timeout=5,
        )
        result = self.executor.run(
            ["sleep", "100"], timeout=5,
        )

        assert result.success is False
        assert result.return_code == -1
        self.mock_logger.log_error.assert_called_once()

    @patch(
        "linux_python_utils.commands.runner.subprocess.run"
    )
    def test_run_commande_introuvable(self, mock_run):
        """Test avec une commande introuvable."""
        mock_run.side_effect = FileNotFoundError(
            "No such file or directory: 'inexistant'"
        )
        result = self.executor.run(["inexistant"])

        assert result.success is False
        assert result.return_code == -1
        self.mock_logger.log_error.assert_called_once()

    @patch(
        "linux_python_utils.commands.runner.subprocess.run"
    )
    def test_run_log_commande(self, mock_run):
        """Test que la commande est loguée."""
        mock_run.return_value = MagicMock(
            returncode=0, stdout="", stderr="",
        )
        self.executor.run(["ls", "-la"])

        self.mock_logger.log_info.assert_called_once()
        call_args = (
            self.mock_logger.log_info.call_args[0][0]
        )
        assert "ls -la" in call_args

    @patch(
        "linux_python_utils.commands.runner.subprocess.Popen"
    )
    def test_run_avec_cwd(self, mock_popen):
        """Test de l'exécution avec répertoire de travail."""
        _setup_popen(mock_popen, returncode=0)
        self.executor.run(["ls"], cwd="/tmp")

        mock_popen.assert_called_once()
        call_kwargs = mock_popen.call_args[1]
        assert call_kwargs["cwd"] == "/tmp"

    @patch(
        "linux_python_utils.commands.runner.subprocess.Popen"
    )
    def test_run_sans_logger(self, mock_popen):
        """Test de l'exécution sans logger."""
        _setup_popen(mock_popen, returncode=0, stdout="ok", stderr="")
        executor = LinuxCommandExecutor()
        result = executor.run(["echo", "test"])

        assert result.success is True
        assert result.stdout == "ok"

    @patch(
        "linux_python_utils.commands.runner.subprocess.Popen"
    )
    def test_run_logue_erreur_si_code_retour_non_zero(
        self, mock_popen
    ):
        """Vérifie que log_error est appelé si returncode != 0."""
        # Arrange
        _setup_popen(mock_popen, returncode=2, stdout="", stderr="echec")

        # Act
        result = self.executor.run(["rsync", "-av", "/src"])

        # Assert
        assert result.success is False
        assert result.return_code == 2
        self.mock_logger.log_error.assert_called_once()
        msg = self.mock_logger.log_error.call_args[0][0]
        assert "2" in msg
        assert "rsync" in msg

    @patch(
        "linux_python_utils.commands.runner.subprocess.run"
    )
    def test_run_pas_log_erreur_si_code_retour_zero(
        self, mock_run
    ):
        """Vérifie que log_error n'est pas appelé si returncode=0."""
        # Arrange
        mock_run.return_value = MagicMock(
            returncode=0, stdout="ok", stderr="",
        )

        # Act
        self.executor.run(["ls", "-la"])

        # Assert
        self.mock_logger.log_error.assert_not_called()


# --- Tests LinuxCommandExecutor.run_streaming ---


class TestLinuxCommandExecutorRunStreaming:
    """Tests pour la méthode run_streaming()."""

    def setup_method(self):
        """Initialise les mocks pour chaque test."""
        self.mock_logger = MagicMock(spec=Logger)
        self.executor = LinuxCommandExecutor(
            logger=self.mock_logger,
        )

    def _make_mock_proc(
        self, stdout_lines, stderr="", returncode=0,
    ):
        """Crée un mock de Popen configuré."""
        mock_proc = MagicMock()
        mock_proc.stdout = iter(stdout_lines)
        mock_proc.stderr.read.return_value = stderr
        mock_proc.returncode = returncode
        mock_proc.wait.return_value = None
        mock_proc.__enter__ = MagicMock(return_value=mock_proc)
        mock_proc.__exit__ = MagicMock(return_value=False)
        return mock_proc

    @patch(
        "linux_python_utils.commands.runner"
        ".subprocess.Popen"
    )
    def test_streaming_capture_sortie(self, mock_popen):
        """Test de la capture de sortie en streaming."""
        mock_popen.return_value = self._make_mock_proc(
            ["ligne1\n", "ligne2\n"],
        )
        result = self.executor.run_streaming(["cmd"])

        assert result.success is True
        assert result.stdout == "ligne1\nligne2"

    @patch(
        "linux_python_utils.commands.runner"
        ".subprocess.Popen"
    )
    def test_streaming_log_chaque_ligne(self, mock_popen):
        """Test que chaque ligne est loguée."""
        mock_popen.return_value = self._make_mock_proc(
            ["ligne1\n", "ligne2\n", "ligne3\n"],
        )
        self.executor.run_streaming(["cmd"])

        # 1 appel pour "Exécution (streaming)" + 3 lignes
        assert self.mock_logger.log_info.call_count == 4

    @patch(
        "linux_python_utils.commands.runner"
        ".subprocess.Popen"
    )
    def test_streaming_timeout(self, mock_popen):
        """Test du timeout en mode streaming."""
        mock_proc = self._make_mock_proc(
            ["partiel\n"],
        )
        mock_proc.wait.side_effect = [
            subprocess.TimeoutExpired(cmd=["cmd"], timeout=5),
            None,
        ]
        mock_popen.return_value = mock_proc

        result = self.executor.run_streaming(
            ["cmd"], timeout=5,
        )

        assert result.success is False
        assert result.return_code == -1
        assert "partiel" in result.stdout
        mock_proc.kill.assert_called_once()

    @patch(
        "linux_python_utils.commands.runner"
        ".subprocess.Popen"
    )
    def test_streaming_capture_stderr(self, mock_popen):
        """Test de la capture de stderr."""
        mock_popen.return_value = self._make_mock_proc(
            ["ok\n"], stderr="avertissement",
        )
        result = self.executor.run_streaming(["cmd"])

        assert result.stderr == "avertissement"

    @patch(
        "linux_python_utils.commands.runner"
        ".subprocess.Popen"
    )
    def test_streaming_sans_logger(self, mock_popen):
        """Test du streaming sans logger."""
        mock_popen.return_value = self._make_mock_proc(
            ["ligne1\n"],
        )
        executor = LinuxCommandExecutor()
        result = executor.run_streaming(["cmd"])

        assert result.success is True
        assert result.stdout == "ligne1"

    @patch(
        "linux_python_utils.commands.runner"
        ".subprocess.Popen"
    )
    def test_streaming_logue_erreur_si_code_retour_non_zero(
        self, mock_popen
    ):
        """Vérifie que log_error est appelé si returncode != 0."""
        # Arrange
        mock_popen.return_value = self._make_mock_proc(
            ["ligne1\n"], stderr="echec", returncode=1,
        )

        # Act
        result = self.executor.run_streaming(
            ["systemctl", "start", "svc"]
        )

        # Assert
        assert result.success is False
        assert result.return_code == 1
        self.mock_logger.log_error.assert_called_once()
        msg = self.mock_logger.log_error.call_args[0][0]
        assert "1" in msg
        assert "systemctl" in msg

    @patch(
        "linux_python_utils.commands.runner"
        ".subprocess.Popen"
    )
    def test_streaming_pas_log_erreur_si_code_retour_zero(
        self, mock_popen
    ):
        """Vérifie que log_error n'est pas appelé si returncode=0."""
        # Arrange
        mock_popen.return_value = self._make_mock_proc(
            ["ligne1\n"], returncode=0,
        )

        # Act
        self.executor.run_streaming(["cmd"])

        # Assert
        self.mock_logger.log_error.assert_not_called()


# --- Tests LinuxCommandExecutor dry_run ---


class TestLinuxCommandExecutorDryRun:
    """Tests pour le mode dry_run."""

    def setup_method(self):
        """Initialise l'exécuteur en mode dry_run."""
        self.mock_logger = MagicMock(spec=Logger)
        self.executor = LinuxCommandExecutor(
            logger=self.mock_logger,
            dry_run=True,
        )

    @patch(
        "linux_python_utils.commands.runner.subprocess.run"
    )
    def test_dry_run_pas_execution(self, mock_run):
        """Test que subprocess n'est pas appelé."""
        self.executor.run(["rm", "-rf", "/"])
        mock_run.assert_not_called()

    def test_dry_run_log_commande(self):
        """Test que la commande est loguée avec [dry-run]."""
        self.executor.run(["echo", "test"])

        call_args = (
            self.mock_logger.log_info.call_args[0][0]
        )
        assert "[dry-run]" in call_args
        assert "echo test" in call_args

    def test_dry_run_retourne_succes(self):
        """Test que le résultat indique un succès."""
        result = self.executor.run(["echo", "test"])

        assert result.success is True
        assert result.return_code == 0
        assert result.duration == 0.0

    @patch(
        "linux_python_utils.commands.runner"
        ".subprocess.Popen"
    )
    def test_dry_run_streaming(self, mock_popen):
        """Test du dry_run avec run_streaming."""
        result = self.executor.run_streaming(
            ["echo", "test"]
        )

        assert result.success is True
        mock_popen.assert_not_called()


# --- Tests LinuxCommandExecutor environnement ---


class TestLinuxCommandExecutorEnv:
    """Tests pour la gestion de l'environnement."""

    @patch(
        "linux_python_utils.commands.runner.subprocess.Popen"
    )
    @patch.dict("os.environ", {"EXISTING": "val"})
    def test_default_env_fusionne(self, mock_popen):
        """Test que default_env est fusionné."""
        _setup_popen(mock_popen, returncode=0)
        executor = LinuxCommandExecutor(
            default_env={"MY_VAR": "42"},
        )
        executor.run(["echo"])

        call_kwargs = mock_popen.call_args[1]
        env = call_kwargs["env"]
        assert env["EXISTING"] == "val"
        assert env["MY_VAR"] == "42"

    @patch(
        "linux_python_utils.commands.runner.subprocess.Popen"
    )
    @patch.dict("os.environ", {"EXISTING": "val"})
    def test_env_appel_prioritaire(self, mock_popen):
        """Test que l'env de l'appel est prioritaire."""
        _setup_popen(mock_popen, returncode=0)
        executor = LinuxCommandExecutor(
            default_env={"KEY": "default"},
        )
        executor.run(["echo"], env={"KEY": "override"})

        call_kwargs = mock_popen.call_args[1]
        env = call_kwargs["env"]
        assert env["KEY"] == "override"

    @patch(
        "linux_python_utils.commands.runner.subprocess.Popen"
    )
    def test_aucun_env_passe_none(self, mock_popen):
        """Test que sans env, subprocess reçoit None."""
        _setup_popen(mock_popen, returncode=0)
        executor = LinuxCommandExecutor()
        executor.run(["echo"])

        call_kwargs = mock_popen.call_args[1]
        assert call_kwargs["env"] is None


# --- Tests CommandResult.executed_as_root ---


class TestCommandResultExecutedAsRoot:
    """Tests pour le champ executed_as_root de CommandResult."""

    def test_executed_as_root_defaut_faux(self):
        """Vérifie que executed_as_root vaut False par défaut."""
        result = CommandResult(
            command=["ls"],
            return_code=0,
            stdout="",
            stderr="",
            success=True,
            duration=0.1,
        )
        assert result.executed_as_root is False

    def test_executed_as_root_vrai_quand_specifie(self):
        """Vérifie que executed_as_root peut être True."""
        result = CommandResult(
            command=["id"],
            return_code=0,
            stdout="uid=0",
            stderr="",
            success=True,
            duration=0.1,
            executed_as_root=True,
        )
        assert result.executed_as_root is True

    def test_executed_as_root_immutable(self):
        """Vérifie que executed_as_root ne peut pas être modifié."""
        result = CommandResult(
            command=["ls"],
            return_code=0,
            stdout="",
            stderr="",
            success=True,
            duration=0.0,
            executed_as_root=False,
        )
        with pytest.raises(AttributeError):
            result.executed_as_root = True


# --- Tests PlainCommandFormatter ---


class TestPlainCommandFormatter:
    """Tests pour le formateur texte brut PlainCommandFormatter."""

    @pytest.fixture
    def formatter(self) -> PlainCommandFormatter:
        """Fixture créant une instance de PlainCommandFormatter."""
        return PlainCommandFormatter()

    # --- format_start ---

    def test_format_start_root_contient_prefixe_root(
        self, formatter
    ):
        """Vérifie le préfixe [ROOT] pour une exécution root."""
        msg = formatter.format_start(["ls", "-la"], is_root=True)
        assert msg.startswith("[ROOT]")

    def test_format_start_user_contient_prefixe_user(
        self, formatter
    ):
        """Vérifie le préfixe [user] pour un utilisateur standard."""
        msg = formatter.format_start(["ls", "-la"], is_root=False)
        assert msg.startswith("[user]")

    def test_format_start_contient_la_commande(self, formatter):
        """Vérifie que la commande est incluse dans le message."""
        msg = formatter.format_start(
            ["rsync", "-av", "/src"], is_root=False
        )
        assert "rsync -av /src" in msg

    def test_format_start_pas_de_codes_ansi(self, formatter):
        """Vérifie l'absence de codes ANSI dans le message."""
        msg = formatter.format_start(["ls"], is_root=True)
        assert "\033[" not in msg

    # --- format_start_streaming ---

    def test_format_start_streaming_root_contient_prefixe(
        self, formatter
    ):
        """Vérifie le préfixe [ROOT] en mode streaming."""
        msg = formatter.format_start_streaming(
            ["cmd"], is_root=True
        )
        assert "[ROOT]" in msg
        assert "streaming" in msg

    def test_format_start_streaming_user_contient_prefixe(
        self, formatter
    ):
        """Vérifie le préfixe [user] en mode streaming."""
        msg = formatter.format_start_streaming(
            ["cmd"], is_root=False
        )
        assert "[user]" in msg
        assert "streaming" in msg

    # --- format_dry_run ---

    def test_format_dry_run_root_contient_dry_run_et_prefixe(
        self, formatter
    ):
        """Vérifie [ROOT] et [dry-run] pour une simulation root."""
        msg = formatter.format_dry_run(["rm", "-rf"], is_root=True)
        assert "[ROOT]" in msg
        assert "[dry-run]" in msg
        assert "rm -rf" in msg

    def test_format_dry_run_user_contient_dry_run_et_prefixe(
        self, formatter
    ):
        """Vérifie [user] et [dry-run] pour une simulation user."""
        msg = formatter.format_dry_run(["rm", "-rf"], is_root=False)
        assert "[user]" in msg
        assert "[dry-run]" in msg

    def test_format_dry_run_pas_de_codes_ansi(self, formatter):
        """Vérifie l'absence de codes ANSI dans le dry-run."""
        msg = formatter.format_dry_run(["cmd"], is_root=True)
        assert "\033[" not in msg

    # --- format_line ---

    def test_format_line_retourne_ligne_inchangee(self, formatter):
        """Vérifie que format_line retourne la ligne sans modification."""
        line = "sortie de la commande"
        assert formatter.format_line(line, is_root=True) == line
        assert formatter.format_line(line, is_root=False) == line

    @pytest.mark.parametrize("is_root", [True, False])
    def test_format_start_est_une_chaine(self, formatter, is_root):
        """Vérifie que format_start retourne toujours une str."""
        result = formatter.format_start(["cmd"], is_root=is_root)
        assert isinstance(result, str)


# --- Tests AnsiCommandFormatter ---


class TestAnsiCommandFormatter:
    """Tests pour le formateur ANSI coloré AnsiCommandFormatter."""

    @pytest.fixture
    def formatter(self) -> AnsiCommandFormatter:
        """Fixture créant une instance d'AnsiCommandFormatter."""
        return AnsiCommandFormatter()

    # --- Comportement avec TTY ---

    def test_format_start_root_avec_tty_contient_style_jaune(
        self, formatter
    ):
        """Vérifie le style jaune-or pour root en mode TTY."""
        with patch.object(formatter, "_is_tty", return_value=True):
            msg = formatter.format_start(["ls"], is_root=True)
        assert AnsiCommandFormatter.ROOT_STYLE in msg
        assert AnsiCommandFormatter.RESET in msg
        assert "[ROOT]" in msg

    def test_format_start_user_avec_tty_contient_style_vert(
        self, formatter
    ):
        """Vérifie le style vert pour user en mode TTY."""
        with patch.object(formatter, "_is_tty", return_value=True):
            msg = formatter.format_start(["ls"], is_root=False)
        assert AnsiCommandFormatter.USER_STYLE in msg
        assert AnsiCommandFormatter.RESET in msg
        assert "[user]" in msg

    def test_format_start_sans_tty_pas_de_codes_ansi(
        self, formatter
    ):
        """Vérifie l'absence de codes ANSI sans TTY (pipe, redirection)."""
        with patch.object(formatter, "_is_tty", return_value=False):
            msg = formatter.format_start(["ls"], is_root=True)
        assert "\033[" not in msg
        assert "[ROOT]" in msg

    def test_format_start_streaming_root_avec_tty(self, formatter):
        """Vérifie le style root en streaming avec TTY."""
        with patch.object(formatter, "_is_tty", return_value=True):
            msg = formatter.format_start_streaming(
                ["cmd"], is_root=True
            )
        assert AnsiCommandFormatter.ROOT_STYLE in msg
        assert "streaming" in msg

    def test_format_start_streaming_sans_tty(self, formatter):
        """Vérifie l'absence d'ANSI en streaming sans TTY."""
        with patch.object(formatter, "_is_tty", return_value=False):
            msg = formatter.format_start_streaming(
                ["cmd"], is_root=False
            )
        assert "\033[" not in msg

    # --- format_dry_run ---

    def test_format_dry_run_avec_tty_contient_style_gris(
        self, formatter
    ):
        """Vérifie le style gris pour dry-run avec TTY."""
        with patch.object(formatter, "_is_tty", return_value=True):
            msg = formatter.format_dry_run(["rm"], is_root=True)
        assert AnsiCommandFormatter.DRY_STYLE in msg
        assert "[dry-run]" in msg

    def test_format_dry_run_root_avec_tty_pas_style_jaune(
        self, formatter
    ):
        """Vérifie que dry-run utilise le gris (pas jaune) même en root."""
        with patch.object(formatter, "_is_tty", return_value=True):
            msg = formatter.format_dry_run(["rm"], is_root=True)
        assert AnsiCommandFormatter.DRY_STYLE in msg
        assert AnsiCommandFormatter.ROOT_STYLE not in msg

    def test_format_dry_run_sans_tty_pas_de_codes_ansi(
        self, formatter
    ):
        """Vérifie l'absence d'ANSI pour dry-run sans TTY."""
        with patch.object(formatter, "_is_tty", return_value=False):
            msg = formatter.format_dry_run(["rm"], is_root=False)
        assert "\033[" not in msg

    # --- format_line ---

    def test_format_line_retourne_ligne_inchangee(self, formatter):
        """Vérifie que les lignes de contenu ne sont pas stylisées."""
        line = "output de la commande"
        assert formatter.format_line(line, is_root=True) == line
        assert formatter.format_line(line, is_root=False) == line

    # --- Héritage ABC ---

    def test_plain_est_une_sous_classe_de_command_formatter(self):
        """Vérifie que PlainCommandFormatter implémente l'interface."""
        assert issubclass(PlainCommandFormatter, CommandFormatter)

    def test_ansi_est_une_sous_classe_de_command_formatter(self):
        """Vérifie que AnsiCommandFormatter implémente l'interface."""
        assert issubclass(AnsiCommandFormatter, CommandFormatter)


# --- Tests LinuxCommandExecutor : préfixes dans les logs ---


class TestLinuxCommandExecutorPrefixeLogs:
    """Tests des préfixes [ROOT]/[user] dans les messages de log."""

    @pytest.fixture
    def mock_logger(self):
        """Fixture fournissant un logger mock."""
        return MagicMock(spec=Logger)

    @patch("linux_python_utils.commands.runner.os.getuid",
           return_value=1000)
    @patch("linux_python_utils.commands.runner.subprocess.run")
    def test_log_contient_prefixe_user_quand_non_root(
        self, mock_run, mock_getuid, mock_logger
    ):
        """Vérifie le préfixe [user] dans le log quand non-root."""
        mock_run.return_value = MagicMock(
            returncode=0, stdout="", stderr=""
        )
        executor = LinuxCommandExecutor(logger=mock_logger)
        executor.run(["ls"])

        log_msg = mock_logger.log_info.call_args[0][0]
        assert "[user]" in log_msg

    @patch("linux_python_utils.commands.runner.os.getuid",
           return_value=0)
    @patch("linux_python_utils.commands.runner.subprocess.run")
    def test_log_contient_prefixe_root_quand_root(
        self, mock_run, mock_getuid, mock_logger
    ):
        """Vérifie le préfixe [ROOT] dans le log quand root (uid=0)."""
        mock_run.return_value = MagicMock(
            returncode=0, stdout="", stderr=""
        )
        executor = LinuxCommandExecutor(logger=mock_logger)
        executor.run(["id"])

        log_msg = mock_logger.log_info.call_args[0][0]
        assert "[ROOT]" in log_msg

    @patch("linux_python_utils.commands.runner.os.getuid",
           return_value=1000)
    def test_dry_run_log_contient_prefixe_user(
        self, mock_getuid, mock_logger
    ):
        """Vérifie le préfixe [user] dans le log dry-run."""
        executor = LinuxCommandExecutor(
            logger=mock_logger, dry_run=True
        )
        executor.run(["echo", "test"])

        log_msg = mock_logger.log_info.call_args[0][0]
        assert "[user]" in log_msg
        assert "[dry-run]" in log_msg

    @patch("linux_python_utils.commands.runner.os.getuid",
           return_value=0)
    def test_dry_run_log_contient_prefixe_root(
        self, mock_getuid, mock_logger
    ):
        """Vérifie le préfixe [ROOT] dans le log dry-run root."""
        executor = LinuxCommandExecutor(
            logger=mock_logger, dry_run=True
        )
        executor.run(["rm", "-rf", "/tmp/test"])

        log_msg = mock_logger.log_info.call_args[0][0]
        assert "[ROOT]" in log_msg
        assert "[dry-run]" in log_msg


# --- Tests LinuxCommandExecutor : console_formatter ---


class TestLinuxCommandExecutorConsoleFormatter:
    """Tests de l'intégration du console_formatter."""

    def _make_mock_proc(self, stdout_lines, stderr="", returncode=0):
        """Crée un mock de Popen configuré."""
        mock_proc = MagicMock()
        mock_proc.stdout = iter(stdout_lines)
        mock_proc.stderr.read.return_value = stderr
        mock_proc.returncode = returncode
        mock_proc.wait.return_value = None
        mock_proc.__enter__ = MagicMock(return_value=mock_proc)
        mock_proc.__exit__ = MagicMock(return_value=False)
        return mock_proc

    @patch("linux_python_utils.commands.runner.subprocess.run")
    def test_console_formatter_format_start_appele_sur_run(
        self, mock_run
    ):
        """Vérifie que format_start du formatter est appelé lors de run."""
        mock_run.return_value = MagicMock(
            returncode=0, stdout="", stderr=""
        )
        mock_formatter = MagicMock(spec=CommandFormatter)
        mock_formatter.format_start.return_value = "msg"

        executor = LinuxCommandExecutor(
            console_formatter=mock_formatter
        )
        executor.run(["ls"])

        mock_formatter.format_start.assert_called_once_with(
            ["ls"], executor._is_root
        )

    def test_console_formatter_format_dry_run_appele(self):
        """Vérifie que format_dry_run est appelé en mode dry_run."""
        mock_formatter = MagicMock(spec=CommandFormatter)
        mock_formatter.format_dry_run.return_value = "msg"

        executor = LinuxCommandExecutor(
            console_formatter=mock_formatter, dry_run=True
        )
        executor.run(["echo"])

        mock_formatter.format_dry_run.assert_called_once_with(
            ["echo"], executor._is_root
        )

    @patch(
        "linux_python_utils.commands.runner.subprocess.Popen"
    )
    def test_console_formatter_format_streaming_appele(
        self, mock_popen
    ):
        """Vérifie que format_start_streaming est appelé."""
        mock_popen.return_value = self._make_mock_proc([])
        mock_formatter = MagicMock(spec=CommandFormatter)
        mock_formatter.format_start_streaming.return_value = "msg"
        mock_formatter.format_line.return_value = "ligne"

        executor = LinuxCommandExecutor(
            console_formatter=mock_formatter
        )
        executor.run_streaming(["cmd"])

        mock_formatter.format_start_streaming.assert_called_once_with(
            ["cmd"], executor._is_root
        )

    @patch("linux_python_utils.commands.runner.subprocess.run")
    def test_sans_console_formatter_pas_appel_format(
        self, mock_run
    ):
        """Vérifie qu'aucun formatter n'est appelé sans console_formatter."""
        mock_run.return_value = MagicMock(
            returncode=0, stdout="", stderr=""
        )
        executor = LinuxCommandExecutor()
        # Ne doit pas lever d'exception
        result = executor.run(["ls"])
        assert result.success is True

    @patch(
        "linux_python_utils.commands.runner.subprocess.Popen"
    )
    def test_console_formatter_format_line_appele_par_ligne(
        self, mock_popen
    ):
        """Vérifie que format_line est appelé pour chaque ligne."""
        mock_popen.return_value = self._make_mock_proc(
            ["ligne1\n", "ligne2\n"]
        )
        mock_formatter = MagicMock(spec=CommandFormatter)
        mock_formatter.format_start_streaming.return_value = "debut"
        mock_formatter.format_line.return_value = "ligne"

        executor = LinuxCommandExecutor(
            console_formatter=mock_formatter
        )
        executor.run_streaming(["cmd"])

        assert mock_formatter.format_line.call_count == 2


# --- Tests LinuxCommandExecutor : executed_as_root dans le résultat ---


class TestLinuxCommandExecutorExecutedAsRoot:
    """Tests du champ executed_as_root dans les résultats."""

    @patch("linux_python_utils.commands.runner.os.getuid",
           return_value=1000)
    @patch("linux_python_utils.commands.runner.subprocess.run")
    def test_executed_as_root_faux_quand_uid_non_zero(
        self, mock_run, mock_getuid
    ):
        """Vérifie executed_as_root=False quand l'uid est non-zero."""
        mock_run.return_value = MagicMock(
            returncode=0, stdout="", stderr=""
        )
        executor = LinuxCommandExecutor()
        result = executor.run(["ls"])

        assert result.executed_as_root is False

    @patch("linux_python_utils.commands.runner.os.getuid",
           return_value=0)
    @patch("linux_python_utils.commands.runner.subprocess.run")
    def test_executed_as_root_vrai_quand_uid_zero(
        self, mock_run, mock_getuid
    ):
        """Vérifie executed_as_root=True quand l'uid est 0 (root)."""
        mock_run.return_value = MagicMock(
            returncode=0, stdout="", stderr=""
        )
        executor = LinuxCommandExecutor()
        result = executor.run(["id"])

        assert result.executed_as_root is True

    @patch("linux_python_utils.commands.runner.os.getuid",
           return_value=0)
    def test_dry_run_executed_as_root_vrai_quand_root(
        self, mock_getuid
    ):
        """Vérifie executed_as_root=True en dry_run root."""
        executor = LinuxCommandExecutor(dry_run=True)
        result = executor.run(["echo"])

        assert result.executed_as_root is True

    @patch("linux_python_utils.commands.runner.os.getuid",
           return_value=1000)
    def test_dry_run_executed_as_root_faux_quand_user(
        self, mock_getuid
    ):
        """Vérifie executed_as_root=False en dry_run non-root."""
        executor = LinuxCommandExecutor(dry_run=True)
        result = executor.run(["echo"])

        assert result.executed_as_root is False

    @patch("linux_python_utils.commands.runner.os.getuid",
           return_value=0)
    @patch("linux_python_utils.commands.runner.subprocess.run")
    def test_run_echec_executed_as_root_preserve(
        self, mock_run, mock_getuid
    ):
        """Vérifie executed_as_root dans un résultat en échec."""
        mock_run.return_value = MagicMock(
            returncode=1, stdout="", stderr="erreur"
        )
        executor = LinuxCommandExecutor()
        result = executor.run(["false"])

        assert result.executed_as_root is True
        assert result.success is False

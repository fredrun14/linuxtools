"""Tests pour le module deploy.destinations."""

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from linuxtools.commands.base import CommandExecutor, CommandResult
from linuxtools.deploy.destinations import (
    LocalDestination,
    RemoteDestination,
    WriteOutcome,
    destination_for,
)
from linuxtools.deploy.models import DeployTarget


def _result(success: bool = True, stderr: str = "") -> CommandResult:
    """Construit un CommandResult scripté pour les tests."""
    return CommandResult(
        command=(),
        return_code=0 if success else 1,
        stdout="",
        stderr=stderr,
        success=success,
        duration=0.01,
    )


class TestLocalDestination:
    """Tests de LocalDestination.write (TOCTOU-safe, write_text_secure)."""

    def test_local_ecrit_le_contenu_et_les_permissions_cas_nominal(
        self, tmp_path: Path
    ) -> None:
        """Cas nominal : le fichier est écrit avec le bon contenu/mode."""
        # Arrange
        dest_path = tmp_path / "config.toml"
        destination = LocalDestination()

        # Act
        outcome = destination.write(dest_path, "clef = 1\n", 0o640)

        # Assert
        assert outcome.success is True
        assert dest_path.read_text(encoding="utf-8") == "clef = 1\n"
        assert oct(os.stat(dest_path).st_mode)[-3:] == "640"
        assert destination.label == "local"

    def test_local_sur_symlink_leve_oserror(self, tmp_path: Path) -> None:
        """Vecteur TOCTOU : dest_path est un symlink -> OSError
        (O_NOFOLLOW)."""
        # Arrange : la cible réelle est en dehors de tmp_path/dest_path
        real_target = tmp_path / "ailleurs.txt"
        real_target.write_text("original")
        dest_path = tmp_path / "config.toml"
        dest_path.symlink_to(real_target)
        destination = LocalDestination()

        # Act / Assert
        with pytest.raises(OSError):
            destination.write(dest_path, "contenu malveillant", 0o644)
        # La cible réelle n'a pas été altérée
        assert real_target.read_text(encoding="utf-8") == "original"

    def test_write_keep_local_laisse_fichier_existant_intact(
        self, tmp_path: Path
    ) -> None:
        """F-07 : un fichier présent garde contenu, mode et mtime."""
        dest_path = tmp_path / "secrets.env"
        dest_path.write_text("SECRET=1\n", encoding="utf-8")
        os.chmod(dest_path, 0o640)
        os.utime(dest_path, (1_000_000, 1_000_000))

        outcome = LocalDestination().write(
            dest_path, "VIDE=\n", 0o600, if_exists="keep"
        )

        assert outcome.success is True
        assert outcome.kept is True
        assert dest_path.read_text(encoding="utf-8") == "SECRET=1\n"
        stat = os.stat(dest_path)
        assert oct(stat.st_mode)[-3:] == "640"
        assert stat.st_mtime == 1_000_000

    def test_write_keep_local_cree_fichier_absent(
        self, tmp_path: Path
    ) -> None:
        """Un fichier absent est créé, kept reste False."""
        dest_path = tmp_path / "secrets.env"

        outcome = LocalDestination().write(
            dest_path, "A=\n", 0o600, if_exists="keep"
        )

        assert outcome == WriteOutcome(True)
        assert dest_path.read_text(encoding="utf-8") == "A=\n"
        assert oct(os.stat(dest_path).st_mode)[-3:] == "600"

    def test_write_keep_local_lien_symbolique_casse_est_conserve(
        self, tmp_path: Path
    ) -> None:
        """Un lien cassé compte comme existant ; rien n'est créé."""
        lien = tmp_path / "lien"
        lien.symlink_to(tmp_path / "rien")

        outcome = LocalDestination().write(
            lien, "A=\n", 0o600, if_exists="keep"
        )

        assert outcome.kept is True
        assert not (tmp_path / "rien").exists()

    def test_write_replace_local_comportement_inchange(
        self, tmp_path: Path
    ) -> None:
        """Non-régression : replace écrase un fichier existant."""
        dest_path = tmp_path / "f.txt"
        dest_path.write_text("ancien", encoding="utf-8")

        outcome = LocalDestination().write(dest_path, "neuf", 0o644)

        assert outcome == WriteOutcome(True)
        assert dest_path.read_text(encoding="utf-8") == "neuf"


class TestRemoteDestination:
    """Tests de RemoteDestination.write (executor.run install -m -T)."""

    def test_remote_ecrit_via_install_cas_nominal(self) -> None:
        """Cas nominal : `mkdir -p --` du parent puis `install -m <mode>
        -T /dev/stdin <dest>`, contenu par stdin."""
        # Arrange
        dest_path = Path("/etc/app/config.toml")
        executor = MagicMock(spec=CommandExecutor)
        executor.run.side_effect = [_result(True), _result(True)]
        destination = RemoteDestination(executor)

        # Act
        outcome = destination.write(dest_path, "contenu distant", 0o640)

        # Assert
        assert outcome.success is True
        assert executor.run.call_args_list == [
            (
                (["mkdir", "-p", "--", "/etc/app"],),
                {},
            ),
            (
                (
                    [
                        "install",
                        "-m",
                        "640",
                        "-T",
                        "/dev/stdin",
                        str(dest_path),
                    ],
                ),
                {"stdin": "contenu distant"},
            ),
        ]
        assert destination.label == "distant"

    @pytest.mark.parametrize(
        "mode,expected",
        [
            (0o600, "600"),
            (0o644, "644"),
            (0o755, "755"),
            (0o400, "400"),
        ],
    )
    def test_remote_formate_le_mode_pour_install(
        self, mode: int, expected: str
    ) -> None:
        """Le mode POSIX est formaté en octal 3 chiffres pour `-m`."""
        executor = MagicMock(spec=CommandExecutor)
        executor.run.side_effect = [_result(True), _result(True)]
        destination = RemoteDestination(executor)

        destination.write(Path("/tmp/x"), "x", mode)

        install_call = executor.run.call_args_list[1]
        assert install_call.args[0][2] == expected

    def test_remote_echec_install_retourne_outcome_echec(self) -> None:
        """L'échec d'`install` retourne un outcome en échec (mkdir a
        réussi)."""
        # Arrange
        dest_path = Path("/etc/app/config.toml")
        executor = MagicMock(spec=CommandExecutor)
        executor.run.side_effect = [
            _result(True),
            _result(success=False, stderr="permission denied"),
        ]
        destination = RemoteDestination(executor)

        # Act
        outcome = destination.write(dest_path, "contenu", 0o644)

        # Assert
        assert outcome.success is False
        assert "permission denied" in outcome.detail
        assert executor.run.call_count == 2

    def test_remote_echec_mkdir_retourne_outcome_echec_sans_appeler_install(
        self,
    ) -> None:
        """L'échec de `mkdir -p` retourne un outcome en échec et
        n'appelle jamais `install`."""
        # Arrange
        dest_path = Path("/etc/app/config.toml")
        executor = MagicMock(spec=CommandExecutor)
        executor.run.return_value = _result(
            success=False, stderr="Permission denied"
        )
        destination = RemoteDestination(executor)

        # Act
        outcome = destination.write(dest_path, "contenu", 0o644)

        # Assert
        assert outcome.success is False
        assert "création du répertoire distant /etc/app" in outcome.detail
        assert "Permission denied" in outcome.detail
        assert executor.run.call_count == 1

    def test_remote_mkdir_protege_un_parent_commencant_par_tiret(self) -> None:
        """`--` empêche un parent relatif en `-x` d'être lu comme option."""
        # Arrange
        executor = MagicMock(spec=CommandExecutor)
        executor.run.side_effect = [_result(True), _result(True)]
        destination = RemoteDestination(executor)

        # Act
        destination.write("-x/f", "c", 0o600)

        # Assert
        assert executor.run.call_args_list[0].args[0] == [
            "mkdir",
            "-p",
            "--",
            "-x",
        ]


def _rc(code: int, stderr: str = "") -> CommandResult:
    """CommandResult avec un code de retour précis."""
    return CommandResult(
        command=(),
        return_code=code,
        stdout="",
        stderr=stderr,
        success=code == 0,
        duration=0.01,
    )


def _scripted_executor(
    codes: dict[str, int],
) -> MagicMock:
    """Exécuteur dont le code de retour dépend de la commande (argv[0])."""
    executor = MagicMock(spec=CommandExecutor)
    executor.run.side_effect = lambda cmd, **_kw: _rc(codes.get(cmd[0], 0))
    return executor


def _argv0(executor: MagicMock) -> list[str]:
    """Liste des commandes (argv[0]) appelées, dans l'ordre."""
    return [c.args[0][0] for c in executor.run.call_args_list]


class TestRemoteDestinationKeep:
    """Tests de RemoteDestination.write(if_exists="keep")."""

    def test_write_keep_distant_fichier_existant_aucune_ecriture(
        self,
    ) -> None:
        """F-07 : sonde code 0 -> kept, aucune autre commande."""
        executor = _scripted_executor({"test": 0})

        outcome = RemoteDestination(executor).write(
            "/etc/a.env", "A=\n", 0o600, if_exists="keep"
        )

        assert outcome == WriteOutcome(True, kept=True)
        assert _argv0(executor) == ["test"]

    @pytest.mark.parametrize("code", [2, 127, 255])
    def test_write_keep_distant_sonde_code_2_echoue_sans_ecriture(
        self, code: int
    ) -> None:
        """Échec fermé : une sonde ambiguë n'écrit rien."""
        executor = _scripted_executor({"test": code})

        outcome = RemoteDestination(executor).write(
            "/etc/a.env", "A=\n", 0o600, if_exists="keep"
        )

        assert outcome.success is False
        assert outcome.kept is False
        assert f"code {code}" in outcome.detail
        assert _argv0(executor) == ["test"]

    def test_write_keep_distant_course_ln_echoue_nettoie_le_temporaire(
        self,
    ) -> None:
        """Course : ln échoue après install -> échec, rm du temporaire."""
        executor = _scripted_executor({"test": 1, "ln": 1})

        outcome = RemoteDestination(executor).write(
            "/etc/a.env", "A=\n", 0o600, if_exists="keep"
        )

        assert outcome.success is False
        assert outcome.kept is False
        assert "existe déjà" in outcome.detail
        assert _argv0(executor) == ["test", "mkdir", "install", "ln", "rm"]

    def test_write_keep_distant_rm_temporaire_echoue_avertit(self) -> None:
        """F07 : un temporaire non supprimé est signalé (warning)."""
        executor = _scripted_executor({"test": 1, "rm": 1})
        logger = MagicMock()

        with patch(
            "linuxtools.deploy.destinations.secrets.token_hex",
            return_value="ab12",
        ):
            outcome = RemoteDestination(executor, logger).write(
                "/etc/a.env", "A=\n", 0o600, if_exists="keep"
            )

        assert outcome == WriteOutcome(True)
        logger.log_warning.assert_called_once()
        assert "/etc/a.env.ab12.tmp" in logger.log_warning.call_args.args[0]

    def test_write_keep_distant_rm_echoue_sans_logger_ne_leve_pas(
        self,
    ) -> None:
        """Sans logger, l'échec du nettoyage reste silencieux."""
        executor = _scripted_executor({"test": 1, "rm": 1})

        outcome = RemoteDestination(executor).write(
            "/etc/a.env", "A=\n", 0o600, if_exists="keep"
        )

        assert outcome == WriteOutcome(True)

    def test_write_keep_distant_absent_cree_via_install_puis_ln_puis_rm(
        self,
    ) -> None:
        """Nominal : sonde, mkdir, install tmp (stdin), ln, rm."""
        executor = _scripted_executor({"test": 1})

        with patch(
            "linuxtools.deploy.destinations.secrets.token_hex",
            return_value="ab12",
        ):
            outcome = RemoteDestination(executor).write(
                "/etc/a.env", "A=\n", 0o600, if_exists="keep"
            )

        tmp = "/etc/a.env.ab12.tmp"
        assert outcome == WriteOutcome(True)
        assert [c.args[0] for c in executor.run.call_args_list] == [
            ["test", "-e", "/etc/a.env", "-o", "-L", "/etc/a.env"],
            ["mkdir", "-p", "--", "/etc"],
            ["install", "-m", "600", "-T", "/dev/stdin", tmp],
            ["ln", "-T", "--", tmp, "/etc/a.env"],
            ["rm", "-f", "--", tmp],
        ]

    def test_write_keep_distant_echec_install_nettoie_le_temporaire(
        self,
    ) -> None:
        """install en échec -> échec, rm du temporaire, pas de ln."""
        executor = _scripted_executor({"test": 1, "install": 1})

        outcome = RemoteDestination(executor).write(
            "/etc/a.env", "A=\n", 0o600, if_exists="keep"
        )

        assert outcome.success is False
        assert _argv0(executor) == ["test", "mkdir", "install", "rm"]

    def test_write_keep_distant_echec_mkdir_n_ecrit_rien(self) -> None:
        """mkdir en échec -> échec sans install."""
        executor = _scripted_executor({"test": 1, "mkdir": 1})

        outcome = RemoteDestination(executor).write(
            "/etc/a.env", "A=\n", 0o600, if_exists="keep"
        )

        assert outcome.success is False
        assert _argv0(executor) == ["test", "mkdir"]

    def test_write_keep_distant_lien_symbolique_existant_non_suivi(
        self,
    ) -> None:
        """Lien planté : la sonde -L répond 0 -> kept, rien n'est suivi."""
        executor = _scripted_executor({"test": 0})

        outcome = RemoteDestination(executor).write(
            "/etc/lien", "A=\n", 0o600, if_exists="keep"
        )

        assert outcome.kept is True
        assert "-L" in executor.run.call_args_list[0].args[0]
        assert _argv0(executor) == ["test"]

    def test_write_keep_distant_ne_met_jamais_le_contenu_en_argv(
        self,
    ) -> None:
        """Le contenu ne passe que par stdin."""
        executor = _scripted_executor({"test": 1})

        RemoteDestination(executor).write(
            "/etc/a.env", "SENTINELLE=secret\n", 0o600, if_exists="keep"
        )

        for call in executor.run.call_args_list:
            assert all("SENTINELLE" not in a for a in call.args[0])
        stdins = [
            c.kwargs["stdin"]
            for c in executor.run.call_args_list
            if "stdin" in c.kwargs
        ]
        assert stdins == ["SENTINELLE=secret\n"]


class TestDestinationFor:
    """Tests de la fabrique destination_for."""

    def test_destination_for_retourne_local_si_cible_locale(self) -> None:
        """Cible locale (host=None) -> LocalDestination."""
        target = DeployTarget()
        executor = MagicMock(spec=CommandExecutor)

        destination = destination_for(target, executor)

        assert isinstance(destination, LocalDestination)

    def test_destination_for_retourne_remote_portant_l_executor(self) -> None:
        """Cible distante -> RemoteDestination portant l'executor fourni."""
        target = DeployTarget(host="serveur.example.com")
        executor = MagicMock(spec=CommandExecutor)

        destination = destination_for(target, executor)

        assert isinstance(destination, RemoteDestination)
        assert destination.executor is executor

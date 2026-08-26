"""Tests pour linuxtools.filesystem.acl."""

import os
import stat
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from linuxtools.commands import LinuxCommandExecutor
from linuxtools.filesystem.acl import ensure_shared_group_directory


def _result_ok() -> MagicMock:
    r = MagicMock()
    r.success = True
    r.return_code = 0
    return r


def _result_fail(code: int = 1) -> MagicMock:
    r = MagicMock()
    r.success = False
    r.return_code = code
    return r


@pytest.fixture
def executor() -> MagicMock:
    mock = MagicMock(spec=LinuxCommandExecutor)
    mock.run.return_value = _result_ok()
    return mock


def _mock_grp(gid: int) -> MagicMock:
    """Fabrique un faux résultat grp.getgrnam avec le GID donné."""
    mock_grp = MagicMock()
    mock_grp.gr_gid = gid
    return mock_grp


class TestEnsureSharedGroupDirectory:
    """Tests pour ensure_shared_group_directory."""

    def test_pose_gid_setgid_et_acl_cas_nominal(
        self,
        tmp_path: Path,
        executor: MagicMock,
    ) -> None:
        """Cas nominal : chown/setgid appliqués + setfacl invoqué."""
        # GID du process de test : évite de nécessiter root.
        current_gid = os.getgid()
        directory = tmp_path / "partage"
        directory.mkdir()

        with patch(
            "linuxtools.filesystem.acl.grp.getgrnam",
            return_value=_mock_grp(current_gid),
        ):
            ensure_shared_group_directory(
                directory,
                "partage-lan",
                executor=executor,
            )

        result = os.stat(directory)
        assert result.st_gid == current_gid
        assert stat.S_IMODE(result.st_mode) == 0o2770
        assert stat.S_ISGID & result.st_mode

        executor.run.assert_called_once()
        cmd = executor.run.call_args[0][0]
        assert cmd[0] == "setfacl"
        assert "-d" in cmd
        assert "-m" in cmd
        assert "g:partage-lan:rwx" in cmd
        assert str(directory) in cmd

    def test_declenche_fchown_si_gid_differe(
        self,
        tmp_path: Path,
        executor: MagicMock,
    ) -> None:
        """GID réel du répertoire différent du GID attendu → fchown appelé."""
        directory = tmp_path / "partage"
        directory.mkdir()
        real_stat = os.stat(directory)
        fake_stat = MagicMock()
        fake_stat.st_gid = real_stat.st_gid + 1
        fake_stat.st_mode = real_stat.st_mode

        with (
            patch(
                "linuxtools.filesystem.acl.grp.getgrnam",
                return_value=_mock_grp(real_stat.st_gid),
            ),
            patch(
                "linuxtools.filesystem.acl.os.fstat",
                return_value=fake_stat,
            ) as mock_fstat,
            patch(
                "linuxtools.filesystem.acl.os.fchown",
            ) as mock_fchown,
        ):
            ensure_shared_group_directory(
                directory,
                "partage-lan",
                executor=executor,
            )

        mock_fstat.assert_called_once()
        mock_fchown.assert_called_once_with(
            mock_fchown.call_args[0][0],
            -1,
            real_stat.st_gid,
        )

    def test_logge_message_recapitulatif_si_logger_fourni(
        self,
        tmp_path: Path,
        executor: MagicMock,
    ) -> None:
        """Un logger fourni reçoit un message récapitulatif en fin d'appel."""
        directory = tmp_path / "partage"
        directory.mkdir()
        logger = MagicMock()

        with patch(
            "linuxtools.filesystem.acl.grp.getgrnam",
            return_value=_mock_grp(os.getgid()),
        ):
            ensure_shared_group_directory(
                directory,
                "partage-lan",
                executor=executor,
                logger=logger,
            )

        logger.log_info.assert_called_once()

    def test_idempotent_si_deja_conforme(
        self,
        tmp_path: Path,
        executor: MagicMock,
    ) -> None:
        """Rejoue sans erreur si le répertoire est déjà conforme."""
        current_gid = os.getgid()
        directory = tmp_path / "partage"
        directory.mkdir()

        with patch(
            "linuxtools.filesystem.acl.grp.getgrnam",
            return_value=_mock_grp(current_gid),
        ):
            ensure_shared_group_directory(
                directory,
                "partage-lan",
                executor=executor,
            )
            # Deuxième appel : déjà conforme (chown/chmod non déclenchés
            # de nouveau, mais setfacl reste rejoué sans erreur).
            ensure_shared_group_directory(
                directory,
                "partage-lan",
                executor=executor,
            )

        assert executor.run.call_count == 2

    def test_leve_oserror_si_symlink(
        self,
        tmp_path: Path,
        executor: MagicMock,
    ) -> None:
        """Lève OSError si path est un lien symbolique (O_NOFOLLOW)."""
        real_dir = tmp_path / "reel"
        real_dir.mkdir()
        link = tmp_path / "lien"
        link.symlink_to(real_dir)

        with patch(
            "linuxtools.filesystem.acl.grp.getgrnam",
            return_value=_mock_grp(os.getgid()),
        ):
            with pytest.raises(OSError):
                ensure_shared_group_directory(
                    link,
                    "partage-lan",
                    executor=executor,
                )
        executor.run.assert_not_called()

    def test_leve_value_error_si_nom_groupe_invalide(
        self,
        tmp_path: Path,
        executor: MagicMock,
    ) -> None:
        """Lève ValueError si le nom de groupe est invalide (injection ACL)."""
        directory = tmp_path / "partage"
        directory.mkdir()

        with pytest.raises(ValueError, match="Nom Unix invalide"):
            ensure_shared_group_directory(
                directory,
                "a:evil",
                executor=executor,
            )
        executor.run.assert_not_called()

    def test_leve_keyerror_si_groupe_absent(
        self,
        tmp_path: Path,
        executor: MagicMock,
    ) -> None:
        """Lève KeyError si le groupe est inconnu du système."""
        directory = tmp_path / "partage"
        directory.mkdir()

        with patch(
            "linuxtools.filesystem.acl.grp.getgrnam",
            side_effect=KeyError("partage-lan"),
        ):
            with pytest.raises(KeyError):
                ensure_shared_group_directory(
                    directory,
                    "partage-lan",
                    executor=executor,
                )
        executor.run.assert_not_called()

    def test_ne_leve_plus_command_execution_error_si_setfacl_echoue(
        self,
        tmp_path: Path,
        executor: MagicMock,
    ) -> None:
        """L'ACL est best-effort : setfacl en échec ne lève plus rien
        (bascule silencieuse sur nfs4_setfacl, cf. tests dédiés).
        """
        directory = tmp_path / "partage"
        directory.mkdir()
        executor.run.return_value = _result_fail(2)

        with patch(
            "linuxtools.filesystem.acl.grp.getgrnam",
            return_value=_mock_grp(os.getgid()),
        ):
            # Ne doit lever aucune exception, y compris quand les deux
            # outils ACL échouent (cf. test dédié au warning ci-dessous).
            ensure_shared_group_directory(
                directory,
                "partage-lan",
                executor=executor,
            )

    def test_bascule_nfs4_setfacl_si_setfacl_echoue(
        self,
        tmp_path: Path,
        executor: MagicMock,
    ) -> None:
        """setfacl échoue → repli sur nfs4_setfacl, qui réussit."""
        directory = tmp_path / "partage"
        directory.mkdir()
        executor.run.side_effect = [_result_fail(1), _result_ok()]
        logger = MagicMock()

        with patch(
            "linuxtools.filesystem.acl.grp.getgrnam",
            return_value=_mock_grp(os.getgid()),
        ):
            ensure_shared_group_directory(
                directory,
                "partage-lan",
                executor=executor,
                logger=logger,
            )

        assert executor.run.call_count == 2
        logger.log_info.assert_called_once()
        logger.log_warning.assert_not_called()
        premiere_cmd = executor.run.call_args_list[0][0][0]
        seconde_cmd = executor.run.call_args_list[1][0][0]
        assert premiere_cmd[0] == "setfacl"
        assert seconde_cmd[0] == "nfs4_setfacl"
        assert "-a" in seconde_cmd
        assert "A:fdig:partage-lan:RWX" in seconde_cmd
        assert str(directory) in seconde_cmd

    def test_logge_warning_si_aucune_acl_disponible(
        self,
        tmp_path: Path,
        executor: MagicMock,
    ) -> None:
        """setfacl et nfs4_setfacl échouent tous les deux → warning loggé,
        aucune exception levée.
        """
        directory = tmp_path / "partage"
        directory.mkdir()
        executor.run.return_value = _result_fail(1)
        logger = MagicMock()

        with patch(
            "linuxtools.filesystem.acl.grp.getgrnam",
            return_value=_mock_grp(os.getgid()),
        ):
            ensure_shared_group_directory(
                directory,
                "partage-lan",
                executor=executor,
                logger=logger,
            )

        assert executor.run.call_count == 2
        logger.log_warning.assert_called_once()
        logger.log_info.assert_not_called()

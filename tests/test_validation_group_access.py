"""Tests unitaires pour PathCheckerGroupAccess."""

import os
import stat
from unittest.mock import MagicMock, patch

import pytest

from linuxtools.validation.path_checker_group_access import (
    PathCheckerGroupAccess,
)

GID_FF_HOME = 1001

# Mode rwxrwxr-x + setgid
MODE_SETGID_RWX = (
    stat.S_ISGID
    | stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR
    | stat.S_IRGRP | stat.S_IWGRP | stat.S_IXGRP
    | stat.S_IROTH | stat.S_IXOTH
)


def _make_stat(gid: int, mode: int) -> MagicMock:
    """Crée un os.stat_result factice."""
    result = MagicMock(spec=os.stat_result)
    result.st_gid = gid
    result.st_mode = mode
    return result


def _grp_entry(gid: int) -> MagicMock:
    """Crée une entrée grp factice."""
    entry = MagicMock()
    entry.gr_gid = gid
    return entry


@pytest.fixture
def mock_getgrnam():
    """Patch grp.getgrnam → GID 1001 pour 'ff_home'."""
    with patch(
        "linuxtools.validation"
        ".path_checker_group_access.grp.getgrnam",
        return_value=_grp_entry(GID_FF_HOME),
    ) as m:
        yield m


class TestPathCheckerGroupAccess:
    """Tests pour PathCheckerGroupAccess."""

    def test_validate_répertoire_valide(self, mock_getgrnam) -> None:
        """validate() silencieux si groupe, rwx et setgid corrects."""
        checker = PathCheckerGroupAccess("/media/nas/keepass", "ff_home")
        with patch(
            "linuxtools.validation"
            ".path_checker_group_access.os.stat",
            return_value=_make_stat(GID_FF_HOME, MODE_SETGID_RWX),
        ):
            checker.validate()

    def test_validate_répertoire_inexistant(self, mock_getgrnam) -> None:
        """FileNotFoundError si le répertoire n'existe pas."""
        checker = PathCheckerGroupAccess("/inexistant", "ff_home")
        with patch(
            "linuxtools.validation"
            ".path_checker_group_access.os.stat",
            side_effect=FileNotFoundError,
        ):
            with pytest.raises(FileNotFoundError, match="introuvable"):
                checker.validate()

    def test_validate_groupe_inconnu_leve_key_error(self) -> None:
        """KeyError si le groupe n'existe pas sur le système."""
        with patch(
            "linuxtools.validation"
            ".path_checker_group_access.grp.getgrnam",
            side_effect=KeyError("ff_home"),
        ):
            checker = PathCheckerGroupAccess("/media/nas", "ff_home")
            with pytest.raises(KeyError):
                checker.validate()

    def test_validate_mauvais_groupe(self, mock_getgrnam) -> None:
        """PermissionError si le répertoire n'appartient pas au groupe."""
        checker = PathCheckerGroupAccess("/media/nas/keepass", "ff_home")
        with patch(
            "linuxtools.validation"
            ".path_checker_group_access.os.stat",
            return_value=_make_stat(9999, MODE_SETGID_RWX),
        ):
            with pytest.raises(PermissionError, match="ff_home"):
                checker.validate()

    def test_validate_message_mauvais_groupe_contient_gids(
        self, mock_getgrnam
    ) -> None:
        """Le message indique le groupe réel et le groupe attendu."""
        checker = PathCheckerGroupAccess("/media/nas/keepass", "ff_home")
        with patch(
            "linuxtools.validation"
            ".path_checker_group_access.os.stat",
            return_value=_make_stat(9999, MODE_SETGID_RWX),
        ):
            with patch(
                "linuxtools.validation"
                ".path_checker_group_access.grp.getgrgid",
                return_value=_grp_entry(9999),
            ):
                with pytest.raises(PermissionError) as exc_info:
                    checker.validate()
                msg = str(exc_info.value)
                assert "9999" in msg
                assert str(GID_FF_HOME) in msg

    def test_validate_permissions_w_manquant(self, mock_getgrnam) -> None:
        """PermissionError si le bit w est absent pour le groupe."""
        checker = PathCheckerGroupAccess("/media/nas/keepass", "ff_home")
        mode = stat.S_ISGID | stat.S_IRGRP | stat.S_IXGRP  # sans W
        with patch(
            "linuxtools.validation"
            ".path_checker_group_access.os.stat",
            return_value=_make_stat(GID_FF_HOME, mode),
        ):
            with pytest.raises(PermissionError, match="w"):
                checker.validate()

    def test_validate_permissions_message_contient_chmod(
        self, mock_getgrnam
    ) -> None:
        """Le message d'erreur inclut la commande chmod corrective."""
        checker = PathCheckerGroupAccess("/media/nas/keepass", "ff_home")
        mode = stat.S_ISGID | stat.S_IRGRP | stat.S_IXGRP  # sans W
        with patch(
            "linuxtools.validation"
            ".path_checker_group_access.os.stat",
            return_value=_make_stat(GID_FF_HOME, mode),
        ):
            with pytest.raises(PermissionError) as exc_info:
                checker.validate()
            assert "chmod g+" in str(exc_info.value)

    def test_validate_setgid_absent_leve_si_requis(
        self, mock_getgrnam
    ) -> None:
        """PermissionError si setgid absent et require_setgid=True."""
        checker = PathCheckerGroupAccess(
            "/media/nas/keepass", "ff_home", require_setgid=True
        )
        mode = stat.S_IRGRP | stat.S_IWGRP | stat.S_IXGRP  # sans setgid
        with patch(
            "linuxtools.validation"
            ".path_checker_group_access.os.stat",
            return_value=_make_stat(GID_FF_HOME, mode),
        ):
            with pytest.raises(PermissionError, match="setgid"):
                checker.validate()

    def test_validate_setgid_absent_ignoré_si_non_requis(
        self, mock_getgrnam
    ) -> None:
        """validate() silencieux si setgid absent et require_setgid=False."""
        checker = PathCheckerGroupAccess(
            "/media/nas/keepass", "ff_home", require_setgid=False
        )
        mode = stat.S_IRGRP | stat.S_IWGRP | stat.S_IXGRP  # sans setgid
        with patch(
            "linuxtools.validation"
            ".path_checker_group_access.os.stat",
            return_value=_make_stat(GID_FF_HOME, mode),
        ):
            checker.validate()

    def test_validate_setgid_message_contient_chmod_gs(
        self, mock_getgrnam
    ) -> None:
        """Le message setgid inclut la commande chmod g+s corrective."""
        checker = PathCheckerGroupAccess("/media/nas/keepass", "ff_home")
        mode = stat.S_IRGRP | stat.S_IWGRP | stat.S_IXGRP
        with patch(
            "linuxtools.validation"
            ".path_checker_group_access.os.stat",
            return_value=_make_stat(GID_FF_HOME, mode),
        ):
            with pytest.raises(PermissionError) as exc_info:
                checker.validate()
            assert "chmod g+s" in str(exc_info.value)


class TestMissingGroupBits:
    """Tests unitaires pour PathCheckerGroupAccess._missing_group_bits."""

    def test_tous_présents(self) -> None:
        """Retourne chaîne vide si tous les bits rwx sont positionnés."""
        mode = stat.S_IRGRP | stat.S_IWGRP | stat.S_IXGRP
        assert PathCheckerGroupAccess._missing_group_bits(mode) == ""

    def test_tous_manquants(self) -> None:
        """Retourne 'rwx' si aucun bit groupe n'est positionné."""
        assert PathCheckerGroupAccess._missing_group_bits(0) == "rwx"

    def test_seul_r_manquant(self) -> None:
        """Retourne 'r' si seul le bit lecture est absent."""
        mode = stat.S_IWGRP | stat.S_IXGRP
        assert PathCheckerGroupAccess._missing_group_bits(mode) == "r"

    def test_seul_w_manquant(self) -> None:
        """Retourne 'w' si seul le bit écriture est absent."""
        mode = stat.S_IRGRP | stat.S_IXGRP
        assert PathCheckerGroupAccess._missing_group_bits(mode) == "w"

    def test_seul_x_manquant(self) -> None:
        """Retourne 'x' si seul le bit exécution est absent."""
        mode = stat.S_IRGRP | stat.S_IWGRP
        assert PathCheckerGroupAccess._missing_group_bits(mode) == "x"

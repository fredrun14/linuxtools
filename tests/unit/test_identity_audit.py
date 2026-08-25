"""Tests pour linuxtools.identity.audit."""

from unittest.mock import MagicMock, patch

from linuxtools.identity.audit import group_gid_drift, user_uid_drift


class TestGroupGidDrift:
    """Tests pour group_gid_drift."""

    def test_group_gid_drift_retourne_none_si_conforme(self) -> None:
        """GID réel == attendu → None."""
        mock_grp = MagicMock()
        mock_grp.gr_gid = 1042
        with patch(
            "linuxtools.identity.audit.grp.getgrnam",
            return_value=mock_grp,
        ):
            assert group_gid_drift("partage-lan", 1042) is None

    def test_group_gid_drift_retourne_gid_reel_si_divergent(self) -> None:
        """GID réel != attendu → GID réel."""
        mock_grp = MagicMock()
        mock_grp.gr_gid = 9999
        with patch(
            "linuxtools.identity.audit.grp.getgrnam",
            return_value=mock_grp,
        ):
            assert group_gid_drift("partage-lan", 1042) == 9999

    def test_group_gid_drift_retourne_none_si_absent(self) -> None:
        """Groupe absent → None (pas un écart)."""
        with patch(
            "linuxtools.identity.audit.grp.getgrnam",
            side_effect=KeyError("partage-lan"),
        ):
            assert group_gid_drift("partage-lan", 1042) is None


class TestUserUidDrift:
    """Tests pour user_uid_drift."""

    def test_user_uid_drift_retourne_none_si_conforme(self) -> None:
        """UID réel == attendu → None."""
        mock_pwd = MagicMock()
        mock_pwd.pw_uid = 1500
        with patch(
            "linuxtools.identity.audit.pwd.getpwnam",
            return_value=mock_pwd,
        ):
            assert user_uid_drift("appsvc", 1500) is None

    def test_user_uid_drift_retourne_uid_reel_si_divergent(self) -> None:
        """UID réel != attendu → UID réel."""
        mock_pwd = MagicMock()
        mock_pwd.pw_uid = 1600
        with patch(
            "linuxtools.identity.audit.pwd.getpwnam",
            return_value=mock_pwd,
        ):
            assert user_uid_drift("appsvc", 1500) == 1600

    def test_user_uid_drift_retourne_none_si_absent(self) -> None:
        """Utilisateur absent → None (pas un écart)."""
        with patch(
            "linuxtools.identity.audit.pwd.getpwnam",
            side_effect=KeyError("appsvc"),
        ):
            assert user_uid_drift("appsvc", 1500) is None

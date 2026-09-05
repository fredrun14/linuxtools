"""Tests pour le module updates.checker."""

from importlib.metadata import PackageNotFoundError
from unittest.mock import MagicMock

import pytest

from linuxtools.logging.base import Logger
from linuxtools.updates.checker import (
    UpdateCheckResult,
    check_for_update,
    format_update_notice,
)
from webapitools.apps.forgejo import ForgejoClient
from webapitools.core.exceptions import ApiError


def _make_client() -> MagicMock:
    """Crée un mock de ForgejoClient."""
    return MagicMock(spec=ForgejoClient)


class TestCheckForUpdate:
    """Tests pour check_for_update()."""

    def test_check_for_update_retourne_checked_false_si_paquet_non_installe(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Paquet non installé -> checked False, pas d'exception."""

        def _leve_package_not_found(_package: str) -> str:
            raise PackageNotFoundError()

        monkeypatch.setattr(
            "linuxtools.updates.checker.version",
            _leve_package_not_found,
        )
        client = _make_client()

        result = check_for_update(
            "mon-outil", "fred", "mon-outil", client
        )

        assert result.checked is False
        assert result.update_available is False
        assert "non installé" in result.detail

    def test_check_for_update_retourne_checked_false_si_forgejo_injoignable(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """ForgejoClient injoignable (ApiError) -> checked False."""
        monkeypatch.setattr(
            "linuxtools.updates.checker.version",
            lambda _package: "1.0.0",
        )
        client = _make_client()
        client.get_latest_release.side_effect = ApiError("timeout")
        logger = MagicMock(spec=Logger)

        result = check_for_update(
            "mon-outil", "fred", "mon-outil", client, logger=logger
        )

        assert result.checked is False
        assert result.update_available is False
        assert "injoignable" in result.detail
        logger.log_warning.assert_called_once()

    def test_check_for_update_retourne_checked_false_si_aucune_release(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Aucune release publiée (None) -> checked False."""
        monkeypatch.setattr(
            "linuxtools.updates.checker.version",
            lambda _package: "1.0.0",
        )
        client = _make_client()
        client.get_latest_release.return_value = None

        result = check_for_update(
            "mon-outil", "fred", "mon-outil", client
        )

        assert result.checked is False
        assert result.update_available is False
        assert "aucune release" in result.detail

    def test_check_for_update_retourne_checked_false_si_tag_non_parsable(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """tag_name non numérique -> checked False."""
        monkeypatch.setattr(
            "linuxtools.updates.checker.version",
            lambda _package: "1.0.0",
        )
        client = _make_client()
        client.get_latest_release.return_value = {"tag_name": "latest"}

        result = check_for_update(
            "mon-outil", "fred", "mon-outil", client
        )

        assert result.checked is False
        assert result.update_available is False
        assert "format de version non reconnu" in result.detail

    def test_check_for_update_retourne_update_available_true_cas_nominal(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Release plus récente disponible -> update_available True."""
        monkeypatch.setattr(
            "linuxtools.updates.checker.version",
            lambda _package: "1.0.0",
        )
        client = _make_client()
        client.get_latest_release.return_value = {"tag_name": "v1.2.0"}
        logger = MagicMock(spec=Logger)

        result = check_for_update(
            "mon-outil", "fred", "mon-outil", client, logger=logger
        )

        assert result.checked is True
        assert result.update_available is True
        assert result.latest_version == "v1.2.0"
        assert result.current_version == "1.0.0"
        logger.log_info.assert_called_once()

    def test_check_for_update_retourne_update_available_false_si_deja_a_jour(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Déjà à jour -> checked True, update_available False."""
        monkeypatch.setattr(
            "linuxtools.updates.checker.version",
            lambda _package: "1.2.0",
        )
        client = _make_client()
        client.get_latest_release.return_value = {"tag_name": "v1.2.0"}

        result = check_for_update(
            "mon-outil", "fred", "mon-outil", client
        )

        assert result.checked is True
        assert result.update_available is False


class TestFormatUpdateNotice:
    """Tests pour format_update_notice()."""

    @pytest.mark.parametrize(
        ("checked", "update_available"),
        [(False, True), (True, False), (False, False)],
    )
    def test_format_update_notice_retourne_none_si_non_checked_ou_a_jour(
        self, checked: bool, update_available: bool
    ) -> None:
        """Non vérifié ou déjà à jour -> None, aucun bruit."""
        result = UpdateCheckResult(
            package="mon-outil",
            current_version="1.0.0",
            latest_version="1.1.0",
            update_available=update_available,
            checked=checked,
            detail="peu importe",
        )

        assert format_update_notice(result) is None

    def test_format_update_notice_retourne_message_si_maj_disponible(
        self,
    ) -> None:
        """Mise à jour disponible -> message formaté prêt à afficher."""
        result = UpdateCheckResult(
            package="mon-outil",
            current_version="1.0.0",
            latest_version="1.1.0",
            update_available=True,
            checked=True,
            detail="mon-outil 1.0.0 -> 1.1.0 disponible",
        )

        message = format_update_notice(result)

        assert message is not None
        assert "mon-outil" in message
        assert "1.0.0" in message
        assert "1.1.0" in message

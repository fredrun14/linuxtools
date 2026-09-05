"""Tests pour le module updates.version_compare."""

import pytest

from linuxtools.updates.version_compare import is_newer, parse_version


class TestParseVersion:
    """Tests pour parse_version()."""

    @pytest.mark.parametrize("text", ["1.26.0", "v1.26.0"])
    def test_parse_version_avec_format_complet_retourne_triplet(
        self, text: str
    ) -> None:
        """Format complet X.Y.Z (avec ou sans préfixe v) -> triplet."""
        assert parse_version(text) == (1, 26, 0)

    @pytest.mark.parametrize(
        ("text", "expected"),
        [("1.2", (1, 2, 0)), ("1", (1, 0, 0))],
    )
    def test_parse_version_avec_composants_manquants_complete_a_zero(
        self, text: str, expected: tuple[int, int, int]
    ) -> None:
        """Composants manquants -> complétés à 0."""
        assert parse_version(text) == expected

    @pytest.mark.parametrize("text", ["", "latest"])
    def test_parse_version_retourne_none_si_non_numerique(
        self, text: str
    ) -> None:
        """Aucun chiffre de tête -> None, pas d'exception."""
        assert parse_version(text) is None


class TestIsNewer:
    """Tests pour is_newer()."""

    def test_is_newer_retourne_true_si_candidate_superieur(self) -> None:
        """candidate > current -> True."""
        assert is_newer("1.3.0", "1.2.0") is True

    @pytest.mark.parametrize(
        ("candidate", "current"),
        [("1.2.0", "1.3.0"), ("1.2.0", "1.2.0")],
    )
    def test_is_newer_retourne_false_si_candidate_inferieur_ou_egal(
        self, candidate: str, current: str
    ) -> None:
        """candidate <= current -> False (inclut l'égalité)."""
        assert is_newer(candidate, current) is False

    def test_is_newer_retourne_none_si_une_version_non_parsable(
        self,
    ) -> None:
        """Une version non parsable -> None, jamais de faux résultat."""
        assert is_newer("latest", "1.2.0") is None
        assert is_newer("1.2.0", "latest") is None

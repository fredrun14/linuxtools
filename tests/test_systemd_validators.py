"""Tests pour le module systemd.validators."""

import pytest

from linuxtools.systemd.validators import (
    reject_control_chars,
    validate_full_unit_name,
    validate_unit_name,
    validate_service_name,
)


class TestValidateUnitName:
    """Tests pour validate_unit_name."""

    @pytest.mark.parametrize("name", [
        "backup",
        "my-service",
        "my_service",
        "my.unit",
        "sys:name",
        "A1",
        "backup-daily_2",
    ])
    def test_noms_valides(self, name: str):
        """Vérifie l'acceptation de noms d'unités valides."""
        assert validate_unit_name(name) == name

    def test_rejet_nom_vide(self):
        """Vérifie le rejet d'un nom vide."""
        with pytest.raises(ValueError, match="vide"):
            validate_unit_name("")

    def test_rejet_traversee_chemin(self):
        """Vérifie le rejet de traversée de chemin."""
        with pytest.raises(ValueError, match="traversée"):
            validate_unit_name("../etc/passwd")

    def test_rejet_slash(self):
        """Vérifie le rejet de slash."""
        with pytest.raises(ValueError, match="traversée"):
            validate_unit_name("foo/bar")

    def test_rejet_injection_point_virgule(self):
        """Vérifie le rejet d'injection de commande."""
        with pytest.raises(ValueError, match="invalide"):
            validate_unit_name("name;cmd")

    def test_rejet_injection_dollar(self):
        """Vérifie le rejet d'injection via $()."""
        with pytest.raises(ValueError, match="invalide"):
            validate_unit_name("name$(cmd)")

    def test_rejet_espaces(self):
        """Vérifie le rejet d'espaces."""
        with pytest.raises(ValueError, match="invalide"):
            validate_unit_name("name with spaces")

    def test_rejet_debut_non_alphanum(self):
        """Vérifie le rejet d'un nom commençant par un tiret."""
        with pytest.raises(ValueError, match="invalide"):
            validate_unit_name("-backup")


class TestValidateServiceName:
    """Tests pour validate_service_name."""

    @pytest.mark.parametrize("name", [
        "backup",
        "my-service",
        "my_service",
        "A1",
        "backup-daily_2",
    ])
    def test_noms_valides(self, name: str):
        """Vérifie l'acceptation de noms de services valides."""
        assert validate_service_name(name) == name

    def test_rejet_nom_vide(self):
        """Vérifie le rejet d'un nom vide."""
        with pytest.raises(ValueError, match="vide"):
            validate_service_name("")

    def test_rejet_traversee_chemin(self):
        """Vérifie le rejet de traversée de chemin."""
        with pytest.raises(ValueError, match="traversée"):
            validate_service_name("../etc/passwd")

    def test_rejet_slash(self):
        """Vérifie le rejet de slash."""
        with pytest.raises(ValueError, match="traversée"):
            validate_service_name("foo/bar")

    def test_rejet_point(self):
        """Vérifie le rejet de points (contrairement à unit_name)."""
        with pytest.raises(ValueError, match="invalide"):
            validate_service_name("my.service")

    def test_rejet_deux_points(self):
        """Vérifie le rejet de deux-points."""
        with pytest.raises(ValueError, match="invalide"):
            validate_service_name("sys:name")

    def test_rejet_caracteres_speciaux(self):
        """Vérifie le rejet de caractères spéciaux."""
        with pytest.raises(ValueError, match="invalide"):
            validate_service_name("name;cmd")


class TestRejectControlChars:
    """Tests pour reject_control_chars."""

    def test_chaine_valide_retournee(self):
        """Retourne la valeur inchangée si elle ne contient aucun contrôle."""
        assert reject_control_chars("valeur normale", "desc") == "valeur normale"

    def test_chaine_vide_acceptee(self):
        """Accepte une chaîne vide."""
        assert reject_control_chars("", "champ") == ""

    def test_rejet_newline(self):
        """Rejette un saut de ligne (\\n)."""
        with pytest.raises(ValueError, match="contrôle"):
            reject_control_chars("ligne1\nligne2", "description")

    def test_rejet_carriage_return(self):
        """Rejette un retour chariot (\\r)."""
        with pytest.raises(ValueError, match="contrôle"):
            reject_control_chars("val\reur", "champ")

    def test_rejet_tab(self):
        """Rejette une tabulation (\\t, code 9 < 32)."""
        with pytest.raises(ValueError, match="contrôle"):
            reject_control_chars("val\teur", "champ")

    def test_message_contient_nom_champ(self):
        """Le message d'erreur mentionne le nom du champ."""
        with pytest.raises(ValueError, match="monchamp"):
            reject_control_chars("val\neur", "monchamp")


class TestValidateFullUnitName:
    """Tests pour validate_full_unit_name."""

    @pytest.mark.parametrize("name", [
        "backup.service",
        "mon-service.timer",
        "media-nas.mount",
        "sshd.socket",
        "my_unit.automount",
    ])
    def test_noms_complets_valides(self, name: str):
        """Accepte les noms complets avec extension autorisée."""
        assert validate_full_unit_name(name) == name

    def test_rejet_sans_extension(self):
        """Rejette un nom sans extension."""
        with pytest.raises(ValueError, match="sans extension"):
            validate_full_unit_name("backup")

    def test_rejet_extension_inconnue(self):
        """Rejette une extension non autorisée."""
        with pytest.raises(ValueError, match="non autorisée"):
            validate_full_unit_name("backup.path")

    def test_rejet_extension_swap(self):
        """Rejette .swap (hors whitelist)."""
        with pytest.raises(ValueError, match="non autorisée"):
            validate_full_unit_name("dev-sda1.swap")

    def test_rejet_radical_invalide(self):
        """Rejette un radical contenant des caractères interdits."""
        with pytest.raises(ValueError):
            validate_full_unit_name("../etc.service")

    def test_rejet_traversal_dans_radical(self):
        """Rejette une tentative de path traversal."""
        with pytest.raises(ValueError):
            validate_full_unit_name("../../etc/cron.service")

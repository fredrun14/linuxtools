"""Tests pour le module systemd.validators."""

import pytest

from linuxtools.systemd.validators import (
    path_to_unit_name,
    reject_control_chars,
    validate_dependency_unit_name,
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
        r"media-nas\x2dbackup",
        r"a\x2d\x2f\x5c",
    ])
    def test_noms_valides(self, name: str) -> None:
        """Vérifie l'acceptation de noms d'unités valides.

        Inclut les échappements ``\\xNN`` de ``systemd-escape --path``.
        """
        assert validate_unit_name(name) == name

    def test_rejet_nom_vide(self) -> None:
        """Vérifie le rejet d'un nom vide."""
        with pytest.raises(ValueError, match="vide"):
            validate_unit_name("")

    def test_rejet_traversee_chemin(self) -> None:
        """Vérifie le rejet de traversée de chemin."""
        with pytest.raises(ValueError, match="traversée"):
            validate_unit_name("../etc/passwd")

    def test_rejet_slash(self) -> None:
        """Vérifie le rejet de slash."""
        with pytest.raises(ValueError, match="traversée"):
            validate_unit_name("foo/bar")

    def test_rejet_injection_point_virgule(self) -> None:
        """Vérifie le rejet d'injection de commande."""
        with pytest.raises(ValueError, match="invalide"):
            validate_unit_name("name;cmd")

    def test_rejet_injection_dollar(self) -> None:
        """Vérifie le rejet d'injection via $()."""
        with pytest.raises(ValueError, match="invalide"):
            validate_unit_name("name$(cmd)")

    def test_rejet_espaces(self) -> None:
        """Vérifie le rejet d'espaces."""
        with pytest.raises(ValueError, match="invalide"):
            validate_unit_name("name with spaces")

    @pytest.mark.parametrize("name", [
        "a\\",
        "a\\n",
        "a\\x",
        "a\\x2",
        "a\\xZZ",
        "a\\x2D",
        "a\\x2g",
        "a\\u002d",
        "a\\\\x2d",
        "a\\x2d\\",
        "a\\x2d\n",
        "a\\x2d%n",
        "a\\x2d/b",
        "a\\x2d..b",
        "\\x2da",
    ])
    def test_rejet_backslash_hors_echappement_hex(self, name: str) -> None:
        """Rejette tout backslash qui n'est pas ``\\x`` + 2 hex minuscules."""
        with pytest.raises(ValueError, match="invalide"):
            validate_unit_name(name)

    @pytest.mark.parametrize("name", [
        r"a\x20", r"a\x7e", r"a\x80", r"a\xff",
        r"a\xc3\xa9", r"a\x8f", r"a\x9f",
    ])
    def test_acceptation_echappement_non_controle(self, name: str) -> None:
        """Accepte les échappements hors contrôles (``\\x20``, ``\\x7e``…)."""
        assert validate_unit_name(name) == name

    @pytest.mark.parametrize("name", [
        "a\\x00", "a\\x00b", "a\\x2d\\x00",
        "a\\x01", "a\\x0a", "a\\x0d", "a\\x10", "a\\x1f", "a\\x7f",
        "a\\x2d\\x1f",
    ])
    def test_rejet_echappement_controle(self, name: str) -> None:
        """Rejette ``\\x00``-``\\x1f`` et ``\\x7f`` (contrôles)."""
        with pytest.raises(ValueError, match="invalide"):
            validate_unit_name(name)

    def test_rejet_debut_non_alphanum(self) -> None:
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
    def test_noms_valides(self, name: str) -> None:
        """Vérifie l'acceptation de noms de services valides."""
        assert validate_service_name(name) == name

    def test_rejet_nom_vide(self) -> None:
        """Vérifie le rejet d'un nom vide."""
        with pytest.raises(ValueError, match="vide"):
            validate_service_name("")

    def test_rejet_traversee_chemin(self) -> None:
        """Vérifie le rejet de traversée de chemin."""
        with pytest.raises(ValueError, match="traversée"):
            validate_service_name("../etc/passwd")

    def test_rejet_slash(self) -> None:
        """Vérifie le rejet de slash."""
        with pytest.raises(ValueError, match="traversée"):
            validate_service_name("foo/bar")

    def test_validate_service_name_rejette_saut_de_ligne_final(self) -> None:
        """SEC : un ``\\n`` final ne passe pas (fullmatch, pas match)."""
        with pytest.raises(ValueError, match="invalide"):
            validate_service_name("x\n")

    def test_validate_service_name_rejette_echappement_systemd(self) -> None:
        """validate_service_name reste restrictif : pas de ``\\xNN``."""
        with pytest.raises(ValueError, match="invalide"):
            validate_service_name("a\\x2db")

    def test_rejet_point(self) -> None:
        """Vérifie le rejet de points (contrairement à unit_name)."""
        with pytest.raises(ValueError, match="invalide"):
            validate_service_name("my.service")

    def test_rejet_deux_points(self) -> None:
        """Vérifie le rejet de deux-points."""
        with pytest.raises(ValueError, match="invalide"):
            validate_service_name("sys:name")

    def test_rejet_caracteres_speciaux(self) -> None:
        """Vérifie le rejet de caractères spéciaux."""
        with pytest.raises(ValueError, match="invalide"):
            validate_service_name("name;cmd")


class TestRejectControlChars:
    """Tests pour reject_control_chars."""

    def test_chaine_valide_retournee(self) -> None:
        """Retourne la valeur inchangée si elle ne contient aucun contrôle."""
        assert reject_control_chars("valeur normale", "desc") == "valeur normale"

    def test_chaine_vide_acceptee(self) -> None:
        """Accepte une chaîne vide."""
        assert reject_control_chars("", "champ") == ""

    def test_rejet_newline(self) -> None:
        """Rejette un saut de ligne (\\n)."""
        with pytest.raises(ValueError, match="contrôle"):
            reject_control_chars("ligne1\nligne2", "description")

    def test_rejet_carriage_return(self) -> None:
        """Rejette un retour chariot (\\r)."""
        with pytest.raises(ValueError, match="contrôle"):
            reject_control_chars("val\reur", "champ")

    def test_rejet_tab(self) -> None:
        """Rejette une tabulation (\\t, code 9 < 32)."""
        with pytest.raises(ValueError, match="contrôle"):
            reject_control_chars("val\teur", "champ")

    def test_message_contient_nom_champ(self) -> None:
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
        r"media-nas\x2dbackup.mount",
        r"media-nas\x2dbackup.automount",
    ])
    def test_noms_complets_valides(self, name: str) -> None:
        """Accepte les noms complets avec extension autorisée."""
        assert validate_full_unit_name(name) == name

    def test_rejet_sans_extension(self) -> None:
        """Rejette un nom sans extension."""
        with pytest.raises(ValueError, match="sans extension"):
            validate_full_unit_name("backup")

    def test_rejet_extension_inconnue(self) -> None:
        """Rejette une extension non autorisée."""
        with pytest.raises(ValueError, match="non autorisée"):
            validate_full_unit_name("backup.path")

    def test_rejet_extension_swap(self) -> None:
        """Rejette .swap (hors whitelist)."""
        with pytest.raises(ValueError, match="non autorisée"):
            validate_full_unit_name("dev-sda1.swap")

    def test_rejet_radical_invalide(self) -> None:
        """Rejette un radical contenant des caractères interdits."""
        with pytest.raises(ValueError):
            validate_full_unit_name("../etc.service")

    @pytest.mark.parametrize("name", [
        "a\\x00.mount",
        "a\\.mount",
        "a\\n.service",
        "a\\x2D.mount",
    ])
    def test_rejet_echappements_invalides_radical(self, name: str) -> None:
        """Rejette les radicaux avec backslash ou échappement invalide."""
        with pytest.raises(ValueError, match="invalide"):
            validate_full_unit_name(name)

    def test_rejet_traversal_dans_radical(self) -> None:
        """Rejette une tentative de path traversal."""
        with pytest.raises(ValueError):
            validate_full_unit_name("../../etc/cron.service")


class TestValidateDependencyUnitName:
    """Tests pour validate_dependency_unit_name."""

    def test_validate_dependency_unit_name_accepte_target(self) -> None:
        """Accepte l'extension target en plus de la liste blanche."""
        name = "network-online.target"
        assert validate_dependency_unit_name(name) == name
        assert validate_dependency_unit_name("a.service") == "a.service"

    @pytest.mark.parametrize("name", ["backup", "a.sh", "a/b.target"])
    def test_validate_dependency_unit_name_rejette(self, name: str) -> None:
        """Rejette sans extension, extension inconnue, traversée."""
        with pytest.raises(ValueError):
            validate_dependency_unit_name(name)

    def test_validate_full_unit_name_refuse_toujours_target(self) -> None:
        """La liste globale n'est pas élargie."""
        with pytest.raises(ValueError, match="non autorisée"):
            validate_full_unit_name("a.target")


class TestPathToUnitName:
    """Tests pour path_to_unit_name."""

    def test_chemin_simple(self) -> None:
        """Convertit un chemin sans caractère spécial."""
        assert path_to_unit_name("/media/nas/backup") == "media-nas-backup"

    @pytest.mark.parametrize("chemin", [
        "/media/a\\x2fb",
        "/media/a\\b",
        "/media/a\\",
    ])
    def test_rejet_backslash_dans_chemin(self, chemin: str) -> None:
        """Rejette un backslash littéral du chemin (collision systemd)."""
        with pytest.raises(ValueError, match="backslash"):
            path_to_unit_name(chemin)

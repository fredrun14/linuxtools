"""Tests pour les validateurs reseau."""

from typing import Any

import pytest

from linuxtools.network.validators import (
    validate_cidr,
    validate_hostname,
    validate_ipv4,
    validate_mac,
)


class TestValidateIpv4:
    """Tests pour validate_ipv4."""

    def test_ip_valide(self) -> None:
        """Adresse IP standard valide."""
        assert validate_ipv4("192.168.1.1") == "192.168.1.1"

    def test_ip_localhost(self) -> None:
        """Adresse localhost valide."""
        assert validate_ipv4("127.0.0.1") == "127.0.0.1"

    def test_ip_broadcast(self) -> None:
        """Adresse broadcast valide."""
        assert validate_ipv4("255.255.255.255") == "255.255.255.255"

    def test_ip_zero(self) -> None:
        """Adresse 0.0.0.0 valide."""
        assert validate_ipv4("0.0.0.0") == "0.0.0.0"

    def test_ip_octet_hors_plage(self) -> None:
        """Octet superieur a 255 leve ValueError."""
        with pytest.raises(ValueError):
            validate_ipv4("192.168.1.256")

    def test_ip_trop_octets(self) -> None:
        """Trop d'octets leve ValueError."""
        with pytest.raises(ValueError):
            validate_ipv4("192.168.1.1.1")

    def test_ip_lettres(self) -> None:
        """Lettres dans l'adresse leve ValueError."""
        with pytest.raises(ValueError):
            validate_ipv4("abc.def.ghi.jkl")

    def test_ip_vide(self) -> None:
        """Chaine vide leve ValueError."""
        with pytest.raises(ValueError):
            validate_ipv4("")

    def test_ip_negative(self) -> None:
        """Octet negatif leve ValueError."""
        with pytest.raises(ValueError):
            validate_ipv4("192.168.1.-1")


class TestValidateMac:
    """Tests pour validate_mac."""

    def test_mac_valide_minuscules(self) -> None:
        """MAC en minuscules retournee telle quelle."""
        assert validate_mac("aa:bb:cc:dd:ee:ff") == "aa:bb:cc:dd:ee:ff"

    def test_mac_valide_majuscules_normalisee(self) -> None:
        """MAC en majuscules normalisee en minuscules."""
        assert validate_mac("AA:BB:CC:DD:EE:FF") == "aa:bb:cc:dd:ee:ff"

    def test_mac_mixte(self) -> None:
        """MAC mixte normalisee en minuscules."""
        assert validate_mac("Aa:Bb:Cc:Dd:Ee:Ff") == "aa:bb:cc:dd:ee:ff"

    def test_mac_invalide_tirets(self) -> None:
        """MAC avec tirets leve ValueError."""
        with pytest.raises(ValueError):
            validate_mac("aa-bb-cc-dd-ee-ff")

    def test_mac_trop_courte(self) -> None:
        """MAC trop courte leve ValueError."""
        with pytest.raises(ValueError):
            validate_mac("aa:bb:cc")

    def test_mac_vide(self) -> None:
        """Chaine vide leve ValueError."""
        with pytest.raises(ValueError):
            validate_mac("")

    def test_mac_caractere_invalide(self) -> None:
        """Caracteres non hexadecimaux leve ValueError."""
        with pytest.raises(ValueError):
            validate_mac("gg:hh:ii:jj:kk:ll")

    def test_validate_mac_rejette_saut_de_ligne_final(self) -> None:
        """Un saut de ligne final leve ValueError."""
        with pytest.raises(ValueError):
            validate_mac("aa:bb:cc:dd:ee:ff\n")

    def test_validate_mac_case_upper_retourne_majuscules(self) -> None:
        """case="upper" retourne la MAC en majuscules."""
        assert (
            validate_mac("aa:bb:cc:dd:ee:ff", case="upper")
            == "AA:BB:CC:DD:EE:FF"
        )

    def test_validate_mac_case_defaut_retourne_minuscules(self) -> None:
        """Sans case, la MAC reste retournee en minuscules."""
        assert validate_mac("AA:BB:CC:DD:EE:FF") == "aa:bb:cc:dd:ee:ff"

    def test_validate_mac_leve_valueerror_si_case_invalide(self) -> None:
        """Une valeur de case hors lower/upper leve ValueError."""
        case_invalide: Any = "UPPER"
        with pytest.raises(ValueError, match="case invalide"):
            validate_mac("aa:bb:cc:dd:ee:ff", case=case_invalide)

    def test_validate_mac_case_invalide_prioritaire_sur_motif(self) -> None:
        """MAC et case invalides : l'erreur levee est celle du case."""
        case_invalide: Any = "UPPER"
        with pytest.raises(ValueError, match="case invalide"):
            validate_mac("pas-une-mac", case=case_invalide)


class TestValidateCidr:
    """Tests pour validate_cidr."""

    def test_cidr_24(self) -> None:
        """CIDR /24 valide."""
        assert validate_cidr("192.168.1.0/24") == "192.168.1.0/24"

    def test_cidr_16(self) -> None:
        """CIDR /16 valide."""
        assert validate_cidr("10.0.0.0/16") == "10.0.0.0/16"

    def test_cidr_32(self) -> None:
        """CIDR /32 valide."""
        assert validate_cidr("192.168.1.1/32") == "192.168.1.1/32"

    def test_cidr_0(self) -> None:
        """CIDR /0 valide."""
        assert validate_cidr("0.0.0.0/0") == "0.0.0.0/0"

    def test_cidr_masque_33(self) -> None:
        """Masque 33 leve ValueError."""
        with pytest.raises(ValueError):
            validate_cidr("192.168.1.0/33")

    def test_cidr_sans_masque(self) -> None:
        """Adresse sans masque leve ValueError."""
        with pytest.raises(ValueError):
            validate_cidr("192.168.1.0")

    def test_cidr_ip_invalide(self) -> None:
        """IP invalide dans CIDR leve ValueError."""
        with pytest.raises(ValueError):
            validate_cidr("999.168.1.0/24")

    def test_validate_cidr_rejette_saut_de_ligne_final(self) -> None:
        """Un saut de ligne final leve ValueError."""
        with pytest.raises(ValueError):
            validate_cidr("192.168.1.0/24\n")


class TestValidateHostname:
    """Tests pour validate_hostname."""

    def test_hostname_simple(self) -> None:
        """Nom d'hote simple valide."""
        assert validate_hostname("nas") == "nas"

    def test_hostname_avec_tiret(self) -> None:
        """Nom d'hote avec tiret valide."""
        assert validate_hostname("my-server") == "my-server"

    def test_hostname_alphanumerique(self) -> None:
        """Nom d'hote alphanumerique valide."""
        assert validate_hostname("server01") == "server01"

    def test_hostname_commence_par_tiret(self) -> None:
        """Nom commencant par tiret leve ValueError."""
        with pytest.raises(ValueError):
            validate_hostname("-invalid")

    def test_hostname_termine_par_tiret(self) -> None:
        """Nom terminant par tiret leve ValueError."""
        with pytest.raises(ValueError):
            validate_hostname("invalid-")

    def test_hostname_trop_long(self) -> None:
        """Nom de 64 caracteres leve ValueError."""
        with pytest.raises(ValueError):
            validate_hostname("a" * 64)

    def test_hostname_vide(self) -> None:
        """Chaine vide leve ValueError."""
        with pytest.raises(ValueError):
            validate_hostname("")

    def test_hostname_caractere_special(self) -> None:
        """Caractere special leve ValueError."""
        with pytest.raises(ValueError):
            validate_hostname("nas@home")

    def test_validate_hostname_rejette_saut_de_ligne_final(self) -> None:
        """Un saut de ligne final leve ValueError."""
        with pytest.raises(ValueError):
            validate_hostname("host\n")

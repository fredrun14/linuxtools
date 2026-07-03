"""Tests pour les validateurs reseau."""

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

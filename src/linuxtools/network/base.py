"""Interfaces abstraites pour le module reseau.

Ce module definit les classes de base abstraites (ABCs) pour
le scan reseau, la persistance, la gestion DHCP/DNS et les
rapports.
"""

from abc import ABC, abstractmethod

from linuxtools.network.config import NetworkConfig
from linuxtools.network.models import (
    MacFilterStatus,
    NetworkDevice,
)


class NetworkScanner(ABC):
    """Interface pour les scanners reseau."""

    @abstractmethod
    def scan(
        self, config: NetworkConfig
    ) -> list[NetworkDevice]:
        """Scanne le reseau et retourne les peripheriques.

        Args:
            config: Configuration reseau.

        Returns:
            Liste des peripheriques decouverts.
        """
        ...


class DeviceRepository(ABC):
    """Interface pour la persistance des peripheriques."""

    @abstractmethod
    def load(self) -> list[NetworkDevice]:
        """Charge les peripheriques depuis le stockage.

        Returns:
            Liste des peripheriques.
        """
        ...

    @abstractmethod
    def save(
        self, devices: list[NetworkDevice]
    ) -> None:
        """Sauvegarde les peripheriques.

        Args:
            devices: Liste des peripheriques a sauvegarder.
        """
        ...

    @abstractmethod
    def find_by_mac(
        self, mac: str
    ) -> NetworkDevice | None:
        """Recherche un peripherique par adresse MAC.

        Args:
            mac: Adresse MAC a rechercher.

        Returns:
            Le peripherique trouve ou None.
        """
        ...

    @abstractmethod
    def find_by_ip(
        self, ip: str
    ) -> NetworkDevice | None:
        """Recherche un peripherique par adresse IP.

        Args:
            ip: Adresse IP a rechercher.

        Returns:
            Le peripherique trouve ou None.
        """
        ...


class DhcpReservationManager(ABC):
    """Interface pour la gestion des reservations DHCP."""

    @abstractmethod
    def generate_reservations(
        self, devices: list[NetworkDevice]
    ) -> list[NetworkDevice]:
        """Genere les reservations DHCP pour les peripheriques.

        Args:
            devices: Liste des peripheriques.

        Returns:
            Liste des peripheriques avec IP fixes assignees.
        """
        ...

    @abstractmethod
    def export_reservations(
        self, devices: list[NetworkDevice]
    ) -> str:
        """Exporte les reservations au format texte.

        Args:
            devices: Liste des peripheriques.

        Returns:
            Reservations formatees.
        """
        ...


class RouterDhcpManager(DhcpReservationManager):
    """Interface DHCP avec application directe au routeur."""

    @abstractmethod
    def apply_reservations(
        self, devices: list[NetworkDevice]
    ) -> None:
        """Envoie les reservations DHCP vers le routeur.

        Args:
            devices: Peripheriques avec IP fixes assignees.
        """
        ...

    @abstractmethod
    def read_reservations(self) -> list[NetworkDevice]:
        """Lit les reservations DHCP existantes du routeur.

        Returns:
            Liste des peripheriques reserves.
        """
        ...


class MacFilterManager(ABC):
    """Interface pour le filtrage MAC Wi-Fi du routeur."""

    @abstractmethod
    def apply_mac_filter(
        self,
        devices: list[NetworkDevice],
        mode: str,
        bands: list[int],
    ) -> None:
        """Applique un filtre MAC sur les bandes Wi-Fi.

        Args:
            devices: Peripheriques dont les MAC constituent
                la liste (whitelist ou blacklist).
            mode: Mode du filtre — 'allow' (liste blanche),
                'deny' (liste noire) ou 'disabled'.
            bands: Indices des bandes Wi-Fi a configurer
                (0 = 2.4 GHz, 1 = 5 GHz).

        Raises:
            ValueError: Si mode ou bands sont invalides.
            RouterAuthError: Si l'authentification echoue.
            RuntimeError: Si l'envoi echoue.
        """
        ...

    @abstractmethod
    def read_mac_filter(
        self, bands: list[int]
    ) -> list[MacFilterStatus]:
        """Lit la configuration du filtre MAC du routeur.

        Args:
            bands: Indices des bandes a lire.

        Returns:
            Liste de MacFilterStatus, une entree par bande.
        """
        ...


class DnsManager(ABC):
    """Interface pour la gestion DNS locale."""

    @abstractmethod
    def generate_dns_names(
        self, devices: list[NetworkDevice]
    ) -> list[NetworkDevice]:
        """Genere les noms DNS pour les peripheriques.

        Args:
            devices: Liste des peripheriques.

        Returns:
            Liste des peripheriques avec noms DNS.
        """
        ...

    @abstractmethod
    def generate_hosts_entries(
        self, devices: list[NetworkDevice]
    ) -> str:
        """Genere les entrees pour le fichier hosts.

        Args:
            devices: Liste des peripheriques.

        Returns:
            Contenu du fichier hosts.
        """
        ...


class DeviceReporter(ABC):
    """Interface pour les rapports de peripheriques."""

    @abstractmethod
    def report(
        self, devices: list[NetworkDevice]
    ) -> str:
        """Genere un rapport des peripheriques.

        Args:
            devices: Liste des peripheriques.

        Returns:
            Rapport formate.
        """
        ...

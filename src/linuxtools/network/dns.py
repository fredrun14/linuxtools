"""Gestion DNS locale.

Ce module fournit les implementations pour generer les noms DNS
locaux et les fichiers de configuration (hosts, dnsmasq).
"""

import dataclasses
import re
from abc import ABC, abstractmethod
from datetime import datetime

from linuxtools.logging.base import Logger
from linuxtools.network.base import DnsManager
from linuxtools.network.config import NetworkConfig
from linuxtools.network.models import NetworkDevice


def _sanitize_dns_label(label: str) -> str:
    """Nettoie un label pour l'utiliser dans un nom DNS.

    Args:
        label: Texte a nettoyer.

    Returns:
        Label valide en minuscules.
    """
    label = label.lower().strip()
    label = re.sub(r"[^a-z0-9-]", "-", label)
    label = re.sub(r"-+", "-", label)
    return label.strip("-")[:63]


class _BaseDnsManager(DnsManager, ABC):
    """Base commune pour les gestionnaires DNS locaux.

    Porte la logique de generation de noms DNS partagee
    entre LinuxHostsFileManager et LinuxDnsmasqConfigGenerator.

    Attributes:
        _config: Configuration reseau.
        _logger: Logger optionnel.
    """

    def __init__(
        self,
        config: NetworkConfig,
        logger: Logger | None = None,
    ) -> None:
        """Initialise le gestionnaire DNS.

        Args:
            config: Configuration reseau.
            logger: Logger optionnel.
        """
        self._config = config
        self._logger = logger

    def generate_dns_names(
        self, devices: list[NetworkDevice]
    ) -> list[NetworkDevice]:
        """Genere les noms DNS pour les peripheriques.

        Args:
            devices: Liste des peripheriques.

        Returns:
            Liste des peripheriques avec noms DNS.
        """
        domain = self._config.dns.domain
        result: list[NetworkDevice] = []
        for device in devices:
            if device.dns_name:
                result.append(device)
                continue
            name = _generate_dns_name(device, domain)
            result.append(
                dataclasses.replace(
                    device, dns_name=name
                )
            )
        return result

    @abstractmethod
    def generate_hosts_entries(
        self, devices: list[NetworkDevice]
    ) -> str:
        """Genere le contenu du fichier de configuration.

        Args:
            devices: Liste des peripheriques.

        Returns:
            Contenu formate pour le fichier cible.
        """


def _generate_dns_name(
    device: NetworkDevice, domain: str
) -> str:
    """Genere un nom DNS pour un peripherique.

    Args:
        device: Peripherique.
        domain: Domaine local.

    Returns:
        Nom DNS complet (FQDN).
    """
    if device.hostname:
        label = _sanitize_dns_label(device.hostname)
    elif device.vendor:
        last_octet = device.ip.split(".")[-1]
        label = _sanitize_dns_label(device.vendor)
        label = f"{label}-{last_octet}"
    else:
        last_octet = device.ip.split(".")[-1]
        label = f"{device.device_type}-{last_octet}"
    return f"{label}.{domain}"


class LinuxHostsFileManager(_BaseDnsManager):
    """Gestionnaire DNS via le fichier /etc/hosts."""

    def generate_hosts_entries(
        self, devices: list[NetworkDevice]
    ) -> str:
        """Genere le contenu du fichier hosts.

        Args:
            devices: Liste des peripheriques.

        Returns:
            Contenu formate pour /etc/hosts.
        """
        domain = self._config.dns.domain
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        lines = [
            "# === Reseau local (genere par "
            "scanNetHome) ===",
            f"# Domaine : {domain}",
            f"# Genere le : {now}",
        ]
        for device in devices:
            if not device.dns_name:
                continue
            ip = device.fixed_ip or device.ip
            fqdn = device.dns_name
            alias = fqdn.split(".")[0] if "." in fqdn else ""
            if alias:
                lines.append(
                    f"{ip}    {fqdn} {alias}"
                )
            else:
                lines.append(f"{ip}    {fqdn}")
        return "\n".join(lines) + "\n"


class LinuxDnsmasqConfigGenerator(_BaseDnsManager):
    """Generateur de configuration DNS pour dnsmasq."""

    def generate_hosts_entries(
        self, devices: list[NetworkDevice]
    ) -> str:
        """Genere la configuration DNS dnsmasq.

        Args:
            devices: Liste des peripheriques.

        Returns:
            Configuration dnsmasq formatee.
        """
        domain = self._config.dns.domain
        lines = [
            "# Configuration DNS locale",
            f"# Domaine : {domain}",
        ]
        for device in devices:
            if not device.dns_name:
                continue
            ip = device.fixed_ip or device.ip
            lines.append(
                f"address=/{device.dns_name}/{ip}"
            )
        return "\n".join(lines) + "\n"

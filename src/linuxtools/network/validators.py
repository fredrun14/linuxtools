"""Fonctions de validation pour les donnees reseau.

Ce module fournit des validateurs pour les adresses IPv4,
les adresses MAC, les notations CIDR et les noms d'hote.
"""

import ipaddress
import re


def validate_ipv4(ip: str) -> str:
    """Valide et retourne une adresse IPv4.

    Args:
        ip: Adresse IPv4 sous forme de chaine.

    Returns:
        L'adresse IPv4 validee.

    Raises:
        ValueError: Si l'adresse est invalide.
    """
    try:
        ipaddress.IPv4Address(ip)
    except ValueError as exc:
        raise ValueError(f"Adresse IPv4 invalide : {ip!r}") from exc
    return ip


def validate_mac(mac: str) -> str:
    """Valide et normalise une adresse MAC.

    Args:
        mac: Adresse MAC sous forme de chaine.

    Returns:
        L'adresse MAC normalisee en minuscules.

    Raises:
        ValueError: Si l'adresse MAC est invalide.
    """
    pattern = r"^([0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}$"
    if not re.match(pattern, mac):
        raise ValueError(f"Adresse MAC invalide : {mac!r}")
    return mac.lower()


def validate_cidr(cidr: str) -> str:
    """Valide une notation CIDR.

    Args:
        cidr: Notation CIDR (ex: "192.168.1.0/24").

    Returns:
        La notation CIDR validee.

    Raises:
        ValueError: Si la notation est invalide.
    """
    pattern = r"^(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})/(\d{1,2})$"
    match = re.match(pattern, cidr)
    if not match:
        raise ValueError(f"Notation CIDR invalide : {cidr!r}")
    ip_part = match.group(1)
    mask = int(match.group(2))
    validate_ipv4(ip_part)
    if not 0 <= mask <= 32:
        raise ValueError(
            f"Masque CIDR hors plage (0-32) : {mask}"
        )
    return cidr


def validate_hostname(hostname: str) -> str:
    """Valide un nom d'hote selon la RFC 952.

    Args:
        hostname: Nom d'hote a valider.

    Returns:
        Le nom d'hote valide.

    Raises:
        ValueError: Si le nom d'hote est invalide.
    """
    if not hostname:
        raise ValueError("Le nom d'hote ne peut pas etre vide")
    if len(hostname) > 63:
        raise ValueError(
            f"Nom d'hote trop long ({len(hostname)} > 63) : "
            f"{hostname!r}"
        )
    pattern = r"^[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?$"
    if not re.match(pattern, hostname):
        raise ValueError(
            f"Nom d'hote invalide : {hostname!r}"
        )
    return hostname

"""Configuration de connexion au routeur ASUS RT-AX88U."""

import ipaddress
import socket
import urllib.parse
from dataclasses import dataclass

_LAN_NETWORKS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
]


def _validate_router_url(url: str) -> None:
    """Valide l'URL du routeur contre les risques SSRF.

    Verifie que le scheme est http ou https et que
    l'adresse IP (si fournie directement) appartient
    a un reseau prive LAN. Les noms de domaine sont
    resolus ; si toutes les IP resolues sont hors LAN,
    la valeur est rejetee.

    Args:
        url: URL du routeur a valider.

    Raises:
        ValueError: Si le scheme n'est pas http/https,
            si l'hostname est absent, ou si l'adresse
            IP n'appartient pas aux plages LAN privees
            autorisees.
    """
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(
            f"Scheme non autorise : {parsed.scheme!r} (http ou https requis)"
        )
    hostname = parsed.hostname or ""
    if not hostname:
        raise ValueError(f"URL sans hostname : {url!r}")
    try:
        addr = ipaddress.ip_address(hostname)
    except ValueError:
        # Hostname non-IP : résoudre et vérifier toutes les IP (anti-SSRF).
        # Si la résolution échoue (gaierror), on ne peut pas vérifier
        # (ex. mDNS en CI) → accepter avec prudence.
        try:
            infos = socket.getaddrinfo(hostname, None)
        except socket.gaierror:
            return
        for info in infos:
            raw_ip = info[4][0]
            try:
                resolved = ipaddress.ip_address(raw_ip)
            except ValueError:
                continue
            if not any(resolved in net for net in _LAN_NETWORKS):
                raise ValueError(
                    f"Hostname {hostname!r} résolu en adresse "
                    f"non-LAN : {raw_ip!r}."
                ) from None
        return
    if not any(addr in net for net in _LAN_NETWORKS):
        raise ValueError(
            f"Adresse non autorisee : {hostname!r}. "
            "Seules les adresses LAN privees "
            "(10/8, 172.16/12, 192.168/16) "
            "sont acceptees."
        )


class RouterAuthError(RuntimeError):
    """Erreur d'authentification au routeur ASUS."""


@dataclass(frozen=True)
class RouterConfig:
    """Configuration de connexion au routeur ASUS.

    Attributes:
        url: URL de base du routeur (http ou https).
        timeout: Timeout des requetes HTTP en secondes.
        username: Nom d'utilisateur admin du routeur.
        password: Mot de passe admin du routeur.
            La surcharge via les variables d'environnement
            ASUS_ROUTER_USER / ASUS_ROUTER_PASSWORD est
            appliquee par l'appelant (ex. CredentialChain),
            pas par RouterConfig elle-meme.
        verify_tls: Verifier le certificat TLS en HTTPS.
            False par defaut : les interfaces d'admin des
            routeurs grand public (ASUS/Merlin inclus)
            utilisent un certificat auto-signe, jamais
            renouvele par une CA publique. L'URL reste
            restreinte aux plages LAN privees par
            _validate_router_url(), ce qui limite le risque
            d'une verification desactivee a une usurpation
            deja possible sur le reseau local lui-meme.
    """

    url: str = "http://192.168.50.1"
    timeout: int = 30
    username: str = "admin"
    password: str = ""
    verify_tls: bool = False

    def __post_init__(self) -> None:
        """Valide la configuration.

        Raises:
            ValueError: Si url est invalide ou si
                timeout est inferieur ou egal a zero.
        """
        _validate_router_url(self.url)
        if self.timeout <= 0:
            raise ValueError(f"Timeout invalide : {self.timeout}")

"""Client HTTP et configuration pour le routeur ASUS RT-AX88U."""

import base64
import ipaddress
import json
import socket
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any

from linuxtools.logging.base import Logger
from linuxtools.network.router._nvram import (
    _NVRAM_KEY_RE,
)

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
            f"Scheme non autorise : {parsed.scheme!r}"
            " (http ou https requis)"
        )
    hostname = parsed.hostname or ""
    if not hostname:
        raise ValueError(
            f"URL sans hostname : {url!r}"
        )
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
    """

    url: str = "http://192.168.50.1"
    timeout: int = 30
    username: str = "admin"
    password: str = ""

    def __post_init__(self) -> None:
        """Valide la configuration.

        Raises:
            ValueError: Si url est invalide ou si
                timeout est inferieur ou egal a zero.
        """
        _validate_router_url(self.url)
        if self.timeout <= 0:
            raise ValueError(
                f"Timeout invalide : {self.timeout}"
            )


class AsusRouterClient:
    """Client HTTP pour l'API locale du routeur ASUS.

    Attributes:
        _config: Configuration de connexion.
        _logger: Logger optionnel.
        _token: Token de session asus_token.
    """

    _HEADERS: dict[str, str] = {
        "User-Agent": (
            "asusrouter-Android-DUTUtil-1.0.0.245"
        ),
        "Content-Type": (
            "application/x-www-form-urlencoded"
        ),
    }

    def __init__(
        self,
        config: RouterConfig,
        logger: Logger | None = None,
    ) -> None:
        """Initialise le client HTTP.

        Args:
            config: Configuration de connexion.
            logger: Logger optionnel.
        """
        self._config = config
        self._logger = logger
        self._token: str | None = None

    def login(
        self, username: str, password: str
    ) -> None:
        """Authentifie la session sur le routeur.

        Args:
            username: Nom d'utilisateur. Ne doit pas
                contenir ':' (format Basic Auth).
            password: Mot de passe.

        Raises:
            ValueError: Si username contient ':'.
            RouterAuthError: Si l'authentification
                echoue.
        """
        if ":" in username:
            raise ValueError(
                "Le nom d'utilisateur ne doit pas "
                "contenir ':'"
            )
        credentials = base64.b64encode(
            f"{username}:{password}".encode("ascii")
        ).decode("ascii")
        data = urllib.parse.urlencode(
            {"login_authorization": credentials}
        ).encode("ascii")
        req = urllib.request.Request(
            f"{self._config.url}/login.cgi",
            data=data,
            headers=self._HEADERS,
            method="POST",
        )
        try:
            with urllib.request.urlopen(
                req, timeout=self._config.timeout  # nosec B310
            ) as resp:
                body = json.loads(
                    resp.read().decode("utf-8")
                )
        except Exception as exc:
            if self._logger:
                self._logger.log_error(
                    f"Echec authentification routeur : {exc}"
                )
            raise RouterAuthError(
                f"Connexion echouee : {exc}"
            ) from exc
        token = body.get("asus_token")
        if not token:
            if self._logger:
                self._logger.log_error(
                    "Authentification routeur : "
                    "token absent de la reponse"
                )
            raise RouterAuthError(
                "Token absent de la reponse login"
            )
        self._token = token
        if self._logger:
            self._logger.log_info(
                "Authentification routeur reussie"
            )

    def logout(self) -> None:
        """Ferme la session sur le routeur."""
        if not self._token:
            return
        req = urllib.request.Request(
            f"{self._config.url}/Logout.asp",
            headers={
                **self._HEADERS,
                "Cookie": f"asus_token={self._token}",
            },
            method="GET",
        )
        try:
            urllib.request.urlopen(
                req, timeout=self._config.timeout  # nosec B310
            )
        except Exception:  # nosec B110
            pass
        finally:
            self._token = None

    def _require_token(self) -> str:
        """Retourne le token actif.

        Returns:
            Token de session.

        Raises:
            RouterAuthError: Si non authentifie.
        """
        if not self._token:
            raise RouterAuthError(
                "Non authentifie : appeler login() d'abord"
            )
        return self._token

    def _hook(self, hook: str) -> dict[str, Any]:
        """Envoie une requete hook vers /appGet.cgi.

        Args:
            hook: Expression hook ASUS.

        Returns:
            Reponse JSON parsee.

        Raises:
            RouterAuthError: Si non authentifie.
            RuntimeError: Si la requete echoue.
        """
        token = self._require_token()
        data = urllib.parse.urlencode(
            {"hook": hook}
        ).encode("ascii")
        req = urllib.request.Request(
            f"{self._config.url}/appGet.cgi",
            data=data,
            headers={
                **self._HEADERS,
                "Cookie": f"asus_token={token}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(
                req, timeout=self._config.timeout  # nosec B310
            ) as resp:
                result: dict[str, Any] = json.loads(
                    resp.read().decode("utf-8")
                )
                return result
        except Exception as exc:
            raise RuntimeError(
                f"Echec requete hook '{hook}' : {exc}"
            ) from exc

    def get_clients(self) -> list[dict[str, Any]]:
        """Retourne tous les clients connus du routeur.

        Inclut les appareils actuellement connectes
        (isOnline==1) et les appareils connus mais hors
        ligne (isOnline==0).

        Returns:
            Liste de dicts avec mac, ip, name, vendor,
            isOnline.
        """
        data = self._hook("get_clientlist(appobj)")
        clients_raw = data.get("get_clientlist", data)
        if not isinstance(clients_raw, dict):
            return []
        return [
            {"mac": mac, **info}
            for mac, info in clients_raw.items()
            if len(mac) == 17
            and isinstance(info, dict)
        ]

    def get_dhcp_leases(self) -> dict[str, str]:
        """Retourne les baux DHCP actifs sous forme mac→ip.

        Returns:
            Dictionnaire {mac_lowercase: ip}.
        """
        data = self._hook("dhcpLeaseMacList()")
        raw = data.get("dhcpLeaseMacList", "")
        leases: dict[str, str] = {}
        for line in str(raw).strip().split("\n"):
            parts = line.strip().split()
            # Format dnsmasq : timestamp mac ip hostname cid
            if len(parts) >= 3:
                mac = parts[1].lower()
                ip = parts[2]
                if len(mac) == 17 and ip != "*":
                    leases[mac] = ip
        return leases

    def get_nvram(self, *keys: str) -> dict[str, str]:
        """Lit des variables NVRAM du routeur.

        Args:
            *keys: Noms de variables NVRAM. Seuls les
                caracteres alphanumeriques et '_' sont
                acceptes (longueur 1-64).

        Returns:
            Dictionnaire {cle: valeur}.

        Raises:
            ValueError: Si une cle contient des
                caracteres non autorises.
        """
        for key in keys:
            if not _NVRAM_KEY_RE.match(key):
                raise ValueError(
                    f"Cle NVRAM invalide : {key!r}"
                )
        hook = ";".join(
            f"nvram_get({k})" for k in keys
        )
        return self._hook(hook)

    def set_static_reservations(
        self,
        static_list: str,
        hostnames: str,
        dhcp_cfg: dict[str, str],
    ) -> None:
        """Envoie les reservations DHCP statiques au routeur.

        Args:
            static_list: Format NVRAM <MAC>IP<MAC>IP...
            hostnames: Format NVRAM <MAC>hostname...
            dhcp_cfg: Valeurs DHCP actuelles du routeur.

        Raises:
            RouterAuthError: Si non authentifie.
            RuntimeError: Si l'envoi echoue.
        """
        token = self._require_token()
        payload = {
            "current_page": (
                "Advanced_DHCP_Content.asp"
            ),
            "next_page": "",
            "action_mode": "apply",
            "action_script": "restart_dnsmasq",
            "action_wait": "5",
            "dhcp_enable_x": dhcp_cfg.get(
                "dhcp_enable_x", "1"
            ),
            "dhcp_start": dhcp_cfg.get(
                "dhcp_start", ""
            ),
            "dhcp_end": dhcp_cfg.get("dhcp_end", ""),
            "dhcp_lease": dhcp_cfg.get(
                "dhcp_lease", "86400"
            ),
            "dhcp_static_x": "1",
            "dhcp_staticlist": static_list,
            "dhcp_hostnames": hostnames,
        }
        data = urllib.parse.urlencode(
            payload
        ).encode("ascii")
        req = urllib.request.Request(
            f"{self._config.url}/start_apply.htm",
            data=data,
            headers={
                **self._HEADERS,
                "Cookie": f"asus_token={token}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(
                req, timeout=self._config.timeout  # nosec B310
            ) as resp:
                status = resp.status
        except Exception as exc:
            raise RuntimeError(
                f"Echec envoi reservations DHCP : {exc}"
            ) from exc
        if status not in (200, 302):
            raise RuntimeError(
                f"Reponse inattendue : HTTP {status}"
            )
        if self._logger:
            self._logger.log_info(
                "Reservations DHCP appliquees sur le routeur"
            )

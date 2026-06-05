"""Client HTTP pour le routeur ASUS RT-AX88U.

Ce module fournit l'acces a l'API locale du routeur ASUS
pour scanner les clients connectes, lire les baux DHCP et
pousser les reservations statiques directement sur le routeur.

Les credentials (username/password) sont resolus par la
couche CLI avant d'etre passes via RouterConfig.
"""

import base64
import dataclasses
import ipaddress
import json
import re
import socket
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple

from linux_python_utils.logging.base import Logger
from linux_python_utils.network.base import (
    NetworkScanner,
    RouterDhcpManager,
)
from linux_python_utils.network.config import (
    DhcpRange,
    NetworkConfig,
)
from linux_python_utils.network.models import NetworkDevice


# ---------------------------------------------------------------------------
# Helpers prives (reutilises par AsusRouterDhcpManager)
# ---------------------------------------------------------------------------

def _ip_to_int(ip: str) -> int:
    """Convertit une adresse IPv4 en entier.

    Args:
        ip: Adresse IPv4 au format a.b.c.d.

    Returns:
        Representation entiere.

    Raises:
        ValueError: Si ip n'est pas une adresse IPv4
            valide.
    """
    try:
        addr = ipaddress.IPv4Address(ip)
    except ipaddress.AddressValueError as exc:
        raise ValueError(
            f"Adresse IPv4 invalide : {ip!r}"
        ) from exc
    return int(addr)


def _int_to_ip(num: int) -> str:
    """Convertit un entier en adresse IPv4.

    Args:
        num: Representation entiere.

    Returns:
        Adresse IPv4.
    """
    return (
        f"{(num >> 24) & 0xFF}."
        f"{(num >> 16) & 0xFF}."
        f"{(num >> 8) & 0xFF}."
        f"{num & 0xFF}"
    )


_VENDOR_TYPES: Tuple = (
    ("synology", "NAS"),
    ("nvidia", "Media Player"),
    ("nintendo", "Console"),
    ("apple", "Apple"),
    ("oneplus", "Smartphone"),
    ("samsung", "Smartphone"),
    ("huawei", "Smartphone"),
    ("xiaomi", "Smartphone"),
    ("asustek", "Routeur"),
    ("philips light", "Eclairage"),
    ("philips hue", "Eclairage"),
    ("hangzhou", "Camera/IoT"),
    ("hikvision", "Camera"),
    ("amazon", "Amazon"),
    ("raspberry", "Raspberry Pi"),
    ("sonos", "Audio"),
    ("espressif", "IoT"),
    ("intel", "PC/Laptop"),
    ("realtek", "PC/Laptop"),
)


_NVRAM_KEY_RE = re.compile(r'^[a-zA-Z0-9_]{1,64}$')


def _infer_type_from_vendor(vendor: str) -> str:
    """Infere le type d'appareil depuis le fabricant.

    Args:
        vendor: Nom du fabricant (OUI ou DPI).

    Returns:
        Type infere ou 'unknown'.
    """
    v = vendor.lower()
    for keyword, device_type in _VENDOR_TYPES:
        if keyword in v:
            return device_type
    return "unknown"


def _parse_custom_clientlist(
    raw: str,
) -> Dict[str, str]:
    """Parse la chaine NVRAM custom_clientlist.

    Extrait tous les appareils memorises par le routeur,
    y compris ceux hors ligne.

    Le firmware ASUS encode les < et > en entites HTML
    (&#60 et &#62). Ce decodage est applique avant le
    parsing.

    Format apres decodage : <nickName>MAC>type>...>
    Exemple : <Shield>48:B0:2D:03:1E:EA>5>

    Args:
        raw: Valeur NVRAM custom_clientlist (encodee HTML).

    Returns:
        Dict {mac_lowercase: nickname}.
    """
    # Le firmware encode < en &#60 et > en &#62 sans
    # point-virgule. html.unescape() est trop gourmand :
    # &#627C serait decode en ɳC au lieu de >7C.
    # On substitue directement les deux entites connues.
    decoded = raw.replace("&#60", "<").replace("&#62", ">")
    result: Dict[str, str] = {}
    pattern = re.compile(
        r"<([^>]*)>"
        r"([0-9A-Fa-f]{2}(?::[0-9A-Fa-f]{2}){5})"
        r">"
    )
    for match in pattern.finditer(decoded):
        nickname = match.group(1).strip()
        mac = match.group(2).lower()
        if nickname:
            result[mac] = nickname
    return result


def _parse_nvram_reservations(
    static_list: str,
    hostnames_str: str,
) -> Dict[str, Tuple[str, str]]:
    """Parse les chaines NVRAM en dict de reservations.

    Supporte les formats ancien et nouveau firmware :
    - Ancien : <MAC>IP<MAC>IP...
    - Nouveau (386+) : <MAC>IP>DNS>HOSTNAME<MAC>...

    Args:
        static_list: Chaine NVRAM dhcp_staticlist.
        hostnames_str: Chaine NVRAM dhcp_hostnames.

    Returns:
        Dict {mac_lowercase: (fixed_ip, dns_name)}.
    """
    hostnames: Dict[str, str] = {
        m.group(1).lower(): m.group(2).split(">")[0]
        for m in re.finditer(
            r"<([^>]+)>([^<]*)", hostnames_str
        )
    }
    result: Dict[str, Tuple[str, str]] = {}
    for match in re.finditer(
        r"<([^>]+)>([^<]*)", static_list
    ):
        mac = match.group(1).lower()
        # Format nouveau : IP>DNS>HOSTNAME — on prend le 1er champ
        fields = match.group(2).split(">")
        ip = fields[0].strip()
        # Le nom DNS peut etre dans le champ 4 (index 3)
        dns_from_nvram = (
            fields[3].strip()
            if len(fields) > 3
            else ""
        )
        if ip:
            result[mac] = (
                ip,
                dns_from_nvram or hostnames.get(mac, ""),
            )
    return result


def _next_available_ip(
    dhcp_range: DhcpRange, used_ips: Set[str]
) -> Optional[str]:
    """Trouve la prochaine IP libre dans la plage DHCP.

    Args:
        dhcp_range: Plage DHCP.
        used_ips: Ensemble des IP deja utilisees.

    Returns:
        Prochaine IP libre, ou None si plage epuisee.
    """
    start = _ip_to_int(dhcp_range.start)
    end = _ip_to_int(dhcp_range.end)
    for num in range(start, end + 1):
        ip = _int_to_ip(num)
        if ip not in used_ips:
            return ip
    return None


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
    acceptes sans resolution DNS.

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
                )
        return
    if not any(addr in net for net in _LAN_NETWORKS):
        raise ValueError(
            f"Adresse non autorisee : {hostname!r}. "
            "Seules les adresses LAN privees "
            "(10/8, 172.16/12, 192.168/16) "
            "sont acceptees."
        )


# ---------------------------------------------------------------------------
# Exceptions et configuration
# ---------------------------------------------------------------------------

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
            Les variables d'environnement ASUS_ROUTER_USER
            et ASUS_ROUTER_PASSWORD ont priorite sur ces
            valeurs si elles sont definies.
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


# ---------------------------------------------------------------------------
# Client HTTP bas niveau
# ---------------------------------------------------------------------------

class AsusRouterClient:
    """Client HTTP pour l'API locale du routeur ASUS.

    Attributes:
        _config: Configuration de connexion.
        _logger: Logger optionnel.
        _token: Token de session asus_token.
    """

    _HEADERS: Dict[str, str] = {
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
        logger: Optional[Logger] = None,
    ) -> None:
        """Initialise le client HTTP.

        Args:
            config: Configuration de connexion.
            logger: Logger optionnel.
        """
        self._config = config
        self._logger = logger
        self._token: Optional[str] = None

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

    def _hook(self, hook: str) -> dict:
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
                return json.loads(
                    resp.read().decode("utf-8")
                )
        except Exception as exc:
            raise RuntimeError(
                f"Echec requete hook '{hook}' : {exc}"
            ) from exc

    def get_clients(self) -> List[dict]:
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

    def get_dhcp_leases(self) -> Dict[str, str]:
        """Retourne les baux DHCP actifs sous forme mac→ip.

        Returns:
            Dictionnaire {mac_lowercase: ip}.
        """
        data = self._hook("dhcpLeaseMacList()")
        raw = data.get("dhcpLeaseMacList", "")
        leases: Dict[str, str] = {}
        for line in str(raw).strip().split("\n"):
            parts = line.strip().split()
            # Format dnsmasq : timestamp mac ip hostname cid
            if len(parts) >= 3:
                mac = parts[1].lower()
                ip = parts[2]
                if len(mac) == 17 and ip != "*":
                    leases[mac] = ip
        return leases

    def get_nvram(self, *keys: str) -> Dict[str, str]:
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
        dhcp_cfg: Dict[str, str],
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


# ---------------------------------------------------------------------------
# Scanner via API routeur
# ---------------------------------------------------------------------------

class AsusRouterScanner(NetworkScanner):
    """Scanner reseau via l'API locale du routeur ASUS.

    Ne necessite pas de privileges root.
    Les credentials sont passes via RouterConfig.

    Attributes:
        _router_config: Configuration routeur.
        _logger: Logger optionnel.
        _client: Client HTTP.
    """

    def __init__(
        self,
        router_config: RouterConfig,
        logger: Optional[Logger] = None,
        client: Optional[AsusRouterClient] = None,
    ) -> None:
        """Initialise le scanner routeur.

        Args:
            router_config: Configuration de connexion.
            logger: Logger optionnel.
            client: Client HTTP optionnel (injection).
        """
        self._router_config = router_config
        self._logger = logger
        self._client = client or AsusRouterClient(
            router_config, logger=logger
        )

    def scan(
        self, config: NetworkConfig
    ) -> List[NetworkDevice]:
        """Scanne le reseau via l'API du routeur.

        Args:
            config: Configuration reseau (parametre ABC,
                non utilise pour la requete HTTP).

        Returns:
            Liste des peripheriques connectes.

        Raises:
            RouterAuthError: Si l'authentification echoue.
            RuntimeError: Si la requete echoue.
        """
        self._client.login(
            self._router_config.username,
            self._router_config.password,
        )
        try:
            raw_clients = self._client.get_clients()
            leases = self._client.get_dhcp_leases()
            nvram = self._client.get_nvram(
                "dhcp_staticlist",
                "dhcp_hostnames",
                "custom_clientlist",
            )
            reservations = _parse_nvram_reservations(
                nvram.get("dhcp_staticlist", ""),
                nvram.get("dhcp_hostnames", ""),
            )
            custom_clients = _parse_custom_clientlist(
                nvram.get("custom_clientlist", "")
            )
            raw_clients = self._merge_offline_clients(
                raw_clients,
                custom_clients,
                leases,
                reservations,
            )
            devices = self._parse_clients(
                raw_clients, leases, reservations
            )
        finally:
            self._client.logout()
        if self._logger:
            self._logger.log_info(
                f"Routeur : {len(devices)} "
                f"peripherique(s) decouvert(s)"
            )
        return devices

    def _merge_offline_clients(
        self,
        raw_clients: List[dict],
        custom_clients: Dict[str, str],
        leases: Dict[str, str],
        reservations: Dict[str, Tuple[str, str]],
    ) -> List[dict]:
        """Ajoute les clients offline depuis custom_clientlist.

        Les clients deja presents dans raw_clients (online)
        sont conserves tels quels. Les clients memorises
        dans custom_clientlist mais absents de raw_clients
        sont ajoutes comme entrees offline si leur IP est
        connue (bail DHCP ou reservation statique).

        Args:
            raw_clients: Clients online retournes par
                get_clientlist.
            custom_clients: Dict {mac: nickname} depuis
                custom_clientlist NVRAM.
            leases: Dict {mac: ip} des baux DHCP actifs.
            reservations: Dict {mac: (fixed_ip, dns_name)}
                des reservations statiques.

        Returns:
            Liste etendue incluant les clients offline.
        """
        online_macs: set = {
            c.get("mac", "").lower()
            for c in raw_clients
        }
        result = list(raw_clients)
        for mac, nickname in custom_clients.items():
            if mac in online_macs:
                continue
            ip = leases.get(mac, "")
            if not ip:
                fixed, _ = reservations.get(
                    mac, (None, None)
                )
                ip = fixed or ""
            result.append(
                {
                    "mac": mac,
                    "ip": ip,
                    "isOnline": "0",
                    "nickName": nickname,
                    "vendor": "",
                    "dpiDevice": "",
                    "ipMethod": (
                        "Manual"
                        if mac in reservations
                        else ""
                    ),
                }
            )
        return result

    def _parse_clients(
        self,
        raw: List[dict],
        leases: Dict[str, str],
        reservations: Optional[
            Dict[str, Tuple[str, str]]
        ] = None,
    ) -> List[NetworkDevice]:
        """Parse les clients bruts en NetworkDevice.

        Utilise nickName > name pour le hostname,
        dpiDevice pour le type, et les reservations DHCP
        statiques pour fixed_ip et dns_name.

        Args:
            raw: Liste de dicts clients du routeur.
            leases: Dict {mac_lowercase: ip} des baux DHCP.
            reservations: Dict {mac: (fixed_ip, dns_name)}
                des reservations statiques du routeur.

        Returns:
            Liste de NetworkDevice valides.
        """
        if reservations is None:
            reservations = {}
        devices: List[NetworkDevice] = []
        for client in raw:
            mac = client.get("mac", "").lower()
            if len(mac) != 17:
                continue
            ip = client.get("ip", "")
            if not ip or ip == "0.0.0.0":  # nosec B104
                ip = leases.get(mac, "")
            if not ip:
                # Dernier recours : IP fixe de la
                # reservation statique (appareils offline
                # sans bail DHCP actif)
                fixed_ip_fallback, _ = reservations.get(
                    mac, (None, None)
                )
                ip = fixed_ip_fallback or ""
            # nickName = nom personnalise dans l'UI routeur
            # name = hostname DHCP envoye par l'appareil
            hostname = (
                client.get("nickName", "").strip()
                or client.get("name", "").strip()
            )
            vendor = client.get("vendor", "")
            # dpiDevice = type DPI du routeur, sinon vendor
            device_type = (
                client.get("dpiDevice", "").strip()
                or _infer_type_from_vendor(vendor)
            )
            fixed_ip, dns_name = reservations.get(
                mac, (None, None)
            )
            # ipMethod=="Manual" : IP fixee dans le routeur
            if not fixed_ip and (
                client.get("ipMethod", "") == "Manual"
            ):
                fixed_ip = ip
            try:
                devices.append(
                    NetworkDevice(
                        ip=ip,
                        mac=mac,
                        hostname=hostname,
                        vendor=vendor,
                        device_type=device_type,
                        fixed_ip=fixed_ip,
                        dns_name=dns_name,
                    )
                )
            except ValueError:
                continue
        return devices


# ---------------------------------------------------------------------------
# Gestionnaire DHCP avec push vers le routeur
# ---------------------------------------------------------------------------

class AsusRouterDhcpManager(RouterDhcpManager):
    """Gestionnaire DHCP avec push direct vers le routeur ASUS.

    Attributes:
        _config: Configuration reseau.
        _router_config: Configuration routeur.
        _logger: Logger optionnel.
        _client: Client HTTP.
    """

    def __init__(
        self,
        config: NetworkConfig,
        router_config: RouterConfig,
        logger: Optional[Logger] = None,
        client: Optional[AsusRouterClient] = None,
    ) -> None:
        """Initialise le gestionnaire DHCP routeur.

        Args:
            config: Configuration reseau.
            router_config: Configuration de connexion.
            logger: Logger optionnel.
            client: Client HTTP optionnel (injection).
        """
        self._config = config
        self._router_config = router_config
        self._logger = logger
        self._client = client or AsusRouterClient(
            router_config, logger=logger
        )

    def generate_reservations(
        self, devices: List[NetworkDevice]
    ) -> List[NetworkDevice]:
        """Alloue des IP fixes depuis la plage DHCP.

        Args:
            devices: Liste des peripheriques.

        Returns:
            Liste avec IP fixes assignees.

        Raises:
            ValueError: Si la plage DHCP manque ou est
                epuisee.
        """
        if self._config.dhcp_range is None:
            raise ValueError(
                "Plage DHCP non configuree"
            )
        used_ips: Set[str] = {
            d.fixed_ip
            for d in devices
            if d.fixed_ip is not None
        }
        result: List[NetworkDevice] = []
        for device in devices:
            if device.fixed_ip is not None:
                result.append(device)
                continue
            ip = _next_available_ip(
                self._config.dhcp_range, used_ips
            )
            if ip is None:
                raise ValueError(
                    "Plage DHCP epuisee"
                )
            used_ips.add(ip)
            result.append(
                dataclasses.replace(device, fixed_ip=ip)
            )
        if self._logger:
            self._logger.log_info(
                f"Reservations DHCP : {len(result)} "
                f"peripherique(s)"
            )
        return result

    def export_reservations(
        self, devices: List[NetworkDevice]
    ) -> str:
        """Exporte les reservations au format NVRAM ASUS.

        Format : <MAC>IP<MAC>IP...
        MAC en majuscules avec ':'.

        Args:
            devices: Liste des peripheriques.

        Returns:
            Chaine dhcp_staticlist.
        """
        parts = []
        for device in devices:
            if device.fixed_ip is None:
                continue
            mac = device.mac.upper()
            parts.append(f"<{mac}>{device.fixed_ip}")
        return "".join(parts)

    def apply_reservations(
        self, devices: List[NetworkDevice]
    ) -> None:
        """Envoie les reservations DHCP vers le routeur.

        Lit la configuration DHCP actuelle du routeur avant
        d'envoyer pour eviter d'ecraser les autres parametres.

        Args:
            devices: Peripheriques avec fixed_ip.

        Raises:
            RouterAuthError: Si l'authentification echoue.
            RuntimeError: Si l'envoi echoue.
        """
        self._client.login(
            self._router_config.username,
            self._router_config.password,
        )
        try:
            dhcp_cfg = self._client.get_nvram(
                "dhcp_enable_x",
                "dhcp_start",
                "dhcp_end",
                "dhcp_lease",
                "dhcp_static_x",
            )
            static_list, hostnames = (
                self._build_nvram_strings(devices)
            )
            self._client.set_static_reservations(
                static_list, hostnames, dhcp_cfg
            )
        finally:
            self._client.logout()
        if self._logger:
            count = sum(
                1
                for d in devices
                if d.fixed_ip is not None
            )
            self._logger.log_info(
                f"{count} reservation(s) DHCP "
                f"appliquee(s) sur le routeur"
            )

    def read_reservations(self) -> List[NetworkDevice]:
        """Lit les reservations DHCP existantes du routeur.

        Returns:
            Liste de NetworkDevice avec ip et mac.

        Raises:
            RouterAuthError: Si l'authentification echoue.
        """
        self._client.login(
            self._router_config.username,
            self._router_config.password,
        )
        try:
            nvram = self._client.get_nvram(
                "dhcp_staticlist",
                "dhcp_hostnames",
            )
        finally:
            self._client.logout()
        return self._parse_nvram_staticlist(
            nvram.get("dhcp_staticlist", ""),
            nvram.get("dhcp_hostnames", ""),
        )

    def _build_nvram_strings(
        self, devices: List[NetworkDevice]
    ) -> Tuple[str, str]:
        """Construit les chaines NVRAM dhcp_staticlist et
        dhcp_hostnames.

        Args:
            devices: Peripheriques avec fixed_ip.

        Returns:
            Tuple (static_list, hostnames).
        """
        static_parts: List[str] = []
        hostname_parts: List[str] = []
        for device in devices:
            if device.fixed_ip is None:
                continue
            mac = device.mac.upper()
            static_parts.append(
                f"<{mac}>{device.fixed_ip}"
            )
            name = device.hostname or device.dns_name
            if name:
                hostname_parts.append(f"<{mac}>{name}")
        return (
            "".join(static_parts),
            "".join(hostname_parts),
        )

    @staticmethod
    def _parse_nvram_staticlist(
        static_list: str,
        hostnames_str: str,
    ) -> List[NetworkDevice]:
        """Parse la chaine NVRAM dhcp_staticlist.

        Args:
            static_list: Chaine <MAC>IP<MAC>IP...
            hostnames_str: Chaine <MAC>hostname...

        Returns:
            Liste de NetworkDevice.
        """
        reservations = _parse_nvram_reservations(
            static_list, hostnames_str
        )
        devices: List[NetworkDevice] = []
        for mac, (ip, hostname) in reservations.items():
            try:
                devices.append(
                    NetworkDevice(
                        ip=ip,
                        mac=mac,
                        fixed_ip=ip,
                        hostname=hostname,
                    )
                )
            except ValueError:
                continue
        return devices

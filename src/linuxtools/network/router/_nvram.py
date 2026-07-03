"""Parseurs NVRAM pour le routeur ASUS."""

import re

_NVRAM_KEY_RE = re.compile(r'^[a-zA-Z0-9_]{1,64}$')


def _parse_custom_clientlist(
    raw: str,
) -> dict[str, str]:
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
    result: dict[str, str] = {}
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
) -> dict[str, tuple[str, str]]:
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
    hostnames: dict[str, str] = {
        m.group(1).lower(): m.group(2).split(">")[0]
        for m in re.finditer(
            r"<([^>]+)>([^<]*)", hostnames_str
        )
    }
    result: dict[str, tuple[str, str]] = {}
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

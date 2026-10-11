"""Clients LAN déclarés et chargeur générique.

Ce module fournit `LanClient` (client déclaré, distinct de
`NetworkDevice` qui est observé) et `load_lan_clients`, qui valide une
liste brute (par ex. issue d'un TOML) en enregistrements uniques.
"""

from collections.abc import Callable
from dataclasses import dataclass

from linuxtools.network.validators import validate_mac

# Clés admises d'une table [[client]] (schéma commun fermé).
_ALLOWED_KEYS: frozenset[str] = frozenset(
    {"mac", "name", "ip", "enabled", "note"}
)


@dataclass(frozen=True)
class LanClient:
    """Client LAN déclaré (intention), distinct de NetworkDevice (observé).

    Attributes:
        mac: Adresse MAC, validée et normalisée en majuscules.
        name: Nom optionnel (politique de validation injectée au loader).
        pinned_ip: IP épinglée optionnelle (idem).
        enabled: False = client conservé pour mémoire ; le chargeur ne
            filtre jamais, c'est à l'appelant de décider.
        note: Commentaire documentaire brut, non interprété.
    """

    mac: str
    name: str | None = None
    pinned_ip: str | None = None
    enabled: bool = True
    note: str | None = None

    def __post_init__(self) -> None:
        """Valide et normalise la MAC.

        name et pinned_ip ne sont pas validés ici : la politique est
        injectée au loader, le modèle reste générique.

        Raises:
            ValueError: Si la MAC est invalide.
        """
        object.__setattr__(self, "mac", validate_mac(self.mac, case="upper"))


def _resolve_optional(
    value: object,
    validator: Callable[[object], str | None] | None,
) -> str | None:
    """Détermine la valeur à stocker pour un champ optionnel.

    Args:
        value: Valeur brute lue dans la table (éventuellement None).
        validator: Validateur injecté, ou None pour la politique par défaut.

    Returns:
        La valeur retournée par le validateur ; sans validateur, la valeur
        si c'est une str, sinon None.
    """
    if validator is not None:
        return validator(value)
    return value if isinstance(value, str) else None


def _read_enabled(raw: dict[object, object]) -> bool:
    """Lit la clé ``enabled`` d'une table (booléen strict).

    Args:
        raw: Table brute du client.

    Returns:
        True si la clé est absente, sinon sa valeur booléenne.

    Raises:
        ValueError: Si la clé est présente mais n'est pas un bool.
    """
    if "enabled" not in raw:
        return True
    value = raw["enabled"]
    if not isinstance(value, bool):
        raise ValueError(f"enabled doit être un booléen : {value!r}")
    return value


def _read_note(raw: dict[object, object]) -> str | None:
    """Lit la clé ``note`` d'une table (chaîne brute).

    Args:
        raw: Table brute du client.

    Returns:
        None si la clé est absente, sinon la note telle quelle.

    Raises:
        ValueError: Si la clé est présente mais n'est pas une str.
    """
    if "note" not in raw:
        return None
    value = raw["note"]
    if not isinstance(value, str):
        raise ValueError(f"note doit être une chaîne : {value!r}")
    return value


def load_lan_clients(
    entries: object,
    *,
    name_validator: Callable[[object], str | None] | None = None,
    ip_validator: Callable[[object], str | None] | None = None,
    dedup_names: bool = False,
    require_non_empty: bool = False,
) -> tuple[LanClient, ...]:
    """Charge une liste brute de clients LAN en enregistrements uniques.

    Args:
        entries: Doit être une liste ; chaque entrée une table (dict) dont
            les clés admises (schéma fermé) sont ``mac`` (obligatoire),
            ``name``, ``ip`` (``ip`` alimente le champ ``pinned_ip``),
            ``enabled`` (bool strict, défaut True) et ``note`` (str,
            défaut None), tous optionnels.
        name_validator: Validateur de nom injecté, appelé avec la valeur
            brute (y compris None). Doit lever ValueError si invalide et
            retourner la valeur à stocker (str ou None). Sans lui : str
            prise telle quelle, sinon None.
        ip_validator: Idem pour l'IP épinglée.
        dedup_names: Si True, deux name identiques (hors None) lèvent
            ValueError.
        require_non_empty: Si True, une liste vide lève ValueError.

    Le chargeur ne filtre jamais ``enabled`` : les clients désactivés
    sont rendus et comptent pour le dédoublonnage MAC/nom et pour
    ``require_non_empty`` ; c'est à l'appelant de décider quoi en faire.

    Returns:
        Tuple immuable de LanClient, ordre d'entrée préservé.

    Raises:
        ValueError: Entrée non-liste ou non-table, clé inconnue, MAC
            absente, invalide ou en doublon ; nom/IP invalide (via
            validateurs) ; ``enabled`` non booléen ; ``note`` non str ;
            nom en doublon (dedup_names) ; liste vide
            (require_non_empty).
    """
    if not isinstance(entries, list):
        raise ValueError(f"client doit être une liste de tables : {entries!r}")
    if require_non_empty and not entries:
        raise ValueError("au moins un client requis")

    clients: list[LanClient] = []
    seen_macs: set[str] = set()
    seen_names: set[str] = set()
    for raw in entries:
        if not isinstance(raw, dict):
            raise ValueError(f"entrée de client invalide : {raw!r}")
        # Schéma fermé : une faute de frappe ne doit pas passer en silence.
        unknown = sorted(set(raw) - _ALLOWED_KEYS)
        if unknown:
            raise ValueError(
                f"clé(s) inconnue(s) {', '.join(repr(k) for k in unknown)}"
                f" — clés admises : {', '.join(sorted(_ALLOWED_KEYS))}"
            )
        mac = raw.get("mac")
        if not isinstance(mac, str):
            raise ValueError(f"MAC invalide : {mac!r}")
        # La MAC est validée avant les validateurs injectés (ordre des
        # erreurs historique) ; la normalisation finale reste assurée par
        # LanClient.__post_init__.
        mac = validate_mac(mac, case="upper")
        client = LanClient(
            mac=mac,
            name=_resolve_optional(raw.get("name"), name_validator),
            pinned_ip=_resolve_optional(raw.get("ip"), ip_validator),
            enabled=_read_enabled(raw),
            note=_read_note(raw),
        )
        # Unicité de la MAC (normalisée), toujours active.
        if client.mac in seen_macs:
            raise ValueError(f"MAC en doublon : {client.mac}")
        seen_macs.add(client.mac)
        # Unicité du nom (option), les noms None sont ignorés.
        if dedup_names and client.name is not None:
            if client.name in seen_names:
                raise ValueError(f"nom de client en doublon : {client.name}")
            seen_names.add(client.name)
        clients.append(client)
    return tuple(clients)

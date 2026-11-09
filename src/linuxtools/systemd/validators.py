"""Fonctions de validation pour les noms d'unités systemd."""

import re

# Nom d'unité systemd : lettres, chiffres, points, tirets, underscores, ':'
# et séquences d'échappement ``\xNN`` (``systemd-escape``, hex minuscule,
# ``\x00``-``\x1f`` et ``\x7f`` exclus : caractères de contrôle).
_UNIT_NAME_RE = re.compile(
    r"^[a-zA-Z0-9](?:[a-zA-Z0-9:._-]|\\x(?![01][0-9a-f]|7f)[0-9a-f]{2})*$"
)

# Nom de service : plus restrictif, pas de '.' ni ':'
_SERVICE_NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]*$")

# Extensions d'unités systemd autorisées
_EXTENSIONS_VALIDES = frozenset(
    {"service", "timer", "mount", "automount", "socket"}
)

# Extensions admises dans ``After=`` : les précédentes + ``target``
_EXTENSIONS_DEPENDANCE = _EXTENSIONS_VALIDES | {"target"}


def _validate_name(
    name: str,
    pattern: re.Pattern[str],
    entity: str,
) -> str:
    """Valide un nom selon un pattern et un label d'entité.

    Args:
        name: Nom à valider.
        pattern: Expression régulière de validation.
        entity: Label pour les messages d'erreur.

    Returns:
        Le nom validé.

    Raises:
        ValueError: Si le nom est invalide.
    """
    if not name:
        raise ValueError(f"Le nom {entity} ne peut pas être vide")
    if ".." in name or "/" in name:
        raise ValueError(
            f"Nom {entity} invalide (traversée interdite) : {name!r}"
        )
    if not pattern.fullmatch(name):
        raise ValueError(f"Nom {entity} invalide : {name!r}")
    return name


def reject_control_chars(value: str, champ: str) -> str:
    """Rejette les caractères de contrôle dans une valeur de champ unit.

    Protège contre l'injection de directives arbitraires dans les
    fichiers unit systemd via un saut de ligne ou tout caractère
    de contrôle ASCII (code < 32).

    Args:
        value: Valeur du champ à vérifier.
        champ: Nom du champ (pour le message d'erreur).

    Returns:
        La valeur inchangée si elle est valide.

    Raises:
        ValueError: Si value contient un caractère de contrôle.
    """
    if any(ord(c) < 32 for c in value):
        raise ValueError(
            f"Caractère de contrôle interdit dans le champ '{champ}'."
        )
    return value


def _validate_unit_with_extensions(
    unit_name: str, extensions: frozenset[str]
) -> str:
    """Valide un nom complet d'unité contre une liste d'extensions.

    Args:
        unit_name: Nom complet de l'unité (ex: ``backup.service``).
        extensions: Extensions autorisées.

    Returns:
        Le nom validé.

    Raises:
        ValueError: Si le nom est invalide ou l'extension non autorisée.
    """
    if "." not in unit_name:
        raise ValueError(f"Nom d'unité sans extension : {unit_name!r}")
    radical, ext = unit_name.rsplit(".", 1)
    if ext not in extensions:
        raise ValueError(f"Extension d'unité non autorisée : {ext!r}")
    validate_unit_name(radical)
    return unit_name


def validate_full_unit_name(unit_name: str) -> str:
    """Valide le nom complet d'une unité systemd (radical + extension).

    Vérifie que l'extension appartient à la liste blanche et délègue
    la validation du radical à validate_unit_name.

    Args:
        unit_name: Nom complet de l'unité (ex: ``mon-service.service``).

    Returns:
        Le nom validé.

    Raises:
        ValueError: Si le nom est invalide ou l'extension non autorisée.
    """
    return _validate_unit_with_extensions(unit_name, _EXTENSIONS_VALIDES)


def validate_dependency_unit_name(unit_name: str) -> str:
    """Valide le nom complet d'une unité citée dans ``After=``.

    Comme ``validate_full_unit_name`` mais accepte aussi l'extension
    ``target`` (ex. ``network-online.target``).

    Args:
        unit_name: Nom complet de l'unité (ex: ``network-online.target``).

    Returns:
        Le nom validé.

    Raises:
        ValueError: Si le nom est invalide ou l'extension non autorisée.
    """
    return _validate_unit_with_extensions(unit_name, _EXTENSIONS_DEPENDANCE)


def path_to_unit_name(mount_path: str) -> str:
    """Convertit un chemin de montage en nom d'unité systemd.

    Exemple: ``/media/nas/backup`` → ``media-nas-backup``.

    Args:
        mount_path: Chemin absolu du point de montage.

    Returns:
        Nom de l'unité validé (sans extension).

    Raises:
        ValueError: Si le chemin contient un backslash ou si le nom
            produit est invalide.
    """
    if "\\" in mount_path:
        raise ValueError(
            f"Chemin de montage invalide (backslash interdit) : {mount_path!r}"
        )
    name = mount_path.strip("/").replace("/", "-")
    return validate_unit_name(name)


def validate_unit_name(name: str) -> str:
    """Valide un nom d'unité systemd.

    Accepte les caractères : lettres, chiffres, points, tirets,
    underscores et deux-points, ainsi que les séquences d'échappement
    systemd ``\\xNN`` (``\\x`` suivi de deux chiffres hexadécimaux
    minuscules, ex. ``\\x2d``, produites par ``systemd-escape --path``),
    sauf ``\\x00``-``\\x1f`` et ``\\x7f`` (caractères de contrôle).
    Tout autre backslash est refusé. Le premier caractère doit être
    alphanumérique.

    Args:
        name: Nom d'unité à valider.

    Returns:
        Le nom validé.

    Raises:
        ValueError: Si le nom est invalide.
    """
    return _validate_name(name, _UNIT_NAME_RE, "d'unité")


def validate_service_name(name: str) -> str:
    """Valide un nom de service systemd.

    Plus restrictif que validate_unit_name : rejette les points
    et les deux-points, ainsi que les séquences dangereuses.

    Args:
        name: Nom de service à valider.

    Returns:
        Le nom validé.

    Raises:
        ValueError: Si le nom est invalide.
    """
    return _validate_name(name, _SERVICE_NAME_RE, "de service")

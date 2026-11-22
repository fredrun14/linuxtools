"""Catalogue des vaults : configuration TOML (XDG) validée, échec fermé."""

import errno
import os
import stat
import tomllib
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path
from typing import Any

from linuxtools.config.xdg import XdgAppConfig
from linuxtools.errors.exceptions import ConfigurationError
from linuxtools.logging.base import Logger
from linuxtools.vaults import _tables

# Seule exception à D4 (Q-15, conception § 9.2) : application et fichier XDG.
_APP_NAME = "vault-tools"
_CONFIG_FILENAME = "vaults.toml"
_EXAMPLE_FILENAME = "vaults.example.toml"

# Colonnes minimales du tableau des emplacements : chemin et libellé.
_MIN_COLUMNS = 2

_BAD_VALUE = "valeur absente, vide ou de mauvais type (chaîne non vide attendue)"


class VaultCatalogError(ConfigurationError):
    """Erreur de lecture du catalogue des vaults (configuration ou sources).

    Attributes:
        source: Fichier en cause (TOML, emplacements ou conventions).
        key: Clé TOML en cause, ou None si l'erreur ne porte pas sur une clé.
    """

    def __init__(self, detail: str, *, source: Path, key: str | None = None) -> None:
        """Construit l'erreur et son message nommant fichier et clé.

        Args:
            detail: Description du problème.
            source: Fichier en cause.
            key: Clé TOML en cause, le cas échéant.
        """
        self.source = source
        self.key = key
        if key:
            message = f"{source} — clé « {key} » : {detail}"
        else:
            message = f"{source} : {detail}"
        super().__init__(message)


@dataclass(frozen=True)
class _Settings:
    """Valeurs validées du fichier de configuration des vaults."""

    config_file: Path
    emplacements_file: Path
    conventions_file: Path
    section: str
    roles: dict[str, str]  # rôle → libellé, ordre du TOML
    table_header: str


class VaultCatalog:
    """Racines des vaults, lues dans les sources configurées.

    Seul endroit qui connaît le format du tableau des emplacements. Les chemins
    et libellés viennent du fichier de configuration XDG de ``vault-tools``.
    Construire avec ``load`` ; le constructeur est réservé à cette méthode.

    Example:
        >>> catalog = VaultCatalog.load()
        >>> catalog.roles
        ('perso', 'pro', 'foyer')
    """

    def __init__(
        self,
        *,
        settings: _Settings,
        locations: dict[str, str],
        logger: Logger | None = None,
    ) -> None:
        """Mémorise réglages et emplacements (libellé → chemin brut)."""
        self._settings = settings
        self._locations = locations
        self._logger = logger
        self._domaines_cache: dict[str, frozenset[str]] | None = None

    @classmethod
    def load(cls, *, logger: Logger | None = None) -> "VaultCatalog":
        """Charge la configuration puis le tableau des emplacements.

        Args:
            logger: Logger optionnel (chargement réussi journalisé en info).

        Returns:
            Le catalogue prêt à répondre.

        Raises:
            VaultCatalogError: Configuration invalide, fichier des emplacements
                absent ou illisible, section ou tableau absent ou mal formé,
                libellé en double, chemin mal formé.
        """
        config_file = _config_file()
        settings = _load_settings(config_file)
        locations = _read_locations(settings)
        if logger is not None:
            logger.log_info(
                f"Catalogue des vaults chargé : {config_file} "
                f"({len(locations)} rôles trouvés)"
            )
        return cls(settings=settings, locations=locations, logger=logger)

    @property
    def roles(self) -> tuple[str, ...]:
        """Rôles déclarés dans la configuration, dans leur ordre."""
        return tuple(self._settings.roles)

    def _check_role(self, role: str) -> None:
        """Vérifie que le rôle est déclaré dans la configuration.

        Args:
            role: Rôle demandé.

        Raises:
            VaultCatalogError: Rôle inconnu.
        """
        # Le rôle n'est qu'une clé de dictionnaire, jamais un fragment de chemin.
        if role not in self._settings.roles:
            raise VaultCatalogError(
                f"rôle « {role} » inconnu ; rôles possibles : {', '.join(self.roles)}",
                source=self._settings.config_file,
                key="emplacements.roles",
            )

    def root(self, role: str) -> Path:
        """Rend la racine résolue du vault d'un rôle.

        Args:
            role: Rôle demandé (ex. valeur de ``--role``).

        Returns:
            Chemin résolu d'un dossier existant.

        Raises:
            VaultCatalogError: Rôle inconnu, libellé absent du tableau, chemin
                relatif, ``~utilisateur`` inconnu, boucle de liens, octet NUL,
                dossier inexistant ou inaccessible (permission refusée).
        """
        settings = self._settings
        self._check_role(role)
        key = f"emplacements.roles.{role}"
        label = settings.roles[role]
        raw = self._locations.get(label)
        if raw is None:
            raise VaultCatalogError(
                f"libellé « {label} » du rôle « {role} » absent du tableau",
                source=settings.emplacements_file,
                key=key,
            )
        path = _expand(raw, source=settings.emplacements_file, key=key)
        if not path.is_absolute():
            raise VaultCatalogError(
                f"chemin relatif refusé pour « {role} » : {raw}",
                source=settings.emplacements_file,
                key=key,
            )
        resolved = _resolve(path, source=settings.emplacements_file, key=key)
        try:
            is_dir = stat.S_ISDIR(resolved.stat().st_mode)
        except (FileNotFoundError, NotADirectoryError):
            is_dir = False
        except OSError as exc:
            # EACCES sur un parent : ``Path.is_dir`` le masque dès Python 3.14,
            # ``stat`` le laisse passer sur toutes les versions.
            raise VaultCatalogError(
                f"dossier du rôle « {role} » inaccessible : {exc}",
                source=settings.emplacements_file,
                key=key,
            ) from exc
        if not is_dir:
            raise VaultCatalogError(
                f"dossier du rôle « {role} » introuvable : {resolved}",
                source=settings.emplacements_file,
                key=key,
            )
        return resolved

    def role_of(self, path: Path) -> str | None:
        """Rend le rôle dont la racine est exactement ``path``.

        Si plusieurs rôles pointent vers le même dossier résolu, le premier dans
        l'ordre de la configuration est rendu : ``load`` ne résout aucun chemin
        (les dossiers sont vérifiés à la demande, par ``root``), donc ne détecte
        pas ce cas.

        Args:
            path: Chemin à identifier (ex. valeur de ``--vault``).

        Returns:
            Le rôle si ``path`` résolu égale une racine résolue, sinon None
            (sous-dossier, chemin inconnu, ``path`` en boucle de liens ou à
            octet NUL). Un candidat du tableau dont le ``~utilisateur`` est
            inconnu ou suivi d'un octet NUL, qui est en boucle de liens ou à
            octet NUL est ignoré, comme un chemin relatif.

        Raises:
            VaultCatalogError: ``path`` lui-même a un ``~utilisateur`` inconnu
                ou un ``~`` suivi d'un octet NUL (l'erreur nomme ``path`` comme
                source, pas le TOML).
        """
        # Égalité stricte (Q-07), resolve() des deux côtés (F-03).
        source = self._settings.config_file
        expanded = _expand(str(path), source=path, key=None)
        try:
            target = _resolve(expanded, source=source, key=None)
        except VaultCatalogError:
            return None
        for role, label in self._settings.roles.items():
            raw = self._locations.get(label)
            if raw is None:
                continue
            try:
                candidate = _expand(raw, source=source, key=None)
                if candidate.is_absolute() and (
                    _resolve(candidate, source=source, key=None) == target
                ):
                    return role
            except VaultCatalogError:
                continue
        return None

    def domaines(self, role: str) -> frozenset[str]:
        """Rend les valeurs de ``domaine:`` autorisées pour un rôle.

        Le fichier de conventions est lu à la première demande, puis gardé en
        cache pour la vie du catalogue.

        Args:
            role: Rôle du vault audité.

        Returns:
            Les valeurs de la ligne du rôle dans le tableau des domaines.

        Raises:
            VaultCatalogError: Rôle inconnu, fichier de conventions absent ou
                illisible, tableau introuvable ou en double, rôle sans ligne,
                ligne en double ou cellule vide.
        """
        self._check_role(role)
        if self._domaines_cache is None:
            self._domaines_cache = _read_domaines(self._settings)
        if role not in self._domaines_cache:
            raise VaultCatalogError(
                f"aucune ligne pour le rôle « {role} »",
                source=self._settings.conventions_file,
                key="conventions.table_header",
            )
        return self._domaines_cache[role]


class _NotRegularFileError(OSError):
    """Le chemin existe mais n'est pas un fichier régulier."""

    def __init__(self) -> None:
        """Fixe le code ``EINVAL`` et le message."""
        super().__init__(errno.EINVAL, "pas un fichier régulier")


def _open_regular(path: Path) -> int:
    """Ouvre un fichier en lecture seule sans bloquer, s'il est régulier.

    Un ``os.stat`` préalable (qui suit les liens) refuse sans l'ouvrir un
    chemin existant non régulier ; le ``fstat`` sur le descripteur reste le
    contrôle qui fait foi (course entre les deux appels).

    Args:
        path: Fichier à ouvrir.

    Returns:
        Le descripteur ouvert (à fermer par l'appelant).

    Raises:
        FileNotFoundError: Chemin absent.
        _NotRegularFileError: Fichier non régulier (FIFO, périphérique,
            dossier) ; le descripteur éventuel est alors refermé.
        OSError: Ouverture impossible.
    """
    if not stat.S_ISREG(path.stat().st_mode):
        raise _NotRegularFileError
    # O_NONBLOCK : l'ouverture d'un FIFO ne doit pas bloquer ; le type est
    # contrôlé sur le descripteur avant toute lecture.
    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
    if not stat.S_ISREG(os.fstat(fd).st_mode):
        os.close(fd)
        raise _NotRegularFileError
    return fd


def _read_source(path: Path, settings: _Settings, key: str) -> str:
    """Lit un fichier source en UTF-8 (un BOM éventuel est ignoré).

    Args:
        path: Fichier à lire.
        settings: Réglages (pour nommer le TOML en cause).
        key: Clé du TOML désignant ce fichier.

    Returns:
        Le contenu du fichier.

    Raises:
        VaultCatalogError: Fichier absent, illisible, non UTF-8, à octet NUL dans
            son chemin, ou qui n'est pas un fichier régulier (FIFO, périphérique,
            dossier).
    """
    try:
        fd = _open_regular(path)
        with os.fdopen(fd, encoding="utf-8-sig") as handle:
            return handle.read()
    except FileNotFoundError as exc:
        raise VaultCatalogError(
            f"fichier introuvable : {path}",
            source=settings.config_file,
            key=key,
        ) from exc
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        raise VaultCatalogError(f"fichier illisible : {exc}", source=path) from exc


def _read_locations(settings: _Settings) -> dict[str, str]:
    """Extrait du tableau des emplacements le chemin de chaque libellé de rôle.

    Args:
        settings: Réglages validés.

    Returns:
        Libellé de rôle → chemin brut (backticks retirés). Les autres lignes du
        tableau sont ignorées.

    Raises:
        VaultCatalogError: Section ou tableau absent ou mal formé, libellé en
            double, cellule de chemin invalide.
    """
    source = settings.emplacements_file
    text = _read_source(source, settings, "sources.emplacements")
    try:
        lines = _tables.find_section(text, settings.section)
        if lines is None:
            raise VaultCatalogError(
                f"section « {settings.section} » introuvable",
                source=source,
                key="emplacements.section",
            )
        table = _tables.first_table(lines)
        if table is None:
            raise VaultCatalogError(
                "aucun tableau dans la section",
                source=source,
                key="emplacements.section",
            )
        if len(table.header) < _MIN_COLUMNS:
            raise VaultCatalogError("structure inattendue du tableau", source=source)
        wanted = set(settings.roles.values())
        locations: dict[str, str] = {}
        for row in table.rows:
            label = row[1]
            if label not in wanted:
                continue
            if label in locations:
                raise VaultCatalogError(
                    f"libellé « {label} » en double",
                    source=source,
                    key="emplacements.roles",
                )
            spans = _tables.code_spans(row[0])
            if len(spans) != 1:
                raise VaultCatalogError(
                    f"un seul chemin entre backticks attendu pour « {label} »",
                    source=source,
                )
            locations[label] = spans[0]
    except ValueError as exc:
        raise VaultCatalogError(str(exc), source=source) from exc
    return locations


def _read_domaines(settings: _Settings) -> dict[str, frozenset[str]]:
    """Extrait du fichier de conventions les valeurs de ``domaine:`` par ligne.

    Args:
        settings: Réglages validés.

    Returns:
        Nom de la ligne (rôle) → valeurs autorisées, toutes lignes comprises.

    Raises:
        VaultCatalogError: Fichier absent ou illisible, tableau introuvable ou en
            double, tableau à une seule colonne, ligne en double, cellule vide ou mal
            formée.
    """
    source = settings.conventions_file
    text = _read_source(source, settings, "sources.conventions")
    result: dict[str, frozenset[str]] = {}
    try:
        table = _tables.find_table_by_header(text, settings.table_header)
        if table is None:
            raise VaultCatalogError(
                f"tableau « {settings.table_header} » introuvable",
                source=source,
                key="conventions.table_header",
            )
        if len(table.header) < _MIN_COLUMNS:
            raise VaultCatalogError("structure inattendue du tableau", source=source)
        for row in table.rows:
            name = row[0]
            if name in result:
                raise VaultCatalogError(f"ligne « {name} » en double", source=source)
            values = _tables.code_spans(row[1])
            if not values:
                raise VaultCatalogError(
                    f"cellule de valeurs vide pour « {name} »", source=source
                )
            result[name] = frozenset(values)
    except ValueError as exc:
        raise VaultCatalogError(str(exc), source=source) from exc
    return result


def _expand(raw: str, *, source: Path, key: str | None) -> Path:
    """Expanse le ``~`` d'un chemin brut en traduisant l'échec en erreur du module.

    Args:
        raw: Chemin brut, éventuellement préfixé de ``~`` ou ``~utilisateur``.
        source: Fichier en cause (pour le message).
        key: Clé en cause, le cas échéant.

    Returns:
        Le chemin expansé (pas forcément absolu).

    Raises:
        VaultCatalogError: ``~utilisateur`` inconnu (``RuntimeError`` de pathlib)
            ou ``~`` suivi d'un octet NUL (``ValueError``).
    """
    try:
        return Path(raw).expanduser()
    except (RuntimeError, ValueError) as exc:
        raise VaultCatalogError(
            f"« ~ » inexpansible dans le chemin : {raw}", source=source, key=key
        ) from exc


def _resolve(path: Path, *, source: Path, key: str | None) -> Path:
    """Résout un chemin et détecte une boucle de liens, quelle que soit la version.

    Jusqu'à Python 3.12, ``resolve()`` lève ``RuntimeError`` sur une boucle de
    liens ; dès 3.13 il rend le chemin tel quel. Un ``stat`` du résultat lève
    alors ``ELOOP``, seul code traduit : un dossier absent (ou tout autre échec
    de ``stat``) n'est pas une boucle et reste accepté. Un octet NUL lève
    ``ValueError``.

    Args:
        path: Chemin à résoudre.
        source: Fichier en cause (pour le message).
        key: Clé en cause, le cas échéant.

    Returns:
        Le chemin résolu (pas forcément existant).

    Raises:
        VaultCatalogError: Boucle de liens, octet NUL ou chemin non résoluble.
    """
    try:
        resolved = path.resolve()
        try:
            resolved.stat()
        except OSError as exc:
            if exc.errno == errno.ELOOP:
                raise
    except (RuntimeError, OSError, ValueError) as exc:
        raise VaultCatalogError(
            f"chemin non résoluble (boucle de liens ou octet NUL ?) : {path}",
            source=source,
            key=key,
        ) from exc
    return resolved


def _config_file() -> Path:
    """Rend le chemin XDG attendu du fichier de configuration (non créé)."""
    # config_dir et non find_config_file : pas de cascade /etc (conception § 5).
    return XdgAppConfig(_APP_NAME).config_dir / _CONFIG_FILENAME


def _example_file() -> Path:
    """Rend le chemin installé du TOML d'exemple empaqueté."""
    return Path(str(files("linuxtools.vaults").joinpath(_EXAMPLE_FILENAME)))


def _lookup(data: dict[str, Any], dotted_key: str) -> object | None:
    """Descend une clé pointée ; rend None si une étape manque ou n'est pas une table.

    Args:
        data: Contenu du TOML.
        dotted_key: Clé pointée (ex. ``"sources.emplacements"``).

    Returns:
        La valeur trouvée, ou None.
    """
    current: object = data
    for part in dotted_key.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def _require_str(data: dict[str, Any], dotted_key: str, config_file: Path) -> str:
    """Rend une chaîne non vide du TOML.

    Args:
        data: Contenu du TOML.
        dotted_key: Clé pointée.
        config_file: Chemin du TOML (pour les messages).

    Returns:
        La chaîne.

    Raises:
        VaultCatalogError: Valeur absente, vide ou de mauvais type.
    """
    value = _lookup(data, dotted_key)
    if not isinstance(value, str) or not value.strip():
        raise VaultCatalogError(_BAD_VALUE, source=config_file, key=dotted_key)
    return value


def _require_path(data: dict[str, Any], dotted_key: str, config_file: Path) -> Path:
    """Rend un chemin absolu (``~`` expansé) du TOML, sans vérifier son existence.

    Args:
        data: Contenu du TOML.
        dotted_key: Clé pointée.
        config_file: Chemin du TOML (pour les messages).

    Returns:
        Le chemin absolu.

    Raises:
        VaultCatalogError: Valeur invalide ou chemin relatif.
    """
    path = _expand(
        _require_str(data, dotted_key, config_file), source=config_file, key=dotted_key
    )
    if not path.is_absolute():
        raise VaultCatalogError(
            f"chemin relatif refusé : {path}", source=config_file, key=dotted_key
        )
    return path


def _require_roles(data: dict[str, Any], config_file: Path) -> dict[str, str]:
    """Rend la table rôle → libellé, validée.

    Args:
        data: Contenu du TOML.
        config_file: Chemin du TOML (pour les messages).

    Returns:
        Les rôles, dans l'ordre du TOML.

    Raises:
        VaultCatalogError: Table absente, vide, entrée invalide, libellé à espaces de
        bord ou libellé en double.
    """
    key = "emplacements.roles"
    raw = _lookup(data, key)
    if not isinstance(raw, dict) or not raw:
        raise VaultCatalogError(
            "table non vide attendue (rôle → libellé)", source=config_file, key=key
        )
    roles: dict[str, str] = {}
    for role, label in raw.items():
        if not role.strip():
            raise VaultCatalogError("nom de rôle vide", source=config_file, key=key)
        if not isinstance(label, str) or not label.strip():
            raise VaultCatalogError(_BAD_VALUE, source=config_file, key=f"{key}.{role}")
        if label != label.strip():
            # Les cellules du tableau sont débarrassées de leurs espaces de bord :
            # un tel libellé ne serait jamais trouvé.
            raise VaultCatalogError(
                "libellé à espaces de bord, jamais trouvé dans le tableau",
                source=config_file,
                key=f"{key}.{role}",
            )
        roles[role] = label
    if len(set(roles.values())) != len(roles):
        raise VaultCatalogError("libellé en double", source=config_file, key=key)
    return roles


def _load_settings(config_file: Path) -> _Settings:
    """Lit et valide toutes les clés du fichier de configuration.

    Args:
        config_file: Chemin du TOML.

    Returns:
        Les réglages validés, chemins sources expansés et absolus.

    Raises:
        VaultCatalogError: TOML absent, pas un fichier régulier (dossier, FIFO,
            périphérique), inaccessible, illisible, invalide (y compris trop
            imbriqué), ou clé absente, vide, de mauvais type, ou chemin relatif.
    """
    try:
        fd = _open_regular(config_file)
        with os.fdopen(fd, "rb") as handle:
            data = tomllib.load(handle)
    except FileNotFoundError as exc:
        raise VaultCatalogError(
            "fichier de configuration introuvable ; copier l'exemple "
            f"{_example_file()} à cet emplacement",
            source=config_file,
        ) from exc
    except _NotRegularFileError as exc:
        raise VaultCatalogError(
            "fichier de configuration n'est pas un fichier régulier",
            source=config_file,
        ) from exc
    except (tomllib.TOMLDecodeError, RecursionError) as exc:
        raise VaultCatalogError(f"TOML invalide : {exc}", source=config_file) from exc
    except (OSError, UnicodeDecodeError) as exc:
        raise VaultCatalogError(
            f"fichier illisible : {exc}", source=config_file
        ) from exc
    return _Settings(
        config_file,
        _require_path(data, "sources.emplacements", config_file),
        _require_path(data, "sources.conventions", config_file),
        _require_str(data, "emplacements.section", config_file),
        _require_roles(data, config_file),
        _require_str(data, "conventions.table_header", config_file),
    )

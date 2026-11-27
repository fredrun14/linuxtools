"""Gestionnaire `systemd --user` simulé par le système de fichiers de test.

Reproduit ce que `systemctl --user show` rend pour les propriétés que
l'installeur lit : `UnitPath` (liste ordonnée des dossiers de recherche),
`LoadState`, `FragmentPath` (fichier d'unité trouvé) et `DropInPaths` (drop-ins
`*.conf` des dossiers `<unité>.d` de ces mêmes dossiers). Un fichier écrit hors de
`UnitPath` n'est donc jamais « chargé », comme sur un vrai poste.

Comme systemd, une unité sans fragment (ni fournie par le système) est
`not-found` et ses drop-ins ne sont pas rendus ; une unité masquée est `masked`.
"""

from collections.abc import Collection, Sequence
from pathlib import Path
from unittest.mock import MagicMock

from linuxtools.systemd.executor import UserSystemdExecutor

# Unités surveillées des tests, supposées fournies par le système (hors `UnitPath`
# de test) : sans fragment dans les dossiers simulés, elles restent « loaded ».
VENDOR_UNITS = frozenset(
    {
        "backup.service",
        "demo.service",
        "dnf5-automatic.service",
        "flatpak-automatic.service",
    }
)


def wire_user_manager(
    manager: MagicMock,
    home: Path,
    unit_path: Sequence[str] | None = None,
    *,
    vendor_units: Collection[str] = VENDOR_UNITS,
    masked: Collection[str] = (),
) -> MagicMock:
    """Branche `show_property` de `manager` sur un `UnitPath` et le disque.

    Args:
        manager: Exécuteur `MagicMock(spec=UserSystemdExecutor)` à configurer.
        home: Dossier personnel de test (défaut de `UnitPath`).
        unit_path: Dossiers de recherche ; par défaut `<home>/.config/systemd/user`.
        vendor_units: Unités fournies par le système (`loaded` sans fragment simulé).
        masked: Unités masquées (`LoadState=masked`).

    Returns:
        `manager`, pour chaîner.
    """
    dirs = [str(home / ".config/systemd/user")] if unit_path is None else unit_path

    def fragments(unit_name: str) -> list[Path]:
        return [Path(d) / unit_name for d in dirs if (Path(d) / unit_name).is_file()]

    def load_state(unit_name: str) -> str:
        if unit_name in masked:
            return "masked"
        found = bool(fragments(unit_name)) or unit_name in vendor_units
        return "loaded" if found else "not-found"

    def show_property(property_name: str, unit_name: str | None = None) -> str:
        if property_name == "UnitPath":
            return " ".join(dirs)
        assert unit_name is not None
        if property_name == "LoadState":
            return load_state(unit_name)
        if property_name == "FragmentPath":
            found = fragments(unit_name)
            return str(found[0]) if found else ""
        assert property_name == "DropInPaths"
        if load_state(unit_name) != "loaded":
            return ""
        confs = sorted(
            conf for d in dirs for conf in (Path(d) / f"{unit_name}.d").glob("*.conf")
        )
        return " ".join(str(conf) for conf in confs)

    manager.show_property.side_effect = show_property
    return manager


def user_manager(
    home: Path,
    unit_path: Sequence[str] | None = None,
    *,
    vendor_units: Collection[str] = VENDOR_UNITS,
    masked: Collection[str] = (),
) -> MagicMock:
    """`UserSystemdExecutor` simulé : unité inactive, reload réussi, XDG vide."""
    manager = MagicMock(spec=UserSystemdExecutor)
    manager.get_status.return_value = "inactive"
    manager.reload_systemd.return_value = True
    manager.show_environment.return_value = {}
    return wire_user_manager(
        manager, home, unit_path, vendor_units=vendor_units, masked=masked
    )

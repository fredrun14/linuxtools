"""Gestionnaire `systemd --user` simulé par le système de fichiers de test.

Reproduit ce que `systemctl --user show` rend pour les trois propriétés que
l'installeur lit : `UnitPath` (liste ordonnée des dossiers de recherche),
`FragmentPath` (fichier d'unité trouvé) et `DropInPaths` (drop-ins `*.conf` des
dossiers `<unité>.d` de ces mêmes dossiers). Un fichier écrit hors de `UnitPath`
n'est donc jamais « chargé », comme sur un vrai poste.
"""

from collections.abc import Sequence
from pathlib import Path
from unittest.mock import MagicMock

from linuxtools.systemd.executor import UserSystemdExecutor


def wire_user_manager(
    manager: MagicMock,
    home: Path,
    unit_path: Sequence[str] | None = None,
) -> MagicMock:
    """Branche `show_property` de `manager` sur un `UnitPath` et le disque.

    Args:
        manager: Exécuteur `MagicMock(spec=UserSystemdExecutor)` à configurer.
        home: Dossier personnel de test (défaut de `UnitPath`).
        unit_path: Dossiers de recherche ; par défaut `<home>/.config/systemd/user`.

    Returns:
        `manager`, pour chaîner.
    """
    dirs = [str(home / ".config/systemd/user")] if unit_path is None else unit_path

    def show_property(property_name: str, unit_name: str | None = None) -> str:
        if property_name == "UnitPath":
            return " ".join(dirs)
        assert unit_name is not None
        if property_name == "FragmentPath":
            found = [
                Path(d) / unit_name for d in dirs if (Path(d) / unit_name).is_file()
            ]
            return str(found[0]) if found else ""
        assert property_name == "DropInPaths"
        confs = sorted(
            conf for d in dirs for conf in (Path(d) / f"{unit_name}.d").glob("*.conf")
        )
        return " ".join(str(conf) for conf in confs)

    manager.show_property.side_effect = show_property
    return manager


def user_manager(home: Path, unit_path: Sequence[str] | None = None) -> MagicMock:
    """`UserSystemdExecutor` simulé : unité inactive, reload réussi, XDG vide."""
    manager = MagicMock(spec=UserSystemdExecutor)
    manager.get_status.return_value = "inactive"
    manager.reload_systemd.return_value = True
    manager.show_environment.return_value = {}
    return wire_user_manager(manager, home, unit_path)

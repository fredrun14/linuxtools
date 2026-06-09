"""Résolution des chemins FHS pour le déploiement de scripts CLI.

Ce module fournit ScriptPaths pour calculer les chemins d'installation
system (/usr/local/share/) ou user (~/.local/share/) en utilisant
platformdirs, conformément au standard FHS Linux.

Typical usage example:

    paths = ScriptPaths("mon-app", "user")
    print(paths.data_dir)   # ~/.local/share/mon-app
    print(paths.bin_path)   # ~/.local/bin/mon-app
    print(paths.venv_dir)   # ~/.local/share/mon-app/venv
"""

from pathlib import Path
from typing import Literal

from platformdirs import site_data_dir, user_data_dir


class ScriptPaths:
    """Résout les chemins FHS pour un script CLI system ou user.

    Calcule les chemins d'installation selon le standard FHS en
    utilisant platformdirs pour la conformité Linux.

    | Type   | data_dir                   | bin_path              |
    |--------|----------------------------|-----------------------|
    | system | /usr/local/share/{name}/   | /usr/local/bin/{name} |
    | user   | ~/.local/share/{name}/     | ~/.local/bin/{name}   |

    Attributes:
        name: Nom de l'application.
        deploy_type: Portée du déploiement ('system' ou 'user').

    Example:
        >>> paths = ScriptPaths("mon-app", "user")
        >>> paths.bin_path.name
        'mon-app'
    """

    def __init__(
        self,
        name: str,
        deploy_type: Literal["system", "user"],
    ) -> None:
        """Initialise avec le nom de l'application et la portée.

        Args:
            name: Nom de l'application.
            deploy_type: 'system' ou 'user'.
        """
        self._name = name
        self._deploy_type = deploy_type

    @property
    def data_dir(self) -> Path:
        """Répertoire de données principal de l'application.

        Returns:
            /usr/local/share/{name} pour system,
            ~/.local/share/{name} pour user.
        """
        if self._deploy_type == "system":
            return Path(site_data_dir(self._name))
        return Path(user_data_dir(self._name))

    @property
    def bin_path(self) -> Path:
        """Chemin du binaire ou wrapper dans le PATH.

        Returns:
            /usr/local/bin/{name} pour system,
            ~/.local/bin/{name} pour user.
        """
        if self._deploy_type == "system":
            return Path("/usr/local/bin") / self._name
        return Path.home() / ".local" / "bin" / self._name

    @property
    def venv_dir(self) -> Path:
        """Répertoire du venv dans data_dir.

        Returns:
            {data_dir}/venv/
        """
        return self.data_dir / "venv"

    @property
    def wrapper_path(self) -> Path:
        """Alias de bin_path pour la clarté sémantique.

        Returns:
            Chemin du wrapper bash (identique à bin_path).
        """
        return self.bin_path

    @property
    def config_dir(self) -> Path:
        """Répertoire de configuration de l'application.

        Returns:
            /etc/{name}/ pour system,
            ~/.config/{name}/ pour user.
        """
        if self._deploy_type == "system":
            return Path("/etc") / self._name
        return Path.home() / ".config" / self._name

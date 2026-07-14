"""Chargeur de configuration pour les unités .mount systemd.

Ce module fournit une classe pour charger un fichier de configuration
(TOML ou JSON) et créer un MountConfig pour les unités systemd .mount.

Example:
    Chargement d'un MountConfig depuis un fichier TOML:

        loader = MountConfigLoader("config/mounts.toml")
        mount_config = loader.load()

    Chargement depuis un fichier JSON:

        loader = MountConfigLoader("config/mounts.json")
        mount_config = loader.load()

    Fichier de configuration attendu:

        [mount]
        description = "Partage NAS"
        what = "192.168.1.10:/share"
        where = "/media/nas"
        type = "nfs"
        options = "rw,soft"
"""

from typing import Any, NamedTuple

from linuxtools.config import ConfigFileLoader
from linuxtools.systemd import MountConfig


class AutomountSettings(NamedTuple):
    """Résultat de MountConfigLoader.load_with_automount().

    Attributes:
        config: Configuration du montage.
        with_automount: True si une unité .automount doit être créée.
        timeout_sec: Délai d'inactivité avant démontage (secondes).
    """

    config: MountConfig
    with_automount: bool
    timeout_sec: int


class MountConfigLoader(ConfigFileLoader[MountConfig]):
    """Chargeur de configuration pour MountConfig.

    Cette classe lit un fichier de configuration (TOML ou JSON) et crée
    un MountConfig à partir de la section [mount].

    Attributes:
        DEFAULT_SECTION: Nom de la section par défaut ("mount").

    Example:
        >>> loader = MountConfigLoader("config/nas.toml")
        >>> config = loader.load()
        >>> print(config.where)
        /media/nas
    """

    DEFAULT_SECTION: str = "mount"

    def load(self, section: str | None = None) -> MountConfig:
        """Charge et retourne un MountConfig.

        Args:
            section: Nom de la section à charger.
                Par défaut "mount".

        Returns:
            Instance de MountConfig avec les valeurs du fichier.

        Raises:
            KeyError: Si la section n'existe pas.
            TypeError: Si les champs requis sont manquants.
            ValueError: Si 'what' ou 'where' sont vides.

        Example:
            >>> loader = MountConfigLoader("config/nas.toml")
            >>> config = loader.load()
            >>> config.type
            'nfs'
        """
        section_name = section or self.DEFAULT_SECTION
        data: dict[str, Any] = self._get_section(section_name)

        return MountConfig(
            description=data["description"],
            what=data["what"],
            where=data["where"],
            type=data["type"],
            options=data.get("options", ""),
        )

    def load_with_automount(
        self,
        section: str | None = None
    ) -> AutomountSettings:
        """Charge un MountConfig et les réglages automount associés.

        Lit les champs optionnels 'with_automount' (bool) et
        'automount_timeout_sec' (int) dans la même section que le
        MountConfig, en plus des champs déjà gérés par load().

        Args:
            section: Nom de la section à charger. Par défaut "mount".

        Returns:
            AutomountSettings (config, with_automount, timeout_sec).

        Raises:
            KeyError: Si la section n'existe pas.
            TypeError: Si les champs requis du MountConfig sont manquants.

        Example:
            >>> loader = MountConfigLoader("config/nas.toml")
            >>> settings = loader.load_with_automount()
            >>> settings.with_automount
            True
        """
        section_name = section or self.DEFAULT_SECTION
        mount_config = self.load(section_name)
        data: dict[str, Any] = self._get_section(section_name)

        return AutomountSettings(
            config=mount_config,
            with_automount=bool(data.get("with_automount", False)),
            timeout_sec=int(data.get("automount_timeout_sec", 0)),
        )

    def load_multiple(self, section: str | None = None) -> list[MountConfig]:
        """Charge plusieurs MountConfig depuis une section de liste.

        Permet de définir plusieurs montages dans un seul fichier
        de configuration sous forme de liste.

        Args:
            section: Nom de la section contenant la liste.
                Par défaut "mounts" (pluriel).

        Returns:
            Liste d'instances de MountConfig.

        Raises:
            KeyError: Si la section n'existe pas.
            TypeError: Si la section n'est pas une liste.

        Example:
            Fichier TOML:

                [[mounts]]
                description = "NAS principal"
                what = "192.168.1.10:/share"
                where = "/media/nas"
                type = "nfs"

                [[mounts]]
                description = "NAS backup"
                what = "192.168.1.11:/backup"
                where = "/media/backup"
                type = "nfs"

            >>> loader = MountConfigLoader("config/mounts.toml")
            >>> configs = loader.load_multiple("mounts")
            >>> len(configs)
            2
        """
        section_name = section or "mounts"
        data = self._get_section(section_name)

        if not isinstance(data, list):
            raise TypeError(
                f"La section '{section_name}' doit être une liste "
                f"(utilisez [[{section_name}]] dans le TOML)"
            )

        return [
            MountConfig(
                description=item["description"],
                what=item["what"],
                where=item["where"],
                type=item["type"],
                options=item.get("options", ""),
            )
            for item in data
        ]

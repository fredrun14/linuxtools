"""Chargeur de configuration pour les unités .service systemd.

Ce module fournit une classe pour charger un fichier de configuration
(TOML ou JSON) et créer un ServiceConfig pour les unités systemd .service.

Example:
    Chargement d'un ServiceConfig depuis un fichier TOML:

        loader = ServiceConfigLoader("config/app.toml")
        service_config = loader.load()

    Chargement depuis un fichier JSON:

        loader = ServiceConfigLoader("config/app.json")
        service_config = loader.load()

    Fichier de configuration attendu:

        [service]
        description = "Mon service"
        exec_start = "/usr/bin/mon-app"
        type = "simple"
"""

from typing import Any

from linux_python_utils.config import ConfigFileLoader
from linux_python_utils.systemd import ServiceConfig


class ServiceConfigLoader(ConfigFileLoader[ServiceConfig]):
    """Chargeur de configuration pour ServiceConfig.

    Cette classe lit un fichier de configuration (TOML ou JSON) et crée
    un ServiceConfig à partir de la section [service].

    Attributes:
        DEFAULT_SECTION: Nom de la section par défaut ("service").

    Example:
        >>> loader = ServiceConfigLoader("config/flatpak.toml")
        >>> config = loader.load()
        >>> print(config.description)
        Flatpak Update Service
    """

    DEFAULT_SECTION: str = "service"

    def load(self, section: str | None = None) -> ServiceConfig:
        """Charge et retourne un ServiceConfig.

        Args:
            section: Nom de la section à charger.
                Par défaut "service".

        Returns:
            Instance de ServiceConfig avec les valeurs du fichier.

        Raises:
            KeyError: Si la section n'existe pas.
            TypeError: Si les champs requis sont manquants.

        Example:
            >>> loader = ServiceConfigLoader("config/app.toml")
            >>> config = loader.load()
            >>> config.type
            'oneshot'
        """
        section_name = section or self.DEFAULT_SECTION
        data: dict[str, Any] = self._get_section(section_name)

        return ServiceConfig(
            description=data["description"],
            exec_start=data["exec_start"],
            type=data.get("type", "simple"),
            user=data.get("user", ""),
            group=data.get("group", ""),
            working_directory=data.get("working_directory", ""),
            environment=data.get("environment", {}),
            restart=data.get("restart", "no"),
            restart_sec=data.get("restart_sec", 0),
            wanted_by=data.get("wanted_by", "multi-user.target"),
        )

    def load_with_exec_override(
        self,
        exec_start: str,
        section: str | None = None
    ) -> ServiceConfig:
        """Charge un ServiceConfig avec un exec_start personnalisé.

        Utile quand exec_start doit pointer vers un script généré
        dynamiquement plutôt que la valeur du fichier de configuration.

        Args:
            exec_start: Commande à utiliser à la place de celle du fichier.
            section: Nom de la section à charger.

        Returns:
            Instance de ServiceConfig avec exec_start personnalisé.

        Example:
            >>> loader = ServiceConfigLoader("config/app.toml")
            >>> config = loader.load_with_exec_override("/usr/local/bin/s.sh")
            >>> config.exec_start
            '/usr/local/bin/s.sh'
        """
        section_name = section or self.DEFAULT_SECTION
        data: dict[str, Any] = self._get_section(section_name)

        return ServiceConfig(
            description=data["description"],
            exec_start=exec_start,
            type=data.get("type", "simple"),
            user=data.get("user", ""),
            group=data.get("group", ""),
            working_directory=data.get("working_directory", ""),
            environment=data.get("environment", {}),
            restart=data.get("restart", "no"),
            restart_sec=data.get("restart_sec", 0),
            wanted_by=data.get("wanted_by", "multi-user.target"),
        )

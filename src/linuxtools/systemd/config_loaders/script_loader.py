"""Chargeur de configuration pour les scripts bash.

Ce module fournit une classe pour charger un fichier de configuration
(TOML ou JSON) et créer un BashScriptConfig avec support optionnel
des notifications.

Example:
    Chargement d'un BashScriptConfig depuis un fichier TOML:

        loader = BashScriptConfigLoader("config/app.toml")
        script_config = loader.load()

    Chargement depuis un fichier JSON:

        loader = BashScriptConfigLoader("config/app.json")
        script_config = loader.load()

    Fichier de configuration attendu:

        [service]
        exec_command = "/usr/bin/flatpak update -y"

        [notification]
        enabled = true
        title = "Flatpak Update"
        message_success = "Mise à jour réussie."
        message_failure = "Échec de la mise à jour."
"""

from typing import Any

from linuxtools.config import ConfigFileLoader
from linuxtools.notification import NotificationConfig
from linuxtools.scripts import BashScriptConfig


class BashScriptConfigLoader(ConfigFileLoader[BashScriptConfig]):
    """Chargeur de configuration pour BashScriptConfig.

    Cette classe lit un fichier de configuration (TOML ou JSON) et crée
    un BashScriptConfig à partir des sections [service] et optionnellement
    [notification].

    Attributes:
        DEFAULT_SECTION: Section par défaut pour exec_command ("service").
        NOTIFICATION_SECTION: Section pour les notifications ("notification").

    Example:
        >>> loader = BashScriptConfigLoader("config/flatpak.toml")
        >>> config = loader.load()
        >>> print(config.exec_command)
        /usr/bin/flatpak update -y
    """

    DEFAULT_SECTION: str = "service"
    NOTIFICATION_SECTION: str = "notification"

    DEFAULT_NOTIFICATION_TITLE: str = "Task Update"
    DEFAULT_MESSAGE_SUCCESS: str = "Task completed successfully."
    DEFAULT_MESSAGE_FAILURE: str = "Task failed."
    DEFAULT_ICON_SUCCESS: str = "software-update-available"
    DEFAULT_ICON_FAILURE: str = "dialog-error"

    def load(self, section: str | None = None) -> BashScriptConfig:
        """Charge et retourne un BashScriptConfig.

        Charge la commande depuis la section spécifiée et les notifications
        depuis la section [notification] si présente et activée.

        Args:
            section: Nom de la section contenant exec_command.
                Par défaut "service".

        Returns:
            Instance de BashScriptConfig avec ou sans notification.

        Raises:
            KeyError: Si la section ou exec_command n'existe pas.

        Example:
            >>> loader = BashScriptConfigLoader("config/app.toml")
            >>> config = loader.load()
            >>> config.notification is not None
            True
        """
        section_name = section or self.DEFAULT_SECTION
        data: dict[str, Any] = self._get_section(section_name)

        exec_command = data.get("exec_command") or data.get("exec_start")
        if not exec_command:
            raise KeyError(
                f"Ni 'exec_command' ni 'exec_start' dans [{section_name}]"
            )

        notification = self._load_notification()

        return BashScriptConfig(
            exec_command=exec_command,
            notification=notification,
        )

    def load_without_notification(
        self,
        section: str | None = None
    ) -> BashScriptConfig:
        """Charge un BashScriptConfig sans notification.

        Utile quand on veut forcer la création d'un script simple
        même si le fichier contient une section [notification].

        Args:
            section: Nom de la section contenant exec_command.

        Returns:
            Instance de BashScriptConfig sans notification.

        Example:
            >>> loader = BashScriptConfigLoader("config/app.toml")
            >>> config = loader.load_without_notification()
            >>> config.notification is None
            True
        """
        section_name = section or self.DEFAULT_SECTION
        data: dict[str, Any] = self._get_section(section_name)

        exec_command = data.get("exec_command") or data.get("exec_start")
        if not exec_command:
            raise KeyError(
                f"Ni 'exec_command' ni 'exec_start' dans [{section_name}]"
            )

        return BashScriptConfig(exec_command=exec_command)

    def _load_notification(self) -> NotificationConfig | None:
        """Charge la configuration de notification si présente et activée.

        Returns:
            Instance de NotificationConfig ou None si désactivée/absente.
        """
        notif_data = self._config.get(self.NOTIFICATION_SECTION, {})

        if not notif_data.get("enabled", False):
            return None

        return NotificationConfig(
            title=notif_data.get("title", self.DEFAULT_NOTIFICATION_TITLE),
            message_success=notif_data.get(
                "message_success", self.DEFAULT_MESSAGE_SUCCESS
            ),
            message_failure=notif_data.get(
                "message_failure", self.DEFAULT_MESSAGE_FAILURE
            ),
            icon_success=notif_data.get(
                "icon_success", self.DEFAULT_ICON_SUCCESS
            ),
            icon_failure=notif_data.get(
                "icon_failure", self.DEFAULT_ICON_FAILURE
            ),
        )

    def has_notification(self) -> bool:
        """Vérifie si les notifications sont configurées et activées.

        Returns:
            True si la section [notification] existe et enabled=true.

        Example:
            >>> loader = BashScriptConfigLoader("config/app.toml")
            >>> if loader.has_notification():
            ...     print("Notifications activées")
        """
        notif_data = self._config.get(self.NOTIFICATION_SECTION, {})
        return bool(notif_data.get("enabled", False))

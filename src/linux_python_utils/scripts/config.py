"""Configuration pour la génération de scripts bash.

Ce module fournit une dataclass pour générer des scripts bash
avec support optionnel des notifications desktop Linux.

Example:
    Script simple sans notification:

        config = BashScriptConfig(exec_command="/usr/bin/flatpak update -y")
        script = config.to_bash_script()

    Script avec notification:

        from linux_python_utils.notification import NotificationConfig

        notif = NotificationConfig(
            title="Flatpak Update",
            message_success="Mise à jour réussie.",
            message_failure="Échec de la mise à jour."
        )
        config = BashScriptConfig(
            exec_command="/usr/bin/flatpak update -y",
            notification=notif
        )
        script = config.to_bash_script()
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from linux_python_utils.notification import NotificationConfig


@dataclass(frozen=True)
class BashScriptConfig:
    """Configuration pour générer des scripts bash.

    Cette dataclass encapsule la configuration nécessaire pour
    générer un script bash exécutant une commande avec support
    optionnel des notifications de succès/échec.

    Attributes:
        exec_command: Commande à exécuter dans le script.
        notification: Configuration des notifications (optionnel).
            Si None, le script n'enverra pas de notifications.

    Example:
        >>> config = BashScriptConfig(exec_command="echo 'Hello'")
        >>> script = config.to_bash_script()
        >>> "echo 'Hello'" in script
        True
    """

    exec_command: str
    notification: NotificationConfig | None = None

    def __post_init__(self) -> None:
        """Valide les champs requis après initialisation.

        Raises:
            ValueError: Si exec_command est vide.
        """
        if not self.exec_command:
            raise ValueError("exec_command est requis")

    def to_bash_script(self) -> str:
        """Génère le script bash complet.

        Si une configuration de notification est fournie, le script
        inclura la fonction send_notification() et enverra des
        notifications selon le code de retour de la commande.

        Returns:
            Contenu complet du script bash.

        Example:
            >>> config = BashScriptConfig(exec_command="ls -la")
            >>> script = config.to_bash_script()
            >>> script.startswith("#!/bin/bash")
            True
        """
        if self.notification is None:
            return self._generate_simple_script()
        return self._generate_script_with_notification()

    def _generate_simple_script(self) -> str:
        """Génère un script bash simple sans notification.

        Returns:
            Script bash minimal exécutant uniquement la commande.
        """
        return f"""#!/bin/bash
{self.exec_command}
"""

    def _generate_script_with_notification(self) -> str:
        """Génère un script bash avec notifications.

        Returns:
            Script bash complet avec fonction de notification et
            envoi conditionnel selon le code de retour.
        """
        return f"""#!/bin/bash
# Script généré automatiquement par linux_python_utils
# Inclut la gestion des notifications KDE Plasma

{self.notification.to_bash_function()}

# Exécuter la commande principale
{self.exec_command}
exit_code=$?

# Envoyer la notification selon le résultat
if [ $exit_code -eq 0 ]; then
    {self.notification.to_bash_call_success()}
else
    {self.notification.to_bash_call_failure()}
fi

exit $exit_code
"""


@dataclass(frozen=True)
class PythonCliConfig:
    """Configuration pour le déploiement d'un script Python CLI.

    Source de vérité pour le déploiement : l'installation respecte
    le standard FHS (system ou user scope) en s'appuyant sur
    pyproject.toml pour les dépendances et les points d'entrée.

    Attributes:
        name: Nom de l'application (utilisé pour les chemins FHS).
        deploy_type: Portée du déploiement ('system' ou 'user').
        source_dir: Répertoire contenant pyproject.toml et le code.
        venv_path: Chemin du venv (None → pas de venv géré).
        check_extras: Groupes d'extras à vérifier (ex. ['dev']).
        generate_wrapper: Si True, génère un wrapper bash si nécessaire.

    Example:
        >>> config = PythonCliConfig(
        ...     name="mon-app",
        ...     deploy_type="user",
        ...     source_dir=Path("/home/user/mon-app"),
        ... )
        >>> config.deploy_type
        'user'
    """

    name: str
    deploy_type: Literal["system", "user"]
    source_dir: Path
    venv_path: Path | None = None
    check_extras: list[str] = field(default_factory=list)
    generate_wrapper: bool = True

    def __post_init__(self) -> None:
        """Valide les champs après initialisation.

        Raises:
            ValueError: Si name est vide ou deploy_type invalide.
        """
        if not self.name.strip():
            raise ValueError(
                "name est requis et ne peut pas être vide"
            )
        if self.deploy_type not in ("system", "user"):
            raise ValueError(
                f"deploy_type invalide : '{self.deploy_type}'."
                " Valeurs acceptées : 'system', 'user'"
            )

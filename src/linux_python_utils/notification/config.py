"""Configuration pour les notifications desktop Linux.

Ce module fournit une dataclass pour configurer les notifications
envoyées via notify-send sur les systèmes Linux.
"""

import shlex
from dataclasses import dataclass


@dataclass(frozen=True)
class NotificationConfig:
    """Configuration pour les notifications desktop Linux.

    Génère du code bash via ``to_bash_function()`` et ``to_bash_call_*()``.
    Les champs texte (title, message_*, app_name) ne doivent pas contenir
    de caractères de contrôle (ord < 32 : ``\\n``, ``\\t``, ``\\x00``…)
    ni être vides.

    Attributes:
        title: Titre de la notification.
        message_success: Message affiché en cas de succès.
        message_failure: Message affiché en cas d'échec.
        icon_success: Icône affichée en cas de succès.
        icon_failure: Icône affichée en cas d'échec.
        app_name: Nom de l'application passé à notify-send (-a).
    """

    title: str
    message_success: str
    message_failure: str
    icon_success: str = "software-update-available"
    icon_failure: str = "dialog-error"
    app_name: str = "Flatpak"

    def __post_init__(self) -> None:
        """Valide les champs texte après initialisation.

        Raises:
            ValueError: Si un champ requis est vide ou contient un
                caractère de contrôle (ord < 32).
        """
        for champ, valeur in (
            ("title", self.title),
            ("message_success", self.message_success),
            ("message_failure", self.message_failure),
            ("app_name", self.app_name),
        ):
            if not valeur:
                raise ValueError(f"{champ} est requis")
            if any(ord(c) < 32 for c in valeur):
                raise ValueError(
                    f"Caractère de contrôle interdit dans '{champ}'."
                )

    def to_bash_function(self) -> str:
        """Génère la fonction bash send_notification().

        Le nom d'application injecté dans notify-send est isolé via
        ``shlex.quote`` pour prévenir toute injection de commande.

        Returns:
            Code bash de la fonction send_notification().
        """
        app_q = shlex.quote(self.app_name)
        return f'''send_notification() {{
    local title="$1"
    local message="$2"
    local icon="$3"

    # Envoyer la notification à tous les utilisateurs connectés
    for user_id in $(loginctl list-users --no-legend \\
        | awk '{{print $1}}'); do
        user_name=$(loginctl list-users --no-legend \\
            | awk -v id="$user_id" '$1==id {{print $2}}')
        user_runtime_dir="/run/user/$user_id"

        if [ -S "$user_runtime_dir/bus" ]; then
            # Exécuter notify-send avec timeout en arrière-plan
            timeout 10 runuser -u "$user_name" -- env \\
                DBUS_SESSION_BUS_ADDRESS="unix:path=$user_runtime_dir/bus" \\
                notify-send -i "$icon" -a {app_q} "$title" "$message" &
        fi
    done
    # Attendre brièvement que les notifications soient envoyées
    sleep 1
}}'''

    def _to_bash_call(self, message: str, icon: str) -> str:
        """Génère une ligne d'appel bash send_notification.

        Args:
            message: Message à afficher.
            icon: Nom de l'icône.

        Returns:
            Ligne bash avec arguments échappés par shlex.quote.
        """
        return (
            f"send_notification {shlex.quote(self.title)}"
            f" {shlex.quote(message)} {shlex.quote(icon)}"
        )

    def to_bash_call_success(self) -> str:
        """Génère l'appel bash pour une notification de succès.

        Returns:
            Ligne bash appelant send_notification avec paramètres succès.
        """
        return self._to_bash_call(self.message_success, self.icon_success)

    def to_bash_call_failure(self) -> str:
        """Génère l'appel bash pour une notification d'échec.

        Returns:
            Ligne bash appelant send_notification avec paramètres échec.
        """
        return self._to_bash_call(self.message_failure, self.icon_failure)

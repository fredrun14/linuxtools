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
    Les champs texte (title, message_*) ne doivent pas contenir de
    caractères de contrôle (ord < 32 : ``\\n``, ``\\t``, ``\\x00``…)
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
        if not self.title:
            raise ValueError("title est requis")
        if not self.message_success:
            raise ValueError("message_success est requis")
        if not self.message_failure:
            raise ValueError("message_failure est requis")
        for champ, valeur in (
            ("title", self.title),
            ("message_success", self.message_success),
            ("message_failure", self.message_failure),
        ):
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

    def to_bash_call_success(self) -> str:
        """Génère l'appel bash pour une notification de succès.

        Returns:
            Ligne bash appelant send_notification avec paramètres succès.
        """
        title = shlex.quote(self.title)
        message = shlex.quote(self.message_success)
        icon = shlex.quote(self.icon_success)
        return f"send_notification {title} {message} {icon}"

    def to_bash_call_failure(self) -> str:
        """Génère l'appel bash pour une notification d'échec.

        Returns:
            Ligne bash appelant send_notification avec paramètres échec.
        """
        title = shlex.quote(self.title)
        message = shlex.quote(self.message_failure)
        icon = shlex.quote(self.icon_failure)
        return f"send_notification {title} {message} {icon}"

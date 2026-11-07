"""Emplacement par défaut des fichiers de logs d'une application."""

import os
from pathlib import Path

from platformdirs import user_state_path


def default_log_dir(app_name: str) -> Path:
    """Retourne le dossier de logs par défaut d'une application.

    Sous root : ``/var/log/<app_name>`` (FHS). Sinon :
    ``$XDG_STATE_HOME/<app_name>`` (``~/.local/state/<app_name>``).
    Le dossier n'est pas créé : ``FileLogger`` crée son dossier parent.

    Args:
        app_name: Nom simple de l'application (kebab-case), sans
            séparateur ni valeur vide : sous root, un nom absolu
            remplacerait ``/var/log``. Il n'est pas validé.

    Returns:
        Chemin du dossier de logs (non créé).
    """
    if os.geteuid() == 0:
        return Path("/var/log") / app_name
    return user_state_path(app_name)

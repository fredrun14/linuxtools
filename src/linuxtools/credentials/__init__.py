"""Module de gestion des credentials pour applications Linux.

Fournit une chaine de priorite configurable :
    Shell env vars -> fichier .env (python-dotenv) -> keyring systeme

Compatibilite keyring : KWallet (KDE Plasma 6), KeePassXC (avec
"Enable Secret Service" active), GNOME Keyring.

Dependances optionnelles :
    pip install python-dotenv   # pour DotEnvCredentialProvider
    pip install keyring         # pour KeyringCredentialProvider

Exemple d'utilisation :

    from linuxtools.credentials import CredentialManager

    manager = CredentialManager.from_dotenv(
        service="monapp",
        dotenv_path=Path("config/.env"),
    )
    password = manager.get("API_PASSWORD")
    manager.store("API_PASSWORD", new_password)
"""

from linuxtools.credentials.base import (
    CredentialProvider,
    CredentialStore,
)
from linuxtools.credentials.chain import CredentialChain
from linuxtools.credentials.exceptions import (
    CredentialError,
    CredentialNotFoundError,
    CredentialProviderUnavailableError,
    CredentialStoreError,
)
from linuxtools.credentials.manager import CredentialManager
from linuxtools.credentials.models import (
    Credential,
    CredentialKey,
)
from linuxtools.credentials.providers import (
    DotEnvCredentialProvider,
    EnvCredentialProvider,
    KeyringCredentialProvider,
)

__all__ = [
    "Credential",
    "CredentialChain",
    "CredentialError",
    "CredentialKey",
    "CredentialManager",
    "CredentialNotFoundError",
    "CredentialProvider",
    "CredentialProviderUnavailableError",
    "CredentialStore",
    "CredentialStoreError",
    "DotEnvCredentialProvider",
    "EnvCredentialProvider",
    "KeyringCredentialProvider",
]

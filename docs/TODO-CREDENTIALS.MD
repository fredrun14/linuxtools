# TODO-CREDENTIALS.MD

Externalisation du module `credentials` dans `linux_python_utils`.

**Objectif** : extraire la logique de gestion des secrets (variables
d'environnement, fichiers `.env`, keyring système) du projet `scanNetHome`
vers un module réutilisable `linux_python_utils/credentials/`, en respectant
scrupuleusement les principes SOLID et les conventions du projet.

**Date de création** : 2026-02-22
**Statut** : À faire

---

## Contexte

Le projet `scanNetHome` implémente une chaîne de priorité pour les
credentials du routeur ASUS :

```
Shell env vars → config/.env (python-dotenv) → keyring système → ""
```

Cette logique est actuellement inline dans `scan_net_home/__main__.py`
(fonctions `_load_dotenv`, `_get_router_username`, `_get_router_password`,
`cmd_router_credentials`) avec des imports conditionnels de `dotenv` et
`keyring`. Elle doit être externalisée pour être réutilisable par tout
projet futur.

---

## Architecture cible

```
linux_python_utils/credentials/
├── __init__.py          # Exports publics via __all__
├── base.py              # ABCs : CredentialProvider, CredentialStore
├── models.py            # CredentialKey, Credential (frozen dataclasses)
├── exceptions.py        # CredentialNotFoundError, CredentialStoreError
├── providers/
│   ├── __init__.py      # Exports des providers
│   ├── env.py           # EnvCredentialProvider (os.environ)
│   ├── dotenv.py        # DotEnvCredentialProvider (python-dotenv optionnel)
│   └── keyring.py       # KeyringCredentialProvider (keyring optionnel)
├── chain.py             # CredentialChain (Chain of Responsibility)
└── manager.py           # CredentialManager (façade)
```

---

## Tâches

---

### TÂCHE 1 — Modèles de données (`models.py`)

**Fichier** : `linux_python_utils/credentials/models.py`

Créer deux frozen dataclasses avec validation dans `__post_init__` :

#### `CredentialKey`

```python
@dataclass(frozen=True)
class CredentialKey:
    """Clé d'identification d'un credential (service + nom de clé)."""
    service: str   # ex: "scannethome", "myapp"
    key: str       # ex: "admin", "ASUS_ROUTER_PASSWORD"

    def __post_init__(self) -> None:
        # Valider que service et key sont non vides, sans espaces
        ...
```

#### `Credential`

```python
@dataclass(frozen=True)
class Credential:
    """Credential complet : clé + valeur."""
    service: str
    key: str
    value: str
    source: str = ""   # ex: "env", "dotenv", "keyring" — pour traçabilité

    def __post_init__(self) -> None:
        # Valider que service et key sont non vides
        ...

    @property
    def credential_key(self) -> CredentialKey:
        """Retourne la clé d'identification."""
        return CredentialKey(service=self.service, key=self.key)
```

**Conventions** :
- Frozen dataclasses, `__post_init__` avec `raise ValueError` si invalide
- Docstrings en français
- Type hints complets

---

### TÂCHE 2 — Exceptions (`exceptions.py`)

**Fichier** : `linux_python_utils/credentials/exceptions.py`

```python
class CredentialNotFoundError(Exception):
    """Levée quand un credential n'est trouvé dans aucun provider."""
    ...

class CredentialStoreError(Exception):
    """Levée quand le stockage d'un credential échoue."""
    ...

class CredentialProviderUnavailableError(Exception):
    """Levée quand un provider requis n'est pas disponible (module absent)."""
    ...
```

---

### TÂCHE 3 — ABCs (`base.py`)

**Fichier** : `linux_python_utils/credentials/base.py`

Appliquer **Interface Segregation Principle** : séparer la lecture de
l'écriture en deux ABCs distinctes.

#### `CredentialProvider` (lecture seule)

```python
class CredentialProvider(ABC):
    """Interface de lecture d'un credential depuis une source."""

    @abstractmethod
    def get(
        self,
        service: str,
        key: str,
    ) -> Optional[str]:
        """Retourne la valeur du credential ou None si absent."""
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """Indique si ce provider est opérationnel (module présent, etc.)."""
        ...

    @property
    @abstractmethod
    def source_name(self) -> str:
        """Nom court de la source (ex: 'env', 'dotenv', 'keyring')."""
        ...
```

#### `CredentialStore` (lecture + écriture)

```python
class CredentialStore(CredentialProvider):
    """Interface de lecture ET d'écriture d'un credential."""

    @abstractmethod
    def set(
        self,
        service: str,
        key: str,
        value: str,
    ) -> None:
        """Stocke un credential. Lève CredentialStoreError si échec."""
        ...

    @abstractmethod
    def delete(
        self,
        service: str,
        key: str,
    ) -> None:
        """Supprime un credential. Silencieux si absent."""
        ...
```

**Justification SOLID** :
- **I (ISP)** : les clients qui lisent seulement dépendent de
  `CredentialProvider`, pas de `CredentialStore`
- **D (DIP)** : les consommateurs dépendent des ABCs, pas des
  implémentations concrètes

---

### TÂCHE 4 — Provider : variables d'environnement (`providers/env.py`)

**Fichier** : `linux_python_utils/credentials/providers/env.py`

```python
class EnvCredentialProvider(CredentialProvider):
    """Lit les credentials depuis os.environ.

    La clé cherchée est le paramètre `key` en majuscules.
    Ex : service="scannethome", key="ASUS_ROUTER_PASSWORD"
    → os.environ.get("ASUS_ROUTER_PASSWORD")
    """

    def __init__(
        self,
        logger: Optional[Logger] = None,
    ) -> None:
        ...

    def get(self, service: str, key: str) -> Optional[str]:
        """Lit os.environ[key.upper()] ou None."""
        ...

    def is_available(self) -> bool:
        """Toujours True (os.environ toujours disponible)."""
        return True

    @property
    def source_name(self) -> str:
        return "env"
```

**Notes** :
- Pas de dépendance externe
- Aucune exception levée — retourne `None` si absent

---

### TÂCHE 5 — Provider : fichier `.env` (`providers/dotenv.py`)

**Fichier** : `linux_python_utils/credentials/providers/dotenv.py`

```python
class DotEnvCredentialProvider(CredentialProvider):
    """Charge un fichier .env puis lit les credentials depuis os.environ.

    Utilise python-dotenv avec override=False (les variables shell
    existantes ont priorité sur le .env).

    Si python-dotenv n'est pas installé, is_available() retourne False
    et get() retourne toujours None (dégradation gracieuse).
    """

    def __init__(
        self,
        dotenv_path: Union[str, Path],
        logger: Optional[Logger] = None,
    ) -> None:
        """
        Args:
            dotenv_path: Chemin absolu ou relatif vers le fichier .env.
            logger: Logger optionnel (injection de dépendance).
        """
        ...

    def load(self) -> bool:
        """Charge le fichier .env. Retourne True si chargé avec succès."""
        ...

    def get(self, service: str, key: str) -> Optional[str]:
        """Lit os.environ[key.upper()] après chargement du .env."""
        ...

    def is_available(self) -> bool:
        """True si python-dotenv est installé et le fichier .env existe."""
        ...

    @property
    def source_name(self) -> str:
        return "dotenv"
```

**Notes** :
- Import `dotenv` conditionnel dans le corps de la méthode ou en haut
  du module avec `try/except ImportError`
- `override=False` : variable shell existante a priorité
- Logger avertit si le fichier `.env` est absent

---

### TÂCHE 6 — Provider : keyring système (`providers/keyring.py`)

**Fichier** : `linux_python_utils/credentials/providers/keyring.py`

```python
class KeyringCredentialProvider(CredentialStore):
    """Lit et écrit des credentials via le keyring FreeDesktop Secret Service.

    Compatibilités vérifiées :
    - KWallet (KDE Plasma 6)
    - KeePassXC (avec "Enable Secret Service" activé)
    - GNOME Keyring
    - Toute implémentation FreeDesktop Secret Service

    Si le module keyring n'est pas installé, is_available() retourne False
    et toutes les opérations retournent None / lèvent
    CredentialProviderUnavailableError (dégradation gracieuse).
    """

    def __init__(
        self,
        logger: Optional[Logger] = None,
        keyring_backend: Optional[Any] = None,
    ) -> None:
        """
        Args:
            logger: Logger optionnel.
            keyring_backend: Backend keyring optionnel (pour tests :
                             injection d'un mock).
        """
        ...

    def get(self, service: str, key: str) -> Optional[str]:
        """Lit keyring.get_password(service, key) ou None."""
        ...

    def set(self, service: str, key: str, value: str) -> None:
        """Stocke via keyring.set_password(service, key, value).

        Raises:
            CredentialStoreError: si le keyring est indisponible ou
                                  si l'opération échoue.
        """
        ...

    def delete(self, service: str, key: str) -> None:
        """Supprime via keyring.delete_password(service, key).
        Silencieux si le credential est absent.
        """
        ...

    def is_available(self) -> bool:
        """True si le module keyring est installé et un backend est actif."""
        ...

    @property
    def source_name(self) -> str:
        return "keyring"
```

**Notes** :
- Injection de `keyring_backend` (DIP) pour faciliter les tests
- `keyring.errors.KeyringError` intercepté → `CredentialStoreError`
- Logger trace les opérations de stockage/suppression

---

### TÂCHE 7 — Chaîne de priorité (`chain.py`)

**Fichier** : `linux_python_utils/credentials/chain.py`

Implémenter le **Chain of Responsibility Pattern** :

```python
class CredentialChain(CredentialProvider):
    """Parcourt une liste ordonnée de providers jusqu'à trouver le credential.

    Exemple de chaîne pour scanNetHome :
        chain = CredentialChain([
            EnvCredentialProvider(),           # 1. Shell env vars
            DotEnvCredentialProvider(path),    # 2. config/.env
            KeyringCredentialProvider(),       # 3. keyring système
        ])
        password = chain.get("scannethome", "ASUS_ROUTER_PASSWORD") or ""
    """

    def __init__(
        self,
        providers: List[CredentialProvider],
        logger: Optional[Logger] = None,
    ) -> None:
        """
        Args:
            providers: Liste ordonnée de providers (priorité décroissante).
            logger: Logger optionnel.
        """
        ...

    def get(self, service: str, key: str) -> Optional[str]:
        """Retourne le premier credential trouvé dans la chaîne, ou None."""
        # Itère sur providers, retourne dès le premier non-None
        # Logger debug: "Credential trouvé dans <source_name>"
        ...

    def get_with_source(
        self,
        service: str,
        key: str,
    ) -> Optional[Credential]:
        """Comme get() mais retourne un Credential avec le champ source."""
        ...

    def is_available(self) -> bool:
        """True si au moins un provider est disponible."""
        ...

    @property
    def source_name(self) -> str:
        return "chain"

    @classmethod
    def default(
        cls,
        dotenv_path: Optional[Union[str, Path]] = None,
        logger: Optional[Logger] = None,
    ) -> "CredentialChain":
        """Factory : crée la chaîne standard env → dotenv → keyring.

        Args:
            dotenv_path: Chemin optionnel vers un fichier .env.
            logger: Logger optionnel partagé.
        """
        providers: List[CredentialProvider] = [
            EnvCredentialProvider(logger=logger),
        ]
        if dotenv_path is not None:
            providers.append(
                DotEnvCredentialProvider(
                    dotenv_path=dotenv_path,
                    logger=logger,
                )
            )
        providers.append(KeyringCredentialProvider(logger=logger))
        return cls(providers=providers, logger=logger)
```

**Justification SOLID** :
- **O (OCP)** : ajouter un provider n'exige pas de modifier `CredentialChain`
- **L (LSP)** : `CredentialChain` est un `CredentialProvider`, utilisable
  partout où un provider simple est attendu
- **D (DIP)** : dépend de l'ABC `CredentialProvider`, pas des concrétions

---

### TÂCHE 8 — Façade (`manager.py`)

**Fichier** : `linux_python_utils/credentials/manager.py`

```python
class CredentialManager:
    """Façade unifiée pour lire et stocker des credentials.

    Combine une CredentialChain pour la lecture et un CredentialStore
    optionnel pour l'écriture (ex: KeyringCredentialProvider).

    Usage typique :
        manager = CredentialManager.from_dotenv(
            service="scannethome",
            dotenv_path=Path("config/.env"),
        )
        password = manager.get("ASUS_ROUTER_PASSWORD")
        manager.store("ASUS_ROUTER_PASSWORD", new_password)
    """

    def __init__(
        self,
        service: str,
        chain: CredentialChain,
        store: Optional[CredentialStore] = None,
        logger: Optional[Logger] = None,
    ) -> None:
        """
        Args:
            service: Nom du service applicatif (ex: "scannethome").
            chain: Chaîne de providers pour la lecture.
            store: Store optionnel pour l'écriture.
            logger: Logger optionnel.
        """
        ...

    def get(self, key: str, default: str = "") -> str:
        """Lit un credential. Retourne default si absent de toute la chaîne."""
        ...

    def require(self, key: str) -> str:
        """Lit un credential. Lève CredentialNotFoundError si absent."""
        ...

    def store(self, key: str, value: str) -> None:
        """Stocke un credential dans le store configuré.

        Raises:
            CredentialStoreError: si aucun store n'est configuré ou si
                                  l'opération échoue.
        """
        ...

    def delete(self, key: str) -> None:
        """Supprime un credential du store configuré."""
        ...

    @classmethod
    def from_dotenv(
        cls,
        service: str,
        dotenv_path: Optional[Union[str, Path]] = None,
        logger: Optional[Logger] = None,
    ) -> "CredentialManager":
        """Factory : crée un manager avec la chaîne standard et keyring store.

        Chaîne : env → dotenv (si dotenv_path fourni) → keyring
        Store  : KeyringCredentialProvider
        """
        ...
```

---

### TÂCHE 9 — Exports (`__init__.py` du module)

**Fichier** : `linux_python_utils/credentials/__init__.py`

```python
"""Module de gestion des credentials pour applications Linux.

Fournit une chaîne de priorité configurable :
    Shell env vars → fichier .env (python-dotenv) → keyring système

Compatibilité keyring : KWallet, KeePassXC (Secret Service), GNOME Keyring.
"""

from linux_python_utils.credentials.base import (
    CredentialProvider,
    CredentialStore,
)
from linux_python_utils.credentials.models import (
    Credential,
    CredentialKey,
)
from linux_python_utils.credentials.exceptions import (
    CredentialNotFoundError,
    CredentialProviderUnavailableError,
    CredentialStoreError,
)
from linux_python_utils.credentials.providers.env import (
    EnvCredentialProvider,
)
from linux_python_utils.credentials.providers.dotenv import (
    DotEnvCredentialProvider,
)
from linux_python_utils.credentials.providers.keyring import (
    KeyringCredentialProvider,
)
from linux_python_utils.credentials.chain import CredentialChain
from linux_python_utils.credentials.manager import CredentialManager

__all__ = [
    "CredentialProvider",
    "CredentialStore",
    "Credential",
    "CredentialKey",
    "CredentialNotFoundError",
    "CredentialProviderUnavailableError",
    "CredentialStoreError",
    "EnvCredentialProvider",
    "DotEnvCredentialProvider",
    "KeyringCredentialProvider",
    "CredentialChain",
    "CredentialManager",
]
```

---

### TÂCHE 10 — Mise à jour de `linux_python_utils/__init__.py`

Ajouter les exports du nouveau module dans le `__init__.py` racine du
package (section `# Credentials`) en suivant le même pattern que les
autres modules (commentaire de section + liste d'imports).

---

### TÂCHE 11 — Dépendances optionnelles (`pyproject.toml`)

Mettre à jour `/home/fred/PycharmProjects/linux_python_utils/pyproject.toml`
pour déclarer les dépendances optionnelles du module `credentials` :

```toml
[project.optional-dependencies]
credentials = [
    "python-dotenv>=1.0",
    "keyring>=24.0",
]
dev = [
    "pytest>=7.0",
    "pycodestyle>=2.10",
    "pydantic>=2.0",
    "python-dotenv>=1.0",   # Pour tests DotEnvCredentialProvider
    "keyring>=24.0",        # Pour tests KeyringCredentialProvider
]
```

**Note** : les providers se dégradent gracieusement si le module est absent
(`is_available()` retourne `False`). L'installation reste optionnelle.

---

### TÂCHE 12 — Tests unitaires

**Fichier** : `tests/test_credentials.py`
(dans `/home/fred/PycharmProjects/linux_python_utils/tests/`)

Couvrir les cas suivants :

#### `test_env_provider.py` (ou section dans `test_credentials.py`)

```python
# EnvCredentialProvider
- get() retourne la valeur si la variable existe dans os.environ
- get() retourne None si la variable est absente
- is_available() retourne toujours True
- insensibilité à la casse du paramètre key (key.upper())
```

#### `test_dotenv_provider.py`

```python
# DotEnvCredentialProvider
- load() charge le .env avec tmp_path fixture
- get() retourne la valeur depuis le fichier .env
- override=False : variable shell existante prend priorité sur .env
- is_available() retourne False si python-dotenv absent (mock import)
- is_available() retourne False si le fichier .env n'existe pas
```

#### `test_keyring_provider.py`

```python
# KeyringCredentialProvider
- get() délègue à keyring.get_password (backend mocké)
- set() délègue à keyring.set_password (backend mocké)
- delete() silencieux si absent (keyring.errors.PasswordDeleteError ignoré)
- set() lève CredentialStoreError si keyring.errors.KeyringError
- is_available() retourne False si keyring absent (mock import)
```

#### `test_credential_chain.py`

```python
# CredentialChain
- get() retourne la valeur du premier provider qui répond
- get() retourne None si aucun provider ne répond
- get_with_source() retourne le bon source_name
- les providers indisponibles (is_available=False) sont ignorés
- CredentialChain.default() crée la chaîne env → dotenv → keyring
```

#### `test_credential_manager.py`

```python
# CredentialManager
- get() retourne la valeur via la chaîne
- get() retourne default si absent
- require() lève CredentialNotFoundError si absent
- store() délègue au CredentialStore
- store() lève CredentialStoreError si pas de store configuré
- from_dotenv() factory crée le bon manager
```

**Convention de mocking** :
- Injecter `MagicMock(spec=CredentialProvider)` dans `CredentialChain`
- Injecter un faux backend keyring via `keyring_backend` dans
  `KeyringCredentialProvider`
- Utiliser `tmp_path` fixture pour les fichiers `.env` de test
- Utiliser `monkeypatch.setenv` pour simuler os.environ

---

### TÂCHE 13 — Migration dans `scanNetHome`

Après validation des tests du module `credentials`, refactorer
`scan_net_home/__main__.py` :

**Supprimer** :
- Les imports conditionnels `keyring` et `dotenv` en tête de fichier
- Les constantes `_KEYRING_AVAILABLE`, `_DOTENV_AVAILABLE`, `_KEYRING_SERVICE`
- Les fonctions `_load_dotenv()`, `_get_router_username()`,
  `_get_router_password()`

**Ajouter** :
```python
from linux_python_utils.credentials import CredentialManager

# Dans main() ou build_manager() :
_CREDENTIAL_SERVICE = "scannethome"
credential_manager = CredentialManager.from_dotenv(
    service=_CREDENTIAL_SERVICE,
    dotenv_path=Path(args.config).parent / ".env",
    logger=logger,
)
username = credential_manager.get("ASUS_ROUTER_USER")
password = credential_manager.get("ASUS_ROUTER_PASSWORD")
```

**Dans `cmd_router_credentials()`** :
```python
credential_manager.store("ASUS_ROUTER_PASSWORD", password)
```

---

### TÂCHE 14 — Documentation et Makefile

#### Makefile (`linux_python_utils`)

Ajouter :
```makefile
test-credentials:  ## Lancer les tests du module credentials
    PYTHONPATH=. pytest tests/test_credentials*.py -v
```

#### README

Ajouter une section `## Module credentials` documentant :
- La chaîne de priorité (env → .env → keyring)
- Les dépendances optionnelles (`pip install linux-python-utils[credentials]`)
- Un exemple minimal d'utilisation
- La compatibilité keyring (KWallet, KeePassXC, GNOME Keyring)

---

## Récapitulatif des fichiers à créer

| Fichier | Description |
|---------|-------------|
| `credentials/__init__.py` | Exports publics du module |
| `credentials/base.py` | ABCs `CredentialProvider`, `CredentialStore` |
| `credentials/models.py` | `CredentialKey`, `Credential` (frozen dataclasses) |
| `credentials/exceptions.py` | Exceptions métier |
| `credentials/providers/__init__.py` | Exports des providers |
| `credentials/providers/env.py` | `EnvCredentialProvider` |
| `credentials/providers/dotenv.py` | `DotEnvCredentialProvider` |
| `credentials/providers/keyring.py` | `KeyringCredentialProvider` |
| `credentials/chain.py` | `CredentialChain` |
| `credentials/manager.py` | `CredentialManager` |
| `tests/test_credentials.py` | Tests unitaires complets |

## Récapitulatif des fichiers à modifier

| Fichier | Modification |
|---------|-------------|
| `linux_python_utils/__init__.py` | Ajouter section exports `credentials` |
| `pyproject.toml` | Ajouter extra `credentials` et dépendances dev |
| `Makefile` | Ajouter cible `test-credentials` |
| `README.md` | Ajouter section module `credentials` |
| `scanNetHome/scan_net_home/__main__.py` | Migrer vers `CredentialManager` |
| `scanNetHome/CLAUDE.md` | Mettre à jour la doc credentials |

---

## Ordre d'implémentation recommandé

```
1  → models.py          (aucune dépendance interne)
2  → exceptions.py      (aucune dépendance interne)
3  → base.py            (dépend de models.py)
4  → providers/env.py   (dépend de base.py)
5  → providers/dotenv.py(dépend de base.py)
6  → providers/keyring.py (dépend de base.py, exceptions.py)
7  → chain.py           (dépend de base.py, models.py, providers/)
8  → manager.py         (dépend de chain.py, base.py, exceptions.py)
9  → __init__.py        (dépend de tout)
10 → tests              (valider chaque étape)
11 → pyproject.toml     (dépendances optionnelles)
12 → linux_python_utils/__init__.py (intégration)
13 → Migration scanNetHome
14 → Documentation
```

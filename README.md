# 🐧 Linux Python Utils

[![Python](https://img.shields.io/badge/Python-3.11%2B-blue.svg)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/Tests-passing-brightgreen.svg)]()
[![Code Style](https://img.shields.io/badge/Code%20Style-PEP8-black.svg)]()
[![SOLID](https://img.shields.io/badge/Architecture-SOLID-purple.svg)]()

> Bibliothèque utilitaire Python pour systèmes Linux, conçue avec les principes SOLID.

Fournit des classes réutilisables et extensibles pour le logging, la configuration, la gestion de fichiers, les services systemd, l'exécution de commandes, la gestion d'identités Unix, la gestion de fichiers INI, la validation de données et la vérification d'intégrité. Architecture basée sur des Abstract Base Classes (ABC) permettant l'injection de dépendances et facilitant les tests unitaires.

## 📋 Table des Matières

- [Fonctionnalités](#-fonctionnalités)
- [Prérequis](#-prérequis)
- [Installation](#-installation)
- [Architecture Globale](#-architecture-globale)
- [Structure du Projet](#-structure-du-projet)
- [Module logging](#-module-logging)
- [Module errors](#-module-errors)
- [Module config](#-module-config)
- [Module commands](#-module-commands)
- [Module filesystem](#-module-filesystem)
- [Module systemd](#-module-systemd)
- [Module scripts](#-module-scripts)
- [Module network](#-module-network)
- [Module identity](#-module-identity)
- [Module cli](#-module-cli)
- [Module dotconf](#-module-dotconf)
- [Module integrity](#-module-integrity)
- [Module credentials](#-module-credentials)
- [Module validation](#-module-validation)
- [Module notification](#-module-notification)
- [Exemple Complet](#-exemple-complet)
- [Tests](#-tests)
- [Troubleshooting](#-troubleshooting)
- [Contribution](#-contribution)
- [Licence](#-licence)

## ✨ Fonctionnalités

- **📝 Logging robuste** — `FileLogger` (fichier + console, UTF-8), `ConsoleLogger` (stdout/stderr sans fichier), `SecurityLogger` (JSON structuré pour audit trail)
- **⚙️ Configuration flexible** — Support TOML/JSON avec fusion profonde et profils
- **📁 Gestion de fichiers** — CRUD fichiers et sauvegardes préservant les métadonnées
- **🔧 Systemd complet** — Gestion services, timers et unités de montage (système et utilisateur)
- **📄 Chargeurs de config** — Loaders typés pour créer des dataclasses depuis TOML ou JSON
- **🔐 Vérification d'intégrité** — Checksums SHA256/SHA512/MD5 pour fichiers et répertoires
- **🖥️ Exécution de commandes** — Construction fluent et exécution avec streaming temps réel
- **📋 Fichiers INI (.conf)** — Lecture, écriture et validation de fichiers de configuration INI ; `SectionAwareEditor` pour l'édition ligne-à-ligne préservant les commentaires
- **📜 Scripts bash et CLI** — Génération de scripts bash + déploiement de scripts Python CLI (FHS, uv, scope système/utilisateur, rapport d'installation)
- **👤 Gestion d'identités Unix** — Création idempotente de groupes (`groupadd`/`groupmod`) et utilisateurs (`useradd`/`usermod`) avec vérification GID/UID
- **🔔 Notifications** — Configuration des notifications desktop (KDE Plasma)
- **✅ Validation** — Validation de chemins (existence, permissions, world-writable) et données avec support optionnel Pydantic
- **🚨 Gestion d'erreurs** — Hiérarchie d'exceptions applicatives + chaîne de handlers (Chain of Responsibility)
- **🔑 Secrets** — `CredentialChain` : env → `.env` → keyring système (KWallet, KeePassXC, GNOME Keyring)
- **🌐 Réseau** — Scan ARP/nmap, inventaire JSON, DHCP, DNS, rapports (table, CSV, JSON, diff)
- **🖱️ Framework CLI** — `CliCommand` (ABC) + `CliApplication` (Command Pattern + argparse)
- **🏗️ Architecture SOLID** — ABCs, injection de dépendances, testabilité maximale
- **🔒 Sécurisé** — Validation des entrées, protection TOCTOU, permissions explicites
- **🛡️ Événements de sécurité** — `SecurityLogger` avec 10 types d'événements typés (`SecurityEventType`) en JSON structuré pour audit trail
- **🧪 Bien testé** — Tests unitaires couvrant tous les modules

## 📦 Prérequis

| Prérequis | Version | Vérification |
|-----------|---------|--------------|
| Python | 3.11+ | `python --version` |
| pip | 21.0+ | `pip --version` |
| Linux | Kernel 4.0+ | `uname -r` |

> **Note** : Python 3.11+ est requis car la bibliothèque utilise `tomllib` (stdlib).

## 🔧 Installation

### Installation depuis les Sources

```bash
# 1. Cloner le repository
git clone https://github.com/user/linux-python-utils.git
cd linux-python-utils

# 2. Créer un environnement virtuel
python -m venv venv
source venv/bin/activate

# 3. Installer en mode développement
pip install -e .

# 4. (Optionnel) Installer les extras
pip install -e ".[validation]"   # validation Pydantic
pip install -e ".[credentials]"  # python-dotenv + keyring
pip install -e ".[deploy]"       # platformdirs (ScriptPaths, CLI installer)
pip install -e ".[dev]"          # tous les outils de développement
```

### Installation via pip

```bash
# Depuis GitHub
pip install git+https://github.com/user/linux-python-utils.git

# Avec extras
pip install "git+https://github.com/user/linux-python-utils.git[credentials]"
pip install "git+https://github.com/user/linux-python-utils.git[validation,credentials]"
```

### Installation sans accès Git (copie directe)

```bash
# Sur la machine source : copier le répertoire du projet
scp -r linux-python-utils/ user@autrepc:~/

# Sur l'autre machine
cd linux-python-utils
python -m venv venv
source venv/bin/activate
pip install -e .
```

### Installation sur Fedora

Fedora protège le Python système — `sudo pip install` est à éviter. Trois approches propres :

**Par projet** (recommandé si la bibliothèque est utilisée dans un projet précis) :
```bash
cd mon-projet/
python -m venv .venv
source .venv/bin/activate
pip install git+https://github.com/user/linux-python-utils.git
```

**Niveau utilisateur** (disponible dans tous tes scripts sans activation de venv) :
```bash
pip install --user git+https://github.com/user/linux-python-utils.git
# Installé dans ~/.local/lib/python3.x/site-packages/
```

**venv dédié** (si la bibliothèque est partagée entre plusieurs scripts perso) :
```bash
python -m venv ~/.local/venvs/linux-python-utils
~/.local/venvs/linux-python-utils/bin/pip install git+https://github.com/user/linux-python-utils.git
```
Puis dans chaque script :
```python
#!/usr/bin/env ~/.local/venvs/linux-python-utils/bin/python
```

### Vérification de l'Installation

```python
import linux_python_utils
print(linux_python_utils.__version__)  # 1.6.0
```

## 🏗️ Architecture Globale

### Vue d'Ensemble

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│                              linux-python-utils  v1.5                            │
├──────────────────────────────────────────────────────────────────────────────────┤
│  MODULES                                                                         │
│                                                                                  │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ │
│  │ logging  │ │  config  │ │filesystem│ │ systemd  │ │integrity │ │ dotconf  │ │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘ └──────────┘ └──────────┘ │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ │
│  │ commands │ │ scripts  │ │validation│ │  errors  │ │credential│ │ network  │ │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘ └──────────┘ └──────────┘ │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐                                         │
│  │ identity │ │   cli    │ │notificat.│                                         │
│  └──────────┘ └──────────┘ └──────────┘                                         │
│                                                                                  │
├──────────────────────────────────────────────────────────────────────────────────┤
│  ABCs (contrats publics)                                                         │
│                                                                                  │
│  Logger · ConfigLoader · ConfigManager · ConfigFileLoader[T]                     │
│  FileManager · FileBackup · CommandExecutor · CommandFormatter                   │
│  ChecksumCalculator · IniSection · IniConfig · IniConfigManager                 │
│  Validator · ErrorHandler · CredentialProvider · CredentialStore                 │
│  NetworkScanner · DeviceRepository · DhcpReservationManager                     │
│  DnsManager · DeviceReporter · ScriptInstaller · ScriptChecker                  │
│  CliCommand · GroupManagerBase · UserManagerBase                                 │
│  UnitManager · ServiceUnitManager · TimerUnitManager · MountUnitManager          │
│  UserUnitManager · UserServiceUnitManager · UserTimerUnitManager                 │
│  ScheduledTaskInstaller                                                          │
│                                                                                  │
├──────────────────────────────────────────────────────────────────────────────────┤
│  Implémentations Linux concrètes                                                 │
│                                                                                  │
│  FileLogger · ConsoleLogger · SecurityLogger                                     │
│  ConfigurationManager · FileConfigLoader                                         │
│  LinuxFileManager · LinuxFileBackup                                              │
│  LinuxCommandExecutor · CommandBuilder · AnsiCommandFormatter                    │
│  HashLibChecksumCalculator · SHA256IntegrityChecker · IniSectionIntegrityChecker │
│  ValidatedSection · LinuxIniConfigManager · SectionAwareEditor                   │
│  PathCheckerPermission · PathCheckerWorldWritable                                │
│  ConsoleErrorHandler · LoggerErrorHandler · ErrorHandlerChain                    │
│  EnvCredentialProvider · DotEnvCredentialProvider · KeyringCredentialProvider    │
│  CredentialChain · CredentialManager                                             │
│  LinuxArpScanner · LinuxNmapScanner · JsonDeviceRepository                       │
│  LinuxDhcpReservationManager · LinuxHostsFileManager · LinuxDnsmasqConfigGen.    │
│  ConsoleTableReporter · CsvReporter · JsonReporter · DiffReporter                │
│  BashScriptInstaller · LinuxCliInstaller · LinuxScriptChecker                    │
│  LinuxGroupManager · LinuxUserManager                                            │
│  CliApplication · DryRunContext                                                  │
│  SystemdExecutor · LinuxServiceUnitManager · LinuxTimerUnitManager               │
│  LinuxMountUnitManager · LinuxUserServiceUnitManager · LinuxUserTimerUnitManager │
│  SystemdScheduledTaskInstaller                                                   │
└──────────────────────────────────────────────────────────────────────────────────┘
```

### Principes SOLID Appliqués

| Principe | Application |
|----------|-------------|
| **S** - Single Responsibility | `SystemdExecutor` (commandes) séparé de `UnitManager` (fichiers unit) |
| **O** - Open/Closed | ABCs stables, nouvelles implémentations sans modification |
| **L** - Liskov Substitution | Toutes les implémentations respectent leurs contrats ABC |
| **I** - Interface Segregation | `MountUnitManager`, `TimerUnitManager`, `ServiceUnitManager` séparés |
| **D** - Dependency Inversion | Injection de `Logger` et `SystemdExecutor` dans les managers |

### Injection de Dépendances

```python
# Toutes les classes acceptent des abstractions en injection
class LinuxMountUnitManager(MountUnitManager):
    def __init__(
        self,
        logger: Logger,           # ABC injectée
        executor: SystemdExecutor  # Executor injecté
    ): ...

# Facilite les tests avec des mocks
class MockLogger(Logger):
    def log_info(self, message): pass
    def log_warning(self, message): pass
    def log_error(self, message): pass

class MockExecutor(SystemdExecutor):
    def reload_systemd(self): return True
    def enable_unit(self, name): return True
    # ...

mount_mgr = LinuxMountUnitManager(MockLogger(), MockExecutor(MockLogger()))
```

## 🗂️ Structure du Projet

```
linux-python-utils/
├── src/linux_python_utils/
│   ├── __init__.py              # Exports publics
│   ├── logging/
│   │   ├── __init__.py
│   │   ├── base.py              # ABC Logger
│   │   ├── console_logger.py    # ConsoleLogger (stdout/stderr, sans fichier)
│   │   ├── file_logger.py       # FileLogger
│   │   └── security_logger.py   # SecurityLogger, SecurityEvent, SecurityEventType
│   ├── config/
│   │   ├── __init__.py
│   │   ├── base.py              # ABC ConfigManager
│   │   ├── loader.py            # ABC ConfigLoader + FileConfigLoader
│   │   └── manager.py           # ConfigurationManager
│   ├── filesystem/
│   │   ├── __init__.py
│   │   ├── base.py              # ABCs FileManager, FileBackup
│   │   ├── linux.py             # LinuxFileManager
│   │   └── backup.py            # LinuxFileBackup
│   ├── systemd/
│   │   ├── __init__.py          # Exports module systemd
│   │   ├── base.py              # ABCs + dataclasses (configs)
│   │   ├── executor.py          # SystemdExecutor, UserSystemdExecutor
│   │   ├── validators.py        # validate_unit_name(), validate_service_name()
│   │   ├── mount.py             # LinuxMountUnitManager
│   │   ├── timer.py             # LinuxTimerUnitManager
│   │   ├── service.py           # LinuxServiceUnitManager
│   │   ├── user_timer.py        # LinuxUserTimerUnitManager
│   │   ├── user_service.py      # LinuxUserServiceUnitManager
│   │   ├── scheduled_task.py    # SystemdScheduledTaskInstaller
│   │   └── config_loaders/      # Chargeurs de configuration (TOML/JSON)
│   │       ├── __init__.py
│   │       ├── base.py          # ConfigFileLoader[T] (ABC)
│   │       ├── service_loader.py # ServiceConfigLoader
│   │       ├── timer_loader.py  # TimerConfigLoader
│   │       ├── mount_loader.py  # MountConfigLoader
│   │       └── script_loader.py # BashScriptConfigLoader
│   ├── integrity/
│   │   ├── __init__.py
│   │   ├── base.py              # ABCs + calculate_checksum
│   │   └── sha256.py            # SHA256IntegrityChecker
│   ├── dotconf/
│   │   ├── __init__.py
│   │   ├── base.py              # ABCs IniSection, IniConfig, IniConfigManager
│   │   ├── section.py           # ValidatedSection + parse_validator, build_validators
│   │   ├── manager.py           # LinuxIniConfigManager
│   │   └── line_editor.py       # SectionAwareEditor (édition préservant commentaires)
│   ├── commands/
│   │   ├── __init__.py
│   │   ├── base.py              # CommandResult + ABC CommandExecutor
│   │   ├── builder.py           # CommandBuilder (API fluent)
│   │   ├── formatter.py         # CommandFormatter ABC + Plain + Ansi
│   │   └── runner.py            # LinuxCommandExecutor (subprocess)
│   ├── scripts/
│   │   ├── __init__.py
│   │   ├── config.py            # BashScriptConfig + PythonCliConfig
│   │   ├── installer.py         # ScriptInstaller, BashScriptInstaller, CliInstaller, LinuxCliInstaller
│   │   ├── paths.py             # ScriptPaths — chemins FHS via platformdirs
│   │   ├── checker.py           # ScriptChecker (ABC) + LinuxScriptChecker
│   │   └── report.py            # InstallReport + MissingDependency
│   ├── identity/
│   │   ├── __init__.py
│   │   ├── base.py              # ABCs GroupManagerBase, UserManagerBase
│   │   ├── group.py             # LinuxGroupManager (groupadd/groupmod)
│   │   └── user.py              # LinuxUserManager (useradd/usermod)
│   ├── notification/
│   │   ├── __init__.py
│   │   └── config.py            # NotificationConfig (dataclass)
│   ├── validation/
│   │   ├── __init__.py
│   │   ├── base.py                        # ABC Validator
│   │   ├── path_checker_Exist.py          # PathChecker
│   │   ├── path_checker_permission.py     # PathCheckerPermission
│   │   └── path_checker_world_writable.py # PathCheckerWorldWritable
│   ├── errors/
│   │   ├── __init__.py
│   │   ├── base.py              # ABC ErrorHandler + ErrorHandlerChain
│   │   ├── exceptions.py        # Hiérarchie ApplicationError
│   │   ├── console_handler.py   # ConsoleErrorHandler
│   │   ├── logger_handler.py    # LoggerErrorHandler
│   │   └── context.py           # ErrorContext
│   ├── credentials/
│   │   ├── __init__.py
│   │   ├── base.py              # ABCs CredentialProvider, CredentialStore
│   │   ├── chain.py             # CredentialChain
│   │   ├── manager.py           # CredentialManager (façade)
│   │   ├── models.py            # Credential, CredentialKey
│   │   ├── exceptions.py        # CredentialError et sous-classes
│   │   └── providers/
│   │       ├── __init__.py
│   │       ├── env.py           # EnvCredentialProvider
│   │       ├── dotenv.py        # DotEnvCredentialProvider
│   │       └── keyring.py       # KeyringCredentialProvider
│   ├── network/
│   │   ├── __init__.py
│   │   ├── base.py              # ABCs NetworkScanner, DeviceRepository, etc.
│   │   ├── models.py            # NetworkDevice
│   │   ├── config.py            # NetworkConfig, DhcpRange, DnsConfig
│   │   ├── scanner.py           # LinuxArpScanner, LinuxNmapScanner
│   │   ├── repository.py        # JsonDeviceRepository
│   │   ├── dhcp.py              # LinuxDhcpReservationManager
│   │   ├── dns.py               # LinuxHostsFileManager, LinuxDnsmasqConfigGenerator
│   │   ├── reporter.py          # ConsoleTableReporter, CsvReporter, etc.
│   │   ├── router.py            # AsusRouterClient, AsusRouterScanner, etc.
│   │   └── validators.py        # validate_ipv4, validate_mac, etc.
│   └── cli/
│       ├── __init__.py
│       ├── base.py              # CliCommand (ABC), CliApplication
│       └── dry_run.py           # DryRunContext, add_dry_run_argument
├── tests/
│   ├── __init__.py
│   ├── test_logging.py
│   ├── test_config.py
│   ├── test_config_validation.py
│   ├── test_integrity.py
│   ├── test_filesystem.py
│   ├── test_systemd_mount.py
│   ├── test_systemd_timer.py
│   ├── test_systemd_service.py
│   ├── test_systemd_executor.py
│   ├── test_systemd_validators.py
│   ├── test_systemd_scheduled_task.py
│   ├── test_systemd_config_loaders.py
│   ├── test_dotconf.py
│   ├── test_dotconf_line_editor.py
│   ├── test_commands.py
│   ├── test_scripts.py
│   ├── test_notification.py
│   ├── test_validation.py
│   ├── test_identity_group.py
│   ├── test_identity_user.py
│   ├── test_cli.py
│   └── test_cli_dry_run.py
├── examples/
│   └── nfs-mounts.toml              # Exemple de configuration
├── pyproject.toml
├── Makefile
├── CLAUDE.md
└── README.md
```

---

## 📝 Module `logging`

Système de logging robuste avec trois implémentations : fichier, console légère, et journalisation structurée des événements de sécurité.

### Utilisation

```python
from linux_python_utils import FileLogger, ConsoleLogger

# Logger fichier (UTF-8, flush immédiat)
logger = FileLogger("/var/log/myapp.log")
logger.log_info("Application démarrée")
logger.log_warning("Attention: ressource limitée")
logger.log_error("Erreur critique")
logger.log_success("Opération terminée")  # délègue à log_info par défaut

# Avec sortie console simultanée
logger = FileLogger("/var/log/myapp.log", console_output=True)

# Logger console uniquement (pas de fichier — dry-run, tests, scripts légers)
console = ConsoleLogger()
console.log_info("Démarrage...")      # → stdout
console.log_warning("Absent")        # → stderr : WARNING: Absent
console.log_error("Échec")           # → stderr : ERROR: Échec
```

#### `SecurityLogger` — Audit trail structuré JSON

Journalise les événements de sécurité en JSON structuré (SIEM-ready). Respecte le DIP : dépend de l'abstraction `Logger`, pas d'une implémentation concrète.

```python
from linux_python_utils.logging import (
    SecurityLogger,
    SecurityEvent,
    SecurityEventType,
)

# Initialisation avec n'importe quel Logger
sec_logger = SecurityLogger(logger)

# Journaliser une modification de configuration
sec_logger.log_event(SecurityEvent(
    event_type=SecurityEventType.CONFIG_CHANGE,
    resource="/etc/myapp/myapp.conf",
    details={
        "section": "main",
        "keys": ["timeout", "retries"],
        "backup": "/etc/myapp/myapp.conf.bak",
        "status": "appliqué",
    },
    severity="warning",
))

# Journaliser un accès refusé
sec_logger.log_event(SecurityEvent(
    event_type=SecurityEventType.ACCESS_DENIED,
    resource="/etc/shadow",
    details={"reason": "permission_denied"},
    severity="error",
    user_id="www-data",
))
```

Types d'événements disponibles (`SecurityEventType`) :

| Type | Valeur | Sévérité recommandée |
|------|--------|----------------------|
| `AUTH_SUCCESS` | `auth.success` | info |
| `AUTH_FAILURE` | `auth.failure` | warning |
| `AUTH_LOCKOUT` | `auth.lockout` | error |
| `ACCESS_DENIED` | `access.denied` | error |
| `ACCESS_ELEVATED` | `access.elevated` | warning |
| `DATA_EXPORT` | `data.export` | warning |
| `DATA_MODIFICATION` | `data.modification` | warning |
| `CONFIG_CHANGE` | `config.change` | warning |
| `RATE_LIMIT_HIT` | `rate_limit.hit` | warning |
| `SUSPICIOUS_ACTIVITY` | `suspicious.activity` | error |

#### `TeeStream` — Capturer stdout/stderr dans un fichier log

Inspiré de la commande Unix `tee` (raccord en T dans une tuyauterie) : tout ce
qui transite par un flux est envoyé **simultanément** vers deux destinations —
le terminal (affichage en temps réel) et un fichier log (trace persistante).

```
sys.stdout.write("hello")
        │
        ├──► terminal  (visible pendant l'exécution)
        └──► fichier   (trace consultable après coup)
```

> **`TeeStream` vs `FileLogger(console_output=True)` — quelle différence ?**
>
> `FileLogger(console_output=True)` ne capture que les messages qui passent
> explicitement par l'interface logger (`log_info`, `log_error`, etc.) :
>
> ```python
> logger.log_info("message")  # → fichier + console ✓
> print("résultat")           # → console seulement ✗  (pas dans le fichier)
> ```
>
> `TeeStream` capture **tout** ce qui passe par `sys.stdout` / `sys.stderr`,
> y compris les `print()`, les exceptions non catchées, et toute sortie directe :
>
> ```python
> logger.log_info("message")            # → fichier (FileLogger) + console ✓
> print("résultat")                     # → fichier (TeeStream)  + console ✓
> print("erreur", file=sys.stderr)      # → fichier (TeeStream)  + console ✓
> # traceback d'une exception           # → fichier (TeeStream)  + console ✓
> ```
>
> Les deux sont complémentaires : `FileLogger` pour les messages de log
> structurés, `TeeStream` pour capturer l'intégralité de ce que l'utilisateur
> voit à l'écran.

```python
import sys
from linux_python_utils.logging import TeeStream

log_fh = open("/var/log/myapp.log", "a", encoding="utf-8")
original_stdout, original_stderr = sys.stdout, sys.stderr

# Wrapper les deux flux APRÈS la création du FileLogger,
# pour que son StreamHandler garde une référence à l'stderr original
# et évite les doublons dans le fichier log.
sys.stdout = TeeStream(original_stdout, log_fh)
sys.stderr = TeeStream(original_stderr, log_fh)
try:
    ...  # tout print() et toute écriture stderr sont maintenant loggés
finally:
    sys.stdout = original_stdout
    sys.stderr = original_stderr
    log_fh.close()
```

### Documentation API

| ABC (Interface) | Implémentation | Description |
|-----------------|----------------|-------------|
| `Logger` | `FileLogger` | Logging fichier/console (UTF-8, flush immédiat) |
| `Logger` | `ConsoleLogger` | Logging stdout/stderr sans fichier (dry-run, tests) |
| — | `TeeStream` | Duplique stdout/stderr vers terminal ET fichier log |
| — | `SecurityLogger` | Journalisation structurée JSON des événements de sécurité |
| — | `SecurityEvent` | Dataclass représentant un événement de sécurité |
| — | `SecurityEventType` | Enum des 10 types d'événements de sécurité |

### Architecture des Classes

```
          ┌────────────────────────────────────────────┐
          │                Logger (ABC)                 │
          │  + log_info(message: str)    [abstract]     │
          │  + log_warning(message: str) [abstract]     │
          │  + log_error(message: str)   [abstract]     │
          │  + log_success(message: str) [→ log_info]   │
          └────────────────────┬───────────────────────┘
                               │ hérite
               ┌───────────────┴───────────────┐
               ▼                               ▼
  ┌────────────────────────┐   ┌───────────────────────────┐
  │     ConsoleLogger      │   │        FileLogger         │
  │                        │   │  - log_file: str          │
  │  log_info  → stdout    │   │  - config: dict | None    │
  │  log_warn  → stderr    │   │  - console_output: bool   │
  │  log_error → stderr    │   │  (UTF-8, flush immédiat)  │
  └────────────────────────┘   └───────────────────────────┘

  SecurityLogger  (composition — injecte Logger)
  ┌────────────────────────────────────────────────┐
  │  SecurityLogger                                │
  │  - _logger: Logger                             │
  │  + log_event(event_type, resource, details,    │
  │              severity, user_id) → JSON         │
  ├────────────────────────────────────────────────┤
  │  SecurityEventType (StrEnum)                   │
  │  AUTH_SUCCESS · AUTH_FAILURE · AUTH_LOCKOUT    │
  │  ACCESS_DENIED · ACCESS_ELEVATED               │
  │  DATA_EXPORT · DATA_MODIFICATION               │
  │  CONFIG_CHANGE · RATE_LIMIT_HIT                │
  │  SUSPICIOUS_ACTIVITY                           │
  ├────────────────────────────────────────────────┤
  │  SecurityEvent (frozen dataclass)              │
  │  - event_type / resource / details             │
  │  - severity / user_id / timestamp (UTC ISO)    │
  └────────────────────────────────────────────────┘
```

---

## 🚨 Module `errors`

Gestion centralisée des erreurs via une hiérarchie d'exceptions et une chaîne de handlers (pattern Chain of Responsibility).

### Utilisation

```python
from linux_python_utils.errors import (
    ApplicationError,
    ConfigurationError,
    ErrorHandlerChain,
    ConsoleErrorHandler,
    LoggerErrorHandler,
    ErrorContext,
)
from linux_python_utils import FileLogger

# Construire une chaîne de handlers
logger = FileLogger("/var/log/myapp.log")
chain = ErrorHandlerChain()
chain.add_handler(ConsoleErrorHandler())      # affiche sur stderr
chain.add_handler(LoggerErrorHandler(logger)) # logue dans le fichier

# Lever et capturer une erreur applicative
try:
    raise ConfigurationError("Clé 'timeout' manquante dans config.toml")
except ApplicationError as e:
    chain.handle(e)           # propagé aux deux handlers
    # ou :
    chain.handle_and_exit(e)  # propagé puis sys.exit(1)

# Hiérarchie des exceptions (toutes héritent de ApplicationError)
# ConfigurationError, FileConfigurationError
# SystemRequirementError, MissingDependencyError
# ValidationError, InstallationError
# AppPermissionError, RollbackError, IntegrityError
```

### Documentation API

| ABC (Interface) | Implémentation | Description |
|-----------------|----------------|-------------|
| `ErrorHandler` | `ConsoleErrorHandler` | Affiche les erreurs sur stderr |
| `ErrorHandler` | `LoggerErrorHandler` | Logue les erreurs via un `Logger` |
| — | `ErrorHandlerChain` | Diffuse l'erreur à tous les handlers enregistrés |
| — | `ErrorContext` | Contexte structuré attaché à une erreur |
| `ApplicationError` | `ConfigurationError` | Erreur de configuration |
| `ApplicationError` | `FileConfigurationError` | Erreur de fichier de configuration |
| `ApplicationError` | `SystemRequirementError` | Prérequis système absent |
| `ApplicationError` | `MissingDependencyError` | Dépendance Python manquante |
| `ApplicationError` | `ValidationError` | Échec de validation |
| `ApplicationError` | `InstallationError` | Erreur d'installation |
| `ApplicationError` | `AppPermissionError` | Permission refusée |
| `ApplicationError` | `RollbackError` | Échec du rollback |
| `ApplicationError` | `IntegrityError` | Violation d'intégrité |

### Architecture des Classes

```
  ┌────────────────────────────────────┐
  │         ErrorHandler (ABC)         │
  │  + handle(error: Exception)        │
  │    [abstract]                      │
  └──────────────┬─────────────────────┘
                 │ hérite
       ┌─────────┴─────────┐
       ▼                   ▼
┌──────────────┐   ┌───────────────┐
│ ConsoleError │   │ LoggerError   │
│   Handler    │   │   Handler     │
│  → stderr    │   │  - logger     │
└──────────────┘   └───────────────┘

  ┌────────────────────────────────────┐
  │         ErrorHandlerChain          │  ← pas un ABC : orchestrateur
  │  - handlers: list[ErrorHandler]    │
  │  + add_handler(h)                  │
  │  + handle(error) → tous handlers   │
  │  + handle_and_exit(error, code)    │
  └────────────────────────────────────┘

  Hiérarchie d'exceptions (errors/exceptions.py)
  Exception
  └── LinuxUtilsError
      ├── ConfigurationError
      ├── FilesystemError
      ├── CommandExecutionError
      ├── CredentialError
      │   ├── CredentialNotFoundError
      │   ├── CredentialProviderUnavailableError
      │   └── CredentialStoreError
      └── SystemdError
```

---

## ⚙️ Module `config`

Chargement et gestion de configuration TOML et JSON.

### Utilisation

#### Classe `FileConfigLoader`

```python
from linux_python_utils import FileConfigLoader

# Chargement TOML ou JSON (détection automatique)
loader = FileConfigLoader()
config = loader.load("/etc/myapp/config.toml")
print(config["section"]["key"])
```

#### Classe `ConfigurationManager`

```python
from linux_python_utils import ConfigurationManager

# Configuration par défaut avec profils
DEFAULT_CONFIG = {
    "logging": {"level": "INFO"},
    "backup": {"destination": "/media/backup"},
    "profiles": {
        "home": {"source": "~", "destination": "/media/backup/home"},
        "documents": {"source": "~/Documents", "destination": "/media/backup/docs"}
    }
}

# Chemins de recherche automatique
SEARCH_PATHS = [
    "~/.config/myapp/config.toml",
    "/etc/myapp/config.toml"
]

config = ConfigurationManager(
    default_config=DEFAULT_CONFIG,
    search_paths=SEARCH_PATHS
)

# Accès par chemin pointé
level = config.get("logging.level", "INFO")
dest = config.get("backup.destination")

# Gestion des profils
profiles = config.list_profiles()  # ["home", "documents"]
home_profile = config.get_profile("home")
# {"source": "/home/user", "destination": "/media/backup/home"}
```

**Fichier TOML exemple :**

```toml
[logging]
level = "DEBUG"

[backup]
destination = "/media/nas/backup"

[profiles.home]
source = "~"
destination = "/media/nas/backup/home"
```

### Documentation API

| ABC (Interface) | Implémentation | Description |
|-----------------|----------------|-------------|
| `ConfigManager` | `ConfigurationManager` | Gestion de configuration |
| `ConfigLoader` | `FileConfigLoader` | Chargement TOML/JSON |

### Architecture des Classes

```
  ┌──────────────────────────────────┐   ┌────────────────────────────────┐
  │        ConfigLoader (ABC)        │   │       ConfigManager (ABC)      │
  │  + load(path) [abstract]         │   │  + get(key)         [abstract] │
  └────────────┬─────────────────────┘   │  + get_section(key) [abstract] │
               │                         │  + get_profile(key) [abstract] │
               ▼                         │  + list_profiles()  [abstract] │
  ┌────────────────────────────────┐     │  + create_default_config()     │
  │       FileConfigLoader         │     └────────────────┬───────────────┘
  │  Supporte TOML + JSON          │                      │ hérite
  │  Validation Pydantic optionnelle│                     ▼
  └────────────────────────────────┘     ┌────────────────────────────────┐
                                         │     ConfigurationManager       │
  ┌────────────────────────────────┐     │  - _loader: ConfigLoader       │
  │    ConfigFileLoader[T] (ABC)   │     │  - default_config: dict        │
  │  Generic typé T (dataclass)    │     │  - search_paths: list[Path]    │
  │  - _config: dict               │     │  - config: dict                │
  │  + config (property)           │     │  + get(key, default)           │
  │  + _get_section(key)           │     │  + get_section(key)            │
  │  + _get_nested_value(key)      │     │  + get_profile(name)           │
  │  + load() [abstract]           │     │  + list_profiles()             │
  └──────────┬─────────────────────┘     │  + create_default_config()     │
             │ hérite                    │  + _deep_merge(base, override) │
  ┌──────────┴──────────┬──────────────┐ └────────────────────────────────┘
  ▼                     ▼              ▼
ServiceConfig   TimerConfig   MountConfig      ← loaders dans systemd/
Loader          Loader        Loader
BashScriptConfigLoader
```

---

## 🖥️ Module `commands`

Construction fluent et exécution de commandes système. Les commandes root et utilisateur sont distinguées visuellement dans les logs et la console.

### Utilisation

```python
from linux_python_utils import (
    FileLogger,
    CommandBuilder,
    LinuxCommandExecutor,
    AnsiCommandFormatter,
)

# Construire une commande avec l'API fluent
cmd = (
    CommandBuilder("rsync")
    .with_options(["-av", "--delete"])
    .with_option("--compress-level", "3")
    .with_flag("--stats")
    .with_args(["/src/", "/dest/"])
    .build()
)
# Résultat : ["rsync", "-av", "--delete",
#             "--compress-level=3", "--stats",
#             "/src/", "/dest/"]

# Exécuter — logs fichier avec préfixe [ROOT] ou [user]
logger = FileLogger("/var/log/commands.log")
executor = LinuxCommandExecutor(logger=logger)
result = executor.run(cmd)

print(result.success)           # True/False
print(result.return_code)       # 0
print(result.stdout)            # Sortie standard
print(result.duration)          # Durée en secondes
print(result.executed_as_root)  # True si lancé en root

# Console colorée (jaune gras=root, vert=user) + logs fichier
executor = LinuxCommandExecutor(
    logger=logger,
    console_formatter=AnsiCommandFormatter(),
)
# → fichier log : "[ROOT] Exécution : rsync -av ..."
# → console     : idem en jaune-or gras si root, vert si user

# Streaming temps réel vers le logger
result = executor.run_streaming(cmd)

# Mode dry-run (simulation sans exécution)
dry_executor = LinuxCommandExecutor(
    logger=logger, dry_run=True
)
result = dry_executor.run(cmd)  # Log "[user] [dry-run] ..." seulement

# Options conditionnelles
cmd = (
    CommandBuilder("rsync")
    .with_options(["-av"])
    .with_option_if("--bwlimit", "1000", condition=True)
    .with_option_if("--exclude", None)  # Ignoré (None)
    .with_args(["/src/", "/dest/"])
    .build()
)
```

### Documentation API

| ABC (Interface) | Implémentation | Description |
|-----------------|----------------|-------------|
| `CommandExecutor` | `LinuxCommandExecutor` | Exécution subprocess |
| — | `CommandBuilder` | Construction fluent de commandes |
| `CommandFormatter` | `PlainCommandFormatter` | Formatage texte brut (logs fichier) |
| `CommandFormatter` | `AnsiCommandFormatter` | Formatage ANSI coloré (console) |

**Dataclass `CommandResult`** (frozen) :

| Champ | Type | Description |
|-------|------|-------------|
| `command` | `list[str]` | Commande exécutée |
| `return_code` | `int` | Code de retour |
| `stdout` | `str` | Sortie standard |
| `stderr` | `str` | Sortie d'erreur |
| `success` | `bool` | True si return_code == 0 |
| `duration` | `float` | Durée en secondes |
| `executed_as_root` | `bool` | True si lancé en root |

### Architecture des Classes

```
  ┌──────────────────────────────────────────────────────────┐
  │                  CommandResult (frozen dataclass)        │
  │  command: list[str]  │  return_code: int  │  stdout: str │
  │  stderr: str  │  success: bool  │  duration: float       │
  │  executed_as_root: bool                                  │
  └──────────────────────────────────────────────────────────┘

  ┌───────────────────────────────┐
  │      CommandBuilder           │
  │  - _program: str              │
  │  + with_options(dict)         │  ← Builder Pattern (fluent API)
  │  + with_flag(flag, cond)      │
  │  + with_option(key, value)    │
  │  + with_option_if(k, v, cond) │
  │  + with_args(args)            │
  │  + build() → list[str]        │
  └───────────────────────────────┘

  ┌───────────────────────────────┐    ┌─────────────────────────────────┐
  │    CommandFormatter (ABC)     │    │      CommandExecutor (ABC)      │
  │  + format_start()  [abstract] │    │  + run(cmd, env, cwd, timeout)  │
  │  + format_dry_run()[abstract] │    │    [abstract] → CommandResult   │
  │  + format_line()   [abstract] │    │  + run_streaming(cmd, ...)      │
  └──────────────┬────────────────┘    │    [abstract]                   │
                 │ hérite              └──────────────┬──────────────────┘
     ┌───────────┴───────────┐                        │ hérite
     ▼                       ▼                        ▼
PlainCommand         AnsiCommand         ┌─────────────────────────────────┐
Formatter            Formatter           │      LinuxCommandExecutor       │
(texte brut)         (ANSI couleurs,     │  - logger: Logger               │
                      TTY-aware)         │  - _dry_run: bool               │
                                         │  - _is_root: bool               │
                                         │  - _console_formatter           │
                                         │  + run(cmd) → CommandResult     │
                                         │  + run_streaming(cmd)           │
                                         │  + _build_env()                 │
                                         │  + _make_dry_run_result()       │
                                         └─────────────────────────────────┘
```

---

## 📁 Module `filesystem`

Opérations sur les fichiers et sauvegardes.

### Utilisation

```python
from linux_python_utils import FileLogger, LinuxFileManager, LinuxFileBackup

logger = FileLogger("/var/log/myapp.log")

# Gestion de fichiers
fm = LinuxFileManager(logger)
fm.create_file("/tmp/test.txt", "Contenu du fichier")

if fm.file_exists("/tmp/test.txt"):
    content = fm.read_file("/tmp/test.txt")
    print(content)

fm.delete_file("/tmp/test.txt")

# Sauvegarde avec préservation des métadonnées
backup = LinuxFileBackup(logger)
backup.backup("/etc/myapp.conf", "/etc/myapp.conf.bak")
# ... modifications ...
backup.restore("/etc/myapp.conf", "/etc/myapp.conf.bak")
```

### Documentation API

| ABC (Interface) | Implémentation | Description |
|-----------------|----------------|-------------|
| `FileManager` | `LinuxFileManager` | CRUD fichiers |
| `FileBackup` | `LinuxFileBackup` | Sauvegarde/restauration |

### Architecture des Classes

```
  ┌─────────────────────────────────┐    ┌──────────────────────────────────┐
  │       FileManager (ABC)         │    │        FileBackup (ABC)          │
  │  + create_file()  [abstract]    │    │  + backup(src, dst)  [abstract]  │
  │  + file_exists()  [abstract]    │    │  + restore(bak, dst) [abstract]  │
  └────────────────┬────────────────┘    └─────────────────┬────────────────┘
                   │ hérite                                 │ hérite
                   ▼                                        ▼
  ┌─────────────────────────────────┐    ┌──────────────────────────────────┐
  │      LinuxFileManager           │    │       LinuxFileBackup            │
  │  - logger: Logger               │    │  - logger: Logger                │
  │  + create_file(path, content)   │    │  + backup(src, dst)              │
  │  + file_exists(path)            │    │    (shutil.copy2 — préserve      │
  │  + read_file(path)              │    │     métadonnées)                 │
  │  (TOCTOU-safe: O_NOFOLLOW)      │    │  + restore(bak, dst)             │
  └─────────────────────────────────┘    └──────────────────────────────────┘
```

---

## 🔧 Module `systemd`

Gestion complète des unités systemd : services, timers et montages, en mode système (root) ou utilisateur.

### Utilisation

#### Architecture de haut niveau

```
┌─────────────────────┐          ┌─────────────────────┐
│   SystemdExecutor   │          │ UserSystemdExecutor │
│  systemctl          │          │  systemctl --user   │
│  /etc/systemd/system│          │  ~/.config/systemd/ │
└─────────┬───────────┘          └─────────┬───────────┘
          │                                │
    ┌─────┼─────┐                    ┌─────┼─────┐
    ▼     ▼     ▼                    ▼           ▼
 Mount  Timer Service          UserTimer   UserService
 UnitMgr UnitMgr UnitMgr       UnitMgr     UnitMgr
```

#### Unités Système (requiert root)

##### Unités de Montage (.mount / .automount)

```python
from linux_python_utils import (
    FileLogger,
    SystemdExecutor,
    LinuxMountUnitManager,
    MountConfig
)

logger = FileLogger("/var/log/mount.log")
executor = SystemdExecutor(logger)
mount_mgr = LinuxMountUnitManager(logger, executor)

# Configuration du montage NFS
config = MountConfig(
    description="NAS Backup",
    what="192.168.1.10:/share",
    where="/media/nas/backup",
    type="nfs",
    options="defaults,soft,timeo=10"
)

# Installer avec automount (montage à la demande)
mount_mgr.install_mount_unit(config, with_automount=True, automount_timeout=60)

# Activer le montage
mount_mgr.enable_mount("/media/nas/backup", with_automount=True)

# Vérifier le statut
if mount_mgr.is_mounted("/media/nas/backup"):
    print("Montage actif")

# Désactiver et supprimer
mount_mgr.disable_mount("/media/nas/backup")
mount_mgr.remove_mount_unit("/media/nas/backup")
```

##### Timers Système

```python
from linux_python_utils import (
    FileLogger,
    SystemdExecutor,
    LinuxTimerUnitManager,
    TimerConfig
)

logger = FileLogger("/var/log/timer.log")
executor = SystemdExecutor(logger)
timer_mgr = LinuxTimerUnitManager(logger, executor)

# Configuration du timer
config = TimerConfig(
    description="Backup quotidien",
    unit="backup.service",
    on_calendar="*-*-* 02:00:00",  # Tous les jours à 2h
    persistent=True,  # Rattraper les exécutions manquées
    randomized_delay_sec="1h"
)

# Installer et activer
timer_mgr.install_timer_unit(config)
timer_mgr.enable_timer("backup")

# Lister les timers actifs
timers = timer_mgr.list_timers()
for t in timers:
    print(f"{t['unit']}: prochaine exécution {t['next']}")
```

##### Services Système

```python
from linux_python_utils import (
    FileLogger,
    SystemdExecutor,
    LinuxServiceUnitManager,
    ServiceConfig
)

logger = FileLogger("/var/log/service.log")
executor = SystemdExecutor(logger)
service_mgr = LinuxServiceUnitManager(logger, executor)

# Configuration du service
config = ServiceConfig(
    description="Mon application web",
    exec_start="/usr/bin/python /opt/myapp/app.py",
    type="simple",
    user="www-data",
    working_directory="/opt/myapp",
    restart="on-failure",
    restart_sec=5,
    environment={"PYTHONPATH": "/opt/myapp"}
)

# Installer avec un nom spécifique
service_mgr.install_service_unit_with_name("myapp", config)

# Contrôler le service
service_mgr.enable_service("myapp")
service_mgr.start_service("myapp")

if service_mgr.is_service_active("myapp"):
    print("Service actif")

service_mgr.restart_service("myapp")
service_mgr.stop_service("myapp")
```

#### Unités Utilisateur (sans root)

Les unités utilisateur sont stockées dans `~/.config/systemd/user/` et ne nécessitent pas de privilèges root.

##### Timers Utilisateur

```python
from linux_python_utils import (
    FileLogger,
    UserSystemdExecutor,
    LinuxUserTimerUnitManager,
    TimerConfig
)

logger = FileLogger("~/.local/log/timer.log")
executor = UserSystemdExecutor(logger)
timer_mgr = LinuxUserTimerUnitManager(logger, executor)

# Timer pour synchroniser des fichiers toutes les heures
config = TimerConfig(
    description="Sync fichiers",
    unit="sync.service",
    on_calendar="hourly",
    persistent=True
)

timer_mgr.install_timer_unit(config)
timer_mgr.enable_timer("sync")
```

##### Services Utilisateur

```python
from linux_python_utils import (
    FileLogger,
    UserSystemdExecutor,
    LinuxUserServiceUnitManager,
    ServiceConfig
)

logger = FileLogger("~/.local/log/service.log")
executor = UserSystemdExecutor(logger)
service_mgr = LinuxUserServiceUnitManager(logger, executor)

# Service de synchronisation
config = ServiceConfig(
    description="Synchronisation Dropbox",
    exec_start="/home/user/.local/bin/sync.sh",
    type="oneshot",
    working_directory="/home/user"
)

service_mgr.install_service_unit_with_name("sync", config)
service_mgr.enable_service("sync")
```

#### Module `systemd.config_loaders`

Chargeurs de configuration pour créer des dataclasses systemd depuis TOML ou JSON.
Le format est automatiquement détecté par l'extension du fichier.

```python
from linux_python_utils.systemd.config_loaders import (
    ServiceConfigLoader,
    TimerConfigLoader,
    MountConfigLoader,
    BashScriptConfigLoader,
)

# Charger un ServiceConfig depuis TOML ou JSON
service_loader = ServiceConfigLoader("config/app.toml")  # ou .json
service_config = service_loader.load()
print(service_config.description)

# Charger un TimerConfig pour un service spécifique
timer_loader = TimerConfigLoader("config/app.toml")
timer_config = timer_loader.load_for_service("my-service")
print(timer_config.unit)  # "my-service.service"

# Charger un BashScriptConfig avec notifications
script_loader = BashScriptConfigLoader("config/app.toml")
script_config = script_loader.load()
if script_config.notification:
    print("Notifications activées")

# Charger plusieurs montages depuis une liste TOML
mount_loader = MountConfigLoader("config/mounts.toml")
mounts = mount_loader.load_multiple("mounts")  # [[mounts]] dans TOML
for mount in mounts:
    print(f"{mount.what} → {mount.where}")
```

**Fichier TOML exemple :**

```toml
[service]
description = "Mon service"
exec_start = "/usr/bin/mon-app"
type = "oneshot"

[timer]
description = "Timer quotidien"
unit = "mon-service.service"
on_calendar = "daily"
persistent = true

[notification]
enabled = true
title = "Mon App"
message_success = "Succès!"
message_failure = "Échec!"
```

### Documentation API

| ABC (Interface) | Implémentation | Description |
|-----------------|----------------|-------------|
| — | `SystemdExecutor` | Exécuteur systemctl (système) |
| — | `UserSystemdExecutor` | Exécuteur systemctl --user |
| `MountUnitManager` | `LinuxMountUnitManager` | Unités .mount/.automount |
| `TimerUnitManager` | `LinuxTimerUnitManager` | Unités .timer (système) |
| `ServiceUnitManager` | `LinuxServiceUnitManager` | Unités .service (système) |
| `UserTimerUnitManager` | `LinuxUserTimerUnitManager` | Unités .timer (utilisateur) |
| `UserServiceUnitManager` | `LinuxUserServiceUnitManager` | Unités .service (utilisateur) |
| `ScheduledTaskInstaller` | `SystemdScheduledTaskInstaller` | Installation tâche planifiée complète |

**`systemd.config_loaders`** :

| ABC (Interface) | Implémentation | Description |
|-----------------|----------------|-------------|
| `ConfigFileLoader[T]` | — | Classe de base générique (TOML/JSON) |
| — | `ServiceConfigLoader` | Config → ServiceConfig |
| — | `TimerConfigLoader` | Config → TimerConfig |
| — | `MountConfigLoader` | Config → MountConfig |
| — | `BashScriptConfigLoader` | Config → BashScriptConfig |

**Dataclasses** :

| Classe | Description |
|--------|-------------|
| `MountConfig` | Configuration d'une unité .mount |
| `AutomountConfig` | Configuration d'une unité .automount |
| `TimerConfig` | Configuration d'une unité .timer |
| `ServiceConfig` | Configuration d'une unité .service |

### Architecture des Classes

```
                    ┌─────────────────────────────────────────────┐
                    │              SystemdExecutor                 │
                    │  - _run_systemctl(args)                     │
                    │  - reload_systemd()                         │
                    │  - enable_unit() / disable_unit()           │
                    │  - start_unit() / stop_unit()               │
                    │  - get_status() / is_active()               │
                    └─────────────────────┬───────────────────────┘
                                          │ hérite
                                          ▼
                    ┌─────────────────────────────────────────────┐
                    │            UserSystemdExecutor              │
                    │  surcharge _run_systemctl pour --user       │
                    └─────────────────────┬───────────────────────┘
                                          │
                                          │ injection
        ┌─────────────────────────────────┼─────────────────────────────────┐
        │                                 │                                 │
        ▼                                 ▼                                 ▼
┌───────────────────┐           ┌───────────────────┐           ┌───────────────────┐
│    UnitManager    │           │  UserUnitManager  │           │  (autres futurs)  │
│ /etc/systemd/sys  │           │ ~/.config/systemd │           │                   │
├───────────────────┤           ├───────────────────┤           └───────────────────┘
│ LinuxMountUnitMgr │           │ LinuxUserTimerMgr │
│ LinuxTimerUnitMgr │           │ LinuxUserServiceMgr│
│ LinuxServiceUnitMgr│          └───────────────────┘
└───────────────────┘
```

---

## 📜 Module `scripts`

Génération de scripts bash et déploiement de scripts Python CLI sur le système de fichiers (FHS, scope système ou utilisateur, rapport d'installation).

### Utilisation

#### Scripts bash

```python
from linux_python_utils import BashScriptConfig, BashScriptInstaller

config = BashScriptConfig(
    name="backup",
    description="Script de sauvegarde quotidien",
    commands=["rsync -av /src /dest", "echo 'Done'"],
    notification=None  # Ou NotificationConfig
)

# Générer le contenu du script
print(config.to_bash_script())

# Installer le script sur le système
installer = BashScriptInstaller(logger)
installer.install(config, "/usr/local/bin/backup.sh")
```

#### Déploiement de scripts Python CLI

Nécessite `pip install linux-python-utils[deploy]` (platformdirs) et `uv` installé sur le système.

```python
from linux_python_utils import (
    FileLogger,
    LinuxCommandExecutor,
    PythonCliConfig,
    LinuxCliInstaller,
    ScriptPaths,
    LinuxScriptChecker,
)
from pathlib import Path

logger = FileLogger("/var/log/deploy.log")
executor = LinuxCommandExecutor(logger)

# Résolution des chemins FHS (système ou utilisateur)
paths = ScriptPaths(scope="user")  # ou "system"
print(paths.data_dir)     # ~/.local/share/
print(paths.scripts_dir)  # ~/.local/share/mon-script/

# Configuration du déploiement
config = PythonCliConfig(
    name="mon-outil",
    source_dir=Path("/home/user/projects/mon-outil"),
    scope="user",   # "user" ou "system"
)

# Vérifications pré-installation (python3, pyproject.toml, dépendances)
checker = LinuxScriptChecker(logger)
report = checker.check(config)
if not report.success:
    for dep in report.missing_deps:
        print(f"Manquant: {dep.name} — {dep.remedy}")

# Installation via uv tool install
installer = LinuxCliInstaller(logger, executor)
report = installer.install(config)

print(report.success)        # True/False
print(report.install_path)   # Chemin d'installation
print(report.missing_deps)   # Dépendances manquantes éventuelles
```

### Documentation API

| ABC (Interface) | Implémentation | Description |
|-----------------|----------------|-------------|
| `ScriptInstaller` | `BashScriptInstaller` | Installation de scripts bash |
| `CliInstaller` | `LinuxCliInstaller` | Déploiement CLI via `uv tool install` |
| `ScriptChecker` | `LinuxScriptChecker` | Vérifications pré-installation (python3, pyproject.toml, dépendances) |
| — | `ScriptPaths` | Résolution chemins FHS via platformdirs (système/utilisateur) |
| — | `PythonCliConfig` | Configuration de déploiement d'un script Python CLI |
| — | `InstallReport` | Rapport complet du déploiement |
| — | `MissingDependency` | Dépendance manquante avec commande de remédiation |

**Dataclasses** :

| Classe | Description |
|--------|-------------|
| `BashScriptConfig` | Configuration d'un script bash |
| `PythonCliConfig` | Configuration de déploiement d'un script Python CLI |
| `InstallReport` | Rapport de déploiement (succès, chemin, dépendances manquantes) |
| `MissingDependency` | Dépendance manquante avec commande de remédiation |

### Architecture des Classes

```
  ┌─────────────────────────────────────────┐
  │           ScriptInstaller (ABC)         │
  │  + install(path, config) [abstract]     │
  └───────────────┬─────────────────────────┘
                  │ hérite
       ┌──────────┴──────────┐
       ▼                     ▼
┌──────────────────┐  ┌────────────────────────────────────┐
│ BashScriptInstall│  │          CliInstaller (ABC)        │
│  - logger        │  │  + install(config) [abstract]      │
│  - file_manager  │  └──────────────────┬─────────────────┘
│  + install(path, │                     │ hérite
│    config)→ bool │                     ▼
└──────────────────┘  ┌────────────────────────────────────┐
                       │         LinuxCliInstaller          │
                       │  - logger: Logger                  │
                       │  - checker: ScriptChecker          │
                       │  + install(config) → InstallReport │
                       │  (FHS, uv, scope sys/user)         │
                       └────────────────────────────────────┘

  ┌─────────────────────────────────────────┐
  │           ScriptChecker (ABC)           │
  │  + check(config) [abstract]             │
  └───────────────┬─────────────────────────┘
                  │ hérite
                  ▼
  ┌─────────────────────────────────────────┐
  │          LinuxScriptChecker             │
  │  + check(config) → list[MissingDep]    │
  └─────────────────────────────────────────┘

  BashScriptConfig (frozen dataclass)
  ┌──────────────────────────────────────────────┐
  │  - exec_command: str                         │
  │  - notification: NotificationConfig | None   │
  │  + to_bash_script() → str                    │
  └──────────────────────────────────────────────┘

  PythonCliConfig (dataclass)
  ┌──────────────────────────────────────────────┐
  │  - name: str                                 │
  │  - deploy_type: "user" | "system"            │
  │  - source_dir: Path                          │
  └──────────────────────────────────────────────┘

  InstallReport + MissingDependency (rapport d'installation)
  ScriptPaths   (utilitaires de chemins FHS)
```

---

## 🌐 Module `network`

Scan, inventaire et gestion des périphériques d'un réseau local.

### Utilisation

```python
from linux_python_utils import (
    LinuxArpScanner,
    JsonDeviceRepository,
    ConsoleTableReporter,
    NetworkConfig,
)
from pathlib import Path

config = NetworkConfig(interface="eth0", subnet="192.168.1.0/24")

# Scanner le réseau
scanner = LinuxArpScanner(config)
devices = scanner.scan()

# Persister l'inventaire
repo = JsonDeviceRepository(Path("/var/lib/myapp/devices.json"))
repo.save_all(devices)

# Afficher un tableau
reporter = ConsoleTableReporter()
reporter.report(devices)
```

Scanners disponibles : `LinuxArpScanner` (arp-scan), `LinuxNmapScanner` (nmap).

Reporters disponibles : `ConsoleTableReporter`, `CsvReporter`, `JsonReporter`, `DiffReporter`.

DNS/DHCP : `LinuxHostsFileManager`, `LinuxDnsmasqConfigGenerator`, `LinuxDhcpReservationManager`.

Validateurs : `validate_ipv4`, `validate_mac`, `validate_cidr`, `validate_hostname`.

### Documentation API

| ABC (Interface) | Implémentation | Description |
|-----------------|----------------|-------------|
| `NetworkScanner` | `LinuxArpScanner` | Scan réseau via arp-scan |
| `NetworkScanner` | `LinuxNmapScanner` | Scan réseau via nmap |
| `DeviceRepository` | `JsonDeviceRepository` | Persistance JSON de l'inventaire |
| `DhcpReservationManager` | `LinuxDhcpReservationManager` | Réservations DHCP |
| `DnsManager` | `LinuxHostsFileManager` | Gestion `/etc/hosts` |
| `DnsManager` | `LinuxDnsmasqConfigGenerator` | Génération config dnsmasq |
| `DeviceReporter` | `ConsoleTableReporter` | Tableau ASCII |
| `DeviceReporter` | `CsvReporter` | Export CSV |
| `DeviceReporter` | `JsonReporter` | Export JSON |
| `DeviceReporter` | `DiffReporter` | Diff entre deux inventaires |

### Architecture des Classes

```
  ┌──────────────────────────────────────┐
  │        NetworkScanner (ABC)          │
  │  + scan(config) → list[NetworkDevice]│
  └──────────────┬───────────────────────┘
                 │ hérite
      ┌──────────┴──────────┐
      ▼                     ▼
┌──────────────┐    ┌───────────────┐
│LinuxArpScanner│   │LinuxNmapScanner│
│  (arp-scan)  │   │    (nmap)      │
└──────────────┘    └───────────────┘

  ┌──────────────────────────────────────┐
  │       DeviceRepository (ABC)        │
  │  + load() → list[NetworkDevice]     │
  │  + save(devices)                    │
  │  + find_by_mac(mac)                 │
  │  + find_by_ip(ip)                   │
  └──────────────┬───────────────────────┘
                 │ hérite
                 ▼
  ┌──────────────────────────────────────┐
  │         JsonDeviceRepository         │
  │  (persistance JSON)                  │
  └──────────────────────────────────────┘

  ┌─────────────────────────────────┐   ┌───────────────────────────────────┐
  │  DhcpReservationManager (ABC)   │   │          DnsManager (ABC)         │
  │  + generate_reservations()      │   │  + add_entry() / remove_entry()   │
  └────────────────┬────────────────┘   └─────────────────┬─────────────────┘
                   │ hérite                               │ hérite
                   ▼                          ┌───────────┴────────────┐
  ┌──────────────────────────────┐            ▼                        ▼
  │  LinuxDhcpReservationManager │  ┌────────────────────┐  ┌─────────────────────────┐
  └──────────────────────────────┘  │LinuxHostsFileManager│  │LinuxDnsmasqConfigGen.   │
                                    └────────────────────┘  └─────────────────────────┘

  ┌─────────────────────────────────────────────────────┐
  │              DeviceReporter (ABC)                   │
  │  + report(devices) [abstract]                       │
  └───────────────────────────┬─────────────────────────┘
                              │ hérite
        ┌──────────┬──────────┼──────────┐
        ▼          ▼          ▼          ▼
ConsoleTable    Csv       Json        Diff
Reporter        Reporter  Reporter    Reporter

  NetworkDevice (frozen dataclass)
  ┌──────────────────────────────────────────┐
  │  ip · mac · hostname · vendor            │
  │  device_type · is_known · fixed_ip       │
  │  dns_name · first_seen · last_seen       │
  │  notes                                   │
  │  + to_dict() / from_dict() [classmethod] │
  └──────────────────────────────────────────┘

  AsusRouterClient  ← client HTTP dédié au routeur ASUS
```

---

## 👤 Module `identity`

Gestion idempotente des groupes et utilisateurs Unix. Les opérations sont sans effet si l'état souhaité est déjà en place.

### Utilisation

```python
from linux_python_utils import (
    FileLogger,
    LinuxCommandExecutor,
    LinuxGroupManager,
    LinuxUserManager,
)

logger = FileLogger("/var/log/identity.log")
executor = LinuxCommandExecutor(logger)

# Groupes — crée ou corrige le GID
group_mgr = LinuxGroupManager(executor, logger)
group_mgr.ensure_group("appuser", gid=1500)
# → groupadd si absent, groupmod --gid si GID incorrect, skip sinon

# Utilisateurs — crée ou corrige l'UID
user_mgr = LinuxUserManager(executor, logger)
user_mgr.ensure_user(
    name="appuser",
    uid=1500,
    shell="/sbin/nologin",
    comment="Application service account",
    create_home=False,
)
# → useradd si absent, usermod --uid si UID incorrect, skip sinon

# Groupes secondaires — ajoute uniquement les manquants
user_mgr.ensure_user_groups(
    username="appuser",
    groups=["docker", "systemd-journal"],
)
# → usermod --append --groups docker,systemd-journal (uniquement les absents)
```

### Documentation API

| ABC (Interface) | Implémentation | Description |
|-----------------|----------------|-------------|
| `GroupManagerBase` | `LinuxGroupManager` | Création/correction idempotente de groupes Unix |
| `UserManagerBase` | `LinuxUserManager` | Création/correction idempotente d'utilisateurs Unix |

### Architecture des Classes

```
  ┌─────────────────────────────────────────┐
  │         GroupManagerBase (ABC)          │
  │  + ensure_group(name, gid) [abstract]   │
  │    (idempotent : crée ou corrige GID)   │
  └───────────────────┬─────────────────────┘
                      │ hérite
                      ▼
  ┌─────────────────────────────────────────┐
  │          LinuxGroupManager              │
  │  - logger: Logger                       │
  │  - executor: CommandExecutor            │
  │  + ensure_group(name, gid)              │
  │    (groupadd / groupmod)                │
  └─────────────────────────────────────────┘

  ┌─────────────────────────────────────────────────┐
  │           UserManagerBase (ABC)                 │
  │  + ensure_user(name, uid, shell,                │
  │      comment, create_home) [abstract]           │
  │  + ensure_user_groups(name, groups) [abstract]  │
  └────────────────────┬────────────────────────────┘
                       │ hérite
                       ▼
  ┌─────────────────────────────────────────────────┐
  │            LinuxUserManager                     │
  │  - logger: Logger                               │
  │  - executor: CommandExecutor                    │
  │  + ensure_user(name, uid, shell, ...)           │
  │    (useradd / usermod — idempotent)             │
  │  + ensure_user_groups(name, groups)             │
  │    (usermod --append --groups ...)              │
  └─────────────────────────────────────────────────┘
```

---

## 🖱️ Module `cli`

Framework CLI minimal basé sur le Command Pattern. Permet de structurer une application argparse en sous-commandes SOLID.

Inclut également un support dry-run réutilisable : `add_dry_run_argument` enregistre `--dry-run` / `-n` de façon standardisée, et `DryRunContext` affiche les actions simulées sans écrire sur le disque.

### Utilisation

```python
import argparse
from typing import Any
from linux_python_utils.cli import (
    CliCommand,
    CliApplication,
    DryRunContext,
    add_dry_run_argument,
)

class SyncCommand(CliCommand):
    @property
    def name(self) -> str:
        return "sync"

    def register(self, subparsers: Any) -> None:
        p = subparsers.add_parser(self.name, help="Synchronise les données")
        add_dry_run_argument(p)  # ajoute --dry-run / -n

    def execute(self, args: argparse.Namespace) -> None:
        ctx = DryRunContext(dry_run=args.dry_run)
        if ctx.dry_run:
            ctx.would_write("/etc/app/config", "key=value")
        else:
            print("sync exécuté")

class ListCommand(CliCommand):
    @property
    def name(self) -> str:
        return "list"

    def register(self, subparsers: Any) -> None:
        subparsers.add_parser(self.name, help="Liste les éléments")

    def execute(self, args: argparse.Namespace) -> None:
        print("list exécuté")

app = CliApplication(
    prog="mon-outil",
    description="Mon outil CLI",
    commands=[SyncCommand(), ListCommand()],
)
app.run()  # parse sys.argv et dispatche
```

### Documentation API

| ABC (Interface) | Implémentation | Description |
|-----------------|----------------|-------------|
| `CliCommand` | — (à implémenter) | Interface pour une sous-commande CLI |
| — | `CliApplication` | Orchestrateur CLI (Command Pattern + argparse) |
| — | `DryRunContext` | Contexte d'exécution simulée (affichage sans écriture disque) |
| — | `add_dry_run_argument` | Enregistre `--dry-run` / `-n` dans un ArgumentParser |

### Architecture des Classes

```
  ┌────────────────────────────────────────────────┐
  │               CliCommand (ABC)                 │
  │  + name: str              [property abstract]  │
  │  + register(subparsers)   [abstract]           │
  │  + execute(args: Namespace) [abstract]         │
  └────────────────────────────────────────────────┘
             ↑ implémentée par les commandes métier

  ┌────────────────────────────────────────────────┐
  │              CliApplication                    │
  │  - _prog: str                                  │
  │  - _description: str                           │
  │  - _commands: list[CliCommand]                 │
  │  + run() → dispatch vers la commande choisie   │
  └────────────────────────────────────────────────┘

  ┌────────────────────────────────────────────────┐
  │              DryRunContext                     │
  │  - dry_run: bool                               │
  │  + would_write() → bool                        │
  │  + would_create() → bool                       │
  │  + would_modify() → bool                       │
  └────────────────────────────────────────────────┘

  add_dry_run_argument(parser)
  └── ajoute --dry-run à un ArgumentParser argparse
```

---

## 📋 Module `dotconf`

Gestion de fichiers de configuration INI (.conf) avec validation externe.

### Utilisation

```python
from dataclasses import dataclass
from pathlib import Path
from linux_python_utils import (
    FileLogger,
    ValidatedSection,
    LinuxIniConfigManager,
)

# Définir une section avec validation
@dataclass(frozen=True)
class CommandsSection(ValidatedSection):
    upgrade_type: str = "default"
    download_updates: str = "yes"

    @staticmethod
    def section_name() -> str:
        return "commands"

# Injecter les validateurs depuis le TOML
CommandsSection.set_validators({
    "upgrade_type": ["default", "security"],
    "download_updates": ["yes", "no"],
})

# Créer et écrire une section
section = CommandsSection(
    upgrade_type="security", download_updates="yes"
)

logger = FileLogger("/var/log/config.log")
manager = LinuxIniConfigManager(logger)

# Écrire une section dans un fichier
manager.write_section(Path("/etc/myapp.conf"), section)

# Lire un fichier INI complet
config = manager.read(Path("/etc/myapp.conf"))
print(config["commands"]["upgrade_type"])  # "security"

# Mise à jour conditionnelle (n'écrit que si changé)
updated = manager.update_section(
    Path("/etc/myapp.conf"), section
)
print(f"Modifié: {updated}")
```

#### `SectionAwareEditor` — Édition ligne-à-ligne préservant les commentaires

Permet de modifier une clé dans un fichier INI sans toucher les commentaires ni la mise en forme existante.

```python
from linux_python_utils import SectionAwareEditor

editor = SectionAwareEditor(Path("/etc/myapp.conf"))

# Modifier une valeur dans une section existante
editor.set_value("commands", "upgrade_type", "security")

# Vérifier qu'une clé est présente
if editor.has_key("commands", "download_updates"):
    print("Clé présente")
```

### Documentation API

| ABC (Interface) | Implémentation | Description |
|-----------------|----------------|-------------|
| `IniSection` | `ValidatedSection` | Section INI avec validation externe |
| `IniConfig` | — | Fichier INI complet |
| `IniConfigManager` | `LinuxIniConfigManager` | Gestion lecture/écriture INI |
| — | `SectionAwareEditor` | Édition ligne-à-ligne préservant les commentaires |
| — | `parse_validator` | Convertit un validateur brut en callable/liste |
| — | `build_validators` | Construit un dictionnaire de validateurs |

**Dataclass** :

| Classe | Description |
|--------|-------------|
| `ValidatedSection` | Section INI avec validation externe |

### Architecture des Classes

```
  ┌─────────────────────────────────┐   ┌────────────────────────────────────┐
  │        IniSection (ABC)         │   │          IniConfig (ABC)           │
  │  + section_name() [static abs.] │   │  + sections() [abstract]           │
  │  + to_dict() → dict [abstract]  │   │  + to_ini() → str [abstract]       │
  │  + from_dict(d) [cls abstract]  │   │  + from_file(path) [cls abstract]  │
  └────────────┬────────────────────┘   └─────────────────────────────────── ┘
               │ hérite
               ▼
  ┌─────────────────────────────────┐
  │         ValidatedSection        │
  │  Dataclass avec validation      │
  │  __post_init__ des champs       │
  └─────────────────────────────────┘

  ┌──────────────────────────────────────────────────┐
  │            IniConfigManager (ABC)                │
  │  + read(path) → IniConfig   [abstract]           │
  │  + write(config, path)      [abstract]           │
  └────────────────────┬─────────────────────────────┘
                       │ hérite
                       ▼
  ┌──────────────────────────────────────────────────┐
  │           LinuxIniConfigManager                  │
  │  (configparser stdlib)                           │
  │  + read(path) → IniConfig                        │
  │  + write(config, path)                           │
  └──────────────────────────────────────────────────┘

  ┌──────────────────────────────────────────────────┐
  │             SectionAwareEditor                   │
  │  Édition ligne-à-ligne préservant les            │
  │  commentaires et la structure du fichier         │
  │  + update_key(section, key, value)               │
  │  + add_section(section)                          │
  │  + remove_key(section, key)                      │
  └──────────────────────────────────────────────────┘
```

---

## 🔐 Module `integrity`

Vérification d'intégrité par checksums, et ABC pour la vérification de sections INI.

### Utilisation

```python
from linux_python_utils import FileLogger, SHA256IntegrityChecker, calculate_checksum

# Fonction utilitaire rapide
checksum = calculate_checksum("/path/to/file")  # SHA256 par défaut
checksum_md5 = calculate_checksum("/path/to/file", algorithm="md5")

# Vérificateur avec logging
logger = FileLogger("/var/log/backup.log")
checker = SHA256IntegrityChecker(logger)

# Vérifier un fichier unique
if checker.verify_file("/source/file.txt", "/dest/file.txt"):
    print("Fichier identique")

# Vérifier un répertoire complet (après rsync)
if checker.verify("/home/user/Documents", "/media/backup"):
    print("Sauvegarde vérifiée")
else:
    print("Erreur d'intégrité!")

# Obtenir le checksum avec logging
checksum = checker.get_checksum("/path/to/file")
```

#### `IniSectionIntegrityChecker` — ABC pour fichiers INI

Contrat abstrait pour implémenter la vérification d'intégrité d'une section INI après écriture.

```python
from pathlib import Path
from linux_python_utils.integrity import IniSectionIntegrityChecker

class MyIniChecker(IniSectionIntegrityChecker):
    def verify(self, file_path: Path, section: object) -> bool:
        """Vérifie que file_path contient les valeurs attendues de section."""
        # ... lecture du fichier et comparaison
        return True

checker = MyIniChecker()
if not checker.verify(Path("/etc/myapp.conf"), my_section):
    raise RuntimeError("Intégrité compromise!")
```

### Documentation API

| ABC (Interface) | Implémentation | Description |
|-----------------|----------------|-------------|
| `IntegrityChecker` | `SHA256IntegrityChecker` | Vérification checksums fichiers/répertoires |
| `ChecksumCalculator` | `HashLibChecksumCalculator` | Calcul checksums |
| `IniSectionIntegrityChecker` | — (ABC à implémenter) | Vérification post-écriture de sections INI |

### Architecture des Classes

```
  ┌────────────────────────────────────────────┐
  │         ChecksumCalculator (ABC)           │
  │  + calculate(file_path, algorithm='sha256')│
  │    → str (hex)  [abstract]                 │
  └───────────────────┬────────────────────────┘
                      │ hérite
                      ▼
  ┌────────────────────────────────────────────┐
  │       HashLibChecksumCalculator            │
  │  (hashlib — sha256, sha512, md5...)        │
  └────────────────────────────────────────────┘

  ┌──────────────────────────────────────────────────┐
  │            SHA256IntegrityChecker                │
  │  - _calculator: ChecksumCalculator               │
  │  + check_file(path, expected) → bool             │
  │  + check_directory(path, manifest) → dict        │
  │  + generate_manifest(path) → dict                │
  └──────────────────────────────────────────────────┘

  ┌──────────────────────────────────────────────────┐
  │            IniSectionIntegrityChecker            │
  │  + compute_section_hash(section) → str           │
  │  + verify_section(section, expected) → bool      │
  └──────────────────────────────────────────────────┘
```

---

## 🔑 Module `credentials`

Gestion des secrets via une chaîne de priorité : variables d'environnement → fichier `.env` → keyring système.

### Utilisation

```python
from linux_python_utils import CredentialManager, CredentialNotFoundError
from pathlib import Path

# Chaîne complète : env → .env → keyring
manager = CredentialManager.from_dotenv(
    service="monapp",
    dotenv_path=Path("config/.env"),
)

# Lire un secret
try:
    password = manager.get("DB_PASSWORD")
except CredentialNotFoundError:
    print("Secret introuvable dans les trois sources")

# Stocker dans le keyring
manager.store("DB_PASSWORD", "nouveau-mot-de-passe")
```

Compatibilité keyring : KWallet (KDE Plasma 6), KeePassXC (Secret Service activé), GNOME Keyring.

Dépendances optionnelles :
```bash
pip install python-dotenv  # pour DotEnvCredentialProvider
pip install keyring        # pour KeyringCredentialProvider
```

### Documentation API

| ABC (Interface) | Implémentation | Description |
|-----------------|----------------|-------------|
| `CredentialProvider` | `EnvCredentialProvider` | Secrets depuis variables d'environnement |
| `CredentialProvider` | `DotEnvCredentialProvider` | Secrets depuis fichier `.env` |
| `CredentialProvider` | `KeyringCredentialProvider` | Secrets depuis keyring système |
| `CredentialStore` | — | Interface d'écriture de secrets |
| — | `CredentialChain` | Chaîne de priorité entre providers |
| — | `CredentialManager` | Façade (lecture + écriture) |

### Architecture des Classes

```
  ┌──────────────────────────────────────┐
  │       CredentialProvider (ABC)       │  ← lecture seule (ISP)
  │  + get(service, key) → str | None    │
  │  + is_available() → bool [abstract]  │
  │  + source_name: str   [property]     │
  └──────────────┬───────────────────────┘
                 │ hérite
     ┌───────────┼───────────────────────────────────┐
     ▼           ▼                    ▼               ▼
┌──────────┐ ┌───────────────┐ ┌──────────────┐ ┌──────────────────────┐
│   Env    │ │    DotEnv     │ │   Keyring    │ │   CredentialChain    │
│Credential│ │  Credential   │ │  Credential  │ │  (Chain of Resp.)    │
│ Provider │ │   Provider    │ │   Provider   │ │  - _providers: list  │
│ (environ)│ │  (.env file)  │ │ (KWallet...) │ │  + get(svc, key)     │
└──────────┘ └───────────────┘ └──────┬───────┘ │  + default()classm. │
                                       │         │    env→dotenv→keyring│
  CredentialStore (ABC)                │ aussi   └──────────────────────┘
  ┌─────────────────────────────┐      │ hérite
  │  étend CredentialProvider   │      │
  │  + set(svc, key, value)     │◄─────┘
  │  + delete(svc, key)         │
  └─────────────────────────────┘

  ┌─────────────────────────────────────────┐
  │           CredentialManager             │  ← Facade
  │  - _service: str                        │
  │  - _chain: CredentialChain              │
  │  - _store: CredentialStore | None       │
  │  + get(key) → str | None                │
  │  + require(key) → str                   │
  │  + store(key, value)                    │
  │  + delete(key)                          │
  │  + from_dotenv(svc, path) [classmethod] │
  └─────────────────────────────────────────┘

  CredentialKey (frozen dc): service + key
  Credential   (frozen dc): service + key + value + source
```

---

## ✅ Module `validation`

Validation de chemins et données avec support optionnel Pydantic.

Trois validateurs de chemins couvrent des besoins distincts :

| Classe | Vérifie | Usage typique |
|--------|---------|---------------|
| `PathChecker` | Répertoires parents existent | Log files, config files |
| `PathCheckerPermission` | Répertoires parents accessibles en écriture | Backup, sauvegardes |
| `PathCheckerWorldWritable` | Fichiers non modifiables par tous | Scripts exécutés en root |

### Utilisation

```python
from linux_python_utils import PathChecker, PathCheckerPermission, PathCheckerWorldWritable

# Vérifie que les répertoires parents existent
checker = PathChecker([
    "/var/log/myapp.log",
    "/etc/myapp/config.toml",
])
checker.validate()  # Lève ValueError si répertoire absent

# Vérifie les droits d'écriture sur les répertoires parents
perm_checker = PathCheckerPermission([
    "/var/log/myapp.log",
    "/tmp/backup.tar.gz",
])
perm_checker.validate()  # Lève PermissionError si non accessible

# Vérifie qu'un fichier de config n'est pas world-writable
# (sécurité essentielle pour les scripts exécutés en root)
ww_checker = PathCheckerWorldWritable("/etc/myapp/config.toml")
ww_checker.validate()  # Lève PermissionError si bit S_IWOTH positionné

# Validation de configuration avec Pydantic (optionnel)
# pip install linux-python-utils[validation]
from pydantic import BaseModel
from linux_python_utils import FileConfigLoader

class AppConfig(BaseModel):
    name: str
    debug: bool = False
    port: int = 8080

loader = FileConfigLoader()
config = loader.load("config.toml", schema=AppConfig)
print(config.name)  # Instance AppConfig validée
```

### Documentation API

| ABC (Interface) | Implémentation | Description |
|-----------------|----------------|-------------|
| `Validator` | `PathChecker` | Répertoires parents existent |
| `Validator` | `PathCheckerPermission` | Répertoires parents accessibles en écriture |
| `Validator` | `PathCheckerWorldWritable` | Fichier non world-writable (sécurité root) |

### Architecture des Classes

```
  ┌──────────────────────────────────────────────────────┐
  │                   Validator (ABC)                    │
  │  + validate() [abstract]                             │
  │    raises: ValueError | PermissionError              │
  └───────────────────────────┬──────────────────────────┘
                              │ hérite
                              ▼
  ┌──────────────────────────────────────────────────────┐
  │                    PathChecker                       │
  │  - path: Path                                        │
  │  + validate()  [abstract]                            │
  └──────────┬────────────────────────┬──────────────────┘
             │ hérite                 │ hérite
             ▼                        ▼
  ┌──────────────────────┐  ┌──────────────────────────────┐
  │  PathCheckerPermission│  │  PathCheckerWorldWritable    │
  │  - expected: int      │  │  Avertit si world-writable   │
  │  + validate()         │  │  + validate()                │
  └──────────────────────┘  └──────────────────────────────┘
```

---

## 🔔 Module `notification`

Configuration des notifications desktop (KDE Plasma).

### Utilisation

```python
from linux_python_utils import NotificationConfig

# Configuration de notification
notif = NotificationConfig(
    enabled=True,
    title="Sauvegarde",
    message_success="Sauvegarde terminée avec succès",
    message_failure="Échec de la sauvegarde"
)

# Générer les appels bash pour notify-send
bash_calls = notif.to_bash_calls()
bash_function = notif.to_bash_function()
```

### Documentation API

| Classe | Description |
|--------|-------------|
| `NotificationConfig` | Dataclass de configuration des notifications desktop (KDE Plasma) |

---

## 🎯 Exemple Complet

Script de sauvegarde utilisant plusieurs modules ensemble :

```python
#!/usr/bin/env python3
from linux_python_utils import (
    FileLogger,
    ConfigurationManager,
    LinuxFileBackup,
    SHA256IntegrityChecker,
    UserSystemdExecutor,
    LinuxUserTimerUnitManager,
    LinuxUserServiceUnitManager,
    TimerConfig,
    ServiceConfig
)

# Configuration
DEFAULT_CONFIG = {
    "logging": {"level": "INFO"},
    "profiles": {
        "documents": {
            "source": "~/Documents",
            "destination": "/media/backup/docs"
        }
    }
}

config = ConfigurationManager(
    config_path="~/.config/backup/config.toml",
    default_config=DEFAULT_CONFIG
)

# Initialisation
logger = FileLogger("~/.local/log/backup.log", config=config, console_output=True)
executor = UserSystemdExecutor(logger)

# Créer le service de backup
service_mgr = LinuxUserServiceUnitManager(logger, executor)
service_config = ServiceConfig(
    description="Sauvegarde documents",
    exec_start="/home/user/scripts/backup.sh",
    type="oneshot"
)
service_mgr.install_service_unit_with_name("backup", service_config)

# Créer le timer (tous les jours à 6h)
timer_mgr = LinuxUserTimerUnitManager(logger, executor)
timer_config = TimerConfig(
    description="Timer backup quotidien",
    unit="backup.service",
    on_calendar="*-*-* 06:00:00",
    persistent=True
)
timer_mgr.install_timer_unit(timer_config)
timer_mgr.enable_timer("backup")

logger.log_info("Backup automatique configuré")
```

---

## 🧪 Tests

### Lancer les Tests

```bash
# Afficher les commandes disponibles
make help

# Lancer tous les tests
make test

# Lancer les tests en mode verbose
make test-verbose

# Lancer un test spécifique
pytest tests/test_logging.py::TestFileLogger::test_log_info -v

# Vérifier PEP8
make lint

# Tout lancer (lint + tests + build)
make all
```

### Résumé des Tests

| Module | Tests | Description |
|--------|-------|-------------|
| `test_logging.py` | 8 | FileLogger, UTF-8, configuration |
| `test_config.py` | 13 | Chargement TOML/JSON, profils, fusion |
| `test_config_validation.py` | 11 | Validation Pydantic optionnelle |
| `test_integrity.py` | 11 | Checksums, vérification fichiers/répertoires |
| `test_systemd_mount.py` | 36 | Génération .mount/.automount, validation, enable/disable |
| `test_systemd_timer.py` | 23 | TimerConfig, to_unit_file(), list_timers JSON/texte |
| `test_systemd_service.py` | 41 | ServiceConfig, validation type/restart/env, TOCTOU, LSP |
| `test_systemd_executor.py` | 9 | Validation noms d'unités dans SystemdExecutor |
| `test_systemd_validators.py` | 25 | validate_unit_name(), validate_service_name() |
| `test_systemd_scheduled_task.py` | 12 | SystemdScheduledTaskInstaller |
| `test_systemd_config_loaders.py` | 30 | Tous les loaders (TOML/JSON) |
| `test_dotconf.py` | 20 | Sections INI, validation, lecture/écriture |
| `test_dotconf_line_editor.py` | — | SectionAwareEditor, édition préservant commentaires |
| `test_commands.py` | 74 | CommandBuilder, formatters, exécution, streaming, dry-run, root/user |
| `test_scripts.py` | 19 | BashScriptConfig, installation scripts |
| `test_notification.py` | 13 | NotificationConfig, génération bash |
| `test_validation.py` | 5 | PathChecker, PathCheckerPermission, PathCheckerWorldWritable |
| `test_identity_group.py` | — | LinuxGroupManager, ensure_group (create/correct/skip) |
| `test_identity_user.py` | — | LinuxUserManager, ensure_user, ensure_user_groups |
| `test_cli.py` | 15 | CliCommand (ABC, register, execute, sous-classes partielles), CliApplication (dispatch, flags, args, edge cases) |
| `test_cli_dry_run.py` | 9 | DryRunContext (would_write/create/modify), add_dry_run_argument (--dry-run, -n) |
| **Total** | **498+** | |

### Tests Paramétrés

```python
@pytest.mark.parametrize("path,expected", [
    ("/media/nas", "media-nas"),
    ("/media/nas/backup/daily", "media-nas-backup-daily"),
    ("/mnt", "mnt"),
])
def test_path_conversion(path, expected):
    assert mount_mgr.path_to_unit_name(path) == expected
```

## 🐛 Troubleshooting

<details>
<summary><b>❌ ModuleNotFoundError: No module named 'linux_python_utils'</b></summary>

**Cause :** Package non installé ou environnement virtuel non activé.

**Solution :**
```bash
# Vérifier l'environnement virtuel
which python

# Réinstaller
pip install -e .
```
</details>

<details>
<summary><b>❌ ModuleNotFoundError: No module named 'tomllib'</b></summary>

**Cause :** Version Python < 3.11.

**Solution :**
```bash
# Vérifier la version
python --version

# Installer Python 3.11+
# Ubuntu/Debian
sudo apt install python3.11

# Fedora
sudo dnf install python3.11
```
</details>

<details>
<summary><b>❌ PermissionError lors de l'écriture des fichiers .mount/.timer/.service</b></summary>

**Cause :** Les fichiers systemd système nécessitent des droits root.

**Solution :**
```bash
# Exécuter avec sudo pour les unités système
sudo python mon_script.py

# Ou utiliser les classes User* pour les unités utilisateur (sans root)
from linux_python_utils import UserSystemdExecutor, LinuxUserTimerUnitManager
```
</details>

<details>
<summary><b>❌ Failed to connect to bus: No such file or directory (systemctl --user)</b></summary>

**Cause :** Le bus D-Bus utilisateur n'est pas disponible (session non graphique).

**Solution :**
```bash
# Activer le lingering pour l'utilisateur
sudo loginctl enable-linger $USER

# Ou définir XDG_RUNTIME_DIR
export XDG_RUNTIME_DIR=/run/user/$(id -u)
```
</details>

<details>
<summary><b>❌ FileNotFoundError pour le fichier de configuration</b></summary>

**Cause :** Le fichier de configuration n'existe pas aux chemins spécifiés.

**Solution :**
```python
# Utiliser search_paths avec un fallback
config = ConfigurationManager(
    default_config=DEFAULT_CONFIG,  # Toujours fournir des défauts
    search_paths=["~/.config/app/config.toml"]
)

# Ou créer le fichier par défaut
config.create_default_config("~/.config/app/config.toml")
```
</details>

## 🤝 Contribution

Les contributions sont les bienvenues !

### Processus

1. **Fork** le projet
2. **Créer** une branche (`git checkout -b feature/amazing-feature`)
3. **Commiter** (`git commit -m 'Add amazing feature'`)
4. **Pusher** (`git push origin feature/amazing-feature`)
5. **Ouvrir** une Pull Request

### Guidelines

- Suivre PEP 8 (max 79 caractères par ligne)
- Docstrings en français (PEP 257)
- Type hints requis (PEP 484)
- Respecter l'architecture SOLID existante
- Ajouter des tests pour les nouvelles fonctionnalités

### Développement Local

```bash
# Installer les dépendances de dev
make install-dev

# Vérifier le style
make lint

# Lancer les tests
make test

# Build complet
make all
```

## 📄 Licence

Ce projet est sous licence MIT. Voir le fichier [LICENSE](LICENSE) pour plus de détails.

---

<p align="center">
  <b>linux-python-utils</b> — Conçu avec les principes SOLID pour une extensibilité maximale
</p>

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

- **📝 Logging robuste** — `FileLogger` (fichier + console, UTF-8), `RotatingFileLogger` (rotation par taille, TOCTOU-safe), `ConsoleLogger` (stdout/stderr sans fichier), `SecurityLogger` (JSON structuré pour audit trail), `build_logger` (factory pilotée par config TOML)
- **⚙️ Configuration flexible** — Support TOML/JSON avec fusion profonde et profils
- **📁 Gestion de fichiers** — CRUD fichiers et sauvegardes TOCTOU-safe, copie récursive sécurisée (`copytree_secure`)
- **🔧 Systemd complet** — Gestion services, timers et unités de montage (système et utilisateur)
- **📄 Chargeurs de config** — Loaders typés pour créer des dataclasses depuis TOML ou JSON
- **🔐 Vérification d'intégrité** — Checksums SHA256/SHA512/MD5 pour fichiers et répertoires
- **🖥️ Exécution de commandes** — Construction fluent et exécution avec streaming temps réel
- **📋 Fichiers INI (.conf)** — Lecture, écriture et validation de fichiers de configuration INI ; `SectionAwareEditor` pour l'édition ligne-à-ligne préservant les commentaires
- **📝 Application déclarative de config** — `TomlSpecLoader` + `ConfigApplier` : décrire les blocs à appliquer dans un TOML `[target]`, les appliquer sur n'importe quel `.conf` (ajout, décommentage, idempotence garantie)
- **📜 Scripts bash et CLI** — Génération de scripts bash + déploiement de scripts Python CLI (FHS, uv, scope système/utilisateur, rapport d'installation)
- **👤 Gestion d'identités Unix** — Création idempotente de groupes (`groupadd`/`groupmod`) et utilisateurs (`useradd`/`usermod`) avec vérification GID/UID
- **🔔 Notifications** — Configuration de notifications desktop via `notify-send` (spec freedesktop.org — GNOME, KDE Plasma, XFCE...)
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
git clone https://github.com/user/linuxtools.git
cd linuxtools

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
pip install git+https://github.com/user/linuxtools.git

# Avec extras
pip install "git+https://github.com/user/linuxtools.git[credentials]"
pip install "git+https://github.com/user/linuxtools.git[validation,credentials]"
```

### Installation sans accès Git (copie directe)

```bash
# Sur la machine source : copier le répertoire du projet
scp -r linuxtools/ user@autrepc:~/

# Sur l'autre machine
cd linuxtools
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
pip install git+https://github.com/user/linuxtools.git
```

**Niveau utilisateur** (disponible dans tous tes scripts sans activation de venv) :
```bash
pip install --user git+https://github.com/user/linuxtools.git
# Installé dans ~/.local/lib/python3.x/site-packages/
```

**venv dédié** (si la bibliothèque est partagée entre plusieurs scripts perso) :
```bash
python -m venv ~/.local/venvs/linuxtools
~/.local/venvs/linuxtools/bin/pip install git+https://github.com/user/linuxtools.git
```
Puis dans chaque script :
```python
#!/usr/bin/env ~/.local/venvs/linuxtools/bin/python
```

### Vérification de l'Installation

```python
import linuxtools
print(linuxtools.__version__)  # 1.6.0
```

## 🏗️ Architecture Globale

### Vue d'Ensemble

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│                              linuxtools  v1.5                            │
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
│  ConfigBlock · ConfigSpec · TomlSpecLoader · ConfigApplier                       │
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
│  SystemdUnitExporter · SystemdUnitRestorer                                       │
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
linuxtools/
├── src/linuxtools/
│   ├── __init__.py              # Exports publics
│   ├── logging/
│   │   ├── __init__.py
│   │   ├── base.py                  # ABC Logger
│   │   ├── ansi_colors.py           # AnsiColors (StrEnum)
│   │   ├── console_logger.py        # ConsoleLogger (stdout/stderr, sans fichier)
│   │   ├── file_logger.py           # FileLogger (TOCTOU-safe, O_NOFOLLOW/0o600)
│   │   ├── rotating_file_logger.py  # RotatingFileLogger (rotation par taille)
│   │   ├── factory.py               # build_logger() — factory pilotée par config
│   │   ├── security_logger.py       # SecurityLogger, SecurityEvent, SecurityEventType
│   │   └── tee_stream.py            # TeeStream (duplication flux, pattern tee Unix)
│   ├── config/
│   │   ├── __init__.py
│   │   ├── base.py              # ABC ConfigManager
│   │   ├── loader.py            # ABC ConfigLoader + FileConfigLoader
│   │   └── manager.py           # ConfigurationManager
│   ├── filesystem/
│   │   ├── __init__.py
│   │   ├── base.py              # ABC FileManager
│   │   ├── linux.py             # LinuxFileManager, write_text_secure
│   │   └── backup.py            # FileBackup, LinuxFileBackup, copytree_secure
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
│   │   ├── unit_porter.py       # SystemdUnitExporter, SystemdUnitRestorer
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
│   │   ├── line_editor.py       # SectionAwareEditor (édition préservant commentaires)
│   │   ├── spec.py              # ConfigBlock, ConfigSpec (modèles de données purs)
│   │   ├── toml_spec_loader.py  # TomlSpecLoader (TOML → ConfigSpec, résolution ~/$VAR)
│   │   └── applier.py           # ConfigApplier (applique ConfigSpec via SectionAwareEditor)
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
│   │   ├── path_checker_exist.py          # PathChecker
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
│   ├── test_systemd_unit_porter.py
│   ├── test_dotconf.py
│   ├── test_dotconf_line_editor.py
│   ├── test_dotconf_spec.py
│   ├── test_dotconf_toml_spec_loader.py
│   ├── test_dotconf_applier.py
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

Système de logging robuste avec quatre implémentations (`FileLogger`, `RotatingFileLogger`, `ConsoleLogger`, `SecurityLogger`), une factory pilotée par config TOML (`build_logger`) et un utilitaire de duplication de flux (`TeeStream`).

### Utilisation

```python
from linuxtools import FileLogger, ConsoleLogger

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

#### `RotatingFileLogger` — Rotation automatique par taille

Même API que `FileLogger`, avec rotation automatique quand le fichier dépasse `max_bytes`. Chaque nouveau fichier (post-rotation inclus) est ouvert via `O_NOFOLLOW | 0o600` — protection TOCTOU préservée.

```python
from linuxtools.logging import RotatingFileLogger

logger = RotatingFileLogger(
    "/var/log/myapp/run.log",
    max_bytes=5_242_880,   # 5 Mo — défaut : 10 Mo
    backup_count=3,        # archives : run.log.1, run.log.2, run.log.3
)
logger.log_info("démarrage")
logger.log_success("sauvegarde terminée")
```

#### `build_logger` — Factory pilotée par config TOML

Instancie le bon logger depuis la section `[logging]` d'un fichier TOML (ou un dict équivalent). Découple le code appelant des classes concrètes.

```toml
# app.toml
[logging]
type = "rotating"
file = "/var/log/myapp/run.log"
level = "WARNING"
max_bytes = 5242880
backup_count = 3
console_output = true
```

```python
from linuxtools.config import ConfigurationManager
from linuxtools.logging import build_logger

cfg = ConfigurationManager("app.toml")
logger = build_logger(cfg.get_section("logging"))
logger.log_info("démarrage")  # → FileLogger, RotatingFileLogger ou ConsoleLogger
```

Types supportés : `"file"` | `"console"` | `"rotating"` (défaut : `"console"`).

#### `SecurityLogger` — Audit trail structuré JSON

Journalise les événements de sécurité en JSON structuré (SIEM-ready). Respecte le DIP : dépend de l'abstraction `Logger`, pas d'une implémentation concrète.

```python
from linuxtools.logging import (
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
from linuxtools.logging import TeeStream

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
| `Logger` | `FileLogger` | Logging fichier/console (UTF-8, flush immédiat, O_NOFOLLOW) |
| `Logger` | `RotatingFileLogger` | Rotation par taille (`max_bytes`), TOCTOU-safe post-rotation |
| `Logger` | `ConsoleLogger` | Logging stdout/stderr sans fichier (dry-run, tests) |
| — | `build_logger` | Factory — instancie le bon Logger depuis la section `[logging]` |
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
          ┌────────────────────┼───────────────────────┐
          ▼                    ▼                        ▼
  ┌──────────────┐  ┌──────────────────┐  ┌────────────────────────┐
  │ConsoleLogger │  │   FileLogger     │  │ RotatingFileLogger     │
  │              │  │ - log_file: Path │  │ - log_file: Path       │
  │ log_info  →  │  │ - config         │  │ - max_bytes: int       │
  │   stdout     │  │ - console_output │  │ - backup_count: int    │
  │ log_warn  →  │  │ O_NOFOLLOW/0o600 │  │ O_NOFOLLOW post-rotate │
  │   stderr     │  │ flush immédiat   │  │ flush immédiat         │
  └──────────────┘  └──────────────────┘  └────────────────────────┘

  build_logger(config: dict) -> Logger    (factory — factory.py)
  ┌────────────────────────────────────────────────┐
  │  config["type"] == "console"  → ConsoleLogger  │
  │  config["type"] == "file"     → FileLogger     │
  │  config["type"] == "rotating" → RotatingFile…  │
  └────────────────────────────────────────────────┘

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
from linuxtools.errors import (
    ApplicationError,
    ConfigurationError,
    ErrorHandlerChain,
    ConsoleErrorHandler,
    LoggerErrorHandler,
    ErrorContext,
)
from linuxtools import FileLogger

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
| `ApplicationError` | `CommandExecutionError` | Commande système avec code non nul |

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
  │  - _handlers: list[ErrorHandler]   │
  │  + add_handler(h)                  │
  │  + handle(error) → best-effort     │
  │    (chaque handler isolé par       │
  │     try/except, fallback stderr)   │
  │  + handle_and_exit(error, code)    │
  └────────────────────────────────────┘

  Hiérarchie d'exceptions (errors/exceptions.py + credentials/exceptions.py)
  Exception
  └── ApplicationError
      ├── ConfigurationError
      │   └── FileConfigurationError
      ├── SystemRequirementError
      │   └── MissingDependencyError
      ├── ValidationError
      ├── InstallationError
      ├── AppPermissionError
      ├── RollbackError
      ├── IntegrityError
      ├── CommandExecutionError
      └── CredentialError            (définie dans credentials/exceptions.py)
          ├── CredentialNotFoundError
          ├── CredentialStoreError
          └── CredentialProviderUnavailableError
```

---

## ⚙️ Module `config`

Chargement et gestion de configuration TOML et JSON.

### Utilisation

#### Classe `FileConfigLoader`

```python
from linuxtools import FileConfigLoader

# Chargement TOML ou JSON (détection automatique)
loader = FileConfigLoader()
config = loader.load("/etc/myapp/config.toml")
print(config["section"]["key"])
```

#### Classe `ConfigurationManager`

```python
from linuxtools import ConfigurationManager

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

**Pattern recommandé — XdgAppConfig + ConfigurationManager :**

```python
from linuxtools import ConfigurationManager, XdgAppConfig

DEFAULT_CONFIG = {
    "logging": {"level": "INFO"},
    "backup": {"destination": "/media/backup"},
}

xdg = XdgAppConfig("mon-appli")

# Crée ~/.config/mon-appli/global.toml s'il n'existe pas
# (tomllib = lecture seule — écriture déléguée à ConfigurationManager)
if not xdg.find_config_file():
    cfg_init = ConfigurationManager(default_config=DEFAULT_CONFIG)
    cfg_init.create_default_config(xdg.config_dir / "global.toml")

# Cascade XDG : ~/.config/mon-appli/global.toml → /etc/mon-appli/global.toml
cfg = ConfigurationManager(
    default_config=DEFAULT_CONFIG,
    search_paths=[
        xdg.find_config_file() or xdg.config_dir / "global.toml",
        xdg.system_config_dir / "global.toml",
    ],
)
level = cfg.get("logging.level", "INFO")
```

### Documentation API

| ABC (Interface) | Implémentation | Description |
|-----------------|----------------|-------------|
| `ConfigManager` | `ConfigurationManager` | Gestion de configuration, profils, `.validate()` Pydantic |
| `ConfigLoader` | `FileConfigLoader` | Chargement TOML/JSON, validation Pydantic optionnelle |
| — | `XdgAppConfig` | Résolution de chemins XDG Base Directory |

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
             │ hérite                    │  + validate(schema) → T        │
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
from linuxtools import (
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
# Commande à fort débit stderr : merge_stderr élimine le risque de deadlock
result = executor.run_streaming(cmd, merge_stderr=True)

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
| `command` | `tuple[str, ...]` | Commande exécutée (convertie en tuple par `__post_init__` pour l'immutabilité) |
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
  │  command: tuple[str,...]│ return_code: int │ stdout: str │
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
  │  + format_start()             │    │  + run(cmd, env, cwd, timeout)  │
  │  + format_dry_run()           │    │    [abstract] → CommandResult   │
  │  + format_line()  ← Template  │    │  + run_streaming(cmd, ...)      │
  │  + _decorate()    [abstract]  │    │    [abstract]                   │
  └──────────────┬────────────────┘    └──────────────┬──────────────────┘
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

### Gestion des privilèges root — deux patterns

`LinuxCommandExecutor` détecte si le processus courant tourne en root (`os.getuid() == 0`) pour préfixer les logs `[ROOT]` ou `[user]`, mais **ne préfixe jamais `sudo` sur les commandes**. Deux patterns existent selon le cas d'usage :

#### Pattern 1 — Process entier en root (recommandé pour les outils d'administration)

Le programme est lancé avec `sudo` une seule fois. Toutes les commandes héritent des droits root sans manipulation supplémentaire. Une garde `_require_root()` lève `AppPermissionError` immédiatement si le process n'est pas root.

```
sudo mon-outil sync
         └── os.getuid() == 0 ✓
             ├── dnf install ...   (root, pas de sudo)
             ├── systemctl enable  (root, pas de sudo)
             └── useradd ...       (root, pas de sudo)
```

```python
from linuxtools.errors import require_root

require_root()  # lève AppPermissionError si os.getuid() != 0
```

C'est le pattern approprié quand **la majorité des commandes requiert root** (outils post-install, provisioning système, gestion de paquets).

#### Pattern 2 — Élévation sélective par commande (sudo explicite)

Le process tourne comme utilisateur normal et élève uniquement les commandes qui le nécessitent, en traitant `sudo` comme le programme principal dans `CommandBuilder`.

```python
# Exemples dans network/scanner.py
cmd = CommandBuilder("sudo").with_args(["arp-scan", "--localnet"]).build()
# → ["sudo", "arp-scan", "--localnet"]

result = executor.run(cmd)
```

C'est le pattern approprié quand **seules quelques commandes requièrent une élévation** au sein d'un process utilisateur (scanner réseau, lecture de fichiers protégés, etc.). Inconvénient : nécessite que l'utilisateur ait `NOPASSWD` dans sudoers ou accepte de taper son mot de passe en cours d'exécution.

#### Résumé

| Critère | Process en root (`sudo mon-outil`) | Sudo par commande |
|---|---|---|
| La plupart des commandes requièrent root | ✅ Naturel | ❌ Verbeux |
| Quelques commandes seulement | ❌ Surpuissant | ✅ Ciblé |
| Invite de mot de passe | Une seule fois au lancement | Potentiellement à chaque commande |
| `LinuxCommandExecutor` | Pas de sudo dans les commandes | `CommandBuilder("sudo").with_args(...)` |

---

## 📁 Module `filesystem`

Opérations sur les fichiers et sauvegardes.

### Utilisation

```python
from linuxtools import FileLogger, LinuxFileManager, LinuxFileBackup

logger = FileLogger("/var/log/myapp.log")

# Gestion de fichiers (TOCTOU-safe, str | Path accepté)
fm = LinuxFileManager(logger)
fm.create_file("/tmp/test.txt", "Contenu du fichier")

if fm.file_exists("/tmp/test.txt"):
    content = fm.read_file("/tmp/test.txt")
    print(content)

fm.delete_file("/tmp/test.txt")

# Sauvegarde (contenu uniquement — métadonnées non préservées)
backup = LinuxFileBackup(logger)
backup.backup("/etc/myapp.conf", "/etc/myapp.conf.bak")
# ... modifications ...
backup.restore("/etc/myapp.conf", "/etc/myapp.conf.bak")
```

Copie récursive sécurisée (alternative TOCTOU-safe à `shutil.copytree`) :

```python
from linuxtools.filesystem import copytree_secure
from shutil import ignore_patterns

# Copie récursive — O_NOFOLLOW sur chaque fichier destination,
# symlinks source ignorés par défaut
copytree_secure("/etc/myapp", "/media/backup/myapp", dirs_exist_ok=True)

# Avec filtre et résolution des symlinks source
copytree_secure(
    "/home/user/project", "/media/backup/project",
    ignore=ignore_patterns("*.pyc", "__pycache__"),
    follow_symlinks=True,  # résout les symlinks source, O_NOFOLLOW côté dest
)
```

Pipeline backup + vérification d'intégrité :

```python
from linuxtools import FileLogger, LinuxFileBackup, SHA256IntegrityChecker

logger = FileLogger("/var/log/backup.log")
backup = LinuxFileBackup(logger)
checker = SHA256IntegrityChecker(logger)

src = "/etc/myapp.conf"
bak = "/etc/myapp.conf.bak"

# Sauvegarder puis vérifier l'intégrité de la copie
if backup.backup(src, bak):
    if not checker.verify_file(src, bak):
        logger.log_error("Corruption détectée après la sauvegarde !")
```

### Documentation API

| ABC (Interface) | Implémentation | Description |
|-----------------|----------------|-------------|
| `FileManager` | `LinuxFileManager` | CRUD fichiers |
| `FileBackup` | `LinuxFileBackup` | Sauvegarde/restauration |
| — | `copytree_secure()` | Copie récursive TOCTOU-safe (O_NOFOLLOW) |

### Architecture des Classes

```
  ┌─────────────────────────────────┐    ┌──────────────────────────────────┐
  │       FileManager (ABC)         │    │        FileBackup (ABC)          │
  │  + create_file(str|Path) [abst] │    │  + backup(str|Path)  [abstract]  │
  │  + file_exists(str|Path) [abst] │    │  + restore(str|Path) [abstract]  │
  │  + read_file(str|Path)   [abst] │    └─────────────────┬────────────────┘
  │  + delete_file(str|Path) [abst] │                      │ hérite
  └────────────────┬────────────────┘                      ▼
                   │ hérite
                   ▼
  ┌─────────────────────────────────┐    ┌──────────────────────────────────┐
  │      LinuxFileManager           │    │       LinuxFileBackup            │
  │  - logger: Logger               │    │  - logger: Logger                │
  │  + create_file(path, content)   │    │  + backup(src, dst)              │
  │  + file_exists(path)            │    │    (contenu uniquement, pas       │
  │  + read_file(path)              │    │     les métadonnées)             │
  │  (TOCTOU-safe: O_NOFOLLOW)      │    │  + restore(bak, dst)             │
  └─────────────────────────────────┘    └──────────────────────────────────┘

  copytree_secure(src, dst, *, dirs_exist_ok, ignore, follow_symlinks)
  └── Copie récursive TOCTOU-safe — délègue à _copy_secure() par fichier
      O_NOFOLLOW côté destination, symlinks source ignorés ou résolus
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
from linuxtools import (
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
from linuxtools import (
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
from linuxtools import (
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
from linuxtools import (
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
from linuxtools import (
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

#### Export / Restauration génériques — `SystemdUnitExporter` et `SystemdUnitRestorer`

Portable une unité systemd entre machines **sans perte de champs INI**. Contrairement
aux `config_loaders` qui n'exposent qu'un sous-ensemble fixe de clés, ces deux classes
préservent **toutes** les sections INI verbatim (`[Unit]`, `[Service]`/`[Timer]`/`[Mount]`,
`[Install]`) ainsi que les clés multi-occurrences (ex : plusieurs `Environment=`).

Le fichier TOML produit suit la convention de nommage `{nom}-{type}.toml`
(ex : `thermal-monitor.service` → `thermal-monitor-service.toml`).

```python
from pathlib import Path
from linuxtools import FileLogger
from linuxtools.systemd import (
    SystemdExecutor,
    SystemdUnitExporter,
    SystemdUnitRestorer,
)

logger = FileLogger("/var/log/porter.log")

# --- Export ---
exporter = SystemdUnitExporter(logger=logger)

toml_str = exporter.export(
    Path("/etc/systemd/system/thermal-monitor.service"),
    enabled=True,                      # état systemctl is-enabled
    requires_exec="/usr/bin/thermal",  # binaire requis (vérifié à la restauration)
)
# toml_str contient [meta], [Unit], [Service], [Install] — aucun champ perdu

Path("thermal-monitor-service.toml").write_text(toml_str)

# Helpers statiques disponibles séparément :
data = SystemdUnitExporter.parse_ini(Path("mon.service"))
# → dict section → dict clé → list[valeur]  (clés dupliquées en liste)

toml_str = SystemdUnitExporter.to_toml(data, unit_type="service", enabled=False)

# --- Restauration ---
executor = SystemdExecutor(logger)          # ou UserSystemdExecutor pour --user
restorer = SystemdUnitRestorer(executor=executor, logger=logger)

ok, unit_name = restorer.restore(
    Path("thermal-monitor-service.toml"),
    Path("/etc/systemd/system"),            # dest_dir explicite
    dry_run=False,
)
# ok=True, unit_name="thermal-monitor.service"
# → écrit le fichier INI, systemctl enable si enabled=true, daemon-reload

# Restauration d'unités utilisateur (sans root) :
from linuxtools.systemd import UserSystemdExecutor
user_executor = UserSystemdExecutor(logger)
user_restorer = SystemdUnitRestorer(executor=user_executor, logger=logger)
ok, name = user_restorer.restore(
    Path("mon-service.toml"),
    Path("~/.config/systemd/user").expanduser(),
)

# Sans executor injecté : fallback subprocess direct, avec flag --user si besoin
restorer_bare = SystemdUnitRestorer(logger=logger)
ok, name = restorer_bare.restore(
    Path("mon-service.toml"),
    Path("~/.config/systemd/user").expanduser(),
    user=True,   # ajoute --user aux commandes systemctl subprocess
)
```

**Format TOML produit :**

```toml
[meta]
unit_type = "service"
enabled = true
requires_exec = "/usr/bin/thermal"

[Unit]
Description = "Thermal monitor"
After = "network.target"

[Service]
Type = "simple"
ExecStart = "/usr/bin/thermal --daemon"
Environment = ["FOO=bar", "BAZ=qux"]   # multi-occurrence → tableau TOML
Restart = "on-failure"

[Install]
WantedBy = "multi-user.target"
```

#### Module `systemd.config_loaders`

Chargeurs de configuration pour créer des dataclasses systemd depuis TOML ou JSON.
Le format est automatiquement détecté par l'extension du fichier.

```python
from linuxtools.systemd.config_loaders import (
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
| — | `SystemdUnitExporter` | Export INI → TOML générique (toutes sections verbatim) |
| — | `SystemdUnitRestorer` | Restauration TOML → INI, enable, daemon-reload |

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
                    │  - get_status() / is_active() / is_enabled()│
                    └─────────────────────┬───────────────────────┘
                                          │ hérite (surcharge _run_systemctl
                                          │ → ajoute --user)
                                          ▼
                    ┌─────────────────────────────────────────────┐
                    │            UserSystemdExecutor              │
                    └─────────────────────┬───────────────────────┘
                                          │ injection
        ┌─────────────────────────────────┴─────────────────────────────────┐
        ▼                                                                   ▼
┌───────────────────────────────┐                         ┌───────────────────────────────┐
│        UnitManager (ABC)       │                         │     UserUnitManager (ABC)      │
│  /etc/systemd/system            │                        │  ~/.config/systemd/user         │
│  - _write_unit_file (O_NOFOLLOW)│                        │  - _ensure_unit_directory       │
│  - _remove_unit_file (TOCTOU)   │                        │  - _write_unit_file/_remove_…   │
│  - reload/enable/disable/status │                        │  - reload/enable/disable/status │
└───────┬──────────┬──────────────┘                        └────────┬─────────────┬──────────┘
        │          │                                                │             │
        ▼          ▼                                               ▼             ▼
MountUnitManager  TimerUnitManager  ServiceUnitManager   UserTimerUnitManager  UserServiceUnitManager
        │                │                  │                      │                    │
        ▼                ▼                  ▼                      ▼                    ▼
LinuxMountUnitMgr  LinuxTimerUnitMgr  LinuxServiceUnitMgr  LinuxUserTimerUnitMgr  LinuxUserServiceUnitMgr

  Mixins de comportement partagé système ↔ utilisateur (composition par
  héritage multiple — évite de dupliquer la logique start/stop/enable/…
  entre les 4 implémentations Timer/Service système et utilisateur) :

  ┌────────────────────────────────────┐   ┌────────────────────────────────────┐
  │     _ServiceOperationsMixin         │   │      _TimerOperationsMixin          │
  │  start/stop/restart/enable/disable_ │   │  enable/disable/remove_timer_unit,  │
  │  service, get_service_status,       │   │  get_timer_status, list_timers      │
  │  remove_service_unit                │   │  (+ fallback texte si JSON absent)  │
  │  contrat : _ServiceOperationsHost   │   │  contrat : _TimerOperationsHost     │
  │  (Protocol + if TYPE_CHECKING:)     │   │  (Protocol + if TYPE_CHECKING:)     │
  └────────────────┬────────────────────┘   └────────────────┬────────────────────┘
                   │ hérité par                                │ hérité par
        LinuxServiceUnitManager                     LinuxTimerUnitManager
        LinuxUserServiceUnitManager                 LinuxUserTimerUnitManager

  Hiérarchie des configurations (dataclasses frozen, valident leurs
  invariants en __post_init__, génèrent l'INI via to_unit_file()) :

  ┌─────────────────────────────────────────────────────────────────────┐
  │                       BaseSystemdConfig                              │
  │           description: str · created_at: datetime (auto)            │
  └───────────────┬───────────────┬───────────────┬─────────────────────┘
                  ▼               ▼               ▼
           MountConfig    AutomountConfig    TimerConfig    ServiceConfig
           (what/where     (where +           (timer_name    (type/restart
            validés selon   timeout_idle_sec)  property)      whitelist,
            le fs_type)                                       env anti-injection)
           Toutes : to_unit_file() avec reject_control_chars() sur chaque champ

  ┌──────────────────────────────────────────────────────────────────┐
  │  Orchestration — ScheduledTaskInstaller (ABC)                     │
  │              → SystemdScheduledTaskInstaller                      │
  │                                                                    │
  │  install(task_name, script_path, script_config, service_config,   │
  │          timer_config) → bool                                     │
  │  Compose par injection : BashScriptInstaller + LinuxServiceUnitMgr│
  │  + LinuxTimerUnitManager — orchestre :                            │
  │  1. script  →  2. service  →  3. timer  →  4. enable_timer        │
  └──────────────────────────────────────────────────────────────────┘

  ┌──────────────────────────────────────────────────────────────┐
  │  Export / Restauration génériques (unit_porter.py)           │
  │                                                              │
  │  SystemdUnitExporter                                         │
  │  - logger: Logger (optionnel — défaut : ConsoleLogger)       │
  │  + export(unit_path, enabled, requires_exec) → str | None   │
  │  + parse_ini(path) → dict[section → dict[clé → list[str]]]  │  ← @staticmethod
  │  + to_toml(data, unit_type, enabled, requires_exec) → str   │  ← @staticmethod
  │                                                              │
  │  SystemdUnitRestorer                                         │
  │  - executor: SystemdExecutor | None                          │
  │  - logger: Logger (optionnel — défaut : ConsoleLogger)       │
  │  + restore(toml_path, dest_dir, dry_run, user)              │
  │    → tuple[bool, str]  (succès, nom_unit)                   │
  │  + to_ini(data, unit_type) → str                            │  ← @staticmethod
  │                                                              │
  │  Convention de nommage TOML :                                │
  │  thermal-monitor.service → thermal-monitor-service.toml      │
  └──────────────────────────────────────────────────────────────┘

  ┌──────────────────────────────────────────────────────────────┐
  │  config_loaders/ — TOML/JSON → dataclass (ConfigFileLoader[T])│
  │  ServiceConfigLoader · TimerConfigLoader · MountConfigLoader  │
  │  · BashScriptConfigLoader (charge aussi NotificationConfig)   │
  └──────────────────────────────────────────────────────────────┘
```

---

## 📜 Module `scripts`

Génération de scripts bash et déploiement de scripts Python CLI sur le système de fichiers (FHS, scope système ou utilisateur, rapport d'installation).

### Utilisation

#### Scripts bash

```python
from linuxtools import (
    BashScriptConfig, BashScriptInstaller, LinuxFileManager,
)

config = BashScriptConfig(
    exec_command="rsync -av /src/ /dest/ && echo 'Done'",
    notification=None  # Ou NotificationConfig
)

# Générer le contenu du script
print(config.to_bash_script())

# Installer le script sur le système (chmod TOCTOU-safe via fd)
installer = BashScriptInstaller(logger, LinuxFileManager(logger))
installer.install("/usr/local/bin/backup.sh", config)
```

#### Déploiement de scripts Python CLI

Nécessite `pip install linuxtools[deploy]` (platformdirs) et `uv` installé sur le système.

```python
from linuxtools import (
    FileLogger,
    PythonCliConfig,
    LinuxCliInstaller,
    ScriptPaths,
    LinuxScriptChecker,
)
from pathlib import Path

logger = FileLogger("/var/log/deploy.log")

# Résolution des chemins FHS (nom de l'app + portée système/utilisateur)
paths = ScriptPaths("mon-outil", "user")  # ou "system"
print(paths.data_dir)   # ~/.local/share/mon-outil
print(paths.bin_path)   # ~/.local/bin/mon-outil

# Configuration du déploiement
config = PythonCliConfig(
    name="mon-outil",
    deploy_type="user",   # "user" ou "system"
    source_dir=Path("/home/user/projects/mon-outil"),
)

# Vérifications pré-installation, étape par étape
checker = LinuxScriptChecker(logger)
if checker.check_python(required_version="3.11"):
    pyproject_path = config.source_dir / "pyproject.toml"
    missing, installed, total, install_cmd = checker.check_dependencies(
        pyproject_path, config.venv_path, config.check_extras
    )
    for dep in missing:
        print(f"Manquant : {dep.package} {dep.required} ({dep.reason})")

# Installation orchestrée : checks + wrapper bash + `uv tool install`
# confirm_wrapper=True demande confirmation interactive si stdin est un TTY ;
# en CI/cron (stdin non-TTY), la confirmation est automatiquement désactivée.
installer = LinuxCliInstaller(logger, checker)
report = installer.install(config, confirm_wrapper=True)

print(report.success)            # True/False
print(report.install_path)       # Chemin d'installation (wrapper ou binaire)
print(report.format_summary())   # Résumé lisible (deps, avertissements...)
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

  ┌──────────────────────────────────────────────┐
  │           ScriptChecker (ABC)                │
  │  + check_python(required_version) [abstract] │
  │  + check_script_syntax(path)      [abstract] │
  │  + check_venv(venv_path)          [abstract] │
  │  + read_pyproject(path)           [abstract] │
  │  + check_dependencies(path, venv_path,       │
  │      extras) [abstract]                      │
  │      → (missing, installed, total, cmd)      │
  └───────────────┬──────────────────────────────┘
                  │ hérite
                  ▼
  ┌──────────────────────────────────────────────┐
  │          LinuxScriptChecker                  │
  │  (subprocess + tomllib + importlib.metadata) │
  └──────────────────────────────────────────────┘

  BashScriptConfig (frozen dataclass)
  ┌──────────────────────────────────────────────┐
  │  - exec_command: str                         │
  │  - notification: NotificationConfig | None   │
  │  + to_bash_script() → str                    │
  └──────────────────────────────────────────────┘

  PythonCliConfig (frozen dataclass)
  ┌──────────────────────────────────────────────┐
  │  - name: str                                 │
  │  - deploy_type: "user" | "system"            │
  │  - source_dir: Path                          │
  │  - venv_path: Path | None = None             │
  │  - check_extras: list[str] = []              │
  │  - generate_wrapper: bool = True             │
  └──────────────────────────────────────────────┘

  InstallReport + MissingDependency + InstalledDependency
  (rapport d'installation — voir report.py)
  ScriptPaths   (utilitaires de chemins FHS, via platformdirs)
```

---

## 🌐 Module `network`

Scan, inventaire et gestion des périphériques d'un réseau local.

### Utilisation

```python
from linuxtools import (
    LinuxArpScanner,
    JsonDeviceRepository,
    ConsoleTableReporter,
    NetworkConfig,
)

config = NetworkConfig(cidr="192.168.1.0/24", interface="eth0")

# Scanner le réseau — la config est passée à scan(), pas au constructeur
scanner = LinuxArpScanner()  # logger/executor injectables en option
devices = scanner.scan(config)

# Persister l'inventaire (le chemin est une str, converti en Path en interne)
repo = JsonDeviceRepository("/var/lib/myapp/devices.json")
repo.save(devices)

# Afficher un tableau (report() retourne une str formatée)
reporter = ConsoleTableReporter()
print(reporter.report(devices))
```

Scanners disponibles : `LinuxArpScanner` (arp-scan), `LinuxNmapScanner` (nmap), `AsusRouterScanner` (API HTTP du routeur, sans root).

Reporters disponibles : `ConsoleTableReporter`, `CsvReporter`, `JsonReporter`, `DiffReporter`.

DNS/DHCP : `LinuxHostsFileManager`, `LinuxDnsmasqConfigGenerator`, `LinuxDhcpReservationManager`.

Validateurs : `validate_ipv4`, `validate_mac`, `validate_cidr`, `validate_hostname`.

### Documentation API

| ABC (Interface) | Implémentation | Description |
|-----------------|----------------|-------------|
| `NetworkScanner` | `LinuxArpScanner` | Scan réseau via arp-scan |
| `NetworkScanner` | `LinuxNmapScanner` | Scan réseau via nmap |
| `NetworkScanner` | `AsusRouterScanner` | Scan via API HTTP du routeur ASUS (sans root) |
| `DeviceRepository` | `JsonDeviceRepository` | Persistance JSON de l'inventaire |
| `DhcpReservationManager` | `LinuxDhcpReservationManager` | Réservations DHCP (export config dnsmasq) |
| `RouterDhcpManager` (← `DhcpReservationManager`) | `AsusRouterDhcpManager` | Réservations DHCP appliquées directement au routeur ASUS |
| `DnsManager` | `LinuxHostsFileManager` | Gestion `/etc/hosts` |
| `DnsManager` | `LinuxDnsmasqConfigGenerator` | Génération config dnsmasq |
| `DeviceReporter` | `ConsoleTableReporter` | Tableau ASCII |
| `DeviceReporter` | `CsvReporter` | Export CSV |
| `DeviceReporter` | `JsonReporter` | Export JSON |
| `DeviceReporter` | `DiffReporter` | Diff entre deux inventaires |
| — | `AsusRouterClient` | Client HTTP bas niveau pour l'API locale ASUS (login, hooks, NVRAM) |

### Architecture des Classes

```
  ┌──────────────────────────────────────┐
  │        NetworkScanner (ABC)          │
  │  + scan(config) → list[NetworkDevice]│
  └──────────────┬───────────────────────┘
                 │ hérite
      ┌──────────┼───────────────────┐
      ▼          ▼                   ▼
┌──────────────┐ ┌───────────────┐ ┌─────────────────────┐
│LinuxArpScanner│ │LinuxNmapScanner│ │  AsusRouterScanner  │
│  (arp-scan)  │ │    (nmap)      │ │ (API HTTP routeur,  │
└──────────────┘ └───────────────┘ │  sans privilège root)│
                                    └──────────┬──────────┘
                                               │ utilise (composition)
                                               ▼
                                       AsusRouterClient

  ┌──────────────────────────────────────┐
  │       DeviceRepository (ABC)        │
  │  + load() → list[NetworkDevice]     │
  │  + save(devices)                    │
  │  + find_by_mac(mac)                 │
  │  + find_by_ip(ip)                   │
  └──────────────┬───────────────────────┘
                 │ hérite
                 ▼
  ┌──────────────────────────────────────────┐
  │         JsonDeviceRepository             │
  │  (persistance JSON, écriture atomique)   │
  │  + merge_scan_results(existing, scanned) │
  │    → (merged, nouveaux, disparus)        │
  └──────────────────────────────────────────┘

  ┌─────────────────────────────────┐
  │  DhcpReservationManager (ABC)   │
  │  + generate_reservations()      │
  │  + export_reservations()        │
  └────────────────┬────────────────┘
                   │ hérite
        ┌──────────┴───────────────────┐
        ▼                              ▼
┌──────────────────────────┐  ┌─────────────────────────────┐
│LinuxDhcpReservationManager│  │   RouterDhcpManager (ABC)   │
│ (export config dnsmasq   │  │  + apply_reservations()     │
│  dhcp-host=MAC,IP,host)  │  │  + read_reservations()      │
└──────────────────────────┘  └──────────────┬──────────────┘
                                              │ hérite
                                              ▼
                                   AsusRouterDhcpManager
                                  (push NVRAM via AsusRouterClient,
                                   relit la config DHCP avant écriture)

  ┌────────────────────────────────────────┐
  │            DnsManager (ABC)            │
  │  + generate_dns_names(devices)         │
  │  + generate_hosts_entries(devices)     │
  └─────────────────┬───────────────────────┘
                    │ hérite
                    ▼
  ┌────────────────────────────────────────┐
  │      _BaseDnsManager (ABC interne)     │
  │  factorise generate_dns_names() :      │
  │  hostname > vendor+octet > type+octet  │
  └─────────────────┬───────────────────────┘
                    │ hérite
        ┌───────────┴────────────┐
        ▼                        ▼
┌─────────────────────┐  ┌─────────────────────────┐
│LinuxHostsFileManager│  │LinuxDnsmasqConfigGen.   │
│   (/etc/hosts)      │  │ (address=/host/ip)      │
└─────────────────────┘  └─────────────────────────┘

  ┌─────────────────────────────────────────────────────┐
  │              DeviceReporter (ABC)                   │
  │  + report(devices) → str [abstract]                 │
  └───────────────────────────┬─────────────────────────┘
                              │ hérite
        ┌──────────┬──────────┼──────────┐
        ▼          ▼          ▼          ▼
ConsoleTable    Csv       Json        Diff
Reporter        Reporter  Reporter    Reporter
                                    (nouveaux / disparus
                                     / IP changée)

  NetworkDevice (frozen dataclass, validée au __post_init__)
  ┌──────────────────────────────────────────┐
  │  ip · mac · hostname · vendor            │
  │  device_type · is_known · fixed_ip       │
  │  dns_name · first_seen · last_seen       │
  │  notes                                   │
  │  + to_dict() / from_dict() [classmethod] │
  └──────────────────────────────────────────┘

  Configuration (frozen dataclasses, validées au __post_init__)
  NetworkConfig(cidr, interface, dhcp_range, dns,
                inventory_path, scan_timeout, scan_bandwidth)
  ├── DhcpRange(start, end)        — valide l'ordre start ≤ end
  └── DnsConfig(domain, hosts_file, dnsmasq_conf)

  Sous-package router/ — intégration routeur ASUS RT-AX88U
  ┌────────────────────────────────────────────────────┐
  │ RouterConfig(url, timeout, username, password)     │
  │   __post_init__ → _validate_router_url() (anti-SSRF,│
  │   accepte uniquement http(s) + IP/hostname LAN)    │
  │ RouterAuthError(RuntimeError)                      │
  │ AsusRouterClient — HTTP : login/logout/_hook/      │
  │   get_clients/get_dhcp_leases/get_nvram/           │
  │   set_static_reservations                          │
  │ _nvram.py — parseurs NVRAM (custom_clientlist,     │
  │   dhcp_staticlist ancien/nouveau firmware)         │
  └────────────────────────────────────────────────────┘
```

---

## 👤 Module `identity`

Gestion idempotente des groupes et utilisateurs Unix. Les opérations sont sans effet si l'état souhaité est déjà en place.

### Utilisation

```python
from linuxtools import (
    FileLogger,
    LinuxCommandExecutor,
    LinuxGroupManager,
    LinuxUserManager,
)

logger = FileLogger("/var/log/identity.log")
executor = LinuxCommandExecutor(logger)

# Groupes — crée ou corrige le GID
group_mgr = LinuxGroupManager(logger=logger, executor=executor)
group_mgr.ensure_group("appuser", gid=1500)
# → groupadd si absent, groupmod --gid si GID incorrect, skip sinon

# Utilisateurs — crée ou corrige l'UID
user_mgr = LinuxUserManager(logger=logger, executor=executor)
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
from linuxtools.cli import (
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
  │  - _logger: Logger | None                      │
  │  + run() → dispatch vers la commande choisie   │
  └────────────────────────────────────────────────┘

  ┌────────────────────────────────────────────────┐
  │              DryRunContext                     │
  │  + dry_run: bool                               │
  │  + would_write(path, content) → None           │  ← no-op si dry_run=False
  │  + would_create(path) → None                   │  ← no-op si dry_run=False
  │  + would_modify(path, line) → None             │  ← no-op si dry_run=False
  │  + would_delete(path) → None                   │  ← no-op si dry_run=False
  │  + would_run_command(cmd) → None               │  ← no-op si dry_run=False
  └────────────────────────────────────────────────┘

  add_dry_run_argument(parser)
  └── ajoute --dry-run à un ArgumentParser argparse
```

---

## 📋 Module `dotconf`

Gestion de fichiers de configuration INI (.conf) avec validation externe, et application déclarative de blocs de configuration depuis un fichier TOML.

### Utilisation

```python
from dataclasses import dataclass
from pathlib import Path
from linuxtools import (
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

Permet d'insérer ou décommenter des blocs dans un fichier `.conf` sans toucher aux commentaires ni à la mise en forme existante.

```python
from linuxtools import SectionAwareEditor

editor = SectionAwareEditor(Path("/etc/myapp.conf"))

# Vérifier qu'un bloc est déjà actif
if editor.is_block_present("fastestmirror = True", section="main"):
    print("Déjà présent")

# Vérifier qu'un bloc est commenté (ex: "# fastestmirror = True")
if editor.is_block_commented("fastestmirror = True", section="main"):
    print("Commenté, sera décommenté")

# Insérer ou décommenter un bloc (avec commentaire optionnel avant)
editor.ensure_block(
    "fastestmirror = True",
    section="main",
    comment="# Activer le miroir le plus rapide",
)

# Lister les sections [section] présentes dans le fichier
sections = editor.list_sections()  # ['main', 'plugins']
```

#### `TomlSpecLoader` + `ConfigApplier` — Application déclarative depuis TOML

Décrit les blocs à appliquer dans un fichier TOML `[target]`, puis les applique de façon idempotente sur n'importe quel `.conf`.

**Format TOML attendu :**

```toml
[target]
file_path = "~/.config/yt-dlp/config"

[[target.content]]
comment = "# Meilleure qualité disponible"
content = '-f "bestvideo*+bestaudio/best"'

[[target.content]]
content = "--no-playlist"

# Pour un fichier INI avec sections (ex: /etc/dnf/dnf.conf)
[[target.content]]
section = "main"
comment = "# Miroir le plus rapide"
content = "fastestmirror = True"
```

**Utilisation :**

```python
from pathlib import Path
# Non ré-exportés au niveau racine (cf. Corrections du module dotconf) —
# import direct depuis le sous-module
from linuxtools.dotconf import TomlSpecLoader, ConfigApplier

# Charger la spec TOML → ConfigSpec
loader = TomlSpecLoader()
spec = loader.load(Path("my-app.toml"))
# spec.file_path → Path résolu (~, $VAR, ${VAR} développés)
# spec.blocks    → list[ConfigBlock]

# Appliquer sur le fichier cible (crée le fichier si absent)
applier = ConfigApplier()
actions = applier.apply(spec)
for action in actions:
    print(action)
# Created: /home/user/.config/yt-dlp/config (2 blocks)
# Appended: fastestmirror = True
# Uncommented: key = value

# Avec logger injectable
from linuxtools import FileLogger
logger = FileLogger("/var/log/myapp.log")
applier = ConfigApplier(logger=logger)
actions = applier.apply(spec)  # chaque action est aussi loggée

# Idempotent : un second appel sur un fichier déjà conforme renvoie []
assert applier.apply(spec) == []
```

**Comportements clés :**
- Crée le fichier (et les répertoires parents) s'il est absent, chmod 644
- Ajoute les blocs manquants en fin de fichier (ou dans la `[section]` INI cible)
- Décommente les lignes commentées (`# key = value` → `key = value`)
- Ne touche pas aux blocs déjà présents (idempotent)
- Retourne une liste d'actions décrivant ce qui a été modifié (vide si aucun changement)

#### `ConfTomlExporter` — Export d'un `.conf` existant vers une spec TOML

Sens inverse de `TomlSpecLoader`/`ConfigApplier` : lit un fichier `.conf` (plat ou INI) déjà configuré sur une machine et produit le TOML de spec correspondant — pour rejouer la même configuration ailleurs via `ConfigApplier`.

```python
from pathlib import Path
# Non ré-exporté au niveau racine — import direct depuis le sous-module
from linuxtools.dotconf import ConfTomlExporter

exporter = ConfTomlExporter()
exporter.export(
    source=Path("/etc/dnf/dnf.conf"),
    dest=Path("/tmp/dnf-spec.toml"),
)
# Produit un TOML [target] / [[target.content]] directement
# rechargeable par TomlSpecLoader().load(...)

# Sérialisation TOML générique d'un dict (tables imbriquées incluses)
toml_text = exporter.export_mapping({
    "main": {"fastestmirror": True, "max_parallel_downloads": 10},
})
```

> Les commentaires consécutifs précédant une ligne de configuration sont associés au bloc suivant ; la détection INI vs fichier plat se fait automatiquement (`_is_ini`, présence d'un en-tête `[section]`). `_toml_escape` échappe guillemets, antislashs et caractères de contrôle (`\uXXXX`) pour produire un TOML valide même à partir d'un contenu arbitraire.

### Documentation API

| ABC (Interface) | Implémentation | Description |
|-----------------|----------------|-------------|
| `IniSection` | `ValidatedSection` | Section INI avec validation externe |
| `IniConfig` | — | Fichier INI complet |
| `IniConfigManager` | `LinuxIniConfigManager` | Gestion lecture/écriture INI |
| — | `SectionAwareEditor` | Édition ligne-à-ligne préservant les commentaires |
| — | `parse_validator` | Convertit un validateur brut en callable/liste |
| — | `build_validators` | Construit un dictionnaire de validateurs |
| — | `ConfigBlock` | Bloc de configuration (content, comment, section) |
| — | `ConfigSpec` | Spec complète (file_path + liste de ConfigBlock) |
| — | `TomlSpecLoader` | Charge un TOML `[target]` → `ConfigSpec` |
| — | `ConfigApplier` | Applique un `ConfigSpec` sur un fichier `.conf` |

**Dataclasses** :

| Classe | Champs | Description |
|--------|--------|-------------|
| `ValidatedSection` | — | Section INI avec validation externe |
| `ConfigBlock` | `content`, `comment=""`, `section=None` | Bloc à appliquer dans le fichier cible |
| `ConfigSpec` | `file_path`, `blocks=[]` | Spec complète (chemin résolu + liste de blocs) |

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
  │  + read(path) → dict[str, dict] [abstract]       │
  │  + write(path, config: IniConfig)    [abstract]  │
  │  + update_section(path, section,                 │
  │      validators=None) → bool         [abstract]  │
  │  + is_section_configured(path, section) → bool   │
  │                                       [abstract]  │
  └────────────────────┬─────────────────────────────┘
                       │ hérite
                       ▼
  ┌──────────────────────────────────────────────────┐
  │           LinuxIniConfigManager                  │
  │  (configparser stdlib + chmod 0o644)             │
  │  + read / write / update_section /               │
  │      is_section_configured                       │
  │  + write_section(path, section)                  │
  │      (crée ou met à jour une seule section)      │
  │  + section_to_ini / config_to_ini → str          │
  │      (rendu sans écriture sur disque)            │
  └──────────────────────────────────────────────────┘

  ┌──────────────────────────────────────────────────┐
  │             SectionAwareEditor                   │
  │  Édition ligne-à-ligne préservant les            │
  │  commentaires et la structure du fichier         │
  │  + is_block_present(content, section) → bool     │
  │  + is_block_commented(content, section) → bool   │
  │  + ensure_block(content, section, comment)       │
  │  + list_sections() → list[str]                   │
  └──────────────────────────────────────────────────┘

  ┌──────────────────────────────────┐
  │         ConfigBlock              │
  │  @dataclass                      │
  │  content: str                    │
  │  comment: str = ""               │
  │  section: str | None = None      │
  └──────────────────────────────────┘

  ┌──────────────────────────────────┐
  │         ConfigSpec               │
  │  @dataclass                      │
  │  file_path: Path                 │
  │  blocks: list[ConfigBlock] = []  │
  └──────────────────────────────────┘

  ┌──────────────────────────────────┐      ┌────────────────────────────┐
  │        TomlSpecLoader            │      │       ConfigApplier         │
  │  __init__(loader=FileConfigLoader│      │  __init__(logger=None)      │
  │  load(spec_path) → ConfigSpec    │      │  apply(spec) → list[str]   │
  │  _resolve_path(raw) → Path       │      │  (crée / ajoute / décomm.) │
  └──────────────────────────────────┘      └────────────────────────────┘
                                                         │ utilise
                                                         ▼
                                            ┌────────────────────────────┐
                                            │     SectionAwareEditor     │
                                            └────────────────────────────┘
```

---

## 🔐 Module `integrity`

Vérification d'intégrité par checksums, et ABC pour la vérification de sections INI.

### Utilisation

```python
from linuxtools import FileLogger, SHA256IntegrityChecker, calculate_checksum

# Fonction utilitaire rapide — whitelist d'algorithmes : sha256, sha384,
# sha512, blake2b uniquement (MD5/SHA1 rejetés : ValueError, faibles)
checksum = calculate_checksum("/path/to/file")  # SHA256 par défaut
checksum_512 = calculate_checksum("/path/to/file", algorithm="sha512")

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

# Variante stricte (fail-fast) — lève IntegrityError au lieu de retourner False
from linuxtools import IntegrityError

try:
    count = checker.verify_or_raise("/home/user/Documents", "/media/backup")
    print(f"{count} fichiers vérifiés")
except IntegrityError as e:
    print(f"Intégrité compromise : {e.path}")
    # e.expected / e.actual contiennent les checksums (None si fichier manquant)
```

#### `IniSectionIntegrityChecker` — ABC pour fichiers INI

Contrat abstrait pour implémenter la vérification d'intégrité d'une section INI après écriture.

```python
from pathlib import Path
from linuxtools.integrity import IniSectionIntegrityChecker

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
  │  (hashlib — whitelist : sha256, sha384,    │
  │   sha512, blake2b — MD5/SHA1 rejetés)      │
  └────────────────────────────────────────────┘

  ┌────────────────────────────────────────────┐
  │          IntegrityChecker (ABC)            │
  │  + verify(source, destination) → bool      │
  │    [abstract]                              │
  └───────────────────┬────────────────────────┘
                      │ hérite
                      ▼
  ┌──────────────────────────────────────────────────┐
  │            SHA256IntegrityChecker                │
  │  - _calculator: ChecksumCalculator (injecté)     │
  │  + verify_file(source, dest) → bool              │
  │  + verify_file_or_raise(source, dest) → None     │  ← lève IntegrityError
  │  + verify(source, destination,                   │
  │      dest_subdir=None) → bool                    │
  │      (compare un répertoire entier, gère le      │
  │       sous-répertoire créé par rsync)            │
  │  + verify_or_raise(source, destination,          │
  │      dest_subdir=None) → int                     │  ← lève IntegrityError
  │  + get_checksum(file_path) → str  (avec log)     │
  │  + calculate_checksum(file_path, algorithm)      │
  │      [staticmethod — délègue à la fonction       │
  │       de module]                                 │
  └──────────────────────────────────────────────────┘

  ┌──────────────────────────────────────────────────┐
  │         IniSectionIntegrityChecker (ABC)         │
  │  + verify(file_path: Path,                       │
  │      section: object) → bool        [abstract]   │
  │    (compare un fichier à un modèle — section     │
  │     doit exposer section_name()/to_dict())       │
  │    aucune implémentation concrète dans le module │
  └──────────────────────────────────────────────────┘
```

---

## 🔑 Module `credentials`

Gestion des secrets via une chaîne de priorité : variables d'environnement → fichier `.env` → keyring système.

### Utilisation

```python
from linuxtools import CredentialManager, CredentialNotFoundError
from pathlib import Path

# Chaîne complète : env → .env → keyring
manager = CredentialManager.from_dotenv(
    service="monapp",
    dotenv_path=Path("config/.env"),
)

# Lire un secret avec valeur par défaut (jamais d'exception)
password = manager.get("DB_PASSWORD", default="")

# Lire un secret obligatoire — lève si absent des trois sources
try:
    password = manager.require("DB_PASSWORD")
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
  │  + get(key, default="") → str           │
  │  + require(key) → str  [raises          │
  │      CredentialNotFoundError si absent] │
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

Cinq validateurs couvrent des besoins distincts :

| Classe | Vérifie | Usage typique |
|--------|---------|---------------|
| `PathChecker` | Répertoires parents existent | Log files, config files |
| `PathCheckerPermission` | Répertoires parents accessibles en écriture | Backup, sauvegardes |
| `PathCheckerWorldWritable` | Fichiers non modifiables par tous | Scripts exécutés en root |
| `PathCheckerGroupAccess` | Appartenance groupe + rwx + setgid | Montages NFS partagés |
| `SystemCommandValidator` | Présence d'exécutables dans le PATH | Scripts dépendant d'outils externes |

### Utilisation

```python
from linuxtools import PathChecker, PathCheckerPermission, PathCheckerWorldWritable

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
ww_checker.validate()  # Lève PermissionError (bit S_IWOTH ou symlink)

# Vérifie la présence de commandes système requises (un quatrième
# validateur, distinct des trois ci-dessus : il ne porte pas sur des
# chemins mais sur la disponibilité d'exécutables dans le PATH)
from linuxtools import SystemCommandValidator

sys_checker = SystemCommandValidator({
    "borg": "sudo dnf install borgbackup",
    "rsync": "sudo dnf install rsync",
})
sys_checker.validate()  # Lève MissingDependencyError si absentes,
                        # message listant les instructions d'installation
manquantes = sys_checker.missing_commands()  # → list[str], sans lever

# Vérifie l'appartenance groupe + rwx + setgid (typique : montage NFS)
from linuxtools import PathCheckerGroupAccess

nfs_checker = PathCheckerGroupAccess(
    "/media/nas/keepass",
    "ff_home",
    require_setgid=True,   # héritage de groupe pour les nouveaux fichiers
)
nfs_checker.validate()
# Lève FileNotFoundError si le chemin n'existe pas
# Lève KeyError si le groupe 'ff_home' est inconnu du système
# Lève PermissionError avec commande corrective si :
#   - le répertoire n'appartient pas à 'ff_home'
#   - les bits rwx groupe sont incomplets
#   - le bit setgid est absent

# Validation de configuration avec Pydantic (optionnel)
# pip install linuxtools[validation]
from pydantic import BaseModel
from linuxtools import FileConfigLoader

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
| `Validator` | `PathChecker` | Répertoires parents existent (`paths: list[str]`) |
| `Validator` | `PathCheckerPermission` | Répertoires parents accessibles en écriture (`paths: list[str]`) |
| `Validator` | `PathCheckerWorldWritable` | Fichier non world-writable, anti-symlink (`path: str \| Path`, unique) |
| `Validator` | `PathCheckerGroupAccess` | Appartenance groupe + rwx + setgid (`path`, `group: str`, `require_setgid: bool = True`) |
| `Validator` | `SystemCommandValidator` | Présence de commandes système dans le `PATH` (`requirements: dict[str, str]`) |

### Architecture des Classes

```
  ┌──────────────────────────────────────────────────────┐
  │                   Validator (ABC)                    │
  │  + validate() → None  [abstract]                     │
  │    raises: ValueError | PermissionError | ...        │
  │    (chaque implémentation documente ses propres      │
  │     exceptions concrètes — voir liste ci-dessous)    │
  └──┬───────────┬───────────┬────────────┬──────────────┘
     │ hérite    │ hérite    │ hérite     │ hérite    │ hérite
     ▼           ▼           ▼            ▼           ▼
  ┌───────────┐ ┌──────────────────┐ ┌───────────────┐ ┌─────────────────────┐ ┌──────────────────┐
  │PathChecker│ │PathCheckerPermis-│ │PathChecker-   │ │PathCheckerGroup-    │ │SystemCommand-    │
  │           │ │sion              │ │WorldWritable  │ │Access               │ │Validator         │
  │ - _paths: │ │ - _paths:        │ │ - _path: Path │ │ - _path: Path       │ │ - _requirements: │
  │  list[str]│ │   list[str]      │ │  (non résolu) │ │ - _group: str       │ │   dict[str, str] │
  │ + validate│ │ + validate()     │ │ + validate()  │ │ - _require_setgid   │ │ + validate()     │
  │   (.resolve│ │  (existence AVANT│ │  (os.lstat — │ │ + validate()        │ │  [MissingDep-    │
  │   anti     │ │  permission,     │ │  TOCTOU-safe, │ │  1. groupe correct? │ │  endencyError]   │
  │   traversal│ │  message précis) │ │  rejette les  │ │  2. rwx groupe?     │ │ + missing_       │
  │   [Value-  │ │  [ValueError |   │ │  symlinks)    │ │  3. setgid? (opt.)  │ │   commands()     │
  │   Error]   │ │  PermissionError]│ │  [FileNotFound│ │  (os.stat — suit    │ │   → list[str]    │
  │            │ │                  │ │  PermissionEr]│ │  les liens, NFS OK) │ │                  │
  │            │ │                  │ │               │ │  [FileNotFound |    │ │                  │
  │            │ │                  │ │               │ │  KeyError |         │ │                  │
  │            │ │                  │ │               │ │  PermissionError]   │ │                  │
  └───────────┘ └──────────────────┘ └───────────────┘ └─────────────────────┘ └──────────────────┘
```

> Les cinq implémentations héritent **directement** de `Validator` — il
> n'existe pas de hiérarchie intermédiaire entre elles. Ce sont cinq
> stratégies sœurs, chacune avec sa propre forme de constructeur et son
> propre jeu d'exceptions.

---

## 🔔 Module `notification`

Configuration de notifications desktop via `notify-send`, diffusées à
tous les utilisateurs ayant une session graphique active (bus D-Bus de
session détecté via `loginctl`) — compatible avec tout environnement
respectant la spécification freedesktop.org Desktop Notifications
(GNOME, KDE Plasma, XFCE...).

### Utilisation

```python
from linuxtools import NotificationConfig

# Configuration de notification (champs texte validés : non vides,
# sans caractère de contrôle — voir __post_init__)
notif = NotificationConfig(
    title="Sauvegarde",
    message_success="Sauvegarde terminée avec succès",
    message_failure="Échec de la sauvegarde",
    app_name="MonScript",  # injecté via shlex.quote — voir Corrections
)

# Générer le code bash à intégrer dans un script de sauvegarde
bash_function = notif.to_bash_function()      # définition de send_notification()
appel_succes = notif.to_bash_call_success()   # appel en cas de succès
appel_echec = notif.to_bash_call_failure()    # appel en cas d'échec
```

### Documentation API

| Classe | Description |
|--------|-------------|
| `NotificationConfig` | Dataclass de configuration des notifications desktop, génère du code bash (`to_bash_function`/`to_bash_call_success`/`to_bash_call_failure`) |

---

## 🎯 Exemple Complet

Script de sauvegarde utilisant plusieurs modules ensemble :

```python
#!/usr/bin/env python3
from linuxtools import (
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
| `test_filesystem.py` | 22 | CRUD TOCTOU-safe, backup/restore, rejet symlinks (src + dst) |
| `test_config.py` | 24 | Chargement TOML/JSON, profils, fusion, deep_merge, cascade search_paths |
| `test_config_validation.py` | 14 | Validation Pydantic FileConfigLoader, ConfigurationManager.validate() |
| `test_integrity.py` | 27 | Checksums, vérification fichiers/répertoires, verify_or_raise |
| `test_systemd_mount.py` | 36 | Génération .mount/.automount, validation, enable/disable |
| `test_systemd_timer.py` | 23 | TimerConfig, to_unit_file(), list_timers JSON/texte |
| `test_systemd_service.py` | 41 | ServiceConfig, validation type/restart/env, TOCTOU, LSP |
| `test_systemd_executor.py` | 9 | Validation noms d'unités dans SystemdExecutor |
| `test_systemd_validators.py` | 25 | validate_unit_name(), validate_service_name() |
| `test_systemd_scheduled_task.py` | 12 | SystemdScheduledTaskInstaller |
| `test_systemd_config_loaders.py` | 30 | Tous les loaders (TOML/JSON) |
| `test_systemd_unit_porter.py` | 45 | SystemdUnitExporter, SystemdUnitRestorer (parse_ini, to_toml, export, to_ini, restore) |
| `test_dotconf.py` | 20 | Sections INI, validation, lecture/écriture |
| `test_dotconf_line_editor.py` | — | SectionAwareEditor, édition préservant commentaires |
| `test_dotconf_spec.py` | 11 | ConfigBlock, ConfigSpec — dataclasses, champs par défaut, indépendance instances |
| `test_dotconf_toml_spec_loader.py` | 9 | TomlSpecLoader : chargement TOML, résolution `~`/`$VAR`, erreurs |
| `test_dotconf_applier.py` | 16 | ConfigApplier : création, ajout, décommentage, section INI, chmod, idempotence, logger |
| `test_commands.py` | 74 | CommandBuilder, formatters, exécution, streaming, dry-run, root/user |
| `test_scripts.py` | 123 | BashScriptConfig, installation scripts, wrapper templates, TTY detection, TOCTOU, edge cases checker/installer |
| `test_notification.py` | 22 | NotificationConfig, génération bash, validation tous champs |
| `test_validation.py` | 11 | PathChecker, PathCheckerPermission, PathCheckerWorldWritable |
| `test_validation_system.py` | 7 | SystemCommandValidator (validate, missing_commands) |
| `test_validation_group_access.py` | 15 | PathCheckerGroupAccess (groupe, rwx, setgid, messages d'erreur) |
| `test_identity_group.py` | — | LinuxGroupManager, ensure_group (create/correct/skip) |
| `test_identity_user.py` | — | LinuxUserManager, ensure_user, ensure_user_groups |
| `test_cli.py` | 15 | CliCommand (ABC, register, execute, sous-classes partielles), CliApplication (dispatch, flags, args, edge cases) |
| `test_cli_dry_run.py` | 16 | DryRunContext (would_write/create/modify/delete/run_command), add_dry_run_argument (--dry-run, -n) |
| **Total** | **1312+** | |

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
<summary><b>❌ ModuleNotFoundError: No module named 'linuxtools'</b></summary>

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
from linuxtools import UserSystemdExecutor, LinuxUserTimerUnitManager
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

<details>
<summary><b>❌ uv tool install — error: Executable already exists</b></summary>

**Cause :** Un précédent `uv tool install` a échoué ou a été supprimé partiellement, laissant un symlink cassé dans `~/.local/bin/`.

```
error: Executable already exists: mon-outil (use `--force` to overwrite)
```

**Diagnostic :**
```bash
ls -la ~/.local/bin/mon-outil
# → lrwxrwxrwx ... ~/.local/bin/mon-outil -> ~/.local/share/uv/tools/mon-outil/bin/mon-outil
#   (cible inexistante = symlink cassé)
```

**Solution :**
```bash
# Supprimer le symlink cassé
rm ~/.local/bin/mon-outil

# Relancer l'installation
mon-outil install
```

> `LinuxCliInstaller` (v1.7+) ajoute automatiquement `--force` à `uv tool install`
> pour les déploiements utilisateur, rendant la commande idempotente.

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

## 🔧 Améliorations connues

| # | Description | Impact |
|---|---|---|
| 1 | **Streaming temps réel des commandes longues** — `LinuxCommandExecutor` utilise `capture_output=True` : la sortie de `dnf5`, `flatpak`, `uv`… n'est visible qu'à la fin. Implémenter un mode streaming via `subprocess.Popen` + lecture ligne par ligne avec comportement "tee" : affichage console en temps réel **et** écriture simultanée dans le fichier de log. | UX sur transactions longues |
| 2 | **Centralisation des logs dans `/var/log/`** — `FileLogger` écrit dans `~/.local/share/<app>/`. Objectif : `/var/log/<app>/$USER/` (mode user) et `/var/log/<app>/` (mode root), répertoire créé avec les bonnes permissions lors de l'initialisation. | Cohérence et visibilité des logs système |

---

## 📄 Licence

Ce projet est sous licence MIT. Voir le fichier [LICENSE](LICENSE) pour plus de détails.

---

<p align="center">
  <b>linuxtools</b> — Conçu avec les principes SOLID pour une extensibilité maximale
</p>

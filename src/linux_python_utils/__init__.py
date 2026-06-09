"""
Linux Python Utils - Bibliothèque utilitaire pour systèmes Linux.

Modules disponibles:
- logging: Gestion des logs (Logger, FileLogger)
- config: Chargement de configuration (TOML, JSON)
- filesystem: Opérations sur fichiers (FileManager, FileBackup)
- systemd: Gestion des services systemd
- integrity: Vérification d'intégrité (checksums)
- dotconf: Gestion de fichiers de configuration INI (.conf)
- notification: Configuration des notifications desktop (NotificationConfig)
- scripts: Génération de scripts bash (BashScriptConfig)
- commands: Exécution de commandes système (CommandBuilder,
  LinuxCommandExecutor)
- validation: Validation de chemins et données (Validator, PathChecker)
- network: Gestion des peripheriques reseau (scanners, inventaire,
  DHCP, DNS, rapports)
- credentials: Gestion des secrets (env, .env, keyring systeme)
- cli: Framework CLI Command Pattern (CliCommand, CliApplication)
- identity: Gestion idempotente des groupes et utilisateurs Unix
"""

__version__ = "1.6.0"

from linux_python_utils.logging import (
    Logger,
    ConsoleLogger,
    FileLogger,
    SecurityEvent,
    SecurityEventType,
    SecurityLogger,
)
from linux_python_utils.config import (
    ConfigManager,
    ConfigLoader,
    FileConfigLoader,
    ConfigurationManager,
    XdgAppConfig,
)
from linux_python_utils.filesystem import (
    FileManager,
    LinuxFileManager,
    FileBackup,
    LinuxFileBackup
)
from linux_python_utils.systemd import (
    # Exécuteurs systemctl
    SystemdExecutor,
    UserSystemdExecutor,
    # Classes abstraites système
    UnitManager,
    MountUnitManager,
    TimerUnitManager,
    ServiceUnitManager,
    # Classes abstraites utilisateur
    UserUnitManager,
    UserTimerUnitManager,
    UserServiceUnitManager,
    # Configurations
    MountConfig,
    AutomountConfig,
    TimerConfig,
    ServiceConfig,
    # Implémentations système
    LinuxMountUnitManager,
    LinuxTimerUnitManager,
    LinuxServiceUnitManager,
    # Implémentations utilisateur
    LinuxUserTimerUnitManager,
    LinuxUserServiceUnitManager,
    # Installateur de tâches planifiées
    ScheduledTaskInstaller,
    SystemdScheduledTaskInstaller,
    # Chargeurs de configuration
    ServiceConfigLoader,
    TimerConfigLoader,
    MountConfigLoader,
    BashScriptConfigLoader,
    # Export / restauration génériques
    SystemdUnitExporter,
    SystemdUnitRestorer,
    # Rétrocompatibilité
    LinuxSystemdServiceManager,
)
from linux_python_utils.integrity import (
    ChecksumCalculator,
    HashLibChecksumCalculator,
    IntegrityChecker,
    SHA256IntegrityChecker,
    calculate_checksum
)
from linux_python_utils.dotconf import (
    IniSection,
    IniConfig,
    IniConfigManager,
    ValidatedSection,
    LinuxIniConfigManager,
    SectionAwareEditor,
    parse_validator,
    build_validators,
)
from linux_python_utils.notification import NotificationConfig
from linux_python_utils.scripts import (
    BashScriptConfig,
    PythonCliConfig,
    ScriptInstaller,
    BashScriptInstaller,
    CliInstaller,
    LinuxCliInstaller,
    ScriptPaths,
    ScriptChecker,
    LinuxScriptChecker,
    InstallReport,
    MissingDependency,
)
from linux_python_utils.commands import (
    CommandResult,
    CommandExecutor,
    CommandBuilder,
    CommandFormatter,
    PlainCommandFormatter,
    AnsiCommandFormatter,
    LinuxCommandExecutor,
)
from linux_python_utils.validation import (
    Validator,
    PathChecker,
    PathCheckerPermission,
    PathCheckerWorldWritable,
    PathCheckerGroupAccess,
    SystemCommandValidator,
)
from linux_python_utils.credentials import (
    # ABCs
    CredentialProvider,
    CredentialStore,
    # Modeles
    Credential,
    CredentialKey,
    # Exceptions
    CredentialNotFoundError,
    CredentialProviderUnavailableError,
    CredentialStoreError,
    # Providers
    EnvCredentialProvider,
    DotEnvCredentialProvider,
    KeyringCredentialProvider,
    # Chaine et facade
    CredentialChain,
    CredentialManager,
)
from linux_python_utils.cli import CliCommand, CliApplication
from linux_python_utils.identity import (
    GroupManagerBase,
    UserManagerBase,
    LinuxGroupManager,
    LinuxUserManager,
)
from linux_python_utils.network import (
    # Modeles
    NetworkDevice,
    # Configuration
    NetworkConfig,
    DhcpRange,
    DnsConfig,
    # ABCs
    NetworkScanner,
    DeviceRepository,
    DhcpReservationManager,
    DnsManager,
    DeviceReporter,
    # Scanners
    LinuxArpScanner,
    LinuxNmapScanner,
    # Repository
    JsonDeviceRepository,
    # DHCP
    LinuxDhcpReservationManager,
    # DNS
    LinuxHostsFileManager,
    LinuxDnsmasqConfigGenerator,
    # Rapports
    ConsoleTableReporter,
    CsvReporter,
    JsonReporter,
    DiffReporter,
    # Validateurs
    validate_ipv4,
    validate_mac,
    validate_cidr,
    validate_hostname,
)

__all__ = [
    # Logging
    "Logger",
    "ConsoleLogger",
    "FileLogger",
    "SecurityEvent",
    "SecurityEventType",
    "SecurityLogger",
    # Config
    "ConfigManager",
    "ConfigLoader",
    "FileConfigLoader",
    "ConfigurationManager",
    "XdgAppConfig",
    # Filesystem
    "FileManager",
    "LinuxFileManager",
    "FileBackup",
    "LinuxFileBackup",
    # Systemd - Exécuteurs
    "SystemdExecutor",
    "UserSystemdExecutor",
    # Systemd - Classes abstraites système
    "UnitManager",
    "MountUnitManager",
    "TimerUnitManager",
    "ServiceUnitManager",
    # Systemd - Classes abstraites utilisateur
    "UserUnitManager",
    "UserTimerUnitManager",
    "UserServiceUnitManager",
    # Systemd - Configurations
    "MountConfig",
    "AutomountConfig",
    "TimerConfig",
    "ServiceConfig",
    # Systemd - Implémentations système
    "LinuxMountUnitManager",
    "LinuxTimerUnitManager",
    "LinuxServiceUnitManager",
    # Systemd - Implémentations utilisateur
    "LinuxUserTimerUnitManager",
    "LinuxUserServiceUnitManager",
    # Systemd - Installateur de tâches planifiées
    "ScheduledTaskInstaller",
    "SystemdScheduledTaskInstaller",
    # Systemd - Chargeurs de configuration
    "ServiceConfigLoader",
    "TimerConfigLoader",
    "MountConfigLoader",
    "BashScriptConfigLoader",
    # Systemd - Export / restauration génériques
    "SystemdUnitExporter",
    "SystemdUnitRestorer",
    # Systemd - Rétrocompatibilité
    "LinuxSystemdServiceManager",
    # Integrity
    "ChecksumCalculator",
    "HashLibChecksumCalculator",
    "IntegrityChecker",
    "SHA256IntegrityChecker",
    "calculate_checksum",
    # DotConf - Interfaces
    "IniSection",
    "IniConfig",
    "IniConfigManager",
    # DotConf - Implémentations
    "ValidatedSection",
    "LinuxIniConfigManager",
    "SectionAwareEditor",
    # DotConf - Utilitaires
    "parse_validator",
    "build_validators",
    # Notification
    "NotificationConfig",
    # Scripts
    "BashScriptConfig",
    "PythonCliConfig",
    "ScriptInstaller",
    "BashScriptInstaller",
    "CliInstaller",
    "LinuxCliInstaller",
    "ScriptPaths",
    "ScriptChecker",
    "LinuxScriptChecker",
    "InstallReport",
    "MissingDependency",
    # Commands - Structures de données
    "CommandResult",
    # Commands - Interface abstraite
    "CommandExecutor",
    # Commands - Constructeur
    "CommandBuilder",
    # Commands - Formateurs
    "CommandFormatter",
    "PlainCommandFormatter",
    "AnsiCommandFormatter",
    # Commands - Implémentation
    "LinuxCommandExecutor",
    # Validation
    "Validator",
    "PathChecker",
    "PathCheckerPermission",
    "PathCheckerWorldWritable",
    "PathCheckerGroupAccess",
    "SystemCommandValidator",
    # Credentials - ABCs
    "CredentialProvider",
    "CredentialStore",
    # Credentials - Modeles
    "Credential",
    "CredentialKey",
    # Credentials - Exceptions
    "CredentialNotFoundError",
    "CredentialProviderUnavailableError",
    "CredentialStoreError",
    # Credentials - Providers
    "EnvCredentialProvider",
    "DotEnvCredentialProvider",
    "KeyringCredentialProvider",
    # Credentials - Chaine et facade
    "CredentialChain",
    "CredentialManager",
    # Network - Modeles
    "NetworkDevice",
    # Network - Configuration
    "NetworkConfig",
    "DhcpRange",
    "DnsConfig",
    # Network - ABCs
    "NetworkScanner",
    "DeviceRepository",
    "DhcpReservationManager",
    "DnsManager",
    "DeviceReporter",
    # Network - Scanners
    "LinuxArpScanner",
    "LinuxNmapScanner",
    # Network - Repository
    "JsonDeviceRepository",
    # Network - DHCP
    "LinuxDhcpReservationManager",
    # Network - DNS
    "LinuxHostsFileManager",
    "LinuxDnsmasqConfigGenerator",
    # Network - Rapports
    "ConsoleTableReporter",
    "CsvReporter",
    "JsonReporter",
    "DiffReporter",
    # Network - Validateurs
    "validate_ipv4",
    "validate_mac",
    "validate_cidr",
    "validate_hostname",
    # CLI - Framework Command Pattern
    "CliCommand",
    "CliApplication",
]

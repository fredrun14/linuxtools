"""
Linux Python Utils - Bibliothèque utilitaire pour systèmes Linux.

Modules disponibles:
- logging: Gestion des logs (Logger, FileLogger)
- config: Chargement de configuration (TOML, JSON)
- filesystem: Opérations sur fichiers (FileManager, FileBackup)
- systemd: Gestion des services systemd
- integrity: Vérification d'intégrité (checksums)
- dotconf: Gestion de fichiers de configuration INI (.conf)
- notification: Notifications multi-canaux et comptes rendus d'exécution
  (Notifier, NotifierChain, ExecutionReport, NotificationConfig)
- scripts: Génération de scripts bash (BashScriptConfig)
- commands: Exécution de commandes système (CommandBuilder,
  LinuxCommandExecutor)
- validation: Validation de chemins et données (Validator, PathChecker)
- network: Gestion des peripheriques reseau (scanners, inventaire,
  DHCP, DNS, rapports)
- credentials: Gestion des secrets (env, .env, keyring systeme)
- cli: Framework CLI Command Pattern (CliCommand, CliApplication)
- identity: Gestion idempotente des groupes et utilisateurs Unix
- deploy: Déployeur/updateur d'outil Python sur hôte, local ou
  distant via SSH (Deployer, DeployConfig, DeployCommand)
"""

__version__ = "1.8.0"

from linuxtools.logging import (
    Logger,
    ConsoleLogger,
    FileLogger,
    SecurityEvent,
    SecurityEventType,
    SecurityLogger,
)
from linuxtools.config import (
    ConfigManager,
    ConfigLoader,
    FileConfigLoader,
    ConfigurationManager,
    XdgAppConfig,
)
from linuxtools.filesystem import (
    FileManager,
    LinuxFileManager,
    FileBackup,
    LinuxFileBackup
)
from linuxtools.systemd import (
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
    # Installateur service + timer (sans script)
    ServiceTimerInstaller,
    SystemdServiceTimerInstaller,
    # Installateur mount + automount
    AutomountInstaller,
    SystemdAutomountInstaller,
    # Chargeurs de configuration
    ServiceConfigLoader,
    TimerConfigLoader,
    MountConfigLoader,
    AutomountSettings,
    BashScriptConfigLoader,
    # Export / restauration génériques
    SystemdUnitExporter,
    SystemdUnitRestorer,
    # Rétrocompatibilité
    LinuxSystemdServiceManager,
)
from linuxtools.integrity import (
    ChecksumCalculator,
    HashLibChecksumCalculator,
    IntegrityChecker,
    SHA256IntegrityChecker,
    calculate_checksum
)
from linuxtools.dotconf import (
    IniSection,
    IniConfig,
    IniConfigManager,
    ValidatedSection,
    LinuxIniConfigManager,
    SectionAwareEditor,
    parse_validator,
    build_validators,
)
from linuxtools.notification import (
    DesktopNotifier,
    ExecutionReport,
    GotifyNotifier,
    JournaldNotifier,
    Notification,
    NotificationConfig,
    NotificationError,
    NotificationSendError,
    Notifier,
    NotifierChain,
    SmtpEmailNotifier,
    StepResult,
    Urgency,
)
from linuxtools.scripts import (
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
from linuxtools.commands import (
    CommandResult,
    CommandExecutor,
    CommandBuilder,
    CommandFormatter,
    PlainCommandFormatter,
    AnsiCommandFormatter,
    LinuxCommandExecutor,
)
from linuxtools.validation import (
    Validator,
    PathChecker,
    PathCheckerPermission,
    PathCheckerWorldWritable,
    PathCheckerGroupAccess,
    SystemCommandValidator,
)
from linuxtools.credentials import (
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
from linuxtools.cli import CliCommand, CliApplication
from linuxtools.deploy import (
    CheckResult,
    DeployCommand,
    DeployConfig,
    Deployer,
    DeployPhase,
    DeployReport,
    DeployTarget,
    InstallVerifier,
    RsyncTransport,
    SshCommandExecutor,
    Transport,
    VenvInstaller,
    VerificationSpec,
    find_editable_source,
    find_project_source,
)
from linuxtools.identity import (
    GroupManagerBase,
    UserManagerBase,
    LinuxGroupManager,
    LinuxUserManager,
)
from linuxtools.network import (
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
    # Systemd - Installateur service + timer (sans script)
    "ServiceTimerInstaller",
    "SystemdServiceTimerInstaller",
    # Systemd - Installateur mount + automount
    "AutomountInstaller",
    "SystemdAutomountInstaller",
    # Systemd - Chargeurs de configuration
    "ServiceConfigLoader",
    "TimerConfigLoader",
    "MountConfigLoader",
    "AutomountSettings",
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
    "DesktopNotifier",
    "ExecutionReport",
    "GotifyNotifier",
    "JournaldNotifier",
    "Notification",
    "NotificationConfig",
    "NotificationError",
    "NotificationSendError",
    "Notifier",
    "NotifierChain",
    "SmtpEmailNotifier",
    "StepResult",
    "Urgency",
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
    # Deploy - Orchestrateur et configuration
    "Deployer",
    "DeployConfig",
    "DeployTarget",
    "VerificationSpec",
    "DeployReport",
    "DeployPhase",
    "CheckResult",
    # Deploy - Exécution et transport
    "SshCommandExecutor",
    "Transport",
    "RsyncTransport",
    # Deploy - Installation et vérification
    "VenvInstaller",
    "InstallVerifier",
    # Deploy - CLI
    "DeployCommand",
    # Deploy - Auto-détection
    "find_project_source",
    "find_editable_source",
]

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
- distro: Helpers spécifiques à une distribution (fedora_version) —
  seul module lié à une distribution, isolé volontairement
"""

__version__ = "1.14.0"

from linuxtools.cli import CliApplication, CliCommand
from linuxtools.commands import (
    AnsiCommandFormatter,
    CommandBuilder,
    CommandExecutor,
    CommandFormatter,
    CommandResult,
    LinuxCommandExecutor,
    PlainCommandFormatter,
)
from linuxtools.config import (
    ConfigLoader,
    ConfigManager,
    ConfigurationManager,
    FileConfigLoader,
    XdgAppConfig,
)
from linuxtools.credentials import (
    # Modeles
    Credential,
    # Chaine et facade
    CredentialChain,
    CredentialKey,
    CredentialManager,
    # Exceptions
    CredentialNotFoundError,
    # ABCs
    CredentialProvider,
    CredentialProviderUnavailableError,
    CredentialStore,
    CredentialStoreError,
    DotEnvCredentialProvider,
    # Providers
    EnvCredentialProvider,
    KeyringCredentialProvider,
)
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
from linuxtools.distro import (
    fedora_version,
)
from linuxtools.dotconf import (
    IniConfig,
    IniConfigManager,
    IniSection,
    LinuxIniConfigManager,
    SectionAwareEditor,
    ValidatedSection,
    build_validators,
    parse_validator,
)
from linuxtools.filesystem import (
    FileBackup,
    FileManager,
    LinuxFileBackup,
    LinuxFileManager,
)
from linuxtools.identity import (
    GroupManagerBase,
    LinuxGroupManager,
    LinuxUserManager,
    UserManagerBase,
)
from linuxtools.integrity import (
    ChecksumCalculator,
    HashLibChecksumCalculator,
    IntegrityChecker,
    SHA256IntegrityChecker,
    calculate_checksum,
)
from linuxtools.logging import (
    ConsoleLogger,
    FileLogger,
    Logger,
    SecurityEvent,
    SecurityEventType,
    SecurityLogger,
)
from linuxtools.network import (
    # Rapports
    ConsoleTableReporter,
    CsvReporter,
    DeviceReporter,
    DeviceRepository,
    DhcpRange,
    DhcpReservationManager,
    DiffReporter,
    DnsConfig,
    DnsManager,
    # Repository
    JsonDeviceRepository,
    JsonReporter,
    # Scanners
    LinuxArpScanner,
    # DHCP
    LinuxDhcpReservationManager,
    LinuxDnsmasqConfigGenerator,
    # DNS
    LinuxHostsFileManager,
    LinuxNmapScanner,
    # Configuration
    NetworkConfig,
    # Modeles
    NetworkDevice,
    # ABCs
    NetworkScanner,
    validate_cidr,
    validate_hostname,
    # Validateurs
    validate_ipv4,
    validate_mac,
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
    BashScriptInstaller,
    CliInstaller,
    InstallReport,
    LinuxCliInstaller,
    LinuxScriptChecker,
    MissingDependency,
    PythonCliConfig,
    ScriptChecker,
    ScriptInstaller,
    ScriptPaths,
)
from linuxtools.systemd import (
    AutomountConfig,
    # Installateur mount + automount
    AutomountInstaller,
    AutomountSettings,
    BashScriptConfigLoader,
    # Implémentations système
    LinuxMountUnitManager,
    LinuxServiceUnitManager,
    LinuxTimerUnitManager,
    LinuxUserServiceUnitManager,
    # Implémentations utilisateur
    LinuxUserTimerUnitManager,
    # Configurations
    MountConfig,
    MountConfigLoader,
    MountUnitManager,
    # Installateur de tâches planifiées
    ScheduledTaskInstaller,
    ServiceConfig,
    # Chargeurs de configuration
    ServiceConfigLoader,
    # Installateur service + timer (sans script)
    ServiceTimerInstaller,
    ServiceUnitManager,
    SystemdAutomountInstaller,
    # Exécuteurs systemctl
    SystemdExecutor,
    SystemdScheduledTaskInstaller,
    SystemdServiceTimerInstaller,
    # Export / restauration génériques
    SystemdUnitExporter,
    SystemdUnitRestorer,
    TimerConfig,
    TimerConfigLoader,
    TimerUnitManager,
    # Classes abstraites système
    UnitManager,
    UserServiceUnitManager,
    UserSystemdExecutor,
    UserTimerUnitManager,
    # Classes abstraites utilisateur
    UserUnitManager,
)
from linuxtools.validation import (
    PathChecker,
    PathCheckerGroupAccess,
    PathCheckerPermission,
    PathCheckerWorldWritable,
    SystemCommandValidator,
    Validator,
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
    # Identity
    "GroupManagerBase",
    "UserManagerBase",
    "LinuxGroupManager",
    "LinuxUserManager",
    # Distro - Helpers Fedora / RPM
    "fedora_version",
]

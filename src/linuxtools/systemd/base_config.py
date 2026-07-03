"""Dataclasses de configuration pour les unités systemd."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import ClassVar

from linuxtools.systemd.validators import (
    path_to_unit_name as _path_to_unit_name,
    reject_control_chars,
)


def _optional_line(label: str, value: str, field_name: str) -> str | None:
    """Retourne une ligne INI optionnelle ou None si la valeur est vide.

    Args:
        label: Clé INI (ex: ``OnCalendar``).
        value: Valeur du champ ; ignorée si vide.
        field_name: Nom du champ pour reject_control_chars.

    Returns:
        ``"label=value"`` ou None.

    Raises:
        ValueError: Si value contient un caractère de contrôle.
    """
    if not value:
        return None
    return f"{label}={reject_control_chars(value, field_name)}"


@dataclass(frozen=True)
class BaseSystemdConfig:
    """Configuration de base pour une unité systemd.

    Attributes:
        description: Description de l'unité pour systemd.
        created_at: Horodatage automatique de la création de la configuration.
    """

    description: str
    created_at: datetime = field(
        default_factory=datetime.now, compare=False, kw_only=True
    )


@dataclass(frozen=True)
class MountConfig(BaseSystemdConfig):
    """Configuration pour une unité .mount systemd.

    Attributes:
        what: Source du montage (ex: "192.168.1.10:/share", "//server/share").
        where: Chemin du point de montage local.
        type: Type de système de fichiers (nfs, cifs, sshfs, ext4, etc.).
        options: Options de montage (défaut: chaîne vide).
    """

    _DEVICE_FS: ClassVar[frozenset[str]] = frozenset({
        "ext4", "ext3", "xfs", "btrfs", "vfat", "ntfs"
    })

    what: str
    where: str
    type: str
    options: str = ""

    def __post_init__(self) -> None:
        """Valide que les champs requis sont présents et cohérents."""
        if not self.what or not self.where:
            raise ValueError("'what' et 'where' sont requis")
        if not self.where.startswith("/"):
            raise ValueError(
                f"'where' doit être un chemin absolu : {self.where!r}"
            )
        self._validate_what()

    def _validate_what(self) -> None:
        """Valide le champ 'what' selon le type de montage."""
        fs_type = self.type.lower()
        if fs_type in ("nfs", "nfs4"):
            if ":" not in self.what or self.what.startswith(":"):
                raise ValueError(
                    f"Format NFS invalide pour 'what' : {self.what!r}"
                    " (attendu : host:/path)"
                )
        elif fs_type == "cifs":
            if not self.what.startswith("//"):
                raise ValueError(
                    f"Format CIFS invalide pour 'what' : {self.what!r}"
                    " (attendu : //host/share)"
                )
        elif fs_type in self._DEVICE_FS:
            if not self.what.startswith("/dev/"):
                raise ValueError(
                    f"'what' doit être un device pour {fs_type} : "
                    f"{self.what!r} (attendu : /dev/...)"
                )

    @property
    def unit_name(self) -> str:
        """Convertit le chemin de montage en nom d'unité systemd.

        Exemple: /media/nas/backup → media-nas-backup

        Returns:
            Nom de l'unité systemd (sans extension).
        """
        return _path_to_unit_name(self.where)

    def to_unit_file(self) -> str:
        """Génère le contenu d'un fichier .mount systemd.

        Returns:
            Contenu du fichier .mount.

        Raises:
            ValueError: Si un champ contient un caractère de contrôle.
        """
        desc = reject_control_chars(self.description, "description")
        what = reject_control_chars(self.what, "what")
        where = reject_control_chars(self.where, "where")
        fs_type = reject_control_chars(self.type, "type")
        options_line = (
            f"Options={reject_control_chars(self.options, 'options')}\n"
            if self.options else ""
        )
        return f"""[Unit]
Description={desc}
DefaultDependencies=no
After=network-online.target nss-lookup.target
Requires=network-online.target
Wants=nss-lookup.target
StartLimitIntervalSec=120
StartLimitBurst=5

[Mount]
What={what}
Where={where}
Type={fs_type}
{options_line}
TimeoutSec=30

[Install]
WantedBy=remote-fs.target
"""


@dataclass(frozen=True)
class AutomountConfig(BaseSystemdConfig):
    """Configuration pour une unité .automount systemd.

    Attributes:

        where: Chemin du point de montage local.
        timeout_idle_sec: Délai d'inactivité avant démontage automatique
            en secondes (0 = pas de démontage automatique).
    """

    where: str
    timeout_idle_sec: int = 0

    def __post_init__(self) -> None:
        """Valide que les champs requis sont présents."""
        if not self.where:
            raise ValueError("'where' est requis")
        if not self.where.startswith("/"):
            raise ValueError(
                f"'where' doit être un chemin absolu : {self.where!r}"
            )

    @property
    def unit_name(self) -> str:
        """Convertit le chemin de montage en nom d'unité systemd.

        Exemple: /media/nas/backup → media-nas-backup

        Returns:
            Nom de l'unité systemd (sans extension).
        """
        return _path_to_unit_name(self.where)

    def to_unit_file(self) -> str:
        """Génère le contenu d'un fichier .automount systemd.

        Returns:
            Contenu du fichier .automount.

        Raises:
            ValueError: Si un champ contient un caractère de contrôle.
        """
        desc = reject_control_chars(self.description, "description")
        where = reject_control_chars(self.where, "where")
        timeout_line = ""
        if self.timeout_idle_sec > 0:
            timeout_line = f"TimeoutIdleSec={self.timeout_idle_sec}\n"
        return f"""[Unit]
Description=Automontage {desc}
DefaultDependencies=no
ConditionPathExists={where}

[Automount]
Where={where}
{timeout_line}
DirectoryMode=0750

[Install]
WantedBy=remote-fs.target
"""


@dataclass(frozen=True)
class TimerConfig(BaseSystemdConfig):
    """Configuration pour une unité .timer systemd.

    Attributes:
        unit: Nom de l'unité à déclencher (ex: "backup.service").
        on_calendar: Expression de calendrier (ex: "daily", "*-*-* 06:00:00").
        on_boot_sec: Délai après le démarrage (ex: "5min").
        on_unit_active_sec: Délai après la dernière activation de l'unité.
        persistent: Rattraper les exécutions manquées après un arrêt.
        randomized_delay_sec: Délai aléatoire ajouté (ex: "1h").
    """

    unit: str
    on_calendar: str = ""
    on_boot_sec: str = ""
    on_unit_active_sec: str = ""
    persistent: bool = False
    randomized_delay_sec: str = ""

    def __post_init__(self) -> None:
        """Valide que les champs requis sont présents."""
        if not self.unit:
            raise ValueError("'unit' est requis")

    @property
    def timer_name(self) -> str:
        """Extrait le nom du timer depuis le nom de l'unité cible.

        Exemple: backup.service → backup

        Returns:
            Nom du timer (sans extension).
        """
        return self.unit.rsplit(".", 1)[0]

    def to_unit_file(self) -> str:
        """Génère le contenu d'un fichier .timer systemd.

        Returns:
            Contenu du fichier .timer.

        Raises:
            ValueError: Si un champ contient un caractère de contrôle.
        """
        lines = [
            "[Unit]",
            f"Description="
            f"{reject_control_chars(self.description, 'description')}",
            "",
            "[Timer]",
            f"Unit={reject_control_chars(self.unit, 'unit')}",
        ]

        lines.extend(filter(None, [
            _optional_line("OnCalendar", self.on_calendar, "on_calendar"),
            _optional_line("OnBootSec", self.on_boot_sec, "on_boot_sec"),
            _optional_line(
                "OnUnitActiveSec",
                self.on_unit_active_sec,
                "on_unit_active_sec",
            ),
            "Persistent=true" if self.persistent else None,
            _optional_line(
                "RandomizedDelaySec",
                self.randomized_delay_sec,
                "randomized_delay_sec",
            ),
        ]))

        lines.extend([
            "",
            "[Install]",
            "WantedBy=timers.target",
        ])

        return "\n".join(lines) + "\n"


@dataclass(frozen=True)
class ServiceConfig(BaseSystemdConfig):
    """Configuration pour une unité .service systemd.

    Attributes:
        exec_start: Commande à exécuter au démarrage.
        type: Type de service (simple, oneshot, forking, notify, dbus, idle).
        user: Utilisateur sous lequel exécuter le service.
        group: Groupe sous lequel exécuter le service.
        working_directory: Répertoire de travail.
        environment: Variables d'environnement (dict).
        restart: Politique de redémarrage (no, always, on-failure, etc.).
        restart_sec: Délai avant redémarrage en secondes.
        wanted_by: Cible d'installation (défaut: multi-user.target).
    """

    _VALID_TYPES: ClassVar[tuple[str, ...]] = (
        "simple", "exec", "forking", "oneshot",
        "dbus", "notify", "idle",
    )
    _VALID_RESTART: ClassVar[tuple[str, ...]] = (
        "no", "always", "on-success", "on-failure",
        "on-abnormal", "on-abort", "on-watchdog",
    )

    exec_start: str
    type: str = "simple"
    user: str = ""
    group: str = ""
    working_directory: str = ""
    environment: dict[str, str] = field(default_factory=dict)
    restart: str = "no"
    restart_sec: int = 0
    wanted_by: str = "multi-user.target"

    def __post_init__(self) -> None:
        """Valide que les champs requis sont présents et cohérents."""
        if not self.exec_start:
            raise ValueError("'exec_start' est requis")
        if self.type not in self._VALID_TYPES:
            raise ValueError(
                f"Type de service invalide : {self.type!r} "
                f"(valeurs acceptées : {', '.join(self._VALID_TYPES)})"
            )
        if self.restart not in self._VALID_RESTART:
            raise ValueError(
                f"Politique de redémarrage invalide : {self.restart!r} "
                f"(valeurs acceptées : "
                f"{', '.join(self._VALID_RESTART)})"
            )
        self._validate_environment()

    def _validate_environment(self) -> None:
        """Valide les variables d'environnement contre l'injection."""
        for key, value in self.environment.items():
            if "\n" in key or "=" in key:
                raise ValueError(
                    f"Clé d'environnement invalide : {key!r}"
                )
            if "\n" in value:
                raise ValueError(
                    f"Valeur d'environnement invalide pour "
                    f"{key!r} : retour à la ligne interdit"
                )

    def to_unit_file(self) -> str:
        """Génère le contenu d'un fichier .service systemd.

        Returns:
            Contenu du fichier .service.

        Raises:
            ValueError: Si un champ contient un caractère de contrôle.
        """
        lines = [
            "[Unit]",
            f"Description="
            f"{reject_control_chars(self.description, 'description')}",
            "",
            "[Service]",
            f"Type={self.type}",
            f"ExecStart="
            f"{reject_control_chars(self.exec_start, 'exec_start')}",
        ]

        lines.extend(filter(None, [
            _optional_line("User", self.user, "user"),
            _optional_line("Group", self.group, "group"),
            _optional_line(
                "WorkingDirectory",
                self.working_directory,
                "working_directory",
            ),
        ]))

        for key, value in self.environment.items():
            lines.append(f"Environment={key}={value}")

        if self.restart != "no":
            lines.append(f"Restart={self.restart}")
            if self.restart_sec > 0:
                lines.append(f"RestartSec={self.restart_sec}")

        lines.extend([
            "",
            "[Install]",
            f"WantedBy="
            f"{reject_control_chars(self.wanted_by, 'wanted_by')}",
        ])

        return "\n".join(lines) + "\n"

"""Structures de données du module deploy.

Ce module définit les dataclasses immuables décrivant une cible de
déploiement, sa configuration, les vérifications post-install
déclaratives et le compte rendu final.

Example:
    Configuration minimale pour un déploiement local :

        from pathlib import Path
        from linuxtools.deploy import DeployConfig, VerificationSpec

        config = DeployConfig(
            source_dir=Path("/home/user/mon-outil"),
            venv_path=Path("/opt/mon-outil/venv"),
            remote_source_dir=Path("/opt/mon-outil/src"),
            verification=VerificationSpec(
                imports=("mon_outil",),
                subcommands=("--version",),
            ),
        )
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from pathlib import Path

    from linuxtools.systemd import ServiceConfig, TimerConfig


class DeployPhase(Enum):
    """Phases du déploiement, dans l'ordre d'exécution."""

    TRANSPORT = "transport"
    BACKUP = "backup"
    INSTALL = "install"
    VERIFY = "verify"
    ROLLBACK = "rollback"
    CONFIG = "config"
    SECRETS = "secrets"
    TIMER = "timer"
    DONE = "done"


@dataclass(frozen=True)
class DeployTarget:
    """Décrit l'hôte cible du déploiement.

    Attributes:
        host: Nom/IP de l'hôte distant, ou None pour une cible locale.
        user: Utilisateur SSH (ignoré si host est None).
        ssh_options: Options ssh supplémentaires (ex. ["-p", "2222"]).
    """

    host: str | None = None
    user: str | None = None
    ssh_options: tuple[str, ...] = ()

    @property
    def is_remote(self) -> bool:
        """True si la cible est distante (host renseigné)."""
        return self.host is not None

    @property
    def ssh_destination(self) -> str:
        """Retourne 'user@host' ou 'host' pour ssh/rsync.

        Returns:
            Destination formatée pour ssh/rsync.

        Raises:
            ValueError: Si appelé sur une cible locale.
        """
        if not self.is_remote:
            raise ValueError(
                "ssh_destination requiert une cible distante"
                " (host non renseigné)"
            )
        if self.user:
            return f"{self.user}@{self.host}"
        return str(self.host)


@dataclass(frozen=True)
class VerificationSpec:
    """Vérifications post-install déclaratives.

    Attributes:
        imports: Modules à importer (ex. ("linuxtools.notification",)).
        subcommands: Sous-commandes attendues, testées via `<cli_bin>
            <subcmd> --help` (ex. ("borg-info", "list")).
        regression_command: Commande de non-régression à rejouer, ou
            None. Exécutée telle quelle sur l'hôte cible.
    """

    imports: tuple[str, ...] = ()
    subcommands: tuple[str, ...] = ()
    regression_command: tuple[str, ...] | None = None


@dataclass(frozen=True)
class ConfigDeploySpec:
    """Spécification de dépôt d'un fichier de config TOML sur la cible.

    Attributes:
        data: Données de configuration à sérialiser en TOML.
        dest_path: Chemin de destination sur la cible.
        mode: Permissions POSIX du fichier déposé (défaut 0o644).
    """

    data: dict[str, object]
    dest_path: Path
    mode: int = 0o644


@dataclass(frozen=True)
class SecretsSpec:
    """Spécification de provisioning de secrets vers la cible.

    Attributes:
        service: Nom du service CredentialManager (ex. "pihole").
        keys: Clés à résoudre et écrire (ex. ("GOTIFY_TOKEN",)).
        dest_path: Chemin du fichier EnvironmentFile= sur la cible.
        mode: Permissions POSIX du fichier déposé (défaut 0o600).
    """

    service: str
    keys: tuple[str, ...]
    dest_path: Path
    mode: int = 0o600


@dataclass(frozen=True)
class TimerDeploySpec:
    """Spécification d'installation d'un couple service+timer systemd.

    Attributes:
        unit_name: Nom de l'unité (service et timer, sans extension).
        service_config: Configuration du service, déjà construite par
            l'appelant (dataclasses ServiceConfig — cf. CDC Q-03).
        timer_config: Configuration du timer.
        scope: Portée d'installation — "system" (défaut,
            /etc/systemd/system/, nécessite root) ou "user"
            (~/.config/systemd/user/, systemctl --user, sans
            élévation de privilèges).
    """

    unit_name: str
    service_config: ServiceConfig
    timer_config: TimerConfig
    scope: Literal["system", "user"] = "system"


@dataclass(frozen=True)
class DeployConfig:
    """Configuration complète d'un déploiement/màj.

    Attributes:
        source_dir: Répertoire source local (clone du projet). Si
            None, auto-détecté via discovery.find_project_source()
            (V1).
        venv_path: Venv cible sur l'hôte (ex. /opt/app/venv).
        remote_source_dir: Où déposer le source sur l'hôte cible.
        target: Description de l'hôte (local ou distant).
        verification: Vérifs post-install déclaratives.
        cli_bin: Chemin/nom de l'exécutable CLI dans le venv, pour
            tester les sous-commandes (ex. "borg-manager").
        recreate_venv: Si True, recrée le venv proprement
            (Could, V1=False).
        config_deploy: Spécification de dépôt de config TOML, ou None
            pour ne pas exécuter cette phase (no-op).
        secrets: Spécification de provisioning de secrets, ou None
            pour ne pas exécuter cette phase (no-op).
        timer_deploy: Spécification d'installation service+timer, ou
            None pour ne pas exécuter cette phase (no-op).
    """

    source_dir: Path | None
    venv_path: Path
    remote_source_dir: Path
    target: DeployTarget = field(default_factory=DeployTarget)
    verification: VerificationSpec = field(
        default_factory=VerificationSpec
    )
    cli_bin: str | None = None
    recreate_venv: bool = False
    config_deploy: ConfigDeploySpec | None = None
    secrets: SecretsSpec | None = None
    timer_deploy: TimerDeploySpec | None = None


@dataclass(frozen=True)
class CheckResult:
    """Résultat d'une vérification unitaire.

    Attributes:
        label: Description lisible (ex. "import linuxtools.notification").
        ok: True si la vérification passe.
        detail: Message d'erreur ou complément (stderr tronqué).
    """

    label: str
    ok: bool
    detail: str = ""


@dataclass(frozen=True)
class DeployReport:
    """Compte rendu complet d'un déploiement.

    Attributes:
        success: True si toutes les phases ont réussi.
        phase_reached: Dernière phase atteinte.
        checks: Résultats des vérifications.
        rolled_back: True si un rollback a été effectué.
        backup_path: Chemin du venv de sauvegarde, ou None.
        messages: Journal des étapes (pour format_summary).
    """

    success: bool
    phase_reached: DeployPhase
    checks: tuple[CheckResult, ...] = ()
    rolled_back: bool = False
    backup_path: Path | None = None
    messages: tuple[str, ...] = ()

    def format_summary(self) -> str:
        """Rend un résumé multi-ligne lisible du déploiement.

        Returns:
            Chaîne multiligne avec statut, phase atteinte, résultats
            des vérifications et éventuel rollback.
        """
        status = "✓ Succès" if self.success else "✗ Échec"
        lines = [
            status,
            f"  Phase atteinte : {self.phase_reached.value}",
        ]

        if self.checks:
            ok_count = sum(1 for c in self.checks if c.ok)
            lines.append(
                f"  Vérifications : {ok_count}/{len(self.checks)}"
                " passées"
            )
            for check in self.checks:
                symbol = "✓" if check.ok else "✗"
                detail = f" ({check.detail})" if check.detail else ""
                lines.append(f"    {symbol} {check.label}{detail}")

        if self.rolled_back:
            lines.append(
                f"  ⚠ Rollback effectué (backup : {self.backup_path})"
            )

        for message in self.messages:
            lines.append(f"  {message}")

        return "\n".join(lines)

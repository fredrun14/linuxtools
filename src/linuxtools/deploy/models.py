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
from pathlib import Path


class DeployPhase(Enum):
    """Phases du déploiement, dans l'ordre d'exécution."""

    TRANSPORT = "transport"
    BACKUP = "backup"
    INSTALL = "install"
    VERIFY = "verify"
    ROLLBACK = "rollback"
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

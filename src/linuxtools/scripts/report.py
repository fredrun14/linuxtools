"""Rapport de déploiement pour les scripts CLI Python.

Ce module fournit des dataclasses pour conserver le résultat
d'une installation : statut, chemin, dépendances satisfaites
ou manquantes, et commande de remédiation.

Typical usage example:

    report = InstallReport(
        success=True,
        app_name="mon-app",
        deploy_type="user",
        install_path=Path("/home/user/.local/bin/mon-app"),
        total_deps=3,
    )
    print(report.format_summary())
"""

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class InstalledDependency:
    """Représente une dépendance satisfaite lors de la vérification.

    Attributes:
        package: Nom du paquet installé.
        location: Chemin d'installation (répertoire source ou site-packages).
    """

    package: str
    location: str


@dataclass
class MissingDependency:
    """Représente une dépendance manquante lors de la vérification.

    Attributes:
        package: Nom du paquet manquant.
        required: Contrainte de version requise (ex. '>=2.0').
        reason: Raison de l'absence.
    """

    package: str
    required: str
    reason: str = "non installé"


@dataclass
class InstallReport:
    """Rapport de déploiement d'un script CLI Python.

    Conserve le résultat complet d'une installation : succès,
    chemin d'installation, dépendances vérifiées et commande
    de remédiation suggérée.

    Attributes:
        success: True si le déploiement s'est terminé sans erreur.
        app_name: Nom de l'application déployée.
        deploy_type: Portée du déploiement ('system' ou 'user').
        install_path: Chemin du script ou wrapper installé.
        missing_deps: Liste des dépendances manquantes.
        total_deps: Nombre total de dépendances vérifiées.
        install_command: Commande pip suggérée pour les manquants.
        warnings: Avertissements non bloquants.

    Example:
        >>> report = InstallReport(
        ...     success=True,
        ...     app_name="mon-app",
        ...     deploy_type="user",
        ...     install_path=Path("/home/user/.local/bin/mon-app"),
        ... )
        >>> report.deps_satisfied
        True
    """

    success: bool
    app_name: str
    deploy_type: str
    install_path: Path
    missing_deps: list[MissingDependency] = field(default_factory=list)
    installed_deps: list[InstalledDependency] = field(default_factory=list)
    total_deps: int = 0
    install_command: str = ""
    warnings: list[str] = field(default_factory=list)

    @property
    def deps_satisfied(self) -> bool:
        """Retourne True si toutes les dépendances sont installées."""
        return len(self.missing_deps) == 0

    def format_summary(self) -> str:
        """Retourne un résumé textuel lisible du rapport.

        Returns:
            Chaîne multiligne avec statut, chemin d'installation,
            dépendances et avertissements éventuels.
        """
        status = "✓ Succès" if self.success else "✗ Échec"
        lines = [
            status,
            f"  Application : {self.app_name} ({self.deploy_type})",
            f"  Installé dans : {self.install_path}",
        ]

        if self.total_deps > 0:
            satisfied = self.total_deps - len(self.missing_deps)
            lines.append(
                f"  Dépendances : {satisfied}/{self.total_deps}"
                " satisfaites"
            )
            for dep in self.installed_deps:
                lines.append(
                    f"    ✓ {dep.package}  ({dep.location})"
                )
            for missing in self.missing_deps:
                lines.append(
                    f"    ✗ {missing.package} {missing.required}"
                    f" ({missing.reason})"
                )
            if self.install_command:
                lines.append(
                    f"  Commande : {self.install_command}"
                )

        for warning in self.warnings:
            lines.append(f"  ⚠ {warning}")

        return "\n".join(lines)
